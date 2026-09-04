import os
import sys
import time
import argparse
import httpx
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "harness_config.yaml")

def load_harness_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "gateway": {"base_url": "http://127.0.0.1:8000/v1", "api_key": "free-token"}
    }

def main():
    parser = argparse.ArgumentParser(description="DeepSeek-Harness 评测与自动化调用测试套件")
    parser.add_argument("--model", type=str, default="deepseek-v4", help="请求模型名称 (如 deepseek-v4, qwen3.6, gemini-flash, gpt-oss-120b, free)")
    parser.add_argument("--prompt", type=str, default="请分步骤解答：小明有 24 颗糖，分给小红 1/3，又给小刚 4 颗，最后小明还剩多少颗？", help="评测或测试提示词")
    parser.add_argument("--stream", action="store_true", help="是否启用流式 SSE 输出")
    args = parser.parse_args()

    cfg = load_harness_config()
    base_url = cfg["gateway"]["base_url"].rstrip("/")
    api_key = cfg["gateway"]["api_key"]

    print("=" * 80)
    print("🚀 DeepSeek-Harness 正在向本地网关发起评测任务...")
    print(f"👉 目标网关: {base_url}")
    print(f"👉 请求模型: {args.model}")
    print(f"👉 提示词: {args.prompt}")
    print("=" * 80)

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "You are a professional benchmark evaluator for DeepSeek-Harness."},
            {"role": "user", "content": args.prompt}
        ],
        "stream": args.stream,
        "max_tokens": 400
    }

    t0 = time.time()
    try:
        if args.stream:
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as resp:
                if resp.status_code != 200:
                    print(f"❌ 请求失败 (HTTP {resp.status_code}): {resp.read().decode('utf-8', errors='ignore')}")
                    return
                
                provider = resp.headers.get("x-gateway-provider", "未知")
                model_used = resp.headers.get("x-gateway-model", args.model)
                print(f"📡 【网关已成功分发】 -> 渠道: [{provider}] | 实际调用大模型: [{model_used}]")
                print("\n🎯 【评测回复输出】:\n")
                
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            import json
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            sys.stdout.write(content)
                            sys.stdout.flush()
                        except Exception:
                            pass
                print("\n")
        else:
            resp = httpx.post(url, headers=headers, json=payload, timeout=60.0)
            lat = int((time.time() - t0) * 1000)
            if resp.status_code != 200:
                print(f"❌ 请求失败 (HTTP {resp.status_code}): {resp.text}")
                return

            provider = resp.headers.get("x-gateway-provider", "未知")
            model_used = resp.headers.get("x-gateway-model", args.model)
            res_json = resp.json()
            content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")

            print(f"📡 【网关已成功分发】 -> 渠道: [{provider}] | 实际调用大模型: [{model_used}] | 耗时: {lat}ms\n")
            print("🎯 【评测回复输出】:\n")
            print(content)

        print("\n" + "=" * 80)
        print("💡 提示：打开 http://127.0.0.1:8000/ 即可在控制台日志面板查看该步骤的完整调用链路！")
        print("=" * 80)

    except Exception as e:
        print(f"❌ 连接异常: {e}")

if __name__ == "__main__":
    main()
