"""
测试 Kimi k2.5 thinking 模式与 tool_calls 的配合
关键问题：第二次调用时需要正确处理 reasoning_content
"""
import asyncio
import json
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()


async def test_k25_with_reasoning():
    """测试 k2.5 在正确处理 reasoning_content 时是否能使用 $web_search"""

    api_key = os.getenv("USER_API_KEY", "")
    base_url = "https://api.moonshot.cn/v1"
    model = "kimi-k2.5"

    print("=" * 70)
    print("Kimi k2.5 Thinking + $web_search 测试")
    print("=" * 70)

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 测试问题
    user_question = "现在是什么年份？今天是几月几号？"

    messages = [
        {"role": "system", "content": "你是 Kimi AI 助手。必须使用 $web_search 工具搜索互联网获取最新信息。"},
        {"role": "user", "content": f"{user_question} 请搜索互联网获取准确信息。"}
    ]

    tools = [{
        "type": "builtin_function",
        "function": {"name": "$web_search"}
    }]

    # 第一次调用 - 禁用 thinking（$web_search 与 thinking 不兼容）
    data1 = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": 1,
        "extra_body": {"thinking": {"type": "disabled"}}
    }

    print(f"\n[1] 第一次请求（禁用 thinking）...")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data1, timeout=60) as resp:
            print(f"    HTTP 状态: {resp.status}")

            if resp.status != 200:
                print(f"    错误: {await resp.text()[:200]}")
                return

            result = await resp.json()
            choice = result["choices"][0]

            print(f"    finish_reason: {choice.get('finish_reason')}")

            # 打印完整的 message 结构
            message = choice.get("message", {})
            print(f"\n    完整的 message 字段:")
            for key in message.keys():
                value = message[key]
                if isinstance(value, str):
                    print(f"      - {key}: {value[:50]}..." if len(value) > 50 else f"      - {key}: {value}")
                else:
                    print(f"      - {key}: {type(value)}")

            # 检查 response 中是否有 reasoning_content
            message = choice.get("message", {})
            reasoning_content = message.get("reasoning_content")

            if reasoning_content:
                print(f"    有 reasoning_content: {reasoning_content[:100]}...")
            else:
                print(f"    无 reasoning_content")

            if choice.get("finish_reason") != "tool_calls":
                print(f"\n    未触发 tool_calls")
                print(f"    回复: {message.get('content', '')[:100]}")
                return

            # 获取 tool_calls
            tool_calls = message.get("tool_calls", [])
            print(f"\n    触发 {len(tool_calls)} 个 tool_call(s)")

            for tc in tool_calls:
                print(f"      - {tc['function']['name']}: {tc['function']['arguments'][:100]}")

            # 关键：构建第二次请求的消息
            # 必须包含 reasoning_content（即使为空字符串）
            print("\n[2] 准备第二次请求...")

            assistant_msg = {
                "role": "assistant",
                "content": message.get("content", ""),
                "tool_calls": tool_calls
            }

            # 如果有 reasoning_content，必须添加
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            else:
                # 即使为空，也尝试添加空字符串
                assistant_msg["reasoning_content"] = ""

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
            print(f"    Assistant 消息包含 reasoning_content: {'reasoning_content' in assistant_msg}")

            # 第二次调用 - 仍然禁用 thinking
            data2 = {
                "model": model,
                "messages": messages,
                "temperature": 1,
                "extra_body": {"thinking": {"type": "disabled"}}
            }

            print("\n[3] 第二次请求...")

            async with session.post(url, headers=headers, json=data2, timeout=60) as resp:
                print(f"    HTTP 状态: {resp.status}")

                if resp.status != 200:
                    error = await resp.text()
                    print(f"    错误: {error[:300]}")
                    print("\n    [失败] 第二次调用失败，k2.5 可能不支持 $web_search")
                    return

                final = await resp.json()
                content = final["choices"][0]["message"]["content"]

                print(f"\n[4] 最终结果:")
                print("-" * 70)
                print(content)
                print("-" * 70)

                # 验证
                print("\n[5] 验证:")
                if "2026" in content or "2025" in content:
                    print("    [成功] 搜索功能正常工作！")
                else:
                    print("    [失败] 可能未使用搜索")


if __name__ == "__main__":
    asyncio.run(test_k25_with_reasoning())
