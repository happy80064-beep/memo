FROM python:3.11-slim

WORKDIR /app

# 安装依赖
RUN pip install --no-cache-dir \
    supabase \
    langchain-openai \
    python-dotenv \
    requests

# 复制应用代码
COPY *.py .
COPY .env .

# 默认命令 (可被覆盖)
CMD ["python", "batch_extractor.py"]
