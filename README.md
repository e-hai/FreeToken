# Free Token 聚合网关与自动负载均衡系统

专为 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 及各类 OpenAI SDK 客户端设计的 **多渠道免费/签到 Token 聚合网关与高可用负载均衡池**。

---

## 🌟 核心特性

1. **多渠道无缝聚合**：预置了 **硅基流动、OhMyGPT、AIHubMix、OpenRouter、DeepInfra、SambaNova、Google AI Studio、NVIDIA NIM** 等大模型免费/签到渠道。
2. **智能别名路由**：支持将客户端传入的 `deepseek-v4`、`deepseek-v4-pro`、`deepseek-r1` 等标准模型名自动映射为各上游服务商的具体模型。
3. **自动熔断与无感故障转移 (Failover)**：当某个渠道的免费额度用尽 (HTTP 402)、触发限流 (HTTP 429) 或网络报错时，网关在毫秒级内自动切换到备用渠道重试，保障 Agent 调用永不断连。
4. **全流式 SSE 转发**：原生支持流式输出，打字机式实时体验。
5. **实时可视化 Web 仪表盘**：访问 `http://127.0.0.1:8000/` 即可直观查看各渠道调用量、成功率、延迟及每日签到入口。

---

## 🚀 快速开始

### 1. 启动网关
```bash
./start_gateway.sh
```
启动后即可访问：
- **OpenAI 兼容接口**：`http://127.0.0.1:8000/v1`
- **可视化仪表盘**：`http://127.0.0.1:8000/`

---

### 2. 渠道体检与每日签到助手
```bash
./start_gateway.sh --checkin
```
终端将自动输出所有渠道 Key 的连通性、响应延迟以及一键签到领额度的快捷链接。

---

### 3. 执行自动化测试与故障转移验证
```bash
./start_gateway.sh --test
```
执行包含模型列表、非流式、流式 SSE 以及模拟渠道故障自动切换在内的全套测试。

---

## ⚙️ 配置渠道 Key (`config.yaml`)

打开 `config.yaml`，将你在各大平台注册或签到领取的 API Key 填入，并将对应渠道的 `enabled` 改为 `true`：

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

  # 示例 2：OhMyGPT (每日签到领额度)
  - name: "OhMyGPT"
    enabled: true
    base_url: "https://api.ohmygpt.com/v1"
    api_key: "sk-xxxxxxxx"
    models:
      - id: "deepseek-v4-pro"
        upstream_model: "deepseek-v4-pro"
```

---

## 🔌 接入 DeepSeek-Harness 配置

1. 启动 DeepSeek-Harness：
   ```bash
   npx @deepseek-ai/dsh web
   ```
2. 打开浏览器访问 `http://127.0.0.1:3080`，进入 **Settings -> Models**，添加自定义 Provider：
   - **Provider ID**: `local-gateway`
   - **Base URL**: `http://127.0.0.1:8000/v1`
   - **API Key**: 任意填写（如 `free-token`）
   - **Model**: `deepseek-v4-pro` 或 `deepseek-v4-flash` 或 `deepseek-r1`

现在你可以尽情享受各大渠道聚合的“无限 Token”池与高可用 Agent 体验！
