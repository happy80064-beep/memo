"""
MemOS Web API - FastAPI Interface for Conversations
Deploy this to Zeabur to get a chat API endpoint
"""

import os
import asyncio
from typing import List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from graph import chat, get_graph
from supabase import create_client

load_dotenv()


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
# Run
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 9000))  # 使用 9000 避免冲突
    print(f"Starting server on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
