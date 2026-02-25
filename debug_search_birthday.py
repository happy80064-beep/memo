"""
调试：验证搜索是否能找到生日事实
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
print("调试搜索：是否能找到李国栋的生日事实")
print("=" * 70)

# 获取li-guodong实体ID
entity = supabase.table("mem_l3_entities") \
    .select("id, name") \
    .eq("path", "/people/li-guodong") \
    .execute()

if not entity.data:
    print("未找到li-guodong实体")
    exit()

entity_id = entity.data[0]['id']
print(f"\n实体ID: {entity_id}")

# 方法1: 直接搜索包含"生日"的active事实
print("\n方法1: 直接搜索包含'生日'的active事实")
result1 = supabase.table("mem_l3_atomic_facts") \
    .select("id, content, status, entity_id") \
    .eq("entity_id", entity_id) \
    .eq("status", "active") \
    .ilike("content", "%生日%") \
    .execute()

if result1.data:
    print(f"找到 {len(result1.data)} 条生日事实:")
    for f in result1.data:
        print(f"  - {f['content']}")
else:
    print("  未找到")

# 方法2: 使用or条件搜索（模仿_search_atomic_facts）
print("\n方法2: 使用or条件搜索多个关键词")
result2 = supabase.table("mem_l3_atomic_facts") \
    .select("id, content, status, entity_id, mem_l3_entities(path, name)") \
    .eq("status", "active") \
    .or_("content.ilike.%父亲%,content.ilike.%爸爸%,content.ilike.%李国栋%,content.ilike.%生日%") \
    .limit(10) \
    .execute()

if result2.data:
    print(f"找到 {len(result2.data)} 条事实:")
    for f in result2.data:
        entity_path = f.get("mem_l3_entities", {}).get("path", "Unknown")
        print(f"  [{entity_path}] {f['content']}")
else:
    print("  未找到")

# 方法3: 检查所有active事实（不限制关键词）
print("\n方法3: 检查该实体所有active事实")
result3 = supabase.table("mem_l3_atomic_facts") \
    .select("id, content, status") \
    .eq("entity_id", entity_id) \
    .eq("status", "active") \
    .execute()

if result3.data:
    print(f"找到 {len(result3.data)} 条active事实:")
    for f in result3.data:
        is_birthday = "生日" in f['content'] or "3月20" in f['content']
        mark = " [生日]" if is_birthday else ""
        print(f"  - {f['content']}{mark}")

print("\n" + "=" * 70)
print("结论分析")
print("=" * 70)

birthday_facts_method1 = len([f for f in result1.data if '生日' in f['content']]) if result1.data else 0
birthday_facts_method2 = len([f for f in result2.data if '生日' in f.get('content', '')]) if result2.data else 0
birthday_facts_method3 = len([f for f in result3.data if '生日' in f['content'] or '3月20' in f['content']]) if result3.data else 0

print(f"\n方法1找到的active生日事实: {birthday_facts_method1}")
print(f"方法2找到的active生日事实: {birthday_facts_method2}")
print(f"方法3找到的active生日事实: {birthday_facts_method3}")

if birthday_facts_method3 > 0 and birthday_facts_method2 == 0:
    print("\n问题定位：方法3能找到，但方法2找不到")
    print("可能原因：or条件搜索时，supabase的or语法有问题")
