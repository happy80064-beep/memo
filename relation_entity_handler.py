"""
关系实体处理器 - 后处理过滤方案
解决：user-father, user-mother 等关系实体与具体人物的映射问题
"""

import os
import re
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


# =============================================================================
# 1. 配置定义
# =============================================================================

@dataclass
class RelationConfig:
    """关系配置"""
    key: str  # user-father
    display_name: str  # 父亲
    synonyms: List[str]  # ["我爸", "我父亲", ...]
    ask_count: int = 0  # 当前询问次数


RELATION_CONFIGS = {
    "user-father": RelationConfig(
        key="user-father",
        display_name="父亲",
        synonyms=["我爸", "我父亲", "爸爸", "父亲", "家父", "老爸", "我爹", "老爷子"]
    ),
    "user-mother": RelationConfig(
        key="user-mother",
        display_name="母亲",
        synonyms=["我妈", "我母亲", "妈妈", "母亲", "家母", "老妈", "老娘"]
    ),
    "user-wife": RelationConfig(
        key="user-wife",
        display_name="妻子",
        synonyms=["我妻子", "我老婆", "媳妇", "太太", "爱人", "对象"]
    ),
    "user-husband": RelationConfig(
        key="user-husband",
        display_name="丈夫",
        synonyms=["我丈夫", "我老公", "先生", "爱人", "对象"]
    ),
    "user-son": RelationConfig(
        key="user-son",
        display_name="儿子",
        synonyms=["我儿子", "孩子", "娃", "小子"]
    ),
    "user-daughter": RelationConfig(
        key="user-daughter",
        display_name="女儿",
        synonyms=["我女儿", "姑娘", "丫头", "闺女"]
    ),
}


# =============================================================================
# 2. 话术模板（亲切版）
# =============================================================================

QUESTION_TEMPLATES = {
    "user-father": {
        "first_ask": [
            "诶，我想不起来叔叔叫什么名字了😅 你能告诉我一下吗？这样以后你一说'我爸'我就知道是谁啦！",
            "哎呀，我脑子里的'爸爸'档案上写着'姓名待填'😂 快告诉我叔叔叫啥名，我补全这个档案！",
            "不好意思呀，我忘了叔叔叫什么了🙈 能再提醒我一下吗？这次我一定记牢！",
        ],
        "retry_ask": [
            "哎呀别嘛~ 告诉我一下嘛，就一下下！不然我老是搞混😣",
            "求求你啦🥺 就告诉我名字，我保证以后再也不问了，直接记住！",
            "那...悄悄告诉我？我保密！不说名字我真的帮不上忙呢😔",
        ],
        "give_up": [
            "好吧好吧，那等你想起来了再告诉我吧🤗 咱们聊点别的？最近有什么好玩的事吗？",
            "行吧行吧，那叔叔的名字档案先空着~ 等哪天你想说了再补！对了，你最近忙什么呢？",
            "好嘞，那我不追问啦😄 等你想起来叔叔名字咱们再回忆！最近过得怎么样？",
        ],
    },
    "user-mother": {
        "first_ask": [
            "诶，我想不起来阿姨叫什么名字了😅 你能告诉我一下吗？这样以后你一说'我妈'我就知道是谁啦！",
            "哎呀，我忘了阿姨叫什么了🙈 能再提醒我一下吗？这次我一定记牢！",
        ],
        "retry_ask": [
            "哎呀别嘛~ 告诉我一下嘛，就一下下！不说名字我帮不上忙呢😣",
            "求求你啦🥺 就告诉我名字，我保证以后直接记住！",
        ],
        "give_up": [
            "好吧好吧，那等你想起来了再告诉我吧🤗 咱们聊点别的？",
            "好嘞，那我不追问啦😄 等你想起来阿姨名字咱们再回忆！",
        ],
    },
    # 其他关系类似...
    "default": {
        "first_ask": [
            "诶，我想不起来{display_name}叫什么名字了😅 你能告诉我一下吗？",
            "哎呀，我忘了{display_name}叫什么了🙈 能再提醒我一下吗？",
        ],
        "retry_ask": [
            "哎呀别嘛~ 告诉我一下嘛，就一下下！😣",
            "求求你啦🥺 就告诉我名字，我保证记住！",
        ],
        "give_up": [
            "好吧好吧，那等你想起来了再告诉我吧🤗 咱们聊点别的？",
            "好嘞，那我不追问啦😄 等你想起来咱们再回忆！",
        ],
    }
}


# =============================================================================
# 3. 关系实体处理器
# =============================================================================

class RelationEntityHandler:
    """关系实体处理器"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        # 会话级别的待确认关系 {session_id: {relation_key: ask_count}}
        self.pending_relations: Dict[str, Dict[str, int]] = {}

    def is_relation_entity(self, entity_path: str) -> bool:
        """检查是否为关系实体（而非具体人物）"""
        return any(
            entity_path == f"/people/{key}"
            for key in RELATION_CONFIGS.keys()
        )

    def get_relation_config(self, entity_path: str) -> Optional[RelationConfig]:
        """获取关系配置"""
        key = entity_path.replace("/people/", "")
        return RELATION_CONFIGS.get(key)

    def find_concrete_person(self, relation_key: str) -> Optional[Dict]:
        """
        根据关系查找对应的具体人物

        策略：
        1. 查找所有人物实体的原子事实
        2. 找包含"XX是用户的{关系}"的事实
        3. 返回对应的人物实体
        """
        config = RELATION_CONFIGS.get(relation_key)
        if not config:
            return None

        # 搜索关系事实
        search_patterns = [
            f"%是用户的{config.display_name}%",
            f"%是用户的{config.display_name}（%",
        ]

        for pattern in search_patterns:
            facts = self.supabase.table("mem_l3_atomic_facts") \
                .select("entity_id, content, mem_l3_entities(path, name)") \
                .eq("status", "active") \
                .ilike("content", pattern) \
                .execute()

            if facts.data:
                fact = facts.data[0]
                entity = fact.get("mem_l3_entities", {})
                return {
                    "entity_id": fact["entity_id"],
                    "entity_path": entity.get("path"),
                    "name": entity.get("name"),
                    "fact_content": fact["content"]
                }

        return None

    def process_entities(
        self,
        entities: List[Dict],
        facts: List[Dict],
        session_id: str,
        conversation: str
    ) -> Tuple[List[Dict], List[Dict], Optional[str]]:
        """
        处理提取的实体，过滤关系实体

        Returns:
            (filtered_entities, filtered_facts, question_to_user)
            question_to_user: 如果需要追问用户，返回问题；否则返回None
        """
        filtered_entities = []
        filtered_facts = []

        # 初始化会话的待确认关系记录
        if session_id not in self.pending_relations:
            self.pending_relations[session_id] = {}

        for entity in entities:
            path = entity.get("path", "")

            # 检查是否为关系实体
            if self.is_relation_entity(path):
                relation_key = path.replace("/people/", "")
                config = self.get_relation_config(path)

                # 查找对应的具体人物
                concrete_person = self.find_concrete_person(relation_key)

                if concrete_person:
                    # 情况1：找到对应的具体人物
                    print(f"[RelationHandler] 关系 '{relation_key}' 对应 "
                          f"'{concrete_person['name']}'，合并事实")

                    # 将事实迁移到具体人物下
                    for fact in facts:
                        if fact.get("entity_path") == path:
                            fact["entity_path"] = concrete_person["entity_path"]
                            filtered_facts.append(fact)

                    # 确保具体人物在实体列表中
                    if not any(e.get("path") == concrete_person["entity_path"]
                               for e in filtered_entities):
                        filtered_entities.append({
                            "path": concrete_person["entity_path"],
                            "name": concrete_person["name"],
                            "entity_type": "person"
                        })

                else:
                    # 情况2：未找到对应的具体人物
                    # 检查询问次数
                    ask_count = self.pending_relations[session_id].get(relation_key, 0)

                    if ask_count >= 2:
                        # 已经问过2次了，放弃追问
                        print(f"[RelationHandler] 关系 '{relation_key}' 已追问2次，放弃")
                        question = self._generate_question(relation_key, "give_up")
                        # 不创建实体，返回放弃追问的话术
                        return [], [], question
                    else:
                        # 增加询问次数
                        self.pending_relations[session_id][relation_key] = ask_count + 1

                        # 生成追问话术
                        if ask_count == 0:
                            question = self._generate_question(relation_key, "first_ask")
                        else:
                            question = self._generate_question(relation_key, "retry_ask")

                        print(f"[RelationHandler] 未找到 '{relation_key}' 对应的人物，"
                              f"第{ask_count + 1}次追问")

                        # 不创建实体，返回追问话术
                        return [], [], question

            else:
                # 不是关系实体，正常保留
                filtered_entities.append(entity)
                filtered_facts.extend([
                    f for f in facts
                    if f.get("entity_path") == path
                ])

        return filtered_entities, filtered_facts, None

    def _generate_question(self, relation_key: str, stage: str) -> str:
        """生成追问话术"""
        templates = QUESTION_TEMPLATES.get(relation_key, QUESTION_TEMPLATES["default"])
        stage_templates = templates.get(stage, QUESTION_TEMPLATES["default"][stage])

        config = RELATION_CONFIGS.get(relation_key)
        display_name = config.display_name if config else ""

        template = random.choice(stage_templates)
        return template.format(display_name=display_name)

    def extract_name_from_response(self, user_input: str) -> Optional[str]:
        """
        从用户回答中提取姓名

        支持格式：
        - "我爸叫李国栋"
        - "李国栋"
        - "他叫李国栋"
        - "名字是李国栋"
        """
        # 常见姓名模式
        patterns = [
            r"(?:叫|是|名字[是叫])([\u4e00-\u9fa5]{2,4})",
            r"([\u4e00-\u9fa5]{2,4})(?:是|叫)",
            r"^([\u4e00-\u9fa5]{2,4})$",  # 纯姓名
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                name = match.group(1)
                # 过滤常见非姓名词
                if name not in ["什么", "谁啊", "不知道", "忘了", "保密"]:
                    return name

        # 如果没匹配到，尝试提取2-4个汉字
        clean_input = re.sub(r"[我爸妈他叫是名字的全名叫]", "", user_input).strip()
        if 2 <= len(clean_input) <= 4 and re.match(r"^[\u4e00-\u9fa5]+$", clean_input):
            return clean_input

        return None

    def create_relation_mapping(
        self,
        relation_key: str,
        person_name: str,
        session_id: str
    ) -> Dict:
        """
        创建关系映射

        在对应人物实体下添加关系事实
        """
        config = RELATION_CONFIGS.get(relation_key)
        if not config:
            return {"success": False, "error": "Unknown relation"}

        # 生成实体路径（拼音）
        person_path = self._name_to_path(person_name)

        # 获取或创建实体
        existing = self.supabase.table("mem_l3_entities") \
            .select("id, path, name") \
            .eq("path", person_path) \
            .execute()

        if existing.data:
            entity_id = existing.data[0]["id"]
        else:
            # 创建新实体
            result = self.supabase.table("mem_l3_entities").insert({
                "path": person_path,
                "name": person_name,
                "description_md": f"# {person_name}\n\n待编译...",
                "entity_type": "person",
                "is_pinned": False,
            }).execute()
            entity_id = result.data[0]["id"]

        # 检查是否已有该关系（避免重复）
        existing_relation = self.supabase.table("mem_l3_atomic_facts") \
            .select("id") \
            .eq("entity_id", entity_id) \
            .eq("status", "active") \
            .ilike("content", f"%{person_name}是用户的{config.display_name}%") \
            .execute()

        if not existing_relation.data:
            # 添加关系事实
            self.supabase.table("mem_l3_atomic_facts").insert({
                "entity_id": entity_id,
                "content": f"{person_name}是用户的{config.display_name}",
                "status": "active",
                "source_type": "inference",
                "context_json": {
                    "extracted_at": datetime.utcnow().isoformat(),
                    "relation_type": relation_key,
                    "session_id": session_id
                }
            }).execute()

        # 清除待确认状态
        if session_id in self.pending_relations:
            self.pending_relations[session_id].pop(relation_key, None)

        return {
            "success": True,
            "entity_path": person_path,
            "entity_id": entity_id,
            "relation": relation_key
        }

    def _name_to_path(self, name: str) -> str:
        """将姓名转换为路径格式（拼音）"""
        # 简单的拼音转换（实际项目中可以用拼音库）
        # 这里简化处理：直接用中文名的拼音风格
        common_names = {
            "李国栋": "li-guodong",
            "李俊杰": "li-jun-jie",
            "杨桂花": "yang-guihua",
            # ... 可以扩展
        }

        if name in common_names:
            return f"/people/{common_names[name]}"

        # 通用处理：转为小写，空格转连字符
        # 实际应该用 pypinyin 库
        return f"/people/{name.lower().replace(' ', '-')}"

    def clear_session(self, session_id: str):
        """清除会话的待确认关系记录"""
        self.pending_relations.pop(session_id, None)


# =============================================================================
# 4. 使用示例
# =============================================================================

if __name__ == "__main__":
    # 测试代码
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    handler = RelationEntityHandler(supabase)

    # 测试场景1：已知关系映射
    print("测试1：查找 user-father 映射")
    result = handler.find_concrete_person("user-father")
    print(f"结果: {result}")

    # 测试场景2：生成追问话术
    print("\n测试2：生成追问话术")
    for stage in ["first_ask", "retry_ask", "give_up"]:
        question = handler._generate_question("user-father", stage)
        print(f"{stage}: {question}")

    # 测试场景3：提取姓名
    print("\n测试3：从回答中提取姓名")
    test_inputs = [
        "我爸叫李国栋",
        "李国栋",
        "他叫李国栋",
        "名字是李国栋",
    ]
    for text in test_inputs:
        name = handler.extract_name_from_response(text)
        print(f"'{text}' -> {name}")
