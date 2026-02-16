"""
检查李国栋实体的生日事实关联情况
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

print("=" * 70)
print("李国栋实体生日事实关联检查")
print("=" * 70)

# 1. 查找所有李国栋相关实体
print("\n1. 所有李国栋相关实体:")
entities = supabase.table("mem_l3_entities") \
    .select("id, path, name, description_md") \
    .or_("name.ilike.%李国栋%,path.ilike.%li-guodong%,path.ilike.%father%") \
    .execute()

entity_map = {}
if entities.data:
    for e in entities.data:
        entity_map[e['id']] = e
        print(f"   ID: {e['id']}")
        print(f"   Path: {e['path']}")
        print(f"   Name: {e['name']}")
        print(f"   Desc: {e['description_md'][:100] if e['description_md'] else 'None'}...")
        print()
else:
    print("   未找到李国栋实体")

# 2. 检查每个实体的原子事实
print("\n2. 各实体的原子事实:")
for entity_id, entity in entity_map.items():
    print(f"\n   实体: {entity['name']} ({entity['path']})")
    print(f"   ID: {entity_id}")

    facts = supabase.table("mem_l3_atomic_facts") \
        .select("content, status") \
        .eq("entity_id", entity_id) \
        .eq("status", "active") \
        .execute()

    if facts.data:
        has_birthday = False
        for f in facts.data:
            content = f['content']
            if '生日' in content or '3月20' in content:
                has_birthday = True
                print(f"      [生日事实] {content}")
            else:
                print(f"      - {content}")

        if not has_birthday:
            print("      ⚠️ 该实体没有生日事实！")
    else:
        print("      ✗ 没有原子事实")

# 3. 搜索所有包含"生日"和"3月20"的事实
print("\n3. 全局搜索包含'3月20'的原子事实:")
facts = supabase.table("mem_l3_atomic_facts") \
    .select("content, status, entity_id, mem_l3_entities(path, name)") \
    .ilike("content", "%3月20%") \
    .eq("status", "active") \
    .execute()

if facts.data:
    for f in facts.data:
        entity = f.get("mem_l3_entities", {})
        print(f"   事实: {f['content']}")
        print(f"   关联实体: {entity.get('name', 'Unknown')} ({entity.get('path', 'Unknown')})")
        print(f"   Entity ID: {f['entity_id']}")
        print()
else:
    print("   未找到")

# 4. 检查实体ID是否匹配
print("\n4. 实体ID匹配检查:")
print("   从第3步获取的entity_id是否在步骤1的实体列表中？")

print("\n" + "=" * 70)
print("结论分析:")
print("=" * 70)
print("""
可能的问题:
1. 生日事实关联到了错误的实体ID
2. 存在多个李国栋实体，生日只关联了其中一个
3. 搜索时返回的实体不包含生日事实

解决方案:
- 如果生日事实关联到了错误的实体，需要迁移到正确的实体
- 如果有多个李国栋实体，需要合并或确保事实关联到主实体
""")
