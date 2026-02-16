"""
飞书机器人集成 - MemOS Feishu/Lark Bot
支持私聊和群聊，完整对接MemOS记忆系统
"""
import os
import json
import hmac
import hashlib
import base64
from datetime import datetime
from typing import Dict, Optional, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
import asyncio

from graph import chat

# 飞书应用配置
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")

# 飞书API基础地址
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

# 内存中的tenant_access_token缓存
_token_cache = {
    "token": None,
    "expire_at": 0
}


class FeishuAuth:
    """飞书认证管理"""

    @staticmethod
    async def get_tenant_access_token() -> str:
        """获取tenant_access_token"""
        global _token_cache

        # 检查缓存是否有效
        now = datetime.now().timestamp()
        if _token_cache["token"] and _token_cache["expire_at"] > now + 60:
            return _token_cache["token"]

        # 请求新token
        url = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            data = resp.json()

            if data.get("code") != 0:
                raise Exception(f"获取token失败: {data}")

            token = data["tenant_access_token"]
            expire = data["expire"]

            _token_cache["token"] = token
            _token_cache["expire_at"] = now + expire

            return token

    @staticmethod
    def verify_signature(timestamp: str, nonce: str, encrypt_key: str, body: str) -> str:
        """验证飞书消息签名"""
        if not encrypt_key:
            return ""

        # 拼接字符串
        raw_string = timestamp + nonce + encrypt_key + body
        # SHA256加密
        signature = hmac.new(
            encrypt_key.encode('utf-8'),
            raw_string.encode('utf-8'),
            hashlib.sha256
        ).digest()
        # Base64编码
        return base64.b64encode(signature).decode('utf-8')


class FeishuMessage:
    """飞书消息处理"""

    def __init__(self, event_data: Dict):
        self.event = event_data
        self.message_type = event_data.get("message", {}).get("message_type")
        self.chat_id = event_data.get("message", {}).get("chat_id")
        self.chat_type = event_data.get("message", {}).get("chat_type")
        self.sender_open_id = event_data.get("sender", {}).get("sender_id", {}).get("open_id")
        self.sender_user_id = event_data.get("sender", {}).get("sender_id", {}).get("user_id")
        self.message_id = event_data.get("message", {}).get("message_id")
        self.content = self._parse_content()
        self.msg_type = event_data.get("message", {}).get("msg_type")

    def _parse_content(self) -> str:
        """解析消息内容"""
        content_str = event_data.get("message", {}).get("content", "{}")
        try:
            content = json.loads(content_str)
            if self.msg_type == "text":
                return content.get("text", "")
            elif self.msg_type == "image":
                return "[图片消息]"
            elif self.msg_type == "file":
                return "[文件消息]"
            else:
                return f"[不支持的消息类型: {self.msg_type}]"
        except:
            return content_str

    def get_session_id(self) -> str:
        """生成MemOS session_id"""
        # 私聊用用户ID，群聊用聊天ID
        if self.chat_type == "p2p":
            return f"feishu-p2p-{self.sender_open_id}"
        else:
            return f"feishu-group-{self.chat_id}"


async def send_feishu_message(chat_id: str, content: str, msg_type: str = "text"):
    """发送消息到飞书"""
    token = await FeishuAuth.get_tenant_access_token()

    url = f"{FEISHU_BASE_URL}/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    if msg_type == "text":
        content_json = json.dumps({"text": content})
    else:
        content_json = content

    params = {"receive_id_type": "chat_id"}
    payload = {
        "receive_id": chat_id,
        "msg_type": msg_type,
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

        if data.get("code") != 0:
            print(f"[ERROR] 发送飞书消息失败: {data}")
            return False

        return True


# 创建FastAPI应用
app = FastAPI(title="MemOS Feishu Bot")


@app.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    """
    飞书事件回调入口
    需要在飞书开发者后台配置：https://memo03.zeabur.app/feishu/webhook
    """
    body = await request.body()
    body_str = body.decode('utf-8')

    try:
        data = json.loads(body_str)
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 处理URL验证（首次配置回调时）
    if data.get("type") == "url_verification":
        return {
            "challenge": data.get("challenge")
        }

    # 验证token（如果是加密模式）
    if FEISHU_VERIFICATION_TOKEN:
        if data.get("token") != FEISHU_VERIFICATION_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid token")

    # 处理事件
    event_type = data.get("header", {}).get("event_type")

    if event_type == "im.message.receive_v1":
        # 异步处理消息，避免超时
        asyncio.create_task(handle_message(data.get("event", {})))

    return JSONResponse({"code": 0})


async def handle_message(event_data: Dict):
    """处理收到的消息"""
    try:
        msg = FeishuMessage(event_data)

        # 忽略自己的消息
        if msg.sender_user_id == FEISHU_APP_ID:
            return

        print(f"[Feishu] 收到消息: {msg.content[:50]}...")
        print(f"[Feishu] 用户: {msg.sender_open_id}, 会话: {msg.get_session_id()}")

        # 调用MemOS生成回复
        result = await chat(
            user_input=msg.content,
            session_id=msg.get_session_id()
        )

        response_text = result["response"]

        # 发送回复到飞书
        await send_feishu_message(msg.chat_id, response_text)

        print(f"[Feishu] 回复已发送")

    except Exception as e:
        print(f"[ERROR] 处理飞书消息失败: {e}")
        import traceback
        traceback.print_exc()


@app.get("/feishu/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "feishu-bot"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
