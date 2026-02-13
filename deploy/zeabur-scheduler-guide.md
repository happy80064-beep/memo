# Zeabur 定时调度配置指南

## 方案选择

Zeabur 支持两种定时任务方式：

### 方案一：Cronjob 服务（推荐）

Zeabur 原生支持定时任务，最简单。

### 方案二：Ofelia 调度器（自托管）

在容器内运行调度器，更灵活但复杂。

---

## 方案一：Cronjob 服务（推荐）

### 1. 上传代码到 GitHub

```bash
cd D:\memo
git add .
git commit -m "Add lifecycle manager and scheduler config"
git push origin main
```

### 2. 在 Zeabur 创建项目

1. 登录 [zeabur.com](https://zeabur.com)
2. 点击 **"Create Project"**
3. 选择 **"Deploy from GitHub"**
4. 选择你的 `memos` 仓库

### 3. 配置定时任务

在 Zeabur 控制台：

#### 创建提取器 Cronjob

1. 点击 **"Add Service"** → **"Cronjob"**
2. 配置：
   - **Name**: `extractor`
   - **Command**: `python batch_extractor.py --once`
   - **Schedule**: `*/10 * * * *` (每10分钟)
3. 环境变量：
   - `SYSTEM_BASE_URL`: `https://generativelanguage.googleapis.com/v1beta/openai/`
   - `SYSTEM_API_KEY`: 你的 Gemini API Key
   - `SYSTEM_MODEL`: `gemini-2.5-flash`
   - `SUPABASE_URL`: 你的 Supabase URL
   - `SUPABASE_SERVICE_ROLE_KEY`: 你的 Supabase Key

#### 创建编译器 Cronjob

1. 点击 **"Add Service"** → **"Cronjob"**
2. 配置：
   - **Name**: `compiler`
   - **Command**: `python compiler.py --once`
   - **Schedule**: `*/30 * * * *` (每30分钟)
3. 同样的环境变量

#### 创建生命周期管理 Cronjob

1. 点击 **"Add Service"** → **"Cronjob"**
2. 配置：
   - **Name**: `lifecycle`
   - **Command**: `python lifecycle_manager.py`
   - **Schedule**: `0 2 * * *` (每天凌晨2点)
3. 同样的环境变量

### 4. Cron 表达式说明

| 表达式 | 含义 | 说明 |
|--------|------|------|
| `*/10 * * * *` | 每10分钟 | 提取器 |
| `*/30 * * * *` | 每30分钟 | 编译器 |
| `0 2 * * *` | 每天2:00 | 生命周期 |
| `0 */6 * * *` | 每6小时 | 高频编译 |
| `0 0 * * 0` | 每周日0点 | 低频归档 |

**Cron 格式**: `分 时 日 月 周`

---

## 方案二：Ofelia 调度器（自托管）

如果你希望所有调度在一个容器内管理：

### 使用 docker-compose.scheduler.yml

```bash
# 本地测试
docker-compose -f docker-compose.scheduler.yml up -d

# 查看日志
docker-compose -f docker-compose.scheduler.yml logs -f ofelia
```

### 部署到 Zeabur

Zeabur 支持 Docker Compose，但 Cronjob 服务更推荐。

---

## 监控和日志

### 查看任务执行记录

在 Zeabur 控制台：
1. 进入 Cronjob 服务
2. 点击 **"Executions"** 标签
3. 查看每次运行的状态和时间

### 查看日志

```bash
# 提取器日志
zeabur service logs extractor

# 编译器日志
zeabur service logs compiler

# 生命周期日志
zeabur service logs lifecycle
```

---

## 费用预估

| 服务 | 运行频率 | 每次运行时间 | 月度费用 |
|------|----------|--------------|----------|
| 提取器 | 每10分钟 | ~30秒 | ~$0.5 |
| 编译器 | 每30分钟 | ~1分钟 | ~$0.3 |
| 生命周期 | 每天1次 | ~2分钟 | ~$0.1 |

**总计**: ~$1/月 (基于 Developer Plan $5/月 足够)

---

## 故障排查

### 任务没有按时运行

1. 检查 Cron 表达式是否正确
2. 查看 **Executions** 是否有错误
3. 检查环境变量是否设置完整

### 生命周期管理报错

1. 确认数据库字段已添加：
   ```sql
   ALTER TABLE mem_l0_buffer ADD COLUMN archived_at TIMESTAMPTZ;
   ALTER TABLE mem_l0_buffer ADD COLUMN archive_tier TEXT;
   ```

2. 确认 Storage Bucket 存在：
   - 在 Supabase 创建 `logs_archive` bucket

### 查看详细日志

在 Zeabur 控制台：
1. 进入服务详情
2. 点击 **Logs** 标签
3. 选择时间范围查看

---

## 快速检查清单

部署前确认：

- [ ] 代码已推送到 GitHub
- [ ] Supabase 数据库已添加归档字段
- [ ] Supabase Storage 创建了 `logs_archive` bucket
- [ ] 所有 API Key 已配置到 Zeabur 环境变量
- [ ] Cron 表达式格式正确
- [ ] 测试过一次手动运行

---

## 替代方案

如果 Zeabur 的 Cronjob 不满足需求：

1. **GitHub Actions**: 免费定时任务（公共仓库）
2. **AWS Lambda**: 云函数定时触发
3. **自托管 Linux**: Systemd timer

推荐还是 **Zeabur Cronjob**，最简单且成本可控。
