"""长静默流式连续性回归测试

复现并守护「Codex 客户端执行一段就停止」的根因：上游在两次分块之间静默数秒
（深度思考 / 长补丁生成时极常见）时，网关必须继续转发后续内容，而不是把连接
当成已结束而静默截断。
"""
import os
import sys
import time
import json
import asyncio
import copy
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
from gateway import app_codex, state

# 上游两次分块之间的静默时长，必须大于网关 5s 的空闲保活阈值
UPSTREAM_IDLE_GAP = 7.0

mock_app = FastAPI()


@mock_app.post("/mock-slow/chat/completions")
async def mock_slow_stream(request: Request):
    body = await request.json()
    model = body.get("model")

    def chunk(delta):
        obj = {
            "id": "chatcmpl-slow-mock",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}]
        }
        return f"data: {json.dumps(obj)}\n\n".encode("utf-8")

    async def stream_data():
        yield chunk({"content": "Part-A"})
        # 模拟上游长时间思考 / 生成超长补丁时的静默期
        await asyncio.sleep(UPSTREAM_IDLE_GAP)
        yield chunk({"content": "Part-B"})
        yield chunk({
            "tool_calls": [{
                "index": 0,
                "id": "call_slow_1",
                "type": "function",
                "function": {"name": "exec_command", "arguments": '{"cmd":"ls"}'}
            }]
        })
        yield b"data: [DONE]\n\n"

    return StreamingResponse(stream_data(), media_type="text/event-stream")


async def run_tests():
    print("=" * 70)
    print("🧪 上游长静默流式连续性回归测试 (Responses API / Codex 通道)...")
    print("=" * 70)

    original_codex = copy.deepcopy(state.codex_config)

    config = uvicorn.Config(mock_app, host="127.0.0.1", port=8998, log_level="warning")
    server = uvicorn.Server(config)
    mock_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.5)

    mock_provider = {
        "name": "Mock-Slow-Upstream",
        "enabled": True,
        "priority": 9999,
        "base_url": "http://127.0.0.1:8998/mock-slow",
        "api_key": "mock-slow-key",
        "models": [
            {"id": "gpt-5.3-codex", "upstream_model": "mock-slow"},
            {"id": "codex", "upstream_model": "mock-slow"},
            {"id": "auto", "upstream_model": "mock-slow"}
        ]
    }
    state.codex_config["providers"].insert(0, copy.deepcopy(mock_provider))
    state._init_stats()

    transport = httpx.ASGITransport(app=app_codex)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=60.0)

    try:
        print(f"\n[Test 1/2] /v1/responses 流式：上游中途静默 {UPSTREAM_IDLE_GAP}s 后仍须完整送达...")
        events = []
        raw = []
        async with client.stream(
            "POST",
            "/v1/responses",
            json={
                "model": "gpt-5.3-codex",
                "instructions": "You are Codex.",
                "input": [{"type": "message", "role": "user", "content": "go"}],
                "tools": [{"type": "function", "name": "exec_command", "parameters": {"type": "object"}}],
                "stream": True
            }
        ) as res:
            assert res.status_code == 200, res.status_code
            async for line in res.aiter_lines():
                raw.append(line)
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except Exception:
                        pass

        types = [e.get("type") for e in events]
        text = "".join(e.get("delta", "") for e in events if e.get("type") == "response.output_text.delta")
        completed = [e for e in events if e.get("type") == "response.completed"]
        tool_items = [
            item for e in events if e.get("type") == "response.output_item.done"
            for item in [e.get("item", {})] if item.get("type") == "function_call"
        ]

        print(f"   收到事件类型: {types}")
        print(f"   聚合文本: '{text}'")

        assert "Part-A" in text, "静默前的内容丢失"
        assert "Part-B" in text, f"静默后的内容被截断 (实际收到: '{text}')"
        assert tool_items, "静默后的工具调用被截断"
        assert tool_items[0]["name"] == "exec_command"
        assert json.loads(tool_items[0]["arguments"])["cmd"] == "ls"
        assert completed, "缺少 response.completed 终结事件"
        assert "response.failed" not in types
        assert any(l.startswith(": keepalive") for l in raw), "静默期间未注入 SSE 保活"
        print("✅ 长静默后文本与工具调用均完整送达，且发射了 response.completed！")

        print(f"\n[Test 2/2] /v1/chat/completions 流式：同样的静默不得截断 Harness 通道...")
        contents = []
        tool_seen = False
        async with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gpt-5.3-codex",
                "messages": [{"role": "user", "content": "go"}],
                "tools": [{"type": "function", "function": {"name": "exec_command", "parameters": {"type": "object"}}}],
                "stream": True
            }
        ) as res:
            assert res.status_code == 200, res.status_code
            async for line in res.aiter_lines():
                if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                    continue
                try:
                    obj = json.loads(line[6:])
                except Exception:
                    continue
                for ch in obj.get("choices", []):
                    delta = ch.get("delta", {})
                    if delta.get("content"):
                        contents.append(delta["content"])
                    if delta.get("tool_calls"):
                        tool_seen = True

        joined = "".join(contents)
        print(f"   聚合文本: '{joined}'")
        assert "Part-A" in joined and "Part-B" in joined, f"Chat Completions 流被截断 (实际收到: '{joined}')"
        assert tool_seen, "Chat Completions 工具调用被截断"
        print("✅ Chat Completions 通道同样完整送达！")

        print("\n" + "=" * 70)
        print("🎉 全部流式连续性测试通过！")
        print("=" * 70)
    finally:
        await client.aclose()
        state.codex_config = original_codex
        state._init_stats()
        server.should_exit = True
        await mock_task


if __name__ == "__main__":
    asyncio.run(run_tests())
