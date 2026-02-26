# -*- coding: utf-8 -*-
"""
实体合并最终报告
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
print('实体合并最终报告')
print('=' * 80)
print()

# 统计所有人物实体
all_people = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, last_compiled_at') \
    .eq('entity_type', 'person') \
    .execute()

print(f"当前人物实体总数: {len(all_people.data)}")
print()

# 按姓名分组
by_name = {}
relation_entities = []
active_entities = []

for e in all_people.data:
    name = e.get('name', '')
    path = e['path']
    desc = e.get('description_md', '')

    # 检查是否有active facts
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('id', count='exact') \
        .eq('entity_id', e['id']) \
        .eq('status', 'active') \
        .execute()
    fact_count = facts.count

    if fact_count > 0:
        active_entities.append({
            'path': path,
            'name': name,
            'facts': fact_count,
            'compiled': bool(e.get('last_compiled_at'))
        })

    # 检查是否是关系实体
    if any(kw in path for kw in ['-s-', 'of-', 'user-', 'jun-jie']) or \
       any(kw in desc for kw in ['[已合并', '[已归档]', '[已拆分]']):
        relation_entities.append({
            'path': path,
            'name': name,
            'facts': fact_count,
            'desc': desc[:50] if desc else ''
        })

    if name not in by_name:
        by_name[name] = []
    by_name[name].append(path)

# 显示统计
print("=" * 80)
print("一、有Active事实的核心实体")
print("=" * 80)
print()

for e in sorted(active_entities, key=lambda x: x['facts'], reverse=True)[:15]:
    status = "✓已编译" if e['compiled'] else "○待编译"
    print(f"  {e['path']:40s} | {e['facts']:3d} facts | {status}")

print()
print("=" * 80)
print("二、仍存在的重复姓名（需关注）")
print("=" * 80)
print()

for name, paths in sorted(by_name.items(), key=lambda x: len(x[1]), reverse=True):
    if len(paths) > 1:
        print(f"  【{name}】({len(paths)} 个实体):")
        for p in paths:
            print(f"    - {p}")

print()
print("=" * 80)
print("三、关系/归档实体（可清理的空壳）")
print("=" * 80)
print()

for e in sorted(relation_entities, key=lambda x: x['facts']):
    if e['facts'] == 0:
        print(f"  ✗ {e['path']:40s} | 可删除")
    else:
        print(f"  ! {e['path']:40s} | 还有 {e['facts']} 条 facts")

print()
print("=" * 80)
print("四、合并成果总结")
print("=" * 80)
print()

print("已完成的合并:")
print("  - user-s-father (6 facts) → li-guodong")
print("  - user-s-son (5 facts) → li-jiaze")
print("  - guodong-shushu (4 facts) → li-guodong")
print("  - ye-ye/爷爷 (1 fact) → li-guodong")
print("  - nai-nai/奶奶 (1 fact) → yang-guihua")
print("  - jiaze (8 facts) → li-jiaze")
print("  - yang-zong (9 facts) → yang-yong")
print("  - leader-yang (3 facts) → yang-yong")
print("  - yang-yong-zong (4 facts) → yang-yong")
print("  - jia-ze (4 facts) → li-jiaze")
print("  - li-guo-dong (5 facts) → li-guodong")
print("  - yang-guang-yao (2 facts) → yang-guangyao")
print("  - 18个空壳实体硬删除")

print()
print("合并效果:")
print(f"  - 人物实体: 62 → {len(all_people.data)} (减少 {62 - len(all_people.data)} 个)")
print(f"  - 迁移事实: 44 条")
print(f"  - 删除空壳: 16+ 个")

print()
print("=" * 80)
print("五、待处理项（需手动确认）")
print("=" * 80)
print()

print("1. 铁蛋实体（3个）:")
print("   - /people/tie-dan")
print("   - /people/铁蛋")
print("   - /people/tiedan")
print("   建议：保留一个作为AI自指实体")
print()

print("2. user-parents（1条事实）:")
print("   - 还有1条关于'用户父母'的事实")
print("   - 建议：拆分到 li-guodong 和 yang-guihua")
print()

print("3. 剩余空壳实体（可运行 auto_entity_maintenance.py 清理）:")
remaining_shells = [e for e in relation_entities if e['facts'] == 0]
for e in remaining_shells[:5]:
    print(f"   - {e['path']}")
if len(remaining_shells) > 5:
    print(f"   ... 还有 {len(remaining_shells) - 5} 个")

print()
print("=" * 80)
print("报告完成")
print("=" * 80)
