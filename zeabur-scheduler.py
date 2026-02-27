"""
Zeabur 内置调度器
在一个容器中运行所有定时任务
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def log(msg):
    """打印带时间戳的日志"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def check_env():
    """检查关键环境变量"""
    log("Checking environment variables...")
    required = ['SYSTEM_API_KEY', 'SYSTEM_BASE_URL', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY']
    for key in required:
        value = os.getenv(key, '')
        if value:
            # 只显示前10个字符
            log(f"  ✓ {key}: {value[:10]}...")
        else:
            log(f"  ✗ {key}: NOT SET!")
    return all(os.getenv(k) for k in required)


def run_extractor():
    """运行提取器"""
    log("[EXTRACTOR] Starting batch_extractor...")
    try:
        result = subprocess.run(
            [sys.executable, "batch_extractor.py", "--once"],
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            log("[EXTRACTOR] Completed successfully")
            return True
        else:
            log(f"[EXTRACTOR] Error: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"[EXTRACTOR] Exception: {e}")
        return False


def run_compiler():
    """运行编译器"""
    log("[COMPILER] Starting compiler...")
    try:
        result = subprocess.run(
            [sys.executable, "compiler.py", "--once"],
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            log("[COMPILER] Completed successfully")
            return True
        else:
            log(f"[COMPILER] Error: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"[COMPILER] Exception: {e}")
        return False


def run_lifecycle():
    """运行生命周期管理"""
    log("[LIFECYCLE] Starting lifecycle_manager...")
    try:
        result = subprocess.run(
            [sys.executable, "lifecycle_manager.py"],
            capture_output=True,
            text=True,
            timeout=600,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            log("[LIFECYCLE] Completed successfully")
            return True
        else:
            log(f"[LIFECYCLE] Error: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"[LIFECYCLE] Exception: {e}")
        return False


def run_snapshot():
    """运行每日快照 (L1)"""
    log("[SNAPSHOT] Starting daily_snapshots...")
    try:
        result = subprocess.run(
            [sys.executable, "daily_snapshots.py"],
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            log("[SNAPSHOT] Completed successfully")
            return True
        else:
            log(f"[SNAPSHOT] Error: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"[SNAPSHOT] Exception: {e}")
        return False


def run_profile():
    """运行画像洞察 (L2)"""
    log("[PROFILE] Starting profile_insights...")
    try:
        result = subprocess.run(
            [sys.executable, "profile_insights.py", "7"],
            capture_output=True,
            text=True,
            timeout=600,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            log("[PROFILE] Completed successfully")
            return True
        else:
            log(f"[PROFILE] Error: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"[PROFILE] Exception: {e}")
        return False


def run_entity_dedup():
    """运行实体去重"""
    log("[DEDUP] Starting entity_dedup_scheduler...")
    try:
        result = subprocess.run(
            [sys.executable, "entity_dedup_scheduler.py"],
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            log("[DEDUP] Completed successfully")
            return True
        else:
            log(f"[DEDUP] Error: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"[DEDUP] Exception: {e}")
        return False


def main():
    """主调度循环"""
    log("=" * 60)
    log("MemOS Zeabur Scheduler Started")
    log("=" * 60)

    # 检查环境变量
    if not check_env():
        log("✗ CRITICAL: Missing required environment variables!")
        log("Please check your Zeabur environment variable settings.")
        sys.exit(1)
    log("Schedule:")
    log("  - Extractor: Every 10 minutes")
    log("  - Compiler: Every 30 minutes")
    log("  - L1 Snapshot: Every day at 01:00")
    log("  - L2 Profile: Every Sunday at 03:00")
    log("  - Lifecycle: Every day at 02:00")
    log("  - Entity Dedup: Every day at 02:30")
    log("=" * 60)

    # 配置（秒）
    EXTRACTOR_INTERVAL = 10 * 60  # 10分钟
    COMPILER_INTERVAL = 30 * 60   # 30分钟

    # 首次运行
    log("Running initial tasks...")
    run_extractor()
    time.sleep(2)
    run_compiler()

    # 记录上次运行时间
    last_extractor = time.time()
    last_compiler = time.time()
    last_lifecycle_date = datetime.now().strftime('%Y-%m-%d')
    last_snapshot_date = datetime.now().strftime('%Y-%m-%d')
    last_profile_week = datetime.now().isocalendar()[1]  # 当前周数
    last_dedup_date = datetime.now().strftime('%Y-%m-%d')

    log("Entering main loop...")

    while True:
        now = time.time()
        current_datetime = datetime.now()
        current_date = current_datetime.strftime('%Y-%m-%d')
        current_hour = current_datetime.hour
        current_week = current_datetime.isocalendar()[1]

        # 检查提取器
        if now - last_extractor >= EXTRACTOR_INTERVAL:
            run_extractor()
            last_extractor = now

        # 检查编译器
        if now - last_compiler >= COMPILER_INTERVAL:
            run_compiler()
            last_compiler = now

        # 检查 L1 每日快照（每天1点运行）
        if current_date != last_snapshot_date and current_hour == 1:
            run_snapshot()
            last_snapshot_date = current_date

        # 检查 L2 画像洞察（每周日3点运行）
        if current_week != last_profile_week and current_datetime.weekday() == 6 and current_hour == 3:
            run_profile()
            last_profile_week = current_week

        # 检查生命周期（每天2点运行）
        if current_date != last_lifecycle_date and current_hour == 2:
            run_lifecycle()
            last_lifecycle_date = current_date

        # 检查实体去重（每天2:30运行）
        if current_date != last_dedup_date and current_hour == 2 and current_datetime.minute >= 30:
            run_entity_dedup()
            last_dedup_date = current_date

        # 显示下次运行倒计时
        next_extractor = EXTRACTOR_INTERVAL - (now - last_extractor)
        next_compiler = COMPILER_INTERVAL - (now - last_compiler)

        log(f"Next extractor: {int(next_extractor/60)}m | Next compiler: {int(next_compiler/60)}m")

        # 每分钟检查一次
        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Scheduler stopped by user")
    except Exception as e:
        log(f"Fatal error: {e}")
        sys.exit(1)
