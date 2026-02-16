"""
检查父亲生日搜索问题 - 验证数据流完整链路
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

print("=" * 60)
print("父亲生日数据链路检查")
print("=" * 60)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# 1. 检查L0 Buffer最近的用户消息
print("\n1. L0 Buffer 最近用户消息:")
result = supabase.table("mem_l0_buffer") \
    .select("role, content, created_at") \
    .eq("role", "user") \
    .order("created_at", desc=True) \
    .limit(5) \
    .execute()

if result.data:
    for r in result.data:
        print(f"   [{r['created_at'][:16]}] {r['content'][:50]}...")
else:
    print("   ✗ 没有找到user消息！")

# 2. 查找父亲相关的实体
print("\n2. L3 Entities - 父亲相关:")
result = supabase.table("mem_l3_entities") \
    .select("id, path, name") \
    .or_("name.ilike.%父亲%,name.ilike.%爸爸%,name.ilike.%李国栋%") \
    .execute()

if result.data:
    for e in result.data:
        print(f"   - {e['path']} (ID: {e['id'][:8]}...)")

        # 3. 检查该实体的事实
        facts = supabase.table("mem_l3_atomic_facts") \
            .select("content, status") \
            .eq("entity_id", e['id']) \
            .eq("status", "active") \
            .execute()

        if facts.data:
            for f in facts.data:
                print(f"      - {f['content']}")
else:
    print("   ✗ 没有找到父亲相关实体")

# 4. 直接搜索包含"生日"的事实
print("\n3. 直接搜索含'生日'的原子事实:")
result = supabase.table("mem_l3_atomic_facts") \
    .select("content, mem_l3_entities(name)") \
    .ilike("content", "%生日%") \
    .eq("status", "active") \
    .execute()

if result.data:
    for f in result.data:
        entity_name = f.get("mem_l3_entities", {}).get("name", "Unknown")
        print(f"   - [{entity_name}] {f['content']}")
else:
    print("   ✗ 没有找到生日相关事实")

print("\n" + "=" * 60)

# 5. 检查未处理的L0记录（Extractor是否在工作）
print("\n4. 未处理的L0记录 (等待Extractor处理):")
result = supabase.table("mem_l0_buffer") \
    .select("role, content, processed") \
    .eq("processed", False) \
    .execute()

if result.data:
    print(f"   有 {len(result.data)} 条未处理记录")
    for r in result.data[:3]:
        print(f"   - [{r['role']}] {r['content'][:40]}...")
else:
    print("   没有未处理记录（Extractor可能正常运行）")

print("\n" + "=" * 60)
print("检查完成")
print("=" * 60)
