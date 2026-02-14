"""
Daily Snapshots - L1 Timeline Generator
生成每日事件日志：何时、何人、发生了什么事
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
from langchain_core.messages import HumanMessage

from llm_factory import get_system_llm

load_dotenv()


class DailySnapshotGenerator:
    """每日快照生成器 - L1 Timeline"""

    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )
        self.llm = get_system_llm()

    def get_yesterday_messages(self, target_date: Optional[str] = None) -> List[Dict]:
        """获取指定日期的消息（默认昨天）"""
        if target_date:
            # 使用指定日期
            date_start = f"{target_date}T00:00:00"
            date_end = f"{target_date}T23:59:59"
        else:
            # 默认昨天
            yesterday = datetime.now() - timedelta(days=1)
            date_start = yesterday.strftime("%Y-%m-%dT00:00:00")
            date_end = yesterday.strftime("%Y-%m-%dT23:59:59")

        result = self.supabase.table("mem_l0_buffer") \
            .select("*") \
            .gte("created_at", date_start) \
            .lte("created_at", date_end) \
            .order("created_at", desc=False) \
            .execute()

        return result.data or []

    def generate_snapshot(self, messages: List[Dict], date_str: str) -> Dict:
        """
        生成每日快照
        格式：事件日志 - 何时、何人、发生了什么事
        """
        if not messages:
            return {
                "date": date_str,
                "summary": "今日无活动记录",
                "events": [],
                "people_involved": [],
                "topics": []
            }

        # 构建对话记录
        conversation_log = []
        for msg in messages:
            time_str = msg["created_at"][11:16]  # HH:MM
            role = "User" if msg["role"] == "user" else "AI"
            content = msg["content"][:200]  # 截断
            conversation_log.append(f"[{time_str}] {role}: {content}")

        conversation_text = "\n".join(conversation_log)

        prompt = f"""分析以下今日对话记录，生成结构化的事件日志。

日期: {date_str}

对话记录:
{conversation_text}

请生成JSON格式的事件日志:
{{
    "summary": "一句话总结今天的主要活动",
    "events": [
        {{
            "time": "HH:MM",
            "who": "涉及的人/角色",
            "what": "发生了什么事",
            "type": "工作/学习/生活/其他"
        }}
    ],
    "people_involved": ["提到的人物"],
    "topics": ["讨论的主题"],
    "key_activities": ["关键活动"]
}}

只输出JSON，不要其他说明。"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()

            # 清理 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            snapshot = json.loads(content.strip())
            snapshot["date"] = date_str
            snapshot["message_count"] = len(messages)

            return snapshot

        except Exception as e:
            print(f"生成快照失败: {e}")
            # 返回基础快照
            return {
                "date": date_str,
                "summary": f"今日有 {len(messages)} 条对话记录",
                "events": [],
                "people_involved": [],
                "topics": [],
                "message_count": len(messages)
            }

    def save_snapshot(self, snapshot: Dict):
        """保存快照到 L1 Timeline"""
        try:
            # 检查是否已存在
            existing = self.supabase.table("mem_l1_timeline") \
                .select("id") \
                .eq("date", snapshot["date"]) \
                .execute()

            record = {
                "date": snapshot["date"],
                "summary": snapshot.get("summary", ""),
                "events": snapshot.get("events", []),
                "people_involved": snapshot.get("people_involved", []),
                "topics": snapshot.get("topics", []),
                "key_activities": snapshot.get("key_activities", []),
                "message_count": snapshot.get("message_count", 0),
                "created_at": datetime.utcnow().isoformat()
            }

            if existing.data:
                # 更新
                self.supabase.table("mem_l1_timeline") \
                    .update(record) \
                    .eq("id", existing.data[0]["id"]) \
                    .execute()
                print(f"  更新快照: {snapshot['date']}")
            else:
                # 插入
                self.supabase.table("mem_l1_timeline").insert(record).execute()
                print(f"  新建快照: {snapshot['date']}")

        except Exception as e:
            print(f"保存快照失败: {e}")

    def run(self, target_date: Optional[str] = None):
        """生成每日快照"""
        print("=" * 60)
        print("Daily Snapshot Generator (L1 Timeline)")
        print("=" * 60)

        # 确定日期
        if target_date:
            date_str = target_date
        else:
            date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"\n处理日期: {date_str}")

        # 获取消息
        messages = self.get_yesterday_messages(date_str)
        print(f"找到 {len(messages)} 条消息")

        if not messages:
            print("无消息，跳过")
            return

        # 生成快照
        print("生成快照...")
        snapshot = self.generate_snapshot(messages, date_str)

        # 保存
        self.save_snapshot(snapshot)

        print(f"\n[OK] 快照完成")
        print(f"  摘要: {snapshot.get('summary', 'N/A')[:80]}...")
        print(f"  事件数: {len(snapshot.get('events', []))}")
        print(f"  涉及人物: {', '.join(snapshot.get('people_involved', []))}")


if __name__ == "__main__":
    import sys

    generator = DailySnapshotGenerator()

    if len(sys.argv) > 1:
        # 指定日期: python daily_snapshots.py 2024-02-13
        generator.run(sys.argv[1])
    else:
        # 默认昨天
        generator.run()
