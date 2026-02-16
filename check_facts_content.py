"""
检查原子事实内容是否完整
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

print("=" * 60)
print("检查原子事实内容完整性")
print("=" * 60)

# 查找李国栋相关的原子事实
print("\n1. 李国栋实体的原子事实:")
entities = supabase.table("mem_l3_entities") \
    .select("id, name, path") \
    .or_("name.ilike.%李国栋%,path.ilike.%li-guodong%") \
    .execute()

if entities.data:
    for entity in entities.data:
        print(f"\n   实体: {entity['name']} ({entity['path']})")

        facts = supabase.table("mem_l3_atomic_facts") \
            .select("content, status") \
            .eq("entity_id", entity['id']) \
            .eq("status", "active") \
            .execute()

        if facts.data:
            for f in facts.data:
                print(f"      - {f['content']}")
        else:
            print("      (没有原子事实)")
else:
    print("   未找到李国栋实体")

# 查找包含"生日"的所有事实
print("\n2. 所有包含'生日'的原子事实:")
facts = supabase.table("mem_l3_atomic_facts") \
    .select("content, status, mem_l3_entities(name, path)") \
    .ilike("content", "%生日%") \
    .eq("status", "active") \
    .execute()

if facts.data:
    for f in facts.data:
        entity = f.get("mem_l3_entities", {})
        entity_name = entity.get("name", "Unknown")
        entity_path = entity.get("path", "Unknown")
        print(f"   [{entity_name}] {f['content']}")
else:
    print("   没有找到生日相关事实")

print("\n" + "=" * 60)
print("问题分析:")
print("如果事实内容只显示'生日是X月X日'而没有主语，")
print("说明Extractor提取时就没有包含完整信息")
print("=" * 60)
