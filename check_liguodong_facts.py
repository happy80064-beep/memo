# -*- coding: utf-8 -*-
"""
检查李国栋实体的事实
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

print('=== 李国栋实体事实检查 ===')
print()

# 获取李国栋实体
entity = supabase.table('mem_l3_entities').select('id, path, name').eq('path', '/people/li-guodong').execute()

if not entity.data:
    print('李国栋实体不存在！')
    exit()

e = entity.data[0]
print(f"实体: {e['path']}")
print(f"名称: {e['name']}")
print()

# 获取所有active事实
facts = supabase.table('mem_l3_atomic_facts').select('content, status').eq('entity_id', e['id']).eq('status', 'active').execute()

if facts.data:
    print(f"Active事实数量: {len(facts.data)}")
    print()
    for f in facts.data:
        print(f"  - {f['content']}")
else:
    print('没有active事实！')

print()
print('=== 检查完成 ===')
