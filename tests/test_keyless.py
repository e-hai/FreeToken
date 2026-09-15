import urllib.request
import json

def test_keyless_endpoint():
    url = "https://text.pollinations.ai/openai/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "model": "openai-fast",
        "messages": [
            {"role": "system", "content": "You are an AI assistant integrated into DeepSeek Harness."},
            {"role": "user", "content": "请用中文写一句测试通过的确认信息，并说明你是什么模型。"}
        ]
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    print("[1/2] 正在向免注册、免Key海外端点发送测试请求...")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data["choices"][0]["message"]["content"]
            model = res_data.get("model", "unknown")
            print("[2/2] ✅ 接口测试成功！返回结果如下：")
            print("-" * 50)
            print(f"模型名称: {model}")
            print(f"回答内容: {content}")
            print("-" * 50)
            return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    test_keyless_endpoint()
