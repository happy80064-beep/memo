"""
Compiler - The Refactorer
将原子事实编译为连贯的 Markdown 档案 (读写分离)
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Optional

from dotenv import load_dotenv
from supabase import create_client, Client
from langchain_core.messages import SystemMessage, HumanMessage

from llm_factory import get_system_llm

load_dotenv()


class EntityCompiler:
    """实体编译器 - 将原子事实融合为连贯叙事"""

    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )
        self.llm = get_system_llm()

    def get_entities_with_new_facts(self, limit: int = 10) -> List[Dict]:
        """
        获取有新事实写入的实体

        策略: 查找最近 X 分钟内有新事实的实体
        """
        # 获取最近有活跃事实的实体
        result = self.supabase.table("mem_l3_atomic_facts") \
            .select("entity_id, created_at, mem_l3_entities(*)") \
            .eq("status", "active") \
            .order("created_at", desc=True) \
            .limit(100) \
            .execute()

        if not result.data:
            return []

        # 去重，保留最新的
        seen = set()
        entities = []
        for row in result.data:
            entity_id = row["entity_id"]
            if entity_id not in seen:
                seen.add(entity_id)
                entities.append(row["mem_l3_entities"])
                if len(entities) >= limit:
                    break

        return entities

    def get_entity_facts(self, entity_id: str) -> List[Dict]:
        """获取实体的所有活跃事实"""
        result = self.supabase.table("mem_l3_atomic_facts") \
            .select("*") \
            .eq("entity_id", entity_id) \
            .eq("status", "active") \
            .order("created_at", desc=False) \
            .execute()

        return result.data or []

    def compile_description(self, entity: Dict, facts: List[Dict]) -> str:
        """
        编译 Markdown 档案

        Input: 旧 description + 新 facts
        Output: 重写后的连贯 Markdown
        """
        current_desc = entity.get("description_md", "")
        entity_name = entity.get("name", "Untitled")
        entity_path = entity.get("path", "")

        # 构建事实列表
        facts_text = "\n".join([
            f"- [{i+1}] {f['content']} (置信度: {f.get('confidence', 0.8)})"
            for i, f in enumerate(facts)
        ])

        prompt = f"""
你是一个记忆档案编译专家。请将零散的事实融合成连贯的 Markdown 文档。

## 实体信息
- 名称: {entity_name}
- 路径: {entity_path}
- 类型: {entity.get("entity_type", "folder")}

## 当前档案内容
{current_desc if current_desc else "(尚无内容)"}

## 新增/更新的原子事实
{facts_text}

## 编译要求

1. **结构要求**:
   - 标题使用 # {entity_name}
   - 包含 ## 概述 段落 (2-3句话总结)
   - 使用 ## 关键信息 分节整理事实
   - 使用 ## 时间线 记录带日期的事实

2. **内容融合**:
   - 将零散事实融合为流畅叙述
   - 去除重复和矛盾
   - 高置信度事实优先
   - 冲突时保留最新信息

3. **冲突处理** (重要):
   - 如果事实显示状态变化(如"已离职")，归档旧状态
   - 在时间线中标注变化节点

4. **格式规范**:
   - 使用标准 Markdown
   - 内部链接格式: [相关实体](/path/to/entity)
   - 适当使用列表、表格增强可读性

直接输出编译后的 Markdown 内容，不要其他解释。
"""

        response = self.llm.invoke([HumanMessage(content=prompt)])

        content = response.content.strip()
        # 去除可能的代码块标记
        if content.startswith("```markdown"):
            content = content[11:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        return content.strip()

    def detect_conflicts(self, entity_id: str, facts: List[Dict]) -> List[Dict]:
        """
        检测事实冲突

        返回需要被标记为 superseded 的旧事实
        """
        if len(facts) < 2:
            return []

        # 使用 LLM 检测冲突
        facts_json = json.dumps([
            {"id": f["id"], "content": f["content"], "created_at": f["created_at"]}
            for f in facts
        ], ensure_ascii=False, indent=2)

        prompt = f"""
检测以下事实列表中的冲突（同一属性的新旧值）：

{facts_json}

冲突类型示例:
- "他在 A 公司工作" vs "他离职了" / "他加入了 B 公司"
- "项目进行中" vs "项目已取消"
- "喜欢 Python" vs "转向使用 Go"

返回格式 (JSON):
{{
    "conflicts": [
        {{
            "old_fact_id": "uuid",
            "new_fact_id": "uuid",
            "reason": "离职信息替代了在职信息"
        }}
    ]
}}

只输出 JSON，无其他内容。
"""

        response = self.llm.invoke([HumanMessage(content=prompt)])

        try:
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())
            return data.get("conflicts", [])

        except Exception as e:
            print(f"冲突检测解析失败: {e}")
            return []

    def supersede_facts(self, conflicts: List[Dict]):
        """标记被替代的事实"""
        for conflict in conflicts:
            old_id = conflict.get("old_fact_id")
            new_id = conflict.get("new_fact_id")

            if old_id and new_id:
                self.supabase.table("mem_l3_atomic_facts") \
                    .update({
                        "status": "superseded",
                        "superseded_by": new_id,
                        "valid_until": datetime.utcnow().isoformat()
                    }) \
                    .eq("id", old_id) \
                    .execute()

                print(f"  事实被替代: {old_id[:8]}... -> {new_id[:8]}...")

    def update_entity_description(self, entity_id: str, new_description: str):
        """更新实体档案"""
        self.supabase.table("mem_l3_entities") \
            .update({
                "description_md": new_description,
                "last_compiled_at": datetime.utcnow().isoformat()
            }) \
            .eq("id", entity_id) \
            .execute()

    def compile_entity(self, entity: Dict) -> bool:
        """编译单个实体"""
        entity_id = entity["id"]
        entity_name = entity.get("name", "Untitled")

        print(f"\n编译: {entity_name} ({entity_id[:8]}...)")

        # 1. 获取活跃事实
        facts = self.get_entity_facts(entity_id)
        if not facts:
            print("  无活跃事实，跳过")
            return False

        print(f"  活跃事实: {len(facts)} 条")

        # 2. 检测冲突
        conflicts = self.detect_conflicts(entity_id, facts)
        if conflicts:
            print(f"  检测到 {len(conflicts)} 个冲突")
            self.supersede_facts(conflicts)

            # 重新获取（排除被替代的）
            facts = self.get_entity_facts(entity_id)

        # 3. 编译 Markdown
        print("  编译中...")
        new_description = self.compile_description(entity, facts)

        # 4. 更新实体
        self.update_entity_description(entity_id, new_description)
        print(f"  [OK] 编译完成 ({len(new_description)} 字符)")

        return True

    def run(self, limit: int = 10):
        """主运行流程"""
        print(f"[{datetime.now()}] 启动编译器...")

        # 获取待编译实体
        entities = self.get_entities_with_new_facts(limit)
        if not entities:
            print("没有需要编译的实体")
            return 0

        print(f"待编译实体: {len(entities)} 个")

        compiled_count = 0
        for entity in entities:
            try:
                if self.compile_entity(entity):
                    compiled_count += 1
            except Exception as e:
                print(f"  [FAIL] 编译失败: {e}")

        print(f"[{datetime.now()}] 编译完成: {compiled_count}/{len(entities)}")
        return compiled_count


def run_scheduler(interval_minutes: int = 60):
    """定时运行器 - 每小时编译一次"""
    import time

    compiler = EntityCompiler()

    print(f"启动编译器调度器，间隔: {interval_minutes} 分钟")

    while True:
        try:
            compiler.run(limit=10)
        except Exception as e:
            print(f"编译器错误: {e}")

        print(f"等待 {interval_minutes} 分钟...")
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    import sys

    compiler = EntityCompiler()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--once":
            # 单次运行
            compiler.run(limit=10)
        elif sys.argv[1] == "--entity" and len(sys.argv) > 2:
            # 编译指定实体
            entity_path = sys.argv[2]
            result = compiler.supabase.table("mem_l3_entities") \
                .select("*").eq("path", entity_path).execute()
            if result.data:
                compiler.compile_entity(result.data[0])
            else:
                print(f"实体不存在: {entity_path}")
        else:
            print("用法: python compiler.py [--once|--entity /path/to/entity]")
    else:
        # 调度模式
        run_scheduler(interval_minutes=60)
