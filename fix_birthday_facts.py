"""
修复被错误标记为superseded的生日事实
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
print("修复生日事实状态")
print("=" * 70)

# 获取li-guodong实体
entity = supabase.table("mem_l3_entities") \
    .select("id") \
    .eq("path", "/people/li-guodong") \
    .execute()

if not entity.data:
    print("未找到li-guodong实体")
    exit()

entity_id = entity.data[0]['id']

# 查找所有包含"生日"和"3月20"的superseded事实
facts = supabase.table("mem_l3_atomic_facts") \
    .select("id, content, status, superseded_by") \
    .eq("entity_id", entity_id) \
    .ilike("content", "%生日%") \
    .execute()

if not facts.data:
    print("未找到生日相关事实")
    exit()

print(f"\n找到 {len(facts.data)} 条生日相关事实")

# 找出应该被恢复的事实（最新的那个）
birthday_facts = [f for f in facts.data if "3月20" in f['content']]

if not birthday_facts:
    print("未找到3月20日的生日事实")
    exit()

# 按创建时间排序，最新的为基准
birthday_facts.sort(key=lambda x: x.get('created_at', ''), reverse=True)

print(f"\n找到 {len(birthday_facts)} 条'3月20日'生日事实:")
for f in birthday_facts:
    print(f"  - [{f['status']}] {f['content'][:50]}... (ID: {f['id'][:8]}...)")

# 策略：保留最新的一条为active，其他的保持superseded
if birthday_facts:
    # 最新的一个恢复为active
    latest = birthday_facts[0]
    print(f"\n将最新的事实恢复为active:")
    print(f"  ID: {latest['id'][:8]}...")
    print(f"  内容: {latest['content']}")

    result = supabase.table("mem_l3_atomic_facts") \
        .update({
            "status": "active",
            "superseded_by": None,
            "valid_until": None
        }) \
        .eq("id", latest['id']) \
        .execute()

    print(f"  [OK] 已恢复为active")

    # 其他的保持superseded（因为它们被最新的事实替代了，这是正确的）
    if len(birthday_facts) > 1:
        print(f"\n其他 {len(birthday_facts)-1} 条生日事实保持superseded状态（被最新事实替代，这是正确的）")

# 验证修复
print("\n" + "=" * 70)
print("验证修复结果:")
print("=" * 70)

active_facts = supabase.table("mem_l3_atomic_facts") \
    .select("content") \
    .eq("entity_id", entity_id) \
    .eq("status", "active") \
    .ilike("content", "%生日%") \
    .execute()

if active_facts.data:
    print(f"\n现在active的生日事实:")
    for f in active_facts.data:
        print(f"  ✓ {f['content']}")
else:
    print("\n警告: 仍然没有active的生日事实！")

print("\n修复完成！")
