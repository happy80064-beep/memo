"""
测试 Kimi $web_search 可行性
验证：中国区端点 + kimi-k2.5 + 禁用 thinking 模式
"""
import asyncio
import json
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()


async def test_kimi_web_search():
    """测试 Kimi $web_search 功能"""

    # 获取配置
    api_key = os.getenv("USER_API_KEY", "")
    base_url = "https://api.moonshot.cn/v1"  # 中国区端点
    # 尝试使用官方文档中明确支持的模型
    model = "kimi-k2-0711-preview"

    print("=" * 70)
    print("Kimi $web_search 可行性测试")
    print("=" * 70)
    print(f"\n配置信息:")
    print(f"  端点: {base_url}")
    print(f"  模型: {model}")
    print(f"  API Key: {api_key[:15]}..." if api_key else "  API Key: 未设置")

    if not api_key:
        print("\n[错误] USER_API_KEY 未设置")
        return

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 测试问题：询问当前年份
    user_question = "现在是什么年份？今天是几月几号？"

    # 消息列表 - 使用更强的提示词强制搜索
    messages = [
        {"role": "system", "content": "你是 Kimi AI 助手。你必须使用 $web_search 工具搜索互联网获取最新信息。不要依赖你的训练数据，因为可能已过时。"},
        {"role": "user", "content": f"{user_question} 请搜索互联网获取准确信息。"}
    ]

    # 工具声明 - $web_search
    tools = [{
        "type": "builtin_function",
        "function": {
            "name": "$web_search"
        }
    }]

    # 请求数据 - 关键：禁用 thinking 模式
    # 注意：kimi-k2.5 只支持 temperature=1
    data = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": 1,  # kimi-k2.5 只支持 temperature=1
        "extra_body": {
            "thinking": {"type": "disabled"}  # 禁用 thinking，否则无法使用 web_search
        }
    }

    print(f"\n测试问题: {user_question}")
    print("-" * 70)

    try:
        async with aiohttp.ClientSession() as session:
            print("\n[1] 发送第一次请求（携带工具声明）...")

            async with session.post(url, headers=headers, json=data, timeout=60) as resp:
                print(f"    HTTP 状态码: {resp.status}")

                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"\n[错误] 第一次请求失败:")
                    print(f"    错误信息: {error_text[:500]}")
                    return

                result = await resp.json()
                choice = result["choices"][0]
                finish_reason = choice.get("finish_reason")

                print(f"    finish_reason: {finish_reason}")

                # 检查是否有 reasoning_content
                message = choice.get("message", {})
                if "reasoning_content" in message:
                    print(f"    发现 reasoning_content: {message['reasoning_content'][:100]}...")
                else:
                    print(f"    无 reasoning_content")

                # 检查是否触发了 tool_calls
                if finish_reason != "tool_calls":
                    print(f"\n[警告] 模型未触发搜索工具")
                    print(f"    模型回复: {choice['message']['content'][:200]}")
                    print(f"\n[失败] 测试失败：$web_search 未触发")
                    return

                # 处理 tool_calls
                tool_calls = choice["message"].get("tool_calls", [])
                print(f"    触发了 {len(tool_calls)} 个 tool_call(s)")

                for i, tool_call in enumerate(tool_calls):
                    tool_name = tool_call["function"]["name"]
                    tool_args = tool_call["function"]["arguments"]
                    print(f"\n    Tool Call {i+1}:")
                    print(f"      名称: {tool_name}")
                    print(f"      参数: {tool_args}")

                    if tool_name == "$web_search":
                        # 解析参数（包含 total_tokens 预估）
                        try:
                            args = json.loads(tool_args)
                            if "total_tokens" in args:
                                print(f"      Token 预估: {args['total_tokens']}")
                        except:
                            pass

                # 准备第二次调用
                print("\n[2] 准备第二次请求（返回 tool 结果）...")

                # 添加 assistant 的消息（包含 tool_calls）
                # 注意：需要添加 reasoning_content 字段以避免错误
                assistant_message = dict(choice["message"])  # 复制消息
                if "reasoning_content" not in assistant_message:
                    assistant_message["reasoning_content"] = ""  # 添加空的 reasoning_content
                messages.append(assistant_message)

                # 添加 tool 结果（对于 $web_search，只需原样返回参数）
                for tool_call in tool_calls:
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_call["function"]["name"],
                        "content": tool_call["function"]["arguments"]  # 原样返回
                    }
                    messages.append(tool_message)

                print(f"    已添加 {len(tool_calls)} 个 tool 结果")

            # 第二次调用 - 需要确保仍然禁用 thinking
            print("\n[3] 发送第二次请求（获取搜索结果后的回复）...")

            # 重新构建 data，确保 extra_body 正确传递
            # 第二次调用不需要传 tools
            data2 = {
                "model": model,
                "messages": messages,
                "temperature": 1,
                "extra_body": {
                    "thinking": {"type": "disabled"}
                }
            }

            async with session.post(url, headers=headers, json=data2, timeout=60) as resp:
                print(f"    HTTP 状态码: {resp.status}")

                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"\n[错误] 第二次请求失败:")
                    print(f"    错误信息: {error_text[:500]}")
                    return

                final_result = await resp.json()
                final_choice = final_result["choices"][0]
                final_content = final_choice["message"]["content"]

                print(f"\n[4] 最终结果:")
                print("-" * 70)
                print(final_content)
                print("-" * 70)

                # 验证结果
                print("\n[5] 验证结果:")
                if "2026" in final_content:
                    print("    [成功] AI 知道当前年份是 2026，搜索功能正常工作！")
                elif "2025" in final_content:
                    print("    [成功] AI 知道当前年份是 2025，搜索功能正常工作！")
                elif "2024" in final_content:
                    print("    [失败] AI 仍然认为是 2024 年，搜索可能未正常工作")
                else:
                    print("    [警告] 无法从回答中确定当前年份，请人工判断")

                # 检查是否提到了搜索
                if "搜索" in final_content or "search" in final_content.lower():
                    print("    [成功] 回答中提到了搜索")
                else:
                    print("    [警告] 回答中没有明确提到搜索")

                print("\n" + "=" * 70)
                print("测试完成")
                print("=" * 70)

    except Exception as e:
        print(f"\n[错误] 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_kimi_web_search())
