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
    intent: Literal["CHAT", "WORK"]

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
    max_history: int = 10


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

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 流程图"""

        workflow = StateGraph(GraphState)

        # 添加节点
        workflow.add_node("input_perception", self.node_input_perception)
        workflow.add_node("router", self.node_router)
        workflow.add_node("load_global_context", self.node_load_global_context)
        workflow.add_node("deep_search", self.node_deep_search)
        workflow.add_node("generate", self.node_generate)

        # 设置入口
        workflow.set_entry_point("input_perception")

        # 边: Input -> Router
        workflow.add_edge("input_perception", "router")

        # 条件边: Router 决策
        workflow.add_conditional_edges(
            "router",
            self.decide_intent,
            {
                "CHAT": "load_global_context",  # 闲聊跳过深度搜索
                "WORK": "deep_search",          # 任务需要深度搜索
            }
        )

        # 边: Deep Search -> Load Global (并行后合并)
        workflow.add_edge("deep_search", "load_global_context")

        # 边: Global Context -> Generate
        workflow.add_edge("load_global_context", "generate")

        # 边: Generate -> END
        workflow.add_edge("generate", END)

        return workflow.compile()

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

            # 存入 L0 Buffer
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

        return {
            **state,
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

            self.supabase.table("mem_l0_buffer").insert({
                "role": role,
                "content": content,
                "meta_data": meta_data,
                "processed": False,
            }).execute()
        except Exception as e:
            print(f"[WARN] L0 Buffer 保存失败: {e}")

    # =========================================================================
    # Node 2: Router (Intent Classification)
    # =========================================================================

    async def node_router(self, state: GraphState) -> GraphState:
        """
        意图分类：CHAT vs WORK
        调用 System Model 快速判断
        """
        user_input = state["user_input"]

        prompt = f"""分析用户输入的意图，判断是闲聊还是需要深度处理的工作请求。

用户输入: {user_input[:500]}

判断标准:
- CHAT (闲聊): 问候、寒暄、简单确认、日常对话、无实质任务
- WORK (工作): 涉及项目、任务、查询知识、需要记忆或检索信息

只回复一个单词: CHAT 或 WORK"""

        try:
            response = await self.system_llm.ainvoke([
                HumanMessage(content=prompt)
            ])

            intent = "WORK" if "WORK" in response.content.upper() else "CHAT"

        except Exception as e:
            print(f"[WARN] 路由失败，默认 WORK: {e}")
            intent = "WORK"

        return {
            **state,
            "intent": intent,
            "metadata": {
                **state.get("metadata", {}),
                "intent": intent,
            }
        }

    def decide_intent(self, state: GraphState) -> Literal["CHAT", "WORK"]:
        """条件边决策函数"""
        return state["intent"]

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
        深度搜索（仅 WORK 意图）
        并行执行:
        - Vector Search: 基于 Query 搜索 embedding
        - Path Search: 如果包含领域关键词，SQL LIKE 查询 path
        """
        user_input = state["user_input"]

        # 并行执行两种搜索
        vector_task = asyncio.create_task(
            self._vector_search(user_input)
        )
        path_task = asyncio.create_task(
            self._path_search(user_input)
        )

        vector_results, path_results = await asyncio.gather(
            vector_task, path_task
        )

        # 合并去重（按 path）
        seen_paths = set()
        merged = []

        for entity in vector_results + path_results:
            path = entity.get("path")
            if path and path not in seen_paths:
                seen_paths.add(path)
                merged.append(entity)

        # 限制数量
        merged = merged[:self.config.vector_top_k + 2]

        return {
            **state,
            "retrieved_entities": merged,
            "metadata": {
                **state.get("metadata", {}),
                "vector_hits": len(vector_results),
                "path_hits": len(path_results),
                "total_entities": len(merged),
            }
        }

    async def _vector_search(self, query: str) -> List[Dict]:
        """向量搜索 - 使用文本搜索作为备用"""
        try:
            # 提取关键词
            import re
            # 移除标点，提取有意义的词
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
                    return result.data
            except Exception:
                pass  # RPC 不存在，使用备用方案

            # 方法2: 文本搜索函数
            try:
                result = self.supabase.rpc(
                    "search_entities_by_text",
                    {"search_query": keywords[0], "result_limit": self.config.vector_top_k}
                ).execute()
                if result.data:
                    return result.data
            except Exception:
                pass

            # 方法3: 直接 ILIKE 查询
            results = []
            for keyword in keywords[:3]:
                result = self.supabase.table("mem_l3_entities") \
                    .select("path, name, description_md, entity_type") \
                    .or_(f"name.ilike.%{keyword}%,description_md.ilike.%{keyword}%") \
                    .limit(3) \
                    .execute()
                results.extend(result.data or [])

            # 去重
            seen = set()
            unique = []
            for r in results:
                if r["path"] not in seen:
                    seen.add(r["path"])
                    unique.append(r)

            return unique[:self.config.vector_top_k]

        except Exception as e:
            print(f"[WARN] 搜索失败: {e}")
            return []

    async def _path_search(self, query: str) -> List[Dict]:
        """路径搜索 - 如果查询包含特定领域关键词"""
        # 提取可能的路径关键词
        path_keywords = self._extract_path_keywords(query)

        if not path_keywords:
            return []

        results = []
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

        return results

    def _extract_path_keywords(self, query: str) -> List[str]:
        """从查询中提取可能的路径关键词"""
        # 简单的关键词映射
        keyword_map = {
            "项目": ["work/projects", "projects"],
            "工作": ["work"],
            "人": ["people"],
            "概念": ["concepts"],
            "工具": ["tools"],
            "生活": ["life"],
            "memos": ["memos"],
            "python": ["python"],
        }

        found = []
        query_lower = query.lower()

        for keyword, paths in keyword_map.items():
            if keyword in query_lower:
                found.extend(paths)

        # 也提取英文单词
        import re
        words = re.findall(r'[a-zA-Z0-9_-]+', query)
        for word in words:
            if len(word) > 2:
                found.append(word.lower())

        return list(set(found))[:3]  # 最多3个

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

        # 构建 System Prompt
        system_prompt = self._build_system_prompt(
            global_context,
            retrieved,
            intent
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
                            intent: str) -> str:
        """构建 System Prompt"""

        # 1. User Profile
        profile_parts = []
        for p in global_context.get("profile", []):
            profile_parts.append(f"- [{p.get('category')}] {p.get('content')} (置信度: {p.get('confidence', 0.5)})")

        profile_text = "\n".join(profile_parts) if profile_parts else "暂无用户画像"

        # 2. Pinned Entities
        pinned_parts = []
        for e in global_context.get("pinned", []):
            desc = e.get("description_md", "")[:200]  # 截断
            pinned_parts.append(f"### {e.get('name')} ({e.get('path')})\n{desc}")

        pinned_text = "\n\n".join(pinned_parts) if pinned_parts else "暂无置顶实体"

        # 3. Retrieved Knowledge (仅 WORK 模式)
        retrieved_text = ""
        if intent == "WORK" and retrieved:
            retrieved_parts = []
            for e in retrieved:
                desc = e.get("description_md", "")[:300]  # 截断
                retrieved_parts.append(f"### {e.get('name')} ({e.get('path')})\n{desc}")
            retrieved_text = "\n\n".join(retrieved_parts)
        else:
            retrieved_text = "（闲聊模式，未检索特定知识）"

        prompt = f"""你是一个拥有长期记忆的 AI 助手。根据以下上下文回答用户问题。

## 用户画像
{profile_text}

## 置顶记忆（始终记住）
{pinned_text}

## 检索到的相关知识
{retrieved_text}

## 回答指南
1. **语气**: 友好、专业，像熟悉的朋友
2. **记忆使用**:
   - 闲聊模式：自然对话，不需要强行引用记忆
   - 工作模式：基于检索到的知识，给出准确、有针对性的回答
3. **格式**: 使用 Markdown，结构清晰
4. **不确定时**: 坦诚告知，不要编造

当前模式: {"工作/查询" if intent == "WORK" else "闲聊"}
"""

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
        initial_state: GraphState = {
            "user_input": user_input,
            "attachments": attachments or [],
            "session_id": session_id,
            "perception_result": None,
            "intent": "WORK",  # 默认
            "global_context": {},
            "retrieved_entities": [],
            "messages": [],
            "response": None,
            "metadata": {},
        }

        # 执行图
        result = await self.graph.ainvoke(initial_state)

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
