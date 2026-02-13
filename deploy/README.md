# MemOS v2.0 部署指南

## 方案一: Systemd (推荐用于 Linux 服务器)

### 安装

```bash
cd systemd
sudo bash install.sh
```

### 管理命令

```bash
# 启动服务
sudo systemctl start memos-extractor
sudo systemctl start memos-compiler

# 停止服务
sudo systemctl stop memos-extractor
sudo systemctl stop memos-compiler

# 查看状态
sudo systemctl status memos-extractor
sudo systemctl status memos-compiler

# 查看日志
sudo journalctl -u memos-extractor -f
sudo journalctl -u memos-compiler -f

# 重启服务
sudo systemctl restart memos-extractor
sudo systemctl restart memos-compiler
```

### 文件位置

- 服务文件: `/etc/systemd/system/memos-*.service`
- 应用目录: `/opt/memos/`
- 日志: `journalctl -u memos-*`

---

## 方案二: Docker Compose (推荐用于开发/测试)

### 启动

```bash
# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f extractor
docker-compose logs -f compiler

# 停止
docker-compose down
```

### 定时任务模式 (Ofelia) ⭐推荐

低频运行，省资源，适合轻量服务器。

```bash
# 使用 Ofelia 调度器
docker-compose -f docker-compose.scheduler.yml up -d
```

**默认调度频率:**
- 提取器: 每 10 分钟运行一次
- 编译器: 每 30 分钟运行一次

**修改频率:** 编辑 `docker-compose.scheduler.yml` 中的 `@every 10m` 值。

---

## 方案对比

| 特性 | Systemd | Docker |
|------|---------|--------|
| 适用场景 | 生产服务器 | 开发/测试/云原生 |
| 自动重启 | ✅ 是 | ✅ 是 |
| 日志管理 | journalctl | docker logs |
| 资源占用 | 低 | 中等 |
| 隔离性 | 进程级 | 容器级 |
| 定时调度 | 持续运行 | 支持 Ofelia 定时 |

---

## 环境变量配置

确保 `.env` 文件包含：

```env
# LLM 配置
SYSTEM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
SYSTEM_API_KEY=your_gemini_key
SYSTEM_MODEL=gemini-2.5-flash

USER_BASE_URL=https://api.moonshot.cn/v1
USER_API_KEY=your_moonshot_key
USER_MODEL=kimi-k2-5

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_key
```

---

## 监控与告警

### 健康检查

```bash
# 检查服务状态
curl -s https://your-health-check-endpoint

# 查看最近错误
sudo journalctl -u memos-extractor --since "1 hour ago" | grep ERROR
```

### 日志轮转

Systemd 日志自动轮转，Docker 日志配置已在 compose 中设置。
