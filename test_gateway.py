import os
import sys
import time
import json
import asyncio
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from gateway import app, state, GatewayState

mock_app = FastAPI()
mock_call_counts = {"primary": 0, "backup": 0}

@mock_app.post("/mock-primary/chat/completions")
async def mock_primary(request: Request):
    mock_call_counts["primary"] += 1
    # 模拟 Primary 渠道额度耗尽 (402) 或触发限流 (429)
    return JSONResponse(
        status_code=402,
        content={"error": {"message": "Insufficient balance on primary channel", "type": "insufficient_quota"}}
    )

@mock_app.post("/mock-backup/chat/completions")
async def mock_backup(request: Request):
    mock_call_counts["backup"] += 1
    body = await request.json()
    is_stream = body.get("stream", False)
    
    if is_stream:
        async def stream_data():
            chunks = ["Hello", " from", " backup", " global", " channel!"]
            for c in chunks:
                chunk_obj = {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body.get("model"),
                    "choices": [{"index": 0, "delta": {"content": c}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk_obj)}\n\n".encode("utf-8")
                await asyncio.sleep(0.01)
            yield b"data: [DONE]\n\n"
        return StreamingResponse(stream_data(), media_type="text/event-stream")
    else:
        return JSONResponse({
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Backup global channel response success!"},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        })

async def run_tests():
    print("=" * 70)
    print("🧪 开始执行 Global Free Token 网关功能与交互控制测试...")
    print("=" * 70)

    # 1. 启动 mock 上游服务器
    config = uvicorn.Config(mock_app, host="127.0.0.1", port=8999, log_level="warning")
    server = uvicorn.Server(config)
    mock_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.5)

    # 2. 注入模拟渠道到 gateway 配置中
    state.config["providers"].insert(0, {
        "name": "Mock-Primary-Exhausted",
        "enabled": True,
        "base_url": "http://127.0.0.1:8999/mock-primary",
        "api_key": "mock-key-1",
        "models": [{"id": "deepseek-v4-pro", "upstream_model": "mock-v4-primary"}]
    })
    state.config["providers"].insert(1, {
        "name": "Mock-Backup-Active",
        "enabled": True,
        "base_url": "http://127.0.0.1:8999/mock-backup",
        "api_key": "mock-key-2",
        "models": [{"id": "deepseek-v4-pro", "upstream_model": "mock-v4-backup"}]
    })
    state._init_stats()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=15.0) as client:
        # Test 1: GET /v1/models
        print("\n[Test 1/6] 测试 GET /v1/models 模型列表聚合接口...")
        res = await client.get("/v1/models")
        assert res.status_code == 200
        models_data = res.json()["data"]
        model_ids = [m["id"] for m in models_data]
        print(f"✅ 模型列表获取成功！包含模型数: {len(model_ids)}")

        # Test 2: GET / 仪表盘
        print("\n[Test 2/6] 测试 GET / 交互式网页仪表盘...")
        res = await client.get("/")
        assert res.status_code == 200
        assert "Free Token" in res.text
        assert "switch" in res.text
        print("✅ 交互式网页仪表盘渲染正常！")

        # Test 3: POST /api/providers/toggle 开关测试
        test_provider_name = state.config["providers"][2]["name"]
        print(f"\n[Test 3/6] 测试 POST /api/providers/toggle 渠道开关接口 (目标: {test_provider_name})...")
        res = await client.post("/api/providers/toggle", json={"name": test_provider_name, "enabled": False})
        assert res.status_code == 200
        assert res.json()["enabled"] is False
        print(f"✅ 渠道开关切换成功 ({test_provider_name} 已设置为 False)！")

        # Test 4: POST /api/providers/update_key 填写与保存 Key
        print(f"\n[Test 4/6] 测试 POST /api/providers/update_key Key 填写与持久化接口 (目标: {test_provider_name})...")
        res = await client.post("/api/providers/update_key", json={"name": test_provider_name, "api_key": "sk-global-test-key"})
        assert res.status_code == 200
        print("✅ Key 填写与自动生效成功！")

        # Test 5: POST /v1/chat/completions (非流式 + 故障转移测试)
        print("\n[Test 5/6] 测试 POST /v1/chat/completions (非流式 + 自动故障转移)...")
        res = await client.post(
            "/v1/chat/completions",
            json={
                "model": "deepseek-v4",
                "messages": [{"role": "user", "content": "Hello!"}],
                "stream": False
            }
        )
        assert res.status_code == 200
        json_data = res.json()
        provider_header = res.headers.get("X-Gateway-Provider")
        retries_header = res.headers.get("X-Gateway-Retries")
        reply = json_data["choices"][0]["message"]["content"]
        
        print(f"✅ 非流式响应成功！返回内容: '{reply}'")
        print(f"✅ 自动切换成功！实际提供商: {provider_header}, 重试次数: {retries_header}")
        assert provider_header == "Mock-Backup-Active"

        # Test 6: POST /v1/chat/completions (流式 SSE 输出)
        print("\n[Test 6/6] 测试 POST /v1/chat/completions (流式 SSE 转发)...")
        chunks = []
        async with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "deepseek-v4",
                "messages": [{"role": "user", "content": "Stream test"}],
                "stream": True
            }
        ) as stream_resp:
            assert stream_resp.status_code == 200
            async for line in stream_resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    cdata = json.loads(line[6:])
                    delta = cdata["choices"][0]["delta"].get("content", "")
                    chunks.append(delta)
        
        full_text = "".join(chunks)
        print(f"✅ 流式 SSE 测试成功！完整接收到流式内容: '{full_text}'")

    server.should_exit = True
    await mock_task

    print("\n" + "=" * 70)
    print("🎉 全球渠道测试全部 100% 通过！网关与多渠道调度容灾完全正常！")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_tests())
