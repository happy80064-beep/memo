# 搜索功能使用说明

## 功能概述

Memo 系统现在支持模型自带搜索功能（Kimi/Gemini），可以在记忆信息不足时自动建议搜索，并在用户确认后启用联网搜索。

## 工作流程

### 1. 信息不足时建议搜索

```
用户: openclaw 是什么？
AI检索: 找到 openclaw 概念，但 description="待编译..."
AI回复: "这件事我之前好像没听你聊过，我现在也不太了解，但如果你想聊，我可以马上去搜索深入了解一下。"
```

### 2. 用户确认后搜索

```
用户: 好的，搜索一下
AI: [调用 Kimi 联网搜索] "根据搜索结果，OpenClaw 是..."
```

### 3. 后续对话自动搜索

```
用户: 它有什么应用场景？（同一话题）
AI: [自动启用搜索] "根据搜索，OpenClaw 的应用场景包括..."
```

## 触发搜索的方式

### 方式1：明确搜索指令
- "搜索一下 openclaw"
- "查一下最新新闻"
- "去了解了解"
- "上网找找"

### 方式2：确认搜索建议
- "好的，搜索"
- "去吧"
- "搜吧"
- "查吧"

### 方式3：同一话题延续
一旦用户确认搜索某话题，后续 30 分钟内相关查询会自动触发搜索。

## 环境配置

确保 `.env` 文件中配置了：

```bash
# Kimi 配置（支持搜索）
USER_BASE_URL=https://api.moonshot.cn/v1
USER_API_KEY=sk-xxx
USER_MODEL=kimi-k2.5

# 或 Gemini 配置（支持搜索）
USER_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
USER_API_KEY=xxx
USER_MODEL=gemini-2.5-flash-preview
```

## 代码修改摘要

### 1. llm_factory.py
- 新增 `LLMWithSearch` 类，支持启用搜索工具
- 新增 `get_user_llm_with_search()` 函数

### 2. graph.py
- 新增 `SEARCH_REQUIRED` 意图类型
- 新增节点：`node_suggest_search` - 建议搜索
- 新增节点：`node_generate_with_search` - 使用搜索生成
- 新增方法：
  - `_detect_search_intent()` - 检测搜索意图
  - `_is_search_confirmation()` - 检测搜索确认
  - `_load_search_topics()` - 加载搜索主题
  - `_save_search_topic()` - 保存搜索主题
  - `_is_search_topic()` - 检查是否命中搜索主题
  - `_extract_keywords()` - 提取关键词

### 3. 流程图更新
```
Router (decide_intent)
    │
    ├─ deep_search ──→ Load Global ──→ Generate
    │
    ├─ load_global_context ──→ Generate
    │
    └─ suggest_search ──→ END (等待用户确认)
```

## 测试结果

运行测试脚本：
```bash
python test_search_feature.py
```

## 注意事项

1. **搜索成本**：启用搜索的调用比普通调用成本更高（2-5倍）
2. **缓存机制**：搜索结果会缓存 30 分钟，相同查询不会重复搜索
3. **中文优化**：Kimi 对中文搜索支持较好，Gemini 可能需要额外优化
4. **错误处理**：如果搜索失败，会自动回退到普通生成

## 后续优化建议

1. **添加搜索开关**：可以为每个会话添加搜索开关，让用户控制是否启用
2. **搜索历史记录**：可以保存搜索结果到 L0 Buffer，供后续参考
3. **搜索结果总结**：可以在搜索结果前添加 AI 总结，提高阅读效率
4. **多轮搜索优化**：对于复杂查询，可以支持多轮搜索逐步深入

## 调试信息

在日志中可以看到以下标记：
- `[DecideIntent] 检测到搜索意图` - 识别到搜索指令
- `[SuggestSearch] 建议搜索` - 进入搜索建议节点
- `[SuggestSearch] 用户确认搜索` - 用户确认，开始搜索
- `[SuggestSearch] 命中搜索主题` - 自动触发搜索
- `[LLMWithSearch] 启用 kimi 搜索` - 实际调用搜索
- `[LLMWithSearch] 使用缓存结果` - 使用缓存避免重复搜索
- `[SearchTopic] 保存主题` - 保存搜索主题供后续使用
