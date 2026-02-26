"""
对比测试：k2-0711-preview vs k2.5 的 $web_search 支持
"""
import asyncio
import json
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()


async def test_model(model_name):
    """测试指定模型的 $web_search 支持"""
    print(f"\n{'='*70}")
    print(f"测试模型: {model_name}")
    print('='*70)

    api_key = os.getenv("USER_API_KEY", "")
    base_url = "https://api.moonshot.cn/v1"

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    messages = [
        {"role": "system", "content": "必须使用 $web_search 工具搜索互联网。"},
        {"role": "user", "content": "现在是什么年份？"}
    ]

    tools = [{
        "type": "builtin_function",
        "function": {"name": "$web_search"}
    }]

    # 第一次调用
    data1 = {
        "model": model_name,
        "messages": messages,
        "tools": tools,
        "temperature": 1,
        "extra_body": {"thinking": {"type": "disabled"}}
    }

    print("\n[1] 第一次调用...")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data1, timeout=60) as resp:
            if resp.status != 200:
                print(f"    失败: {await resp.text()[:200]}")
                return False

            result = await resp.json()
            choice = result["choices"][0]
            message = choice["message"]

            print(f"    finish_reason: {choice.get('finish_reason')}")
            print(f"    message keys: {list(message.keys())}")

            if choice.get("finish_reason") != "tool_calls":
                print(f"    未触发 tool_calls")
                return False

            # 准备第二次调用
            print("\n[2] 准备第二次调用...")

            # 关键：正确构建 assistant 消息
            assistant_msg = {
                "role": "assistant",
                "content": message.get("content", "")
            }

            # 如果有 reasoning_content，必须保留
            if "reasoning_content" in message:
                assistant_msg["reasoning_content"] = message["reasoning_content"]
                print(f"    保留 reasoning_content: {message['reasoning_content'][:50]}...")

            # 添加 tool_calls
            assistant_msg["tool_calls"] = message.get("tool_calls", [])

            messages.append(assistant_msg)

            # 添加 tool 结果
            for tc in message.get("tool_calls", []):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": tc["function"]["arguments"]
                })

            # 第二次调用
            print("\n[3] 第二次调用...")

            data2 = {
                "model": model_name,
                "messages": messages,
                "temperature": 1,
                "extra_body": {"thinking": {"type": "disabled"}}
            }

            async with session.post(url, headers=headers, json=data2, timeout=60) as resp:
                print(f"    HTTP 状态: {resp.status}")

                if resp.status != 200:
                    error = await resp.text()
                    print(f"    错误: {error[:300]}")
                    return False

                final = await resp.json()
                content = final["choices"][0]["message"]["content"]
                print(f"\n[4] 结果: {content[:150]}...")

                if "2026" in content or "2025" in content:
                    print("    [成功] 搜索功能正常！")
                    return True
                else:
                    print("    [失败] 可能未使用搜索")
                    return False


async def main():
    print("="*70)
    print("模型对比测试")
    print("="*70)

    models = ["kimi-k2-0711-preview", "kimi-k2.5"]

    results = {}
    for model in models:
        try:
            results[model] = await test_model(model)
        except Exception as e:
            print(f"\n测试 {model} 时出错: {e}")
            results[model] = False

    print("\n" + "="*70)
    print("测试结果汇总")
    print("="*70)
    for model, success in results.items():
        status = "支持 $web_search" if success else "不支持 $web_search"
        print(f"  {model}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
