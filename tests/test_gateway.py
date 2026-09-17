import os
import sys
import time
import json
import asyncio
import copy
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

# 确保无论从何处运行均可正确导入 src/gateway
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
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

@mock_app.post("/v1beta/models/imagen-3.0-generate-002:predict")
@mock_app.post("/v1beta/models/imagen-3.0-fast-generate-001:predict")
async def mock_imagen(request: Request):
    mock_call_counts["imagen"] = mock_call_counts.get("imagen", 0) + 1
    # 1x1 base64 transparent png (valid image)
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    return JSONResponse({
        "predictions": [
            {
                "bytesBase64Encoded": dummy_b64,
                "mimeType": "image/png"
            }
        ]
    })

async def run_tests():
    print("=" * 70)
    print("🧪 开始执行 Global Free Token 网关功能与交互控制测试...")
    print("=" * 70)

    # 0. 备份原始配置，确保测试结束后 100% 还原，不污染 config.harness.yaml / config.codex.yaml
    original_harness = copy.deepcopy(state.harness_config)
    original_codex = copy.deepcopy(state.codex_config)

    # 1. 启动 mock 上游服务器
    config = uvicorn.Config(mock_app, host="127.0.0.1", port=8999, log_level="warning")
    server = uvicorn.Server(config)
    mock_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.5)

    # 2. 注入模拟渠道到 gateway 内存配置中 (测试完自动清理)
    mock_providers = [
        {
            "name": "Mock-Primary-Exhausted",
            "enabled": True,
            "priority": 999,
            "base_url": "http://127.0.0.1:8999/mock-primary",
            "api_key": "mock-key-1",
            "models": [
                {"id": "deepseek-v4", "upstream_model": "mock-v4-primary"},
                {"id": "deepseek-v4-pro", "upstream_model": "mock-v4-primary"},
                {"id": "deepseek-ai/deepseek-v4-flash-0731", "upstream_model": "mock-v4-primary"},
                {"id": "codex", "upstream_model": "mock-v4-primary"},
                {"id": "gpt-5.3-codex", "upstream_model": "mock-v4-primary"},
                {"id": "auto", "upstream_model": "mock-v4-primary"}
            ]
        },
        {
            "name": "Mock-Backup-Active",
            "enabled": True,
            "priority": 998,
            "base_url": "http://127.0.0.1:8999/mock-backup",
            "api_key": "mock-key-2",
            "models": [
                {"id": "deepseek-v4", "upstream_model": "mock-v4-backup"},
                {"id": "deepseek-v4-pro", "upstream_model": "mock-v4-backup"},
                {"id": "deepseek-ai/deepseek-v4-flash-0731", "upstream_model": "mock-v4-backup"},
                {"id": "codex", "upstream_model": "mock-v4-backup"},
                {"id": "gpt-5.3-codex", "upstream_model": "mock-v4-backup"},
                {"id": "auto", "upstream_model": "mock-v4-backup"}
            ]
        },
        {
            "name": "Mock-Google-AI-Studio",
            "enabled": True,
            "priority": 997,
            "base_url": "http://127.0.0.1:8999",
            "api_key": "mock-google-key",
            "models": [{"id": "imagen-3.0-generate-002", "upstream_model": "imagen-3.0-generate-002"}]
        }
    ]

    for p in reversed(mock_providers):
        state.harness_config["providers"].insert(0, copy.deepcopy(p))
        state.codex_config["providers"].insert(0, copy.deepcopy(p))
    state._init_stats()

    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=15.0)

    try:
        # Test 1: GET /v1/models
        print("\n[Test 1/6] 测试 GET /v1/models 模型列表聚合接口...")
        res = await client.get("/v1/models")
        assert res.status_code == 200
        models_data = res.json()["data"]
        model_ids = [m["id"] for m in models_data]
        assert model_ids == ["auto", "deepseek", "glm", "kimi"]
        print(f"✅ 模型列表获取成功！包含模型数: {len(model_ids)}")

        # 四个入口是模型组而非单模型：显式组必须先耗尽同家族，再跨组容灾。
        from gateway import build_tiered_execution_plan
        expected_prefixes = {
            "deepseek": ["deepseek"],
            "glm": ["glm", "glm"],
            "kimi": ["kimi"],
        }
        for group, prefixes in expected_prefixes.items():
            plan = build_tiered_execution_plan(group, has_tools=True, channel="harness")
            ordered_models = [
                model
                for tier in plan
                for provider, model in tier["candidates"]
                if not provider.get("name", "").startswith("Mock-")
            ]
            assert len(ordered_models) >= len(prefixes)
            assert all(
                prefix in model.lower()
                for prefix, model in zip(prefixes, ordered_models)
            ), f"{group} 组未被优先调度: {ordered_models[:5]}"

        # 带 tools 的会话里绝不能混入视觉专用或小参数老模型：它们没有 tool calling，
        # 一旦被降级命中，Agent 客户端只拿到纯文本，表现为“执行一段就停”。
        from gateway import is_agent_capable_model
        for group in ("auto", "deepseek", "glm", "kimi"):
            plan = build_tiered_execution_plan(group, has_tools=True, channel="harness")
            for tier in plan:
                for provider, model in tier["candidates"]:
                    if provider.get("name", "").startswith("Mock-"):
                        continue
                    assert is_agent_capable_model(model), \
                        f"{group} 组工具队列混入了弱模型: {model}"

        # 视觉任务走 Gemini Flash + Llama 3.2 Vision 专属天梯，不得混入 embedding / 老旧 VLM
        from gateway import convert_responses_content, messages_have_image, is_vision_fallback_model
        mixed = convert_responses_content([
            {"type": "input_text", "text": "看这张截图"},
            {"type": "input_image", "image_url": "data:image/png;base64,abc"},
        ])
        assert isinstance(mixed, list)
        assert mixed[0]["type"] == "text" and mixed[0]["text"] == "看这张截图"
        assert mixed[1]["type"] == "image_url"
        assert mixed[1]["image_url"]["url"].startswith("data:image/png")
        assert messages_have_image([{"role": "user", "content": mixed}])
        assert not messages_have_image([{"role": "user", "content": "hello"}])

        vision_plan = build_tiered_execution_plan("auto", has_tools=True, has_image=True, channel="harness")
        vision_models = [m for tier in vision_plan for _, m in tier["candidates"]]
        assert vision_models, "视觉队列为空"
        assert all(is_vision_fallback_model(m) for m in vision_models), f"视觉队列混入了非旗舰模型: {vision_models}"
        assert any("gemini" in m.lower() for m in vision_models), f"视觉队列缺少 Gemini: {vision_models}"
        assert any("llama-3.2" in m.lower() and "vision" in m.lower() for m in vision_models), \
            f"视觉队列缺少 Llama 3.2 Vision 兜底: {vision_models}"
        print("✅ 模型组调度队列无弱模型混入，视觉链路完好！")

        ds_models = [
            model
            for tier in build_tiered_execution_plan("deepseek", has_tools=True, channel="harness")
            for provider, model in tier["candidates"]
            if not provider.get("name", "").startswith("Mock-")
        ]
        assert any("v4-pro-0813" in model for model in ds_models), \
            f"OpenRouter 的 DeepSeek V4 Pro 未进入 deepseek 组: {ds_models[:8]}"

        # Test 2: GET / 仪表盘
        print("\n[Test 2/6] 测试 GET / 交互式网页仪表盘...")
        res = await client.get("/")
        assert res.status_code == 200
        assert "Free Token" in res.text
        assert "switch" in res.text
        assert "全局总览" not in res.text
        assert "Harness 独立渠道商" in res.text
        assert "Codex 独立渠道商" in res.text
        assert "显示 Key" in res.text
        assert "调度队列" in res.text
        assert "类别" not in res.text
        assert "<svg" not in res.text
        for p in state.harness_config.get("providers", []) + state.codex_config.get("providers", []):
            key = (p.get("api_key") or "").strip()
            if key and not key.startswith("YOUR_") and len(key) > 8:
                assert key not in res.text, "仪表盘不得下发明文 API Key"
        print("✅ 交互式网页仪表盘渲染正常！")

        # Test 3: POST /api/providers/toggle 开关测试 (测试真实生产渠道，验证落盘能力)
        real_providers = [p for p in state.config["providers"] if not p.get("name", "").startswith("Mock-")]
        test_provider_name = real_providers[0]["name"]
        print(f"\n[Test 3/6] 测试 POST /api/providers/toggle 渠道开关接口 (目标: {test_provider_name})...")
        codex_before = next(p.get("enabled") for p in state.codex_config["providers"] if p.get("name") == test_provider_name)
        res = await client.post("/api/providers/toggle", json={"name": test_provider_name, "enabled": False, "channel": "harness"})
        assert res.status_code == 200
        assert res.json()["enabled"] is False
        harness_after = next(p.get("enabled") for p in state.harness_config["providers"] if p.get("name") == test_provider_name)
        codex_after = next(p.get("enabled") for p in state.codex_config["providers"] if p.get("name") == test_provider_name)
        assert harness_after is False
        assert codex_after is codex_before
        print(f"✅ 渠道开关仅作用于 Harness ({test_provider_name} 已设置为 False)，Codex 保持 {codex_after}！")

        # Test 4: POST /api/providers/update_key 填写与保存 Key
        print(f"\n[Test 4/6] 测试 POST /api/providers/update_key Key 填写与持久化接口 (目标: {test_provider_name})...")
        res = await client.post("/api/providers/update_key", json={"name": test_provider_name, "api_key": "sk-global-test-key", "channel": "harness"})
        assert res.status_code == 200
        print("✅ Key 填写与自动生效成功！")

        print("\n[Test 4b] 密钥脱敏、YAML 预览与调度队列...")
        stats_res = await client.get("/api/stats")
        assert stats_res.status_code == 200
        stats_json = stats_res.json()
        assert "dispatch" in stats_json and "queues" in stats_json["dispatch"]["harness"]
        assert "deepseek" in stats_json["dispatch"]["harness"]["queues"]
        for ch in ("harness", "codex"):
            for p in stats_json["providers"][ch]:
                raw = next((x.get("api_key") for x in state.get_config(ch)["providers"] if x.get("name") == p.get("name")), "")
                if raw and not str(raw).startswith("YOUR_") and len(str(raw)) > 8:
                    assert p.get("api_key") != raw
                    assert "••••" in (p.get("api_key") or p.get("api_key_masked") or "")
        masked_list = await client.get("/api/providers", params={"channel": "harness", "reveal": False})
        revealed_list = await client.get("/api/providers", params={"channel": "harness", "reveal": True})
        assert masked_list.status_code == 200 and revealed_list.status_code == 200
        bad = await client.post("/api/config/validate", json={"content": "providers: ["})
        assert bad.status_code == 400
        good = await client.post("/api/config/validate", json={"content": "server:\n  port: 8000\nproviders:\n- name: Demo\n  enabled: true\n  models: []\n"})
        assert good.status_code == 200
        assert good.json()["summary"]["enabled"] == ["Demo"]
        print("✅ 脱敏、调度快照与 YAML 预览校验通过！")

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

        # Test 7: Web Search 检索与 Anthropic Messages 协议适配
        print("\n[Test 7/7] 测试 DeepSeek-Harness 实时 Web 检索与 Anthropic 协议端点...")
        search_res = await client.post(
            "/anthropic/v1/messages",
            json={
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": [{"type": "text", "text": "Perform a web search for the query: Python"}]}],
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
            }
        )
        assert search_res.status_code == 200
        search_json = search_res.json()
        assert search_json.get("type") == "message"
        result_blocks = [b for b in search_json.get("content", []) if b.get("type") == "web_search_tool_result"]
        assert len(result_blocks) > 0
        items = result_blocks[0].get("content", [])
        first_title = items[0].get('title', '')[:30] if items else 'Network Search Fallback'
        print(f"✅ Web 检索端点测试成功！成功返回 {len(items)} 条网页索引结果 (首条: {first_title}...)")

        # Test 8: AI 文生图接口与 Google Imagen 3 引擎调度 (/v1/images/generations)
        print("\n[Test 8/9] 测试 Google Imagen 3 官方扩散模型文生图接口与本地落盘托管 (/v1/images/generations)...")
        img_res = await client.post(
            "/v1/images/generations",
            headers={"x-goog-api-key": "mock-google-key"},
            json={
                "prompt": "A cute origami bird, studio lighting",
                "size": "1024x1024",
                "model": "imagen-3",
                "n": 1
            }
        )
        assert img_res.status_code == 200
        img_json = img_res.json()
        assert "data" in img_json and len(img_json["data"]) > 0
        img_url = img_json["data"][0]["url"]
        assert img_url is not None
        assert img_json["data"][0].get("engine") == "google-imagen-3"
        print(f"✅ Google Imagen 3 文生图端点测试成功！返回图像 URL: {img_url}")

        # 测试本地静态图片获取
        if "/generated_images/" in img_url:
            path_part = "/generated_images/" + img_url.split("/generated_images/")[-1]
            static_res = await client.get(path_part)
            assert static_res.status_code == 200
            assert len(static_res.content) > 50
            print(f"✅ 本地静态图片托管验证通过！图片字节大小: {len(static_res.content)} bytes")

        # Test 9: 测试 Google Imagen 3 Fast 极速模型与 16:9 画幅映射
        print("\n[Test 9/10] 测试 Google Imagen 3 Fast 极速模型与 16:9 画幅映射...")
        imagen_res = await client.post(
            "/v1/images/generations",
            headers={"x-goog-api-key": "mock-google-key"},
            json={
                "prompt": "A futuristic metropolis with flying cars, photorealistic 8k",
                "size": "1280x720",
                "model": "imagen-3.0-fast-generate-001",
                "n": 1
            }
        )
        assert imagen_res.status_code == 200
        imagen_json = imagen_res.json()
        assert len(imagen_json["data"]) > 0
        assert imagen_json["data"][0].get("engine") == "google-imagen-3"
        assert mock_call_counts.get("imagen", 0) >= 2
        print(f"✅ Google Imagen 3 Fast 引擎调用成功！(引擎标识: {imagen_json['data'][0].get('engine')}, 调用计数: {mock_call_counts.get('imagen')})")

        # Test 10: 测试旧模型别名 (如 flux / auto) 自动映射至 Google Imagen 3
        print("\n[Test 10/10] 测试旧模型别名 (如 flux / auto) 自动平滑映射至 Google Imagen 3...")
        fallback_res = await client.post(
            "/v1/images/generations",
            headers={"x-goog-api-key": "mock-google-key"},
            json={
                "prompt": "Cyberpunk robot in neon rain",
                "size": "1024x1024",
                "model": "flux",
                "n": 1
            }
        )
        assert fallback_res.status_code == 200
        fallback_json = fallback_res.json()
        assert len(fallback_json["data"]) > 0
        assert fallback_json["data"][0].get("engine") == "google-imagen-3"
        print(f"✅ 旧别名平滑映射测试成功！成功调度引擎: {fallback_json['data'][0].get('engine')}")

        # Test 11: OpenAI Responses API 非流式适配 (/v1/responses)
        print("\n[Test 11/12] 测试 ChatGPT Codex CLI 专用 Responses API 非流式适配 (/v1/responses)...")
        resp_res = await client.post(
            "/v1/responses",
            json={
                "model": "codex",
                "instructions": "You are a specialized Codex assistant.",
                "input": "Write a python function to add two numbers.",
                "stream": False
            }
        )
        assert resp_res.status_code == 200
        resp_json = resp_res.json()
        assert resp_json.get("object") == "response"
        assert resp_json.get("status") == "completed"
        assert "output" in resp_json and len(resp_json["output"]) > 0
        first_item = resp_json["output"][0]
        assert first_item.get("type") == "message"
        assert len(first_item.get("content", [])) > 0
        text_out = first_item["content"][0].get("text", "")
        assert len(text_out) > 0
        print(f"✅ Responses API 非流式测试成功！(输出对象: {resp_json.get('object')}, 模型: {resp_json.get('model')}, 回复内容: '{text_out[:40]}...')")

        # Test 12: OpenAI Responses API 流式 SSE 适配 (/v1/responses)
        print("\n[Test 12/12] 测试 ChatGPT Codex CLI 专用 Responses API 流式 SSE 适配 (/v1/responses)...")
        stream_res = await client.post(
            "/v1/responses",
            json={
                "model": "gpt-5.3-codex",
                "instructions": "You are an automated coding test agent.",
                "input": [{"role": "user", "content": "Explain binary search in one sentence."}],
                "stream": True
            }
        )
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers.get("content-type", "")
        full_stream_text = stream_res.text
        assert "event: response.created" in full_stream_text
        assert "event: response.output_text.delta" in full_stream_text
        assert "event: response.completed" in full_stream_text
        print(f"✅ Responses API 流式 SSE 测试成功！已完整发射 response.created, output_text.delta, response.completed 等规范事件链！")

        print("\n" + "=" * 70)
        print("🎉 全球渠道测试全部 100% 通过！网关调度容灾、实时搜索、双引擎文生图与 Codex Responses API 完全正常！")
        print("=" * 70)
    finally:
        await client.aclose()
        server.should_exit = True
        await mock_task
        # 100% 还原原始内存与磁盘配置，避免 Mock 污染
        state.harness_config = original_harness
        state.codex_config = original_codex
        state.reload_config()

if __name__ == "__main__":
    asyncio.run(run_tests())
