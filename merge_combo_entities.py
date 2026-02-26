# -*- coding: utf-8 -*-
"""
处理组合实体（user-parents, jiazes-grandparents）
将事实拆分到具体个人
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

print('=' * 60)
print('处理组合实体')
print('=' * 60)

# 处理 user-parents
print("\n1. 处理 user-parents")
print('-' * 60)

entity = supabase.table('mem_l3_entities').select('id').eq('path', '/people/user-parents').execute()
if entity.data:
    entity_id = entity.data[0]['id']
    facts = supabase.table('mem_l3_atomic_facts').select('id, content').eq('entity_id', entity_id).eq('status', 'active').execute()

    guodong = supabase.table('mem_l3_entities').select('id').eq('path', '/people/li-guodong').execute()
    guihua = supabase.table('mem_l3_entities').select('id').eq('path', '/people/yang-guihua').execute()

    if guodong.data and guihua.data:
        guodong_id = guodong.data[0]['id']
        guihua_id = guihua.data[0]['id']

        for fact in facts.data:
            content = fact['content']
            print(f"\n  原事实: {content}")

            # 为用户父亲创建事实
            fact1 = f"李国栋（用户父亲）{content.replace('用户父母', '')}"
            # 为用户母亲创建事实
            fact2 = f"杨桂花（用户母亲）{content.replace('用户父母', '')}"

            print(f"  → 拆分到 li-guodong: {fact1}")
            print(f"  → 拆分到 yang-guihua: {fact2}")

            # 插入新事实
            supabase.table('mem_l3_atomic_facts').insert({
                'entity_id': guodong_id,
                'content': fact1,
                'status': 'active',
                'source_type': 'dialogue',
                'context_json': {'split_from': '/people/user-parents', 'created_at': datetime.utcnow().isoformat()}
            }).execute()

            supabase.table('mem_l3_atomic_facts').insert({
                'entity_id': guihua_id,
                'content': fact2,
                'status': 'active',
                'source_type': 'dialogue',
                'context_json': {'split_from': '/people/user-parents', 'created_at': datetime.utcnow().isoformat()}
            }).execute()

            # 删除原事实
            supabase.table('mem_l3_atomic_facts').delete().eq('id', fact['id']).execute()

        # 删除实体
        supabase.table('mem_l3_entities').delete().eq('id', entity_id).execute()
        print("\n  已删除 user-parents 实体")

        # 触发重新编译
        supabase.table('mem_l3_entities').update({'last_compiled_at': None}).eq('id', guodong_id).execute()
        supabase.table('mem_l3_entities').update({'last_compiled_at': None}).eq('id', guihua_id).execute()
        print("  已触发 li-guodong 和 yang-guihua 重新编译")

# 处理 jiazes-grandparents
print("\n2. 处理 jiazes-grandparents")
print('-' * 60)

entity = supabase.table('mem_l3_entities').select('id').eq('path', '/people/jiazes-grandparents').execute()
if entity.data:
    entity_id = entity.data[0]['id']
    facts = supabase.table('mem_l3_atomic_facts').select('id, content').eq('entity_id', entity_id).eq('status', 'active').execute()

    guodong = supabase.table('mem_l3_entities').select('id').eq('path', '/people/li-guodong').execute()
    guihua = supabase.table('mem_l3_entities').select('id').eq('path', '/people/yang-guihua').execute()

    if guodong.data and guihua.data:
        guodong_id = guodong.data[0]['id']
        guihua_id = guihua.data[0]['id']

        for fact in facts.data:
            content = fact['content']
            print(f"\n  原事实: {content}")

            # 这条事实只提到爷爷
            if '爷爷' in content and '奶奶' not in content:
                new_content = content.replace('佳泽的爷爷', '李国栋（佳泽爷爷）')
                print(f"  → 拆分到 li-guodong: {new_content}")

                supabase.table('mem_l3_atomic_facts').insert({
                    'entity_id': guodong_id,
                    'content': new_content,
                    'status': 'active',
                    'source_type': 'dialogue',
                    'context_json': {'split_from': '/people/jiazes-grandparents', 'created_at': datetime.utcnow().isoformat()}
                }).execute()

            supabase.table('mem_l3_atomic_facts').delete().eq('id', fact['id']).execute()

        # 删除实体
        supabase.table('mem_l3_entities').delete().eq('id', entity_id).execute()
        print("\n  已删除 jiazes-grandparents 实体")

        # 触发重新编译
        supabase.table('mem_l3_entities').update({'last_compiled_at': None}).eq('id', guodong_id).execute()
        supabase.table('mem_l3_entities').update({'last_compiled_at': None}).eq('id', guihua_id).execute()
        print("  已触发 li-guodong 和 yang-guihua 重新编译")

print("\n" + "=" * 60)
print("处理完成")
print("=" * 60)
