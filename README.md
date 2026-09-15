# ⚡ Free Token 聚合网关与自动负载均衡系统

专为 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 及各类 OpenAI SDK 客户端设计的 **多渠道免费大模型聚合网关与高可用调度中心**。

---

## 🚀 快速开始 (一键启动)

```bash
./start_gateway.sh
```

单一脚本自动拉起并守护所有服务：

| 服务 | 地址 | 说明 |
| :--- | :--- | :--- |
| **聚合网关 API** | `http://127.0.0.1:8000/v1` | 标准 OpenAI 兼容接口，支持流式 SSE |
| **Web 可视化仪表盘** | `http://127.0.0.1:8000/` | 查看各渠道健康度、实时切换渠道与更新 Key |
| **DeepSeek-Harness** | `http://127.0.0.1:3080/` | AI Agent 交互界面（自动对接网关与实时搜索） |

> 💡 按 `Ctrl+C` 自动安全关闭所有子进程并释放端口。

---

## 📁 项目目录结构

```text
free-token/
├── start_gateway.sh       # 🚀 一键启动器 (网关 + Harness + 自动清理)
├── config.example.yaml    # ⚙️ 渠道商配置模板
├── config.yaml            # 🔑 本地运行时配置 (填入你的 API Key)
├── AGENTS.md              # 🤖 Agent 视觉与浏览器 MCP 协同规范
├── README.md              # 📖 项目说明
│
├── src/                   # 📦 网关核心源码
│   └── gateway.py         # 聚合路由、单渠道天梯轮询、Web 仪表盘、实时检索
│
├── tests/                 # 🧪 自动化测试套件
│   ├── test_gateway.py    # 功能与故障转移端到端测试 (7 项全通)
│   └── test_keyless.py    # 免 Key 海外公共节点连通测试
│
├── harness/               # 🔌 DeepSeek-Harness 适配与评测
│   ├── harness_env.sh     # 环境变量重定向 (API 与搜索拦截)
│   ├── harness_config.yaml# Harness 评测参数
│   ├── run_harness.sh     # 评测启动脚本
│   └── run_harness_eval.py# 评测执行逻辑
│
├── tools/                 # 🛠️ 辅助工具与外挂
│   ├── vision_mcp.py      # 视觉多模态 MCP 服务 & CLI (Gemini 驱动)
│   └── run_ollama.sh      # 本地 Ollama 启动脚本
│
└── skills/                # 🧠 Agent Skills 库
    └── vision/            # 视觉感知外挂 Skill
```

---

## ⚙️ 常用命令

```bash
# 1. 启动全套服务 (网关 + Harness Web)
./start_gateway.sh

# 2. 运行自动化全套自检测试 (7 项功能与故障转移测试)
./start_gateway.sh --test

# 3. 独立调用视觉外挂 (分析 UI、OCR 提取报错)
python3 tools/vision_mcp.py "error.png" "请提取图中所有报错堆栈与行号"

# 4. 执行 Harness 基准评测
cd harness && ./run_harness.sh
```

---

## 🌟 核心特性速览

- **多渠道天梯容灾**：NVIDIA NIM、Groq、Cloudflare、SiliconFlow 等 10+ 渠道聚合，单个渠道模型全挂后自动顺滑晋级下一个渠道，报错秒级熔断。
- **内置零成本实时搜索**：原生拦截 Harness `web_search`，由 Headless Chrome / DuckDuckGo 实时抓取，免付费 Key、无调用限制。
- **挂载 Chrome DevTools MCP**：支持 Agent 操作真实 Chrome 浏览器打开页面、点击链接、阅读长文。
- **专属视觉解耦外挂**：主 Agent 专注写代码，视觉交给 Gemini 3.8/3.5 Flash 提取 OCR 与 UI 坐标。

