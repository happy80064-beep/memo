#!/bin/bash
# 安装 Systemd 服务

set -e

cd /opt/memos

# 创建提取器服务
cat > /etc/systemd/system/memos-extractor.service << 'EOF'
[Unit]
Description=MemOS Batch Extractor Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/memos
Environment=PATH=/opt/memos/venv/bin
EnvironmentFile=/opt/memos/.env
ExecStart=/opt/memos/venv/bin/python batch_extractor.py
Restart=always
RestartSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 创建编译器服务
cat > /etc/systemd/system/memos-compiler.service << 'EOF'
[Unit]
Description=MemOS Compiler Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/memos
Environment=PATH=/opt/memos/venv/bin
EnvironmentFile=/opt/memos/.env
ExecStart=/opt/memos/venv/bin/python compiler.py
Restart=always
RestartSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 重载 systemd
systemctl daemon-reload

# 启用服务
systemctl enable memos-extractor.service
systemctl enable memos-compiler.service

# 启动服务
systemctl start memos-extractor.service
systemctl start memos-compiler.service

echo "=========================================="
echo "服务已安装并启动！"
echo "=========================================="
echo ""
echo "管理命令："
echo "  查看状态: systemctl status memos-extractor"
echo "  查看日志: journalctl -u memos-extractor -f"
echo "  重启服务: systemctl restart memos-extractor"
echo "  停止服务: systemctl stop memos-extractor"
echo ""
