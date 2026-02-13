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


def main():
    """主调度循环"""
    log("=" * 60)
    log("MemOS Zeabur Scheduler Started")
    log("=" * 60)
    log("Schedule:")
    log("  - Extractor: Every 10 minutes")
    log("  - Compiler: Every 30 minutes")
    log("  - Lifecycle: Every day at 02:00")
    log("=" * 60)

    # 配置（秒）
    EXTRACTOR_INTERVAL = 10 * 60  # 10分钟
    COMPILER_INTERVAL = 30 * 60   # 30分钟
    LIFECYCLE_INTERVAL = 24 * 60 * 60  # 24小时（但会检查是否是2点）

    # 首次运行
    log("Running initial tasks...")
    run_extractor()
    time.sleep(2)
    run_compiler()

    # 记录上次运行时间
    last_extractor = time.time()
    last_compiler = time.time()
    last_lifecycle_date = datetime.now().strftime('%Y-%m-%d')

    log("Entering main loop...")

    while True:
        now = time.time()
        current_datetime = datetime.now()
        current_date = current_datetime.strftime('%Y-%m-%d')

        # 检查提取器
        if now - last_extractor >= EXTRACTOR_INTERVAL:
            run_extractor()
            last_extractor = now

        # 检查编译器
        if now - last_compiler >= COMPILER_INTERVAL:
            run_compiler()
            last_compiler = now

        # 检查生命周期（每天2点运行一次）
        if current_date != last_lifecycle_date and current_datetime.hour == 2:
            run_lifecycle()
            last_lifecycle_date = current_date

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
