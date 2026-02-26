# -*- coding: utf-8 -*-
"""
检查所有"杨"姓实体，确认合并关系
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
print('所有"杨"姓实体分析')
print('=' * 80)
print()

# 查询所有人物实体
all_people = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, created_at') \
    .eq('entity_type', 'person') \
    .execute()

# 筛选杨姓实体
yang_entities = [e for e in all_people.data if e.get('name') and '杨' in e['name']]

print(f"找到 {len(yang_entities)} 个杨姓实体:")
print()

for e in yang_entities:
    path = e['path']
    name = e.get('name', '')
    desc = e.get('description_md', '')

    # 获取active facts
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('content') \
        .eq('entity_id', e['id']) \
        .eq('status', 'active') \
        .execute()

    print(f"{'='*60}")
    print(f"路径: {path}")
    print(f"姓名: {name}")
    print(f"创建时间: {e['created_at']}")
    print(f"Active事实数: {len(facts.data) if facts.data else 0}")

    if desc:
        if len(desc) > 200:
            print(f"描述预览: {desc[:200]}...")
        else:
            print(f"描述: {desc}")

    if facts.data:
        print("关键事实:")
        for f in facts.data[:3]:
            print(f"  - {f['content'][:80]}...")

    print()

print('=' * 80)
print("请确认: 'leader-yang' 和 'yang-zong' 应该合并到哪个目标？")
print("从描述看:")
print("  - yang-zong: 基金融资方案的最终审批人（职场关系）")
print("  - leader-yang: 描述为'待编译'，可能是重复创建")
print("  - yang-guangyao: 部门成员，游戏伙伴")
print("=" * 80)
