# -*- coding: utf-8 -*-
"""
检查用户的学校信息
"""
import os
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
print(f"实体: {e['name']} ({e['path']})")
print(f"ID: {e['id']}")
print()

# 获取所有active事实
facts = supabase.table("mem_l3_atomic_facts") \
    .select("content, status, created_at") \
    .eq("entity_id", e['id']) \
    .eq("status", "active") \
    .order("created_at", desc=False) \
    .execute()

print(f"共 {len(facts.data)} 条事实\n")
print("=" * 60)

# 筛选学校相关的事实
school_keywords = ['小学', '初中', '高中', '大学', '学校', '就读', '毕业', '专业']
school_facts = []
other_facts = []

for f in facts.data:
    content = f['content']
    if any(kw in content for kw in school_keywords):
        school_facts.append(content)
    else:
        other_facts.append(content)

print("\n【学校相关事实】")
print("-" * 60)
for i, fact in enumerate(school_facts, 1):
    print(f"{i}. {fact}")

print(f"\n【其他事实（共{len(other_facts)}条）】")
print("-" * 60)
for i, fact in enumerate(other_facts[:10], 1):  # 只显示前10条
    print(f"{i}. {fact}")

if len(other_facts) > 10:
    print(f"... 还有 {len(other_facts) - 10} 条其他事实")

print("\n" + "=" * 60)
print("问题分析:")
print("=" * 60)
print(f"学校事实数量: {len(school_facts)}")
print(f"学校事实内容: {school_facts}")
