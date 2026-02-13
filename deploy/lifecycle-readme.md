# L0 Buffer 生命周期管理

## 概述

自动管理 L0 Buffer 数据的生命周期，降低存储成本，提高查询性能。

## 归档策略

```
时间线:
Day 0-7:    [活跃数据] → 正常参与批处理
Day 7-90:   [温归档]   → 标记为 archived, 不参与向量检索
Day 90+:    [冷归档]   → 导出为 JSONL 压缩文件，物理删除
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `lifecycle_manager.py` | 主脚本 |
| `migrate_add_archive_fields.sql` | 数据库升级脚本 |
| `test_lifecycle.py` | 测试脚本 |

## 数据库升级

在 Supabase SQL Editor 中执行：

```sql
-- 添加归档字段
ALTER TABLE mem_l0_buffer
ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS archive_tier TEXT CHECK (archive_tier IN ('warm', 'cold'));

-- 添加索引
CREATE INDEX idx_l0_archive_tier ON mem_l0_buffer(archive_tier, archived_at) WHERE archive_tier IS NOT NULL;
CREATE INDEX idx_l0_warm_archive ON mem_l0_buffer(archived_at) WHERE archive_tier = 'warm';
```

## 手动运行

```bash
# 查看统计
python lifecycle_manager.py --stats

# 仅执行温归档 (7天+)
python lifecycle_manager.py --warm

# 仅执行冷归档 (90天+)
python lifecycle_manager.py --cold

# 完整运行
python lifecycle_manager.py

# 测试模式
python test_lifecycle.py --setup
python test_lifecycle.py --test
python test_lifecycle.py --cleanup
```

## 自动调度

### Systemd (Linux)

创建 `/etc/systemd/system/memos-lifecycle.service`:

```ini
[Unit]
Description=MemOS L0 Lifecycle Manager
[Service]
Type=oneshot
WorkingDirectory=/opt/memos
ExecStart=/opt/memos/venv/bin/python lifecycle_manager.py
```

创建 `/etc/systemd/system/memos-lifecycle.timer`:

```ini
[Unit]
Description=Run MemOS Lifecycle daily
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
```

启用：
```bash
sudo systemctl enable memos-lifecycle.timer
sudo systemctl start memos-lifecycle.timer
```

### Zeabur / Docker

添加到 `docker-compose.scheduler.yml`:

```yaml
  lifecycle:
    build: .
    container_name: memos-lifecycle
    command: python lifecycle_manager.py
    env_file: .env
    restart: "no"
    labels:
      ofelia.enabled: "true"
      ofelia.job-run.lifecycle.schedule: "@daily"  # 每天运行一次
```

### Windows 计划任务

```powershell
# 每天凌晨2点运行
$Action = New-ScheduledTaskAction -Execute "python.exe" -Argument "D:\memo\lifecycle_manager.py"
$Trigger = New-ScheduledTaskTrigger -Daily -At "02:00"
Register-ScheduledTask -TaskName "MemOS-Lifecycle" -Action $Action -Trigger $Trigger
```

## Storage 配置

脚本会自动创建 `logs_archive` Bucket。手动创建：

```sql
-- Supabase Storage
INSERT INTO storage.buckets (id, name, public)
VALUES ('logs_archive', 'logs_archive', false);
```

## 监控指标

运行后会输出：
- 活跃数据数量
- 温归档数据数量
- 冷归档文件数量和大小
- 本次处理记录数

## 数据恢复

从冷归档恢复数据：

```python
from supabase import create_client
import gzip
import json

client = create_client(url, key)

# 下载文件
data = client.storage.from_('logs_archive').download('l0_buffer/2024/01/l0_buffer_xxx.jsonl.gz')

# 解压并读取
import gzip
with gzip.open(BytesIO(data), 'rt') as f:
    for line in f:
        record = json.loads(line)
        print(record)
```
