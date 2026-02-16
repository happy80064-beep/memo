"""
详细测试 Gemini API 连接
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("Gemini API 详细诊断")
print("=" * 60)

# 获取环境变量
api_key = os.getenv("SYSTEM_API_KEY", "")
base_url = os.getenv("SYSTEM_BASE_URL", "")
model = os.getenv("SYSTEM_MODEL", "gemini-2.5-flash")

print(f"\n1. 环境变量检查:")
print(f"   SYSTEM_API_KEY: {'✓ 已设置' if api_key else '✗ 未设置'}")
print(f"   SYSTEM_BASE_URL: {base_url or '✗ 未设置'}")
print(f"   SYSTEM_MODEL: {model or '✗ 未设置'}")

if not api_key or not base_url:
    print("\n✗ 缺少必要的环境变量")
    exit(1)

# 测试直接 HTTP 调用
print(f"\n2. 测试直接 HTTP 调用...")

# Gemini API 通过 OpenAI 兼容接口的调用方式
url = f"{base_url.rstrip('/')}/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
data = {
    "model": model,
    "messages": [{"role": "user", "content": "Hello"}],
    "temperature": 0.3,
    "max_tokens": 100
}

try:
    print(f"   URL: {url}")
    print(f"   Headers: Authorization: Bearer {api_key[:10]}...")
    print(f"   Model: {model}")

    response = requests.post(url, headers=headers, json=data, timeout=30)

    print(f"\n   响应状态: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        print(f"   ✓ API 调用成功")
        print(f"   响应内容: {content[:50]}...")
    elif response.status_code == 401:
        print(f"   ✗ 401 未授权 - API Key 无效")
        print(f"   响应内容: {response.text[:200]}")
    else:
        print(f"   ✗ 错误: {response.status_code}")
        print(f"   响应内容: {response.text[:500]}")

except Exception as e:
    print(f"   ✗ 请求失败: {e}")
    import traceback
    traceback.print_exc()

# 测试 LangChain 调用
print(f"\n3. 测试 LangChain 调用...")
try:
    from llm_factory import get_system_llm
    from langchain_core.messages import HumanMessage

    llm = get_system_llm()
    print(f"   LLM 配置:")
    print(f"     base_url: {llm.openai_api_base}")
    print(f"     model: {llm.model_name}")

    response = llm.invoke([HumanMessage(content="Say 'API is working' only")])
    print(f"   ✓ LangChain 调用成功")
    print(f"   响应: {response.content}")

except Exception as e:
    print(f"   ✗ LangChain 调用失败: {e}")
    import traceback
    traceback.print_exc()

print(f"\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
