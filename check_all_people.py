# -*- coding: utf-8 -*-
"""
检查所有人物实体，识别重复和待处理问题
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
print('所有人物实体清单')
print('=' * 80)
print()

# 查询所有人物实体
all_people = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, last_compiled_at, compile_version, created_at') \
    .eq('entity_type', 'person') \
    .execute()

print(f"人物实体总数: {len(all_people.data)}")
print()

# 按姓名分组
by_name = {}
relation_entities = []  # 关系实体（路径中包含's'或'of'等）

for e in all_people.data:
    name = e.get('name', '')
    path = e['path']

    # 识别关系实体（通过路径特征）
    if any(kw in path for kw in ['-s-', 'of-', '-child', '-father', '-mother', 'user-', 'jun-jie']):
        relation_entities.append(e)
    else:
        if name not in by_name:
            by_name[name] = []
        by_name[name].append(e)

# 显示有重复姓名的实体
print("=" * 80)
print("按姓名分组（显示有重复的）")
print("=" * 80)
for name in sorted(by_name.keys()):
    entities = by_name[name]
    if len(entities) > 1:
        print(f"\n【{name}】有 {len(entities)} 个实体:")
        for e in entities:
            print(f"  - {e['path']}")
            print(f"    描述: {e.get('description_md', '')[:80]}...")

# 显示关系实体
print("\n" + "=" * 80)
print("关系实体（可能需要合并到具体人物）")
print("=" * 80)
for e in sorted(relation_entities, key=lambda x: x['path']):
    name = e.get('name', '【无姓名】')
    print(f"\n路径: {e['path']}")
    print(f"姓名: {name}")
    desc = e.get('description_md', '')
    if desc:
        print(f"描述: {desc[:100]}...")
    else:
        print(f"描述: 【空】")

    # 获取该实体的atomic_facts数量
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('id', count='exact') \
        .eq('entity_id', e['id']) \
        .eq('status', 'active') \
        .execute()
    print(f"Active事实数: {facts.count}")

print("\n" + "=" * 80)
print("检查完成")
print("=" * 80)
