"""
测试 Lifecycle Manager
"""
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from supabase import create_client
from lifecycle_manager import L0LifecycleManager


def setup_test_data():
    """创建测试数据"""
    print("[SETUP] 创建测试数据...")

    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    # 检查并添加归档字段（如果不存在）
    try:
        client.table("mem_l0_buffer").select("archived_at").limit(1).execute()
    except Exception:
        print("[WARN] 需要运行 migrate_add_archive_fields.sql 添加归档字段")
        return False

    now = datetime.utcnow()

    # 创建一些旧数据用于测试
    test_messages = [
        {
            "role": "user",
            "content": "这是一条8天前的测试消息",
            "processed": True,
            "created_at": (now - timedelta(days=8)).isoformat(),
        },
        {
            "role": "ai",
            "content": "这是一条91天前的测试消息",
            "processed": True,
            "created_at": (now - timedelta(days=91)).isoformat(),
        },
        {
            "role": "user",
            "content": "这是一条新的消息",
            "processed": True,
            "created_at": now.isoformat(),
        },
    ]

    for msg in test_messages:
        client.table("mem_l0_buffer").insert(msg).execute()

    print(f"[OK] 创建了 {len(test_messages)} 条测试数据")
    return True


def test_lifecycle():
    """测试生命周期管理"""
    print("\n" + "=" * 60)
    print("测试 Lifecycle Manager")
    print("=" * 60)

    manager = L0LifecycleManager()

    # 1. 查看统计
    print("\n[TEST 1] 查看当前统计...")
    stats = manager.get_stats()
    print(f"  活跃: {stats.get('active', 0)}")
    print(f"  温归档: {stats.get('warm', 0)}")

    # 2. 测试 Warm Archive
    print("\n[TEST 2] 执行 Warm Archive...")
    result = manager.warm_archive()
    print(f"  归档记录数: {result.get('archived', 0)}")

    # 3. 再次查看统计
    print("\n[TEST 3] 再次查看统计...")
    stats = manager.get_stats()
    print(f"  活跃: {stats.get('active', 0)}")
    print(f"  温归档: {stats.get('warm', 0)}")

    # 4. 测试 Cold Archive（如果温归档数据足够老）
    print("\n[TEST 4] 执行 Cold Archive...")
    result = manager.cold_archive()
    print(f"  导出记录数: {result.get('exported', 0)}")
    print(f"  删除记录数: {result.get('deleted', 0)}")
    if result.get('storage_path'):
        print(f"  存储路径: {result.get('storage_path')}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


def cleanup_test_data():
    """清理测试数据"""
    print("\n[CLEANUP] 清理测试数据...")

    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    # 删除包含"测试消息"的记录
    result = client.table("mem_l0_buffer") \
        .delete() \
        .ilike("content", "%测试消息%") \
        .execute()

    print(f"[OK] 清理完成")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试 Lifecycle Manager")
    parser.add_argument("--setup", action="store_true", help="创建测试数据")
    parser.add_argument("--cleanup", action="store_true", help="清理测试数据")
    parser.add_argument("--test", action="store_true", help="运行测试")

    args = parser.parse_args()

    if args.setup:
        setup_test_data()
    elif args.cleanup:
        cleanup_test_data()
    elif args.test:
        test_lifecycle()
    else:
        # 默认运行完整流程
        if setup_test_data():
            test_lifecycle()
            cleanup_test_data()
