"""
重置数据并用 Gemini-2.5-Flash 测试完整流程
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

print("重置数据库...")

# 删除事实
client.table("mem_l3_atomic_facts").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
print("- 已删除 atomic_facts")

# 删除实体
client.table("mem_l3_entities").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
print("- 已删除 entities")

# 重置 L0
client.table("mem_l0_buffer").update({"processed": False}).neq("id", "00000000-0000-0000-0000-000000000000").execute()
print("- 已重置 L0 buffer")

# 检查
l0 = client.table("mem_l0_buffer").select("count", count="exact").eq("processed", False).execute()
print(f"\n未处理消息: {l0.count}")

print("\n现在可以运行: python batch_extractor.py --once")
