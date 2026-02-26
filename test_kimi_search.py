"""
测试 Kimi 搜索功能是否正确工作
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from llm_factory import LLMConfig, LLMWithSearch
from langchain_core.messages import HumanMessage, SystemMessage


async def test_kimi_search():
    """测试 Kimi 搜索功能"""
    print("=" * 60)
    print("测试 Kimi 搜索功能")
    print("=" * 60)

    # 检查配置
    base_url = os.getenv("USER_BASE_URL", "")
    api_key = os.getenv("USER_API_KEY", "")[:10] + "..." if os.getenv("USER_API_KEY") else ""
    model = os.getenv("USER_MODEL", "")

    print(f"\n配置信息:")
    print(f"  BASE_URL: {base_url}")
    print(f"  API_KEY: {api_key}")
    print(f"  MODEL: {model}")

    # 创建 LLMWithSearch 实例
    config = LLMConfig.from_env("USER")
    llm = LLMWithSearch(config)

    print(f"\n检测到的模型类型: {llm.model_type}")

    # 测试问题：需要联网搜索才能回答
    messages = [
        SystemMessage(content="你是 Kimi AI 助手，请基于搜索结果回答用户问题。"),
        HumanMessage(content="现在是什么年份？请告诉我当前的年份。")
    ]

    print("\n" + "=" * 60)
    print("测试 1: 普通生成（不启用搜索）")
    print("=" * 60)
    result1 = await llm.generate(messages, enable_search=False)
    print(f"回答: {result1}")

    print("\n" + "=" * 60)
    print("测试 2: 启用搜索生成")
    print("=" * 60)
    result2 = await llm.generate(messages, enable_search=True)
    print(f"回答: {result2}")

    # 检查是否提到了 2026 年
    if "2026" in result2:
        print("\n✅ 搜索功能正常工作！AI 知道了当前年份是 2026")
    elif "2024" in result2 or "2025" in result2:
        print("\n❌ 搜索功能可能未正常工作，AI 仍然在使用训练数据")
    else:
        print("\n⚠️ 无法确定搜索是否正常工作，需要人工检查")

    # 测试 OpenClaw 搜索
    print("\n" + "=" * 60)
    print("测试 3: 搜索 OpenClaw 信息")
    print("=" * 60)
    messages3 = [
        SystemMessage(content="你是 Kimi AI 助手，请基于搜索结果回答用户问题。"),
        HumanMessage(content="OpenClaw 是什么？请详细介绍一下这个项目。")
    ]
    result3 = await llm.generate(messages3, enable_search=True)
    print(f"回答: {result3[:500]}...")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_kimi_search())
