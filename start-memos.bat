@echo off
chcp 65001 >nul
echo ========================================
echo MemOS v2.0 - Windows 本地启动
echo ========================================
echo.
echo 启动调度器 (每10分钟提取/30分钟编译)
echo 按 Ctrl+C 停止
echo.

cd /d D:\memo
python test_scheduler.py

pause
