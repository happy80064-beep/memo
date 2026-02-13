"""
LLM Factory - 混合模型架构工厂
支持中国大陆访问，统一使用 OpenAI Compatible API
"""

import os
from typing import Optional
from functools import lru_cache

from langchain_openai import ChatOpenAI
from pydantic import SecretStr


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
        return ChatOpenAI(
            base_url=config.base_url,
            api_key=SecretStr(config.api_key) if config.api_key else None,
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
