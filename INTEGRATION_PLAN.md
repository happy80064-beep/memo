# 关系实体处理集成方案

## 目标
在实时对话流程中检测关系实体，追问用户具体姓名，避免创建碎片化的关系实体。

## 当前架构问题
```
用户消息 → L0 Buffer → batch_extractor(30分钟后) → L3 Entities
```
batch_extractor 是异步批处理，无法实时追问用户。

## 新架构方案

### 方案：实时关系检测（推荐）

在 graph.py 实时流程中添加关系检测节点：

```
用户消息
    ↓
[Node: Relation Checker] 检测是否提到关系但不知道是谁
    ↓
  ├─ 需要追问 → 直接返回追问话术，不保存到 L0
  │
  └─ 不需要追问 → 正常流程 → L0 Buffer → batch_extractor
```

## 具体修改

### 1. 修改 graph.py

#### 1.1 导入 RelationEntityHandler
```python
from relation_entity_handler import RelationEntityHandler, RELATION_CONFIGS
```

#### 1.2 在 MemOSGraph.__init__ 中初始化
```python
def __init__(self):
    # ... 现有代码 ...
    self.relation_handler = RelationEntityHandler(self.supabase)
    # 会话级别的待确认关系状态
    self._session_pending_relations: Dict[str, Dict] = {}
```

#### 1.3 添加新节点：node_relation_check
```python
async def node_relation_check(self, state: GraphState) -> GraphState:
    """
    关系检测节点
    检测用户是否提到关系但系统不知道具体是谁
    """
    user_input = state["user_input"]
    session_id = state["session_id"]

    # 检查是否有待确认的关系（用户之前被追问过）
    pending = self._session_pending_relations.get(session_id)
    if pending:
        # 用户可能回答了姓名，尝试提取
        name = self.relation_handler.extract_name_from_response(user_input)
        if name:
            # 创建关系映射
            result = self.relation_handler.create_relation_mapping(
                pending["relation_key"],
                name,
                session_id
            )
            if result["success"]:
                # 清除待确认状态
                del self._session_pending_relations[session_id]
                # 回复确认
                response = f"好嘞！{name}我记下了，以后你一说'{pending['display_name']}'我就知道是谁啦！"
                return {
                    **state,
                    "response": response,
                    "intent": "CASUAL",
                    "metadata": {"early_return": True, "relation_mapped": True}
                }
        else:
            # 用户还是没告诉名字，增加询问次数
            pending["ask_count"] += 1
            if pending["ask_count"] >= 2:
                # 放弃追问
                question = self.relation_handler._generate_question(
                    pending["relation_key"], "give_up"
                )
                del self._session_pending_relations[session_id]
                return {
                    **state,
                    "response": question,
                    "intent": "CASUAL",
                    "metadata": {"early_return": True, "give_up": True}
                }
            else:
                # 继续追问
                question = self.relation_handler._generate_question(
                    pending["relation_key"], "retry_ask"
                )
                return {
                    **state,
                    "response": question,
                    "intent": "CASUAL",
                    "metadata": {"early_return": True}
                }

    # 检查用户输入是否包含关系称呼
    for relation_key, config in RELATION_CONFIGS.items():
        # 检查是否提到该关系
        if any(synonym in user_input for synonym in config.synonyms):
            # 查找是否已知对应的具体人物
            concrete_person = self.relation_handler.find_concrete_person(relation_key)
            if not concrete_person:
                # 不知道是谁，需要追问
                self._session_pending_relations[session_id] = {
                    "relation_key": relation_key,
                    "display_name": config.display_name,
                    "ask_count": 0
                }
                question = self.relation_handler._generate_question(relation_key, "first_ask")
                return {
                    **state,
                    "response": question,
                    "intent": "CASUAL",
                    "metadata": {"early_return": True, "relation_unknown": True}
                }

    # 正常流程，继续
    return state
```

#### 1.4 修改流程图
```python
def _build_graph(self) -> StateGraph:
    graph = StateGraph(GraphState)

    # 添加节点
    graph.add_node("relation_check", self.node_relation_check)  # 新增
    graph.add_node("router", self.node_router)
    graph.add_node("load_global_context", self.node_load_global_context)
    graph.add_node("deep_search", self.node_deep_search)
    graph.add_node("generate", self.node_generate)

    # 设置入口
    graph.set_entry_point("relation_check")  # 修改入口

    # 条件边：如果需要追问，直接结束
    graph.add_conditional_edges(
        "relation_check",
        self.check_early_return,  # 新增条件函数
        {
            "early_return": END,
            "continue": "router"
        }
    )

    # ... 后续流程保持不变 ...
```

#### 1.5 添加条件函数
```python
def check_early_return(self, state: GraphState) -> str:
    """检查是否需要提前返回（追问用户）"""
    metadata = state.get("metadata", {})
    if metadata.get("early_return"):
        # 保存AI回复到L0（可选，记录追问历史）
        self._save_to_l0_buffer(
            role="ai",
            content=state["response"],
            attachments=[],
            perception="追问用户关系映射"
        )
        return "early_return"
    return "continue"
```

### 2. 修改 batch_extractor.py（可选增强）

如果 batch_extractor 还是提取到了关系实体（比如通过历史消息），可以添加后处理：

```python
def process_batch(self, batch_size: int = 100):
    # ... 现有代码 ...

    # 提取实体后，进行关系实体过滤
    from relation_entity_handler import RelationEntityHandler
    handler = RelationEntityHandler(self.supabase)

    filtered_entities, filtered_facts, pending_questions = handler.process_entities(
        entities, facts, "batch_session", conversation
    )

    # 如果有关系实体没有映射，跳过这些事实（等用户明确后再处理）
    if pending_questions:
        print(f"[BatchExtractor] 跳过 {len(pending_questions)} 个待确认关系")
        # 不存储这些事实，标记消息为已处理但不提取

    entities = filtered_entities
    facts = filtered_facts

    # ... 继续处理 ...
```

## 数据迁移总结

已完成：
- ✅ 清理 user-father 等关系实体的错误事实
- ✅ 迁移 user-mother → 杨桂花（生日4月6日）
- ✅ 迁移 my-dad → 李国栋（爱好、生日2月16日）

待处理：
- ⏳ user-wife（妻子）→ 下次提到时追问姓名
- ⏳ user-son（儿子）→ 下次提到时追问姓名

## 测试场景

### 场景1：首次提到父亲（已知）
```
用户：我爸快过生日了
AI：你爸李国栋生日是3月20日，快到了！
```

### 场景2：首次提到妻子（未知）
```
用户：我妻子喜欢滑雪
AI：诶，我想不起来阿姨叫什么名字了😅 你能告诉我一下吗？
      这样以后你一说'我妻子'我就知道是谁啦！

用户：她叫贾XX
AI：好嘞！贾XX我记下了，以后你一说'我妻子'我就知道是谁啦！
      她喜欢滑雪呀？还有别的爱好吗？
```

### 场景3：拒绝告诉名字（2次）
```
用户：我妻子喜欢滑雪
AI：诶，我想不起来阿姨叫什么名字了😅 你能告诉我一下吗？

用户：我不想说
AI：哎呀别嘛~ 告诉我一下嘛，就一下下！不然我老是搞混😣

用户：说了不想说
AI：好吧好吧，那等你想起来了再告诉我吧🤗 咱们聊点别的？
      最近有什么好玩的事吗？
```

## 实施建议

1. **先测试已知的映射**（李国栋、杨桂花）
2. **再测试未知的追问**（user-wife、user-son）
3. **最后优化话术**（根据实际回复调整）

是否需要我实施这个集成方案？
