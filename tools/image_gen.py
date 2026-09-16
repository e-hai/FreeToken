#!/usr/bin/env python3
"""
AI Image Generation CLI Tool (文生图独立命令行工具)
支持一键将文本描述渲染为高清图像：
- 默认连接本地 FreeToken 网关 (http://127.0.0.1:8000/v1/images/generations)
- 网关未启动时，无缝降级至 Pollinations Flux 免费极速引擎直连
- 支持自定义尺寸 (--size: 1024x1024, 1280x720, 720x1280 等)
- 零额外三方库依赖 (纯原生 Python 标准库实现)
"""

import sys
import os
import time
import json
import urllib.request
import urllib.parse
import urllib.error
import argparse

GATEWAY_URL = os.environ.get("IMAGE_GATEWAY_URL", "http://127.0.0.1:8000/v1/images/generations")

def generate_image_via_gateway(prompt: str, size: str = "1024x1024", model: str = "flux", output_path: str = None) -> tuple:
    """通过本地网关生成图像"""
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

def generate_image_direct(prompt: str, size: str = "1024x1024", model: str = "flux", output_path: str = None) -> tuple:
    """网关不可用时，直接请求免Key公共端点出图"""
    width, height = 1024, 1024
    if size and "x" in size:
        try:
            parts = size.lower().split("x")
            width, height = int(parts[0]), int(parts[1])
        except Exception:
            pass

    seed = int(time.time() * 1000) % 1000000
    encoded = urllib.parse.quote(prompt.strip())
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model={model}&nologo=true&seed={seed}"
    
    if not output_path:
        output_path = f"img_{int(time.time())}.jpg"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (FreeToken CLI)"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        with open(output_path, "wb") as f:
            f.write(resp.read())
    return output_path, url

def main():
    parser = argparse.ArgumentParser(description="🎨 AI Image Generation CLI Tool (文生图命令行工具)")
    parser.add_argument("prompt", type=str, help="画面描述提示词 (支持中英文)")
    parser.add_argument("-o", "--output", type=str, default=None, help="输出图像保存路径 (如 output.jpg)")
    parser.add_argument("-s", "--size", type=str, default="1024x1024", help="图像尺寸，如 1024x1024 (1:1), 1280x720 (16:9), 720x1280 (9:16)")
    parser.add_argument("-m", "--model", type=str, default="auto", choices=["auto", "flux", "imagen-3", "turbo", "sdxl"], help="模型架构 (默认: auto，支持 flux 优先 + imagen-3 容灾)")

    args = parser.parse_args()

    print(f"🎨 [AI画图] 正在渲染图像: '{args.prompt}' (尺寸: {args.size}, 模型: {args.model})...")
    start_time = time.time()

    saved_file = None
    source_url = None
    try:
        saved_file, source_url = generate_image_via_gateway(args.prompt, args.size, args.model, args.output)
        engine_used = "本地网关 (Flux 优先 · Imagen 3 容灾)"
    except Exception as e:
        print(f"⚠️ [提示] 本地网关未响应 ({e})，切换至免Key云端极速渲染引擎...")
        try:
            saved_file, source_url = generate_image_direct(args.prompt, args.size, "flux" if args.model == "auto" else args.model, args.output)
            engine_used = "云端直连 (Pollinations Flux)"
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
