"""
集成测试：验证 LLMWithSearch 的完整搜索流程
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from llm_factory import LLMConfig, LLMWithSearch
from langchain_core.messages import HumanMessage, SystemMessage


async def test_search_integration():
    """测试完整的搜索集成"""
    print("=" * 70)
    print("LLMWithSearch 集成测试")
    print("=" * 70)

    # 检查配置
    base_url = os.getenv("USER_BASE_URL", "")
    model = os.getenv("USER_MODEL", "")

    print(f"\n配置:")
    print(f"  BASE_URL: {base_url}")
    print(f"  MODEL: {model}")

    # 创建 LLMWithSearch 实例
    config = LLMConfig.from_env("USER")
    llm = LLMWithSearch(config)

    print(f"\n检测到的模型类型: {llm.model_type}")

    # 测试问题
    messages = [
        SystemMessage(content="你是 Kimi AI 助手，请基于搜索结果回答用户问题。"),
        HumanMessage(content="现在是什么年份？今天是几月几号？")
    ]

    print("\n" + "-" * 70)
    print("测试 1: 普通生成（不启用搜索）")
    print("-" * 70)
    result1 = await llm.generate(messages, enable_search=False)
    print(f"回答: {result1[:200]}...")

    print("\n" + "-" * 70)
    print("测试 2: 启用搜索生成")
    print("-" * 70)
    result2 = await llm.generate(messages, enable_search=True)
    print(f"回答: {result2}")

    # 验证
    print("\n" + "=" * 70)
    print("验证结果")
    print("=" * 70)

    if "2026" in result2 or "2025" in result2:
        print("[成功] 搜索功能正常工作！AI 知道当前年份是 2026/2025")
    elif "2024" in result2:
        print("[失败] AI 仍然认为是 2024 年，搜索可能未正常工作")
    else:
        print("[不确定] 无法从回答中确定年份")

    # 测试 3: 搜索 OpenClaw
    print("\n" + "-" * 70)
    print("测试 3: 搜索 OpenClaw 信息")
    print("-" * 70)
    messages3 = [
        SystemMessage(content="你是 Kimi AI 助手，请基于搜索结果回答用户问题。"),
        HumanMessage(content="OpenClaw 是什么？请详细介绍一下这个项目。")
    ]
    result3 = await llm.generate(messages3, enable_search=True)
    print(f"回答: {result3[:500]}...")

    print("\n" + "=" * 70)
    print("所有测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_search_integration())
