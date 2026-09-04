#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 1. 检查 Python 虚拟环境
if [ ! -d ".venv" ]; then
    echo "[1/3] 📦 正在创建 Python 虚拟环境并安装依赖..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install fastapi uvicorn httpx pyyaml
else
    source .venv/bin/activate
fi

# 2. 检查配置文件
if [ ! -f "config.yaml" ] && [ -f "config.example.yaml" ]; then
    echo "📋 检测到本地尚未生成配置，正在从 config.example.yaml 创建 config.yaml..."
    cp config.example.yaml config.yaml
fi

# 处理命令行参数
if [ "$1" == "--test" ]; then
    echo "🧪 正在执行自动化测试套件..."
    python3 test_gateway.py
    exit 0
fi

echo "=========================================================================="
echo "⚡ Free Token 聚合网关与自动故障转移系统"
echo "=========================================================================="
echo "👉 本地 OpenAI 兼容端点 : http://127.0.0.1:8000/v1"
echo "👉 网页可视化仪表盘     : http://127.0.0.1:8000/"
echo "👉 配置文件             : $DIR/config.yaml"
echo "=========================================================================="
echo "💡 快速命令："
echo "   • 运行自检与故障转移测试    :  ./start_gateway.sh --test"
echo "=========================================================================="
echo "🔌 接入 DeepSeek-Harness 配置指南："
echo "   1. 运行 npx @deepseek-ai/dsh web 启动 Harness"
echo "   2. 在 Settings -> Models 中添加自定义 Provider："
echo "      - Base URL: http://127.0.0.1:8000/v1"
echo "      - API Key : 任意填写（如 free-token）"
echo "      - Model   : deepseek-v4-pro, deepseek-v4-flash, deepseek-r1"
echo "=========================================================================="
echo "正在启动网关服务 (按 Ctrl+C 可停止)..."
echo ""

python3 gateway.py
