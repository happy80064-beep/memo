# -*- coding: utf-8 -*-
"""
合并 yong-hu-fu-qin 到 li-guodong
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

print("合并: yong-hu-fu-qin -> li-guodong")
print("-" * 60)

# 获取实体
source = supabase.table('mem_l3_entities').select('id, path, name').eq('path', '/people/yong-hu-fu-qin').execute()
target = supabase.table('mem_l3_entities').select('id, path, name').eq('path', '/people/li-guodong').execute()

if not source.data:
    print("源实体不存在")
    exit()

if not target.data:
    print("目标实体不存在")
    exit()

source_id = source.data[0]['id']
target_id = target.data[0]['id']

# 迁移事实
facts = supabase.table('mem_l3_atomic_facts').select('id, content').eq('entity_id', source_id).eq('status', 'active').execute()

migrated = 0
for fact in facts.data:
    new_content = fact['content'].replace("用户父亲", "李国栋（用户父亲）")

    # 检查重复
    existing = supabase.table('mem_l3_atomic_facts').select('id').eq('entity_id', target_id).eq('content', new_content).eq('status', 'active').execute()

    if existing.data:
        print(f"  跳过重复: {new_content}")
        supabase.table('mem_l3_atomic_facts').delete().eq('id', fact['id']).execute()
    else:
        supabase.table('mem_l3_atomic_facts').update({
            'entity_id': target_id,
            'content': new_content,
            'context_json': {'merged_from': '/people/yong-hu-fu-qin', 'merged_at': datetime.utcnow().isoformat()}
        }).eq('id', fact['id']).execute()
        print(f"  已迁移: {new_content}")
        migrated += 1

# 触发重新编译
supabase.table('mem_l3_entities').update({'last_compiled_at': None}).eq('id', target_id).execute()
print("  已触发重新编译")

# 删除源实体
supabase.table('mem_l3_atomic_facts').delete().eq('entity_id', source_id).execute()
supabase.table('mem_l3_entities').delete().eq('id', source_id).execute()
print("  已删除源实体")
print(f"\n完成，迁移 {migrated} 条事实")
