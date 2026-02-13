# Zeabur 部署指南

## 什么是 Zeabur？

Zeabur 是一个开发者友好的 PaaS 平台，可以一键部署各种应用。免费额度足够运行 MemOS。

官网：https://zeabur.com

---

## 部署步骤

### 1. 准备工作

确保你的项目包含这些文件：
- `Dockerfile.zeabur` - Zeabur 专用 Dockerfile
- `zeabur.yaml` - Zeabur 配置文件
- `zeabur-entrypoint.sh` - 容器启动脚本
- `*.py` - Python 源代码
- `.env.zeabur` - 环境变量模板

### 2. 上传到 GitHub

```bash
# 在你的项目目录
cd D:\memo

# 初始化 git
git init
git add .
git commit -m "Initial MemOS deployment"

# 创建 GitHub 仓库并推送
git remote add origin https://github.com/yourname/memos.git
git branch -M main
git push -u origin main
```

### 3. 在 Zeabur 部署

1. 登录 [Zeabur](https://zeabur.com)
2. 点击 **"Create Project"**
3. 选择 **"Deploy from GitHub"**
4. 选择你的 `memos` 仓库
5. Zeabur 会自动识别 `zeabur.yaml` 并部署

### 4. 配置环境变量

部署后，在 Zeabur 控制台设置环境变量：

必需变量：
- `SYSTEM_API_KEY` - Gemini API Key
- `USER_API_KEY` - Moonshot API Key
- `SUPABASE_URL` - Supabase 项目 URL
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase Service Role Key

可选变量（已有默认值）：
- `SCHEDULE_EXTRACTOR_MINUTES` - 提取间隔（默认10）
- `SCHEDULE_COMPILER_MINUTES` - 编译间隔（默认30）

### 5. 查看日志

在 Zeabur 控制台：
- 点击你的服务
- 进入 **Logs** 标签查看运行日志

---

## 监控与调试

### 查看服务状态

在 Zeabur 控制台可以看到：
- 容器运行状态
- CPU/内存使用率
- 实时日志

### 调整资源

如果内存不足（默认 512MB）：
1. 进入服务设置
2. 升级 Plan（Developer Plan 约 $5/月）

---

## 优势

| 特性 | Zeabur |
|------|--------|
| 部署难度 | ⭐ 一键部署 |
| 24小时运行 | ✅ 自动保持 |
| 自动重启 | ✅ 崩溃后自动恢复 |
| 免费额度 | ✅ 足够小项目 |
| 自定义域名 | ✅ 支持 |

---

## 注意事项

1. **免费额度限制**：如果处理量很大，可能需要升级
2. **冷启动**：免费版可能有几秒冷启动时间
3. **日志保留**：免费版日志保留时间有限

---

## 快速启动检查清单

- [ ] 项目已上传到 GitHub
- [ ] 包含 `Dockerfile.zeabur` 和 `zeabur.yaml`
- [ ] 在 Zeabur 创建了项目
- [ ] 已设置所有环境变量
- [ ] 查看日志确认运行正常
