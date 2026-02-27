# -*- coding: utf-8 -*-
"""
定时实体去重任务
每天运行一次，检测并合并重复实体
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client
from pinyin_utils import chinese_to_pinyin, is_chinese

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)


def get_active_facts_count(entity_id: str) -> int:
    """获取实体的 active facts 数量"""
    result = supabase.table("mem_l3_atomic_facts") \
        .select("id", count="exact") \
        .eq("entity_id", entity_id) \
        .eq("status", "active") \
        .execute()
    return result.count


def select_main_entity(entities: list) -> dict:
    """
    选择主实体
    评分标准：
    1. facts 数量最多（权重10）
    2. 已编译（description 不是"待编译"）（权重50）
    3. 拼音格式优先（权重20）
    """
    scored = []

    for e in entities:
        score = 0

        # facts 数量
        facts_count = get_active_facts_count(e["id"])
        score += facts_count * 10

        # 是否已编译
        desc = e.get("description_md", "")
        if desc and "待编译" not in desc and len(desc) > 100:
            score += 50

        # 拼音格式
        path = e.get("path", "")
        path_part = path.replace("/people/", "") if "/people/" in path else path
        if not is_chinese(path_part) and "-" in path_part:
            score += 20

        scored.append((score, facts_count, e))

    # 按得分排序，返回最高分的
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2]


def auto_merge_duplicates():
    """自动合并重复实体"""
    print(f"[{datetime.utcnow().isoformat()}] 开始自动去重...")
    print()

    # 1. 获取所有人物实体
    people = supabase.table("mem_l3_entities") \
        .select("id, path, name, description_md") \
        .eq("entity_type", "person") \
        .execute()

    # 2. 按拼音分组
    pinyin_groups = {}
    for p in people.data:
        name = p.get("name", "")
        if not name or not is_chinese(name):
            continue

        py = chinese_to_pinyin(name)
        if py not in pinyin_groups:
            pinyin_groups[py] = []
        pinyin_groups[py].append(p)

    # 3. 处理重复组
    merged_count = 0
    migrated_facts_count = 0

    for py, entities in pinyin_groups.items():
        if len(entities) <= 1:
            continue

        # 选择主实体
        main = select_main_entity(entities)
        main_facts = get_active_facts_count(main["id"])

        print(f"发现重复: {main['name']} ({len(entities)} 个实体)")
        print(f"  主实体: {main['path']} (facts: {main_facts})")

        # 合并其他实体
        for e in entities:
            if e["id"] == main["id"]:
                continue

            # 迁移 facts
            facts = supabase.table("mem_l3_atomic_facts") \
                .select("*") \
                .eq("entity_id", e["id"]) \
                .execute()

            migrated = 0
            for fact in facts.data:
                try:
                    supabase.table("mem_l3_atomic_facts") \
                        .update({"entity_id": main["id"]}) \
                        .eq("id", fact["id"]) \
                        .execute()
                    migrated += 1
                except Exception as ex:
                    print(f"    迁移 fact 失败: {ex}")

            # 标记为空壳
            try:
                supabase.table("mem_l3_entities") \
                    .update({
                        "description_md": f"# {e['name']}\n\n[已合并至 {main['path']} - {main['name']}]",
                        "path": f"{e['path']}-merged-{e['id'][:8]}"
                    }) \
                    .eq("id", e["id"]) \
                    .execute()

                print(f"  合并: {e['path']} -> {main['path']} ({migrated} facts)")
                merged_count += 1
                migrated_facts_count += migrated
            except Exception as ex:
                print(f"  标记空壳失败: {ex}")

    print()

    # 4. 清理空壳
    deleted = cleanup_empty_shells()

    print(f"[{datetime.utcnow().isoformat()}] 去重完成:")
    print(f"  合并实体: {merged_count}")
    print(f"  迁移 facts: {migrated_facts_count}")
    print(f"  清理空壳: {deleted}")
    print()

    return merged_count


def cleanup_empty_shells() -> int:
    """清理空壳实体（已合并且无 facts）"""
    # 查找所有标记为已合并的实体
    shells = supabase.table("mem_l3_entities") \
        .select("id, path, description_md") \
        .like("description_md", "%[已合并%") \
        .execute()

    deleted = 0
    for shell in shells.data:
        # 检查是否还有 active facts
        facts = supabase.table("mem_l3_atomic_facts") \
            .select("id", count="exact") \
            .eq("entity_id", shell["id"]) \
            .eq("status", "active") \
            .execute()

        if facts.count == 0:
            try:
                # 删除实体
                supabase.table("mem_l3_entities") \
                    .delete() \
                    .eq("id", shell["id"]) \
                    .execute()
                print(f"  删除空壳: {shell['path']}")
                deleted += 1
            except Exception as e:
                print(f"  删除失败 {shell['path']}: {e}")

    return deleted


if __name__ == "__main__":
    auto_merge_duplicates()
