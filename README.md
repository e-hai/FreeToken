# Free Token 聚合网关与自动负载均衡系统

专为 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 及各类 OpenAI SDK 客户端设计的 **多渠道免费 Token 聚合网关与高可用负载均衡池**。

---

## 🌟 核心特性

1. **多渠道无缝聚合**：预置了 **硅基流动、OhMyGPT、AIHubMix、OpenRouter、DeepInfra、SambaNova、Google AI Studio、NVIDIA NIM** 等主流大模型免费渠道。
2. **智能别名路由**：支持将客户端传入的 `deepseek-v4`、`deepseek-v4-pro`、`deepseek-r1` 等标准模型名自动映射为各上游服务商的具体模型。
3. **自动熔断与无感故障转移 (Failover)**：当某个渠道的免费额度用尽 (HTTP 402)、触发限流 (HTTP 429) 或网络报错时，网关在毫秒级内自动切换到备用渠道重试，保障 Agent 调用永不断连。
4. **全流式 SSE 转发**：原生支持流式输出，打字机式实时体验。
5. **实时可视化 Web 仪表盘**：访问 `http://127.0.0.1:8000/` 即可直观查看各渠道状态、调用量、成功率及延迟。
6. **内置免费实时网页搜索**：本地搜索引擎自动拦截 DeepSeek-Harness 的 `web_search` 调用，通过 DuckDuckGo 实时检索全网，零成本、无 API Key 依赖。

---

## 🚀 快速开始

### 一键启动（网关 + DeepSeek-Harness）

```bash
./start_gateway.sh
```

一条命令同时启动两个服务：

| 服务 | 地址 | 说明 |
|------|------|------|
| **Free Token 网关** | `http://127.0.0.1:8000/` | OpenAI 兼容接口 + 可视化仪表盘 |
| **DeepSeek-Harness Web** | `http://127.0.0.1:3080/` | AI Agent 交互界面（自动接入网关） |

启动器会：
1. 先启动网关并等待端口 8000 就绪
2. 自动注入环境变量（搜索路由 + API 转发）后启动 DeepSeek-Harness
3. 按 `Ctrl+C` 时一键优雅关闭所有服务并释放端口

---

### 执行自动化测试

```bash
./start_gateway.sh --test
```

执行包含模型列表、非流式、流式 SSE、模拟渠道故障自动切换及实时网页搜索在内的 7 项全套测试。

---

## ⚙️ 配置渠道 Key (`config.yaml`)

打开 `config.yaml`，将你在各大平台获取的 API Key 填入，并将对应渠道的 `enabled` 改为 `true`：

```yaml
providers:
  # 示例 1：硅基流动 (注册送体验金)
  - name: "SiliconFlow"
    enabled: true
    base_url: "https://api.siliconflow.cn/v1"
    api_key: "sk-xxxxxxxx"
    models:
      - id: "deepseek-v4-pro"
        upstream_model: "deepseek-ai/DeepSeek-V4-Pro"

  # 示例 2：OhMyGPT (免费额度)
  - name: "OhMyGPT"
    enabled: true
    base_url: "https://api.ohmygpt.com/v1"
    api_key: "sk-xxxxxxxx"
    models:
      - id: "deepseek-v4-pro"
        upstream_model: "deepseek-v4-pro"
```

---

## 🔌 接入 DeepSeek-Harness

> **推荐方式**：直接使用 `./start_gateway.sh` 一键启动，无需手动配置。

如需手动接入，在 DeepSeek-Harness 的 **Settings → Models** 中添加自定义 Provider：

| 字段 | 值 |
|------|------|
| Provider ID | `local-gateway` |
| Base URL | `http://127.0.0.1:8000/v1` |
| API Key | 任意填写（如 `free-token`） |
| Model | `deepseek-v4-pro` / `deepseek-v4-flash` / `deepseek-r1` |

---

## 🔍 内置网页搜索 (Chrome 驱动)

网关内置了基于 **Headless Chrome (Playwright CDP)** 的实时网页搜索引擎，自动拦截 DeepSeek-Harness Agent 的 `web_search` 工具调用：

- **Chrome 驱动 Google 搜索**：通过 Playwright 启动 Headless Chromium，直接访问 Google 搜索并提取结构化结果，支持 JS 渲染和完整的搜索质量
- **智能降级兜底**：当 Chrome/Google 不可用时，自动切换至 DuckDuckGo HTTP 抓取
- **零成本**：无需任何付费 API Key
- **全自动**：`./start_gateway.sh` 启动时已自动配置好搜索路由，无需额外操作
- **协议兼容**：完整实现 Anthropic Messages `web_search_20250305` 协议格式

也可直接调用搜索 API：
```bash
curl "http://127.0.0.1:8000/v1/search?q=你的搜索词"
```

---

## 📁 项目结构

| 文件 | 说明 |
|------|------|
| `gateway.py` | 网关核心：路由、故障转移、搜索引擎、Web 仪表盘 |
| `config.yaml` | 渠道配置（API Key、模型映射） |
| `start_gateway.sh` | 一键启动器（网关 + Harness + 自动清理） |
| `harness_env.sh` | Harness 环境变量注入（搜索路由 + API 转发） |
| `test_gateway.py` | 自动化测试套件（7 项全覆盖） |

现在你可以尽情享受各大渠道聚合的"无限 Token"池与高可用 Agent 体验！
