import os
import sys
import time
import yaml
import httpx
import asyncio

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ 找不到配置文件: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

async def test_provider(provider: dict) -> dict:
    name = provider.get("name", "Unknown")
    enabled = provider.get("enabled", False)
    api_key = provider.get("api_key", "").strip()
    base_url = provider.get("base_url", "").rstrip("/")
    checkin_url = provider.get("checkin_url", "")
    models = provider.get("models", [])
    
    if not enabled:
        return {"name": name, "status": "⚪ 未启用 (Disabled)", "latency": "-", "msg": "在 config.yaml 中 enabled: false", "checkin": checkin_url}

    if not api_key or api_key.startswith("YOUR_"):
        return {"name": name, "status": "🟡 未配置 Key", "latency": "-", "msg": "请填入真实 API Key", "checkin": checkin_url}

    candidate_models = [m.get("upstream_model") for m in models if m.get("upstream_model")]
    if not candidate_models:
        candidate_models = ["deepseek-ai/DeepSeek-V4-Flash"]

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    if "openrouter" in base_url.lower():
        headers["HTTP-Referer"] = "https://github.com/deepseek-ai/deepseek-harness"
        headers["X-Title"] = "DeepSeek-Harness"

    start = time.time()
    last_status = 500
    last_text = ""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for test_model in candidate_models:
                try:
                    resp = await client.post(
                        url,
                        headers=headers,
                        json={
                            "model": test_model,
                            "messages": [{"role": "user", "content": "hi"}],
                            "max_tokens": 5
                        }
                    )
                    latency = int((time.time() - start) * 1000)
                    if resp.status_code == 200:
                        return {"name": name, "status": "🟢 正常可用", "latency": f"{latency}ms", "msg": f"[{test_model}] 连通成功", "checkin": checkin_url}
                    else:
                        last_status = resp.status_code
                        last_text = resp.text[:60]
                except Exception as e:
                    last_text = str(e)[:60]

            latency = int((time.time() - start) * 1000)
            if last_status == 401:
                return {"name": name, "status": "🔴 鉴权失败 (401)", "latency": f"{latency}ms", "msg": "API Key 错误或已过期", "checkin": checkin_url}
            elif last_status == 402:
                return {"name": name, "status": "🟡 余额不足 (402)", "latency": f"{latency}ms", "msg": "免费额度已耗尽，请点击签到领额度", "checkin": checkin_url}
            elif last_status == 403:
                return {"name": name, "status": "🔴 权限受限 (403)", "latency": f"{latency}ms", "msg": last_text, "checkin": checkin_url}
            elif last_status == 429:
                return {"name": name, "status": "🟡 触发限流 (429)", "latency": f"{latency}ms", "msg": "已触发速率限制 (Rate limit)", "checkin": checkin_url}
            else:
                return {"name": name, "status": f"🔴 异常 ({last_status})", "latency": f"{latency}ms", "msg": last_text, "checkin": checkin_url}
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        return {"name": name, "status": "🔴 连接超时/错误", "latency": f"{latency}ms", "msg": str(e)[:60], "checkin": checkin_url}

async def main():
    config = load_config()
    providers = config.get("providers", [])
    
    print("=" * 80)
    print("📋 Free Token 渠道健康度体检 & 每日签到看板")
    print("=" * 80)
    print("正在测试各渠道连通性，请稍候...\n")

    tasks = [test_provider(p) for p in providers]
    results = await asyncio.gather(*tasks)

    header_fmt = "{:<18} | {:<16} | {:<10} | {:<30}"
    row_fmt = "{:<18} | {:<18} | {:<10} | {:<30}"
    print(header_fmt.format("渠道平台", "状态", "响应延迟", "说明 / 诊断"))
    print("-" * 80)

    checkins = []
    for r in results:
        print(row_fmt.format(r["name"][:18], r["status"], r["latency"], r["msg"][:30]))
        if r.get("checkin"):
            checkins.append((r["name"], r["checkin"]))

    print("\n" + "=" * 80)
    print("🎁 每日签到 / 领免费额度快捷入口列表：")
    print("=" * 80)
    for name, url in checkins:
        print(f"• {name:<14} 👉  {url}")
    print("=" * 80)
    print("💡 提示：在各平台签到/领完 Key 后，直接在仪表盘 http://127.0.0.1:8000/ 更新即可秒级生效！\n")

if __name__ == "__main__":
    asyncio.run(main())
