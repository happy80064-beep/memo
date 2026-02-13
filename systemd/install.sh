#!/bin/bash
# MemOS Systemd Service 安装脚本

set -e

echo "=== MemOS Systemd Service 安装 ==="

# 检查权限
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行"
    exit 1
fi

# 创建用户
if ! id -u memos &>/dev/null; then
    useradd -r -s /bin/false -d /opt/memos memos
    echo "创建用户: memos"
fi

# 创建目录
mkdir -p /opt/memos
mkdir -p /var/log/memos

# 复制文件
cp -r ../*.py /opt/memos/
cp ../.env /opt/memos/
cp ../requirements.txt /opt/memos/ 2>/dev/null || echo "注意: requirements.txt 不存在"

# 设置权限
chown -R memos:memos /opt/memos
chmod 600 /opt/memos/.env

echo "安装依赖..."
cd /opt/memos
python3 -m venv venv
source venv/bin/activate
pip install -q supabase langchain-openai python-dotenv requests

# 复制 service 文件
cp memos-extractor.service /etc/systemd/system/
cp memos-compiler.service /etc/systemd/system/

# 重载 systemd
systemctl daemon-reload

# 启用服务
systemctl enable memos-extractor.service
systemctl enable memos-compiler.service

echo ""
echo "=== 安装完成 ==="
echo "启动服务:"
echo "  sudo systemctl start memos-extractor"
echo "  sudo systemctl start memos-compiler"
echo ""
echo "查看状态:"
echo "  sudo systemctl status memos-extractor"
echo "  sudo systemctl status memos-compiler"
echo ""
echo "查看日志:"
echo "  sudo journalctl -u memos-extractor -f"
echo "  sudo journalctl -u memos-compiler -f"
