# -*- coding: utf-8 -*-
"""
最终实体合并执行脚本
Phase 1: 合并有事实的关系实体（替换称呼）
Phase 2: 硬删除空壳实体
Phase 3: 合并其他重复实体
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime

load_dotenv()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# ============================================================================
# 配置：合并映射（源实体 -> 目标实体，替换规则）
# ============================================================================

MERGE_CONFIG = [
    # Phase 1: 关系实体合并（有事实需要迁移）
    {
        "source": "/people/user-s-father",
        "target": "/people/li-guodong",
        "replacements": {
            "User's Father": "李国栋（用户父亲）",
            "User's father": "李国栋（用户父亲）",
            "user's father": "李国栋（用户父亲）"
        }
    },
    {
        "source": "/people/user-s-son",
        "target": "/people/li-jiaze",
        "replacements": {
            "User's Son": "李佳泽（用户儿子）",
            "User's son": "李佳泽（用户儿子）",
            "user's son": "李佳泽（用户儿子）"
        }
    },
    {
        "source": "/people/guodong-shushu",
        "target": "/people/li-guodong",
        "replacements": {
            "国栋叔叔": "李国栋（用户父亲）"
        }
    },
    {
        "source": "/people/ye-ye",
        "target": "/people/li-guodong",
        "replacements": {
            "爷爷": "李国栋（佳泽爷爷）"
        }
    },
    {
        "source": "/people/nai-nai",
        "target": "/people/yang-guihua",
        "replacements": {
            "奶奶": "杨桂花（佳泽奶奶）"
        }
    },
    {
        "source": "/people/jiaze",
        "target": "/people/li-jiaze",
        "replacements": {
            "佳泽": "李佳泽"
        }
    },
    {
        "source": "/people/yang-zong",
        "target": "/people/yang-yong",
        "replacements": {
            "杨总": "杨勇（用户领导）"
        }
    },
    {
        "source": "/people/leader-yang",
        "target": "/people/yang-yong",
        "replacements": {
            "杨总": "杨勇（用户领导）"
        }
    },
    {
        "source": "/people/yang-yong-zong",
        "target": "/people/yang-yong",
        "replacements": {
            "杨勇总": "杨勇（用户领导）",
            "杨总": "杨勇（用户领导）"
        }
    },
    # Phase 3: 其他重复实体
    {
        "source": "/people/jia-ze",
        "target": "/people/li-jiaze",
        "replacements": {
            "佳泽": "李佳泽"
        }
    },
]

# Phase 2: 空壳实体（直接硬删除）
EMPTY_SHELLS = [
    "/people/grandfather",
    "/people/jiazes-mother",
    "/people/jiaze-s-mother",
    "/people/jiaze-s-grandparents",
    "/people/user-child",
    "/people/child-of-user",
    "/people/6-bao",
    "/people/user-grandmother",
    "/people/jia-jie",
    "/people/jun-jie-s-father",
    "/people/jun-jie-s-mother",
    "/people/son",
    "/people/贾雪云",
    "/people/yang-gui-hua",
    "/people/李国栋",
    "/people/李佳泽",
    "/people/wo-ba",
    "/people/wo-ma",
    "/people/li-junjie",  # 保留 li-jun-jie，删除这个
]

def get_entity_by_path(path):
    """根据路径获取实体"""
    result = supabase.table('mem_l3_entities') \
        .select('id, path, name, description_md') \
        .eq('path', path) \
        .execute()
    return result.data[0] if result.data else None

def get_active_facts(entity_id):
    """获取实体的所有active facts"""
    result = supabase.table('mem_l3_atomic_facts') \
        .select('id, content') \
        .eq('entity_id', entity_id) \
        .eq('status', 'active') \
        .execute()
    return result.data if result.data else []

def apply_replacements(text, replacements):
    """应用替换规则"""
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def migrate_facts(source_entity, target_entity, replacements):
    """迁移事实到目标实体"""
    facts = get_active_facts(source_entity['id'])
    migrated = 0
    skipped = 0

    for fact in facts:
        new_content = apply_replacements(fact['content'], replacements)

        # 检查目标实体是否已有相同内容（去重）
        existing = supabase.table('mem_l3_atomic_facts') \
            .select('id') \
            .eq('entity_id', target_entity['id']) \
            .eq('content', new_content) \
            .eq('status', 'active') \
            .execute()

        if existing.data:
            print(f"    跳过重复: {new_content[:50]}...")
            skipped += 1
            continue

        # 更新 fact 的 entity_id 和 content
        supabase.table('mem_l3_atomic_facts') \
            .update({
                'entity_id': target_entity['id'],
                'content': new_content,
                'context_json': {
                    'merged_from': source_entity['path'],
                    'merged_at': datetime.utcnow().isoformat(),
                    'original_content': fact['content']
                }
            }) \
            .eq('id', fact['id']) \
            .execute()

        print(f"    已迁移: {new_content[:50]}...")
        migrated += 1

    return migrated, skipped

def trigger_recompile(entity_id):
    """触发实体重新编译"""
    supabase.table('mem_l3_entities') \
        .update({'last_compiled_at': None}) \
        .eq('id', entity_id) \
        .execute()

def hard_delete_entity(entity_id, path):
    """硬删除实体"""
    try:
        # 先删除关联的 facts（如果有）
        supabase.table('mem_l3_atomic_facts') \
            .delete() \
            .eq('entity_id', entity_id) \
            .execute()

        # 删除实体
        supabase.table('mem_l3_entities') \
            .delete() \
            .eq('id', entity_id) \
            .execute()

        return True
    except Exception as e:
        print(f"    [错误] 删除失败: {e}")
        return False

# ============================================================================
# 主执行流程
# ============================================================================

print('=' * 80)
print('Phase 1: 合并关系实体（迁移事实并替换称呼）')
print('=' * 80)
print()

total_migrated = 0
total_skipped = 0

for config in MERGE_CONFIG:
    source_path = config['source']
    target_path = config['target']
    replacements = config['replacements']

    print(f"\n合并: {source_path} -> {target_path}")
    print('-' * 60)

    # 获取实体
    source = get_entity_by_path(source_path)
    target = get_entity_by_path(target_path)

    if not source:
        print(f"  [跳过] 源实体不存在")
        continue

    if not target:
        print(f"  [错误] 目标实体不存在: {target_path}")
        continue

    # 迁移事实
    migrated, skipped = migrate_facts(source, target, replacements)
    total_migrated += migrated
    total_skipped += skipped

    if migrated > 0:
        # 触发目标实体重新编译
        trigger_recompile(target['id'])
        print(f"  已触发重新编译")

    # 硬删除源实体
    if hard_delete_entity(source['id'], source_path):
        print(f"  已删除源实体")

    print(f"  统计: 迁移 {migrated} 条, 跳过 {skipped} 条")

print()
print('=' * 80)
print('Phase 2: 硬删除空壳实体')
print('=' * 80)
print()

deleted_count = 0
failed_count = 0

for path in EMPTY_SHELLS:
    entity = get_entity_by_path(path)
    if not entity:
        print(f"  [跳过] {path} 不存在")
        continue

    # 检查是否真的没有 active facts
    facts = get_active_facts(entity['id'])
    if facts:
        print(f"  [警告] {path} 还有 {len(facts)} 条 active facts，跳过删除")
        for f in facts[:3]:
            print(f"    - {f['content'][:60]}...")
        failed_count += 1
        continue

    if hard_delete_entity(entity['id'], path):
        print(f"  已删除: {path}")
        deleted_count += 1
    else:
        failed_count += 1

print()
print('=' * 80)
print('合并完成统计')
print('=' * 80)
print(f"迁移事实数: {total_migrated}")
print(f"跳过重复数: {total_skipped}")
print(f"删除空壳数: {deleted_count}")
print(f"删除失败数: {failed_count}")
print('=' * 80)
