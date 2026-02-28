# -*- coding: utf-8 -*-
"""
手动测试实体去重任务
模拟今天的去重流程，验证功能是否正常
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 直接调用去重函数
from entity_dedup_scheduler import daily_incremental_dedup

if __name__ == "__main__":
    print("=" * 60)
    print("手动执行实体去重任务")
    print("=" * 60)
    print()

    # 执行去重
    daily_incremental_dedup()

    print()
    print("=" * 60)
    print("执行完成，请检查：")
    print("1. 上方输出是否正常")
    print("2. 飞书是否收到报告")
    print("=" * 60)
