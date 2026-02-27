# -*- coding: utf-8 -*-
"""
清理无效人物实体
删除或迁移关系代称和通用角色实体（如：用户父亲、用户、AI助手等）
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# 需要清理的无效人名列表
INVALID_PERSON_NAMES = {
    "用户", "用户父亲", "用户母亲", "我父亲", "我母亲",
    "父亲", "母亲", "爸爸", "妈妈", "助手", "系统",
    "管理员", "客服", "老板", "同事", "朋友", "家人",
    "AI助手", "ai助手", "机器人"
}

# 需要清理的 path 前缀
INVALID_PATH_PREFIXES = [
    "/people/user-", "/people/ai-", "/people/my-"
]


def get_invalid_entities():
    """获取所有无效的人物实体"""
    invalid_entities = []

    # 1. 获取所有 person 类型实体
    result = supabase.table("mem_l3_entities") \
        .select("id, path, name, description_md, entity_type") \
        .eq("entity_type", "person") \
        .execute()

    for entity in result.data:
        name = entity.get("name", "")
        path = entity.get("path", "")

        # 检查是否在无效名单
        if name in INVALID_PERSON_NAMES:
            invalid_entities.append({
                **entity,
                "reason": f"无效人名: {name}"
            })
            continue

        # 检查是否包含关系代称关键词
        invalid_keywords = ["父亲", "母亲", "爸爸", "妈妈", "助手", "用户"]
        for kw in invalid_keywords:
            if kw in name and len(name) <= 4:
                invalid_entities.append({
                    **entity,
                    "reason": f"包含关系代称: {name}"
                })
                break

        # 检查 path 前缀
        for prefix in INVALID_PATH_PREFIXES:
            if path.startswith(prefix):
                invalid_entities.append({
                    **entity,
                    "reason": f"关系实体前缀: {path}"
                })
                break

    return invalid_entities


def get_entity_facts_count(entity_id: str) -> int:
    """获取实体的 active facts 数量"""
    result = supabase.table("mem_l3_atomic_facts") \
        .select("id", count="exact") \
        .eq("entity_id", entity_id) \
        .eq("status", "active") \
        .execute()
    return result.count


def cleanup_entity(entity: dict):
    """清理单个无效实体"""
    entity_id = entity["id"]
    path = entity["path"]
    name = entity["name"]
    reason = entity["reason"]

    # 获取 facts 数量
    facts_count = get_entity_facts_count(entity_id)

    print(f"\n处理: {path} ({name})")
    print(f"  原因: {reason}")
    print(f"  facts数量: {facts_count}")

    if facts_count == 0:
        # 没有 facts，直接删除
        try:
            supabase.table("mem_l3_entities") \
                .delete() \
                .eq("id", entity_id) \
                .execute()
            print(f"  ✓ 已删除（无facts）")
            return "deleted"
        except Exception as e:
            print(f"  ✗ 删除失败: {e}")
            return "error"
    else:
        # 有 facts，标记为待处理而不是删除
        try:
            new_path = f"{path}-archived-{entity_id[:8]}"
            supabase.table("mem_l3_entities") \
                .update({
                    "path": new_path,
                    "description_md": f"# {name}\n\n[已归档 - {reason} - 包含 {facts_count} 个facts需人工处理]\n\n{entity.get('description_md', '')}",
                    "entity_type": "folder"  # 改为 folder 类型
                }) \
                .eq("id", entity_id) \
                .execute()
            print(f"  ✓ 已归档（{facts_count}个facts）-> {new_path}")
            return "archived"
        except Exception as e:
            print(f"  ✗ 归档失败: {e}")
            return "error"


def main():
    """主函数"""
    print("=" * 60)
    print("无效人物实体清理工具")
    print("=" * 60)
    print()

    # 获取无效实体
    invalid_entities = get_invalid_entities()

    if not invalid_entities:
        print("没有发现无效的人物实体")
        return

    print(f"发现 {len(invalid_entities)} 个无效实体:")
    for e in invalid_entities:
        facts_count = get_entity_facts_count(e["id"])
        print(f"  - {e['path']} ({e['name']}) - {e['reason']} - {facts_count} facts")

    print()
    confirm = input("确认清理这些实体？(输入 'yes' 执行，其他取消): ")
    if confirm.strip().lower() != "yes":
        print("\n操作已取消")
        return

    print()
    print("=" * 60)
    print("开始清理...")
    print("=" * 60)

    # 执行清理
    deleted = 0
    archived = 0
    errors = 0

    for entity in invalid_entities:
        result = cleanup_entity(entity)
        if result == "deleted":
            deleted += 1
        elif result == "archived":
            archived += 1
        else:
            errors += 1

    print()
    print("=" * 60)
    print("清理完成")
    print("=" * 60)
    print(f"删除: {deleted}")
    print(f"归档: {archived}")
    print(f"失败: {errors}")
    print()

    if archived > 0:
        print("【注意】有实体被归档而非删除，因为它们包含 facts。")
        print("如需处理这些 facts，请手动检查 path 中包含 '-archived-' 的实体。")


if __name__ == "__main__":
    main()
