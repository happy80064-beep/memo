"""
测试 Gemini-2.5-Flash (OpenAI 兼容 API)
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("SYSTEM_API_KEY"),
    base_url=os.getenv("SYSTEM_BASE_URL")
)

print("测试 Gemini-2.5-Flash...")
print(f"Base URL: {os.getenv('SYSTEM_BASE_URL')}")
print(f"Model: {os.getenv('SYSTEM_MODEL')}")
print()

response = client.chat.completions.create(
    model=os.getenv("SYSTEM_MODEL"),
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "简要解释 AI 是如何工作的，用中文回答"}
    ]
)

print("响应:")
print(response.choices[0].message.content)
