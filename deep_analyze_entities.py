# -*- coding: utf-8 -*-
"""
深度分析人物实体 - 找出非姓名表示的实体并分析合并方案
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

print('=' * 90)
print('深度人物实体分析 - 非姓名实体识别与合并方案')
print('=' * 90)
print()

# 获取所有人物实体
entities = supabase.table('mem_l3_entities') \
    .select('id, path, name, description_md') \
    .ilike('path', '/people/%') \
    .execute()

if not entities.data:
    print('没有人物实体')
    exit()

# 定义姓名模式（拼音或中文姓名）
import re

def is_likely_real_name(path):
    """判断是否可能是真实姓名"""
    # 去掉 /people/ 前缀
    name_part = path.replace('/people/', '')

    # 如果是纯拼音（带连字符），可能是真实姓名
    if re.match(r'^[a-z]+(-[a-z]+)+$', name_part):
        return True

    # 如果是中文姓名（2-4个汉字）
    if re.match(r'^[\u4e00-\u9fa5]{2,4}$', name_part):
        return True

    return False

def analyze_entity(e):
    """分析单个实体"""
    path = e['path']
    name = e['name']

    # 获取事实
    facts = supabase.table('mem_l3_atomic_facts') \
        .select('content, status') \
        .eq('entity_id', e['id']) \
        .execute()

    active_facts = [f for f in facts.data if f['status'] == 'active'] if facts.data else []
    superseded_facts = [f for f in facts.data if f['status'] == 'superseded'] if facts.data else []

    e['active_facts'] = active_facts
    e['superseded_facts'] = superseded_facts
    e['active_count'] = len(active_facts)
    e['superseded_count'] = len(superseded_facts)

    # 从事实中提取可能的姓名线索
    name_clues = []
    for f in active_facts:
        content = f['content']
        # 匹配 "XX是..." 模式
        if '是' in content:
            parts = content.split('是')
            if len(parts) >= 2:
                potential_name = parts[0].strip()
                if 2 <= len(potential_name) <= 4:
                    name_clues.append(potential_name)

    e['name_clues'] = list(set(name_clues))
    e['is_real_name'] = is_likely_real_name(path)

    return e

# 分析所有实体
print('正在分析所有实体...')
analyzed = [analyze_entity(e) for e in entities.data]

# 分类
categories = {
    'real_name': [],  # 真实姓名实体
    'relation': [],   # 关系称呼实体 (father, mother, wife, son等)
    'nickname': [],   # 昵称实体 (铁蛋, 贾姐等)
    'mixed': [],      # 混合/不确定
    'archive': [],    # 工作/档案类
}

for e in analyzed:
    path = e['path']
    name = e['name']

    # 根据路径特征分类
    if 'user-' in path or path in ['/people/user', '/people/father', '/people/mother',
                                    '/people/son', '/people/daughter', '/people/wife',
                                    '/people/husband', '/people/parents', '/people/child']:
        categories['relation'].append(e)
    elif path in ['/people/child-of-user', '/people/user-child']:
        categories['relation'].append(e)
    elif 'jiaze' in path.lower() or 'jia-ze' in path.lower() or '李佳泽' in name:
        categories['real_name'].append(e)  # 李佳泽是真实姓名
    elif 'li-jun' in path.lower() or 'lijun' in path.lower() or '俊杰' in name:
        categories['real_name'].append(e)  # 李俊杰是真实姓名
    elif 'li-guo' in path.lower() or 'liguo' in path.lower() or '国栋' in name:
        categories['real_name'].append(e)  # 李国栋是真实姓名
    elif 'yang-gui' in path.lower() or 'yanggui' in path.lower() or '桂花' in name:
        categories['real_name'].append(e)  # 杨桂花是真实姓名
    elif 'jia' in path.lower() or '贾' in name or 'xueyun' in path.lower() or '雪云' in name:
        categories['real_name'].append(e)  # 贾雪云是真实姓名
    elif 'tiedan' in path.lower() or 'tie-dan' in path.lower() or '铁蛋' in name or 'claude' in path.lower():
        categories['nickname'].append(e)  # 铁蛋是昵称，Claude是AI名
    elif 'huiyuan' in path.lower() or '惠源' in name or 'li-hui' in path.lower():
        categories['real_name'].append(e)  # 李惠源是真实姓名
    elif 'jianqiu' in path.lower() or '剑秋' in name or 'gao-jian' in path.lower():
        categories['real_name'].append(e)  # 高剑秋是真实姓名
    elif 'work' in path or '档案' in name or '经历' in name:
        categories['archive'].append(e)
    else:
        categories['mixed'].append(e)

# 打印详细分析
for cat_name, cat_entities in categories.items():
    if not cat_entities:
        continue

    print(f'\n{"="*90}')
    cat_titles = {
        'real_name': '【真实姓名实体】有明确姓名',
        'relation': '【关系称呼实体】需要合并到具体人物',
        'nickname': '【昵称实体】需要建立映射',
        'mixed': '【混合/待确认】需要人工判断',
        'archive': '【档案/工作类】特殊处理'
    }
    print(cat_titles.get(cat_name, f'【{cat_name}】'))
    print('=' * 90)

    for e in sorted(cat_entities, key=lambda x: x['active_count'], reverse=True):
        print(f"\n  路径: {e['path']}")
        print(f"  名称: {e['name']}")
        print(f"  Active事实: {e['active_count']}, Superseded: {e['superseded_count']}")

        if e['name_clues']:
            print(f"  可能的姓名线索: {', '.join(e['name_clues'])}")

        # 显示前3个事实
        for f in e['active_facts'][:3]:
            print(f"    - {f['content']}")
        if len(e['active_facts']) > 3:
            print(f"    ... 还有 {len(e['active_facts']) - 3} 条")

# 生成合并建议
print('\n' + '=' * 90)
print('合并建议 - 非姓名实体到真实姓名实体')
print('=' * 90)

merge_suggestions = []

# 分析每个关系实体应该合并到哪里
for e in categories['relation']:
    path = e['path']
    suggestion = {
        'entity': e,
        'target': None,
        'reason': ''
    }

    # 根据路径判断应该合并到哪里
    if 'user-father' in path or path == '/people/father' or 'my-dad' in path or 'wo-ba' in path or 'yong-hu-fu-qin' in path:
        suggestion['target'] = '/people/li-guodong (李国栋)'
        suggestion['reason'] = '用户父亲 = 李国栋'
    elif 'user-mother' in path or path == '/people/mother' or 'my-mom' in path or 'wo-ma' in path:
        suggestion['target'] = '/people/yang-guihua (杨桂花)'
        suggestion['reason'] = '用户母亲 = 杨桂花'
    elif 'user-wife' in path or path == '/people/wife':
        suggestion['target'] = '/people/jia-xueyun (贾雪云) 或 jia-jie (贾姐)'
        suggestion['reason'] = '用户妻子 = 贾雪云(贾姐)'
    elif 'user-son' in path or path == '/people/son' or 'child-of-user' in path or 'user-child' in path:
        suggestion['target'] = '/people/li-jiaze (李佳泽) 或 jia-ze (佳泽)'
        suggestion['reason'] = '用户儿子 = 李佳泽(佳泽)'
    elif 'user-daughter' in path or path == '/people/daughter':
        suggestion['target'] = '暂无（需要确认是否有女儿）'
        suggestion['reason'] = '用户女儿 - 待确认'
    elif 'user-parents' in path:
        suggestion['target'] = '拆分到 li-guodong 和 yang-guihua'
        suggestion['reason'] = '父母 = 父亲+母亲，需要拆分事实'
    elif path == '/people/user':
        suggestion['target'] = '/people/li-jun-jie (李俊杰)'
        suggestion['reason'] = '用户 = 李俊杰'
    else:
        suggestion['target'] = '待分析'
        suggestion['reason'] = '需要进一步确认'

    merge_suggestions.append(suggestion)

# 打印合并建议
print()
for s in merge_suggestions:
    e = s['entity']
    print(f"  源实体: {e['path']}")
    print(f"  名称: {e['name']}")
    print(f"  Active事实: {e['active_count']}")
    print(f"  建议合并到: {s['target']}")
    print(f"  理由: {s['reason']}")
    print()

# 真实姓名实体合并建议
print('=' * 90)
print('真实姓名实体内部合并 - 处理重复')
print('=' * 90)

real_name_groups = {
    '李国栋': [e for e in categories['real_name'] if 'guodong' in e['path'].lower() or '国栋' in e['name']],
    '李俊杰': [e for e in categories['real_name'] if 'junjie' in e['path'].lower() or '俊杰' in e['name']],
    '杨桂花': [e for e in categories['real_name'] if 'guihua' in e['path'].lower() or '桂花' in e['name']],
    '李佳泽': [e for e in categories['real_name'] if 'jiaze' in e['path'].lower() or '佳泽' in e['name']],
    '贾雪云': [e for e in categories['real_name'] if 'jia' in e['path'].lower() or '贾' in e['name'] or 'xueyun' in e['path'].lower()],
    '李惠源': [e for e in categories['real_name'] if 'huiyuan' in e['path'].lower() or '惠源' in e['name']],
    '高剑秋': [e for e in categories['real_name'] if 'jianqiu' in e['path'].lower() or '剑秋' in e['name']],
}

for person_name, person_entities in real_name_groups.items():
    if len(person_entities) > 1:
        print(f"\n【{person_name}】有 {len(person_entities)} 个重复实体:")
        # 选事实最多的作为主实体
        main = max(person_entities, key=lambda x: x['active_count'])
        print(f"  建议主实体: {main['path']} ({main['active_count']}条active)")
        print(f"  需要合并:")
        for e in person_entities:
            if e['path'] != main['path']:
                print(f"    - {e['path']} ({e['active_count']}条active)")

print('\n' + '=' * 90)
print('分析完成')
print('=' * 90)
