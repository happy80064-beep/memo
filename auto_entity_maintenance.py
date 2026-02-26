# -*- coding: utf-8 -*-
"""
自动实体维护任务
- 检测并合并关系实体
- 清理空壳实体
- 每日定时运行
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime

load_dotenv()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# 关系实体识别模式（用于自动检测）
RELATION_PATTERNS = [
    r'-s-(father|mother|son|daughter|wife|husband)',
    r'user-s-',
    r'jiaze-s-',
    r'jun-jie-s-',
    r'child-of-',
]

# 已知的关系映射（用于自动合并）
KNOWN_RELATIONS = {
    '/people/user-father': '/people/li-guodong',
    '/people/user-son': '/people/li-jiaze',
    '/people/user-mother': '/people/yang-guihua',
    '/people/user-wife': '/people/jia-xueyun',
    '/people/user-child': '/people/li-jiaze',
}

def get_active_facts_count(entity_id):
    """获取实体的active facts数量"""
    result = supabase.table('mem_l3_atomic_facts') \
        .select('id', count='exact') \
        .eq('entity_id', entity_id) \
        .eq('status', 'active') \
        .execute()
    return result.count

def is_empty_shell(entity):
    """检查是否是空壳实体"""
    desc = entity.get('description_md', '')
    markers = ['[已合并', '[已归档]', '[已拆分]']
    has_marker = any(m in desc for m in markers)

    if not has_marker:
        return False

    # 检查是否有active facts
    fact_count = get_active_facts_count(entity['id'])
    return fact_count == 0

def cleanup_empty_shells():
    """清理空壳实体"""
    print("\n" + "="*60)
    print("清理空壳实体")
    print("="*60)

    # 查询所有人物实体
    result = supabase.table('mem_l3_entities') \
        .select('id, path, description_md') \
        .eq('entity_type', 'person') \
        .execute()

    deleted = 0
    for e in result.data:
        if is_empty_shell(e):
            try:
                # 硬删除
                supabase.table('mem_l3_atomic_facts').delete().eq('entity_id', e['id']).execute()
                supabase.table('mem_l3_entities').delete().eq('id', e['id']).execute()
                print(f"  已删除: {e['path']}")
                deleted += 1
            except Exception as ex:
                print(f"  [错误] 删除 {e['path']} 失败: {ex}")

    print(f"\n共删除 {deleted} 个空壳实体")
    return deleted

def check_relation_entities():
    """检查关系实体（待实现：根据具体需求扩展）"""
    print("\n" + "="*60)
    print("检查关系实体")
    print("="*60)

    # 查找可能的代称实体
    generic_names = ['爷爷', '奶奶', '爸爸', '妈妈', '父亲', '母亲']

    result = supabase.table('mem_l3_entities') \
        .select('id, path, name, description_md') \
        .eq('entity_type', 'person') \
        .execute()

    found = []
    for e in result.data:
        name = e.get('name', '')
        desc = e.get('description_md', '')

        # 检查是否是代称（且无"已合并"标记）
        if name in generic_names and '[已' not in desc:
            fact_count = get_active_facts_count(e['id'])
            found.append({
                'path': e['path'],
                'name': name,
                'fact_count': fact_count
            })

    if found:
        print(f"\n发现 {len(found)} 个可能需要处理的代称实体:")
        for f in found:
            print(f"  - {f['path']} (名称: {f['name']}, facts: {f['fact_count']})")
        print("\n[提示] 请手动确认这些实体是否需要合并")
    else:
        print("\n没有发现需要处理的代称实体")

    return found

def main():
    print('=' * 60)
    print('自动实体维护任务')
    print(f'开始时间: {datetime.utcnow().isoformat()}')
    print('=' * 60)

    # 1. 清理空壳实体
    deleted = cleanup_empty_shells()

    # 2. 检查关系实体
    relations = check_relation_entities()

    print("\n" + "=" * 60)
    print("任务完成")
    print(f"删除空壳: {deleted}")
    print(f"待处理关系实体: {len(relations)}")
    print("=" * 60)

if __name__ == '__main__':
    main()
