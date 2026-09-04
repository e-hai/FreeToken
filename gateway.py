import os
import time
import json
import shutil
import logging
import asyncio
import urllib.parse
from typing import Dict, List, Any, Optional
import yaml
import httpx
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Gateway")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_config(config: dict, force_key_updates: Optional[dict] = None):
    if os.path.exists(CONFIG_PATH):
        try:
            shutil.copy2(CONFIG_PATH, f"{CONFIG_PATH}.bak")
        except Exception as e:
            logger.warning(f"Backup config file failed: {e}")

    existing_keys = {}
    existing_enabled = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                disk_cfg = yaml.safe_load(f) or {}
                for p in disk_cfg.get("providers", []):
                    p_name = p.get("name")
                    key = (p.get("api_key") or "").strip()
                    if key and not key.startswith("YOUR_"):
                        existing_keys[p_name] = key
                        existing_enabled[p_name] = p.get("enabled", False)
        except Exception as e:
            logger.warning(f"Read existing keys for merge protection error: {e}")

    for p in config.get("providers", []):
        p_name = p.get("name")
        if force_key_updates and p_name in force_key_updates:
            p["api_key"] = force_key_updates[p_name]
            if p["api_key"] and not p["api_key"].startswith("YOUR_"):
                p["enabled"] = True
        else:
            cur_key = (p.get("api_key") or "").strip()
            if (not cur_key or cur_key.startswith("YOUR_")) and p_name in existing_keys:
                p["api_key"] = existing_keys[p_name]
                if p_name in existing_enabled:
                    p["enabled"] = existing_enabled[p_name]

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    logger.info("Config saved successfully.")

app = FastAPI(title="Free Token Aggregator Gateway", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GatewayState:
    def __init__(self):
        self.config = load_config()
        self.stats = {
            "total_requests": 0,
            "success_requests": 0,
            "failed_requests": 0,
            "failover_events": 0,
            "tier_fallback_events": 0,
            "total_latency_sum": 0,
            "provider_stats": {}
        }
        self.request_logs = []
        self.tier_indices = {}
        self.start_time = time.time()
        self.provider_cooldowns = {}  # {provider_name: expire_time}
        self.model_cooldowns = {}     # {f"{provider_name}:{model_name}": expire_time}
        self._init_stats()

    def _init_stats(self):
        for p in self.config.get("providers", []):
            name = p.get("name")
            if name not in self.stats["provider_stats"]:
                self.stats["provider_stats"][name] = {
                    "calls": 0,
                    "success": 0,
                    "errors": 0,
                    "last_error": "",
                    "last_latency_ms": 0,
                    "status": "Active" if p.get("enabled") else "Disabled"
                }

    def add_log(self, entry: dict):
        self.request_logs.insert(0, entry)
        if len(self.request_logs) > 200:
            self.request_logs.pop()

    def reload_config(self):
        self.config = load_config()
        self._init_stats()

state = GatewayState()

def is_model_vision_capable(model_name: str) -> bool:
    m_lower = model_name.lower()
    vision_kws = ["gemini", "vision", "vl", "omni", "4o", "pixtral", "image", "visual"]
    non_vision_kws = ["gpt-oss", "qwen3.8", "qwen3.6", "nemotron-3-ultra", "nemotron-3.5", "compound", "north-mini-code", "inkling", "deepseek"]
    if any(nv in m_lower for nv in non_vision_kws):
        return False
    return any(vk in m_lower for vk in vision_kws)

def extract_tool_schemas(tools: list) -> dict:
    schemas = {}
    if not isinstance(tools, list):
        return schemas
    for t in tools:
        if not isinstance(t, dict):
            continue
        func = t.get("function") or t
        name = func.get("name")
        params = func.get("parameters") or {}
        if name and isinstance(params, dict):
            schemas[name] = {
                "required": params.get("required", []),
                "properties": params.get("properties", {})
            }
    return schemas

def repair_tool_call_arguments(func_name: str, args_str: str, tool_schemas: dict) -> str:
    if not func_name or not args_str:
        return args_str
    
    schema = tool_schemas.get(func_name) if tool_schemas else None
    required_fields = schema.get("required", []) if schema else []
    properties = schema.get("properties", {}) if schema else {}

    try:
        args = json.loads(args_str)
        if not isinstance(args, dict):
            return args_str
    except Exception:
        return args_str

    modified = False

    # 1. 根据 schema required 严格自愈
    if required_fields:
        for req in required_fields:
            if req not in args:
                # 优先大小写模糊匹配（例如 Description vs description）
                matched_key = next((k for k in args if k.lower() == req.lower()), None)
                if matched_key:
                    args[req] = args[matched_key]
                    modified = True
                    continue

                # 智能推断缺失字段的默认合规值
                prop_def = properties.get(req, {})
                prop_type = (prop_def.get("type") or "string").lower()

                if "string" in prop_type:
                    if req.lower() in ["description", "desc"]:
                        cmd_val = str(args.get("command") or args.get("CommandLine") or func_name)[:60]
                        args[req] = f"Run: {cmd_val}"
                    elif req.lower() in ["toolaction", "action"]:
                        args[req] = "Executing action"
                    elif req.lower() in ["toolsummary", "summary"]:
                        args[req] = "Tool execution"
                    elif req.lower() in ["cwd", "directory"]:
                        args[req] = "."
                    else:
                        args[req] = prop_def.get("description", "") or "default"
                elif "bool" in prop_type:
                    args[req] = False
                elif "int" in prop_type or "num" in prop_type:
                    args[req] = 5000 if ("wait" in req.lower() or "timeout" in req.lower()) else 0
                elif "array" in prop_type or "list" in prop_type:
                    args[req] = []
                elif "object" in prop_type:
                    args[req] = {}
                else:
                    args[req] = "default"
                modified = True

    # 2. 针对命令执行类工具（bash / run_command / execute_command）普遍要求的 description 顽疾进行双重保底
    if any(k in func_name.lower() for k in ["command", "bash", "exec", "sh", "terminal"]) or "command" in args or "CommandLine" in args:
        if "description" not in args and "desc" not in args:
            cmd_val = str(args.get("command") or args.get("CommandLine") or func_name)[:60]
            args["description"] = f"Run: {cmd_val}"
            modified = True

    if modified:
        logger.info(f"🛠️ [工具调用自愈引擎] 补齐模型遗漏必填字段: {func_name} -> {args}")
        return json.dumps(args, ensure_ascii=False)
    return args_str

# 路由计划构建：仅保留 auto 与 deepseek-v4-flash
def build_tiered_execution_plan(requested_model: str, has_image: bool = False) -> List[Dict[str, Any]]:
    req_clean = requested_model.lower().strip()
    providers = state.config.get("providers", [])
    active_providers = [
        p for p in providers 
        if p.get("enabled") and p.get("api_key") and not p.get("api_key", "").startswith("YOUR_")
    ]
    # 按大厂优先级权重排序 (Google 100 > NVIDIA 95 > Groq 90 > OpenRouter 85 > 中转 40)
    active_providers.sort(key=lambda p: p.get("priority", 50), reverse=True)

    # 1. 当请求 "auto" 时，执行跨大厂多级降级天梯
    if req_clean in ["auto", "default"]:
        ladders_config = state.config.get("fallback_ladders", {})
        ladder = ladders_config.get("auto", [])
        plan_tiers = []
        for tier_info in ladder:
            tier_name = tier_info.get("tier", "Fallback Tier")
            target_models = tier_info.get("models", [])
            
            tier_candidates = []
            for target_m in target_models:
                t_lower = target_m.lower()
                for p in active_providers:
                    for m in p.get("models", []):
                        mid = m.get("id", "").lower()
                        up_name = m.get("upstream_model", mid)
                        if t_lower == mid or t_lower in mid or mid in t_lower or t_lower == up_name.lower():
                            item = (p, up_name)
                            if item not in tier_candidates:
                                tier_candidates.append(item)

            if has_image:
                tier_candidates = [item for item in tier_candidates if is_model_vision_capable(item[1])]

            if tier_candidates:
                tier_candidates.sort(key=lambda item: item[0].get("priority", 50), reverse=True)
                plan_tiers.append({
                    "tier_name": tier_name,
                    "candidates": tier_candidates
                })
        return plan_tiers

    # 2. 当请求 "deepseek-v4-flash"（或指定模型）时，大厂优先轮询目标模型，并追加紧急高可用保活层
    aliases = state.config.get("model_aliases", {})
    alias_target = aliases.get(requested_model, aliases.get(req_clean, requested_model))
    target_keys = {
        requested_model.lower(),
        req_clean,
        str(alias_target).lower()
    }
    if "deepseek" in req_clean:
        target_keys.update([
            "deepseek-ai/deepseek-v4-flash-0731",
            "deepseek-ai/deepseek-v4-flash",
            "deepseek/deepseek-v4-flash-0731",
            "deepseek-v4-flash-0731",
            "deepseek-v4-flash",
            "deepseek-v4"
        ])

    exact_candidates = []
    fuzzy_candidates = []
    for p in active_providers:
        for m in p.get("models", []):
            mid = m.get("id", "").lower()
            up_name = m.get("upstream_model", mid)
            up_lower = up_name.lower()
            
            if mid in target_keys or up_lower in target_keys:
                item = (p, up_name)
                if item not in exact_candidates:
                    exact_candidates.append(item)
            elif any(k in up_lower or (len(up_lower) > 4 and up_lower in k) for k in target_keys):
                item = (p, up_name)
                if item not in fuzzy_candidates and item not in exact_candidates:
                    fuzzy_candidates.append(item)

    exact_candidates.sort(key=lambda item: item[0].get("priority", 50), reverse=True)
    fuzzy_candidates.sort(key=lambda item: item[0].get("priority", 50), reverse=True)
    
    # 结合精准大厂渠道与备用兼容渠道 (例如 NVIDIA NIM 优先，OpenRouter 兜底)
    candidates = list(exact_candidates)
    for c in fuzzy_candidates:
        if c not in candidates:
            candidates.append(c)

    if not candidates:
        for p in active_providers:
            up_target = alias_target if alias_target != requested_model else requested_model
            item = (p, up_target)
            if item not in candidates:
                candidates.append(item)
        candidates.sort(key=lambda item: item[0].get("priority", 50), reverse=True)

    plans = [{
        "tier_name": f"专属渠道轮询: {requested_model}",
        "candidates": candidates
    }]

    # 为保障长流程 Agent (如 30+ 轮自动化编码任务) 绝不因上游单模型瞬时超载崩溃，追加紧急保活兜底层
    emergency_candidates = []
    emergency_target_models = [
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "gemini-3.5-flash"
    ]
    for target_m in emergency_target_models:
        t_lower = target_m.lower()
        for p in active_providers:
            for m in p.get("models", []):
                mid = m.get("id", "").lower()
                up_name = m.get("upstream_model", mid)
                if t_lower == mid or t_lower == up_name.lower() or t_lower in mid:
                    item = (p, up_name)
                    if item not in candidates and item not in emergency_candidates:
                        emergency_candidates.append(item)
    if emergency_candidates:
        emergency_candidates.sort(key=lambda item: item[0].get("priority", 50), reverse=True)
        plans.append({
            "tier_name": f"长流程高可用保活兜底层 (Groq LPU / Nemotron 550B 极速接管)",
            "candidates": emergency_candidates
        })
    return plans

# 1. 深度复刻 Linear.app 官方设计系统控制台（精简双模型版）
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    state._init_stats()
    providers_json = json.dumps(state.config.get("providers", []))
    stats_json = json.dumps(state.stats)
    
    total_calls = state.stats["total_requests"]
    success_calls = state.stats["success_requests"]
    success_rate = f"{(success_calls / total_calls * 100):.1f}%" if total_calls > 0 else "100.0%"
    avg_latency = f"{(state.stats.get('total_latency_sum', 0) / success_calls):.0f}ms" if success_calls > 0 else "0ms"

    html = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Linear Gateway · Free Token 调度中心 (精简版)</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-body: #08090c;
                --bg-card: rgba(18, 20, 26, 0.75);
                --bg-card-solid: #111318;
                --bg-card-hover: rgba(26, 29, 38, 0.9);
                --border-subtle: rgba(255, 255, 255, 0.06);
                --border-card: rgba(255, 255, 255, 0.08);
                --border-focus: rgba(94, 106, 210, 0.6);
                
                --text-primary: #f2f3f5;
                --text-secondary: #8a8f98;
                --text-tertiary: #5c6068;
                
                --linear-brand: #5e6ad2;
                --linear-brand-hover: #6875e5;
                --linear-gradient: linear-gradient(135deg, #5e6ad2 0%, #818cf8 100%);
                --glow-brand: rgba(94, 106, 210, 0.25);
                
                --accent-emerald: #10b981;
                --accent-amber: #f59e0b;
                --accent-rose: #f43f5e;
                --accent-cyan: #38bdf8;
                --accent-violet: #a855f7;
            }}

            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: var(--bg-body);
                background-image: 
                    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(94, 106, 210, 0.16), transparent),
                    radial-gradient(circle at 10% 20%, rgba(56, 189, 248, 0.04), transparent 40%),
                    radial-gradient(circle at 90% 80%, rgba(168, 85, 247, 0.04), transparent 40%);
                background-attachment: fixed;
                color: var(--text-primary);
                min-height: 100vh;
                padding: 28px 24px 80px;
                letter-spacing: -0.012em;
                -webkit-font-smoothing: antialiased;
            }}

            ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
            ::-webkit-scrollbar-track {{ background: transparent; }}
            ::-webkit-scrollbar-thumb {{ background: rgba(255, 255, 255, 0.12); border-radius: 3px; }}
            ::-webkit-scrollbar-thumb:hover {{ background: rgba(255, 255, 255, 0.25); }}

            .container {{ max-width: 1360px; margin: 0 auto; }}

            .svg-icon {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 15px;
                height: 15px;
                flex-shrink: 0;
            }}
            .svg-icon svg {{
                width: 100%;
                height: 100%;
                stroke-width: 1.8;
                stroke: currentColor;
                fill: none;
                stroke-linecap: round;
                stroke-linejoin: round;
            }}
            .svg-icon-lg {{ width: 18px; height: 18px; }}
            .svg-icon-sm {{ width: 13px; height: 13px; }}

            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 28px;
                padding: 6px 0;
            }}
            .brand {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .brand-icon {{
                width: 36px;
                height: 36px;
                border-radius: 10px;
                background: linear-gradient(135deg, #5e6ad2 0%, #38bdf8 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 0 20px rgba(94, 106, 210, 0.35);
                color: white;
            }}
            .brand-title {{
                font-size: 18px;
                font-weight: 700;
                color: var(--text-primary);
                letter-spacing: -0.025em;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            .brand-badge {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid var(--border-card);
                color: var(--text-secondary);
                font-size: 11px;
                font-weight: 500;
                padding: 2px 7px;
                border-radius: 6px;
            }}
            .badge-priority {{
                background: rgba(245, 158, 11, 0.12);
                border: 1px solid rgba(245, 158, 11, 0.3);
                color: #fbbf24;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 8px;
                border-radius: 6px;
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }}

            .live-status {{
                display: inline-flex;
                align-items: center;
                gap: 6px;
                background: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.2);
                color: #34d399;
                padding: 3px 9px;
                border-radius: 20px;
                font-size: 11px;
                font-weight: 500;
            }}
            .pulse-dot {{
                width: 6px;
                height: 6px;
                background: #10b981;
                border-radius: 50%;
                box-shadow: 0 0 8px #10b981;
                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; transform: scale(1); }}
                50% {{ opacity: .4; transform: scale(.85); }}
            }}

            .header-actions {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}

            .btn {{
                background: rgba(255, 255, 255, 0.05);
                color: var(--text-primary);
                border: 1px solid var(--border-card);
                padding: 6px 13px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                transition: all 0.15s ease;
                letter-spacing: -0.01em;
            }}
            .btn:hover {{
                background: rgba(255, 255, 255, 0.09);
                border-color: rgba(255, 255, 255, 0.15);
                transform: translateY(-1px);
            }}
            .btn:hover .icon-rotate {{
                transform: rotate(180deg);
                transition: transform 0.4s ease;
            }}
            .btn:active {{ transform: translateY(0); }}
            .btn-primary {{
                background: var(--linear-brand);
                border-color: rgba(255, 255, 255, 0.12);
                color: white;
                box-shadow: 0 0 16px var(--glow-brand);
            }}
            .btn-primary:hover {{
                background: var(--linear-brand-hover);
                box-shadow: 0 0 24px rgba(94, 106, 210, 0.4);
            }}
            .btn-danger {{
                background: rgba(244, 63, 94, 0.08);
                border-color: rgba(244, 63, 94, 0.2);
                color: #fb7185;
            }}
            .btn-danger:hover {{
                background: rgba(244, 63, 94, 0.2);
                border-color: rgba(244, 63, 94, 0.4);
                color: white;
            }}
            .spin {{
                animation: spin 1s linear infinite;
            }}
            @keyframes spin {{
                from {{ transform: rotate(0deg); }}
                to {{ transform: rotate(360deg); }}
            }}

            .metrics-grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 14px;
                margin-bottom: 24px;
            }}
            .metric-box {{
                background: var(--bg-card);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border: 1px solid var(--border-card);
                border-radius: 12px;
                padding: 16px 18px;
                position: relative;
                transition: border-color 0.2s, background-color 0.2s;
            }}
            .metric-box:hover {{
                border-color: rgba(255, 255, 255, 0.15);
                background: var(--bg-card-hover);
            }}
            .metric-top {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }}
            .metric-label {{
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-secondary);
                display: flex;
                align-items: center;
                gap: 6px;
            }}
            .metric-val {{
                font-size: 26px;
                font-weight: 700;
                letter-spacing: -0.03em;
                color: var(--text-primary);
                font-feature-settings: "cv02", "cv03", "cv04", "cv11";
            }}
            .metric-foot {{
                font-size: 11px;
                color: var(--text-tertiary);
                margin-top: 4px;
            }}

            .card {{
                background: var(--bg-card);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border: 1px solid var(--border-card);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
                position: relative;
            }}
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 16px;
                flex-wrap: wrap;
                gap: 10px;
            }}
            .card-title {{
                font-size: 14px;
                font-weight: 600;
                color: var(--text-primary);
                letter-spacing: -0.01em;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            .card-subtitle {{
                font-size: 12px;
                color: var(--text-secondary);
            }}

            /* 精简展示卡片 */
            .models-showcase {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 14px;
            }}
            .model-card {{
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid var(--border-subtle);
                border-radius: 10px;
                padding: 16px 18px;
                transition: all 0.2s ease;
            }}
            .model-card:hover {{
                border-color: rgba(94, 106, 210, 0.4);
                background: rgba(255, 255, 255, 0.04);
            }}
            .model-card-top {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }}
            .model-card-id {{
                font-family: 'JetBrains Mono', monospace;
                font-size: 14px;
                font-weight: 700;
                color: var(--text-primary);
            }}
            .model-card-desc {{
                font-size: 12px;
                color: var(--text-secondary);
                line-height: 1.5;
            }}

            .toolbar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 14px;
                gap: 12px;
                flex-wrap: wrap;
            }}
            .search-box {{
                position: relative;
                width: 260px;
            }}
            .search-input {{
                width: 100%;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid var(--border-card);
                color: var(--text-primary);
                padding: 7px 12px 7px 32px;
                border-radius: 8px;
                font-size: 12px;
                outline: none;
                transition: all 0.15s ease;
            }}
            .search-input:focus {{
                border-color: var(--border-focus);
                background: rgba(255, 255, 255, 0.06);
                box-shadow: 0 0 0 3px rgba(94, 106, 210, 0.15);
            }}
            .search-icon {{
                position: absolute;
                left: 10px;
                top: 50%;
                transform: translateY(-50%);
                color: var(--text-tertiary);
                display: flex;
                align-items: center;
            }}
            
            .segmented-control {{
                display: flex;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid var(--border-card);
                padding: 2px;
                border-radius: 8px;
                gap: 2px;
            }}
            .segmented-btn {{
                background: transparent;
                border: none;
                color: var(--text-secondary);
                padding: 5px 11px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.15s ease;
                display: inline-flex;
                align-items: center;
                gap: 5px;
            }}
            .segmented-btn.active {{
                background: rgba(255, 255, 255, 0.08);
                color: var(--text-primary);
                box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            }}
            .segmented-btn:hover:not(.active) {{
                color: var(--text-primary);
            }}

            .table-container {{
                overflow-x: auto;
                border: 1px solid var(--border-subtle);
                border-radius: 10px;
                background: rgba(10, 11, 15, 0.4);
            }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 12px; }}
            th {{
                background: rgba(255, 255, 255, 0.02);
                padding: 10px 14px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-secondary);
                border-bottom: 1px solid var(--border-subtle);
            }}
            td {{
                padding: 11px 14px;
                border-bottom: 1px solid var(--border-subtle);
                color: var(--text-secondary);
                vertical-align: middle;
            }}
            tr:hover td {{
                background: rgba(255, 255, 255, 0.02);
                color: var(--text-primary);
            }}

            .switch {{
                position: relative;
                display: inline-block;
                width: 36px;
                height: 20px;
            }}
            .switch input {{ opacity: 0; width: 0; height: 0; }}
            .slider {{
                position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
                background-color: #272a34; transition: .2s; border-radius: 20px;
            }}
            .slider:before {{
                position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px;
                background-color: #8a8f98; transition: .2s; border-radius: 50%;
            }}
            input:checked + .slider {{ background-color: var(--linear-brand); }}
            input:checked + .slider:before {{ transform: translateX(16px); background-color: #ffffff; }}

            .key-group {{ display: flex; align-items: center; gap: 4px; }}
            .key-input {{
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid var(--border-card);
                color: var(--text-primary);
                padding: 5px 8px;
                border-radius: 6px;
                font-family: 'JetBrains Mono', monospace;
                font-size: 11px;
                width: 150px;
                outline: none;
            }}
            .key-input:focus {{ border-color: var(--border-focus); }}

            .badge {{
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10.5px;
                font-weight: 500;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid var(--border-subtle);
                color: var(--text-secondary);
            }}
            .badge-model {{
                background: rgba(94, 106, 210, 0.08);
                border-color: rgba(94, 106, 210, 0.25);
                color: #a5b4fc;
                font-family: 'JetBrains Mono', monospace;
                font-size: 10px;
                margin: 1px;
            }}
            .badge-success {{
                background: rgba(16, 185, 129, 0.08);
                border-color: rgba(16, 185, 129, 0.25);
                color: #34d399;
            }}
            .badge-tier {{
                background: rgba(168, 85, 247, 0.08);
                border-color: rgba(168, 85, 247, 0.25);
                color: #c084fc;
            }}

            .trace-step {{
                display: inline-flex;
                align-items: center;
                gap: 4px;
                font-size: 10.5px;
                background: rgba(255, 255, 255, 0.02);
                padding: 3px 6px;
                border-radius: 4px;
                border: 1px solid var(--border-subtle);
                margin: 1px 0;
            }}

            .snippet-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 12px;
            }}
            .snippet-box {{
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid var(--border-subtle);
                padding: 14px;
                border-radius: 8px;
                font-family: 'JetBrains Mono', monospace;
                font-size: 11px;
                line-height: 1.6;
                color: var(--text-secondary);
            }}
            .snippet-box strong {{ color: var(--text-primary); }}

            #toast {{
                position: fixed;
                bottom: 24px;
                right: 24px;
                background: #151821;
                color: var(--text-primary);
                border: 1px solid rgba(255, 255, 255, 0.12);
                padding: 12px 18px;
                border-radius: 8px;
                box-shadow: 0 12px 30px rgba(0,0,0,0.6);
                display: none;
                align-items: center;
                gap: 8px;
                border-left: 3px solid var(--linear-brand);
                z-index: 2000;
                font-size: 12px;
                font-weight: 500;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="brand">
                    <div class="brand-icon">
                        <span class="svg-icon svg-icon-lg">
                            <svg viewBox="0 0 24 24">
                                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                            </svg>
                        </span>
                    </div>
                    <div>
                        <div class="brand-title">
                            Linear Gateway
                            <span class="brand-badge">Free Token 调度中心</span>
                            <span class="badge-priority">
                                <span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg></span>
                                官方大厂优先调度
                            </span>
                        </div>
                    </div>
                </div>

                <div class="header-actions">
                    <div class="live-status">
                        <span class="pulse-dot"></span>
                        <span>精简核心双模型就绪</span>
                    </div>
                    <button class="btn" onclick="testCascadingSimulator()">
                        <span class="svg-icon"><svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg></span>
                        <span>演练 Auto 降级</span>
                    </button>
                    <button class="btn" onclick="enableAllConfigured()">
                        <span class="svg-icon"><svg viewBox="0 0 24 24"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line></svg></span>
                        <span>全部启用</span>
                    </button>
                    <button class="btn btn-primary" onclick="location.reload()">
                        <span class="svg-icon icon-rotate"><svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg></span>
                        <span>刷新</span>
                    </button>
                </div>
            </div>

            <!-- Hero Metrics Grid -->
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-top">
                        <span class="metric-label">
                            <span class="svg-icon" style="color:var(--linear-brand);"><svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg></span>
                            Total Requests
                        </span>
                        <span class="svg-icon" style="color:var(--text-tertiary);"><svg viewBox="0 0 24 24"><line x1="7" y1="17" x2="17" y2="7"></line><polyline points="7 7 17 7 17 17"></polyline></svg></span>
                    </div>
                    <div class="metric-val">{total_calls}</div>
                    <div class="metric-foot">大厂优先 · 精确调度</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top">
                        <span class="metric-label">
                            <span class="svg-icon" style="color:var(--accent-emerald);"><svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg></span>
                            Success Rate
                        </span>
                        <span class="svg-icon" style="color:var(--accent-emerald);"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"></circle></svg></span>
                    </div>
                    <div class="metric-val" style="color:var(--accent-emerald);">{success_rate}</div>
                    <div class="metric-foot">成功请求 {success_calls} 次</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top">
                        <span class="metric-label">
                            <span class="svg-icon" style="color:var(--accent-violet);"><svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg></span>
                            Auto Fallbacks
                        </span>
                        <span class="svg-icon" style="color:var(--accent-violet);"><svg viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
                    </div>
                    <div class="metric-val" style="color:var(--accent-violet);">{state.stats.get("tier_fallback_events", 0)}</div>
                    <div class="metric-foot">仅在 Auto 模式下触发跨模型降级</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top">
                        <span class="metric-label">
                            <span class="svg-icon" style="color:var(--accent-amber);"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg></span>
                            Avg Latency
                        </span>
                        <span class="svg-icon" style="color:var(--accent-amber);"><svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg></span>
                    </div>
                    <div class="metric-val" style="color:var(--accent-amber);">{avg_latency}</div>
                    <div class="metric-foot">Google / Groq 直连极速 ~700ms</div>
                </div>
            </div>

            <!-- 🎯 保留的核心双模型展示卡片 -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span class="svg-icon" style="color:var(--linear-brand);"><svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg></span>
                        <span>Gateway Core Models · 网关保留的核心模型 (2 个)</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                        <span class="card-subtitle" style="margin:0;">DeepSeek-Harness 与客户端暴露模型</span>
                        <button class="btn btn-primary" id="btn-update-models-top" onclick="updateLatestModels()" style="padding:4px 12px;font-size:11.5px;font-weight:600;display:inline-flex;align-items:center;gap:6px;" title="从全网与各渠道获取最新最强免费模型并写入配置">
                            <span class="svg-icon svg-icon-sm" id="update-models-icon-top"><svg viewBox="0 0 24 24"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path></svg></span>
                            <span id="update-models-text-top">获取最新最强免费模型</span>
                        </button>
                    </div>
                </div>
                <div class="models-showcase">
                    <div class="model-card" style="border-color: rgba(94, 106, 210, 0.4); background: rgba(94, 106, 210, 0.04);">
                        <div class="model-card-top">
                            <div class="model-card-id" style="color: #a5b4fc;">✨ auto (推荐默认)</div>
                            <span class="badge badge-priority">大厂优先 · 多级智能降级</span>
                        </div>
                        <div class="model-card-desc">
                            <strong>全网自适应降级：</strong>优先直连 Google Gemini 3.5 旗舰与 NVIDIA 70B 满血推理，遇限流毫秒级切换 Groq LPU 极速芯片 (700ms) 及 OpenRouter 免费池，保障 100% 成功率。
                        </div>
                    </div>
                    <div class="model-card" style="border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.04);">
                        <div class="model-card-top">
                            <div class="model-card-id" style="color: #34d399;">⚡ deepseek-v4-flash</div>
                            <span class="badge badge-success">同模型跨渠道轮询</span>
                        </div>
                        <div class="model-card-desc">
                            <strong>专属指定模型：</strong>严格锁定 DeepSeek 官方 V4-Flash 极速推理架构，仅在支持该模型的各渠道商间轮询（大厂优先）；若全部渠道均不可用则直接报错，绝不跨模型降级。
                        </div>
                    </div>
                </div>
            </div>

            <!-- 📜 实时调用链路与模型追踪审计 -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span class="svg-icon" style="color:var(--accent-emerald);"><svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg></span>
                        <span>Live Request Traces</span>
                        <span class="badge badge-success">
                            <span class="pulse-dot" style="width:5px;height:5px;"></span>
                            实时监听中
                        </span>
                    </div>
                    <div style="display:flex;gap:6px;">
                        <button class="btn" style="padding:4px 10px;font-size:11px;" onclick="loadLogs()">
                            <span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg></span>
                            <span>刷新日志</span>
                        </button>
                        <button class="btn btn-danger" style="padding:4px 10px;font-size:11px;" onclick="clearLogs()">
                            <span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></span>
                            <span>清空</span>
                        </button>
                    </div>
                </div>

                <div class="table-container" style="max-height: 360px;">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:85px;">Time</th>
                                <th style="width:140px;">Client Model</th>
                                <th style="width:180px;">Routed Provider</th>
                                <th style="width:220px;">Upstream Model</th>
                                <th>Fallback Trace Steps</th>
                                <th style="width:85px;">Latency</th>
                                <th style="width:110px;">Status</th>
                            </tr>
                        </thead>
                        <tbody id="logs-table"></tbody>
                    </table>
                </div>
            </div>

            <!-- 📡 活跃渠道管理与在线测速 -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span class="svg-icon" style="color:var(--linear-brand);"><svg viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg></span>
                        <span>Active Providers (<span id="total-count">0</span>)</span>
                    </div>
                    <span class="card-subtitle">
                        <span class="svg-icon svg-icon-sm" style="color:var(--accent-emerald);"><svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg></span>
                        大厂优先置顶（Google 100 > NVIDIA 95 > Groq 90 > OpenRouter 85）
                    </span>
                </div>

                <div class="toolbar">
                    <div class="search-box">
                        <span class="search-icon svg-icon svg-icon-sm">
                            <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        </span>
                        <input type="text" id="search-box" class="search-input" placeholder="搜索渠道、模型 ID..." oninput="filterProviders()">
                    </div>
                    <div class="segmented-control">
                        <button class="segmented-btn active" onclick="setCategoryFilter('all', this)">全部</button>
                        <button class="segmented-btn" onclick="setCategoryFilter('enabled', this)">已开启</button>
                        <button class="segmented-btn" onclick="setCategoryFilter('全球大厂', this)">👑 全球大厂</button>
                        <button class="segmented-btn" onclick="setCategoryFilter('极速芯片', this)">⚡ 极速芯片</button>
                        <button class="segmented-btn" onclick="setCategoryFilter('全球聚合', this)">🌍 全球聚合</button>
                        <button class="segmented-btn" onclick="setCategoryFilter('出海中转', this)">出海中转</button>
                    </div>
                </div>

                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th style="width:60px;">Status</th>
                                <th style="width:200px;">Provider</th>
                                <th style="width:280px;">API Key</th>
                                <th>
                                    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                                        <span>Models</span>
                                        <button class="btn btn-primary" id="btn-update-models-th" onclick="updateLatestModels()" title="获取最新最强免费模型到配置" style="padding:2px 8px;font-size:10.5px;font-weight:600;display:inline-flex;align-items:center;gap:4px;">
                                            <span class="svg-icon svg-icon-sm" id="update-models-icon-th" style="width:11px;height:11px;"><svg viewBox="0 0 24 24"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path></svg></span>
                                            <span id="update-models-text-th">更新模型</span>
                                        </button>
                                    </div>
                                </th>
                                <th style="width:90px;">Calls</th>
                                <th style="width:170px;">Ping Test</th>
                                <th style="width:50px;">Action</th>
                            </tr>
                        </thead>
                        <tbody id="providers-table"></tbody>
                    </table>
                </div>
            </div>

            <!-- 🔌 配置指南 -->
            <div class="card">
                <div class="card-title" style="margin-bottom:12px;">
                    <span class="svg-icon" style="color:var(--linear-brand);"><svg viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg></span>
                    <span>Quick Setup & Client Integration</span>
                </div>
                <div class="snippet-grid">
                    <div class="snippet-box">
                        <strong style="color:var(--linear-brand);">DeepSeek-Harness / Web Client:</strong><br>
                        <strong>Base URL</strong>: http://127.0.0.1:{state.config['server']['port']}/v1<br>
                        <strong>API Key </strong>: free-token<br>
                        <strong>Available Models</strong>:<br>
                        &nbsp;&nbsp;1. <strong>auto</strong> (推荐：大厂优先 · 全网自适应降级)<br>
                        &nbsp;&nbsp;2. <strong>deepseek-v4-flash</strong> (DeepSeek 极速架构 · 同模型轮询)
                    </div>
                    <div class="snippet-box">
                        <strong style="color:var(--linear-brand);">Python / OpenAI SDK:</strong><br>
                        from openai import OpenAI<br>
                        client = OpenAI(base_url="http://127.0.0.1:{state.config['server']['port']}/v1", api_key="free-token")<br>
                        resp = client.chat.completions.create(model="auto", messages=[{{"role": "user", "content": "Hello!"}}])
                    </div>
                </div>
            </div>
        </div>

        <div id="toast"></div>

        <script>
            let providers = {providers_json};
            let stats = {stats_json};
            let currentCategory = "all";

            function showToast(msg, type = "info", duration = 3000) {{
                const t = document.getElementById("toast");
                t.innerHTML = msg;
                if (type === "success") {{
                    t.style.borderLeftColor = "var(--accent-emerald)";
                }} else if (type === "error") {{
                    t.style.borderLeftColor = "var(--accent-rose)";
                }} else {{
                    t.style.borderLeftColor = "var(--linear-brand)";
                }}
                t.style.display = "flex";
                if (window._toastTimer) clearTimeout(window._toastTimer);
                window._toastTimer = setTimeout(() => {{ t.style.display = "none"; }}, duration);
            }}

            function setCategoryFilter(cat, btn) {{
                currentCategory = cat;
                document.querySelectorAll(".segmented-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                filterProviders();
            }}

            function filterProviders() {{
                const query = document.getElementById("search-box").value.toLowerCase().trim();
                const filtered = providers.filter(p => {{
                    const matchCat = currentCategory === "all" || 
                                     (currentCategory === "enabled" && p.enabled) ||
                                     (p.category === currentCategory);
                    const matchQuery = !query || 
                                       p.name.toLowerCase().includes(query) ||
                                       (p.category && p.category.toLowerCase().includes(query)) ||
                                       (p.models || []).some(m => m.id.toLowerCase().includes(query) || (m.upstream_model && m.upstream_model.toLowerCase().includes(query)));
                    return matchCat && matchQuery;
                }});
                renderTable(filtered);
            }}

            function renderTable(list = providers) {{
                const tbody = document.getElementById("providers-table");
                document.getElementById("total-count").innerText = list.length;
                tbody.innerHTML = "";

                if (list.length === 0) {{
                    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-tertiary);padding:24px;">No matching providers found</td></tr>`;
                    return;
                }}

                list.forEach((p) => {{
                    const pStat = stats.provider_stats[p.name] || {{ calls: 0, success: 0, errors: 0, last_latency_ms: 0 }};
                    const modelsHtml = (p.models || []).slice(0, 4).map(m => `<span class="badge badge-model">${{m.id}}</span>`).join(" ");
                    const moreBadge = (p.models && p.models.length > 4) ? `<span class="badge badge-model" style="color:var(--linear-brand);">+${{p.models.length - 4}}</span>` : "";
                    const categoryBadge = p.category ? `<span class="badge">${{p.category}}</span>` : "";
                    
                    const isBigTech = (p.priority || 0) >= 90;
                    const rankBadge = isBigTech 
                        ? `<span class="badge-priority" style="font-size:9.5px;padding:1px 5px;">👑 优先 (P:${{p.priority || 50}})</span>` 
                        : `<span class="badge" style="font-size:9.5px;color:var(--text-tertiary);">P:${{p.priority || 50}}</span>`;

                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>
                            <label class="switch">
                                <input type="checkbox" ${{p.enabled ? "checked" : ""}} onchange="toggleProvider('${{p.name}}', this.checked)">
                                <span class="slider"></span>
                            </label>
                        </td>
                        <td>
                            <div style="font-weight:600;color:var(--text-primary);display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                                ${{p.name}}
                                ${{rankBadge}}
                            </div>
                        </td>
                        <td>
                            <div class="key-group">
                                <input type="password" id="key-${{p.name}}" class="key-input" value="${{p.api_key || ""}}" placeholder="填入 API Key">
                                <button class="btn" style="padding:4px 6px;" onclick="toggleKeyVisibility('${{p.name}}')" title="显示/隐藏">
                                    <span class="svg-icon svg-icon-sm" id="eye-icon-${{p.name}}"><svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg></span>
                                </button>
                                <button class="btn btn-primary" style="padding:4px 9px;font-size:11px;" onclick="saveKey('${{p.name}}')">
                                    <span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg></span>
                                    <span>保存</span>
                                </button>
                            </div>
                        </td>
                        <td>
                            <div style="display:flex;flex-wrap:wrap;align-items:center;">
                                ${{modelsHtml}} ${{moreBadge}}
                            </div>
                        </td>
                        <td>
                            <strong style="color:var(--text-primary);">${{pStat.calls}}</strong> / <span style="color:var(--accent-emerald);font-weight:600;">${{pStat.success}}</span>
                        </td>
                        <td>
                            <button class="btn" style="padding:4px 9px;font-size:11px;" id="test-btn-${{p.name}}" onclick="testProviderKey('${{p.name}}')">
                                <span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg></span>
                                <span>测速</span>
                            </button>
                            <span id="test-res-${{p.name}}" style="margin-left:6px;font-size:11px;"></span>
                        </td>
                        <td>
                            <button class="btn btn-danger" style="padding:4px 6px;" onclick="deleteProvider('${{p.name}}')" title="删除此渠道">
                                <span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></span>
                            </button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                }});
            }}

            function toggleKeyVisibility(name) {{
                const input = document.getElementById(`key-${{name}}`);
                const isPass = input.type === "password";
                input.type = isPass ? "text" : "password";
                const eyeSpan = document.getElementById(`eye-icon-${{name}}`);
                if (eyeSpan) {{
                    eyeSpan.innerHTML = isPass 
                        ? `<svg viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`
                        : `<svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
                }}
            }}

            async function toggleProvider(name, enabled) {{
                try {{
                    const res = await fetch("/api/providers/toggle", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ name, enabled }})
                    }});
                    const data = await res.json();
                    if (res.ok) {{
                        const p = providers.find(item => item.name === name);
                        if (p) p.enabled = enabled;
                        showToast(`[${{name}}] 已${{enabled ? "开启" : "禁用"}}`, "success");
                    }} else {{
                        showToast(`更新失败: ${{data.detail || "未知错误"}}`, "error");
                    }}
                }} catch (e) {{
                    showToast(`网络请求失败: ${{e.message}}`, "error");
                }}
            }}

            async function saveKey(name) {{
                const key = document.getElementById(`key-${{name}}`).value.trim();
                try {{
                    const res = await fetch("/api/providers/update_key", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ name, api_key: key }})
                    }});
                    const data = await res.json();
                    if (res.ok) {{
                        const p = providers.find(item => item.name === name);
                        if (p) {{
                            p.api_key = key;
                            if (key && !key.startswith("YOUR_")) p.enabled = true;
                        }}
                        showToast(`[${{name}}] API Key 保存成功`, "success");
                    }} else {{
                        showToast(`保存失败: ${{data.detail || "未知错误"}}`, "error");
                    }}
                }} catch (e) {{
                    showToast(`保存失败: ${{e.message}}`, "error");
                }}
            }}

            async function deleteProvider(name) {{
                if (!confirm(`确定要从网关中删除渠道 [${{name}}] 吗？`)) return;
                try {{
                    const res = await fetch("/api/providers/delete", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ name }})
                    }});
                    if (res.ok) {{
                        providers = providers.filter(p => p.name !== name);
                        showToast(`渠道 [${{name}}] 已删除`, "success");
                        filterProviders();
                    }} else {{
                        showToast(`删除失败`, "error");
                    }}
                }} catch (e) {{
                    showToast(`删除失败: ${{e.message}}`, "error");
                }}
            }}

            async function testProviderKey(name) {{
                const btn = document.getElementById(`test-btn-${{name}}`);
                const resSpan = document.getElementById(`test-res-${{name}}`);
                btn.disabled = true;
                btn.innerHTML = `<span class="svg-icon svg-icon-sm icon-rotate"><svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg></span><span>测速中</span>`;
                resSpan.innerHTML = "";

                try {{
                    const res = await fetch("/api/providers/test", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ name }})
                    }});
                    const data = await res.json();
                    if (data.status === "ok") {{
                        resSpan.innerHTML = `<span style="color:var(--accent-emerald);font-weight:600;display:inline-flex;align-items:center;gap:3px;"><span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg></span>${{data.latency_ms}}ms</span>`;
                        showToast(`[${{name}}] 测速正常: ${{data.latency_ms}}ms`, "success");
                    }} else {{
                        resSpan.innerHTML = `<span style="color:var(--accent-rose);font-weight:600;display:inline-flex;align-items:center;gap:3px;"><span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg></span>失败</span>`;
                        showToast(`[${{name}}] 验证未通过: ${{data.message}}`, "error");
                    }}
                }} catch (e) {{
                    resSpan.innerHTML = `<span style="color:var(--accent-rose);">超时</span>`;
                }} finally {{
                    btn.disabled = false;
                    btn.innerHTML = `<span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg></span><span>测速</span>`;
                }}
            }}

            async function enableAllConfigured() {{
                let count = 0;
                for (const p of providers) {{
                    if (p.api_key && !p.api_key.startsWith("YOUR_") && !p.enabled) {{
                        await toggleProvider(p.name, true);
                        count++;
                    }}
                }}
                showToast(`已开启 ${{count}} 个有效渠道`, "success");
                filterProviders();
            }}

            async function testCascadingSimulator() {{
                showToast("🪜 正在发起 Auto 智能降级测试...", "info");
                try {{
                    const res = await fetch("/v1/chat/completions", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{
                            model: "auto",
                            messages: [{{ role: "user", content: "Ping Auto Cascading" }}],
                            max_tokens: 5
                        }})
                    }});
                    const provider = res.headers.get("x-gateway-provider") || "Unknown";
                    const tier = decodeURIComponent(res.headers.get("x-gateway-tier") || "Tier");
                    const model = res.headers.get("x-gateway-model") || "Unknown";
                    if (res.ok) {{
                        showToast(`演练成功！命中 [${{tier}}] ➡️ ${{provider}} (${{model}})`, "success");
                        loadLogs();
                    }} else {{
                        showToast("降级演练测试未成功", "error");
                    }}
                }} catch (e) {{
                    showToast(`模拟测试失败: ${{e.message}}`, "error");
                }}
            }}

            async function updateLatestModels() {{
                const btnTop = document.getElementById("btn-update-models-top");
                const btnTh = document.getElementById("btn-update-models-th");
                const iconTop = document.getElementById("update-models-icon-top");
                const iconTh = document.getElementById("update-models-icon-th");
                const textTop = document.getElementById("update-models-text-top");
                const textTh = document.getElementById("update-models-text-th");

                if (btnTop) btnTop.disabled = true;
                if (btnTh) btnTh.disabled = true;
                if (iconTop) iconTop.classList.add("spin");
                if (iconTh) iconTh.classList.add("spin");
                if (textTop) textTop.innerText = "检索全网最新模型中...";
                if (textTh) textTh.innerText = "更新中...";

                showToast("🔍 正在跨渠道探测最新最强免费模型 (Google, Groq, NVIDIA, OpenRouter)...", "info", 5000);

                try {{
                    const res = await fetch("/api/models/update_latest", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }}
                    }});
                    const data = await res.json();
                    if (data.status === "ok") {{
                        if (data.providers) {{
                            providers = data.providers;
                            filterProviders();
                        }}
                        const highlight = data.top_models ? data.top_models.slice(0, 4).map(m => `<b>${{m.name}}</b> (${{m.provider}})`).join("、") : "";
                        showToast(`✅ <b>最新最强免费模型已写入配置！</b><br><span style="font-size:11px;color:var(--text-secondary);">已同步接入 ${{highlight}} 等前沿大模型</span>`, "success", 6000);
                    }} else {{
                        showToast(`更新模型失败: ${{data.message || "未知错误"}}`, "error", 4000);
                    }}
                }} catch (e) {{
                    showToast(`更新请求异常: ${{e.message}}`, "error", 4000);
                }} finally {{
                    if (btnTop) btnTop.disabled = false;
                    if (btnTh) btnTh.disabled = false;
                    if (iconTop) iconTop.classList.remove("spin");
                    if (iconTh) iconTh.classList.remove("spin");
                    if (textTop) textTop.innerText = "获取最新最强免费模型";
                    if (textTh) textTh.innerText = "更新模型";
                }}
            }}

            async function loadLogs() {{
                try {{
                    const res = await fetch("/api/logs");
                    if (!res.ok) return;
                    const logs = await res.json();
                    renderLogs(logs);
                }} catch (e) {{}}
            }}

            function renderLogs(logs) {{
                const tbody = document.getElementById("logs-table");
                if (!logs || logs.length === 0) {{
                    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-tertiary);padding:24px;">暂无调用记录，发起任务后实时展示。</td></tr>`;
                    return;
                }}

                tbody.innerHTML = "";
                logs.forEach((log) => {{
                    const statusBadge = log.status === "success" 
                        ? `<span class="badge badge-success"><span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg></span>200 OK</span>` 
                        : (log.status === "failover_success" 
                            ? `<span class="badge badge-tier"><span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polyline points="13 17 18 12 13 7"></polyline><polyline points="6 17 11 12 6 7"></polyline></svg></span>降级成功</span>` 
                            : `<span class="badge badge-danger"><span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg></span>Fail (${{log.status_code || 500}})</span>`);

                    let traceHtml = "";
                    if (log.attempts && log.attempts.length > 0) {{
                        traceHtml = log.attempts.map((att, idx) => {{
                            const isSuccess = att.status === "success";
                            const color = isSuccess ? "var(--accent-emerald)" : "var(--accent-rose)";
                            const tierBadge = att.tier ? `<span class="badge badge-tier" style="margin-right:2px;">${{att.tier}}</span>` : "";
                            const iconSvg = isSuccess 
                                ? `<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>`
                                : `<svg viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
                            return `<div class="trace-step">
                                ${{tierBadge}}
                                <span class="svg-icon svg-icon-sm" style="color:${{color}};">${{iconSvg}}</span>
                                <span style="color:${{color}};font-weight:500;">${{att.provider}}</span>
                                <span style="color:var(--text-secondary);font-family:monospace;">(${{att.model}})</span>
                                <span style="color:var(--text-tertiary);">${{att.latency_ms}}ms</span>
                            </div>`;
                        }}).join(" ");
                    }} else {{
                        traceHtml = `<span style="color:var(--text-tertiary);display:inline-flex;align-items:center;gap:3px;"><span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg></span>直接命中</span>`;
                    }}

                    const streamBadge = log.stream ? `<span class="badge" style="color:var(--linear-brand);font-size:9.5px;margin-left:3px;"><span class="svg-icon svg-icon-sm"><svg viewBox="0 0 24 24"><path d="M2 12h5l3 8 4-16 3 8h5"></path></svg></span>Stream</span>` : "";

                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-tertiary);">${{log.time}}</td>
                        <td><strong style="color:var(--text-primary);font-family:'JetBrains Mono',monospace;">${{log.requested_model}}</strong>${{streamBadge}}</td>
                        <td><span style="color:var(--text-primary);font-weight:500;">${{log.final_provider || "-"}}</span></td>
                        <td><span style="font-family:'JetBrains Mono',monospace;color:var(--linear-brand);font-size:11px;">${{log.final_model || "-"}}</span></td>
                        <td>${{traceHtml}}</td>
                        <td style="font-family:'JetBrains Mono',monospace;color:var(--text-primary);">${{log.latency_ms}}ms</td>
                        <td>${{statusBadge}}</td>
                    `;
                    tbody.appendChild(tr);
                }});
            }}

            async function clearLogs() {{
                if (!confirm("确定要清空调用日志吗？")) return;
                try {{
                    const res = await fetch("/api/logs/clear", {{ method: "POST" }});
                    if (res.ok) {{
                        showToast("调用日志已清空", "success");
                        loadLogs();
                    }}
                }} catch (e) {{}}
            }}

            renderTable();
            loadLogs();
            setInterval(loadLogs, 2000);
        </script>
    </body>
    </html>
    """
    return html

# 2. 交互控制 API
class ToggleRequest(BaseModel):
    name: str
    enabled: bool

class UpdateKeyRequest(BaseModel):
    name: str
    api_key: str

class DeleteProviderRequest(BaseModel):
    name: str

class TestKeyRequest(BaseModel):
    name: str

@app.post("/api/providers/toggle")
async def api_toggle_provider(req: ToggleRequest):
    updated = False
    for p in state.config.get("providers", []):
        if p.get("name") == req.name:
            p["enabled"] = req.enabled
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=404, detail=f"未找到渠道: {req.name}")
    
    save_config(state.config)
    state.reload_config()
    return {"status": "ok", "name": req.name, "enabled": req.enabled}

@app.post("/api/providers/update_key")
async def api_update_key(req: UpdateKeyRequest):
    updated = False
    for p in state.config.get("providers", []):
        if p.get("name") == req.name:
            p["api_key"] = req.api_key
            if req.api_key and not req.api_key.startswith("YOUR_"):
                p["enabled"] = True
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=404, detail=f"未找到渠道: {req.name}")
    
    save_config(state.config, force_key_updates={req.name: req.api_key})
    state.reload_config()
    return {"status": "ok", "name": req.name}

@app.post("/api/providers/delete")
async def api_delete_provider(req: DeleteProviderRequest):
    providers = state.config.get("providers", [])
    new_providers = [p for p in providers if p.get("name") != req.name]
    if len(new_providers) == len(providers):
        raise HTTPException(status_code=404, detail=f"未找到渠道: {req.name}")
    
    state.config["providers"] = new_providers
    if os.path.exists(CONFIG_PATH):
        try:
            shutil.copy2(CONFIG_PATH, f"{CONFIG_PATH}.bak")
        except Exception:
            pass
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(state.config, f, allow_unicode=True, sort_keys=False)
    state.reload_config()
    return {"status": "ok", "deleted": req.name}

@app.get("/api/logs")
async def api_get_logs():
    return state.request_logs

@app.post("/api/logs/clear")
async def api_clear_logs():
    state.request_logs.clear()
    return {"status": "ok", "message": "Logs cleared"}

@app.post("/api/providers/test")
async def api_test_provider(req: TestKeyRequest):
    target = None
    for p in state.config.get("providers", []):
        if p.get("name") == req.name:
            target = p
            break
    
    if not target:
        return {"status": "error", "message": f"未找到渠道: {req.name}"}

    api_key = target.get("api_key", "").strip()
    if not api_key or api_key.startswith("YOUR_"):
        return {"status": "error", "message": "请先填入有效 API Key"}

    base_url = target.get("base_url", "").rstrip("/")
    models = target.get("models", [])
    
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    if "openrouter" in base_url.lower():
        headers["HTTP-Referer"] = "https://github.com/deepseek-ai/deepseek-harness"
        headers["X-Title"] = "DeepSeek-Harness"

    # 针对不同大厂，优先挑选响应最快、最稳定的探活模型
    preferred_probes = {
        "Google AI Studio": ["gemini-3.5-flash", "gemini-flash-latest"],
        "Groq Cloud": ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"],
        "NVIDIA NIM": ["meta/llama-3.2-11b-vision-instruct", "nvidia/nemotron-3-ultra-550b-a55b", "deepseek-ai/deepseek-v4-flash-0731"],
        "OpenRouter (Global)": ["cohere/north-mini-code:free", "thinkingmachines/inkling-small:free", "openrouter/free"]
    }
    p_name = target.get("name", "")
    candidate_models = list(preferred_probes.get(p_name, []))
    for m in models:
        up = m.get("upstream_model")
        if up and up not in candidate_models:
            candidate_models.append(up)

    if not candidate_models:
        candidate_models = ["gemini-3.5-flash", "meta/llama-3.2-11b-vision-instruct", "openrouter/free"]

    start = time.time()
    last_err = ""
    async with httpx.AsyncClient(timeout=12.0) as client:
        for test_model in candidate_models[:5]:
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
                    return {"status": "ok", "latency_ms": latency, "model": test_model, "message": "测试通过"}
                else:
                    last_err = f"[{test_model}] {resp.status_code}: {resp.text[:80]}"
            except Exception as e:
                last_err = f"[{test_model}] {str(e)[:80]}"

    latency = int((time.time() - start) * 1000)
    return {"status": "error", "latency_ms": latency, "message": last_err}

async def fetch_and_update_latest_free_models() -> dict:
    """
    Dynamically probes Google AI Studio, Groq Cloud, NVIDIA NIM, and OpenRouter
    for the latest and strongest free models, updates config.yaml, and reloads in-memory state.
    """
    providers = state.config.get("providers", [])
    prov_map = {p.get("name", ""): p for p in providers}

    discovered_models = {}

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # 1. OpenRouter Free Models
        try:
            r = await client.get("https://openrouter.ai/api/v1/models")
            if r.status_code == 200:
                data = r.json().get("data", [])
                free_list = [
                    m for m in data
                    if m.get("id", "").endswith(":free") or
                       (isinstance(m.get("pricing"), dict) and str(m["pricing"].get("prompt")) == "0" and str(m["pricing"].get("completion")) == "0")
                ]
                free_list.sort(key=lambda x: x.get("context_length", 0), reverse=True)
                discovered_models["OpenRouter (Global)"] = [
                    {"id": m.get("id"), "upstream_model": m.get("id")}
                    for m in free_list
                ]
        except Exception as e:
            logger.warning(f"Failed to query OpenRouter models: {e}")

        # 2. Google AI Studio Models
        google_p = prov_map.get("Google AI Studio")
        if google_p:
            g_key = (google_p.get("api_key") or "").strip()
            if g_key and not g_key.startswith("YOUR_"):
                try:
                    r = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={g_key}")
                    if r.status_code == 200:
                        g_data = r.json().get("models", [])
                        g_models = []
                        for m in g_data:
                            methods = m.get("supportedGenerationMethods", [])
                            if "generateContent" in methods:
                                mid = m.get("name", "").replace("models/", "")
                                g_models.append({"id": mid, "upstream_model": mid})
                        discovered_models["Google AI Studio"] = g_models
                except Exception as e:
                    logger.warning(f"Failed to query Google models: {e}")

        # 3. Groq Cloud Models
        groq_p = prov_map.get("Groq Cloud")
        if groq_p:
            groq_key = (groq_p.get("api_key") or "").strip()
            if groq_key and not groq_key.startswith("YOUR_"):
                try:
                    r = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {groq_key}"})
                    if r.status_code == 200:
                        models_data = r.json().get("data", [])
                        discovered_models["Groq Cloud"] = [
                            {"id": m.get("id"), "upstream_model": m.get("id")}
                            for m in models_data
                        ]
                except Exception as e:
                    logger.warning(f"Failed to query Groq models: {e}")

        # 4. NVIDIA NIM Models
        nim_p = prov_map.get("NVIDIA NIM")
        if nim_p:
            nim_key = (nim_p.get("api_key") or "").strip()
            if nim_key and not nim_key.startswith("YOUR_"):
                try:
                    r = await client.get("https://integrate.api.nvidia.com/v1/models", headers={"Authorization": f"Bearer {nim_key}"})
                    if r.status_code == 200:
                        models_data = r.json().get("data", [])
                        discovered_models["NVIDIA NIM"] = [
                            {"id": m.get("id"), "upstream_model": m.get("id")}
                            for m in models_data
                        ]
                except Exception as e:
                    logger.warning(f"Failed to query NVIDIA NIM models: {e}")

    # Curated Top Free Models Priorities
    curated_priorities = {
        "Google AI Studio": [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-flash-lite-latest",
            "gemini-2.5-pro",
            "gemma-4-31b-it",
            "gemma-4-26b-a4b-it"
        ],
        "Groq Cloud": [
            "openai/gpt-oss-120b",
            "qwen/qwen3.8-27b",
            "groq/compound-mini",
            "groq/compound",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant"
        ],
        "NVIDIA NIM": [
            "nvidia/nemotron-3-ultra-550b-a55b",
            "meta/llama-3.2-11b-vision-instruct",
            "deepseek-ai/deepseek-v4-pro-0813",
            "deepseek-ai/deepseek-v4-flash-0731",
            "meta/llama-3.3-70b-instruct"
        ],
        "OpenRouter (Global)": [
            "thinkingmachines/inkling-small:free",
            "thinkingmachines/inkling:free",
            "nvidia/nemotron-3.5-lightning:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "minimax/minimax-m3:free",
            "dots-studio/dots-3-note-preview:free",
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "z-ai/glm-5.2:free",
            "cohere/north-mini-code:free",
            "openrouter/free"
        ]
    }

    added_count = 0
    updated_providers = []

    # Merge models into providers
    for p in providers:
        p_name = p.get("name", "")
        existing_models = p.get("models", [])
        existing_ids = {m.get("id") for m in existing_models}
        existing_upstreams = {m.get("upstream_model") for m in existing_models}

        candidates = []
        for cur_id in curated_priorities.get(p_name, []):
            candidates.append({"id": cur_id, "upstream_model": cur_id})

        for disc_m in discovered_models.get(p_name, []):
            candidates.append(disc_m)

        new_top_models = []
        seen = set()
        for cand in candidates:
            cid = cand.get("id")
            cup = cand.get("upstream_model") or cid
            if cid and cid not in seen:
                seen.add(cid)
                if cid not in existing_ids and cup not in existing_upstreams:
                    added_count += 1
                new_top_models.append({"id": cid, "upstream_model": cup})

        for old_m in existing_models:
            old_id = old_m.get("id")
            if old_id and old_id not in seen:
                seen.add(old_id)
                new_top_models.append(old_m)

        p["models"] = new_top_models
        updated_providers.append(p_name)

    # Synchronize fallback ladders for "auto"
    state.config["fallback_ladders"] = {
        "auto": [
            {
                "tier": "Tier 1: 大厂满血旗舰层 (Google Gemini 3.8 / 3.5 / NVIDIA 550B · 100万上下文)",
                "models": [
                    "gemini-3.8-flash",
                    "gemini-3.5-flash",
                    "gemini-flash-latest",
                    "nvidia/nemotron-3-ultra-550b-a55b",
                    "openai/gpt-oss-120b",
                    "qwen/qwen3.8-27b"
                ]
            },
            {
                "tier": "Tier 2: LPU 极速芯片与视觉层 (Groq Qwen 3.8 / GPT-OSS 120B / Llama 3.2 视觉)",
                "models": [
                    "openai/gpt-oss-120b",
                    "qwen/qwen3.8-27b",
                    "groq/compound-mini",
                    "meta/llama-3.2-11b-vision-instruct"
                ]
            },
            {
                "tier": "Tier 3: 开源百万长上下文与深度思维链推理层 (Thinking Machines 1M / Cohere Code / Dots 512K)",
                "models": [
                    "thinkingmachines/inkling-small:free",
                    "thinkingmachines/inkling:free",
                    "cohere/north-mini-code:free",
                    "dots-studio/dots-3-note-preview:free",
                    "nvidia/nemotron-3.5-lightning:free",
                    "minimax/minimax-m3:free",
                    "gemini-flash-lite-latest"
                ]
            },
            {
                "tier": "Tier 4: 全球高可用动态免费兜底层 (OpenRouter Free 动态智能路由池)",
                "models": [
                    "openrouter/free"
                ]
            }
        ]
    }

    save_config(state.config)
    state.reload_config()

    top_models_summary = [
        {"name": "gemini-3.8-flash", "provider": "Google AI Studio", "context": "1,048,576", "tag": "3.8代旗舰 · 百万上下文"},
        {"name": "gemini-3.5-flash", "provider": "Google AI Studio", "context": "1,048,576", "tag": "3.5代生产主力"},
        {"name": "openai/gpt-oss-120b", "provider": "Groq Cloud", "context": "131,072", "tag": "120B 开源旗舰 · 700+ t/s LPU"},
        {"name": "qwen/qwen3.8-27b", "provider": "Groq Cloud", "context": "131,042", "tag": "通义千问3.8极速"},
        {"name": "nvidia/nemotron-3-ultra-550b-a55b", "provider": "NVIDIA NIM", "context": "1,000,000", "tag": "550B MoE 巨无霸"},
        {"name": "meta/llama-3.2-11b-vision-instruct", "provider": "NVIDIA NIM", "context": "131,072", "tag": "多模态视觉理解"},
        {"name": "thinkingmachines/inkling-small:free", "provider": "OpenRouter", "context": "1,048,576", "tag": "100万长上下文 · 思维链"},
        {"name": "dots-studio/dots-3-note-preview:free", "provider": "OpenRouter", "context": "512,000", "tag": "512K 上下文 · MoE 专家"}
    ]

    return {
        "status": "ok",
        "message": "成功检索并更新最新最强免费模型矩阵！",
        "added_count": added_count,
        "updated_providers": updated_providers,
        "top_models": top_models_summary,
        "providers": state.config.get("providers", [])
    }

@app.post("/api/models/update_latest")
async def api_update_latest_models():
    try:
        res = await fetch_and_update_latest_free_models()
        return res
    except Exception as e:
        logger.error(f"Update latest models failed: {e}")
        return {"status": "error", "message": f"更新失败: {str(e)}"}

# 3. 精简模型列表接口 (/v1/models) - 严格只暴露 auto 和 deepseek-v4-flash
@app.get("/v1/models")
async def list_models():
    exposed = state.config.get("exposed_models", ["auto", "deepseek-v4-flash"])
    data = [
        {
            "id": mid,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "free-token-gateway",
            "permission": [],
            "root": mid,
            "parent": None
        }
        for mid in exposed
    ]
    return {"object": "list", "data": data}

# 💰 兼容 DeepSeek-Harness 虚拟额度接口
@app.get("/v1/dashboard/billing/credit_grants")
@app.get("/dashboard/billing/credit_grants")
@app.get("/v1/dashboard/billing/usage")
@app.get("/dashboard/billing/usage")
@app.get("/v1/users/current")
@app.get("/v1/billing/subscription")
async def mock_unlimited_balance():
    return {
        "object": "credit_summary",
        "total_granted": 9999999.0,
        "total_used": 0.0,
        "total_available": 9999999.0,
        "grants": {
            "object": "list",
            "data": [
                {
                    "id": "free-token-infinite-grant",
                    "grant_amount": 9999999.0,
                    "used_amount": 0.0,
                    "expires_at": int(time.time()) + 315360000
                }
            ]
        }
    }

# 4. 核心转发接口 (/v1/chat/completions)
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    req_time_str = time.strftime("%H:%M:%S")
    req_start_time = time.time()
    state.stats["total_requests"] += 1
    
    body = await request.json()
    requested_model = body.get("model", "auto")
    is_stream = body.get("stream", False)
    
    messages = body.get("messages", [])
    prompt_snippet = ""
    if messages and isinstance(messages, list):
        last_msg = messages[-1]
        content = last_msg.get("content", "")
        if isinstance(content, str):
            prompt_snippet = content[:60]
        elif isinstance(content, list):
            prompt_snippet = "[多模态输入]"

    forward_body = dict(body)
    tools = body.get("tools", [])
    tool_schemas = extract_tool_schemas(tools)

    if tool_schemas:
        req_params_hint = []
        for fname, s in tool_schemas.items():
            reqs = s.get("required") or []
            if reqs:
                req_params_hint.append(f"'{fname}' requires: {reqs}")
        if req_params_hint:
            hint_str = (
                "\n[IMPORTANT TOOL CALLING RULES]:"
                f"\n1. When calling ANY tool, you MUST strictly include ALL required parameters: {'; '.join(req_params_hint[:4])}. Never omit required parameters such as 'description', 'CommandLine', etc."
                "\n2. Never overwrite an existing file directly without reading it first. Always call 'view_file' or read tool to inspect existing code before calling 'write_to_file' or 'replace_file_content'."
            )
            f_msgs = forward_body.get("messages", [])
            if f_msgs and isinstance(f_msgs, list):
                if f_msgs[0].get("role") == "system" and isinstance(f_msgs[0].get("content"), str):
                    f_msgs[0]["content"] += hint_str
                else:
                    f_msgs.insert(0, {"role": "system", "content": hint_str.strip()})

    # 彻底解除 4096 截断限制：尊重客户端配置，未指定时默认提供 16384 超大输出窗口，支持长代码生成与完整深度思维链
    req_max_tokens = forward_body.get("max_tokens")
    req_max_comp = forward_body.get("max_completion_tokens")
    if req_max_tokens is None and req_max_comp is None:
        forward_body["max_tokens"] = 16384
    elif req_max_comp is not None and req_max_tokens is None:
        forward_body["max_tokens"] = req_max_comp
        forward_body.pop("max_completion_tokens", None)
    elif req_max_comp is not None and req_max_tokens is not None:
        forward_body.pop("max_completion_tokens", None)

    # 智能多模态视觉嗅探：检测请求中是否包含图像输入 (image_url)
    has_image = False
    if messages and isinstance(messages, list):
        for msg in messages:
            c = msg.get("content")
            if isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        has_image = True
                        break
            if has_image:
                break

    # 若包含图像输入且请求模型为非原生视觉模型，自动无缝调度至顶级多模态视觉模型天梯
    effective_model = requested_model
    if has_image and not is_model_vision_capable(requested_model):
        logger.info(f"👁️ 【多模态视觉智能协同】检测到图像输入！[{requested_model}] 无原生视觉感知能力，已自动无缝切换至多模态视觉天梯 (Google Gemini 3.8 / 3.5 / Llama 3.2 Vision)...")
        effective_model = "auto"

    tiered_plan = build_tiered_execution_plan(effective_model, has_image=has_image)
    if not tiered_plan:
        state.stats["failed_requests"] += 1
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": f"未找到任何支持模型 '{requested_model}' 的活跃渠道商。",
                    "type": "invalid_request_error",
                    "code": "no_active_provider"
                }
            }
        )

    last_error_detail = None
    total_retries = 0
    attempts_trace = []
    failed_providers_in_req = set()

    # 智能多轮工具历史嗅探：检测请求历史中是否包含外部多轮 tool_calls / role="tool"
    # Google AI Studio 的 OpenAI 兼容端要求每条 tool_calls 必须携带其私有 thought_signature，否则必报 HTTP 400
    if messages and isinstance(messages, list):
        for msg in messages:
            if msg.get("role") == "tool" or msg.get("tool_calls"):
                extra = msg.get("extra_content", {})
                if not extra or not extra.get("google", {}).get("thought_signature"):
                    logger.info("⚡ 检测到多轮 Tool Calling 交互历史，自动秒级跳过 Google AI Studio（规避 400 thought_signature 错误），直达 NVIDIA / Groq 标准大厂！")
                    failed_providers_in_req.add("Google AI Studio")
                    break

    for tier_idx, tier_obj in enumerate(tiered_plan, 1):
        tier_name = tier_obj["tier_name"]
        candidates = tier_obj["candidates"]

        for provider, upstream_model in candidates:
            p_name = provider.get("name", "Unknown")
            base_url = provider.get("base_url", "").rstrip("/")
            api_key = provider.get("api_key", "")
            
            # 1. 检查当前请求内是否已标记该渠道不可用（如全局429或不支持tool calls）
            if p_name in failed_providers_in_req:
                continue

            # 2. 检查单模型是否处于 429 熔断冷却期
            model_key = f"{p_name}:{upstream_model}"
            now = time.time()
            if now < state.model_cooldowns.get(model_key, 0):
                rem = int(state.model_cooldowns[model_key] - now)
                logger.info(f"⏳ [{p_name} | {upstream_model}] 正处于 429 熔断冷却中 (剩余 {rem}s)，秒级避让跳过...")
                continue

            # 3. 检查全渠道是否处于 429 熔断冷却期
            if now < state.provider_cooldowns.get(p_name, 0):
                rem = int(state.provider_cooldowns[p_name] - now)
                logger.info(f"⏳ 渠道 [{p_name}] 正处于全局 429 熔断冷却中 (剩余 {rem}s)，秒级避让跳过...")
                continue

            call_body = dict(forward_body)
            call_body["model"] = upstream_model

            # 对 Google AI Studio 等严格校验 JSON 字段的提供商进行参数清洗
            if "generativelanguage" in base_url.lower() or "google" in p_name.lower():
                unsupported_keys = [
                    "stream_options", "service_tier", "store", "metadata",
                    "reasoning_effort", "parallel_tool_calls", "user",
                    "logprobs", "top_logprobs", "echo", "best_of"
                ]
                for k in unsupported_keys:
                    call_body.pop(k, None)
                if "max_completion_tokens" in call_body and "max_tokens" in call_body:
                    call_body.pop("max_tokens", None)

            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            if "openrouter" in base_url.lower():
                headers["HTTP-Referer"] = "https://github.com/deepseek-ai/deepseek-harness"
                headers["X-Title"] = "DeepSeek-Harness"

            p_stat = state.stats["provider_stats"].setdefault(p_name, {
                "calls": 0, "success": 0, "errors": 0, "last_error": "", "last_latency_ms": 0, "status": "Active"
            })
            p_stat["calls"] += 1

            start_time = time.time()
            logger.info(f"🔄 [{tier_name}] 尝试渠道 [{p_name} (P:{provider.get('priority', 50)})] -> 真实模型 [{upstream_model}]...")

            try:
                # 建连阶段保持 4.0s 极速故障转移，读取阶段给予 120s 充裕窗口，防止大模型长文本/长思维链生成被截断
                client_timeout = httpx.Timeout(120.0, connect=4.0, read=120.0, write=15.0, pool=5.0)
                client = httpx.AsyncClient(timeout=client_timeout)

                if is_stream:
                    req = client.build_request("POST", url, headers=headers, json=call_body)
                    response = await client.send(req, stream=True)

                    # 若遇到瞬时超载 (529/503) 或服务不可用，开启 30s 冷却并秒级故障转移至下一候选
                    if response.status_code in [529, 503]:
                        error_text = await response.aread()
                        error_str = error_text.decode("utf-8", errors="ignore")
                        logger.warning(f"⚠️ [{p_name} | {upstream_model}] 遇到瞬时超载 (HTTP {response.status_code})，开启 30s 冷却并秒级转移至下一候选！")
                        await response.aclose()
                        await client.aclose()
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        raise HTTPException(status_code=response.status_code, detail=f"[{p_name}] 服务瞬时超载 (HTTP {response.status_code}): {error_str[:200]}")

                    if response.status_code >= 400:
                        error_text = await response.aread()
                        error_str = error_text.decode("utf-8", errors="ignore")
                        logger.warning(f"❌ [{p_name} | {upstream_model}] HTTP {response.status_code}: {error_str[:300]}")
                        await client.aclose()

                        # 处理 429 限流/配额熔断：针对具体模型开启 60s 冷却，不连坐整个渠道（允许同渠道健康模型如 flash-lite 正常服务）
                        if response.status_code == 429:
                            logger.warning(f"⚠️ [{p_name} | {upstream_model}] 触发 429 限流/配额不足，开启该模型 60s 快速熔断并转移至下一模型！")
                            state.model_cooldowns[model_key] = time.time() + 60.0

                        # 处理 400 不支持 thought_signature 的 tool_calls 历史或上下文超长
                        if response.status_code == 400:
                            if "thought_signature" in error_str or "functioncall" in error_str.lower():
                                logger.warning(f"⚠️ [{p_name}] 缺少 thought_signature 拒绝处理历史 tool_calls，本次请求快速跳过该渠道并转移至标准兼容模型！")
                                failed_providers_in_req.add(p_name)
                            elif "context" in error_str.lower() or ("token" in error_str.lower() and "length" in error_str.lower()):
                                logger.warning(f"⚠️ [{p_name} | {upstream_model}] 上下文长度超过模型上限，本次请求快速跳过并切往更高上下文大模型！")
                                failed_providers_in_req.add(p_name)

                        raise HTTPException(status_code=response.status_code, detail=f"[{p_name}] {error_str}")

                    # 首包探针：预读取第一块数据，拦截假 HTTP 200 实为 503/Overloaded 的 SSE 错误包
                    stream_iter = response.aiter_bytes()
                    first_chunk = None
                    try:
                        async for chunk in stream_iter:
                            first_chunk = chunk
                            break
                    except Exception as peek_err:
                        await response.aclose()
                        await client.aclose()
                        raise HTTPException(status_code=503, detail=f"[{p_name}] 连接建立后首包读取中断: {peek_err}")

                    # 检查首包是否包含上游超载或报错 (如 NVIDIA/OpenRouter 在 200 SSE 流中推送 error 载荷)
                    if first_chunk:
                        chunk_lower = first_chunk.lower()
                        if (b'"error"' in chunk_lower or b'"detail"' in chunk_lower or b'overload' in chunk_lower) and b'"choices"' not in chunk_lower:
                            await response.aclose()
                            await client.aclose()
                            error_peek_str = first_chunk.decode("utf-8", errors="ignore")
                            logger.warning(f"⚠️ [{p_name} | {upstream_model}] 流式首包检测到服务超载/报错: {error_peek_str[:200]}，开启 30s 冷却并秒级转移至下一候选渠道！")
                            state.model_cooldowns[model_key] = time.time() + 30.0
                            raise HTTPException(status_code=503, detail=f"[{p_name}] 流式首包超载: {error_peek_str[:200]}")

                    latency = int((time.time() - start_time) * 1000)
                    total_latency = int((time.time() - req_start_time) * 1000)
                    p_stat["success"] += 1
                    p_stat["last_latency_ms"] = latency
                    state.stats["success_requests"] += 1
                    state.stats["total_latency_sum"] = state.stats.get("total_latency_sum", 0) + latency
                    if tier_idx > 1:
                        state.stats["tier_fallback_events"] = state.stats.get("tier_fallback_events", 0) + 1

                    attempts_trace.append({
                        "tier": f"L{tier_idx}",
                        "provider": p_name,
                        "model": upstream_model,
                        "status": "success",
                        "latency_ms": latency
                    })
                    log_entry = {
                        "time": req_time_str,
                        "requested_model": requested_model,
                        "final_provider": p_name,
                        "final_model": upstream_model,
                        "status": "success" if total_retries == 0 else "failover_success",
                        "status_code": 200,
                        "latency_ms": total_latency,
                        "stream": True,
                        "prompt_snippet": prompt_snippet,
                        "attempts": attempts_trace
                    }
                    state.add_log(log_entry)

                    async def stream_generator():
                        try:
                            # 1. 未配置 tools 的纯文本对话：直通极速通道（0 延迟、0 损耗、不截断）
                            if not tool_schemas:
                                if first_chunk:
                                    yield first_chunk
                                async for chunk in stream_iter:
                                    yield chunk
                                return

                            # 2. 配置了 tools 的智能自愈通道：
                            # 必须持续解析流事件，绝不能因前面有 reasoning_content/content 就锁死直通，
                            # 否则思考型大模型 (DeepSeek-V4/Nemotron) 的 tool_calls 将被漏过导致缺少 description 报错！
                            buffer = ""
                            tc_active = {}
                            tc_flushed = False

                            async def combined_iter():
                                if first_chunk:
                                    yield first_chunk
                                async for c in stream_iter:
                                    yield c

                            async for chunk in combined_iter():
                                text = chunk.decode("utf-8", errors="ignore")
                                buffer += text

                                while "\n\n" in buffer:
                                    event_str, buffer = buffer.split("\n\n", 1)
                                    lines = event_str.split("\n")
                                    event_has_tc = False

                                    for line in lines:
                                        line_s = line.strip()
                                        if line_s.startswith("data: ") and line_s != "data: [DONE]":
                                            payload = line_s[6:]
                                            try:
                                                d = json.loads(payload)
                                                choices = d.get("choices", [])
                                                if choices:
                                                    delta = choices[0].get("delta", {})
                                                    tcs = delta.get("tool_calls")
                                                    finish_reason = choices[0].get("finish_reason")

                                                    # 累积 tool_calls 片段
                                                    if tcs and isinstance(tcs, list):
                                                        event_has_tc = True
                                                        for tc in tcs:
                                                            idx = tc.get("index", 0)
                                                            entry = tc_active.setdefault(idx, {"id": tc.get("id", f"call_{idx}"), "name": "", "args": ""})
                                                            if tc.get("id"):
                                                                entry["id"] = tc["id"]
                                                            fn = tc.get("function", {})
                                                            if fn.get("name"):
                                                                entry["name"] = fn["name"]
                                                            if fn.get("arguments"):
                                                                entry["args"] += fn["arguments"]

                                                    # 当工具调用流结束，立即执行自愈校验并下发完整修复后的参数
                                                    if (finish_reason in ["tool_calls", "stop"] or finish_reason is not None) and tc_active and not tc_flushed:
                                                        event_has_tc = True
                                                        tc_flushed = True
                                                        for idx, entry in tc_active.items():
                                                            repaired = repair_tool_call_arguments(entry["name"], entry["args"], tool_schemas)
                                                            repaired_chunk = {
                                                                "choices": [{
                                                                    "index": 0,
                                                                    "delta": {
                                                                        "role": "assistant",
                                                                        "content": None,
                                                                        "tool_calls": [{
                                                                            "index": idx,
                                                                            "id": entry["id"],
                                                                            "type": "function",
                                                                            "function": {
                                                                                "name": entry["name"],
                                                                                "arguments": repaired
                                                                            }
                                                                        }]
                                                                    },
                                                                    "finish_reason": None
                                                                }]
                                                            }
                                                            yield f"data: {json.dumps(repaired_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                                                        
                                                        finish_chunk = {
                                                            "choices": [{
                                                                "index": 0,
                                                                "delta": {},
                                                                "finish_reason": finish_reason or "tool_calls"
                                                            }]
                                                        }
                                                        yield f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                                                        continue
                                            except Exception:
                                                pass

                                    # 非 tool_calls 事件（纯文本 content、reasoning_content 思考过程等）立即流式直出
                                    if not event_has_tc:
                                        yield (event_str + "\n\n").encode("utf-8")

                            # 若流在未收到明确 finish_reason 时意外结束，但存在未刷新的工具调用，予以终极自愈刷新
                            if tc_active and not tc_flushed:
                                tc_flushed = True
                                for idx, entry in tc_active.items():
                                    repaired = repair_tool_call_arguments(entry["name"], entry["args"], tool_schemas)
                                    repaired_chunk = {
                                        "choices": [{
                                            "index": 0,
                                            "delta": {
                                                "role": "assistant",
                                                "content": None,
                                                "tool_calls": [{
                                                    "index": idx,
                                                    "id": entry["id"],
                                                    "type": "function",
                                                    "function": {
                                                        "name": entry["name"],
                                                        "arguments": repaired
                                                    }
                                                }]
                                            },
                                            "finish_reason": None
                                        }]
                                    }
                                    yield f"data: {json.dumps(repaired_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                                finish_chunk = {
                                    "choices": [{
                                        "index": 0,
                                        "delta": {},
                                        "finish_reason": "tool_calls"
                                    }]
                                }
                                yield f"data: {json.dumps(finish_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                                yield b"data: [DONE]\n\n"

                            if buffer:
                                yield buffer.encode("utf-8")
                        except Exception as e:
                            logger.warning(f"Streaming chunk interrupted from [{p_name}]: {e}")
                        finally:
                            try:
                                await response.aclose()
                            except Exception:
                                pass
                            try:
                                await client.aclose()
                            except Exception:
                                pass

                    return StreamingResponse(
                        stream_generator(),
                        media_type="text/event-stream",
                        headers={
                            "X-Gateway-Provider": p_name,
                            "X-Gateway-Model": upstream_model,
                            "X-Gateway-Tier": urllib.parse.quote(tier_name),
                            "X-Gateway-Retries": str(total_retries),
                            "Cache-Control": "no-cache"
                        }
                    )
                else:
                    resp = await client.post(url, headers=headers, json=call_body)
                    latency = int((time.time() - start_time) * 1000)
                    total_latency = int((time.time() - req_start_time) * 1000)
                    p_stat["last_latency_ms"] = latency
                    await client.aclose()

                    # 瞬时超载 (529/503) 快速避让并故障转移
                    if resp.status_code in [529, 503] or ("overload" in resp.text.lower()):
                        error_str = resp.text
                        logger.warning(f"⚠️ [{p_name} | {upstream_model}] 遇到瞬时超载 (HTTP {resp.status_code})，开启 30s 冷却并秒级故障转移！")
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        raise HTTPException(status_code=resp.status_code, detail=f"[{p_name}] {error_str}")

                    if resp.status_code >= 400:
                        error_str = resp.text
                        logger.warning(f"❌ [{p_name} | {upstream_model}] HTTP {resp.status_code}: {error_str[:300]}")

                        # 处理 429 限流/配额熔断：针对具体模型开启 60s 冷却，不连坐整个渠道（允许同渠道健康模型如 flash-lite 正常服务）
                        if resp.status_code == 429:
                            logger.warning(f"⚠️ [{p_name} | {upstream_model}] 触发 429 限流/配额不足，开启该模型 60s 快速熔断并转移至下一模型！")
                            state.model_cooldowns[model_key] = time.time() + 60.0

                        # 处理 400 不支持 thought_signature 的 tool_calls 历史或上下文超长
                        if resp.status_code == 400:
                            if "thought_signature" in error_str or "functioncall" in error_str.lower():
                                logger.warning(f"⚠️ [{p_name}] 缺少 thought_signature 拒绝处理历史 tool_calls，本次请求快速跳过该渠道并转移至标准兼容模型！")
                                failed_providers_in_req.add(p_name)
                            elif "context" in error_str.lower() or ("token" in error_str.lower() and "length" in error_str.lower()):
                                logger.warning(f"⚠️ [{p_name} | {upstream_model}] 上下文长度超过模型上限，本次请求快速跳过并切往更高上下文大模型！")
                                failed_providers_in_req.add(p_name)

                        raise HTTPException(status_code=resp.status_code, detail=f"[{p_name}] {error_str}")

                    res_json = resp.json()
                    if "error" in res_json and "choices" not in res_json:
                        error_str = str(res_json["error"])
                        logger.warning(f"⚠️ [{p_name} | {upstream_model}] HTTP 200 响应中包含错误体: {error_str[:200]}，开启 30s 冷却并极速转移！")
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        raise HTTPException(status_code=503, detail=f"[{p_name}] {error_str}")

                    res_json["model"] = requested_model

                    # 工具调用自愈补全
                    if tool_schemas and "choices" in res_json and isinstance(res_json["choices"], list):
                        for choice in res_json["choices"]:
                            msg = choice.get("message", {})
                            tcs = msg.get("tool_calls", [])
                            if tcs and isinstance(tcs, list):
                                for tc in tcs:
                                    fn = tc.get("function", {})
                                    fname = fn.get("name", "")
                                    fargs = fn.get("arguments", "")
                                    repaired = repair_tool_call_arguments(fname, fargs, tool_schemas)
                                    fn["arguments"] = repaired

                    p_stat["success"] += 1
                    state.stats["success_requests"] += 1
                    state.stats["total_latency_sum"] = state.stats.get("total_latency_sum", 0) + latency
                    if tier_idx > 1:
                        state.stats["tier_fallback_events"] = state.stats.get("tier_fallback_events", 0) + 1
                    logger.info(f"✅ [{tier_name}] -> 大厂 [{p_name}] 响应成功！实际模型: [{upstream_model}] 耗时: {latency}ms")

                    attempts_trace.append({
                        "tier": f"L{tier_idx}",
                        "provider": p_name,
                        "model": upstream_model,
                        "status": "success",
                        "latency_ms": latency
                    })
                    log_entry = {
                        "time": req_time_str,
                        "requested_model": requested_model,
                        "final_provider": p_name,
                        "final_model": upstream_model,
                        "status": "success" if total_retries == 0 else "failover_success",
                        "status_code": 200,
                        "latency_ms": total_latency,
                        "stream": False,
                        "prompt_snippet": prompt_snippet,
                        "attempts": attempts_trace
                    }
                    state.add_log(log_entry)

                    return JSONResponse(
                        content=res_json,
                        headers={
                            "X-Gateway-Provider": p_name,
                            "X-Gateway-Model": upstream_model,
                            "X-Gateway-Tier": urllib.parse.quote(tier_name),
                            "X-Gateway-Retries": str(total_retries)
                        }
                    )

            except Exception as e:
                latency = int((time.time() - start_time) * 1000)
                error_msg = str(e)
                if isinstance(e, httpx.TimeoutException):
                    error_msg = f"Timeout after {latency}ms ({type(e).__name__})"
                    logger.warning(f"⏱️ [{p_name} | {upstream_model}] 响应超时 ({latency}ms)，立即极速故障转移 (Failover) 至下一候选...")
                p_stat["errors"] += 1
                p_stat["last_error"] = error_msg[:120]
                p_stat["last_latency_ms"] = latency
                
                attempts_trace.append({
                    "tier": f"L{tier_idx}",
                    "provider": p_name,
                    "model": upstream_model,
                    "status": "failed",
                    "error": error_msg[:80],
                    "latency_ms": latency
                })
                last_error_detail = error_msg
                total_retries += 1
                state.stats["failover_events"] += 1
                continue

    total_latency = int((time.time() - req_start_time) * 1000)
    state.stats["failed_requests"] += 1
    
    log_entry = {
        "time": req_time_str,
        "requested_model": requested_model,
        "final_provider": "Exhausted",
        "final_model": "None",
        "status": "failed",
        "status_code": 502,
        "latency_ms": total_latency,
        "stream": is_stream,
        "prompt_snippet": prompt_snippet,
        "attempts": attempts_trace
    }
    state.add_log(log_entry)

    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": f"所有支持模型 '{requested_model}' 的渠道商均调用失败，最后一次报错: {last_error_detail}",
                "type": "model_provider_exhausted",
                "code": "all_providers_failed"
            }
        }
    )

@app.get("/v1/status")
async def get_status():
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "stats": state.stats,
        "config_providers": len(state.config.get("providers", [])),
        "recent_logs_count": len(state.request_logs)
    }

if __name__ == "__main__":
    import uvicorn
    host = state.config["server"].get("host", "127.0.0.1")
    port = state.config["server"].get("port", 8000)
    uvicorn.run("gateway:app", host=host, port=port, reload=False)
