# -*- coding: utf-8 -*-
import os
import sys
# 设置 stdout 编码
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# 查询李俊杰的实体
entity = supabase.table("mem_l3_entities") \
    .select("id, name, path") \
    .eq("path", "/people/li-jun-jie") \
    .execute()

if not entity.data:
    print("未找到李俊杰实体")
    exit()

e = entity.data[0]
entity_id = e['id']

# 获取所有包含学校关键词的事实
school_keywords = ['小学', '初中', '高中', '大学', '就读', '毕业', '专业']

print("查询学校相关事实...")
print()

for kw in school_keywords:
    facts = supabase.table("mem_l3_atomic_facts") \
        .select("content") \
        .eq("entity_id", entity_id) \
        .eq("status", "active") \
        .ilike("content", f"%{kw}%") \
        .execute()

    if facts.data:
        print(f"关键词 '{kw}': {len(facts.data)} 条")
        for f in facts.data:
            print(f"  - {f['content']}")
        print()
