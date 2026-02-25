# -*- coding: utf-8 -*-
"""
迁移已知人物的事实
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

print('=' * 70)
print('迁移已知人物的事实')
print('=' * 70)
print()

# 定义迁移映射
migrations = [
    {
        'from_entity_path': '/people/user-mother',
        'to_entity_path': '/people/yang-guihua',
        'relation_fact': '杨桂花是用户的母亲'
    },
    {
        'from_entity_path': '/people/my-dad',
        'to_entity_path': '/people/li-guodong',
        'relation_fact': '李国栋是用户的父亲'
    }
]

for migration in migrations:
    from_path = migration['from_entity_path']
    to_path = migration['to_entity_path']
    relation_fact = migration['relation_fact']

    print(f'迁移: {from_path} -> {to_path}')
    print('-' * 70)

    # 获取源实体
    from_entity = supabase.table('mem_l3_entities') \
        .select('id, name') \
        .eq('path', from_path) \
        .execute()

    if not from_entity.data:
        print(f'  源实体不存在: {from_path}')
        print()
        continue

    from_entity_id = from_entity.data[0]['id']
    from_entity_name = from_entity.data[0]['name']

    # 获取目标实体
    to_entity = supabase.table('mem_l3_entities') \
        .select('id, name') \
        .eq('path', to_path) \
        .execute()

    if not to_entity.data:
        print(f'  目标实体不存在: {to_path}')
        print()
        continue

    to_entity_id = to_entity.data[0]['id']
    to_entity_name = to_entity.data[0]['name']

    # 获取源实体的所有 superseded 事实
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('id, content, context_json') \
        .eq('entity_id', from_entity_id) \
        .execute()

    if not facts.data:
        print(f'  没有事实需要迁移')
        print()
        continue

    print(f'  找到 {len(facts.data)} 条事实')

    # 迁移每条事实
    migrated_count = 0
    for fact in facts.data:
        content = fact['content']

        # 跳过错误/矛盾的事实
        skip_keywords = ['没有记录', '尚未告知', '信息是空白的']
        if any(kw in content for kw in skip_keywords):
            print(f'  跳过错误事实: {content[:40]}...')
            continue

        # 检查目标实体是否已有相同事实（去重）
        existing = supabase.table('mem_l3_atomic_facts') \
            .select('id') \
            .eq('entity_id', to_entity_id) \
            .eq('content', content) \
            .eq('status', 'active') \
            .execute()

        if existing.data:
            print(f'  跳过重复: {content[:40]}...')
            continue

        # 迁移事实到目标实体
        supabase.table('mem_l3_atomic_facts').insert({
            'entity_id': to_entity_id,
            'content': content,
            'status': 'active',
            'source_type': 'manual_entry',
            'context_json': {
                'migrated_from': from_path,
                'migrated_at': datetime.utcnow().isoformat(),
                'original_context': fact.get('context_json', {})
            }
        }).execute()

        print(f'  已迁移: {content[:50]}...')
        migrated_count += 1

    # 添加关系映射事实（如果不存在）
    existing_relation = supabase.table('mem_l3_atomic_facts') \
        .select('id') \
        .eq('entity_id', to_entity_id) \
        .ilike('content', f'%{relation_fact}%') \
        .eq('status', 'active') \
        .execute()

    if not existing_relation.data:
        supabase.table('mem_l3_atomic_facts').insert({
            'entity_id': to_entity_id,
            'content': relation_fact,
            'status': 'active',
            'source_type': 'manual_entry',
            'context_json': {
                'relation_mapping': True,
                'migrated_at': datetime.utcnow().isoformat()
            }
        }).execute()
        print(f'  已添加关系映射: {relation_fact}')
    else:
        print(f'  关系映射已存在: {relation_fact}')

    print(f'  完成！迁移了 {migrated_count} 条事实')
    print()

print('=' * 70)
print('迁移完成！')
print('=' * 70)
