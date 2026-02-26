# -*- coding: utf-8 -*-
"""
检查 yong-hu-fu-qin 实体
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

entity = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md') \
    .eq('path', '/people/yong-hu-fu-qin') \
    .execute()

if entity.data:
    e = entity.data[0]
    print(f"路径: {e['path']}")
    print(f"姓名: {e['name']}")
    print(f"描述: {e.get('description_md', '')[:200]}")

    facts = supabase.table('mem_l3_atomic_facts') \
        .select('content') \
        .eq('entity_id', e['id']) \
        .eq('status', 'active') \
        .execute()

    print(f"\nActive事实数: {len(facts.data) if facts.data else 0}")
    for f in facts.data:
        print(f"  - {f['content']}")
else:
    print("实体不存在")
