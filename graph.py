"""
graph.py - LangGraph RAG 对话主流程
高并发、低延迟的记忆增强对话系统
"""

import os
import json
import asyncio
from typing import TypedDict, Annotated, List, Dict, Optional, Literal
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    BaseMessage
)
from langchain_core.runnables import RunnableConfig
from supabase import create_client, Client

from llm_factory import get_system_llm, get_user_llm
from perception import process_attachment
from relation_entity_handler import RelationEntityHandler, RELATION_CONFIGS

load_dotenv()


# =============================================================================
# 状态定义
# =============================================================================

class GraphState(TypedDict):
    """LangGraph 状态定义"""
    # 输入
    user_input: str
    attachments: List[Dict]  # [{"url": "...", "mime_type": "..."}]
    session_id: str

    # 感知输出
    perception_result: Optional[str]

    # 路由决策
    intent: Literal["CASUAL", "PERSONAL_QUERY", "WORK_QUERY", "TASK", "FOLLOW_UP"]

    # 对话历史（用于跟进检测）
    session_history: List[Dict]  # 最近几轮对话记录

    # 认知 Router 输出
    search_strategy: Dict  # 搜索策略（时间扩展、优先级路径等）
    cognitive_context: Dict  # 认知上下文（时间推理、关系推理等）
    is_follow_up: bool  # 是否是跟进问题

    # 检索结果
    global_context: Dict  # L2 Profile + L3 Pinned
    retrieved_entities: List[Dict]  # Vector/Path 搜索结果

    # 生成
    messages: List[BaseMessage]
    response: Optional[str]

    # 元数据
    metadata: Dict


# =============================================================================
# 初始化
# =============================================================================

@dataclass
class MemOSConfig:
    """MemOS 配置"""
    supabase_url: str = os.getenv("SUPABASE_URL")
    supabase_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # 检索配置
    vector_top_k: int = 5
    path_search_limit: int = 5
    pinned_limit: int = 5

    # 历史消息长度
    max_history: int = 5


class MemOSGraph:
    """MemOS LangGraph 主流程"""

    def __init__(self):
        self.config = MemOSConfig()
        self.supabase: Client = create_client(
            self.config.supabase_url,
            self.config.supabase_key
        )
        self.system_llm = get_system_llm()
        self.user_llm = get_user_llm()
        self.graph = self._build_graph()
        # Session 历史存储（内存中）
        self._session_histories: Dict[str, List[Dict]] = {}
        # 关系实体处理器
        self.relation_handler = RelationEntityHandler(self.supabase)
        # 会话级别的待确认关系状态 {session_id: {relation_key, display_name, ask_count}}
        self._session_pending_relations: Dict[str, Dict] = {}

    def _get_session_history(self, session_id: str) -> List[Dict]:
        """获取会话历史"""
        return self._session_histories.get(session_id, [])

    def _update_session_history(self, session_id: str, user_input: str,
                                response: str, intent: str):
        """更新会话历史"""
        if session_id not in self._session_histories:
            self._session_histories[session_id] = []

        self._session_histories[session_id].append({
            "user_input": user_input,
            "response": response,
            "intent": intent,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # 限制历史长度
        if len(self._session_histories[session_id]) > self.config.max_history:
            self._session_histories[session_id] = self._session_histories[session_id][-self.config.max_history:]

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 流程图"""

        workflow = StateGraph(GraphState)

        # 添加节点
        workflow.add_node("relation_check", self.node_relation_check)
        workflow.add_node("input_perception", self.node_input_perception)
        workflow.add_node("router", self.node_router)
        workflow.add_node("load_global_context", self.node_load_global_context)
        workflow.add_node("deep_search", self.node_deep_search)
        workflow.add_node("generate", self.node_generate)

        # 设置入口
        workflow.set_entry_point("relation_check")

        # 条件边: Relation Check -> 如果需要追问，直接结束；否则继续
        workflow.add_conditional_edges(
            "relation_check",
            self.check_early_return,
            {
                "early_return": END,
                "continue": "input_perception",
            }
        )

        # 边: Input -> Router
        workflow.add_edge("input_perception", "router")

        # 条件边: Router 决策
        # 返回: deep_search (需要检索) 或 load_global_context (跳过检索)
        workflow.add_conditional_edges(
            "router",
            self.decide_intent,
            {
                "deep_search": "deep_search",
                "load_global_context": "load_global_context",
            }
        )

        # 边: Deep Search -> Load Global (并行后合并)
        workflow.add_edge("deep_search", "load_global_context")

        # 边: Global Context -> Generate
        workflow.add_edge("load_global_context", "generate")

        # 边: Generate -> END
        workflow.add_edge("generate", END)

        return workflow.compile()

    def check_early_return(self, state: GraphState):
        """检查是否需要提前返回（追问用户）"""
        metadata = state.get("metadata", {})
        if metadata.get("early_return"):
            # 保存AI回复到L0（记录追问历史）
            try:
                self._save_to_l0_buffer(
                    role="ai",
                    content=state.get("response", ""),
                    attachments=[],
                    perception="追问用户关系映射"
                )
            except Exception as e:
                print(f"[WARN] 保存追问回复到L0失败: {e}")
            return "early_return"
        return "continue"

    # =========================================================================
    # Node 1: Input & Perception
    # =========================================================================

    async def node_input_perception(self, state: GraphState) -> GraphState:
        """
        处理用户输入和附件
        - 如果有附件，调用 perception.py 转录
        - 将描述存入 L0 Buffer
        """
        user_input = state["user_input"]
        attachments = state.get("attachments", [])
        perception_parts = []

        # 处理附件（并行）
        if attachments:
            tasks = []
            for att in attachments:
                task = asyncio.create_task(
                    self._process_attachment_async(
                        att.get("url"),
                        att.get("mime_type")
                    )
                )
                tasks.append(task)

            # 等待所有附件处理完成
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    perception_parts.append(f"[附件 {i+1} 处理失败]")
                else:
                    perception_parts.append(f"[附件 {i+1}]: {result}")

        # 存入 L0 Buffer - 所有用户输入（无论是否有附件）都要保存
        print(f"[DEBUG] 正在保存user消息到L0: {user_input[:50]}...")
        self._save_to_l0_buffer(
            role="user",
            content=user_input,
            attachments=attachments,
            perception="\n".join(perception_parts)
        )

        # 构建增强输入
        enhanced_input = user_input
        if perception_parts:
            enhanced_input += "\n\n[附件描述]\n" + "\n".join(perception_parts)

        # 使用增强后的输入（包含附件描述）
        enhanced_input = user_input
        if perception_parts:
            enhanced_input += "\n\n[附件描述]\n" + "\n".join(perception_parts)

        return {
            **state,
            "user_input": enhanced_input,  # 更新为增强后的输入
            "perception_result": "\n".join(perception_parts) if perception_parts else None,
            "metadata": {
                **state.get("metadata", {}),
                "has_attachments": len(attachments) > 0,
                "timestamp": datetime.utcnow().isoformat(),
            }
        }

    async def _process_attachment_async(self, url: str, mime_type: str) -> str:
        """异步处理附件"""
        # 在线程池中运行同步的 process_attachment
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, process_attachment, url, mime_type
        )

    def _save_to_l0_buffer(self, role: str, content: str,
                          attachments: List[Dict], perception: str):
        """保存到 L0 Buffer"""
        try:
            meta_data = {
                "attachments": attachments,
                "perception": perception,
                "source": "graph_input",
            }

            print(f"[DEBUG] _save_to_l0_buffer: role={role}, content_len={len(content)}")
            result = self.supabase.table("mem_l0_buffer").insert({
                "role": role,
                "content": content,
                "meta_data": meta_data,
                "processed": False,
            }).execute()
            print(f"[DEBUG] L0保存成功: {result.data}")
        except Exception as e:
            print(f"[WARN] L0 Buffer 保存失败: {e}")
            import traceback
            traceback.print_exc()

    # =========================================================================
    # Node 1.5: Relation Checker - 关系实体检测
    # 检测用户是否提到关系但系统不知道具体是谁，需要追问
    # =========================================================================

    async def node_relation_check(self, state: GraphState) -> GraphState:
        """
        关系检测节点
        检测用户是否提到关系但系统不知道具体是谁
        """
        user_input = state["user_input"]
        session_id = state["session_id"]

        # 检查是否有待确认的关系（用户之前被追问过）
        pending = self._session_pending_relations.get(session_id)
        if pending:
            # 用户可能回答了姓名，尝试提取
            name = self.relation_handler.extract_name_from_response(user_input)
            if name:
                # 创建关系映射
                result = self.relation_handler.create_relation_mapping(
                    pending["relation_key"],
                    name,
                    session_id
                )
                if result["success"]:
                    # 清除待确认状态
                    del self._session_pending_relations[session_id]
                    # 回复确认
                    relation_name = RELATION_CONFIGS[pending["relation_key"]].display_name
                    response = f"好嘞！{name}我记下了，以后你一说'{relation_name}'我就知道是谁啦！"
                    return {
                        **state,
                        "response": response,
                        "intent": "CASUAL",
                        "metadata": {**state.get("metadata", {}), "early_return": True, "relation_mapped": True}
                    }
            else:
                # 用户还是没告诉名字，增加询问次数
                pending["ask_count"] += 1
                if pending["ask_count"] >= 2:
                    # 放弃追问
                    question = self.relation_handler._generate_question(
                        pending["relation_key"], "give_up"
                    )
                    del self._session_pending_relations[session_id]
                    return {
                        **state,
                        "response": question,
                        "intent": "CASUAL",
                        "metadata": {**state.get("metadata", {}), "early_return": True, "give_up": True}
                    }
                else:
                    # 继续追问
                    question = self.relation_handler._generate_question(
                        pending["relation_key"], "retry_ask"
                    )
                    return {
                        **state,
                        "response": question,
                        "intent": "CASUAL",
                        "metadata": {**state.get("metadata", {}), "early_return": True}
                    }

        # 检查用户输入是否包含关系称呼
        user_input_lower = user_input.lower()
        for relation_key, config in RELATION_CONFIGS.items():
            # 检查是否提到该关系（使用同义词匹配）
            if any(synonym in user_input_lower for synonym in config.synonyms):
                # 查找是否已知对应的具体人物
                concrete_person = self.relation_handler.find_concrete_person(relation_key)
                if not concrete_person:
                    # 不知道是谁，需要追问
                    self._session_pending_relations[session_id] = {
                        "relation_key": relation_key,
                        "display_name": config.display_name,
                        "ask_count": 0
                    }
                    question = self.relation_handler._generate_question(relation_key, "first_ask")
                    print(f"[RelationCheck] 检测到关系 '{relation_key}'，追问用户")
                    return {
                        **state,
                        "response": question,
                        "intent": "CASUAL",
                        "metadata": {**state.get("metadata", {}), "early_return": True, "relation_unknown": True}
                    }
                else:
                    # 已知关系映射，记录日志
                    print(f"[RelationCheck] 关系 '{relation_key}' 对应 '{concrete_person['name']}'，正常处理")

        # 正常流程，继续
        return state

    # =========================================================================
    # Node 2: Cognitive Router v4 - 具备多维度推理能力
    # 上下文推理、时间推理、关系推理、场景推理、画像推理
    # =========================================================================

    async def node_router(self, state: GraphState) -> GraphState:
        """
        认知 Router - 多维度推理引擎
        1. 构建认知上下文（对话历史、用户画像、场景信息）
        2. 使用推理能力分析用户意图
        3. 生成检索策略建议
        """
        user_input = state["user_input"]
        session_history = state.get("session_history", [])

        # 步骤 1: 认知推理分析
        reasoning_result = await self._cognitive_reasoning(user_input, session_history)

        # 步骤 2: 基于推理结果生成检索策略
        intent = reasoning_result.get("intent", "CASUAL")
        is_follow_up = reasoning_result.get("is_follow_up", False)
        search_strategy = reasoning_result.get("search_strategy", {})

        print(f"[CognitiveRouter] 意图: {intent}, 跟进: {is_follow_up}")
        print(f"[CognitiveRouter] 推理: {reasoning_result.get('reasoning_summary', '')}")

        # 构建认知上下文（包含所有推理维度）
        cognitive_context = {
            "temporal_reasoning": reasoning_result.get("temporal_reasoning", {}),
            "relational_reasoning": reasoning_result.get("relational_reasoning", {}),
            "scenario_reasoning": reasoning_result.get("scenario_reasoning", {}),
            "profile_reasoning": reasoning_result.get("profile_reasoning", {}),
        }

        # 保存推理结果到 state，供后续节点使用
        return self._return_intent(
            state,
            intent,
            is_follow_up,
            search_strategy=search_strategy,
            cognitive_context=cognitive_context
        )

    async def _cognitive_reasoning(self, user_input: str, session_history: List[Dict]) -> Dict:
        """
        认知推理引擎 - 多维度推理分析
        """
        # 构建对话上下文
        context_text = self._build_conversation_context(session_history)

        # 认知推理 Prompt
        prompt = f"""你是一个认知推理引擎。分析用户输入，进行多维度推理，输出结构化的认知分析结果。

## 对话历史：
{context_text}

## 用户最新输入：
{user_input}

## 推理任务（Chain-of-Thought）：

### 1. 上下文推理 (Context Reasoning)
- 分析对话的连贯性和话题演变
- 判断用户是否在延续之前的话题
- 识别指代和省略的内容

### 2. 时间推理 (Temporal Reasoning)
- 提取用户查询中的时间信息（年份、月份、时间段）
- 分析时间关系（当前、过去、未来、区间）
- 判断是否需要时间区间匹配（如"2016年"可能落在"2010-2018"区间内）

### 3. 关系推理 (Relational Reasoning)
- 识别用户询问的关系类型（人物关系、工作关系、项目关系）
- 分析实体间的关联（公司-职位、学校-专业、人物-关系）

### 4. 场景推理 (Scenario Reasoning)
- 判断当前对话场景（闲聊、咨询、求助、回忆）
- 分析用户的情感状态和沟通意图
- 识别隐性需求

### 5. 画像推理 (Profile Reasoning)
- 基于历史推断用户的关注点和偏好
- 预测用户可能想了解的信息
- 识别信息缺口

## 输出格式（JSON）：
{{
    "context_reasoning": {{
        "is_follow_up": true/false,
        "topic_continuation": "话题延续性分析",
        "referencing": "指代解析"
    }},
    "temporal_reasoning": {{
        "time_mentioned": ["提取的时间信息"],
        "time_type": "point/range/duration",
        "needs_range_matching": true/false,
        "implied_time": "隐含的时间范围"
    }},
    "relational_reasoning": {{
        "entity_types": ["涉及的实体类型"],
        "relation_type": "关系类型",
        "inferred_entities": ["推断的相关实体"]
    }},
    "scenario_reasoning": {{
        "scenario": "场景类型",
        "user_emotion": "用户情感状态",
        "implicit_needs": ["隐性需求"]
    }},
    "profile_reasoning": {{
        "likely_interests": ["可能感兴趣的话题"],
        "information_gaps": ["信息缺口"],
        "suggested_topics": ["建议补充的话题"]
    }},
    "intent": "选择其中一个: CASUAL | PERSONAL_QUERY | WORK_QUERY | TASK",
    "intent_confidence": "high/medium/low",
    "intent_reasoning": "意图判断的完整推理过程",
    "reasoning_summary": "一句话总结",
    "dimensions_used": ["使用的推理维度"],
    "search_strategy": {{
        "primary_keywords": ["主要搜索关键词"],
        "time_expansion": true/false,
        "entity_expansion": ["需要扩展的实体"],
        "relation_depth": 1-3,
        "priority_paths": ["优先搜索路径"]
    }}
}}

只输出JSON，确保格式正确。"""

        try:
            response = await self.system_llm.ainvoke([
                HumanMessage(content=prompt)
            ])

            content = response.content.strip()

            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            import json
            result = json.loads(content.strip())

            return result

        except Exception as e:
            print(f"[WARN] 认知推理失败: {e}, 使用默认推断")

            # 基于关键词的简单推断（降级方案）
            query_lower = user_input.lower()

            # 判断是否为个人查询
            personal_keywords = ['爸', '妈', '父', '母', '生日', '年龄', '家人', '家庭', '我', '我的']
            work_keywords = ['工作', '公司', '职位', '职业', '项目', '技术']

            is_personal = any(kw in query_lower for kw in personal_keywords)
            is_work = any(kw in query_lower for kw in work_keywords)

            if is_personal:
                fallback_intent = "PERSONAL_QUERY"
                priority_paths = ["/people/"]
            elif is_work:
                fallback_intent = "WORK_QUERY"
                priority_paths = ["/work/", "/projects/"]
            elif session_history and len(user_input) < 20:
                # 可能是跟进问题
                fallback_intent = "PERSONAL_QUERY"
                priority_paths = ["/people/", "/work/"]
            else:
                fallback_intent = "CASUAL"
                priority_paths = []

            # 提取简单关键词
            keywords = [kw for kw in personal_keywords + work_keywords if kw in query_lower]
            if not keywords:
                keywords = [user_input[:10]]

            print(f"[WARN] 降级推断: intent={fallback_intent}, keywords={keywords}")

            return {
                "intent": fallback_intent,
                "is_follow_up": False,
                "reasoning_summary": f"认知推理失败，基于关键词推断为{fallback_intent}",
                "dimensions_used": ["keyword_fallback"],
                "search_strategy": {
                    "primary_keywords": keywords,
                    "time_expansion": "生日" in query_lower or "年" in query_lower,
                    "entity_expansion": [],
                    "relation_depth": 2,
                    "priority_paths": priority_paths
                }
            }

    def _build_conversation_context(self, session_history: List[Dict]) -> str:
        """构建对话上下文"""
        if not session_history:
            return "（无历史对话）"

        context_lines = []
        recent_history = session_history[-5:] if len(session_history) > 5 else session_history

        for i, turn in enumerate(recent_history):
            user_msg = turn.get("user_input", "")[:80]
            ai_msg = turn.get("response", "")[:80]
            intent = turn.get("intent", "UNKNOWN")

            if user_msg:
                context_lines.append(f"用户 [{intent}]: {user_msg}")
            if ai_msg:
                context_lines.append(f"AI: {ai_msg}")

        return "\n".join(context_lines)

    def _return_intent(self, state: GraphState, intent: str, is_follow_up: bool = False,
                       search_strategy: Dict = None, cognitive_context: Dict = None) -> GraphState:
        """返回意图结果"""
        result = {
            **state,
            "intent": intent,
            "is_follow_up": is_follow_up,
            "search_strategy": search_strategy or {},
            "cognitive_context": cognitive_context or {},
            "metadata": {
                **state.get("metadata", {}),
                "intent": intent,
                "is_follow_up": is_follow_up,
            }
        }
        return result

    def decide_intent(self, state: GraphState) -> Literal["deep_search", "load_global_context"]:
        """条件边决策函数"""
        intent = state["intent"]

        # 需要检索的意图（包含个人查询的各种变体）
        if intent in ["PERSONAL_QUERY", "WORK_QUERY", "TASK"] or "PERSONAL" in intent or "QUERY" in intent:
            return "deep_search"

        # CASUAL 和 FOLLOW_UP（非继承）跳过检索
        return "load_global_context"

    # =========================================================================
    # Node 3a: Load Global Context (Always)
    # =========================================================================

    async def node_load_global_context(self, state: GraphState) -> GraphState:
        """
        加载全局上下文（每次对话都加载）
        - L2 Profile (用户画像)
        - L3 Pinned Entities (Top 5)
        """
        # 并行加载
        profile_task = asyncio.create_task(self._load_l2_profile())
        pinned_task = asyncio.create_task(self._load_pinned_entities())

        profile, pinned = await asyncio.gather(profile_task, pinned_task)

        global_context = {
            "profile": profile,
            "pinned": pinned,
        }

        return {
            **state,
            "global_context": global_context,
        }

    async def _load_l2_profile(self) -> List[Dict]:
        """加载 L2 用户画像"""
        try:
            result = self.supabase.table("mem_l2_profile") \
                .select("*") \
                .eq("status", "active") \
                .order("confidence", desc=True) \
                .limit(10) \
                .execute()
            return result.data or []
        except Exception as e:
            print(f"[WARN] 加载 Profile 失败: {e}")
            return []

    async def _load_pinned_entities(self) -> List[Dict]:
        """加载置顶的 L3 Entities"""
        try:
            result = self.supabase.table("mem_l3_entities") \
                .select("path, name, description_md") \
                .eq("is_pinned", True) \
                .limit(self.config.pinned_limit) \
                .execute()
            return result.data or []
        except Exception as e:
            print(f"[WARN] 加载 Pinned 失败: {e}")
            return []

    # =========================================================================
    # Node 3b: Deep Search (Only for WORK)
    # =========================================================================

    async def node_deep_search(self, state: GraphState) -> GraphState:
        """
        深度搜索（认知增强搜索 3.0）
        利用认知 Router 的推理结果优化搜索策略
        """
        user_input = state["user_input"]
        intent = state.get("intent", "WORK_QUERY")
        search_strategy = state.get("search_strategy", {})
        cognitive_context = state.get("cognitive_context", {})

        print(f"[DeepSearch] Query: {user_input[:50]}..., Intent: {intent}")

        # 检查是否需要时间扩展搜索
        temporal_reasoning = cognitive_context.get("temporal_reasoning", {})
        needs_time_expansion = temporal_reasoning.get("needs_range_matching", False)
        time_mentioned = temporal_reasoning.get("time_mentioned", [])

        if needs_time_expansion and time_mentioned:
            print(f"[DeepSearch] 启用时间扩展搜索: {time_mentioned}")

        # 使用智能混合搜索（传入搜索策略）
        merged = await self._smart_search(
            user_input,
            intent,
            search_strategy=search_strategy,
            time_expansion=needs_time_expansion,
            time_mentioned=time_mentioned
        )

        print(f"[DeepSearch] Found {len(merged)} entities")
        for e in merged[:3]:
            fact_info = " [+fact]" if e.get('matched_fact') else ""
            print(f"  - {e.get('name')} ({e.get('path')}){fact_info}")

        return {
            **state,
            "retrieved_entities": merged,
            "metadata": {
                **state.get("metadata", {}),
                "total_entities": len(merged),
                "search_intent": intent,
                "time_expansion_used": needs_time_expansion,
            }
        }

    async def _vector_search(self, query: str, priority_paths: Optional[List[str]] = None) -> List[Dict]:
        """向量搜索 - 使用文本搜索作为备用"""
        try:
            # 提取关键词
            import re
            keywords = re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', query)
            keywords = [k for k in keywords if len(k) > 1][:5]

            if not keywords:
                return []

            # 方法1: 尝试 RPC 向量搜索（如果函数存在）
            try:
                result = self.supabase.rpc(
                    "match_entities",
                    {
                        "query_embedding": [0] * 1536,
                        "match_threshold": 0.7,
                        "match_count": self.config.vector_top_k,
                    }
                ).execute()
                if result.data:
                    # 如果有优先路径，排序优化
                    if priority_paths:
                        return self._prioritize_results(result.data, priority_paths)
                    return result.data
            except Exception:
                pass

            # 方法2: 优先路径查询
            results = []

            # 如果有优先路径，先查询这些路径
            if priority_paths:
                for path_prefix in priority_paths:
                    result = self.supabase.table("mem_l3_entities") \
                        .select("path, name, description_md, entity_type") \
                        .ilike("path", f"{path_prefix}%") \
                        .limit(5) \
                        .execute()
                    results.extend(result.data or [])

            # 方法3: 关键词查询
            for keyword in keywords[:3]:
                result = self.supabase.table("mem_l3_entities") \
                    .select("path, name, description_md, entity_type") \
                    .or_(f"name.ilike.%{keyword}%,description_md.ilike.%{keyword}%") \
                    .limit(3) \
                    .execute()
                results.extend(result.data or [])

            # 去重并排序（优先路径的排在前面）
            seen = set()
            unique = []
            for r in results:
                if r["path"] not in seen:
                    seen.add(r["path"])
                    unique.append(r)

            if priority_paths:
                unique = self._prioritize_results(unique, priority_paths)

            return unique[:self.config.vector_top_k]

        except Exception as e:
            print(f"[WARN] 搜索失败: {e}")
            return []

    def _prioritize_results(self, results: List[Dict], priority_paths: List[str]) -> List[Dict]:
        """根据优先路径排序结果"""
        def priority_score(entity):
            path = entity.get("path", "")
            for i, prefix in enumerate(priority_paths):
                if path.startswith(prefix):
                    return i  # 越小优先级越高
            return 999  # 无匹配的排在最后

        return sorted(results, key=priority_score)

    async def _path_search(self, query: str, priority_paths: Optional[List[str]] = None) -> List[Dict]:
        """路径搜索 - 如果查询包含特定领域关键词"""
        results = []

        # 如果提供了优先路径，直接查询这些路径
        if priority_paths:
            try:
                for path_prefix in priority_paths:
                    result = self.supabase.table("mem_l3_entities") \
                        .select("path, name, description_md, entity_type") \
                        .ilike("path", f"{path_prefix}%") \
                        .limit(5) \
                        .execute()
                    results.extend(result.data or [])
            except Exception as e:
                print(f"[WARN] 优先路径搜索失败: {e}")

        # 提取可能的路径关键词
        path_keywords = self._extract_path_keywords(query)

        if path_keywords:
            try:
                for keyword in path_keywords:
                    # SQL LIKE 查询 path
                    result = self.supabase.table("mem_l3_entities") \
                        .select("path, name, description_md, entity_type") \
                        .ilike("path", f"%{keyword}%") \
                        .limit(3) \
                        .execute()

                    results.extend(result.data or [])
            except Exception as e:
                print(f"[WARN] 路径搜索失败: {e}")

        # 去重
        seen = set()
        unique = []
        for r in results:
            if r["path"] not in seen:
                seen.add(r["path"])
                unique.append(r)

        return unique

    async def _semantic_understand(self, query: str) -> Dict:
        """
        语义理解层：用 LLM 深度理解用户查询
        返回结构化理解结果，指导后续检索
        """
        prompt = f"""深度理解用户查询，提取语义信息。

用户查询："{query}"

分析要求：
1. 查询目标：用户想要找到什么信息？
2. 涉及实体：提到了哪些人物、公司、项目、概念？
3. 关系类型：家庭关系、工作关系、时间关系等
4. 信息类型：生日、职位、历史事件、偏好等
5. 可能同义词：用户用词的可能替代说法

输出JSON格式：
{{
    "query_goal": "查询目标描述",
    "entities": [
        {{"name": "实体名", "type": "people/work/concept", "confidence": 0.9}}
    ],
    "relation_type": "家庭/工作/时间/其他",
    "info_type": "生日/职位/地点/事件/其他",
    "search_terms": ["用于搜索的关键词1", "关键词2"],
    "synonyms": {{"原始词": ["同义词1", "同义词2"]}}
}}

只输出JSON，不要其他文字。"""

        try:
            response = await self.system_llm.ainvoke([HumanMessage(content=prompt)])
            content = response.content.strip()

            # 清理 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())
            print(f"[Semantic] 理解结果: {result.get('query_goal', 'N/A')}")
            return result

        except Exception as e:
            print(f"[WARN] 语义理解失败: {e}")
            return None

    async def _smart_search(self, query: str, intent: str,
                           search_strategy: Dict = None,
                           time_expansion: bool = False,
                           time_mentioned: List[str] = None) -> List[Dict]:
        """
        智能混合搜索 4.0（语义理解增强）
        先语义理解，再精准检索
        """
        import re

        all_results = []

        # ===== 步骤1: 语义理解（优先）=====
        semantic_understanding = await self._semantic_understand(query)

        if semantic_understanding:
            # 基于语义理解构建精准搜索
            search_terms = semantic_understanding.get('search_terms', [])
            entities = semantic_understanding.get('entities', [])
            info_type = semantic_understanding.get('info_type', '')

            print(f"[SmartSearch] 语义搜索: terms={search_terms}, entities={len(entities)}")

            # 使用语义搜索词查找事实
            if search_terms:
                fact_results = await self._search_by_semantic_terms(search_terms, entities)
                all_results.extend([{**r, '_source': 'semantic', '_score': 5} for r in fact_results])

        # ===== 步骤2: 传统关键词搜索（备用/补充）=====
        # 提取多种类型的关键词
        path_keywords = self._extract_smart_keywords(query, 'path')
        content_keywords = self._extract_smart_keywords(query, 'content')
        semantic_keywords = self._extract_smart_keywords(query, 'semantic')

        print(f"[SmartSearch] 关键词搜索: Path={path_keywords}, Content={content_keywords}")

        # 策略 1: 路径模式搜索
        if path_keywords:
            path_results = await self._search_by_path_patterns(path_keywords)
            all_results.extend([{**r, '_source': 'path', '_score': 3} for r in path_results])

        # 策略 3: 原子事实搜索（关键！）
        # 使用语义关键词 + 内容关键词组合搜索，提高命中率
        search_keywords = list(set(content_keywords + semantic_keywords))
        fact_results = await self._search_atomic_facts(query, search_keywords)
        all_results.extend([{**r, '_source': 'facts', '_score': 4} for r in fact_results])

        # 策略 4: 时间扩展搜索（新增！）
        if time_expansion and time_mentioned:
            time_results = await self._search_time_expansion(time_mentioned, content_keywords)
            all_results.extend([{**r, '_source': 'time_expansion', '_score': 5} for r in time_results])

        # 策略 5: 意图感知的优先级调整
        all_results = self._apply_intent_scoring(all_results, intent, query)

        # 去重并排序
        return self._deduplicate_and_rank(all_results)

    def _extract_smart_keywords(self, query: str, keyword_type: str) -> List[str]:
        """
        智能关键词提取
        keyword_type: 'path' | 'content' | 'semantic'
        """
        import re
        query_lower = query.lower()

        # 语义关键词映射（用于内容搜索）
        semantic_map = {
            # 教育相关（完整覆盖各阶段）
            "小学": ["elementary", "primary", "小学", "就读"],
            "初中": ["middle school", "junior high", "初中", "中学", "就读"],
            "高中": ["high school", "senior high", "高中", "中学", "就读"],
            "大学": ["university", "college", "school", "campus", "graduate", "本科", "硕士", "博士", "就读"],
            "学校": ["school", "university", "college", "academy", "就读", "念书", "上学"],
            "毕业": ["graduate", "graduation", "alumni", "degree", "学历", "毕业于"],
            "专业": ["major", "specialty", "biotechnology", "生物技术", "主修"],
            "就读": ["就读", "念书", "上学", "学习", "读书", "求学"],
            "念书": ["念书", "就读", "上学", "学习", "读书"],
            # 工作相关
            "工作": ["work", "job", "career", "employment", "company"],
            "公司": ["company", "corporation", "firm", "enterprise", "inc"],
            "职位": ["position", "title", "role", "engineer", "manager"],
            # 人物相关
            "父亲": ["father", "dad", "家长", "父母"],
            "生日": ["birthday", "born", "出生日期"],
            "家人": ["family", "parent", "relative"],
            # 其他
            "项目": ["project", "program", "initiative"],
            "技术": ["technology", "tech", "technique", "technical"],
        }

        # 路径关键词映射（用于路径搜索）
        path_map = {
            "我": ["people"],
            "我的": ["people"],
            "父亲": ["people"],
            "爸爸": ["people"],
            "母亲": ["people"],
            "妈妈": ["people"],
            "家人": ["people"],
            # 教育相关（完整覆盖）
            "小学": ["education", "school"],
            "初中": ["education", "school", "middle-school"],
            "高中": ["education", "school", "high-school"],
            "大学": ["university", "college", "school", "education"],
            "学校": ["school", "education"],
            "就读": ["education", "school"],
            "念书": ["education", "school"],
            "毕业": ["education"],
            "专业": ["education"],
            # 工作相关
            "工作": ["work"],
            "公司": ["work"],
            "职位": ["work"],
            "职业": ["career"],
            # 人物相关
            "生日": ["people"],
            "年龄": ["people"],
            # 其他
            "项目": ["projects"],
            "概念": ["concepts"],
            "memos": ["memos"],
            "python": ["python"],
        }

        found = []

        if keyword_type == 'semantic':
            for keyword, synonyms in semantic_map.items():
                if keyword in query:
                    found.extend(synonyms)
                    found.append(keyword)

        elif keyword_type == 'path':
            for keyword, path_parts in path_map.items():
                if keyword in query_lower:
                    found.extend(path_parts)

        elif keyword_type == 'content':
            # 提取查询中的核心名词
            # 移除常见虚词
            stop_words = {'的', '了', '是', '在', '有', '我', '你', '他', '她', '它',
                         '哪', '什么', '怎么', '为什么', '吗', '呢', '吧', '啊',
                         'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on', 'at'}

            # 提取中文词
            chinese_words = re.findall(r'[\u4e00-\u9fff]{2,}', query)
            found.extend([w for w in chinese_words if w not in stop_words])

            # 提取英文词
            english_words = re.findall(r'[a-zA-Z]{3,}', query_lower)
            found.extend([w for w in english_words if w not in stop_words])

        return list(set(found))[:8]

    async def _search_by_path_patterns(self, keywords: List[str]) -> List[Dict]:
        """基于路径模式搜索"""
        results = []

        for keyword in keywords:
            try:
                # 搜索路径中包含关键词的实体
                result = self.supabase.table("mem_l3_entities") \
                    .select("path, name, description_md, entity_type") \
                    .ilike("path", f"%{keyword}%") \
                    .limit(5) \
                    .execute()

                if result.data:
                    results.extend(result.data)
            except Exception as e:
                print(f"[WARN] 路径搜索失败 for {keyword}: {e}")

        return results

    async def _search_by_content(self, keywords: List[str]) -> List[Dict]:
        """基于名称/描述内容搜索"""
        results = []

        for keyword in keywords:
            try:
                # 搜索名称或描述中包含关键词的实体
                result = self.supabase.table("mem_l3_entities") \
                    .select("path, name, description_md, entity_type") \
                    .or_(f"name.ilike.%{keyword}%,description_md.ilike.%{keyword}%") \
                    .limit(5) \
                    .execute()

                if result.data:
                    results.extend(result.data)
            except Exception as e:
                print(f"[WARN] 内容搜索失败 for {keyword}: {e}")

        return results

    async def _search_atomic_facts(self, query: str, keywords: List[str]) -> List[Dict]:
        """
        搜索原子事实，返回关联的实体
        这是解决个人记忆问题的关键！
        """
        results = []

        try:
            # 从查询中提取核心关键词（而不是依赖传入的keywords）
            core_keywords = []
            query_lower = query.lower()

            # 人物相关
            if '父' in query_lower or '爸' in query_lower:
                core_keywords.extend(['父亲', '爸爸', '爸', '李国栋'])
            if '母' in query_lower or '妈' in query_lower:
                core_keywords.extend(['母亲', '妈妈', '妈', '杨桂花'])
            if '奶' in query_lower:
                core_keywords.extend(['奶奶', '奶', '高剑秋'])

            # 主题相关
            if '生日' in query_lower:
                core_keywords.append('生日')
            if '工作' in query_lower or '公司' in query_lower:
                core_keywords.extend(['工作', '公司', '职位'])
            if '大学' in query_lower or '学校' in query_lower or '就读' in query_lower or '念书' in query_lower:
                core_keywords.extend(['大学', '学校', '专业', '就读', '念书', '小学', '初中', '高中', '毕业'])

            # 合并传入的关键词
            all_keywords = list(set(core_keywords + [kw for kw in keywords if len(kw) >= 2]))

            # 策略1: 如果有有效关键词，用关键词搜索
            valid_keywords = [kw for kw in all_keywords if kw not in ['什么', '怎么', '为什么', '记得', '知道', '对了']]

            print(f"[AtomicSearch] Keywords: {valid_keywords}")

            if valid_keywords:
                # 搜索包含关键词的事实
                conditions = []
                for kw in valid_keywords[:5]:  # 增加关键词数量限制
                    conditions.append(f"content.ilike.%{kw}%")

                # 使用 OR 连接多个条件
                query_filter = ",".join(conditions)

                facts_result = self.supabase.table("mem_l3_atomic_facts") \
                    .select("content, entity_id, mem_l3_entities(path, name, description_md)") \
                    .or_(query_filter) \
                    .eq("status", "active") \
                    .limit(10) \
                    .execute()

                if facts_result.data:
                    # 收集找到的实体ID
                    found_entity_ids = set()
                    for fact in facts_result.data:
                        entity = fact.get("mem_l3_entities", {})
                        if entity:
                            entity_id = entity.get('id')
                            if entity_id:
                                found_entity_ids.add(entity_id)
                            # 将事实内容附加到实体描述中
                            enriched_entity = {
                                **entity,
                                "matched_fact": fact.get("content", ""),
                                "fact_entity_id": fact.get("entity_id")
                            }
                            results.append(enriched_entity)

                    # 关键修复：对于找到的每个实体，查询其所有active事实
                    # 因为用户可能问"李国栋的生日"，但"生日是3月20日"这个事实不包含"李国栋"
                    for entity_id in found_entity_ids:
                        all_facts_result = self.supabase.table("mem_l3_atomic_facts") \
                            .select("content, entity_id, mem_l3_entities(path, name, description_md)") \
                            .eq("entity_id", entity_id) \
                            .eq("status", "active") \
                            .limit(20) \
                            .execute()

                        if all_facts_result.data:
                            for fact in all_facts_result.data:
                                entity = fact.get("mem_l3_entities", {})
                                if entity:
                                    # 检查是否已存在（去重）
                                    fact_content = fact.get("content", "")
                                    already_exists = any(
                                        r.get("path") == entity.get("path") and
                                        r.get("matched_fact") == fact_content
                                        for r in results
                                    )
                                    if not already_exists:
                                        enriched_entity = {
                                            **entity,
                                            "matched_fact": fact_content,
                                            "fact_entity_id": fact.get("entity_id")
                                        }
                                        results.append(enriched_entity)
                                        print(f"[AtomicSearch] 补充实体 {entity.get('path')} 的事实: {fact_content[:50]}...")

            # 策略2: 如果关键词搜索没结果，尝试提取查询中的核心名词进行模糊搜索
            if not results:
                # 提取查询中的关键名词（父亲、生日、公司等）
                core_terms = []
                if '父' in query or '爸' in query:
                    core_terms.extend(['父亲', '爸爸', '爸'])
                if '生日' in query or '生' in query:
                    core_terms.append('生日')
                if '母' in query or '妈' in query:
                    core_terms.extend(['母亲', '妈妈', '妈'])

                for term in core_terms:
                    facts_result = self.supabase.table("mem_l3_atomic_facts") \
                        .select("content, entity_id, mem_l3_entities(path, name, description_md)") \
                        .ilike("content", f"%{term}%") \
                        .eq("status", "active") \
                        .limit(5) \
                        .execute()

                    if facts_result.data:
                        for fact in facts_result.data:
                            entity = fact.get("mem_l3_entities", {})
                            if entity:
                                enriched_entity = {
                                    **entity,
                                    "matched_fact": fact.get("content", ""),
                                    "fact_entity_id": fact.get("entity_id")
                                }
                                if not any(r.get('path') == enriched_entity.get('path') and
                                          r.get('matched_fact') == enriched_entity.get('matched_fact')
                                          for r in results):
                                    results.append(enriched_entity)

        except Exception as e:
            print(f"[WARN] 原子事实搜索失败: {e}")

        return results

    async def _search_by_semantic_terms(self, search_terms: List[str], entities: List[Dict]) -> List[Dict]:
        """
        基于语义理解结果搜索事实
        使用语义搜索词而不是简单的关键词匹配
        【方案A+C】增加description_md搜索和实体全事实补充
        """
        results = []
        found_entity_ids = set()  # 用于跟踪已找到的实体

        try:
            # 构建搜索条件 - 使用语义搜索词
            entity_names = [e.get('name', '') for e in entities if e.get('name')]

            # 策略1: 按实体名搜索其所有事实
            for name in entity_names[:3]:  # 限制数量
                facts_result = self.supabase.table("mem_l3_atomic_facts") \
                    .select("content, entity_id, mem_l3_entities(path, name, description_md)") \
                    .eq("status", "active") \
                    .ilike("content", f"%{name}%") \
                    .limit(10) \
                    .execute()

                if facts_result.data:
                    for fact in facts_result.data:
                        entity = fact.get("mem_l3_entities", {})
                        if entity:
                            entity_id = entity.get('id') or fact.get('entity_id')
                            if entity_id:
                                found_entity_ids.add(entity_id)
                            results.append({
                                **entity,
                                "matched_fact": fact.get("content", ""),
                                "fact_entity_id": fact.get("entity_id")
                            })

            # 策略2: 按语义搜索词搜索
            for term in search_terms[:5]:
                if len(term) < 2:
                    continue

                facts_result = self.supabase.table("mem_l3_atomic_facts") \
                    .select("content, entity_id, mem_l3_entities(path, name, description_md)") \
                    .eq("status", "active") \
                    .ilike("content", f"%{term}%") \
                    .limit(5) \
                    .execute()

                if facts_result.data:
                    for fact in facts_result.data:
                        entity = fact.get("mem_l3_entities", {})
                        if entity:
                            entity_id = entity.get('id') or fact.get('entity_id')
                            if entity_id:
                                found_entity_ids.add(entity_id)
                            enriched = {
                                **entity,
                                "matched_fact": fact.get("content", ""),
                                "fact_entity_id": fact.get("entity_id")
                            }
                            # 去重
                            if not any(r.get('path') == enriched.get('path') and
                                      r.get('matched_fact') == enriched.get('matched_fact')
                                      for r in results):
                                results.append(enriched)

            # 【方案A】策略3: 搜索description_md（重要！）
            for term in search_terms[:3]:
                if len(term) < 2:
                    continue

                desc_result = self.supabase.table("mem_l3_entities") \
                    .select("id, path, name, description_md") \
                    .ilike("description_md", f"%{term}%") \
                    .limit(5) \
                    .execute()

                if desc_result.data:
                    for entity in desc_result.data:
                        entity_id = entity.get('id')
                        if entity_id:
                            found_entity_ids.add(entity_id)

                        # 将description_md作为matched_fact返回
                        desc_text = entity.get("description_md", "")
                        if desc_text:
                            # 截取相关片段（包含搜索词的部分）
                            term_pos = desc_text.lower().find(term.lower())
                            if term_pos >= 0:
                                # 提取搜索词前后200字符的上下文
                                start = max(0, term_pos - 100)
                                end = min(len(desc_text), term_pos + len(term) + 100)
                                context = desc_text[start:end]
                                matched_snippet = f"[来自档案] ...{context}..."
                            else:
                                matched_snippet = f"[来自档案] {desc_text[:200]}..."

                            enriched = {
                                **entity,
                                "matched_fact": matched_snippet,
                                "_source": "description_md"
                            }
                            # 去重检查
                            if not any(r.get('path') == enriched.get('path') and
                                      r.get('_source') == 'description_md'
                                      for r in results):
                                results.append(enriched)
                                print(f"[SemanticSearch] 从description_md匹配: {entity.get('path')}")

            # 【方案C】策略4: 为找到的每个实体补充所有active事实
            for entity_id in found_entity_ids:
                try:
                    all_facts_result = self.supabase.table("mem_l3_atomic_facts") \
                        .select("content, entity_id, mem_l3_entities(path, name, description_md)") \
                        .eq("entity_id", entity_id) \
                        .eq("status", "active") \
                        .limit(20) \
                        .execute()

                    if all_facts_result.data:
                        for fact in all_facts_result.data:
                            entity = fact.get("mem_l3_entities", {})
                            if entity:
                                fact_content = fact.get("content", "")
                                # 检查是否已存在
                                already_exists = any(
                                    r.get("path") == entity.get("path") and
                                    r.get("matched_fact") == fact_content
                                    for r in results
                                )
                                if not already_exists:
                                    enriched_entity = {
                                        **entity,
                                        "matched_fact": fact_content,
                                        "fact_entity_id": fact.get("entity_id"),
                                        "_source": "entity_full_facts"
                                    }
                                    results.append(enriched_entity)
                except Exception as e:
                    print(f"[WARN] 补充实体全事实失败 for {entity_id}: {e}")

            print(f"[SemanticSearch] 找到 {len(results)} 条语义匹配")

        except Exception as e:
            print(f"[WARN] 语义搜索失败: {e}")

        return results

    async def _search_time_expansion(self, time_mentioned: List[str], keywords: List[str]) -> List[Dict]:
        """
        时间扩展搜索
        搜索包含时间区间的事实，即使查询的具体时间不在事实文本中，
        只要在时间区间内就应该匹配
        """
        import re
        results = []

        try:
            # 提取查询中的年份
            years = []
            for t in time_mentioned:
                year_match = re.search(r'20\d{2}', t)
                if year_match:
                    years.append(int(year_match.group()))

            if not years:
                return results

            query_year = years[0]  # 使用第一个提到的年份

            # 搜索包含年份范围的事实
            # 策略：搜索包含 "年" 和数字的事实，然后手动检查区间
            facts_result = self.supabase.table("mem_l3_atomic_facts") \
                .select("content, entity_id, mem_l3_entities(path, name, description_md)") \
                .ilike("content", "%年%") \
                .eq("status", "active") \
                .limit(50) \
                .execute()

            if facts_result.data:
                for fact in facts_result.data:
                    content = fact.get("content", "")
                    entity = fact.get("mem_l3_entities", {})

                    if not entity:
                        continue

                    # 解析时间区间
                    # 匹配模式："2010年9月至2018年9月"、"2010-2018"、"2010年到2018年"
                    time_patterns = [
                        r'(20\d{2})\s*年?\s*\d*\s*[月]?\s*至\s*(20\d{2})',  # 2010年至2018年
                        r'(20\d{2})\s*[-~]\s*(20\d{2})',  # 2010-2018
                        r'(20\d{2})\s*年.*到\s*(20\d{2})\s*年',  # 2010年到2018年
                    ]

                    for pattern in time_patterns:
                        match = re.search(pattern, content)
                        if match:
                            start_year = int(match.group(1))
                            end_year = int(match.group(2))

                            # 检查查询年份是否在区间内
                            if start_year <= query_year <= end_year:
                                # 找到了！添加这个事实
                                enriched_entity = {
                                    **entity,
                                    "matched_fact": f"[时间匹配: {query_year}年在 {start_year}-{end_year} 区间内] {content}",
                                    "fact_entity_id": fact.get("entity_id"),
                                    "time_match": {
                                        "query_year": query_year,
                                        "start_year": start_year,
                                        "end_year": end_year
                                    }
                                }
                                results.append(enriched_entity)
                                print(f"[TimeExpansion] OK {query_year}年匹配区间 {start_year}-{end_year}: {entity.get('name', 'Unknown')}")
                                break  # 找到匹配就不再检查其他模式

        except Exception as e:
            print(f"[WARN] 时间扩展搜索失败: {e}")

        return results

    def _apply_intent_scoring(self, results: List[Dict], intent: str, query: str) -> List[Dict]:
        """根据意图调整分数"""
        import re

        for r in results:
            score = r.get('_score', 1)
            path = r.get('path', '')
            name = r.get('name', '')
            matched_fact = r.get('matched_fact', '')

            # PERSONAL_QUERY 意图：提升个人相关实体的分数
            if intent == "PERSONAL_QUERY":
                if '/people/' in path:
                    score += 2
                if '/concepts/education' in path or 'university' in path or 'school' in path:
                    score += 1
                if '父亲' in query or '爸爸' in query or '妈' in query:
                    if '父亲' in matched_fact or '爸爸' in matched_fact or '妈' in matched_fact:
                        score += 3
                if '大学' in query or '学校' in query:
                    if '大学' in matched_fact or '毕业' in matched_fact or '专业' in matched_fact:
                        score += 3

            # WORK_QUERY 意图：提升工作相关实体
            elif intent == "WORK_QUERY":
                if '/work/' in path:
                    score += 2
                if '项目' in query and '项目' in name:
                    score += 2

            r['_score'] = score

        return results

    def _deduplicate_and_rank(self, results: List[Dict]) -> List[Dict]:
        """去重并按分数排序"""
        seen = {}
        ranked = []

        # 调试：显示所有输入结果
        print(f"[DEDUP] Input {len(results)} results:")
        for r in results:
            has_fact = "✓" if r.get('matched_fact') else "✗"
            print(f"  - {r.get('path')} (score:{r.get('_score',1)}) {has_fact}")

        for r in results:
            path = r.get('path')
            if not path:
                continue

            score = r.get('_score', 1)

            if path in seen:
                # 合并分数
                seen[path]['_score'] += score
                # 合并匹配的事实（关键修复：保留所有事实，不只是第一个）
                if r.get('matched_fact'):
                    existing = seen[path].get('matched_fact', '')
                    new_fact = r['matched_fact']
                    # 去重追加，用分号分隔多个事实
                    if new_fact not in existing:
                        if existing:
                            seen[path]['matched_fact'] = existing + '; ' + new_fact
                        else:
                            seen[path]['matched_fact'] = new_fact
                        print(f"[DEDUP] Merged fact to {path}: {new_fact[:50]}...")
            else:
                seen[path] = r
                ranked.append(r)

        # 调试：显示输出结果
        print(f"[DEDUP] Output {len(ranked)} results:")
        for r in ranked:
            has_fact = "✓" if r.get('matched_fact') else "✗"
            print(f"  - {r.get('path')} {has_fact}")

        # 按分数降序
        ranked.sort(key=lambda x: x.get('_score', 0), reverse=True)

        # 清理内部字段
        for r in ranked:
            r.pop('_score', None)
            r.pop('_source', None)

        return ranked[:10]

    def _extract_path_keywords(self, query: str) -> List[str]:
        """保持向后兼容"""
        # 这个方法现在只用于简单的路径搜索
        # 主要逻辑移到 _extract_smart_keywords
        return self._extract_smart_keywords(query, 'path')

    # =========================================================================
    # Node 4: Generate (The Soul)
    # =========================================================================

    async def node_generate(self, state: GraphState) -> GraphState:
        """
        生成回复
        调用 User Model (Kimi)，注入所有上下文
        """
        user_input = state["user_input"]
        intent = state["intent"]
        global_context = state.get("global_context", {})
        retrieved = state.get("retrieved_entities", [])
        session_history = state.get("session_history", [])

        # 构建 System Prompt
        system_prompt = self._build_system_prompt(
            global_context,
            retrieved,
            intent,
            session_history
        )

        # 构建消息列表
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input),
        ]

        # 调用 User Model 生成
        try:
            response = await self.user_llm.ainvoke(messages)
            response_text = response.content

            # 保存 AI 回复到 L0 Buffer
            self._save_to_l0_buffer(
                role="ai",
                content=response_text,
                attachments=[],
                perception=""
            )

        except Exception as e:
            print(f"[ERROR] 生成失败: {e}")
            response_text = "抱歉，处理请求时出现问题，请重试。"

        return {
            **state,
            "messages": messages + [AIMessage(content=response_text)],
            "response": response_text,
            "metadata": {
                **state.get("metadata", {}),
                "response_length": len(response_text),
                "completed_at": datetime.utcnow().isoformat(),
            }
        }

    def _build_system_prompt(self, global_context: Dict,
                            retrieved: List[Dict],
                            intent: str,
                            session_history: List[Dict] = None) -> str:
        """构建 System Prompt（优化版：隐私保护 + 简洁回答）"""

        session_history = session_history or []

        # 1. User Profile - 根据意图过滤敏感信息
        profile_parts = []
        for p in global_context.get("profile", []):
            category = p.get('category', '')
            content = p.get('content', '')

            # 统一画像过滤：只保留一般性特征，不保留具体家庭关系详情
            # 家庭相关信息应通过检索到的具体事实来回答，而不是通过画像
            if category in ['skill', 'habit', 'mental_model', 'preference']:
                profile_parts.append(f"- {content}")

        profile_text = "\n".join(profile_parts) if profile_parts else ""
        if profile_text:
            profile_text = f"## 用户画像\n{profile_text}\n"

        # 2. 会话历史（最近对话上下文）
        session_history_text = ""
        if session_history:
            # 只取最近3轮对话
            recent_history = session_history[-3:]
            history_parts = []
            for h in recent_history:
                user_msg = h.get('user_input', '')
                ai_msg = h.get('response', '')
                if user_msg and ai_msg:
                    history_parts.append(f"用户: {user_msg}\nAI: {ai_msg[:100]}...")
            if history_parts:
                session_history_text = "## 刚才的对话\n" + "\n\n".join(history_parts) + "\n\n"

        # 3. 检索到的知识 - 精简展示，只显示匹配的事实
        retrieved_facts = []
        needs_retrieval = intent in ["PERSONAL_QUERY", "WORK_QUERY", "TASK", "FOLLOW_UP"]

        # 调试：显示接收到的检索结果
        print(f"[SYS_PROMPT] Received {len(retrieved)} entities")
        for e in retrieved[:3]:
            has_fact = "✓" if e.get('matched_fact') else "✗"
            print(f"  - {e.get('path')} {has_fact}: {e.get('matched_fact','')[:50]}")

        if needs_retrieval and retrieved:
            for e in retrieved[:3]:  # 只取前3个最相关的
                matched_fact = e.get("matched_fact", "")
                entity_name = e.get("name", "")
                if matched_fact:
                    # 支持分号分隔的多个事实
                    facts_list = [f.strip() for f in matched_fact.split(';') if f.strip()]
                    for fact in facts_list:
                        # 清理标记
                        clean_fact = fact.replace("[相关事实] ", "")
                        # 如果事实不包含实体名称，添加前缀
                        if entity_name and entity_name not in clean_fact:
                            clean_fact = f"{entity_name}: {clean_fact}"
                        retrieved_facts.append(clean_fact)
                        print(f"[SYS_PROMPT] Added fact: {clean_fact[:50]}")

        retrieved_text = "\n".join([f"- {f}" for f in retrieved_facts]) if retrieved_facts else ""
        if retrieved_text:
            retrieved_text = f"## 检索到的相关事实\n{retrieved_text}\n"

        # 3. 自然对话风格指南
        base_guidelines = """
## 回答风格指南（必须遵守）

1. **像朋友一样自然聊天**:
   - 使用口语化表达，不要太正式或机械
   - 可以带一点轻松、亲切的语气
   - 适当使用"呢"、"吧"、"呀"等语气词
   - 像真人朋友那样有温度，不要像机器人

2. **人性化表达**:
   - 提到家人时可以用"叔叔"、"阿姨"、"奶奶"等亲切称呼
   - 可以说"我记得"、"如果我没记错的话"、"好像听你说起过"等自然表达
   - 不确定时可以带一点保留，比如"应该是...吧？"
   - 回答后可以自然地延伸话题或简单关心

3. **隐私保护**:
   - 不要在没问的情况下主动列举家庭成员名单
   - 只有用户问起某人才提具体姓名
   - 自然回答即可，不需要刻意强调"我存储了"

4. **基于事实但灵活表达**:
   - 用检索到的事实作为基础
   - 但要用自己的话组织，不要生硬列举
   - 可以说"我记得叔叔生日是3月20日"，而不是"存储的信息显示：生日-3月20日"

5. **没记录时的处理**:
   - 可以说"我记得不太清了"、"好像没听你说过"、"这个我还真不知道"
   - 自然地询问用户是否愿意分享
   - 不要生硬地说"没有记录"

6. **注意对话上下文**:
   - 仔细看"刚才的对话"，理解用户在延续什么话题
   - 如果用户说"还没想好"、"我是指..."，说明你在理解上有偏差，要及时纠正
   - 不要突然跳到不相关的话题

## 参考信息
{session_history_text}{retrieved_text}{profile_text}
请像好朋友一样自然地回答用户问题，注意刚才的对话上下文。
"""

        # 格式化模板，填充检索到的信息和画像
        prompt = base_guidelines.format(
            session_history_text=session_history_text,
            retrieved_text=retrieved_text,
            profile_text=profile_text
        )

        return prompt

    # =========================================================================
    # 公开接口
    # =========================================================================

    async def chat(self, user_input: str,
                   attachments: Optional[List[Dict]] = None,
                   session_id: str = "default") -> Dict:
        """
        主入口：处理用户消息

        Args:
            user_input: 用户输入文本
            attachments: 附件列表 [{"url": "...", "mime_type": "..."}]
            session_id: 会话ID

        Returns:
            {"response": "...", "metadata": {...}}
        """
        # 获取会话历史
        session_history = self._get_session_history(session_id)

        initial_state: GraphState = {
            "user_input": user_input,
            "attachments": attachments or [],
            "session_id": session_id,
            "session_history": session_history,
            "perception_result": None,
            "intent": "CASUAL",  # 默认改为 CASUAL，让 Router 决定
            "search_strategy": {},  # 由 Router 填充
            "cognitive_context": {},  # 由 Router 填充
            "is_follow_up": False,  # 由 Router 判断
            "global_context": {},
            "retrieved_entities": [],
            "messages": [],
            "response": None,
            "metadata": {},
        }

        # 执行图
        result = await self.graph.ainvoke(initial_state)

        # 更新会话历史
        self._update_session_history(
            session_id,
            user_input,
            result["response"],
            result["intent"]
        )

        return {
            "response": result["response"],
            "metadata": result["metadata"],
            "intent": result["intent"],
        }


# =============================================================================
# 同步包装（方便调用）
# =============================================================================

_graph_instance: Optional[MemOSGraph] = None


def get_graph() -> MemOSGraph:
    """获取单例实例"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = MemOSGraph()
    return _graph_instance


async def chat(user_input: str,
               attachments: Optional[List[Dict]] = None,
               session_id: str = "default") -> Dict:
    """便捷函数：异步聊天"""
    graph = get_graph()
    return await graph.chat(user_input, attachments, session_id)


def chat_sync(user_input: str,
              attachments: Optional[List[Dict]] = None,
              session_id: str = "default") -> Dict:
    """便捷函数：同步聊天"""
    return asyncio.run(chat(user_input, attachments, session_id))


# =============================================================================
# 测试
# =============================================================================

if __name__ == "__main__":
    async def test():
        print("=" * 50)
        print("MemOS Graph 测试")
        print("=" * 50)

        # 测试 WORK 意图
        print("\n[测试 1] 工作查询...")
        result = await chat("告诉我 MemOS v2.0 项目的进展")
        print(f"意图: {result['intent']}")
        print(f"回复: {result['response'][:200]}...")
        print(f"元数据: {json.dumps(result['metadata'], indent=2)}")

        # 测试 CHAT 意图
        print("\n[测试 2] 闲聊...")
        result = await chat("你好，今天怎么样？")
        print(f"意图: {result['intent']}")
        print(f"回复: {result['response'][:200]}...")

    asyncio.run(test())
