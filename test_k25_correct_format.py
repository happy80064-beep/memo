"""
使用正确的格式测试 k2.5 的 $web_search
官网示例：thinking 放在请求体顶层，不是 extra_body
"""
import asyncio
import json
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()


async def test_k25_correct_format():
    """使用正确的请求格式测试 k2.5"""

    print("=" * 70)
    print("Kimi k2.5 $web_search 测试 - 正确的请求格式")
    print("=" * 70)

    api_key = os.getenv("USER_API_KEY", "")
    base_url = "https://api.moonshot.cn/v1"
    model = "kimi-k2.5"

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    messages = [
        {"role": "system", "content": "必须使用 $web_search 工具搜索互联网获取最新信息。"},
        {"role": "user", "content": "现在是什么年份？今天是几月几号？请搜索获取准确信息。"}
    ]

    tools = [{
        "type": "builtin_function",
        "function": {"name": "$web_search"}
    }]

    # 官网示例格式：thinking 直接放在请求体顶层
    # 注意：当禁用 thinking 时，k2.5 只支持 temperature=0.6
    data1 = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": 0.6,  # 禁用 thinking 时，k2.5 只支持 0.6
        "thinking": {"type": "disabled"}  # 官网格式：直接放在顶层，不是 extra_body
    }

    print(f"\n配置:")
    print(f"  模型: {model}")
    print(f"  temperature: 0.6 (禁用 thinking 时 k2.5 只支持这个值)")
    print(f"  thinking: {{'type': 'disabled'}}")
    print(f"  请求体结构: {list(data1.keys())}")

    print("\n[1] 第一次调用...")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data1, timeout=60) as resp:
            print(f"    HTTP 状态: {resp.status}")

            if resp.status != 200:
                error = await resp.text()
                print(f"    错误: {error[:300]}")
                return

            result = await resp.json()
            choice = result["choices"][0]
            message = choice["message"]

            print(f"    finish_reason: {choice.get('finish_reason')}")
            print(f"    message keys: {list(message.keys())}")

            # 检查是否有 reasoning_content
            if "reasoning_content" in message:
                print(f"    reasoning_content: {message['reasoning_content'][:100]}...")
            else:
                print(f"    无 reasoning_content")

            if choice.get("finish_reason") != "tool_calls":
                print(f"\n    未触发 tool_calls")
                print(f"    回复: {message.get('content', '')[:200]}")
                return

            # 获取 tool_calls
            tool_calls = message.get("tool_calls", [])
            print(f"\n    触发 {len(tool_calls)} 个 tool_call(s)")
            for tc in tool_calls:
                print(f"      - {tc['function']['name']}")

            # 准备第二次调用
            print("\n[2] 准备第二次调用...")

            # 构建 assistant 消息
            assistant_msg = {
                "role": "assistant",
                "content": message.get("content", ""),
                "tool_calls": tool_calls
            }

            # 关键：如果有 reasoning_content，必须保留
            if "reasoning_content" in message:
                assistant_msg["reasoning_content"] = message["reasoning_content"]
                print(f"    添加 reasoning_content 到 assistant 消息")

            messages.append(assistant_msg)

            # 添加 tool 结果
            for tc in tool_calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": tc["function"]["arguments"]
                })

            print(f"    消息列表长度: {len(messages)}")

            # 第二次调用 - 同样格式
            data2 = {
                "model": model,
                "messages": messages,
                "temperature": 0.6,  # 禁用 thinking 时，k2.5 只支持 0.6
                "thinking": {"type": "disabled"}  # 保持禁用 thinking
            }

            print("\n[3] 第二次调用...")

            async with session.post(url, headers=headers, json=data2, timeout=60) as resp:
                print(f"    HTTP 状态: {resp.status}")

                if resp.status != 200:
                    error = await resp.text()
                    print(f"    错误: {error[:300]}")
                    print("\n    [失败] k2.5 即使使用正确格式也不支持 $web_search")
                    return

                final = await resp.json()
                content = final["choices"][0]["message"]["content"]

                print(f"\n[4] 最终结果:")
                print("-" * 70)
                print(content)
                print("-" * 70)

                # 验证
                print("\n[5] 验证:")
                if "2026" in content:
                    print("    [成功] AI 知道是 2026 年，搜索功能正常工作！")
                elif "2025" in content:
                    print("    [成功] AI 知道是 2025 年，搜索功能正常工作！")
                elif "2024" in content:
                    print("    [失败] AI 仍然认为是 2024 年")
                else:
                    print("    [不确定] 无法从回答中确定年份")


if __name__ == "__main__":
    asyncio.run(test_k25_correct_format())
