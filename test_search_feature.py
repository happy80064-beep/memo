# -*- coding: utf-8 -*-
"""
测试搜索功能
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

load_dotenv()

print('=' * 60)
print('搜索功能测试')
print('=' * 60)

# 测试1: LLMWithSearch 类导入
print("\n1. 测试 LLMWithSearch 导入...")
try:
    from llm_factory import get_user_llm_with_search, LLMConfig
    print("   ✓ 导入成功")
except Exception as e:
    print(f"   ✗ 导入失败: {e}")
    sys.exit(1)

# 测试2: 模型类型检测
print("\n2. 测试模型类型检测...")
from llm_factory import LLMWithSearch

config = LLMConfig(
    base_url=os.getenv("USER_BASE_URL", ""),
    api_key=os.getenv("USER_API_KEY", ""),
    model="kimi-k2.5"
)
llm = LLMWithSearch(config)
print(f"   模型: {config.model}")
print(f"   检测类型: {llm.model_type}")
print(f"   搜索工具: {llm._get_search_tools()}")

# 测试3: 搜索意图检测
print("\n3. 测试搜索意图检测...")
from graph import MemOSGraph

graph = MemOSGraph()

test_cases = [
    ("搜索一下 openclaw 是什么", True),
    ("查一下最新新闻", True),
    ("去了解了解", True),
    ("openclaw 是什么？", False),
    ("今天天气怎么样", False),
    ("好的，搜索吧", False),  # 这是确认，不是主动搜索
]

for text, expected in test_cases:
    result = graph._detect_search_intent(text)
    status = "✓" if result == expected else "✗"
    print(f"   {status} '{text[:20]}...' -> {result}")

# 测试4: 搜索确认检测
print("\n4. 测试搜索确认检测...")

confirm_cases = [
    ("好的，搜索", True),
    ("去吧", True),
    ("搜吧", True),
    ("查查看", True),
    ("不用了", False),
    ("算了", False),
]

for text, expected in confirm_cases:
    result = graph._is_search_confirmation(text)
    status = "✓" if result == expected else "✗"
    print(f"   {status} '{text[:15]}...' -> {result}")

# 测试5: 关键词提取
print("\n5. 测试关键词提取...")

test_queries = [
    "openclaw 是什么",
    "最近AI有什么新发展",
    "Kimi和GPT有什么区别",
]

for query in test_queries:
    keywords = graph._extract_keywords(query)
    print(f"   '{query}' -> {keywords}")

print("\n" + "=" * 60)
print("基础测试完成")
print("=" * 60)
print("\n注意: 实际搜索功能需要在运行环境中测试")
print("请确保 USER_BASE_URL 和 USER_API_KEY 已配置")
