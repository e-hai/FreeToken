#!/usr/bin/env python3
"""
AI Image Generation CLI Tool (文生图独立命令行工具)
基于 Google Imagen 3 官方扩散模型，支持一键将文本描述渲染为高清无水印图像：
- 默认连接本地 FreeToken 网关 (http://127.0.0.1:8000/v1/images/generations)
- 网关未启动时，直连 Google AI Studio 官方 Imagen 3 端点
- 100% 官方原生零水印、无任何外部图床或平台 Logo
- 支持标准画幅比例 (1024x1024, 1280x720, 720x1280, 1024x768, 768x1024)
- 零额外三方库依赖 (纯原生 Python 标准库实现)
"""

import sys
import os
import time
import json
import base64
import urllib.request
import urllib.parse
import urllib.error
import argparse

GATEWAY_URL = os.environ.get("IMAGE_GATEWAY_URL", "http://127.0.0.1:8000/v1/images/generations")

def get_google_key() -> str:
    """获取可用的 Google API Key"""
    for env in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_STUDIO_KEY"]:
        val = os.environ.get(env, "").strip()
        if val and not val.startswith("YOUR_"):
            return val
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                in_google = False
                for line in f:
                    if "Google AI Studio" in line or "google" in line.lower():
                        in_google = True
                    elif in_google and "api_key:" in line:
                        key = line.split("api_key:")[-1].strip().strip('"').strip("'")
                        if key and not key.startswith("YOUR_"):
                            return key
                    elif in_google and line.strip().startswith("- name:"):
                        in_google = False
        except Exception:
            pass
    return ""

def generate_image_via_gateway(prompt: str, size: str = "1024x1024", model: str = "imagen-3", output_path: str = None) -> tuple:
    """通过本地网关生成 Google Imagen 3 图像"""
    payload = {
        "prompt": prompt,
        "size": size,
        "model": model,
        "n": 1,
        "response_format": "url"
    }
    req = urllib.request.Request(
        GATEWAY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        img_url = data["data"][0]["url"]
        
        if not output_path:
            output_path = f"img_{int(time.time())}.jpg"
        
        urllib.request.urlretrieve(img_url, output_path)
        return output_path, img_url

def generate_image_direct(prompt: str, size: str = "1024x1024", model: str = "imagen-3", output_path: str = None) -> tuple:
    """网关未启动时，直接调用 Google 官方 Imagen 3 扩散大模型端点出图 (100% 零水印)"""
    key = get_google_key()
    if not key:
        raise RuntimeError("未检测到有效 Google API Key，请在环境变量或 config.yaml 中配置 Google AI Studio Key")
    
    aspect_ratio = "1:1"
    if size and "x" in size:
        try:
            parts = size.lower().split("x")
            w, h = int(parts[0]), int(parts[1])
            if w == h:
                aspect_ratio = "1:1"
            elif w > h:
                aspect_ratio = "16:9" if (w / h) >= 1.5 else "4:3"
            else:
                aspect_ratio = "9:16" if (h / w) >= 1.5 else "3:4"
        except Exception:
            aspect_ratio = "1:1"

    m_id = "imagen-3.0-generate-002"
    if "fast" in (model or "").lower():
        m_id = "imagen-3.0-fast-generate-001"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_id}:predict"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": aspect_ratio,
            "personGeneration": "ALLOW_ADULT",
            "outputMimeType": "image/jpeg"
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key
        }
    )
    if not output_path:
        output_path = f"img_{int(time.time())}.jpg"

    with urllib.request.urlopen(req, timeout=60.0) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
        preds = res_data.get("predictions", [])
        if not preds or "bytesBase64Encoded" not in preds[0]:
            raise RuntimeError(f"Google Imagen 3 出图失败: {res_data}")
        img_bytes = base64.b64decode(preds[0]["bytesBase64Encoded"])
        with open(output_path, "wb") as f:
            f.write(img_bytes)
    return output_path, url

def main():
    parser = argparse.ArgumentParser(description="🎨 Google Imagen 3 CLI Tool (官方扩散模型文生图命令行工具)")
    parser.add_argument("prompt", type=str, help="画面描述提示词 (支持中英文)")
    parser.add_argument("-o", "--output", type=str, default=None, help="输出图像保存路径 (如 output.jpg)")
    parser.add_argument("-s", "--size", type=str, default="1024x1024", help="图像尺寸，如 1024x1024 (1:1), 1280x720 (16:9), 720x1280 (9:16), 1024x768 (4:3), 768x1024 (3:4)")
    parser.add_argument("-m", "--model", type=str, default="imagen-3", choices=["imagen-3", "imagen-3.0-generate-002", "imagen-3.0-fast-generate-001"], help="扩散模型 (默认: imagen-3 官方高精旗舰)")

    args = parser.parse_args()

    print(f"🎨 [AI画图] 正在渲染图像: '{args.prompt}' (尺寸: {args.size}, 模型: {args.model})...")
    start_time = time.time()

    saved_file = None
    source_url = None
    try:
        saved_file, source_url = generate_image_via_gateway(args.prompt, args.size, args.model, args.output)
        engine_used = "本地网关 (Google Imagen 3 官方引擎)"
    except Exception as e:
        print(f"⚠️ [提示] 本地网关未响应 ({e})，切换至 Google 官方端点直连...")
        try:
            saved_file, source_url = generate_image_direct(args.prompt, args.size, args.model, args.output)
            engine_used = "Google 官方端点直连 (Imagen 3)"
        except Exception as direct_err:
            print(f"❌ 图像生成失败: {direct_err}")
            sys.exit(1)

    cost_time = time.time() - start_time
    abs_path = os.path.abspath(saved_file)
    print(f"✅ [成功] 图像生成完毕！(耗时: {cost_time:.1f}s, 引擎: {engine_used})")
    print(f"📁 本地保存路径: {abs_path}")
    print(f"🌐 原始预览链接: {source_url}")

if __name__ == "__main__":
    main()
