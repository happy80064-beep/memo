# MemOS Windows 服务安装脚本 (管理员权限运行)

# 检查管理员权限
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator"))
{
    Write-Error "请使用管理员权限运行 PowerShell!"
    exit 1
}

Write-Host "=== MemOS Windows 服务安装 ===" -ForegroundColor Green

# 创建计划任务 - 提取器 (每10分钟)
$Action = New-ScheduledTaskAction -Execute "python.exe" -Argument "D:\memo\batch_extractor.py --once" -WorkingDirectory "D:\memo"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 9999)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType ServiceAccount -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "MemOS-Extractor" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force
Write-Host "[OK] 提取器任务已创建 (每10分钟)" -ForegroundColor Green

# 创建计划任务 - 编译器 (每30分钟)
$Action2 = New-ScheduledTaskAction -Execute "python.exe" -Argument "D:\memo\compiler.py --once" -WorkingDirectory "D:\memo"
$Trigger2 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 9999)

Register-ScheduledTask -TaskName "MemOS-Compiler" -Action $Action2 -Trigger $Trigger2 -Principal $Principal -Settings $Settings -Force
Write-Host "[OK] 编译器任务已创建 (每30分钟)" -ForegroundColor Green

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Green
Write-Host "查看任务: 任务计划程序 (taskschd.msc)" -ForegroundColor Yellow
Write-Host "启动任务: Start-ScheduledTask -TaskName MemOS-Extractor" -ForegroundColor Yellow
Write-Host "停止任务: Stop-ScheduledTask -TaskName MemOS-Extractor" -ForegroundColor Yellow
