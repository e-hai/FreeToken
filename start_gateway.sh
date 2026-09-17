#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# ==================== 1. Python 虚拟环境 ====================
if [ ! -d ".venv" ]; then
    echo "[1/3] 📦 正在创建 Python 虚拟环境并安装依赖..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install fastapi uvicorn httpx pyyaml beautifulsoup4 playwright
    echo "[2/3] 🌐 正在安装 Headless Chromium 浏览器 (用于 Google 实时搜索)..."
    playwright install chromium
else
    source .venv/bin/activate
fi

# ==================== 2. 配置文件 ====================
if [ ! -f "config.yaml" ] && [ -f "config.example.yaml" ]; then
    echo "📋 检测到本地尚未生成配置，正在从 config.example.yaml 创建 config.yaml..."
    cp config.example.yaml config.yaml
fi

# ==================== 3. 处理命令行参数 ====================
if [ "$1" == "--test" ]; then
    echo "🧪 正在执行自动化测试套件..."
    python3 tests/test_gateway.py
    exit 0
fi

# ==================== 4. 注入 Harness 环境变量 ====================
source "$DIR/harness/harness_env.sh"

# ==================== 5. 进程管理与自动清理 ====================
GATEWAY_PID=""
HARNESS_PID=""

cleanup() {
    echo ""
    echo "🛑 正在优雅关闭所有服务..."
    [ -n "$HARNESS_PID" ] && kill "$HARNESS_PID" 2>/dev/null && echo "   ↳ DeepSeek-Harness (PID $HARNESS_PID) 已停止"
    [ -n "$GATEWAY_PID" ] && kill "$GATEWAY_PID" 2>/dev/null && echo "   ↳ Free Token 网关   (PID $GATEWAY_PID) 已停止"
    # 确保端口释放
    lsof -ti :8000 -ti :8001 -ti :3080 2>/dev/null | xargs kill -9 2>/dev/null || true
    echo "👋 所有服务已关闭，再见！"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# ==================== 6. 启动网关服务 (后台) ====================
echo "=========================================================================="
echo "⚡ Free Token 双轨聚合网关 (Harness & Codex) + DeepSeek 一体化启动器"
echo "=========================================================================="
echo "👉 DeepSeek Harness & 控制台 : http://127.0.0.1:8000/ (API: /v1)"
echo "👉 ChatGPT Codex CLI 专区    : http://127.0.0.1:8001/v1 (Wire: responses)"
echo "👉 DeepSeek-Harness Web      : http://127.0.0.1:3080/"
echo "👉 实时免费网页检索引擎      : http://127.0.0.1:8000/anthropic/v1/messages"
echo "👉 独立配置文件              : $DIR/config.harness.yaml & config.codex.yaml"
echo "=========================================================================="
echo ""

echo "🚀 [1/2] 正在启动 Free Token 双轨网关 (端口 8000 & 8001)..."
python3 src/gateway.py &
GATEWAY_PID=$!

# 等待网关服务就绪 (最多 15 秒)
echo "⏳ 等待网关服务就绪..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8000/v1/models > /dev/null 2>&1; then
        echo "✅ 网关服务已就绪！(耗时 ${i}×0.5s)"
        break
    fi
    if ! kill -0 "$GATEWAY_PID" 2>/dev/null; then
        echo "❌ 网关进程异常退出，请检查 gateway.py 日志"
        exit 1
    fi
    sleep 0.5
done

# 最终确认
if ! curl -s http://127.0.0.1:8000/v1/models > /dev/null 2>&1; then
    echo "❌ 网关服务在 15 秒内未响应，请手动检查"
    exit 1
fi

# ==================== 7. 自动启动 DeepSeek-Harness Web (后台) ====================
echo ""
echo "🚀 [2/2] 正在自动启动 DeepSeek-Harness Web (端口 3080)..."
npx @deepseek-ai/dsh web &
HARNESS_PID=$!

# 等待 Harness 就绪 (最多 20 秒)
echo "⏳ 等待 DeepSeek-Harness Web 就绪..."
for i in $(seq 1 40); do
    if curl -s http://127.0.0.1:3080 > /dev/null 2>&1; then
        echo "✅ DeepSeek-Harness Web 已就绪！(耗时 ${i}×0.5s)"
        break
    fi
    if ! kill -0 "$HARNESS_PID" 2>/dev/null; then
        echo "⚠️ DeepSeek-Harness 进程异常退出，网关仍正常运行"
        HARNESS_PID=""
        break
    fi
    sleep 0.5
done

# ==================== 8. 一体化运行状态 ====================
echo ""
echo "=========================================================================="
echo "🎉 所有服务已成功启动！"
echo "=========================================================================="
echo "   ✅ Free Token 网关    → http://127.0.0.1:8000/   (PID: $GATEWAY_PID)"
[ -n "$HARNESS_PID" ] && \
echo "   ✅ DeepSeek-Harness   → http://127.0.0.1:3080/   (PID: $HARNESS_PID)"
echo "=========================================================================="
echo "💡 按 Ctrl+C 可同时停止所有服务"
echo "=========================================================================="
echo ""

# 前台等待，保持脚本存活直到用户 Ctrl+C
wait
