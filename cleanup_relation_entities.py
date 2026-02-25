# -*- coding: utf-8 -*-
"""
清理关系实体 - 删除 user-father 等关系实体及其事实
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

# 关系实体模式
relation_patterns = [
    'user-father', 'user-mother', 'user-wife', 'user-husband',
    'user-son', 'user-daughter',
    'father', 'mother', 'wo-ba', 'wo-ma',
    'my-dad', 'my-mom',
    'junjie'  # 也检查 junjie 实体下的错误事实
]

print('=' * 70)
print('步骤1: 查看需要清理的关系实体')
print('=' * 70)
print()

total_entities = 0
total_facts = 0
entities_to_cleanup = []

for pattern in relation_patterns:
    # 查找匹配的实体
    entities = supabase.table('mem_l3_entities') \
        .select('id, path, name') \
        .ilike('path', f'%/people/{pattern}%') \
        .execute()

    if entities.data:
        print(f'[发现] 路径匹配: {pattern}')
        for e in entities.data:
            print(f'  实体: {e["path"]}')
            print(f'  名称: {e["name"]}')
            print(f'  ID: {e["id"]}')

            # 查看该实体的事实
            facts = supabase.table('mem_l3_atomic_facts') \
                .select('id, content, status') \
                .eq('entity_id', e['id']) \
                .execute()

            active_facts = [f for f in facts.data if f['status'] == 'active'] if facts.data else []

            if active_facts:
                print(f'  Active事实数: {len(active_facts)}')
                for f in active_facts:
                    print(f'    - {f["content"]}')
                total_facts += len(active_facts)
            else:
                print(f'  Active事实数: 0')

            entities_to_cleanup.append({
                'id': e['id'],
                'path': e['path'],
                'name': e['name'],
                'facts': active_facts
            })

            total_entities += 1
        print()

print('=' * 70)
print(f'发现 {total_entities} 个关系实体, {total_facts} 条active事实')
print('=' * 70)
print()

# 步骤2: 清理
print('=' * 70)
print('步骤2: 清理关系实体')
print('=' * 70)
print()

for entity in entities_to_cleanup:
    print(f'处理: {entity["path"]}')

    # 标记所有active事实为 superseded
    for fact in entity['facts']:
        print(f'  标记事实为 superseded: {fact["content"][:50]}...')
        supabase.table('mem_l3_atomic_facts') \
            .update({
                'status': 'superseded',
                'context_json': {
                    'cleanup_reason': '关系实体清理，迁移到具体人物实体',
                    'cleanup_time': datetime.utcnow().isoformat(),
                    'original_entity': entity['path']
                }
            }) \
            .eq('id', fact['id']) \
            .execute()

    # 可选：标记实体本身为 archived（而不是删除，保留历史）
    print(f'  标记实体为 archived')
    supabase.table('mem_l3_entities') \
        .update({
            'description_md': f'[已归档] 关系实体已清理，内容已迁移或删除。原名称: {entity["name"]}'
        }) \
        .eq('id', entity['id']) \
        .execute()

    print(f'  ✓ 清理完成')
    print()

print('=' * 70)
print('清理完成！')
print('=' * 70)
