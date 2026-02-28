# -*- coding: utf-8 -*-
"""
测试飞书报告推送
模拟今天的去重结果并发送报告
"""
import os
import sys
import asyncio
sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 飞书配置
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# 如果没有配置报告聊天ID，使用默认测试ID或从环境获取
FEISHU_REPORT_CHAT_ID = os.getenv("FEISHU_REPORT_CHAT_ID", "")


def generate_test_report():
    """生成测试报告（模拟数据）"""
    report = f"""🤖 MemOS 每日实体去重报告（测试）

📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}

📊 统计：
- 检查新实体：3 个
- 成功合并：1 个
- 保留为新实体：2 个

✅ 合并详情：
• /people/li-jiaze → /people/li-jia-ze (迁移 3 个 facts)

📋 保留为新实体：
• 王小红（AI判定为新人物）
• 张伟（信息不足无法判断）

🗑️ 清理：
- 无超期待编译实体

---
这是测试报告，用于验证飞书推送功能是否正常。
"""
    return report


async def send_feishu_message(chat_id: str, content: str):
    """发送消息到飞书（复制自 feishu_bot.py）"""
    import httpx
    import json

    FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

    # 获取 tenant_access_token
    token_url = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, json={
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET
        })
        data = resp.json()

        if data.get("code") != 0:
            print(f"获取token失败: {data}")
            return False

        token = data["tenant_access_token"]

    # 发送消息
    url = f"{FEISHU_BASE_URL}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    content_json = json.dumps({"text": content})
    params = {"receive_id_type": "open_id"}  # 单聊模式使用 open_id
    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": content_json
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers=headers,
            params=params,
            json=payload
        )
        data = resp.json()

        if data.get("code") == 0:
            print("✅ 报告发送成功！")
            return True
        else:
            print(f"❌ 发送失败: {data}")
            return False


async def main():
    """主函数"""
    print("=" * 60)
    print("测试飞书报告推送")
    print("=" * 60)

    # 检查配置
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        print("❌ 错误: 未配置 FEISHU_APP_ID 或 FEISHU_APP_SECRET")
        print("请在 Zeabur 环境变量中配置飞书应用凭证")
        return

    if not FEISHU_REPORT_CHAT_ID:
        print("⚠️ 警告: 未配置 FEISHU_REPORT_CHAT_ID")
        print("将尝试发送到默认聊天（需要你提供 chat_id）")
        print("\n如何获取 chat_id:")
        print("1. 在飞书群聊中 @机器人")
        print("2. 查看日志中的 chat_id 字段")
        print("3. 或运行: python -c \"from feishu_bot import ...\"")
        return

    # 生成测试报告
    report = generate_test_report()

    print("\n生成的报告内容：")
    print("-" * 60)
    print(report)
    print("-" * 60)

    # 发送报告
    print(f"\n发送到 chat_id: {FEISHU_REPORT_CHAT_ID}")
    success = await send_feishu_message(FEISHU_REPORT_CHAT_ID, report)

    if success:
        print("\n✅ 测试完成！请检查飞书是否收到消息")
    else:
        print("\n❌ 测试失败，请检查配置")


if __name__ == "__main__":
    asyncio.run(main())
