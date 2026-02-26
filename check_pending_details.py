# -*- coding: utf-8 -*-
"""
详细检查待编译实体的情况
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
print('检查描述为"待编译"的实体')
print('=' * 80)
print()

# 查询所有描述包含"待编译"的实体
all_entities = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, entity_type, last_compiled_at, compile_version, created_at, updated_at') \
    .execute()

pending_desc_entities = [e for e in all_entities.data if '待编译' in (e.get('description_md') or '')]

print(f"描述为'待编译'的实体数量: {len(pending_desc_entities)}")
print()

for e in pending_desc_entities:
    print(f"路径: {e['path']}")
    print(f"姓名: {e.get('name', '【无】')}")
    print(f"类型: {e.get('entity_type')}")
    print(f"编译时间: {e.get('last_compiled_at', 'N/A')}")
    print(f"编译版本: {e.get('compile_version', 'N/A')}")
    print(f"描述: {e.get('description_md', '')}")
    print("-" * 80)

print()
print('=' * 80)
print('检查描述为空的实体')
print('=' * 80)
print()

empty_desc_entities = [e for e in all_entities.data if not e.get('description_md')]

print(f"描述为空的实体数量: {len(empty_desc_entities)}")
print()

for e in empty_desc_entities[:10]:  # 只显示前10个
    print(f"路径: {e['path']}")
    print(f"姓名: {e.get('name', '【无】')}")
    print(f"类型: {e.get('entity_type')}")
    print(f"创建时间: {e['created_at']}")
    print("-" * 80)

if len(empty_desc_entities) > 10:
    print(f"... 还有 {len(empty_desc_entities) - 10} 个")

print()
print('=' * 80)
print('检查可能的问题实体（描述短或无atomic_facts）')
print('=' * 80)
print()

# 检查所有人物实体
people = [e for e in all_entities.data if e.get('entity_type') == 'person']

problem_entities = []
for e in people:
    desc = e.get('description_md', '')
    # 获取atomic_facts数量
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('id', count='exact') \
        .eq('entity_id', e['id']) \
        .eq('status', 'active') \
        .execute()
    fact_count = facts.count

    # 判断是否有问题：描述很短或者没有active事实
    is_short_desc = len(desc) < 50 if desc else True
    is_no_facts = fact_count == 0

    if is_short_desc or is_no_facts:
        problem_entities.append({
            'entity': e,
            'short_desc': is_short_desc,
            'no_facts': is_no_facts,
            'fact_count': fact_count
        })

print(f"可能有问题的人物实体数量: {len(problem_entities)}")
print()
print("标准：描述少于50字符 或 没有active事实")
print()

for p in problem_entities[:20]:  # 只显示前20个
    e = p['entity']
    print(f"路径: {e['path']}")
    print(f"姓名: {e.get('name', '【无】')}")
    desc = e.get('description_md', '')
    print(f"描述长度: {len(desc) if desc else 0} 字符")
    print(f"Active事实数: {p['fact_count']}")
    print(f"问题: {'描述短' if p['short_desc'] else ''} {'无事实' if p['no_facts'] else ''}")
    print("-" * 80)

if len(problem_entities) > 20:
    print(f"... 还有 {len(problem_entities) - 20} 个")

print()
print('=' * 80)
print("检查完成")
print('=' * 80)
