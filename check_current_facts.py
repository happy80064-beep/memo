"""
检查li-guodong实体当前的所有事实
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
print("检查 /people/li-guodong 实体当前的所有事实")
print("=" * 70)

# 获取li-guodong实体
entity = supabase.table("mem_l3_entities") \
    .select("id, path, name") \
    .eq("path", "/people/li-guodong") \
    .execute()

if not entity.data:
    print("未找到li-guodong实体")
    exit()

entity_id = entity.data[0]['id']
print(f"\n实体ID: {entity_id}")
print(f"路径: {entity.data[0]['path']}")
print(f"名称: {entity.data[0]['name']}")

# 获取所有事实（包括active和superseded）
print("\n所有事实（按时间排序）:")
facts = supabase.table("mem_l3_atomic_facts") \
    .select("id, content, status, superseded_by, created_at") \
    .eq("entity_id", entity_id) \
    .order("created_at", desc=False) \
    .execute()

if facts.data:
    for i, f in enumerate(facts.data, 1):
        status_mark = "[ACTIVE]" if f['status'] == 'active' else f['status']
        if f['status'] == 'superseded':
            status_mark = f"[SUPERSEDED by {f['superseded_by'][:8]}...]"
        print(f"\n{i}. {status_mark}")
        print(f"   ID: {f['id'][:8]}...")
        print(f"   内容: {f['content']}")
        print(f"   创建时间: {f['created_at']}")
else:
    print("  该实体没有任何事实！")

print("\n" + "=" * 70)
print("结论:")
print("=" * 70)
