# -*- coding: utf-8 -*-
"""
检查最近2天创建的人物实体和待编译实体
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timedelta

load_dotenv()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

print('=' * 80)
print('检查最近2天创建的人物实体')
print('=' * 80)
print()

# 计算2天前的日期
two_days_ago = (datetime.utcnow() - timedelta(days=2)).isoformat()

# 查询最近2天创建的人物实体
recent_entities = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, entity_type, tags, last_compiled_at, compile_version, created_at, updated_at') \
    .eq('entity_type', 'person') \
    .gte('created_at', two_days_ago) \
    .execute()

print(f"最近2天创建的人物实体数量: {len(recent_entities.data) if recent_entities.data else 0}")
print()

if recent_entities.data:
    print("详细信息:")
    print("-" * 80)
    for e in recent_entities.data:
        name_display = e.get('name') if e.get('name') else "【无姓名】"
        compiled_status = "已编译" if e.get('last_compiled_at') else "待编译"
        print(f"路径: {e['path']}")
        print(f"姓名: {name_display}")
        print(f"编译状态: {compiled_status}")
        print(f"编译时间: {e.get('last_compiled_at', 'N/A')}")
        print(f"编译版本: {e.get('compile_version', 'N/A')}")
        print(f"创建时间: {e['created_at']}")
        print(f"描述长度: {len(e.get('description_md', '') if e.get('description_md') else '')} 字符")
        print("-" * 80)

print()
print('=' * 80)
print('检查所有"待编译"状态的人物实体（last_compiled_at 为 null）')
print('=' * 80)
print()

# 查询所有待编译的人物实体（last_compiled_at 为 null）
pending_people = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, entity_type, tags, last_compiled_at, compile_version, created_at, updated_at') \
    .eq('entity_type', 'person') \
    .is_('last_compiled_at', 'null') \
    .execute()

print(f"待编译人物实体总数: {len(pending_people.data) if pending_people.data else 0}")
print()

if pending_people.data:
    print("待编译人物实体列表:")
    print("-" * 80)
    for e in pending_people.data:
        name_display = e.get('name') if e.get('name') else "【无姓名】"
        print(f"\n路径: {e['path']}")
        print(f"姓名: {name_display}")
        print(f"创建时间: {e['created_at']}")
        desc = e.get('description_md', '')
        if desc:
            print(f"描述预览: {desc[:150]}...")
        else:
            print(f"描述: 【空】")

print()
print('=' * 80)
print('检查所有没有 name 的人物实体（无论编译状态）')
print('=' * 80)
print()

# 查询所有没有name的人物实体
all_people = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, last_compiled_at, created_at') \
    .eq('entity_type', 'person') \
    .execute()

no_name_people = [e for e in all_people.data if not e.get('name')]

print(f"无姓名的人物实体数量: {len(no_name_people)}")
print()

if no_name_people:
    for e in no_name_people:
        compiled_status = "已编译" if e.get('last_compiled_at') else "待编译"
        print(f"  路径: {e['path']}")
        print(f"  状态: {compiled_status}")
        print(f"  创建时间: {e['created_at']}")
        desc = e.get('description_md', '')
        if desc:
            print(f"  描述预览: {desc[:100]}...")
        print()

print()
print('=' * 80)
print('检查所有实体类型的待编译情况统计')
print('=' * 80)
print()

# 查询所有待编译实体
all_pending = supabase.table('mem_l3_entities') \
    .select('id, path, name, entity_type, last_compiled_at, created_at') \
    .is_('last_compiled_at', 'null') \
    .execute()

if all_pending.data:
    by_type = {}
    for e in all_pending.data:
        etype = e.get('entity_type', 'unknown')
        if etype not in by_type:
            by_type[etype] = []
        by_type[etype].append(e)

    for etype in sorted(by_type.keys()):
        entities = by_type[etype]
        print(f"\n【{etype}】类型 - {len(entities)} 个待编译实体:")
        print("-" * 80)
        for e in entities[:10]:  # 只显示前10个
            name_display = e.get('name') if e.get('name') else "【无姓名】"
            print(f"  - {e['path']} (姓名: {name_display}, 创建于: {e['created_at'][:10]})")
        if len(entities) > 10:
            print(f"  ... 还有 {len(entities) - 10} 个")

print()
print('=' * 80)
print("检查完成")
print('=' * 80)
