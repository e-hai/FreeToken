#!/bin/bash
# ==============================================================================
# DeepSeek-Harness 一键执行脚本
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# 1. 注入环境变量
source ./harness_env.sh

# 2. 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 3. 运行评测套件
python3 run_harness_eval.py "$@"
