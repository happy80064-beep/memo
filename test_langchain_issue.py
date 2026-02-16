"""
诊断 LangChain 调用问题
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("LangChain 问题诊断")
print("=" * 60)

# 获取环境变量
api_key = os.getenv("SYSTEM_API_KEY", "")
base_url = os.getenv("SYSTEM_BASE_URL", "")
model = os.getenv("SYSTEM_MODEL", "gemini-2.5-flash-preview")

print(f"\n1. 环境变量:")
print(f"   API Key: {api_key[:15]}... (长度: {len(api_key)})")
print(f"   Base URL: {base_url}")
print(f"   Model: {model}")

# 测试1: 直接实例化 ChatOpenAI
print(f"\n2. 测试直接实例化 ChatOpenAI...")
try:
    from langchain_openai import ChatOpenAI
    from pydantic import SecretStr

    llm = ChatOpenAI(
        base_url=base_url.rstrip("/"),
        api_key=SecretStr(api_key),
        model=model,
        temperature=0.3,
    )
    print(f"   ✓ 实例化成功")
    print(f"     - base_url: {llm.openai_api_base}")
    print(f"     - model: {llm.model_name}")
    print(f"     - api_key type: {type(llm.openai_api_key)}")

except Exception as e:
    print(f"   ✗ 实例化失败: {e}")
    import traceback
    traceback.print_exc()

# 测试2: 使用字符串 API Key（不用 SecretStr）
print(f"\n3. 测试不使用 SecretStr...")
try:
    from langchain_openai import ChatOpenAI

    llm2 = ChatOpenAI(
        base_url=base_url.rstrip("/"),
        api_key=api_key,  # 直接用字符串
        model=model,
        temperature=0.3,
    )
    print(f"   ✓ 实例化成功")

    # 尝试调用
    from langchain_core.messages import HumanMessage
    response = llm2.invoke([HumanMessage(content="Say 'test passed'")])
    print(f"   ✓ 调用成功: {response.content}")

except Exception as e:
    print(f"   ✗ 失败: {e}")
    import traceback
    traceback.print_exc()

# 测试3: 使用 openai 库直接调用
print(f"\n4. 测试 openai 库直接调用...")
try:
    from openai import OpenAI

    client = OpenAI(
        base_url=base_url.rstrip("/"),
        api_key=api_key
    )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say 'openai works'"}],
        temperature=0.3,
    )
    print(f"   ✓ 调用成功: {response.choices[0].message.content}")

except Exception as e:
    print(f"   ✗ 失败: {e}")
    import traceback
    traceback.print_exc()

# 测试4: 检查 langchain-openai 版本
print(f"\n5. 检查版本...")
try:
    import langchain_openai
    print(f"   langchain-openai: {langchain_openai.__version__}")
except:
    print(f"   无法获取版本")

try:
    import openai
    print(f"   openai: {openai.__version__}")
except:
    print(f"   无法获取版本")

print(f"\n" + "=" * 60)
