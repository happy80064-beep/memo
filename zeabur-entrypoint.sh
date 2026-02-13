#!/bin/bash
# Zeabur 容器入口脚本
# 在单个容器内调度提取器和编译器

set -e

echo "=========================================="
echo "MemOS v2.0 - Zeabur 部署"
echo "=========================================="
echo ""

# 使用环境变量或默认值
EXTRACTOR_INTERVAL=${SCHEDULE_EXTRACTOR_MINUTES:-10}
COMPILER_INTERVAL=${SCHEDULE_COMPILER_MINUTES:-30}

echo "调度配置:"
echo "  提取器: 每 ${EXTRACTOR_INTERVAL} 分钟"
echo "  编译器: 每 ${COMPILER_INTERVAL} 分钟"
echo ""

# 首次运行
echo "[INIT] 首次运行提取器和编译器..."
python batch_extractor.py --once || echo "提取器完成或无可处理数据"
sleep 2
python compiler.py --once || echo "编译器完成或无可处理数据"

echo ""
echo "[READY] 进入定时调度循环..."
echo "=========================================="

# 记录上次运行时间
LAST_EXTRACTOR=$(date +%s)
LAST_COMPILER=$(date +%s)

# 转换为秒
EXTRACTOR_SEC=$((EXTRACTOR_INTERVAL * 60))
COMPILER_SEC=$((COMPILER_INTERVAL * 60))

# 主循环
while true; do
    NOW=$(date +%s)

    # 检查是否需要运行提取器
    if [ $((NOW - LAST_EXTRACTOR)) -ge $EXTRACTOR_SEC ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 运行提取器..."
        python batch_extractor.py --once || echo "提取器完成"
        LAST_EXTRACTOR=$NOW
    fi

    # 检查是否需要运行编译器
    if [ $((NOW - LAST_COMPILER)) -ge $COMPILER_SEC ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 运行编译器..."
        python compiler.py --once || echo "编译器完成"
        LAST_COMPILER=$NOW
    fi

    # 显示下次运行时间
    NEXT_EXTRACTOR=$((LAST_EXTRACTOR + EXTRACTOR_SEC - NOW))
    NEXT_COMPILER=$((LAST_COMPILER + COMPILER_SEC - NOW))

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 下次提取: ${NEXT_EXTRACTOR}s | 下次编译: ${NEXT_COMPILER}s"

    # 每分钟检查一次
    sleep 60
done
