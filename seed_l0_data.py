"""
插入测试数据到 L0 Buffer
"""

import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def seed_test_data():
    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    # 测试数据：项目讨论
    test_messages = [
        {
            "role": "user",
            "content": "我想开始一个新的AI记忆系统项目，代号叫 MemOS v2.0。目标是构建一个支持文件系统隐喻的记忆架构。",
            "processed": False,
        },
        {
            "role": "ai",
            "content": "好的，MemOS v2.0 听起来很有前景。我们可以采用分层架构：L0缓冲层、L1时间线、L2用户画像、L3实体层。",
            "processed": False,
        },
        {
            "role": "user",
            "content": "对，L3层要用文件系统隐喻，比如 /work/projects/memos 这样的路径。另外我习惯用Python写后端。",
            "meta_data": {"source_app": "claude-code", "session_id": "test-001"},
            "processed": False,
        },
        {
            "role": "ai",
            "content": "明白了。我会用Python实现，采用读写分离设计：atomic_facts作为写模型，description_md作为读模型。",
            "processed": False,
        },
    ]

    for msg in test_messages:
        result = client.table("mem_l0_buffer").insert(msg).execute()
        print(f"插入消息: {result.data[0]['id'][:8]}...")

    print(f"\n成功插入 {len(test_messages)} 条测试消息")

    # 检查当前数量
    count_result = client.table("mem_l0_buffer").select("count", count="exact").eq("processed", False).execute()
    print(f"未处理消息总数: {count_result.count}")


if __name__ == "__main__":
    seed_test_data()
