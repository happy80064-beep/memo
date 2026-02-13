"""
模拟 Ofelia 定时调度 - 本地测试版
每10分钟运行提取器，每30分钟运行编译器
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def run_extractor():
    """运行提取器（单次模式）"""
    log("[START] 提取器")
    try:
        result = subprocess.run(
            [sys.executable, "batch_extractor.py", "--once"],
            capture_output=True,
            text=True,
            timeout=120,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            log("[OK] 提取器完成")
            return True
        else:
            log(f"[FAIL] 提取器: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"[ERR] 提取器: {e}")
        return False


def run_compiler():
    """运行编译器（单次模式）"""
    log("[START] 编译器")
    try:
        result = subprocess.run(
            [sys.executable, "compiler.py", "--once"],
            capture_output=True,
            text=True,
            timeout=180,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            log("[OK] 编译器完成")
            return True
        else:
            log(f"[FAIL] 编译器: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"[ERR] 编译器: {e}")
        return False


def main():
    """主调度循环"""
    log("=" * 50)
    log("MemOS 定时调度器启动")
    log("=" * 50)
    log(f"提取器间隔: 10分钟")
    log(f"编译器间隔: 30分钟")
    log(f"按 Ctrl+C 停止")
    log("=" * 50)

    last_extractor = 0
    last_compiler = 0
    extractor_interval = 10 * 60  # 10分钟
    compiler_interval = 30 * 60   # 30分钟

    # 首次运行
    log("首次运行提取器和编译器...")
    run_extractor()
    time.sleep(2)
    run_compiler()

    last_extractor = time.time()
    last_compiler = time.time()

    log("\n进入定时调度循环...")

    try:
        while True:
            now = time.time()

            # 检查是否需要运行提取器
            if now - last_extractor >= extractor_interval:
                run_extractor()
                last_extractor = now

            # 检查是否需要运行编译器
            if now - last_compiler >= compiler_interval:
                run_compiler()
                last_compiler = now

            # 显示倒计时
            next_extractor = extractor_interval - (now - last_extractor)
            next_compiler = compiler_interval - (now - last_compiler)

            log(f"下次提取: {int(next_extractor/60)}分{int(next_extractor%60)}秒 | "
                f"下次编译: {int(next_compiler/60)}分{int(next_compiler%60)}秒")

            time.sleep(60)  # 每分钟检查一次

    except KeyboardInterrupt:
        log("\n调度器已停止")


if __name__ == "__main__":
    main()
