"""
测试 Zeabur 部署的 MemOS
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def test_connection():
    """测试 Supabase 连接"""
    print("=" * 60)
    print("测试 MemOS Zeabur 部署")
    print("=" * 60)

    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    # 1. 统计 L0 Buffer
    print("\n[1] L0 Buffer 统计:")
    result = client.table("mem_l0_buffer").select("count", count="exact").execute()
    total_l0 = result.count
    print(f"  总消息数: {total_l0}")

    result = client.table("mem_l0_buffer").select("count", count="exact").eq("processed", True).execute()
    processed_l0 = result.count
    print(f"  已处理: {processed_l0}")
    print(f"  未处理: {total_l0 - processed_l0}")

    # 2. 统计 L3 实体
    print("\n[2] L3 Entities 统计:")
    result = client.table("mem_l3_entities").select("count", count="exact").execute()
    print(f"  实体数量: {result.count}")

    if result.count > 0:
        entities = client.table("mem_l3_entities").select("path, name, entity_type").execute()
        print("  实体列表:")
        for e in entities.data:
            print(f"    - {e['path']} ({e['entity_type']})")

    # 3. 统计原子事实
    print("\n[3] Atomic Facts 统计:")
    result = client.table("mem_l3_atomic_facts").select("count", count="exact").execute()
    print(f"  事实总数: {result.count}")

    result = client.table("mem_l3_atomic_facts").select("count", count="exact").eq("status", "active").execute()
    print(f"  活跃事实: {result.count}")

    # 4. 检查编译结果
    print("\n[4] 编译状态:")
    entities = client.table("mem_l3_entities").select("path, name, description_md, last_compiled_at").execute()
    compiled = 0
    for e in entities.data:
        if e.get("description_md") and "待编译" not in e.get("description_md", ""):
            compiled += 1
            print(f"  [OK] {e['path']} - compiled")

    if compiled == 0 and len(entities.data) > 0:
        print(f"  ⏳ {len(entities.data)} 个实体待编译")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

    if total_l0 > 0 and processed_l0 > 0:
        print("[OK] Extractor working")
    else:
        print("[WAIT] Extractor waiting for data")

    if compiled > 0:
        print("[OK] Compiler working")
    elif len(entities.data) > 0:
        print("[WAIT] Compiler pending")
    else:
        print("[WAIT] No entities to compile")

def insert_test_data():
    """插入测试数据"""
    print("\n插入测试数据...")

    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    test_messages = [
        {
            "role": "user",
            "content": "这是测试消息1: 我计划学习Python编程",
            "processed": False,
        },
        {
            "role": "ai",
            "content": "Python是很好的选择，你想学习什么方向？",
            "processed": False,
        },
        {
            "role": "user",
            "content": "我想做AI相关的项目，比如智能助手",
            "processed": False,
        },
    ]

    for msg in test_messages:
        client.table("mem_l0_buffer").insert(msg).execute()

    print(f"✅ 插入了 {len(test_messages)} 条测试消息")
    print("⏳ 等待10分钟后，提取器会自动处理")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--insert":
        insert_test_data()
    else:
        test_connection()
