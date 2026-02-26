# -*- coding: utf-8 -*-
"""
检查李国栋重复实体
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

print('=' * 80)
print('检查李国栋重复实体')
print('=' * 80)
print()

paths = ['/people/li-guodong', '/people/li-guo-dong']

for path in paths:
    entity = supabase.table('mem_l3_entities') \
        .select('id, path, name, description_md, last_compiled_at') \
        .eq('path', path) \
        .execute()

    if entity.data:
        e = entity.data[0]
        print(f"\n路径: {e['path']}")
        print(f"姓名: {e['name']}")
        print(f"编译时间: {e.get('last_compiled_at', 'N/A')}")

        # 获取 facts
        facts = supabase.table('mem_l3_atomic_facts') \
            .select('content') \
            .eq('entity_id', e['id']) \
            .eq('status', 'active') \
            .execute()

        print(f"Active事实数: {len(facts.data) if facts.data else 0}")

        if facts.data:
            print("事实内容:")
            for f in facts.data[:5]:
                print(f"  - {f['content'][:80]}...")

print("\n" + "=" * 80)
print("建议: li-guo-dong 的 facts 应该合并到 li-guodong")
print("=" * 80)
