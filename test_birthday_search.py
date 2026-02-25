# -*- coding: utf-8 -*-
"""
精确测试：李国栋的生日事实搜索
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

print('=== 精确测试：李国栋的生日事实 ===')
print()

# 直接搜索李国栋实体下的所有事实
entity = supabase.table('mem_l3_entities').select('id').eq('path', '/people/li-guodong').execute()

if entity.data:
    entity_id = entity.data[0]['id']

    # 获取所有事实
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('content') \
        .eq('entity_id', entity_id) \
        .eq('status', 'active') \
        .execute()

    print(f'李国栋所有active事实 ({len(facts.data) if facts.data else 0}条):')
    if facts.data:
        for f in facts.data:
            has_birthday = '生日' in f['content']
            marker = ' ★生日★' if has_birthday else ''
            print(f'  - {f["content"]}{marker}')

    print()
    print('--- 测试搜索 "生日" ---')

    # 测试like搜索
    result = supabase.table('mem_l3_atomic_facts') \
        .select('content, mem_l3_entities(path)') \
        .eq('status', 'active') \
        .ilike('content', '%生日%') \
        .execute()

    print(f'找到 {len(result.data) if result.data else 0} 条包含"生日"的事实:')
    if result.data:
        for r in result.data:
            print(f'  - {r["content"]} ({r["mem_l3_entities"]["path"]})')

        # 检查李国栋的生日事实是否在其中
        liguodong_birthday = any('li-guodong' in r['mem_l3_entities']['path']
                                 for r in result.data)
        print()
        print(f'李国栋的生日事实在结果中: {liguodong_birthday}')
    else:
        print('  没有结果')
