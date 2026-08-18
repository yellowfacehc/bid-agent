#!/bin/bash
# ============================================
# 招投标信息查询平台 - 一键部署脚本
# ============================================
# 用法: 在项目根目录执行 bash deploy.sh
# ============================================

set -e

echo "========================================"
echo "  招投标信息查询平台 - 部署脚本"
echo "========================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python3，请先安装 Python 3.10+"
    exit 1
fi

echo "[1/4] 安装依赖包..."
pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt

echo ""
echo "[2/4] 初始化 Git 仓库..."
if [ ! -d .git ]; then
    git init
    git add .
    git commit -m "招投标信息查询平台初始版本"
    echo ""
    echo "Git 仓库已初始化并提交。"
else
    echo "Git 仓库已存在。"
fi

echo ""
echo "[3/4] 本地测试启动..."
echo "正在启动应用，请访问 http://localhost:5000"
echo "按 Ctrl+C 停止"
echo ""

python3 app.py
