"""
Daily Snapshots - L1 Timeline Generator
生成每日事件日志：何时、何人、发生了什么事
"""

import os
import json
import re
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
                "topics": [],
                "key_activities": []
            }

        # 提取关键词（备用方案）
        all_text = " ".join([msg.get("content", "") for msg in messages])
        people_mentioned = self._extract_people(all_text)
        topics_mentioned = self._extract_topics(all_text)

        # 构建对话记录
        conversation_log = []
        for msg in messages:
            time_str = msg["created_at"][11:16]  # HH:MM
            role = "User" if msg["role"] == "user" else "AI"
            content = msg["content"][:300]  # 增加截断长度
            conversation_log.append(f"[{time_str}] {role}: {content}")

        conversation_text = "\n".join(conversation_log)

        # 预填的字段
        people_json = ', '.join([f'"{p}"' for p in people_mentioned[:5]]) if people_mentioned else '"用户"'
        topics_json = ', '.join([f'"{t}"' for t in topics_mentioned[:5]]) if topics_mentioned else '"日常对话"'

        prompt = f"""分析以下今日对话记录，提取关键信息并生成JSON格式的事件日志。

日期: {date_str}
对话记录数: {len(messages)}条

对话记录:
{conversation_text}

请严格按以下JSON格式输出，不要添加任何其他文字：
{{
    "summary": "用一句话总结今天的主要活动和讨论内容，要具体",
    "events": [
        {{
            "time": "HH:MM",
            "who": "涉及的人名或角色",
            "what": "具体发生了什么",
            "type": "工作/学习/生活/其他"
        }}
    ],
    "people_involved": [{people_json}],
    "topics": [{topics_json}],
    "key_activities": ["主要活动1", "主要活动2"]
}}

注意：
1. 必须返回有效的JSON格式
2. events数组不能为空，至少提取3个关键事件
3. people_involved从对话中提取提到的人名
4. topics提取讨论的主题关键词
5. key_activities总结主要活动类型"""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"  调用LLM生成摘要 (尝试 {attempt + 1}/{max_retries})...")
                response = self.llm.invoke([HumanMessage(content=prompt)])
                content = response.content.strip()

                # 清理 JSON
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                # 尝试解析JSON
                content = content.strip()
                snapshot = json.loads(content)

                # 验证必要字段
                if not isinstance(snapshot.get("events"), list):
                    snapshot["events"] = []
                if not isinstance(snapshot.get("people_involved"), list):
                    snapshot["people_involved"] = people_mentioned
                if not isinstance(snapshot.get("topics"), list):
                    snapshot["topics"] = topics_mentioned
                if not isinstance(snapshot.get("key_activities"), list):
                    snapshot["key_activities"] = []

                snapshot["date"] = date_str
                snapshot["message_count"] = len(messages)

                # 如果LLM返回的数组为空，使用备用提取的结果
                if not snapshot.get("people_involved"):
                    snapshot["people_involved"] = people_mentioned if people_mentioned else ["用户"]
                if not snapshot.get("topics"):
                    snapshot["topics"] = topics_mentioned if topics_mentioned else ["日常对话"]
                if not snapshot.get("summary") or snapshot["summary"].startswith("今日有"):
                    snapshot["summary"] = f"今日主要讨论了{', '.join(topics_mentioned[:3])}等话题" if topics_mentioned else f"今日有{len(messages)}条对话记录"

                print(f"  ✓ 成功生成摘要: {snapshot.get('summary', 'N/A')[:60]}...")
                return snapshot

            except json.JSONDecodeError as e:
                print(f"  ✗ JSON解析失败: {e}")
                print(f"  响应内容: {content[:200]}...")
                if attempt < max_retries - 1:
                    continue
            except Exception as e:
                print(f"  ✗ LLM调用失败: {e}")
                if attempt < max_retries - 1:
                    continue

        # 所有重试失败，使用备用方案生成基础快照
        print("  使用备用方案生成基础快照...")
        return self._generate_fallback_snapshot(messages, date_str, people_mentioned, topics_mentioned)

    def _extract_people(self, text: str) -> List[str]:
        """从文本中提取可能的人名"""
        people = set()

        # 匹配"XX是..."、"XX的"等模式中的XX
        patterns = [
            r'([\u4e00-\u9fa5]{2,4})(?:是|的|和|与)',
            r'(?:父亲|爸爸|母亲|妈妈|奶奶|爷爷|哥哥|姐姐|弟弟|妹妹)(?:是|叫)?([\u4e00-\u9fa5]{2,4})',
            r'([\u4e00-\u9fa5]{2,4})(?:生日|年龄)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) >= 2 and len(match) <= 4:
                    people.add(match)

        return list(people)[:10]

    def _extract_topics(self, text: str) -> List[str]:
        """从文本中提取主题关键词"""
        # 主题关键词列表
        topic_keywords = {
            '生日': ['生日', '出生日期'],
            '家庭': ['父亲', '爸爸', '母亲', '妈妈', '奶奶', '爷爷', '家人', '家庭'],
            '工作': ['工作', '公司', '职位', '职业', '上班'],
            '学习': ['学习', '学校', '大学', '专业', '毕业', '课程'],
            '项目': ['项目', '开发', '代码', '系统', 'MemOS'],
            '健康': ['健康', '医院', '医生', '病', '体检'],
            '生活': ['生活', '日常', '吃饭', '旅行', '购物'],
            '技术': ['技术', '编程', 'AI', '人工智能', '算法']
        }

        topics = set()
        for topic, keywords in topic_keywords.items():
            for kw in keywords:
                if kw in text:
                    topics.add(topic)
                    break

        return list(topics)[:10]

    def _generate_fallback_snapshot(self, messages: List[Dict], date_str: str,
                                    people: List[str], topics: List[str]) -> Dict:
        """备用方案：基于规则生成快照"""
        # 按时间分组提取事件
        events = []
        for i, msg in enumerate(messages[:20]):  # 只处理前20条
            if msg["role"] == "user":
                time_str = msg["created_at"][11:16]
                content = msg["content"][:100]
                events.append({
                    "time": time_str,
                    "who": "User",
                    "what": content,
                    "type": "对话"
                })

        # 生成摘要
        if topics:
            summary = f"今日主要讨论了{', '.join(topics[:3])}等话题，共{len(messages)}条对话"
        elif people:
            summary = f"今日聊到关于{', '.join(people[:3])}的话题，共{len(messages)}条对话"
        else:
            summary = f"今日有{len(messages)}条对话记录，涉及日常交流和个人事务讨论"

        return {
            "date": date_str,
            "summary": summary,
            "events": events[:5],  # 最多5个事件
            "people_involved": people if people else ["用户"],
            "topics": topics if topics else ["日常对话"],
            "key_activities": ["对话交流", "信息查询"] if not topics else topics[:3],
            "message_count": len(messages),
            "_fallback": True  # 标记这是备用方案生成的
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
