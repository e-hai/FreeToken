#!/bin/bash
set -e

echo "========================================================"
echo "🚀 方案一：一键启动本地免注册、免Key推理引擎 (Ollama + DeepSeek-R1)"
echo "========================================================"

# 1. 检查 Ollama 是否安装
if ! command -v ollama &> /dev/null; then
    echo "[1/3] 检测到未安装 Ollama，正在通过 Homebrew 自动安装..."
    if command -v brew &> /dev/null; then
        brew install ollama
    else
        echo "正在直接下载安装 Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
    fi
else
    echo "[1/3] ✅ Ollama 已就绪"
fi

# 2. 后台启动 Ollama 服务
echo "[2/3] 正在启动 Ollama 后台服务..."
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
fi

# 3. 自动拉取 DeepSeek-R1 蒸馏模型 (轻量高速版)
echo "[3/3] 正在拉取 DeepSeek-R1 模型 (约 1.1GB，首次运行需下载)..."
ollama pull deepseek-r1:1.5b

echo ""
echo "========================================================"
echo "🎉 本地大模型已成功运行！"
echo "👉 OpenAI 兼容接口地址: http://127.0.0.1:11434/v1"
echo "👉 API Key: (无需Key，填任意字符如 'ollama' 即可)"
echo "👉 模型名称: deepseek-r1:1.5b (也可随时运行 ollama pull deepseek-r1:7b)"
echo "========================================================"
echo "正在启动 DeepSeek Harness Web 界面..."
echo "打开浏览器进入 http://127.0.0.1:3080 即可直接使用！"
echo "========================================================"

npx @deepseek-ai/dsh web
