# -*- coding: utf-8 -*-
"""
清理矛盾事实 - 删除过时的"尚未告知"、"不知道"等事实
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
print('清理矛盾/过时事实')
print('=' * 70)
print()

# 定义要清理的矛盾事实模式
contradictory_patterns = [
    '尚未告知',
    '不知道.*生日',
    '请求.*告知.*生日',
    '未记录.*生日',
    '没有记录.*生日',
    '不知道.*具体.*日期',
]

# 要清理的实体（这些实体下的矛盾事实）
target_entities = [
    '/people/tie-dan',
    '/people/tiedan',
    '/people/铁蛋',
    '/people/li-jun-jie',
    '/people/jun-jie',
    '/people/俊杰',
]

total_cleaned = 0

for entity_path in target_entities:
    print(f'检查: {entity_path}')

    # 获取实体
    entity = supabase.table('mem_l3_entities') \
        .select('id, name') \
        .eq('path', entity_path) \
        .execute()

    if not entity.data:
        print(f'  实体不存在')
        continue

    entity_id = entity.data[0]['id']
    entity_name = entity.data[0]['name']

    # 获取所有active事实
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('id, content') \
        .eq('entity_id', entity_id) \
        .eq('status', 'active') \
        .execute()

    if not facts.data:
        print(f'  没有active事实')
        continue

    cleaned_count = 0
    for fact in facts.data:
        content = fact['content']
        should_clean = False

        for pattern in contradictory_patterns:
            import re
            if re.search(pattern, content):
                should_clean = True
                break

        if should_clean:
            print(f'  清理: {content[:60]}...')
            supabase.table('mem_l3_atomic_facts') \
                .update({
                    'status': 'superseded',
                    'context_json': {
                        'cleanup_reason': '矛盾/过时事实：已知道生日，清理旧的"不知道"记录',
                        'cleanup_at': datetime.utcnow().isoformat()
                    }
                }) \
                .eq('id', fact['id']) \
                .execute()
            cleaned_count += 1
            total_cleaned += 1

    if cleaned_count > 0:
        print(f'  清理了 {cleaned_count} 条事实')
    else:
        print(f'  无需清理')
    print()

print('=' * 70)
print(f'总计清理: {total_cleaned} 条矛盾事实')
print('=' * 70)
