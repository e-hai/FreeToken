#!/bin/bash
# ==============================================================================
# DeepSeek-Harness 环境变量配置
# 将所有评测与大模型调用自动重定向至本地网关 (127.0.0.1:8000)
# ==============================================================================

export OPENAI_API_BASE="http://127.0.0.1:8000/v1"
export OPENAI_BASE_URL="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="free-token"

echo "✅ DeepSeek-Harness 环境变量已生效！"
echo "👉 OPENAI_API_BASE = $OPENAI_API_BASE"
echo "👉 OPENAI_API_KEY  = $OPENAI_API_KEY"
