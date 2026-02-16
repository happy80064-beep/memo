"""
测试 API Key 是否有效
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("API Key 测试")
print("=" * 60)

# 检查环境变量
system_api_key = os.getenv("SYSTEM_API_KEY", "")
system_base_url = os.getenv("SYSTEM_BASE_URL", "")

print(f"\n环境变量检查:")
print(f"  SYSTEM_API_KEY: {'✓ 已设置' if system_api_key else '✗ 未设置'}")
if system_api_key:
    print(f"    值: {system_api_key[:15]}...")
    print(f"    长度: {len(system_api_key)}")
    if system_api_key.startswith("Bearer "):
        print(f"    ⚠️ 警告: API Key 不应包含 'Bearer ' 前缀")

print(f"  SYSTEM_BASE_URL: {system_base_url or '✗ 未设置'}")

# 测试调用
if system_api_key and system_base_url:
    print(f"\n测试 API 调用...")
    try:
        from llm_factory import get_system_llm
        from langchain_core.messages import HumanMessage

        llm = get_system_llm()
        response = llm.invoke([HumanMessage(content="Hello, are you working?")])
        print(f"  ✓ API 调用成功")
        print(f"  响应: {response.content[:50]}...")
    except Exception as e:
        print(f"  ✗ API 调用失败: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"\n✗ 缺少必要的环境变量，无法测试")
