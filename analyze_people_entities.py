# -*- coding: utf-8 -*-
"""
分析人物实体，找出可以合并的
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
print('人物实体分析')
print('=' * 80)
print()

# 获取所有人物实体
entities = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, entity_type') \
    .ilike('path', '/people/%') \
    .execute()

if not entities.data:
    print('没有人物实体')
    exit()

print(f'总计 {len(entities.data)} 个人物实体')
print()

# 按路径分组分析
groups = {}
for e in entities.data:
    path = e['path']
    name = e['name']

    # 获取该实体的事实数量
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('id, content, status') \
        .eq('entity_id', e['id']) \
        .execute()

    active_facts = [f for f in facts.data if f['status'] == 'active'] if facts.data else []
    superseded_facts = [f for f in facts.data if f['status'] == 'superseded'] if facts.data else []

    e['active_count'] = len(active_facts)
    e['superseded_count'] = len(superseded_facts)
    e['total_facts'] = len(facts.data) if facts.data else 0
    e['facts'] = facts.data or []

    # 分组逻辑
    if 'li-guo' in path.lower() or '李国栋' in name or 'guodong' in path.lower():
        groups.setdefault('李国栋', []).append(e)
    elif 'li-jun' in path.lower() or '俊杰' in name or 'junjie' in path.lower():
        groups.setdefault('李俊杰', []).append(e)
    elif 'yang-gui' in path.lower() or '桂花' in name or 'guihua' in path.lower():
        groups.setdefault('杨桂花', []).append(e)
    elif 'jiaze' in path.lower() or '佳泽' in name:
        groups.setdefault('李佳泽', []).append(e)
    elif 'tiedan' in path.lower() or '铁蛋' in name or 'claude' in path.lower():
        groups.setdefault('铁蛋/Claude', []).append(e)
    elif 'user' in path.lower():
        groups.setdefault('User相关', []).append(e)
    elif 'jia' in path.lower() or '贾' in name:
        groups.setdefault('贾家相关', []).append(e)
    else:
        groups.setdefault('其他', []).append(e)

# 打印分组结果
for group_name, group_entities in sorted(groups.items()):
    print(f'\n【{group_name}】({len(group_entities)}个实体)')
    print('-' * 80)
    for e in sorted(group_entities, key=lambda x: x['path']):
        status = '✓' if e['active_count'] > 0 else '✗'
        print(f"  {status} {e['path']}")
        print(f"    名称: {e['name']}")
        print(f"    Active事实: {e['active_count']}, Superseded: {e['superseded_count']}")

        # 显示active事实
        active_facts = [f for f in e['facts'] if f['status'] == 'active']
        for f in active_facts[:3]:  # 只显示前3个
            print(f"      - {f['content']}")
        if len(active_facts) > 3:
            print(f"      ... 还有 {len(active_facts) - 3} 条")
        print()

# 找出需要合并的组
print('=' * 80)
print('合并建议')
print('=' * 80)
print()

for group_name, group_entities in sorted(groups.items()):
    active_entities = [e for e in group_entities if e['active_count'] > 0]
    if len(active_entities) > 1:
        print(f"【{group_name}】有 {len(active_entities)} 个实体有active事实，建议合并：")
        for e in active_entities:
            print(f"  - {e['path']} ({e['active_count']}条active事实)")
        print()

print('=' * 80)
print('分析完成')
print('=' * 80)
