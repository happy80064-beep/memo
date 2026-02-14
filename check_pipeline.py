"""
检查 MemOS 管道执行状态
验证提取器、编译器是否正常运行
"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def check_pipeline():
    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    print("=" * 70)
    print("MemOS 管道执行状态检查")
    print("=" * 70)

    # 1. 检查 L0 Buffer 最近处理时间
    print("\n[1] L0 Buffer 处理状态:")
    result = client.table("mem_l0_buffer").select("*").order("created_at", desc=True).limit(5).execute()

    for i, row in enumerate(result.data, 1):
        created = row.get('created_at', 'N/A')
        processed = "[OK]" if row.get('processed') else "[NO]"
        print(f"  {i}. {created[:19]} | Processed: {processed} | {row['content'][:50]}...")

    # 2. 统计今日处理量
    today = datetime.now().strftime('%Y-%m-%d')
    today_start = f"{today}T00:00:00"
    today_end = f"{today}T23:59:59"

    today_count = client.table("mem_l0_buffer").select("count", count="exact") \
        .gte("created_at", today_start).lte("created_at", today_end).execute().count

    today_processed = client.table("mem_l0_buffer").select("count", count="exact") \
        .eq("processed", True).gte("created_at", today_start).lte("created_at", today_end).execute().count

    print(f"\n[2] 今日 ({today}) 统计:")
    print(f"  新增消息: {today_count}")
    print(f"  已处理: {today_processed}")

    # 3. 检查 L3 实体最近创建时间
    print("\n[3] L3 Entities 最近创建:")
    result = client.table("mem_l3_entities").select("path, name, created_at, last_compiled_at") \
        .order("created_at", desc=True).limit(5).execute()

    for i, row in enumerate(result.data, 1):
        created = row.get('created_at', 'N/A')[:19]
        compiled = row.get('last_compiled_at', 'N/A')[:19] if row.get('last_compiled_at') else "未编译"
        print(f"  {i}. {row['path']}")
        print(f"     Created: {created} | Compiled: {compiled}")

    # 4. 检查原子事实最近创建时间
    print("\n[4] Atomic Facts 最近创建:")
    result = client.table("mem_l3_atomic_facts").select("*, mem_l3_entities(path)") \
        .order("created_at", desc=True).limit(5).execute()

    for i, row in enumerate(result.data, 1):
        created = row.get('created_at', 'N/A')[:19]
        entity_path = row.get('mem_l3_entities', {}).get('path', 'N/A')
        print(f"  {i}. {created} | {entity_path}")
        print(f"     {row['content'][:60]}...")

    # 5. 总体统计
    print("\n[5] 总体统计:")
    l0_total = client.table("mem_l0_buffer").select("count", count="exact").execute().count
    l0_processed = client.table("mem_l0_buffer").select("count", count="exact").eq("processed", True).execute().count
    l3_total = client.table("mem_l3_entities").select("count", count="exact").execute().count
    facts_total = client.table("mem_l3_atomic_facts").select("count", count="exact").execute().count

    print(f"  L0 Buffer: {l0_processed}/{l0_total} 已处理 ({l0_processed/l0_total*100:.1f}%)")
    print(f"  L3 Entities: {l3_total} 个实体")
    print(f"  Atomic Facts: {facts_total} 条事实")

    # 6. 管道健康度评估
    print("\n[6] 管道健康度:")
    if l0_processed == l0_total and l0_total > 0:
        print("  ✓ 提取器 (Extractor): 工作正常 - 所有消息已处理")
    else:
        print(f"  ⚠ 提取器 (Extractor): 有 {l0_total - l0_processed} 条消息待处理")

    if l3_total > 0:
        compiled = client.table("mem_l3_entities").select("count", count="exact") \
            .neq("last_compiled_at", "null").execute().count
        print(f"  ✓ 编译器 (Compiler): 工作正常 - {compiled}/{l3_total} 个实体已编译")
    else:
        print("  ⚠ 编译器 (Compiler): 暂无实体需要编译")

    print("\n" + "=" * 70)
    print("检查完成")
    print("=" * 70)

if __name__ == "__main__":
    check_pipeline()
