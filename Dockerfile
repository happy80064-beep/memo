# MemOS v2.0 - Unified Dockerfile
# 支持 Web 服务和调度器两种模式
# 通过 Zeabur 控制台设置不同的 Start Command 来区分

FROM python:3.11-slim

WORKDIR /app

# 安装完整依赖（Web和调度器共用）
RUN pip install --no-cache-dir \
    supabase>=2.0.0 \
    langchain>=0.3.0 \
    langchain-openai>=0.2.0 \
    openai>=1.0.0 \
    fastapi>=0.100.0 \
    uvicorn>=0.30.0 \
    python-dotenv>=1.0.0 \
    requests>=2.31.0 \
    pydantic>=2.0.0 \
    PyPDF2>=3.0.0 \
    python-docx>=1.1.0 \
    langgraph>=0.2.0

# 复制应用代码
COPY *.py .
COPY *.html .

# 注意：.env 不复制，环境变量从 Zeabur 平台读取

# 默认命令（调度器模式）
# 在 Zeabur 控制台可以覆盖为：uvicorn web_app_multimodal:app --host 0.0.0.0 --port 8000
CMD ["python", "zeabur-scheduler.py"]
