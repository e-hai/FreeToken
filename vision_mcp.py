#!/usr/bin/env python3
"""
Vision MCP Server & CLI Tool for DeepSeek-Harness
提供给 DeepSeek V4 的视觉外挂工具：
- 支持作为 MCP (Model Context Protocol) Server 运行 (stdio 模式)
- 支持作为独立 CLI 命令行运行 (python3 vision_mcp.py <image_path> [prompt])
- 自动通过本地网关 (http://127.0.0.1:8000/v1) 调用顶级免费视觉模型 (Google Gemini 3.5 Flash)
- 零外部三方库依赖 (纯原生 Python 标准库实现)
"""

import sys
import os
import json
import base64
import urllib.request
import urllib.error

GATEWAY_URL = os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:8000/v1") + "/chat/completions"
API_KEY = os.environ.get("OPENAI_API_KEY", "free-token")

def analyze_image(image_path: str, prompt: str = "请详细描述此图片中的所有视觉内容、UI 元素、文字 OCR 与布局结构：") -> str:
    path = os.path.expanduser(image_path.strip())
    if not os.path.exists(path):
        return f"❌ 错误：在路径 '{path}' 未找到图片文件。请确认文件路径是否正确。"

    ext = os.path.splitext(path)[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    mime = f"image/{ext}" if ext in ["png", "jpeg", "webp", "gif"] else "image/png"

    try:
        with open(path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return f"❌ 读取图片文件失败: {str(e)}"

    payload = {
        "model": "auto",  # 自动走网关的顶级视觉模型 (Google Gemini 3.5 Flash)
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_data}"}}
                ]
            }
        ],
        "max_tokens": 2048
    }

    try:
        req = urllib.request.Request(
            GATEWAY_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            resp_body = resp.read().decode("utf-8")
            data = json.loads(resp_body)
            choice = data["choices"][0]["message"]
            content = choice.get("content")
            if content and content.strip():
                return content.strip()
            reasoning = choice.get("reasoning")
            if reasoning and reasoning.strip():
                return reasoning.strip()
            return "视觉分析完成，但视觉模型未返回具体文字描述。"
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        return f"❌ 视觉大模型请求失败 (HTTP {e.code}): {err_msg[:300]}"
    except Exception as e:
        return f"❌ 视觉请求出现异常: {str(e)}"

def run_mcp_server():
    """以标准 JSON-RPC 2.0 stdio 模式运行 MCP 服务"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "vision-tool",
                        "version": "1.0.0"
                    }
                }
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            continue

        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "inspect_image",
                            "description": "视觉分析工具（眼睛外挂）：让纯文本模型调用视觉大模型来识别和理解图片、UI 截图、图表、手稿或错误截屏。返回详细的视觉元素、文字 OCR 和层级布局描述。",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "image_path": {
                                        "type": "string",
                                        "description": "本地图片文件的路径（绝对路径或相对工作区的相对路径，如 'Assets/UI/login.png'）"
                                    },
                                    "prompt": {
                                        "type": "string",
                                        "description": "对该图片的具体提问或分析侧重点（例如：'提取图中的报错堆栈'、'描述界面中的所有按钮及其颜色样式'）"
                                    }
                                },
                                "required": ["image_path"]
                            }
                        }
                    ]
                }
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            if tool_name == "inspect_image":
                img_path = args.get("image_path", "")
                p_text = args.get("prompt", "请详细描述此图片中的所有视觉内容、文字与布局结构：")
                result_text = analyze_image(img_path, p_text)
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": result_text
                            }
                        ]
                    }
                }
            else:
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"未知的工具名称: {tool_name}"
                    }
                }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif req_id is not None:
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"不支持的方法: {method}"
                }
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        image_arg = sys.argv[1]
        prompt_arg = sys.argv[2] if len(sys.argv) > 2 else "请详细描述此图片中的所有视觉内容、文字与布局结构："
        print(analyze_image(image_arg, prompt_arg))
    else:
        run_mcp_server()
