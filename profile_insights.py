"""
Profile Insights - L2 Profile Extractor
提取模式、偏好、经验教训
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client, Client
from langchain_core.messages import HumanMessage

from llm_factory import get_system_llm

load_dotenv()


class ProfileInsightExtractor:
    """画像洞察提取器 - L2 Profile"""

    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )
        self.llm = get_system_llm()

    def get_recent_facts(self, days: int = 7) -> List[Dict]:
        """获取最近 N 天的原子事实"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        result = self.supabase.table("mem_l3_atomic_facts") \
            .select("*, mem_l3_entities(path, name)") \
            .eq("status", "active") \
            .gte("created_at", cutoff) \
            .execute()

        return result.data or []

    def get_recent_entities(self, days: int = 7) -> List[Dict]:
        """获取最近 N 天创建的实体"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        result = self.supabase.table("mem_l3_entities") \
            .select("*") \
            .gte("created_at", cutoff) \
            .execute()

        return result.data or []

    def analyze_patterns(self, facts: List[Dict], entities: List[Dict]) -> Dict:
        """
        分析模式、偏好、经验教训
        """
        # 准备分析材料
        facts_text = []
        for f in facts[:50]:  # 限制数量
            entity_name = f.get("mem_l3_entities", {}).get("name", "Unknown")
            facts_text.append(f"- {entity_name}: {f['content']}")

        entities_text = []
        for e in entities[:30]:
            entities_text.append(f"- {e['path']} ({e['entity_type']}): {e['name']}")

        prompt = f"""基于以下用户最近的活动记录，提取画像洞察。

最近的事实记录:
{chr(10).join(facts_text)}

最近创建的实体:
{chr(10).join(entities_text)}

请分析并输出JSON格式:
{{
    "patterns": [
        {{
            "category": "行为模式/思维模式/工作模式",
            "insight": "描述这个模式",
            "evidence": ["支持证据1", "证据2"],
            "confidence": 0.9
        }}
    ],
    "preferences": [
        {{
            "category": "技术偏好/沟通偏好/学习偏好",
            "preference": "偏好描述",
            "context": "在什么场景下体现"
        }}
    ],
    "lessons_learned": [
        {{
            "situation": "当时的情况",
            "lesson": "学到的经验",
            "application": "如何应用"
        }}
    ],
    "skills": [
        {{
            "skill": "技能名称",
            "level": "beginner/intermediate/expert",
            "evidence": "证据"
        }}
    ]
}}

只输出JSON。"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content.strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            return json.loads(content.strip())

        except Exception as e:
            print(f"分析失败: {e}")
            return {
                "patterns": [],
                "preferences": [],
                "lessons_learned": [],
                "skills": []
            }

    def save_insights(self, insights: Dict, analysis_period: str):
        """保存洞察到 L2 Profile"""
        timestamp = datetime.utcnow().isoformat()

        # 保存模式
        for pattern in insights.get("patterns", []):
            self._save_profile_item(
                category="pattern",
                content=pattern.get("insight", ""),
                evidence=pattern.get("evidence", []),
                confidence=pattern.get("confidence", 0.5),
                context={"analysis_period": analysis_period},
                timestamp=timestamp
            )

        # 保存偏好
        for pref in insights.get("preferences", []):
            self._save_profile_item(
                category="preference",
                content=f"{pref.get('category')}: {pref.get('preference')}",
                evidence=[pref.get("context", "")],
                confidence=0.7,
                context={"analysis_period": analysis_period},
                timestamp=timestamp
            )

        # 保存经验教训
        for lesson in insights.get("lessons_learned", []):
            self._save_profile_item(
                category="lesson",
                content=f"{lesson.get('situation')} → {lesson.get('lesson')}",
                evidence=[lesson.get("application", "")],
                confidence=0.8,
                context={"analysis_period": analysis_period},
                timestamp=timestamp
            )

        # 保存技能
        for skill in insights.get("skills", []):
            self._save_profile_item(
                category="skill",
                content=f"{skill.get('skill')} ({skill.get('level')})",
                evidence=[skill.get("evidence", "")],
                confidence=0.75,
                context={"analysis_period": analysis_period},
                timestamp=timestamp
            )

    def _save_profile_item(self, category: str, content: str, evidence: List,
                          confidence: float, context: Dict, timestamp: str):
        """保存单个画像项"""
        try:
            # 检查是否已存在类似内容
            existing = self.supabase.table("mem_l2_profile") \
                .select("id, confidence") \
                .eq("category", category) \
                .ilike("content", f"%{content[:50]}%") \
                .execute()

            record = {
                "category": category,
                "content": content,
                "evidence": evidence,
                "confidence": confidence,
                "context": context,
                "status": "active",
                "last_confirmed": timestamp
            }

            if existing.data:
                # 更新（如果置信度更高）
                old_conf = existing.data[0].get("confidence", 0)
                if confidence >= old_conf:
                    self.supabase.table("mem_l2_profile") \
                        .update(record) \
                        .eq("id", existing.data[0]["id"]) \
                        .execute()
                    print(f"  更新 {category}: {content[:50]}...")
            else:
                # 新建
                record["first_observed"] = timestamp
                self.supabase.table("mem_l2_profile").insert(record).execute()
                print(f"  新建 {category}: {content[:50]}...")

        except Exception as e:
            print(f"保存失败: {e}")

    def run(self, days: int = 7):
        """运行画像提取"""
        print("=" * 60)
        print("Profile Insight Extractor (L2 Profile)")
        print("=" * 60)

        print(f"\n分析最近 {days} 天的数据...")

        # 获取数据
        facts = self.get_recent_facts(days)
        entities = self.get_recent_entities(days)

        print(f"  原子事实: {len(facts)} 条")
        print(f"  实体: {len(entities)} 个")

        if not facts and not entities:
            print("数据不足，跳过")
            return

        # 分析
        print("\n提取洞察...")
        insights = self.analyze_patterns(facts, entities)

        # 保存
        analysis_period = f"{(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}"
        self.save_insights(insights, analysis_period)

        # 统计
        print(f"\n[OK] 提取完成")
        print(f"  模式: {len(insights.get('patterns', []))} 个")
        print(f"  偏好: {len(insights.get('preferences', []))} 个")
        print(f"  经验教训: {len(insights.get('lessons_learned', []))} 个")
        print(f"  技能: {len(insights.get('skills', []))} 个")


if __name__ == "__main__":
    import sys

    extractor = ProfileInsightExtractor()

    if len(sys.argv) > 1:
        days = int(sys.argv[1])
    else:
        days = 7

    extractor.run(days)
