#!/bin/bash
# MemOS 云服务器一键部署脚本
# 在阿里云/腾讯云 Ubuntu 服务器上运行

set -e

echo "=========================================="
echo "MemOS v2.0 - 云服务器部署"
echo "=========================================="

# 更新系统
echo "[1/7] 更新系统..."
apt update && apt upgrade -y

# 安装 Python
echo "[2/7] 安装 Python..."
apt install -y python3 python3-pip python3-venv

# 安装 Docker（可选）
echo "[3/7] 安装 Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $USER
    systemctl enable docker
    systemctl start docker
fi

# 创建应用目录
echo "[4/7] 创建应用目录..."
mkdir -p /opt/memos
mkdir -p /var/log/memos

# 进入目录
cd /opt/memos

# 创建虚拟环境
echo "[5/7] 创建 Python 虚拟环境..."
python3 -m venv venv
source venv/bin/activate

# 安装依赖
echo "[6/7] 安装依赖..."
pip install -q supabase langchain-openai python-dotenv requests

# 创建 .env 文件（需要手动修改）
echo "[7/7] 创建配置文件..."
cat > /opt/memos/.env << 'EOF'
# 请修改以下配置
SYSTEM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
SYSTEM_API_KEY=your_gemini_api_key
SYSTEM_MODEL=gemini-2.5-flash
SYSTEM_TEMPERATURE=0.3

USER_BASE_URL=https://api.moonshot.cn/v1
USER_API_KEY=your_moonshot_api_key
USER_MODEL=kimi-k2-5
USER_TEMPERATURE=0.7

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

APP_ENV=production
LOG_LEVEL=INFO
EOF

echo ""
echo "=========================================="
echo "基础安装完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 编辑配置文件: nano /opt/memos/.env"
echo "2. 上传 Python 脚本到 /opt/memos/"
echo "3. 运行: bash /opt/memos/install-service.sh"
echo ""
