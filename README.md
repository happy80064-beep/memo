# Memo AI 记忆系统

> 一个具有长期记忆能力的 AI 对话系统，能够记住用户的生活细节、人物关系和重要事件，并支持联网搜索获取最新信息。

---

## 项目简介

Memo 是一个基于 LangGraph 构建的智能对话系统，核心特性包括：

- **长期记忆**：自动提取和存储对话中的实体、事实和事件
- **人物关系管理**：智能识别人物关系，避免实体碎片化
- **联网搜索**：当记忆不足时，自动搜索互联网获取最新信息
- **多平台部署**：支持 Zeabur 云平台部署，可配置 Web 服务或定时任务模式

### 系统架构

```
用户消息
    ↓
[Intent Router] 意图识别 (搜索/聊天/记忆)
    ↓
├─ 搜索意图 → [Web Search] → LLM 生成
├─ 聊天意图 → [Memory Retrieval] → [LLM Generate]
└─ 记忆更新 → [Entity Extraction] → [L3 Storage]
    ↓
响应用户
```

---

## 更新历程

### 2026-02-26 v2.2 - 搜索功能正式上线
- ✅ 实现 Kimi `$web_search` 原生搜索功能
- ✅ 支持禁用 thinking 模式进行搜索（temperature=0.6）
- ✅ 添加外部搜索 API 作为后备（DuckDuckGo/SerpAPI）
- ✅ 搜索结果缓存 30 分钟

### 2026-02-26 v2.1 - 实体合并完成
- ✅ 合并 46 个人物实体，从 62 个减少到 16 个
- ✅ 优化实体级搜索逻辑
- ✅ 添加自动实体维护脚本

### 2026-02-20 v2.0 - 关系实体处理
- ✅ 实时关系检测与追问
- ✅ 避免创建碎片化的关系实体（如"我爸"、"用户父亲"）
- ✅ 支持追问用户确认具体姓名

### 2026-02-10 v1.0 - 基础架构
- ✅ LangGraph 工作流架构
- ✅ L0/L1/L2/L3 四级记忆存储
- ✅ Supabase 数据库集成
- ✅ Feishu/Lark 机器人支持

---

## 快速开始

### 1. 环境配置

创建 `.env` 文件：

```bash
# === System Model (用于路由、提取、感知) ===
SYSTEM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
SYSTEM_API_KEY=your_gemini_api_key
SYSTEM_MODEL=gemini-2.5-flash
SYSTEM_TEMPERATURE=0.3

# === User Model (用于生成，支持搜索) ===
USER_BASE_URL=https://api.moonshot.cn/v1
USER_API_KEY=your_moonshot_api_key
USER_MODEL=kimi-k2.5
USER_TEMPERATURE=1.0

# === Supabase 数据库 ===
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key

# === Feishu/Lark 机器人 (可选) ===
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_ENCRYPT_KEY=xxx
FEISHU_VERIFICATION_TOKEN=xxx

# === 外部搜索 API (可选，用于 Gemini 等模型) ===
# SERPAPI_KEY=xxx  # 可选，使用 SerpAPI
# GOOGLE_API_KEY=xxx  # 可选，使用 Google Custom Search
# GOOGLE_CX=xxx
```

### 2. 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行 Web 服务
uvicorn web_app_multimodal:app --host 0.0.0.0 --port 8000

# 或运行定时任务调度器
python zeabur-scheduler.py
```

### 3. Zeabur 部署

```bash
# 推送代码后，在 Zeabur 控制台设置：
# - Web 服务：Start Command = uvicorn web_app_multimodal:app --host 0.0.0.0 --port 8000
# - 定时任务：Start Command = python zeabur-scheduler.py
```

---

## 使用说明

### 基本对话

直接发送消息，AI 会：
1. 从记忆中检索相关信息
2. 生成个性化回复
3. 自动提取新的事实保存到记忆

### 触发搜索

当 AI 不了解某个话题时，可以通过以下方式触发联网搜索：

**方式 1：明确搜索指令**
```
用户：搜索一下 OpenClaw
用户：查一下最新新闻
用户：去了解了解
```

**方式 2：确认搜索建议**
```
AI：这件事我之前好像没听你聊过...我可以马上去搜索深入了解一下。
用户：好的，搜索一下
用户：去吧
```

**方式 3：同一话题延续**
```
用户：它有什么应用场景？（同一话题）
AI：[自动启用搜索] 根据搜索，OpenClaw 的应用场景包括...
```

### 记忆查询示例

```
用户：我爸生日是哪天？
AI：您父亲的生日是3月20日。

用户：佳佳泽生日呢？
AI：李佳泽的生日是3月26日。

用户：杨总收到方案了吗？
AI：杨勇（您的领导）已经收到方案了。
```

---

## 项目结构

```
memo/
├── web_app_multimodal.py    # FastAPI Web 服务主入口
├── zeabur-scheduler.py      # 定时任务调度器
├── graph.py                 # LangGraph 工作流核心
├── llm_factory.py           # LLM 工厂（支持搜索）
├── search_tool.py           # 外部搜索工具
├── l3_storage.py           # L3 长期记忆存储
├── batch_extractor.py      # 批量实体提取
├── relation_entity_handler.py  # 关系实体处理
├── auto_entity_maintenance.py  # 自动实体维护
├── requirements.txt        # Python 依赖
├── Dockerfile             # 容器构建
└── deploy/                # 部署相关文档
```

---

## 核心功能详解

### 1. 四级记忆架构

| 层级 | 名称 | 描述 | 存储 |
|-----|------|------|------|
| L0 | Buffer | 原始对话记录 | Supabase messages |
| L1 | Context | 会话上下文摘要 | 内存 |
| L2 | Semantic | 语义检索索引 | 内存 |
| L3 | Entity | 长期实体和事实 | Supabase entities/facts |

### 2. 搜索功能实现

**Kimi 模型（推荐）**
- 使用原生 `$web_search` builtin_function
- 需要禁用 thinking 模式：`{"thinking": {"type": "disabled"}}`
- 温度限制：`temperature=0.6`
- 成本：¥0.03/次搜索 + token 费用

**Gemini/其他模型**
- 使用外部搜索 API（DuckDuckGo/SerpAPI/Google）
- 将搜索结果作为上下文传入 LLM

### 3. 实体合并策略

为了避免实体碎片化（如"我爸"、"用户父亲"、"李国栋"指代同一人）：

1. **实时检测**：在对话中检测关系代称
2. **追问确认**：询问用户具体姓名
3. **合并映射**：将关系代称映射到具体人物实体
4. **定期维护**：自动检测和合并新产生的重复实体

---

## 配置详解

### LLM 配置

| 配置项 | System Model | User Model |
|-------|--------------|------------|
| 用途 | 路由、提取、感知 | 最终生成 |
| 推荐模型 | gemini-2.5-flash | kimi-k2.5 |
| 温度 | 0.3 | 1.0 |
| 搜索支持 | 否 | 是 |

### 搜索配置

```python
# Kimi 原生搜索（无需额外配置）
USER_MODEL=kimi-k2.5

# 外部搜索（用于 Gemini 或其他模型）
# 方式1: DuckDuckGo（免费，无需配置）
# 方式2: SerpAPI
SERPAPI_KEY=xxx
# 方式3: Google Custom Search
GOOGLE_API_KEY=xxx
GOOGLE_CX=xxx
```

---

## 调试与日志

搜索相关的日志标记：

```
[DecideIntent] 检测到搜索意图      - 识别到搜索指令
[SuggestSearch] 建议搜索            - 进入搜索建议节点
[SuggestSearch] 用户确认搜索        - 用户确认，开始搜索
[SuggestSearch] 命中搜索主题        - 自动触发搜索
[LLMWithSearch] 启用 kimi 搜索      - 实际调用搜索
[LLMWithSearch] 使用缓存结果        - 使用缓存避免重复搜索
[SearchTopic] 保存主题              - 保存搜索主题供后续使用
```

---

## 测试

```bash
# 测试 Kimi 搜索功能
python test_k25_correct_format.py

# 测试完整集成
python test_search_integration.py

# 测试实体维护
python auto_entity_maintenance.py
```

---

## 后续规划

- [ ] 搜索历史记录保存到 L0 Buffer
- [ ] 搜索结果 AI 总结
- [ ] 多轮搜索逐步深入
- [ ] 搜索开关（用户控制是否启用）
- [ ] 更多平台集成（微信、钉钉等）

---

## 技术栈

- **后端**：Python, FastAPI
- **AI 框架**：LangChain, LangGraph
- **LLM**：Kimi (Moonshot), Gemini (Google)
- **数据库**：Supabase (PostgreSQL)
- **部署**：Zeabur, Docker
- **消息平台**：Feishu/Lark

---

## 许可证

MIT License

---

## 致谢

- [Moonshot AI](https://moonshot.cn/) - Kimi 大模型
- [Google AI](https://ai.google.dev/) - Gemini 模型
- [LangChain](https://langchain.com/) - LLM 应用框架
- [Zeabur](https://zeabur.com/) - 云原生部署平台
