"""
MemOS Web API - FastAPI Interface for Conversations
Deploy this to Zeabur to get a chat API endpoint
"""

import os
import asyncio
import json
import hmac
import hashlib
import base64
from typing import List, Optional, Dict
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import httpx

from graph import chat, get_graph
from supabase import create_client

load_dotenv()

# ============================================================================
# 飞书机器人配置
# ============================================================================

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

# 内存中的tenant_access_token缓存
_token_cache = {
    "token": None,
    "expire_at": 0
}


# ============================================================================
# Pydantic Models
# ============================================================================

class ChatRequest(BaseModel):
    """Chat request model"""
    message: str = Field(..., description="User message", min_length=1)
    session_id: str = Field(default="default", description="Unique session ID")
    attachments: Optional[List[dict]] = Field(
        default=None,
        description="Optional attachments [{\"url\": \"...\", \"mime_type\": \"image/png\"}]"
    )


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str = Field(..., description="AI response")
    intent: str = Field(..., description="Detected intent (CHAT/WORK)")
    metadata: dict = Field(..., description="Response metadata")


class StatsResponse(BaseModel):
    """System stats response"""
    l0_total: int
    l0_processed: int
    l0_unprocessed: int
    l3_entities: int
    atomic_facts: int
    compiled_entities: int


# ============================================================================
# FastAPI App
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup: Initialize graph
    print("=" * 60)
    print("MemOS Web API Starting...")
    print("=" * 60)

    # Pre-load the graph to avoid cold start
    get_graph()
    print("[OK] Graph initialized")

    yield

    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title="MemOS API",
    description="AI Memory System with RAG pipeline",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# API Endpoints
# ============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint

    Example request:
    ```json
    {
        "message": "Tell me about MemOS project",
        "session_id": "user-001"
    }
    ```
    """
    try:
        result = await chat(
            user_input=request.message,
            session_id=request.session_id,
            attachments=request.attachments
        )

        return ChatResponse(
            response=result["response"],
            intent=result["intent"],
            metadata=result["metadata"]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get system statistics"""
    try:
        from supabase import create_client

        client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )

        # L0 stats
        l0_total = client.table("mem_l0_buffer").select("count", count="exact").execute().count
        l0_processed = client.table("mem_l0_buffer").select("count", count="exact").eq("processed", True).execute().count

        # L3 stats
        l3_entities = client.table("mem_l3_entities").select("count", count="exact").execute().count

        # Facts stats
        atomic_facts = client.table("mem_l3_atomic_facts").select("count", count="exact").execute().count

        # Compiled stats
        compiled = client.table("mem_l3_entities").select("count", count="exact").neq("description_md", "# {name}\n\n待编译...\n").execute().count

        return StatsResponse(
            l0_total=l0_total,
            l0_processed=l0_processed,
            l0_unprocessed=l0_total - l0_processed,
            l3_entities=l3_entities,
            atomic_facts=atomic_facts,
            compiled_entities=compiled
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "memos",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with simple HTML interface"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MemOS API</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #333; }
            .endpoint {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 5px;
                margin: 10px 0;
                font-family: monospace;
            }
            .method {
                display: inline-block;
                padding: 3px 8px;
                border-radius: 3px;
                font-weight: bold;
                margin-right: 10px;
            }
            .post { background: #28a745; color: white; }
            .get { background: #007bff; color: white; }
            code {
                background: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
            }
            #chat-box {
                margin-top: 30px;
                border-top: 2px solid #eee;
                padding-top: 20px;
            }
            #messages {
                height: 300px;
                overflow-y: auto;
                border: 1px solid #ddd;
                padding: 10px;
                margin-bottom: 10px;
                background: #fafafa;
            }
            .message {
                margin: 10px 0;
                padding: 10px;
                border-radius: 5px;
            }
            .user { background: #e3f2fd; text-align: right; }
            .assistant { background: #f5f5f5; }
            #input-area {
                display: flex;
                gap: 10px;
            }
            #user-input {
                flex: 1;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            button {
                padding: 10px 20px;
                background: #007bff;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }
            button:hover { background: #0056b3; }
            .loading { opacity: 0.6; pointer-events: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>MemOS v2.0 API</h1>
            <p>AI Memory System with RAG Pipeline</p>

            <h2>API Endpoints</h2>

            <div class="endpoint">
                <span class="method post">POST</span>
                <code>/chat</code> - Send a message
            </div>

            <div class="endpoint">
                <span class="method get">GET</span>
                <code>/stats</code> - Get system statistics
            </div>

            <div class="endpoint">
                <span class="method get">GET</span>
                <code>/health</code> - Health check
            </div>

            <div id="chat-box">
                <h2>Test Chat</h2>
                <div id="messages"></div>
                <div id="input-area">
                    <input type="text" id="user-input" placeholder="Type your message..." />
                    <button onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>

        <script>
            const sessionId = 'web-' + Math.random().toString(36).substr(2, 9);

            async function sendMessage() {
                const input = document.getElementById('user-input');
                const messages = document.getElementById('messages');
                const message = input.value.trim();

                if (!message) return;

                // Add user message
                messages.innerHTML += `<div class="message user"><strong>You:</strong> ${escapeHtml(message)}</div>`;
                input.value = '';
                document.body.classList.add('loading');

                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: message,
                            session_id: sessionId
                        })
                    });

                    const data = await response.json();

                    // Add AI response
                    messages.innerHTML += `<div class="message assistant"><strong>MemOS:</strong> ${escapeHtml(data.response)}<br><small>Intent: ${data.intent}</small></div>`;
                } catch (error) {
                    messages.innerHTML += `<div class="message assistant" style="color: red;"><strong>Error:</strong> ${escapeHtml(error.message)}</div>`;
                }

                document.body.classList.remove('loading');
                messages.scrollTop = messages.scrollHeight;
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            // Allow Enter key to send
            document.getElementById('user-input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') sendMessage();
            });
        </script>
    </body>
    </html>
    """


# ============================================================================
# 飞书机器人功能
# ============================================================================

async def get_feishu_token() -> str:
    """获取飞书tenant_access_token"""
    global _token_cache

    now = datetime.now().timestamp()
    if _token_cache["token"] and _token_cache["expire_at"] > now + 60:
        return _token_cache["token"]

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


async def send_feishu_message(chat_id: str, content: str, msg_type: str = "text"):
    """发送消息到飞书"""
    token = await get_feishu_token()

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
        self.msg_type = event_data.get("message", {}).get("msg_type")
        self.content = self._parse_content()

    def _parse_content(self) -> str:
        """解析消息内容"""
        content_str = self.event.get("message", {}).get("content", "{}")
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
        if self.chat_type == "p2p":
            return f"feishu-p2p-{self.sender_open_id}"
        else:
            return f"feishu-group-{self.chat_id}"


async def handle_feishu_message(event_data: Dict):
    """处理收到的飞书消息"""
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


@app.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    """
    飞书事件回调入口
    需要在飞书开发者后台配置此URL
    """
    body = await request.body()
    body_str = body.decode('utf-8')

    try:
        data = json.loads(body_str)
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 处理URL验证（首次配置回调时）
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # 验证token
    if FEISHU_VERIFICATION_TOKEN:
        if data.get("token") != FEISHU_VERIFICATION_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid token")

    # 处理事件
    event_type = data.get("header", {}).get("event_type")

    if event_type == "im.message.receive_v1":
        # 异步处理消息，避免超时
        asyncio.create_task(handle_feishu_message(data.get("event", {})))

    return JSONResponse({"code": 0})


@app.get("/feishu/health")
async def feishu_health_check():
    """飞书机器人健康检查"""
    return {
        "status": "ok",
        "service": "feishu-bot",
        "app_id_configured": bool(FEISHU_APP_ID),
        "app_secret_configured": bool(FEISHU_APP_SECRET)
    }


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 9000))  # 使用 9000 避免冲突
    print(f"Starting server on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
