"""
检查生产环境li-guodong实体当前状态
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
print("生产环境状态检查 - li-guodong 实体")
print("=" * 70)

# 获取li-guodong实体
entity = supabase.table("mem_l3_entities") \
    .select("id, path, name, description_md") \
    .eq("path", "/people/li-guodong") \
    .execute()

if not entity.data:
    print("\n错误: 未找到li-guodong实体!")
    exit()

entity_id = entity.data[0]['id']
print(f"\n实体ID: {entity_id}")
print(f"路径: {entity.data[0]['path']}")
print(f"名称: {entity.data[0]['name']}")
print(f"描述摘要: {entity.data[0]['description_md'][:100] if entity.data[0]['description_md'] else 'None'}...")

# 获取所有事实（包括active和superseded）
print("\n" + "=" * 70)
print("所有事实（包括active和superseded）:")
print("=" * 70)

facts = supabase.table("mem_l3_atomic_facts") \
    .select("id, content, status, superseded_by, created_at") \
    .eq("entity_id", entity_id) \
    .order("created_at", desc=False) \
    .execute()

if not facts.data:
    print("\n该实体没有任何事实！")
else:
    print(f"\n共 {len(facts.data)} 条事实:")

    active_birthday_facts = []
    superseded_birthday_facts = []

    for i, f in enumerate(facts.data, 1):
        is_birthday = '生日' in f['content'] or '3月20' in f['content']
        is_active = f['status'] == 'active'

        if is_birthday:
            if is_active:
                active_birthday_facts.append(f)
            else:
                superseded_birthday_facts.append(f)

        status_mark = "[ACTIVE]" if is_active else f"[{f['status']}]"
        birthday_mark = " [生日]" if is_birthday else ""

        print(f"\n{i}. {status_mark}{birthday_mark}")
        print(f"   ID: {f['id']}")
        print(f"   内容: {f['content']}")
        print(f"   创建时间: {f['created_at']}")
        if f['superseded_by']:
            print(f"   被替代: {f['superseded_by']}")

    print("\n" + "=" * 70)
    print("统计:")
    print("=" * 70)
    print(f"Active 事实数: {len([f for f in facts.data if f['status'] == 'active'])}")
    print(f"Superseded 事实数: {len([f for f in facts.data if f['status'] == 'superseded'])}")
    print(f"Active 生日事实: {len(active_birthday_facts)}")
    print(f"Superseded 生日事实: {len(superseded_birthday_facts)}")

    if active_birthday_facts:
        print("\n✓ 有active的生日事实:")
        for f in active_birthday_facts:
            print(f"   - {f['content']}")
    else:
        print("\n✗ 没有active的生日事实!")

    if superseded_birthday_facts:
        print(f"\n⚠ 有 {len(superseded_birthday_facts)} 条被标记为superseded的生日事实")

# 检查全局是否有其他实体有李国栋的生日
print("\n" + "=" * 70)
print("全局检查：是否有其他实体有李国栋/父亲的生日事实")
print("=" * 70)

all_birthday_facts = supabase.table("mem_l3_atomic_facts") \
    .select("content, status, entity_id, mem_l3_entities(path, name)") \
    .ilike("content", "%生日%") \
    .ilike("content", "%3月20%") \
    .execute()

if all_birthday_facts.data:
    print(f"\n找到 {len(all_birthday_facts.data)} 条生日事实:")
    for f in all_birthday_facts.data:
        entity_name = f.get("mem_l3_entities", {}).get("name", "Unknown")
        entity_path = f.get("mem_l3_entities", {}).get("path", "Unknown")
        print(f"   [{f['status']}] {entity_name} ({entity_path})")
        print(f"      内容: {f['content']}")
        print(f"      Entity ID: {f['entity_id']}")
else:
    print("\n没有找到任何'3月20日'生日事实!")

print("\n" + "=" * 70)
print("结论")
print("=" * 70)
