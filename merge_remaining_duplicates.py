# -*- coding: utf-8 -*-
"""
合并剩余的重复实体
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

print('=' * 80)
print('合并剩余重复实体')
print('=' * 80)

# 剩余需要合并的重复实体
MERGE_TASKS = [
    {
        "source": "/people/li-guo-dong",
        "target": "/people/li-guodong",
        "note": "李国栋重复实体"
    },
    {
        "source": "/people/yang-guang-yao",
        "target": "/people/yang-guangyao",
        "note": "杨光曜重复实体"
    },
    {
        "source": "/people/jia-xue-yun",
        "target": "/people/jia-xueyun",
        "note": "贾雪云重复实体"
    },
    {
        "source": "/people/俊杰",
        "target": "/people/li-jun-jie",
        "note": "俊杰重复实体"
    }
]

def get_entity_by_path(path):
    result = supabase.table('mem_l3_entities') \
        .select('id, path, name') \
        .eq('path', path) \
        .execute()
    return result.data[0] if result.data else None

def get_active_facts(entity_id):
    result = supabase.table('mem_l3_atomic_facts') \
        .select('id, content') \
        .eq('entity_id', entity_id) \
        .eq('status', 'active') \
        .execute()
    return result.data if result.data else []

for task in MERGE_TASKS:
    source_path = task['source']
    target_path = task['target']

    print(f"\n【{task['note']}】")
    print(f"合并: {source_path} -> {target_path}")
    print('-' * 60)

    source = get_entity_by_path(source_path)
    target = get_entity_by_path(target_path)

    if not source:
        print(f"  [跳过] 源实体不存在")
        continue
    if not target:
        print(f"  [错误] 目标实体不存在")
        continue

    # 迁移事实
    facts = get_active_facts(source['id'])
    print(f"  发现 {len(facts)} 条 active facts")

    migrated = 0
    skipped = 0

    for fact in facts:
        # 检查重复
        existing = supabase.table('mem_l3_atomic_facts') \
            .select('id') \
            .eq('entity_id', target['id']) \
            .eq('content', fact['content']) \
            .eq('status', 'active') \
            .execute()

        if existing.data:
            print(f"    跳过重复: {fact['content'][:50]}...")
            skipped += 1
            # 删除源事实
            supabase.table('mem_l3_atomic_facts').delete().eq('id', fact['id']).execute()
        else:
            # 迁移事实
            supabase.table('mem_l3_atomic_facts') \
                .update({
                    'entity_id': target['id'],
                    'context_json': {
                        'merged_from': source_path,
                        'merged_at': datetime.utcnow().isoformat()
                    }
                }) \
                .eq('id', fact['id']) \
                .execute()
            print(f"    已迁移: {fact['content'][:50]}...")
            migrated += 1

    # 触发重新编译
    if migrated > 0:
        supabase.table('mem_l3_entities') \
            .update({'last_compiled_at': None}) \
            .eq('id', target['id']) \
            .execute()
        print(f"  已触发重新编译")

    # 删除源实体
    supabase.table('mem_l3_atomic_facts').delete().eq('entity_id', source['id']).execute()
    supabase.table('mem_l3_entities').delete().eq('id', source['id']).execute()
    print(f"  已删除源实体: {source_path}")
    print(f"  统计: 迁移 {migrated} 条, 跳过 {skipped} 条")

print()
print('=' * 80)
print('合并完成')
print('=' * 80)
