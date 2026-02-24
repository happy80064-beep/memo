"""
MemOS Web API - Multimodal Version with File Upload Support
支持图片、PDF、文档上传和转录
"""

import os
import uuid
import shutil
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from graph import chat, get_graph
from perception import process_attachment
from supabase import create_client

load_dotenv()

# 创建上传目录
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ============================================================================
# Pydantic Models
# ============================================================================

class ChatRequest(BaseModel):
    """Chat request model"""
    message: str = Field(default="", description="User message", min_length=0)
    session_id: str = Field(default="default", description="Unique session ID")
    attachments: Optional[List[dict]] = Field(default=None, description="Attachments")


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str = Field(..., description="AI response")
    intent: str = Field(..., description="Detected intent (CHAT/WORK)")
    metadata: dict = Field(..., description="Response metadata")
    attachments_processed: List[dict] = Field(default=[], description="Processed attachments")


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
    print("=" * 60)
    print("MemOS Multimodal Web API Starting...")
    print("=" * 60)
    print(f"Upload directory: {UPLOAD_DIR.absolute()}")

    # Pre-load the graph to avoid cold start
    get_graph()
    print("[OK] Graph initialized")
    print("[OK] Multimodal support enabled (Images, PDF, Audio)")

    yield

    print("Shutting down...")


app = FastAPI(
    title="MemOS Multimodal API",
    description="AI Memory System with RAG pipeline and Multimodal Support",
    version="2.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount uploads directory for serving files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ============================================================================
# Helper Functions
# ============================================================================

def get_mime_type(filename: str) -> str:
    """Get MIME type from filename"""
    ext = Path(filename).suffix.lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.txt': 'text/plain',
        '.mp3': 'audio/mpeg',
        '.mp4': 'video/mp4',
        '.wav': 'audio/wav',
    }
    return mime_types.get(ext, 'application/octet-stream')


# ============================================================================
# API Endpoints
# ============================================================================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Text-only chat endpoint"""
    try:
        result = await chat(
            user_input=request.message,
            session_id=request.session_id,
            attachments=request.attachments
        )

        return ChatResponse(
            response=result["response"],
            intent=result["intent"],
            metadata=result["metadata"],
            attachments_processed=[]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/with-files")
async def chat_with_files(
    message: str = Form(default=""),
    session_id: str = Form(default="default"),
    files: List[UploadFile] = File(default=[])
):
    """
    Chat with file upload support

    Supports:
    - Images (jpg, png, gif, webp)
    - Documents (pdf, doc, docx, txt)
    - Audio (mp3, wav) - partial support
    """
    try:
        attachments = []
        processed_attachments = []

        # Process uploaded files
        for file in files:
            if not file.filename:
                continue

            # Generate unique filename
            file_id = str(uuid.uuid4())[:8]
            ext = Path(file.filename).suffix
            new_filename = f"{file_id}{ext}"
            file_path = UPLOAD_DIR / new_filename

            # Save file
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            # Get MIME type
            mime_type = get_mime_type(file.filename)

            # Create file URL
            file_url = f"/uploads/{new_filename}"

            attachments.append({
                "url": str(file_path.absolute()),
                "mime_type": mime_type,
                "original_name": file.filename
            })

            processed_attachments.append({
                "filename": file.filename,
                "mime_type": mime_type,
                "saved_as": new_filename,
                "url": file_url
            })

        # Call chat with attachments
        result = await chat(
            user_input=message or "I've uploaded some files for you to analyze.",
            session_id=session_id,
            attachments=attachments if attachments else None
        )

        return ChatResponse(
            response=result["response"],
            intent=result["intent"],
            metadata=result["metadata"],
            attachments_processed=processed_attachments
        )

    except Exception as e:
        import traceback
        print(f"Error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get system statistics"""
    try:
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
        "service": "memos-multimodal",
        "timestamp": datetime.utcnow().isoformat(),
        "features": ["text", "image", "pdf", "doc"]
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with multimodal HTML interface"""
    # 读取外部 chat.html 文件
    try:
        with open("chat.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MemOS v2.1 - Multimodal AI Memory System</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                font-size: 28px;
                margin-bottom: 10px;
            }
            .header p {
                opacity: 0.9;
                font-size: 14px;
            }
            .features {
                display: flex;
                justify-content: center;
                gap: 15px;
                margin-top: 15px;
                flex-wrap: wrap;
            }
            .feature-tag {
                background: rgba(255,255,255,0.2);
                padding: 5px 12px;
                border-radius: 15px;
                font-size: 12px;
            }
            .chat-container {
                padding: 20px;
                height: 500px;
                overflow-y: auto;
                background: #f8f9fa;
            }
            .message {
                margin-bottom: 20px;
                max-width: 80%;
                animation: fadeIn 0.3s ease;
            }
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .message.user {
                margin-left: auto;
                text-align: right;
            }
            .message-bubble {
                display: inline-block;
                padding: 15px 20px;
                border-radius: 20px;
                font-size: 15px;
                line-height: 1.5;
                text-align: left;
            }
            .message.user .message-bubble {
                background: #667eea;
                color: white;
                border-bottom-right-radius: 4px;
            }
            .message.assistant .message-bubble {
                background: white;
                color: #333;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            .file-attachment {
                background: rgba(255,255,255,0.2);
                padding: 8px 12px;
                border-radius: 10px;
                margin-top: 8px;
                font-size: 13px;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .input-area {
                padding: 20px;
                background: white;
                border-top: 1px solid #eee;
            }
            .file-upload {
                margin-bottom: 15px;
            }
            .file-upload input[type="file"] {
                display: none;
            }
            .file-upload-label {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 10px 20px;
                background: #f0f0f0;
                border-radius: 10px;
                cursor: pointer;
                font-size: 14px;
                transition: all 0.2s;
            }
            .file-upload-label:hover {
                background: #e0e0e0;
            }
            .selected-files {
                margin-top: 10px;
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }
            .file-tag {
                background: #e3f2fd;
                color: #1976d2;
                padding: 5px 12px;
                border-radius: 15px;
                font-size: 12px;
                display: flex;
                align-items: center;
                gap: 5px;
            }
            .file-tag button {
                background: none;
                border: none;
                color: #1976d2;
                cursor: pointer;
                font-size: 14px;
            }
            .text-input-row {
                display: flex;
                gap: 10px;
            }
            #message-input {
                flex: 1;
                padding: 15px 20px;
                border: 2px solid #e0e0e0;
                border-radius: 30px;
                font-size: 15px;
                outline: none;
                transition: border-color 0.3s;
            }
            #message-input:focus {
                border-color: #667eea;
            }
            #send-btn {
                padding: 15px 30px;
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 30px;
                font-size: 15px;
                cursor: pointer;
                transition: all 0.2s;
            }
            #send-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
            }
            #send-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }
            .typing-indicator {
                display: none;
                padding: 15px 20px;
            }
            .typing-indicator.active {
                display: block;
            }
            .typing-dots {
                display: inline-flex;
                gap: 5px;
            }
            .typing-dot {
                width: 8px;
                height: 8px;
                background: #999;
                border-radius: 50%;
                animation: typing 1.4s infinite;
            }
            .typing-dot:nth-child(2) { animation-delay: 0.2s; }
            .typing-dot:nth-child(3) { animation-delay: 0.4s; }
            @keyframes typing {
                0%, 60%, 100% { transform: translateY(0); }
                30% { transform: translateY(-10px); }
            }
            .empty-state {
                text-align: center;
                padding: 60px 20px;
                color: #999;
            }
            .empty-state-icon {
                font-size: 48px;
                margin-bottom: 20px;
            }
            .image-preview {
                max-width: 200px;
                max-height: 150px;
                border-radius: 10px;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MemOS v2.1</h1>
                <p>AI Memory System with Multimodal Support</p>
                <div class="features">
                    <span class="feature-tag">📝 Text</span>
                    <span class="feature-tag">🖼️ Images</span>
                    <span class="feature-tag">📄 PDF</span>
                    <span class="feature-tag">📎 Docs</span>
                </div>
            </div>

            <div class="chat-container" id="chat-container">
                <div class="empty-state">
                    <div class="empty-state-icon">🧠</div>
                    <p>Start a conversation with MemOS</p>
                    <p style="font-size: 12px; margin-top: 10px;">
                        You can upload images, PDFs, or documents for analysis.
                    </p>
                </div>
            </div>

            <div class="typing-indicator" id="typing-indicator">
                <div class="message assistant">
                    <div class="message-bubble">
                        <div class="typing-dots">
                            <div class="typing-dot"></div>
                            <div class="typing-dot"></div>
                            <div class="typing-dot"></div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="input-area">
                <div class="file-upload">
                    <label for="file-input" class="file-upload-label">
                        📎 Attach Files (Images, PDF, DOC)
                    </label>
                    <input type="file" id="file-input" multiple
                           accept=".jpg,.jpeg,.png,.gif,.pdf,.doc,.docx,.txt">
                    <div class="selected-files" id="selected-files"></div>
                </div>

                <div class="text-input-row">
                    <input type="text" id="message-input"
                           placeholder="Type your message or just send files...">
                    <button id="send-btn">Send</button>
                </div>
            </div>
        </div>

        <script>
            const sessionId = 'multimodal-' + Math.random().toString(36).substr(2, 9);
            const chatContainer = document.getElementById('chat-container');
            const messageInput = document.getElementById('message-input');
            const sendBtn = document.getElementById('send-btn');
            const fileInput = document.getElementById('file-input');
            const selectedFiles = document.getElementById('selected-files');
            const typingIndicator = document.getElementById('typing-indicator');

            let currentFiles = [];

            // File selection handler
            fileInput.addEventListener('change', (e) => {
                currentFiles = Array.from(e.target.files);
                updateFileDisplay();
            });

            function updateFileDisplay() {
                selectedFiles.innerHTML = '';
                currentFiles.forEach((file, index) => {
                    const tag = document.createElement('div');
                    tag.className = 'file-tag';
                    tag.innerHTML = `
                        ${getFileIcon(file.type)} ${file.name}
                        <button onclick="removeFile(${index})">×</button>
                    `;
                    selectedFiles.appendChild(tag);
                });
            }

            function getFileIcon(mimeType) {
                if (mimeType.startsWith('image/')) return '🖼️';
                if (mimeType.includes('pdf')) return '📄';
                if (mimeType.includes('word') || mimeType.includes('document')) return '📝';
                return '📎';
            }

            function removeFile(index) {
                currentFiles.splice(index, 1);
                updateFileDisplay();
            }

            function addMessage(role, content, files = []) {
                const emptyState = chatContainer.querySelector('.empty-state');
                if (emptyState) emptyState.remove();

                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;

                let fileHtml = '';
                if (files.length > 0) {
                    fileHtml = '<div style="margin-top: 8px;">' +
                        files.map(f => `<div class="file-attachment">📎 ${f.filename}</div>`).join('') +
                        '</div>';
                }

                messageDiv.innerHTML = `
                    <div class="message-bubble">
                        ${content}
                        ${fileHtml}
                    </div>
                `;

                chatContainer.appendChild(messageDiv);
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }

            async function sendMessage() {
                const message = messageInput.value.trim();

                if (!message && currentFiles.length === 0) return;

                // Add user message
                addMessage('user', message || '[Files]', currentFiles.map(f => ({filename: f.name})));
                messageInput.value = '';

                // Show typing
                sendBtn.disabled = true;
                typingIndicator.classList.add('active');

                try {
                    let response;

                    if (currentFiles.length > 0) {
                        // Send with files
                        const formData = new FormData();
                        formData.append('message', message);
                        formData.append('session_id', sessionId);
                        currentFiles.forEach(file => formData.append('files', file));

                        response = await fetch('/chat/with-files', {
                            method: 'POST',
                            body: formData
                        });

                        currentFiles = [];
                        updateFileDisplay();
                        fileInput.value = '';
                    } else {
                        // Text only
                        response = await fetch('/chat', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({message, session_id: sessionId})
                        });
                    }

                    const data = await response.json();

                    typingIndicator.classList.remove('active');
                    addMessage('assistant', data.response);

                } catch (error) {
                    typingIndicator.classList.remove('active');
                    addMessage('assistant', 'Sorry, an error occurred: ' + error.message);
                }

                sendBtn.disabled = false;
                messageInput.focus();
            }

            sendBtn.addEventListener('click', sendMessage);
            messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') sendMessage();
            });
        </script>
    </body>
    </html>
    """


# ============================================================================
# Feishu Bot Integration
# ============================================================================

import json
import hmac
import hashlib
import base64
import httpx

# 飞书配置
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

_token_cache = {"token": None, "expire_at": 0}

async def get_feishu_token() -> str:
    """获取飞书tenant_access_token"""
    global _token_cache
    import time
    now = time.time()
    if _token_cache["token"] and _token_cache["expire_at"] > now + 60:
        return _token_cache["token"]

    url = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET
        })
        data = resp.json()
        if data.get("code") == 0:
            _token_cache["token"] = data["tenant_access_token"]
            _token_cache["expire_at"] = now + data["expire"]
            return _token_cache["token"]
    return ""

async def send_feishu_reply(chat_id: str, text: str):
    """发送回复到飞书"""
    if not FEISHU_APP_ID:
        return
    token = await get_feishu_token()
    if not token:
        return

    url = f"{FEISHU_BASE_URL}/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text})
    }

    async with httpx.AsyncClient() as client:
        await client.post(url, headers=headers, params={"receive_id_type": "chat_id"}, json=payload)

@app.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    """飞书事件回调"""
    body = await request.body()
    data = json.loads(body.decode('utf-8'))

    # URL验证
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # Token验证（添加调试日志）
    received_token = data.get("token")
    if FEISHU_VERIFICATION_TOKEN and received_token != FEISHU_VERIFICATION_TOKEN:
        print(f"[DEBUG] Token mismatch!")
        print(f"[DEBUG] Expected: {FEISHU_VERIFICATION_TOKEN[:10]}...")
        print(f"[DEBUG] Received: {received_token[:10] if received_token else 'None'}...")
        raise HTTPException(status_code=401)

    # 处理消息事件
    event_type = data.get("header", {}).get("event_type")
    if event_type == "im.message.receive_v1":
        event = data.get("event", {})
        message = event.get("message", {})
        chat_type = message.get("chat_type")
        chat_id = message.get("chat_id")

        # 解析消息内容
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "")

        # 生成session_id
        sender = event.get("sender", {}).get("sender_id", {})
        open_id = sender.get("open_id", "")
        session_id = f"feishu-p2p-{open_id}" if chat_type == "p2p" else f"feishu-group-{chat_id}"

        print(f"[Feishu] 收到: {text[:50]}... 会话: {session_id}")

        # 调用MemOS生成回复
        try:
            result = await chat(user_input=text, session_id=session_id)
            response_text = result.get("response", "抱歉，处理失败")

            # 发送回复
            await send_feishu_reply(chat_id, response_text)
            print(f"[Feishu] 回复已发送")
        except Exception as e:
            print(f"[ERROR] Feishu处理失败: {e}")

    return {"code": 0}


@app.get("/feishu/health")
async def feishu_health_check():
    """飞书机器人健康检查"""
    return {
        "status": "ok",
        "service": "feishu-bot",
        "app_id_configured": bool(FEISHU_APP_ID),
        "app_secret_configured": bool(FEISHU_APP_SECRET),
        "verification_token_configured": bool(FEISHU_VERIFICATION_TOKEN)
    }


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    import time
    import sys

    port = int(os.getenv("PORT", 8000))
    print(f"[STARTUP] Port: {port}", flush=True)
    print(f"[STARTUP] Starting Multimodal Server on http://0.0.0.0:{port}", flush=True)

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=True,
            loop="asyncio"
        )
    except Exception as e:
        print(f"[ERROR] Server crashed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
