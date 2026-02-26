"""
测试 Gemini 搜索功能
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from llm_factory import LLMConfig, LLMWithSearch
from langchain_core.messages import HumanMessage, SystemMessage


async def test_gemini_search():
    """测试 Gemini 搜索功能"""
    print("=" * 60)
    print("测试 Gemini 搜索功能")
    print("=" * 60)

    # 临时切换到 Gemini 配置
    os.environ["USER_BASE_URL"] = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # 保留原有的 API key 和 model

    base_url = os.getenv("USER_BASE_URL", "")
    model = os.getenv("USER_MODEL", "")

    print(f"\n配置信息:")
    print(f"  BASE_URL: {base_url}")
    print(f"  MODEL: {model}")

    # 创建 LLMWithSearch 实例
    config = LLMConfig.from_env("USER")
    llm = LLMWithSearch(config)

    print(f"\n检测到的模型类型: {llm.model_type}")

    if llm.model_type != "gemini":
        print("\n当前配置不是 Gemini 模型，跳过测试")
        return

    # 测试问题
    messages = [
        SystemMessage(content="你是 Gemini AI 助手，请基于搜索结果回答用户问题。"),
        HumanMessage(content="现在是什么年份？请告诉我当前的年份。")
    ]

    print("\n" + "=" * 60)
    print("启用搜索生成")
    print("=" * 60)
    result = await llm.generate(messages, enable_search=True)
    print(f"回答: {result}")

    # 检查是否提到了 2026 年
    if "2026" in result:
        print("\n✅ 搜索功能正常工作！AI 知道了当前年份是 2026")
    elif "2024" in result or "2025" in result:
        print("\n❌ 搜索功能可能未正常工作，AI 仍然在使用训练数据")
    else:
        print("\n⚠️ 无法确定搜索是否正常工作，需要人工检查")


if __name__ == "__main__":
    asyncio.run(test_gemini_search())
