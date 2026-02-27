# -*- coding: utf-8 -*-
"""
一次性数据迁移脚本
将现有中文 path 实体迁移到拼音 path

执行前请确保：
1. 已备份数据库
2. 已测试 pinyin_utils.py
3. 确认多音字例外表完整
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client
from pinyin_utils import generate_entity_path, is_chinese

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


def migrate_entities():
    """迁移所有人物实体到拼音 path"""
    print("=" * 80)
    print("人物实体拼音化迁移")
    print("=" * 80)
    print()

    # 1. 获取所有人物实体
    people = supabase.table("mem_l3_entities") \
        .select("id, path, name, entity_type, description_md") \
        .eq("entity_type", "person") \
        .execute()

    print(f"找到 {len(people.data)} 个人物实体")
    print()

    migration_plan = []

    for person in people.data:
        old_path = person["path"]
        name = person["name"]
        entity_id = person["id"]

        # 跳过已经是拼音格式的
        path_without_prefix = old_path.replace("/people/", "") if "/people/" in old_path else old_path
        if not is_chinese(path_without_prefix) and "-" in path_without_prefix:
            # 可能是 li-jia-ze 格式，检查是否已经是标准格式
            expected_path = generate_entity_path(name)
            if old_path == expected_path:
                print(f"  跳过（已是标准格式）: {old_path}")
                continue

        # 生成新的拼音 path
        try:
            new_path = generate_entity_path(name)
        except Exception as e:
            print(f"  错误: 无法转换 {name} - {e}")
            continue

        # 检查新 path 是否已存在
        existing = supabase.table("mem_l3_entities") \
            .select("id, path, name") \
            .eq("path", new_path) \
            .execute()

        if existing.data and existing.data[0]["id"] != entity_id:
            # 目标 path 已存在，需要合并
            target_id = existing.data[0]["id"]
            target_path = existing.data[0]["path"]
            source_facts = get_active_facts_count(entity_id)
            target_facts = get_active_facts_count(target_id)

            migration_plan.append({
                "type": "merge",
                "from_id": entity_id,
                "from_path": old_path,
                "from_name": name,
                "to_id": target_id,
                "to_path": target_path,
                "to_name": existing.data[0]["name"],
                "from_facts": source_facts,
                "to_facts": target_facts
            })
        else:
            # 直接重命名
            migration_plan.append({
                "type": "rename",
                "entity_id": entity_id,
                "old_path": old_path,
                "new_path": new_path,
                "name": name
            })

    # 2. 显示迁移计划
    print("=" * 80)
    print("迁移计划")
    print("=" * 80)

    rename_count = sum(1 for m in migration_plan if m["type"] == "rename")
    merge_count = sum(1 for m in migration_plan if m["type"] == "merge")

    print(f"\n需要重命名: {rename_count} 个实体")
    print(f"需要合并: {merge_count} 个实体")
    print()

    # 显示重命名
    if rename_count > 0:
        print("【重命名列表】")
        for m in migration_plan:
            if m["type"] == "rename":
                print(f"  {m['old_path']:30} -> {m['new_path']}")
        print()

    # 显示合并
    if merge_count > 0:
        print("【合并列表】")
        for m in migration_plan:
            if m["type"] == "merge":
                print(f"  {m['from_path']:30} -> {m['to_path']}")
                print(f"      {m['from_name']}({m['from_facts']} facts) -> {m['to_name']}({m['to_facts']} facts)")
        print()

    # 3. 确认执行
    confirm = input("确认执行迁移？(输入 'yes' 执行，其他取消): ")
    if confirm.strip().lower() != "yes":
        print("\n迁移已取消")
        return

    print("\n" + "=" * 80)
    print("开始执行迁移...")
    print("=" * 80)
    print()

    # 4. 执行迁移
    success_count = 0
    error_count = 0

    for m in migration_plan:
        try:
            if m["type"] == "rename":
                # 直接更新 path
                supabase.table("mem_l3_entities") \
                    .update({"path": m["new_path"]}) \
                    .eq("id", m["entity_id"]) \
                    .execute()
                print(f"✓ 重命名: {m['old_path']} -> {m['new_path']}")
                success_count += 1

            elif m["type"] == "merge":
                # 迁移 facts
                facts = supabase.table("mem_l3_atomic_facts") \
                    .select("*") \
                    .eq("entity_id", m["from_id"]) \
                    .execute()

                migrated = 0
                for fact in facts.data:
                    supabase.table("mem_l3_atomic_facts") \
                        .update({"entity_id": m["to_id"]}) \
                        .eq("id", fact["id"]) \
                        .execute()
                    migrated += 1

                # 标记原实体为已合并
                supabase.table("mem_l3_entities") \
                    .update({
                        "description_md": f"# {m['from_name']}\n\n[已合并至 {m['to_path']} - {m['to_name']}]",
                        "path": f"{m['old_path']}-merged-{m['from_id'][:8]}"
                    }) \
                    .eq("id", m["from_id"]) \
                    .execute()

                print(f"✓ 合并: {m['from_path']} -> {m['to_path']} ({migrated} facts)")
                success_count += 1

        except Exception as e:
            print(f"✗ 错误: {m.get('old_path', m.get('from_path'))} - {e}")
            error_count += 1

    print()
    print("=" * 80)
    print("迁移完成")
    print("=" * 80)
    print(f"成功: {success_count}")
    print(f"失败: {error_count}")
    print()

    # 5. 清理建议
    if merge_count > 0:
        print("【下一步】")
        print("运行以下命令清理空壳实体：")
        print("  python auto_entity_maintenance.py")
        print()


if __name__ == "__main__":
    migrate_entities()
