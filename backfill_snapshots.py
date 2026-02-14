"""
Backfill L1 Snapshots - 补充历史每日快照
可以生成指定日期的 L1 Timeline 数据
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from daily_snapshots import DailySnapshotGenerator


def backfill_date(target_date: str):
    """为指定日期生成快照"""
    print(f"\nGenerating snapshot for: {target_date}")

    generator = DailySnapshotGenerator()
    generator.run(target_date)


def backfill_range(start_date: str, end_date: str):
    """为日期范围生成快照"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        backfill_date(date_str)
        current += timedelta(days=1)


if __name__ == "__main__":
    # 默认补充昨天
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if len(sys.argv) == 1:
        # 无参数：补充昨天
        print("=" * 60)
        print("Backfill L1 Snapshots")
        print("=" * 60)
        print(f"\nNo date specified, using yesterday: {yesterday}")
        backfill_date(yesterday)

    elif len(sys.argv) == 2:
        # 单个日期: python backfill_snapshots.py 2024-02-13
        date = sys.argv[1]
        print("=" * 60)
        print("Backfill L1 Snapshots")
        print("=" * 60)
        backfill_date(date)

    elif len(sys.argv) == 3:
        # 日期范围: python backfill_snapshots.py 2024-02-10 2024-02-13
        start, end = sys.argv[1], sys.argv[2]
        print("=" * 60)
        print("Backfill L1 Snapshots (Range)")
        print("=" * 60)
        backfill_range(start, end)

    else:
        print("Usage:")
        print("  python backfill_snapshots.py              # Yesterday")
        print("  python backfill_snapshots.py 2024-02-13   # Specific date")
        print("  python backfill_snapshots.py 2024-02-10 2024-02-13  # Date range")
