# -*- coding: utf-8 -*-
"""
深度分析最近2天创建的人物实体 - 识别"无真实姓名"问题
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
print('深度分析：最近2天创建的人物实体')
print('=' * 80)
print()

# 计算2天前的日期
two_days_ago = (datetime.utcnow() - timedelta(days=2)).isoformat()

# 查询所有最近2天创建的人物实体
recent_entities = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md, entity_type, last_compiled_at, compile_version, created_at, updated_at') \
    .eq('entity_type', 'person') \
    .gte('created_at', two_days_ago) \
    .execute()

print(f"最近2天创建的人物实体总数: {len(recent_entities.data)}")
print()

# 分类定义
def classify_entity(e):
    """分类实体类型"""
    path = e['path']
    name = e.get('name', '')
    desc = e.get('description_md', '')

    # 检查是否已合并/归档
    if desc and ('[已合并' in desc or '[已归档]' in desc or '[已拆分]' in desc):
        return '已处理的关系实体'

    # 检查是否是关系实体（通过path特征）
    relation_patterns = [
        '-s-', 'of-', '-child', '-father', '-mother', '-son', 'user-',
        'jun-jie', 'jiaze', 'jiazes'
    ]
    if any(p in path for p in relation_patterns):
        return '关系实体'

    # 检查是否是昵称/代称（无真实姓名）
    generic_names = ['爷爷', '奶奶', '爸爸', '妈妈', '父亲', '母亲', '儿子', '叔叔']
    if name in generic_names:
        return '代称实体（无真实姓名）'

    # 检查是否英文名/描述性名称
    if name and any(kw in name.lower() for kw in ["user's", "user", "child", "father", "son"]):
        return '描述性名称（非真实姓名）'

    # 检查是否有真实中文姓名（至少2个汉字）
    if name and len(name) >= 2:
        # 检查是否全是汉字（可能是真实姓名）
        chinese_chars = sum(1 for c in name if '\u4e00' <= c <= '\u9fff')
        if chinese_chars >= 2:
            return '有真实姓名'

    return '其他'

# 分类统计
categories = {}
for e in recent_entities.data:
    category = classify_entity(e)
    if category not in categories:
        categories[category] = []
    categories[category].append(e)

# 显示分类结果
for cat in sorted(categories.keys(), key=lambda x: len(categories[x]), reverse=True):
    entities = categories[cat]
    print(f"\n【{cat}】 - {len(entities)} 个实体")
    print("-" * 80)

    for e in entities:
        path = e['path']
        name = e.get('name', '【无】')
        desc = e.get('description_md', '')
        fact_count = supabase.table('mem_l3_atomic_facts') \
            .select('id', count='exact') \
            .eq('entity_id', e['id']) \
            .eq('status', 'active') \
            .execute().count

        print(f"\n  路径: {path}")
        print(f"  名称: {name}")
        print(f"  Active事实: {fact_count} 条")

        # 显示描述的关键信息
        if desc:
            if '[已合并到' in desc:
                # 提取合并目标
                import re
                match = re.search(r'\[已合并到 ([^\]]+)\]', desc)
                if match:
                    print(f"  合并目标: {match.group(1)}")
            elif len(desc) < 100:
                print(f"  描述: {desc}")
            else:
                # 提取概述部分
                overview_match = re.search(r'## 概述\s*\n([^\n]+)', desc)
                if overview_match:
                    print(f"  概述: {overview_match.group(1)[:80]}...")
                else:
                    print(f"  描述: {desc[:80]}...")

print("\n" + "=" * 80)
print("重点分析：'代称实体'和'描述性名称'实体")
print("=" * 80)

problematic = categories.get('代称实体（无真实姓名）', []) + \
              categories.get('描述性名称（非真实姓名）', [])

if problematic:
    print(f"\n发现 {len(problematic)} 个需要处理的问题实体:")
    print()

    for e in problematic:
        path = e['path']
        name = e.get('name', '')
        desc = e.get('description_md', '')

        # 获取所有active facts
        facts = supabase.table('mem_l3_atomic_facts') \
            .select('content') \
            .eq('entity_id', e['id']) \
            .eq('status', 'active') \
            .execute()

        print(f"\n{'='*60}")
        print(f"实体: {path}")
        print(f"当前名称: {name}")
        print(f"描述长度: {len(desc)} 字符")
        print(f"Active事实数: {len(facts.data) if facts.data else 0}")

        if facts.data:
            print("\n事实内容:")
            for f in facts.data[:5]:
                print(f"  - {f['content']}")
            if len(facts.data) > 5:
                print(f"  ... 还有 {len(facts.data) - 5} 条")

        # 分析应该合并到哪个目标
        print("\n【建议处理方案】")

        if 'guodong' in path.lower() or 'shushu' in path.lower():
            print("  → 建议合并到: /people/li-guodong (李国栋)")
            print("  → 原因: 国栋叔叔 = 李国栋")
        elif 'ye-ye' in path or path.endswith('/grandfather'):
            print("  → 建议合并到: /people/li-guodong (李国栋)")
            print("  → 原因: 爷爷 = 李国栋")
        elif 'nai-nai' in path or 'grandmother' in path:
            print("  → 建议合并到: /people/yang-guihua (杨桂花)")
            print("  → 原因: 奶奶 = 杨桂花")
        elif 'user-s-son' in path or (name and "son" in name.lower()):
            print("  → 建议合并到: /people/li-jiaze (李佳泽)")
            print("  → 原因: user's son = 李佳泽")
        elif 'user-s-father' in path or (name and "father" in name.lower()):
            print("  → 建议合并到: /people/li-guodong (李国栋)")
            print("  → 原因: user's father = 李国栋")
        elif 'yang-zong' in path or 'leader-yang' in path:
            print("  → 需要确认: 这个'杨总'是指哪位？")
            print("  → 如果是指杨光曜 → 合并到 /people/yang-guangyao")
            print("  → 如果是其他人 → 需要创建新实体或确认姓名")

print("\n" + "=" * 80)
print("分析完成")
print("=" * 80)
