"""
Batch Extractor - 30分钟批处理工作器
L0 Buffer -> L3 Entities + Atomic Facts
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from uuid import uuid4

from dotenv import load_dotenv
from supabase import create_client, Client
from langchain_core.messages import SystemMessage, HumanMessage

from llm_factory import get_system_llm

load_dotenv()


class BatchExtractor:
    """批处理提取器 - Clawdbot 风格"""

    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )
        self.llm = get_system_llm()

    def fetch_unprocessed_messages(self, batch_size: int = 100) -> List[Dict]:
        """读取未处理的 L0 消息"""
        result = self.supabase.table("mem_l0_buffer") \
            .select("*") \
            .eq("processed", False) \
            .order("created_at", desc=False) \
            .limit(batch_size) \
            .execute()
        return result.data or []

    def is_chitchat(self, messages: List[Dict]) -> bool:
        """判断是否为纯闲聊（跳过条件）"""
        if len(messages) < 2:
            return True  # 消息太少，跳过

        # 合并消息内容
        combined_text = "\n".join([m["content"] for m in messages])

        # 简单启发式判断
        chitchat_keywords = [
            "你好", "在吗", "谢谢", "不客气", "好的", "ok", "没问题",
            "hello", "hi", "thanks", "bye", "再见"
        ]
        words = combined_text.lower().split()
        chitchat_ratio = sum(1 for w in words if any(k in w for k in chitchat_keywords)) / max(len(words), 1)

        if chitchat_ratio > 0.5:
            return True

        # 用 LLM 判断
        prompt = f"""
判断以下对话是否为**纯闲聊**（无实质信息提取价值）：

对话内容：
{combined_text[:2000]}

判断标准：
- 纯闲聊：问候、寒暄、简单确认、无具体事实
- 有实质：涉及项目、人物、计划、偏好、事件等

只回复 "CHITCHAT" 或 "SUBSTANTIVE"
"""
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return "CHITCHAT" in response.content.upper()

    def extract_entities_and_facts(self, messages: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        提取实体和原子事实

        Returns:
            (entities_list, facts_list)
        """
        # 构建对话上下文
        conversation = "\n\n".join([
            f"[{m['role']}] {m['content']}"
            for m in messages
        ])

        # 多模态附件处理提示
        attachments_info = ""
        for m in messages:
            meta = m.get("meta_data", {})
            if meta.get("attachments"):
                attachments_info += f"\n附件: {json.dumps(meta['attachments'])}"

        prompt = f"""
你是一个记忆提取专家。从以下对话中提取实体和原子事实。

## 输出格式 (JSON)
{{
    "entities": [
        {{
            "path": "/work/projects/project-name" | "/people/person-name" | "/concepts/concept-name",
            "name": "显示名称",
            "entity_type": "project" | "person" | "concept" | "file" | "folder"
        }}
    ],
    "facts": [
        {{
            "entity_path": "/work/projects/project-name",
            "content": "原子事实陈述",
            "confidence": 0.95
        }}
    ]
}}

## 路径命名规范（重要！）
- 工作项目: /work/projects/{{项目名称}} (entity_type: project)
- 个人: /people/{{拼音姓名}} (entity_type: person)
  **关键规则**：
  - 中文姓名必须转换为拼音，每个字分开用连字符
  - "李佳泽" → path: "/people/li-jia-ze", name: "李佳泽"
  - "李国栋" → path: "/people/li-guo-dong", name: "李国栋"
  - "杨桂花" → path: "/people/yang-gui-hua", name: "杨桂花"
  - 外文姓名保持原样："Peter" → path: "/people/peter"
- 概念知识: /concepts/{{概念名}} (entity_type: concept)
- 工具/应用: /tools/{{工具名}} (entity_type: folder)
- 生活: /life/{{类别}}/{{项目}} (entity_type: folder)

## 提取原则
1. 实体路径使用小写，连字符分隔
2. 人物实体路径必须使用拼音格式（重要！）
3. 实体名称(name字段)保持原始中文/外文
4. 事实必须是离散的、原子化的陈述
5. 每个事实关联一个已定义的实体路径
6. 置信度 0-1，基于信息明确程度

## 对话内容
{conversation}

{attachments_info}

只输出 JSON，不要其他解释。
"""

        response = self.llm.invoke([HumanMessage(content=prompt)])

        try:
            # 解析 JSON 响应
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())
            entities = data.get("entities", [])
            facts = data.get("facts", [])

            return entities, facts

        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")
            print(f"原始响应: {response.content[:500]}")
            return [], []

    def get_or_create_entity(self, path: str, name: str, entity_type: str = "folder") -> str:
        """获取或创建实体，返回 entity_id

        支持模糊匹配：
        1. 精确匹配 path
        2. 按 name 匹配（适用于拼音标准化前创建的实体）
        3. 拼音相似度匹配（检测重复实体）
        """
        from pinyin_utils import generate_entity_path, chinese_to_pinyin, is_chinese

        # 标准化 path（如果是人物实体）
        if entity_type == "person" and is_chinese(name):
            standard_path = generate_entity_path(name)
        else:
            standard_path = path

        # 1. 精确匹配标准化 path
        existing = self.supabase.table("mem_l3_entities") \
            .select("id") \
            .eq("path", standard_path) \
            .execute()

        if existing.data:
            return existing.data[0]["id"]

        # 2. 模糊匹配：检查 name 相同且类型相同
        name_match = self.supabase.table("mem_l3_entities") \
            .select("id, path, name") \
            .eq("name", name) \
            .eq("entity_type", entity_type) \
            .execute()

        if name_match.data:
            # 找到了相同 name 的实体，复用
            print(f"[EntityMatch] 通过 name 匹配到现有实体: {name} -> {name_match.data[0]['path']}")
            return name_match.data[0]["id"]

        # 3. 模糊匹配：拼音相似度（仅人物实体）
        if entity_type == "person" and is_chinese(name):
            name_pinyin = chinese_to_pinyin(name)
            # 查询所有同类型人物实体
            all_entities = self.supabase.table("mem_l3_entities") \
                .select("id, path, name") \
                .eq("entity_type", "person") \
                .execute()

            for e in all_entities.data:
                if is_chinese(e["name"]):
                    e_pinyin = chinese_to_pinyin(e["name"])
                    if name_pinyin == e_pinyin:
                        print(f"[EntityMatch] 通过拼音匹配到现有实体: {name}({name_pinyin}) -> {e['name']}({e['path']})")
                        return e["id"]

        # 创建新实体（使用标准化 path）
        new_entity = {
            "path": standard_path,
            "name": name,
            "description_md": f"# {name}\n\n待编译...\n",
            "entity_type": entity_type,
            "is_pinned": False,
        }

        result = self.supabase.table("mem_l3_entities") \
            .insert(new_entity) \
            .execute()

        return result.data[0]["id"]

    def write_facts(self, entity_id: str, facts: List[Dict]):
        """写入原子事实"""
        if not facts:
            return

        fact_records = []
        for fact in facts:
            fact_records.append({
                "entity_id": entity_id,
                "content": fact["content"],
                "status": "active",
                "source_type": "inference",
                "context_json": {
                    "extracted_at": datetime.utcnow().isoformat(),
                    "extractor": "batch_extractor",
                    "confidence": fact.get("confidence", 0.8),
                }
            })

        self.supabase.table("mem_l3_atomic_facts") \
            .insert(fact_records) \
            .execute()

    def mark_processed(self, message_ids: List[str]):
        """标记 L0 消息为已处理"""
        for msg_id in message_ids:
            self.supabase.table("mem_l0_buffer") \
                .update({"processed": True}) \
                .eq("id", msg_id) \
                .execute()

    def process_batch(self, batch_size: int = 100):
        """主处理流程"""
        print(f"[{datetime.now()}] 开始批处理...")

        # 1. 获取未处理消息
        messages = self.fetch_unprocessed_messages(batch_size)
        if not messages:
            print("没有待处理的消息")
            return

        print(f"获取到 {len(messages)} 条未处理消息")

        # 2. 闲聊过滤
        if self.is_chitchat(messages):
            print("判定为纯闲聊，跳过提取")
            self.mark_processed([m["id"] for m in messages])
            return

        # 3. 提取实体和事实
        print("提取实体和事实...")
        entities, facts = self.extract_entities_and_facts(messages)

        print(f"提取到 {len(entities)} 个实体, {len(facts)} 条事实")

        # 4. 写入实体和事实
        path_to_id = {}
        for entity in entities:
            path = entity["path"]
            entity_id = self.get_or_create_entity(
                path=path,
                name=entity["name"],
                entity_type=entity.get("entity_type", "folder")
            )
            path_to_id[path] = entity_id
            print(f"  实体: {path}")

        # 将事实关联到实体ID
        for fact in facts:
            entity_path = fact.get("entity_path")
            if entity_path in path_to_id:
                entity_id = path_to_id[entity_path]
                self.write_facts(entity_id, [fact])
                print(f"  事实: {fact['content'][:50]}...")

        # 5. 标记已处理
        self.mark_processed([m["id"] for m in messages])
        print(f"[{datetime.now()}] 批处理完成")


def run_scheduler(interval_minutes: int = 30):
    """定时运行器"""
    import time

    extractor = BatchExtractor()

    print(f"启动批处理调度器，间隔: {interval_minutes} 分钟")

    while True:
        try:
            extractor.process_batch()
        except Exception as e:
            print(f"批处理错误: {e}")

        print(f"等待 {interval_minutes} 分钟...")
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # 单次运行模式
        extractor = BatchExtractor()
        extractor.process_batch()
    else:
        # 调度模式 (默认30分钟)
        run_scheduler(interval_minutes=30)
