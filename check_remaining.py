# -*- coding: utf-8 -*-
"""
检查剩余的 user-parents 和 jiazes-grandparents
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

paths = ['/people/user-parents', '/people/jiazes-grandparents']

for path in paths:
    print(f"\n{'='*60}")
    print(f"检查: {path}")
    print('-'*60)

    entity = supabase.table('mem_l3_entities').select('id, path, name, description_md').eq('path', path).execute()

    if not entity.data:
        print("实体不存在")
        continue

    e = entity.data[0]
    print(f"名称: {e['name']}")
    print(f"描述: {e.get('description_md', '')[:150]}...")

    facts = supabase.table('mem_l3_atomic_facts').select('content').eq('entity_id', e['id']).eq('status', 'active').execute()

    print(f"\nActive事实 ({len(facts.data) if facts.data else 0} 条):")
    for f in facts.data:
        print(f"  - {f['content']}")

    # 分析事实内容
    print("\n【分析】")
    if 'grandparents' in path or 'parents' in path:
        print("  这是组合实体（爷爷奶奶/父母）")
        print("  建议: 将事实拆分到具体个人")

        for f in facts.data:
            content = f['content']
            if '滑雪' in content or '陪伴' in content or '照片' in content:
                print(f"  → 这条事实涉及两位老人，可以分别添加到 li-guodong 和 yang-guihua")
