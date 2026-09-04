---
name: vision
description: 本地多模态视觉外挂与图像分析工具。当需要查看和理解本地图片文件、UI 设计稿、界面截图、错误报错截屏(OCR)、架构流程图或手绘草图时使用此 Skill。无论主模型是否具备原生识图能力，都可以直接调用网关后端的顶级视觉模型（Google Gemini 3.8/3.5 Flash）获得高精度的元素布局、文字 OCR 与视觉细节解析。
---

# 视觉感知外挂 Skill (Vision Multi-modal Tool)

为纯文本大模型（如 DeepSeek-V4、Llama 系列等）提供“视觉眼睛外挂”。

## 适用场景
- **UI 还原与界面开发**：分析设计稿或截图中的按钮、输入框、相对位置、组件层级与颜色风格。
- **报错截屏诊断 (OCR)**：精确提取截屏中的报错堆栈、异常类名、行号与报错信息。
- **流程图 / 架构图 / 手稿解析**：理解系统架构图、数据流图或白板手绘草图。

## 调用方式

### 方式 1：CLI 命令直接调用（支持任何包含 Bash / 终端执行权限的 Harness）
在终端中直接运行：
```bash
vision "<图片文件路径>" "<具体的分析要求或提问>"
```
*备用完整 Python 路径*：
```bash
python3 /Users/a/Develop/project/free-token/vision_mcp.py "<图片文件路径>" "<具体的分析要求或提问>"
```

### 方式 2：MCP 函数调用（支持配置了 MCP 服务的 Harness）
调用工具：
- 工具名：`inspect_image`
- 参数：
  - `image_path`: 图片文件路径（如 `Assets/UI/login.png` 或绝对路径）
  - `prompt`: 针对该图片的提问或分析指示

## 执行示例
```bash
# 1. 提取错误截屏中的堆栈文字
vision "error.png" "请提取图中所有的报错堆栈与行号"

# 2. 分析 UI 布局
vision "Assets/UI/main_menu.png" "请分析该 UI 截图：列出所有按钮、文本输入框、背景色、各控件相对坐标位置及组件层级结构"
```
