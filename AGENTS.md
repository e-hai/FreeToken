# 视觉多模态智能协同工作流规范 (Vision Collaboration Workflow)

无论当前运行的是 DeepSeek V4、Auto 智能自适应天梯，还是其他大语言模型，只要你当前无法直接读取本地像素图片、或者需要精确的视觉解析与 OCR 提取时，系统均已为你配备了专属的全局视觉感知外挂工具 `vision`。

## 视觉工具调用方式

当你面对“看图编程、UI 截图分析、UI 还原、审查设计稿、读取报错截屏文字 (OCR)、架构流程图分析”等任务时，**直接在 Bash 终端中运行 `vision` 命令**：

```bash
vision "<图片文件路径>" "<你的具体分析要求或提问>"
```
*(备用完整路径：`python3 tools/vision_mcp.py "<图片文件路径>" "<要求>" `)*

### 常用典型场景示例：

1. **Unity / 前端界面还原与 UI 控件布局分析**：
   ```bash
   vision "Assets/UI/login.png" "请详细分析该 UI 截图：列出所有按钮、文本输入框、背景色、各控件相对坐标位置及组件层级结构"
   ```
2. **提取报错截屏中的详细文字堆栈 (OCR 提取)**：
   ```bash
   vision "error.png" "请提取图中所有的报错堆栈、异常类名和错误行号"
   ```
3. **流程图 / 架构图 / 手绘草图理解**：
   ```bash
   vision "docs/architecture.png" "请分析该架构图中的核心模块划分与数据交互数据流"
   ```

### 多 Agent 角色明确分工规范：
- **主 Agent（编程与架构主管）**：由 DeepSeek-V4 / Kimi-K3 担任，专注逻辑思考、代码编写、文件读写与命令执行，绝对不介入直接像素分析；
- **从 Agent（多模态视觉专家）**：由 Google Gemini 3.8 / 3.6 Flash 担任，专注高精度视觉 OCR、UI 控件相对坐标与视觉缺陷分析，彻底剥离常规编程任务，保障长流程开发永不因协议与格式漂移而中断。

### 协作工作流规范：
1. **第一步（视觉感知）**：主 Agent 先运行 `vision` 命令或 MCP 工具，网关将自动调度至专属视觉天梯由 Google Gemini 顶级多模态模型深度解析，并返回图像中所有元素的结构化文字描述；
2. **第二步（逻辑实现）**：主 Agent 根据返回的精准视觉结构与控件细节，发挥强大的代码与架构长项，编写完整、高质量的工程代码。

---

## Chrome DevTools 网页自动化与深度检索规范 (Browser MCP Workflow)

系统已为 Agent 挂载官方 `chrome-devtools-mcp` 插件（工具前缀为 `mcp__chrome__*`），支持自主操控真实 Chrome 浏览器执行复杂检索与网页深度浏览。

### 常用工具与调用步骤：
1. **导航网页**：使用 `mcp__chrome__navigate_page` 访问目标网址（如 `https://www.bing.com`、`https://www.google.com`、GitHub 或技术文档链接）；
2. **分析页面元素**：使用 `mcp__chrome__take_snapshot` 获取页面可访问性树及控件 uid；
3. **交互操作**：使用 `mcp__chrome__fill` 在输入框键入关键词，使用 `mcp__chrome__click` 点击搜索按钮或目标文章；
4. **正文提取**：使用 `mcp__chrome__evaluate_script` 在页面上下文中执行 JS 获取文本正文或解析动态数据。

### 工具选择策略：
- **普通查资料 / 简单问答**：优先使用极速轻量的内置 `web_search`；
- **深度网页阅读 / 动态 JS 渲染页面 / 页面表单交互**：调起 `mcp__chrome__*` 进行完整的浏览器交互。

---

## AI 图像生成外挂规范 (Google Imagen 3 官方零水印引擎)

系统已为 Agent 挂载 Google 官方顶级扩散模型 **Google Imagen 3 (`imagen-3.0-generate-002`)**，具备电影级光影质感与原生 100% 零水印保障。

### 工具调用方式：
1. **终端命令行直接出图**：
   ```bash
   python3 tools/image_gen.py "<画面描述提示词>" -o "<输出路径.jpg>" -s "1024x1024"
   ```
2. **MCP 工具调用**：
   - 工具名：`generate_image`
   - 参数：`prompt` (画面描述), `size` (尺寸如 `1024x1024`, `1280x720`, `720x1280`, `1024x768`), `output_path` (保存路径)

### 官方画质与 100% 零水印保障：
- **Google Imagen 3 官方引擎**：Google 官方原生输出，100% 纯净零水印，无任何外部图床或平台 Logo；出图分辨率高达 1024x1024，支持标准 1:1、16:9、9:16、4:3、3:4 等多种宽高比例。

### 常用典型场景示例：
- **生成 UI 插画 / App 图标**：`python3 tools/image_gen.py "扁平化极简移动端登录页插图，科技感紫色调" -o login_illus.png`
- **概念图 / 游戏美术 / 配图生成**：根据任务需求自主生成图片并直接嵌入 Markdown。

---

## ChatGPT Codex CLI / Agent 接入规范 (Codex Wire API)

网关已原生支持 OpenAI 2026 Responses API 适配协议 (`POST /v1/responses`)，全面兼容 ChatGPT Codex CLI 终端代码助理。
Codex CLI 拥有专属运行端口 **8001** 与专属配置文件 `config.codex.yaml`，与 DeepSeek Harness (端口 8000) 彻底物理隔离。

### Codex CLI 配置 (`~/.codex/config.toml`)：
```toml
model = "deepseek-v4"
model_provider = "free_token"

[model_providers.free_token]
name = "FreeToken Gateway"
base_url = "http://127.0.0.1:8001/v1"
wire_api = "responses"
```
> 支持在 `model` 中指定 `deepseek-v4`、`codex`、`auto` 或 `gpt-5.3-codex` 等别名，全自动享受全球渠道多级故障转移容灾。
> 可在控制台 Web 页面 (`http://127.0.0.1:8000/`) 的 **[ChatGPT Codex CLI]** 标签页中点击“一键同步”，自动完成上述配置。
