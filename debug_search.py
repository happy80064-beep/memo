"""
调试搜索功能 - 检查为什么找不到父亲的生日
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

print("=" * 60)
print("搜索调试")
print("=" * 60)

# 连接数据库
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# 1. 检查李国栋的实体
print("\n1. 查找李国栋实体:")
result = supabase.table("mem_l3_entities") \
    .select("*") \
    .ilike("name", "%李国栋%") \
    .execute()

if result.data:
    for e in result.data:
        print(f"   - ID: {e['id']}")
        print(f"   - Path: {e['path']}")
        print(f"   - Name: {e['name']}")
else:
    print("   ✗ 未找到")

# 2. 查找包含"生日"的事实
print("\n2. 查找包含'生日'的原子事实:")
result = supabase.table("mem_l3_atomic_facts") \
    .select("*, mem_l3_entities(id, path, name)") \
    .ilike("content", "%生日%") \
    .eq("status", "active") \
    .execute()

if result.data:
    for f in result.data:
        entity = f.get("mem_l3_entities", {})
        print(f"   - 事实: {f['content']}")
        print(f"     实体: {entity.get('name', 'Unknown')} ({entity.get('path', 'Unknown')})")
        print(f"     entity_id: {f.get('entity_id')}")
else:
    print("   ✗ 未找到")

# 3. 测试关键词搜索
print("\n3. 测试关键词搜索 (父亲 或 生日):")
result = supabase.table("mem_l3_atomic_facts") \
    .select("*, mem_l3_entities(id, path, name)") \
    .or_("content.ilike.%父亲%,content.ilike.%生日%") \
    .eq("status", "active") \
    .limit(10) \
    .execute()

if result.data:
    print(f"   找到 {len(result.data)} 条事实:")
    for f in result.data:
        entity = f.get("mem_l3_entities", {})
        print(f"   - {f['content'][:50]}... (实体: {entity.get('name', 'Unknown')})")
else:
    print("   ✗ 未找到")

# 4. 测试具体实体关联
print("\n4. 测试按 entity_id 查找:")
# 先找到李国栋的 ID
entity_result = supabase.table("mem_l3_entities") \
    .select("id") \
    .ilike("name", "%李国栋%") \
    .execute()

if entity_result.data:
    entity_id = entity_result.data[0]['id']
    print(f"   李国栋 entity_id: {entity_id}")

    facts = supabase.table("mem_l3_atomic_facts") \
        .select("*") \
        .eq("entity_id", entity_id) \
        .eq("status", "active") \
        .execute()

    if facts.data:
        print(f"   找到 {len(facts.data)} 条关联事实:")
        for f in facts.data:
            print(f"   - {f['content']}")
    else:
        print("   ✗ 该实体没有关联事实")

print("\n" + "=" * 60)
