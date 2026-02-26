"""
LLM Factory - 混合模型架构工厂
支持中国大陆访问，统一使用 OpenAI Compatible API
支持模型自带搜索功能（Kimi/Gemini）
"""

import os
import aiohttp
from typing import Optional, List, Dict, Any
from functools import lru_cache
from datetime import datetime, timedelta

from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from langchain_core.messages import BaseMessage


class LLMConfig:
    """LLM 配置类"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @classmethod
    def from_env(cls, prefix: str, **kwargs) -> "LLMConfig":
        """从环境变量加载配置

        Args:
            prefix: 配置前缀，如 'SYSTEM' 或 'USER'
            **kwargs: 覆盖默认值的额外参数
        """
        return cls(
            base_url=os.getenv(f"{prefix}_BASE_URL", ""),
            api_key=os.getenv(f"{prefix}_API_KEY", ""),
            model=os.getenv(f"{prefix}_MODEL", "gpt-4o-mini"),
            temperature=float(os.getenv(f"{prefix}_TEMPERATURE", kwargs.get("temperature", 0.7))),
            max_tokens=int(os.getenv(f"{prefix}_MAX_TOKENS", kwargs.get("max_tokens", 0))) or None,
        )


class LLMFactory:
    """LLM 工厂 - 管理双模型架构

    System Model: 用于路由、提取、批处理、感知 (快且便宜)
    User Model: 用于最终生成 (高质量)
    """

    _system_llm: Optional[ChatOpenAI] = None
    _user_llm: Optional[ChatOpenAI] = None

    @classmethod
    def _create_llm(cls, config: LLMConfig) -> ChatOpenAI:
        """创建 ChatOpenAI 实例"""
        # 直接使用配置，不做任何修改
        # Gemini OpenAI 兼容接口: https://generativelanguage.googleapis.com/v1beta/openai/
        return ChatOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    @classmethod
    def get_system_llm(cls) -> ChatOpenAI:
        """获取 System Model (Fast)

        用途:
        - 路由决策
        - 实体提取
        - 批处理任务
        - 感知/多模态处理 (Vision)
        """
        if cls._system_llm is None:
            config = LLMConfig.from_env(
                "SYSTEM",
                temperature=0.3,  # 确定性输出，适合提取和路由
            )
            cls._system_llm = cls._create_llm(config)
        return cls._system_llm

    @classmethod
    def get_user_llm(cls) -> ChatOpenAI:
        """获取 User Model (Smart)

        用途:
        - 最终内容生成
        - 深度推理
        - 复杂任务处理
        """
        if cls._user_llm is None:
            config = LLMConfig.from_env(
                "USER",
                temperature=0.7,  # 创造性输出
            )
            cls._user_llm = cls._create_llm(config)
        return cls._user_llm

    @classmethod
    def reset(cls):
        """重置缓存的 LLM 实例 (用于热重载配置)"""
        cls._system_llm = None
        cls._user_llm = None


# 便捷函数
def get_system_llm() -> ChatOpenAI:
    """获取 System Model (Fast)"""
    return LLMFactory.get_system_llm()


def get_user_llm() -> ChatOpenAI:
    """获取 User Model (Smart)"""
    return LLMFactory.get_user_llm()


def get_vision_llm() -> ChatOpenAI:
    """获取支持 Vision 的模型 (默认使用 System Model)

    确保 SYSTEM_MODEL 配置为支持 Vision 的模型:
    - Gemini-2.5-Flash
    - gpt-4o
    - Kimi k2.5
    """
    return LLMFactory.get_system_llm()


class LLMWithSearch:
    """支持搜索的 LLM 包装器

    支持 Kimi 和 Gemini 的联网搜索功能
    """

    # 搜索结果缓存（查询 -> (结果, 时间)）
    _search_cache: Dict[str, tuple] = {}
    _cache_ttl_minutes = 30

    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_llm = ChatOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        self.model_type = self._detect_model_type(config.model)

    def _detect_model_type(self, model_name: str) -> str:
        """检测模型类型"""
        model_lower = model_name.lower()
        if "kimi" in model_lower or "moonshot" in model_lower:
            return "kimi"
        elif "gemini" in model_lower or "google" in model_lower:
            return "gemini"
        else:
            return "unknown"

    def _get_search_tools(self) -> List[Dict]:
        """获取搜索工具配置"""
        if self.model_type == "kimi":
            return [{"type": "web_search"}]
        elif self.model_type == "gemini":
            return [{"google_search": {}}]
        else:
            return []

    def _get_cache_key(self, messages: List[BaseMessage]) -> str:
        """生成缓存键"""
        # 使用最后一条用户消息作为缓存键
        for msg in reversed(messages):
            if hasattr(msg, 'role') and msg.role == 'user':
                return msg.content[:100]  # 取前100字符
        return ""

    def _get_cached_result(self, key: str) -> Optional[str]:
        """获取缓存的搜索结果"""
        if key in self._search_cache:
            result, timestamp = self._search_cache[key]
            if datetime.utcnow() - timestamp < timedelta(minutes=self._cache_ttl_minutes):
                print(f"[LLMWithSearch] 使用缓存结果")
                return result
            else:
                # 过期，删除
                del self._search_cache[key]
        return None

    def _cache_result(self, key: str, result: str):
        """缓存搜索结果"""
        self._search_cache[key] = (result, datetime.utcnow())

    async def generate(self, messages: List[BaseMessage], enable_search: bool = False) -> str:
        """生成回复

        Args:
            messages: 消息列表
            enable_search: 是否启用搜索

        Returns:
            生成的文本
        """
        if not enable_search:
            # 普通生成
            response = await self.base_llm.ainvoke(messages)
            return response.content

        # 检查缓存
        cache_key = self._get_cache_key(messages)
        if cache_key:
            cached = self._get_cached_result(cache_key)
            if cached:
                return cached

        # 启用搜索生成
        result = await self._generate_with_search(messages)

        # 缓存结果
        if cache_key:
            self._cache_result(cache_key, result)

        return result

    async def _generate_with_search(self, messages: List[BaseMessage]) -> str:
        """使用搜索生成回复"""
        try:
            # 方案1: 尝试使用 extra_body 传递工具参数（LangChain方式）
            tools = self._get_search_tools()
            if tools:
                print(f"[LLMWithSearch] 启用 {self.model_type} 搜索")
                response = await self.base_llm.ainvoke(
                    messages,
                    extra_body={"tools": tools}
                )
                return response.content
        except Exception as e:
            print(f"[LLMWithSearch] extra_body 方式失败: {e}")

        try:
            # 方案2: 使用 HTTP 直接调用
            return await self._generate_with_search_http(messages)
        except Exception as e:
            print(f"[LLMWithSearch] HTTP 方式失败: {e}")

        # 回退到普通生成
        print(f"[LLMWithSearch] 回退到普通生成")
        response = await self.base_llm.ainvoke(messages)
        return response.content

    async def _generate_with_search_http(self, messages: List[BaseMessage]) -> str:
        """使用 HTTP 直接调用启用搜索"""
        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        # 转换消息格式
        msgs = []
        for msg in messages:
            role = getattr(msg, 'role', 'user')
            content = getattr(msg, 'content', str(msg))
            msgs.append({"role": role, "content": content})

        data = {
            "model": self.config.model,
            "messages": msgs,
            "tools": self._get_search_tools(),
            "temperature": self.config.temperature,
        }

        if self.config.max_tokens:
            data["max_tokens"] = self.config.max_tokens

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=60) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {text[:200]}")

                result = await resp.json()
                return result["choices"][0]["message"]["content"]


def get_user_llm_with_search() -> LLMWithSearch:
    """获取支持搜索的用户模型"""
    config = LLMConfig.from_env("USER")
    return LLMWithSearch(config)
