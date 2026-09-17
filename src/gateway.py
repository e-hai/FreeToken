import os
import time
import json
import base64
import shutil
import logging
import asyncio
import urllib.parse
import re
import uuid
import copy
from typing import Dict, List, Any, Optional
import yaml
import httpx
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Gateway")

def _resolve_config_path(default_name: str = "config.yaml") -> str:
    env_path = os.environ.get("CONFIG_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_path = os.path.join(root_dir, default_name)
    if os.path.exists(target_path):
        return target_path
    src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), default_name)
    if os.path.exists(src_path):
        return src_path
    return target_path

CONFIG_PATH = _resolve_config_path("config.yaml")
PROJECT_ROOT = os.path.dirname(CONFIG_PATH)

HARNESS_CONFIG_PATH = os.environ.get("CONFIG_HARNESS_PATH") or os.path.join(PROJECT_ROOT, "config.harness.yaml")
CODEX_CONFIG_PATH = os.environ.get("CONFIG_CODEX_PATH") or os.path.join(PROJECT_ROOT, "config.codex.yaml")

GENERATED_IMAGES_DIR = os.path.join(PROJECT_ROOT, "static", "generated_images")
os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)

def _ensure_channel_configs():
    base_cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                base_cfg = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to read base config: {e}")
    if not base_cfg:
        example_path = os.path.join(PROJECT_ROOT, "config.example.yaml")
        if os.path.exists(example_path):
            with open(example_path, "r", encoding="utf-8") as f:
                base_cfg = yaml.safe_load(f) or {}

    # 1. 自动派生 config.harness.yaml (端口 8000)
    if not os.path.exists(HARNESS_CONFIG_PATH):
        try:
            h_cfg = copy.deepcopy(base_cfg)
            h_cfg.setdefault("server", {})
            h_cfg["server"]["port"] = 8000
            h_cfg["server"]["description"] = "DeepSeek Harness & Web Management Gateway"
            with open(HARNESS_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(h_cfg, f, allow_unicode=True, sort_keys=False)
            logger.info(f"✨ 已自动从基础配置派生 DeepSeek Harness 配置文件: {HARNESS_CONFIG_PATH}")
        except Exception as e:
            logger.error(f"派生 config.harness.yaml 失败: {e}")

    # 2. 自动派生 config.codex.yaml (端口 8001)
    if not os.path.exists(CODEX_CONFIG_PATH):
        try:
            c_cfg = copy.deepcopy(base_cfg)
            c_cfg.setdefault("server", {})
            c_cfg["server"]["port"] = 8001
            c_cfg["server"]["description"] = "ChatGPT Codex CLI Dedicated Wire Gateway"
            with open(CODEX_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(c_cfg, f, allow_unicode=True, sort_keys=False)
            logger.info(f"✨ 已自动从基础配置派生 Codex CLI 专属配置文件: {CODEX_CONFIG_PATH}")
        except Exception as e:
            logger.error(f"派生 config.codex.yaml 失败: {e}")

def _get_channel_config_path(channel: str = "harness") -> str:
    return CODEX_CONFIG_PATH if channel == "codex" else HARNESS_CONFIG_PATH

def load_config(channel: str = "harness") -> dict:
    cfg_path = _get_channel_config_path(channel)
    if not os.path.exists(cfg_path):
        _ensure_channel_configs()
    if not os.path.exists(cfg_path):
        # 兜底读取 CONFIG_PATH
        cfg_path = CONFIG_PATH
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"Config file not found at {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_config(config: dict, channel: str = "harness", force_key_updates: Optional[dict] = None):
    cfg_path = _get_channel_config_path(channel)
    if os.path.exists(cfg_path):
        try:
            shutil.copy2(cfg_path, f"{cfg_path}.bak")
        except Exception as e:
            logger.warning(f"Backup config file failed: {e}")

    existing_keys = {}
    existing_enabled = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
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

    clean_providers = [
        p for p in config.get("providers", [])
        if not p.get("name", "").startswith("Mock-") and ":8999" not in str(p.get("base_url", ""))
    ]
    dump_cfg = copy.deepcopy(config)
    dump_cfg["providers"] = clean_providers

    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(dump_cfg, f, allow_unicode=True, sort_keys=False)
    logger.info(f"Config for [{channel}] saved successfully to {cfg_path}.")

# 实例化双端 FastAPI 应用
app_harness = FastAPI(title="Free Token Harness & Web Gateway", version="3.0.0")
app_codex = FastAPI(title="Free Token Codex Dedicated Gateway", version="3.0.0")

for _sub_app in [app_harness, app_codex]:
    _sub_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 保持 app 别名，兼容旧代码与测试导入
app = app_harness

class GatewayState:
    def __init__(self):
        _ensure_channel_configs()
        self.harness_config = load_config("harness")
        self.codex_config = load_config("codex")
        # 为兼容旧属性，默认 self.config 指向 harness_config
        self.config = self.harness_config
        self.stats = {
            "total_requests": 0,
            "success_requests": 0,
            "failed_requests": 0,
            "failover_events": 0,
            "tier_fallback_events": 0,
            "total_latency_sum": 0,
            "model_hits": {},
            "provider_stats": {},
            "harness": {
                "total_requests": 0,
                "success_requests": 0,
                "failed_requests": 0,
                "failover_events": 0,
                "tier_fallback_events": 0,
                "total_latency_sum": 0,
                "tokens": 0,
                "model_hits": {},
                "provider_stats": {}
            },
            "codex": {
                "total_requests": 0,
                "success_requests": 0,
                "failed_requests": 0,
                "failover_events": 0,
                "tier_fallback_events": 0,
                "total_latency_sum": 0,
                "tokens": 0,
                "model_hits": {},
                "tool_calls": {
                    "apply_patch": 0,
                    "exec_command": 0,
                    "other": 0
                },
                "provider_stats": {}
            }
        }
        self.request_logs = []
        self.tier_indices = {}
        self.start_time = time.time()
        self.provider_cooldowns = {}
        self.model_cooldowns = {}
        self._init_stats()

    def get_config(self, channel: str = "harness") -> dict:
        if channel == "codex":
            return self.codex_config
        return self.harness_config

    def _init_stats(self):
        for ch, cfg in [("harness", self.harness_config), ("codex", self.codex_config)]:
            ch_stats = self.stats[ch]["provider_stats"]
            for p in cfg.get("providers", []):
                name = p.get("name")
                if name not in ch_stats:
                    ch_stats[name] = {
                        "calls": 0,
                        "success": 0,
                        "errors": 0,
                        "last_error": "",
                        "last_latency_ms": 0,
                        "status": "Active" if p.get("enabled") else "Disabled"
                    }
                if name not in self.stats["provider_stats"]:
                    self.stats["provider_stats"][name] = dict(ch_stats[name])

    def add_log(self, entry: dict, channel: str = "global"):
        entry["channel"] = channel
        self.request_logs.insert(0, entry)
        if len(self.request_logs) > 300:
            self.request_logs.pop()

    def reload_config(self, channel: Optional[str] = None):
        mock_harness = [
            p for p in self.harness_config.get("providers", [])
            if p.get("name", "").startswith("Mock-") or ":8999" in str(p.get("base_url", ""))
        ]
        mock_codex = [
            p for p in self.codex_config.get("providers", [])
            if p.get("name", "").startswith("Mock-") or ":8999" in str(p.get("base_url", ""))
        ]
        if channel in (None, "harness"):
            self.harness_config = load_config("harness")
            if mock_harness:
                real_h = [
                    p for p in self.harness_config.get("providers", [])
                    if not p.get("name", "").startswith("Mock-") and ":8999" not in str(p.get("base_url", ""))
                ]
                self.harness_config["providers"] = mock_harness + real_h

        if channel in (None, "codex"):
            self.codex_config = load_config("codex")
            mock_to_add = mock_codex if mock_codex else mock_harness
            if mock_to_add:
                real_c = [
                    p for p in self.codex_config.get("providers", [])
                    if not p.get("name", "").startswith("Mock-") and ":8999" not in str(p.get("base_url", ""))
                ]
                self.codex_config["providers"] = mock_to_add + real_c

        self.config = self.harness_config
        self._init_stats()

state = GatewayState()

def is_model_vision_capable(model_name: str) -> bool:
    m_lower = model_name.lower()
    vision_kws = ["gemini", "vision", "vl", "omni", "4o", "pixtral", "image", "visual"]
    non_vision_kws = ["gpt-oss", "qwen3.8", "qwen3.6", "nemotron-3-ultra", "nemotron-3.5", "compound", "north-mini-code", "inkling", "deepseek"]
    if any(nv in m_lower for nv in non_vision_kws):
        return False
    return any(vk in m_lower for vk in vision_kws)

INVOKE_REGEX = re.compile(r'<(?:invoke|function_call|tool_call)\s+[^>]*name=["\']([^"\']+)["\'][^>]*>(.*?)(?:</(?:invoke|function_call|tool_call)>|$)', re.DOTALL)
PARAM_REGEX = re.compile(r'<parameter\s+[^>]*name=["\']([^"\']+)["\'][^>]*>(.*?)(?:</parameter>|(?=<parameter)|(?=</(?:invoke|function_call|tool_call)>)|$)', re.DOTALL)
TOOL_CALL_BRACKET_REGEX = re.compile(r'\[Tool Call:\s*([\w\:\-\.]+)(?:\{|\()(.*?)(?:\}|\)\])', re.DOTALL)
PREV_TOOL_REGEX = re.compile(r'(?:Previously executed tool|Tool Call|Call tool)\s*[`\'"]?([\w\:\-\.]+)[`\'"]?\s*with arguments:\s*(\{.*)', re.DOTALL)
INVOKE_PREFIXES = tuple("<invoke"[:i] for i in range(1, 8)) + tuple("<function_call"[:i] for i in range(1, 15)) + tuple("<tool_call"[:i] for i in range(1, 11)) + tuple("[Tool Call:"[:i] for i in range(1, 12)) + tuple("Previously executed tool"[:i] for i in range(5, 25))

def parse_xml_to_tool_calls(xml_text: str) -> List[Dict[str, Any]]:
    """
    Parses <invoke name="...">, <function_call name="...">, <tool_call name="...">,
    [Tool Call: name{...}], or Previously executed tool `name` with arguments: {...}
    blocks into standard OpenAI tool_calls structure.
    Also ensures required parameters like 'description' for bash are present.
    """
    matches = list(INVOKE_REGEX.finditer(xml_text))
    if not matches:
        b_matches = list(TOOL_CALL_BRACKET_REGEX.finditer(xml_text))
        if b_matches:
            tool_calls = []
            for bm in b_matches:
                t_name = bm.group(1).strip()
                t_body = bm.group(2).strip()
                args = {}
                if t_body.startswith("{") and t_body.endswith("}"):
                    try:
                        args = json.loads(t_body)
                    except Exception:
                        pass
                if not args:
                    for part in t_body.split(","):
                        if ":" in part:
                            k, v = part.split(":", 1)
                            args[k.strip()] = v.strip()
                if not args and t_body:
                    args["command"] = t_body
                if ("bash" in t_name or t_name.endswith(":bash")) and "description" not in args:
                    args["description"] = f"Run: {args.get('command', '')[:60]}"
                call_id = f"call_{uuid.uuid4().hex[:12]}"
                tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": t_name,
                        "arguments": json.dumps(args, ensure_ascii=False)
                    }
                })
            return tool_calls

        p_matches = list(PREV_TOOL_REGEX.finditer(xml_text))
        if p_matches:
            tool_calls = []
            for pm in p_matches:
                t_name = pm.group(1).strip()
                t_body = pm.group(2).strip()
                args = {}
                try:
                    args = json.loads(t_body)
                except Exception:
                    pass
                if ("bash" in t_name or t_name.endswith(":bash")) and "description" not in args:
                    args["description"] = f"Run: {args.get('command', '')[:60]}"
                call_id = f"call_{uuid.uuid4().hex[:12]}"
                tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": t_name,
                        "arguments": json.dumps(args, ensure_ascii=False)
                    }
                })
            return tool_calls
        return []

    tool_calls = []
    for match in matches:
        tool_name = match.group(1).strip()
        body = match.group(2)
        args = {}
        for p in PARAM_REGEX.finditer(body):
            args[p.group(1).strip()] = p.group(2).strip()
        if not args and body.strip():
            raw = body.strip()
            if raw.startswith("{") and raw.endswith("}"):
                try:
                    args = json.loads(raw)
                except Exception:
                    args = {"command": raw} if "bash" in tool_name else {"input": raw}
            else:
                args = {"command": raw} if "bash" in tool_name else {"input": raw}
        elif ("bash" in tool_name or tool_name.endswith(":bash")) and "command" not in args:
            if "content" in args:
                args["command"] = args["content"]
            elif "input" in args:
                args["command"] = args["input"]

        if ("bash" in tool_name or tool_name.endswith(":bash")) and "description" not in args:
            args["description"] = f"Run: {args.get('command', '')[:60]}"

        call_id = f"call_{uuid.uuid4().hex[:12]}"
        tool_calls.append({
            "id": call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(args, ensure_ascii=False)
            }
        })
    return tool_calls

def extract_and_convert_xml_tool_calls(text: str):
    """
    Splits out thinking/explanation text and parses XML/custom tool calls.
    Returns: (cleaned_text, tool_calls_list)
    """
    if not text or not any(k in text for k in ("<invoke", "<function_call", "<tool_call", "[Tool Call:", "Previously executed tool")):
        return text, []

    first_start = -1
    for m in INVOKE_REGEX.finditer(text):
        first_start = m.start()
        break
    if first_start == -1:
        for m in TOOL_CALL_BRACKET_REGEX.finditer(text):
            first_start = m.start()
            break
    if first_start == -1:
        for m in PREV_TOOL_REGEX.finditer(text):
            first_start = m.start()
            break

    if first_start == -1:
        return text, []

    cleaned_text = text[:first_start].strip()
    tool_calls = parse_xml_to_tool_calls(text)
    return cleaned_text, tool_calls

# 路由计划构建：仅保留 auto 与 deepseek-v4-flash
def build_tiered_execution_plan(requested_model: str, has_image: bool = False, has_tools: bool = False, channel: str = "harness") -> List[Dict[str, Any]]:
    req_clean = requested_model.lower().strip()
    cfg = state.get_config(channel)
    providers = cfg.get("providers", [])
    active_providers = [
        p for p in providers 
        if p.get("enabled") and p.get("api_key") and not p.get("api_key", "").startswith("YOUR_")
    ]
    # 按大厂优先级权重排序 (NVIDIA 100 > Google 95 > Groq 90 > OpenRouter 85 > 中转 40)
    active_providers.sort(key=lambda p: p.get("priority", 50), reverse=True)

    # 1. 当请求 "vision" 时，执行专属多模态视觉天梯 (Google Gemini 3.8 / 3.6 / 3.5 Flash 优先)
    if req_clean in ["vision", "vision-agent", "gemini-vision"]:
        ladders_config = cfg.get("fallback_ladders", {})
        ladder = ladders_config.get("vision", [])
        plan_tiers = []
        for tier_info in ladder:
            tier_name = tier_info.get("tier", "Vision Tier")
            target_models = tier_info.get("models", [])
            tier_candidates = []
            for target_m in target_models:
                t_lower = target_m.lower()
                m_candidates = []
                for p in active_providers:
                    p_name_lower = p.get("name", "").lower()
                    for m in p.get("models", []):
                        mid = m.get("id", "").lower()
                        up_name = m.get("upstream_model", mid)
                        if "openrouter" in p_name_lower:
                            if not (up_name.endswith(":free") or up_name == "openrouter/free"):
                                continue
                            if ":batch" in up_name:
                                continue
                        if t_lower == mid or t_lower in mid or mid in t_lower or t_lower == up_name.lower():
                            item = (p, up_name)
                            if item not in m_candidates and item not in tier_candidates:
                                m_candidates.append(item)
                m_candidates.sort(key=lambda item: item[0].get("priority", 50), reverse=True)
                tier_candidates.extend(m_candidates)
            tier_candidates = tier_candidates[:10]
            if tier_candidates:
                plan_tiers.append({
                    "tier_name": tier_name,
                    "candidates": tier_candidates
                })
            return plan_tiers

    # 2. 当请求 "auto" 时，执行【渠道商首选独占容灾天梯】(单个渠道商中已配置大模型全部失败后，再去切换下一个渠道商)
    if req_clean in ["auto", "default"]:
        plan_tiers = []

        if has_image:
            # 视觉模式：专属多模态渠道天梯 (Google AI Studio 顶级视觉优先 -> NVIDIA NIM 视觉兜底)
            vision_providers = [p for p in active_providers if any(is_model_vision_capable(m.get("id", "")) or is_model_vision_capable(m.get("upstream_model", "")) for m in p.get("models", []))]
            vision_providers.sort(key=lambda p: p.get("priority", 50), reverse=True)
            for p in vision_providers:
                p_name = p.get("name", "Unknown")
                p_priority = p.get("priority", 50)
                v_models = []
                for m in p.get("models", []):
                    mid = m.get("id", "")
                    up_name = m.get("upstream_model", mid)
                    if not up_name or ":batch" in up_name:
                        continue
                    if "openrouter" in p_name.lower() and not (up_name.endswith(":free") or up_name == "openrouter/free"):
                        continue
                    if is_model_vision_capable(up_name) and up_name not in v_models:
                        v_models.append(up_name)
                if v_models:
                    plan_tiers.append({
                        "tier_name": f"多模态视觉渠道商天梯: [{p_name}] (优先级 {p_priority})",
                        "candidates": [(p, m) for m in v_models]
                    })
            return plan_tiers

        # 编程与通用推理模式：单个渠道商中所有已配置模型全部失败后再切换下一个渠道商
        NON_CHAT_KEYWORDS = [
            "embed", "guard", "safeguard", "clip", "reward", "parse", "detector",
            "deplot", "tts", "transcribe", "whisper", "diffusion", "veo", "lyria",
            "video", "audio", "fuyu", "kosmos", "vila", "neva", "synthetic", "calibration",
            "content-safety", "translate", "creative", "med", "fin", "orpheus", "allam"
        ]

        if has_tools:
            NVIDIA_PREFERRED = [
                "deepseek-ai/deepseek-v4-flash-0731",
                "z-ai/glm-5.3",
                "z-ai/glm-5.3-flash",
                "moonshotai/kimi-k3",
                "nvidia/nemotron-3.5-lightning-30b-a3b",
                "nvidia/nemotron-3-ultra-550b-a55b",
                "nvidia/nemotron-3-super-120b-a12b"
            ]
            GROQ_PREFERRED = []
            OPENROUTER_PREFERRED = []
        else:
            NVIDIA_PREFERRED = [
                "deepseek-ai/deepseek-v4-flash-0731",
                "z-ai/glm-5.3",
                "z-ai/glm-5.3-flash",
                "moonshotai/kimi-k3",
                "nvidia/nemotron-3.5-lightning-30b-a3b",
                "nvidia/nemotron-3-ultra-550b-a55b",
                "nvidia/nemotron-3-super-120b-a12b",
                "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                "google/gemma-4-31b-it",
                "deepseek-ai/deepseek-coder-6.7b-instruct",
                "openai/gpt-oss-20b",
                "minimaxai/minimax-m3",
                "01-ai/yi-large",
                "mistralai/mistral-large-2-instruct"
            ]

            GROQ_PREFERRED = [
                "qwen/qwen3.8-27b",
                "openai/gpt-oss-120b",
                "groq/compound-mini",
                "groq/compound",
                "llama-3.3-70b-versatile",
                "qwen/qwen3.6-27b",
                "llama-3.1-8b-instant",
                "openai/gpt-oss-20b"
            ]

            OPENROUTER_PREFERRED = [
                "nvidia/nemotron-3-ultra-550b-a55b:free",
                "nvidia/nemotron-3.5-lightning:free",
                "cohere/north-mini-code:free",
                "dots-studio/dots-3-note-preview:free",
                "minimax/minimax-m3:free",
                "thinkingmachines/inkling:free",
                "thinkingmachines/inkling-small:free",
                "google/gemma-4-31b-it:free",
                "openrouter/free"
            ]

        # 遍历所有活跃渠道商 (按优先级降序：NVIDIA NIM 100 > Groq Cloud 90 > OpenRouter 85)
        for p in active_providers:
            p_name = p.get("name", "Unknown")
            p_name_lower = p_name.lower()
            p_priority = p.get("priority", 50)

            # 编程模式：100% 杜绝 Gemini 参与代码生成，仅保留纯编程与推理旗舰渠道
            if "google" in p_name_lower or "gemini" in p_name_lower:
                continue

            raw_models = p.get("models", [])
            available_upstreams = []
            for m in raw_models:
                mid = m.get("id", "")
                up_name = m.get("upstream_model", mid)
                if not up_name or ":batch" in up_name:
                    continue
                up_low = up_name.lower()
                if any(k in up_low for k in NON_CHAT_KEYWORDS):
                    continue
                if "gemini" in up_low:
                    continue
                if "openrouter" in p_name_lower:
                    if not (up_name.endswith(":free") or up_name == "openrouter/free"):
                        continue
                if up_name not in available_upstreams:
                    available_upstreams.append(up_name)

            # 确定当前渠道内的模型优选执行天梯
            if "nvidia" in p_name_lower:
                pref_list = NVIDIA_PREFERRED
            elif "groq" in p_name_lower:
                pref_list = GROQ_PREFERRED
            elif "openrouter" in p_name_lower:
                pref_list = OPENROUTER_PREFERRED
            else:
                pref_list = []

            ordered_models = []
            # 1. 优先将渠道内的核心旗舰模型排在最前
            for pref in pref_list:
                pref_low = pref.lower()
                matched = [
                    u for u in available_upstreams 
                    if u.lower() == pref_low or pref_low in u.lower() or u.lower() in pref_low
                ]
                for m in matched:
                    if m not in ordered_models:
                        ordered_models.append(m)

            # 2. 将该渠道商中其它已配置的聊天/编程模型作为后备候选排入当前天梯
            for u in available_upstreams:
                if u not in ordered_models:
                    ordered_models.append(u)

            # 各渠道商严格只保留前10个性能最好的大模型
            ordered_models = ordered_models[:10]
            if ordered_models:
                tier_candidates = [(p, m) for m in ordered_models]
                plan_tiers.append({
                    "tier_name": f"渠道商独占容灾天梯: [{p_name}] (优先级 {p_priority})",
                    "candidates": tier_candidates
                })

        return plan_tiers

    # 2. 当请求 "deepseek-v4-flash"（或指定模型）时，大厂优先轮询目标模型，并追加紧急高可用保活层
    aliases = cfg.get("model_aliases", {})
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
    if "codex" in req_clean:
        target_keys.update([
            "deepseek-ai/deepseek-v4-flash-0731",
            "deepseek-ai/deepseek-v4-flash",
            "deepseek-v4",
            "deepseek-coder",
            "codestral"
        ])

    exact_candidates = []
    fuzzy_candidates = []
    for p in active_providers:
        p_name_lower = p.get("name", "").lower()
        for m in p.get("models", []):
            mid = m.get("id", "").lower()
            up_name = m.get("upstream_model", mid)
            up_lower = up_name.lower()
            if "openrouter" in p_name_lower:
                if not (up_name.endswith(":free") or up_name == "openrouter/free"):
                    continue
                if ":batch" in up_name:
                    continue
            
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

    if not has_image:
        # 非视觉任务（编程与长流程 Agent 会话）：按指定大厂旗舰天梯顺序追加第一天梯高可用容灾候选
        # 顺序严格保证：deepseek-ai -> z-ai -> moonshotai -> nvidia
        ordered_fallbacks = [
            "z-ai/glm-5.3",
            "z-ai/glm-5.3-flash",
            "moonshotai/kimi-k3",
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "nvidia/nemotron-3-ultra-550b-a55b"
        ]
        for tf in ordered_fallbacks:
            for p in active_providers:
                if "nvidia" in p.get("name", "").lower():
                    for m in p.get("models", []):
                        mid = m.get("upstream_model") or m.get("id")
                        if mid == tf:
                            item = (p, mid)
                            if item not in candidates:
                                candidates.append(item)

    if not candidates:
        for p in active_providers:
            up_target = alias_target if alias_target != requested_model else requested_model
            item = (p, up_target)
            if item not in candidates:
                candidates.append(item)
        candidates.sort(key=lambda item: item[0].get("priority", 50), reverse=True)

    if has_tools:
        # 严格过滤：在工具调用模式下，坚决剔除不支持 tool calling 的模型 (如 openrouter/free, groq/compound, qwen)
        candidates = [
            c for c in candidates 
            if not ("openrouter" in c[0].get("name", "").lower() and (c[1] == "openrouter/free" or c[1].endswith(":free")))
            and "compound" not in c[1].lower()
            and "qwen" not in c[1].lower()
        ]

    plans = [{
        "tier_name": f"专属渠道轮询: {requested_model}",
        "candidates": candidates
    }]

    # 为保障长流程 Agent (如 30+ 轮自动化编码任务) 绝不因上游单模型瞬时超载或挂起超时而崩溃，追加多维度极速保活兜底层
    if not has_image:
        candidates = [c for c in candidates if "gemini" not in c[1].lower()]

    emergency_candidates = []
    if not has_image:
        if has_tools:
            # 工具/Agent 会话：严格使用经过验证的原生 Tool Calling 旗舰模型，杜绝非工具模型导致客户端假死
            emergency_target_models = [
                "deepseek-ai/deepseek-v4-flash-0731",
                "z-ai/glm-5.3",
                "z-ai/glm-5.3-flash",
                "moonshotai/kimi-k3",
                "nvidia/nemotron-3.5-lightning-30b-a3b",
                "nvidia/nemotron-3-ultra-550b-a55b",
                "nvidia/nemotron-3-super-120b-a12b",
            ]
        else:
            # 编程长会话：100% 杜绝 Gemini 介入，严格使用顶级代码/推理大模型兜底
            emergency_target_models = [
                "deepseek-ai/deepseek-v4-flash-0731",
                "z-ai/glm-5.3",
                "z-ai/glm-5.3-flash",
                "moonshotai/kimi-k3",
                "nvidia/nemotron-3.5-lightning-30b-a3b",
                "nvidia/nemotron-3-ultra-550b-a55b",
                "nvidia/nemotron-3-super-120b-a12b",
                "openai/gpt-oss-120b",
                "qwen/qwen3.8-27b",
                "openrouter/free"
            ]
    else:
        # 视觉会话：由 Google Gemini 旗舰与开源多模态接管
        emergency_target_models = [
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "meta/llama-3.2-11b-vision-instruct"
        ]
    for target_m in emergency_target_models:
        t_lower = target_m.lower()
        for p in active_providers:
            p_name_lower = p.get("name", "").lower()
            for m in p.get("models", []):
                mid = m.get("id", "").lower()
                up_name = m.get("upstream_model", mid)
                if "openrouter" in p_name_lower:
                    if not (up_name.endswith(":free") or up_name == "openrouter/free"):
                        continue
                    if ":batch" in up_name:
                        continue
                if t_lower == mid or t_lower == up_name.lower() or t_lower in mid:
                    item = (p, up_name)
                    if item not in candidates and item not in emergency_candidates:
                        emergency_candidates.append(item)
    if emergency_candidates:
        if has_tools:
            emergency_candidates = [
                c for c in emergency_candidates 
                if not ("openrouter" in c[0].get("name", "").lower() and (c[1] == "openrouter/free" or c[1].endswith(":free")))
                and "compound" not in c[1].lower()
                and "qwen" not in c[1].lower()
            ]
        if emergency_candidates:
            emergency_candidates.sort(key=lambda item: item[0].get("priority", 50), reverse=True)
            plans.append({
                "tier_name": f"长流程高可用保活兜底层 (Groq LPU / Nemotron 550B 极速接管)",
                "candidates": emergency_candidates
            })
    return plans

# 1. 深度复刻 Linear.app 官方设计系统控制台（单页聚合双轨三 Tab 版）
from dashboard_html import get_dashboard_html

@app_harness.get("/", response_class=HTMLResponse)
async def dashboard():
    state._init_stats()
    providers_json = json.dumps(state.harness_config.get("providers", []))
    harness_port = state.harness_config.get("server", {}).get("port", 8000)
    codex_port = state.codex_config.get("server", {}).get("port", 8001)
    return get_dashboard_html(providers_json, harness_port, codex_port)

# 2. 交互控制 API
class ToggleRequest(BaseModel):
    name: str
    enabled: bool
    channel: Optional[str] = "both"

class UpdateKeyRequest(BaseModel):
    name: str
    api_key: str
    channel: Optional[str] = "both"

class DeleteProviderRequest(BaseModel):
    name: str
    channel: Optional[str] = "both"

class TestKeyRequest(BaseModel):
    name: str
    channel: Optional[str] = "harness"

@app_harness.post("/api/providers/toggle")
async def api_toggle_provider(req: ToggleRequest):
    target_channels = ["harness", "codex"] if req.channel == "both" else [req.channel or "harness"]
    updated = False
    for ch in target_channels:
        cfg = state.get_config(ch)
        for p in cfg.get("providers", []):
            if p.get("name") == req.name:
                p["enabled"] = req.enabled
                updated = True
                save_config(cfg, channel=ch)
                break
    if not updated:
        raise HTTPException(status_code=404, detail=f"未找到渠道: {req.name}")
    state.reload_config()
    return {"status": "ok", "name": req.name, "enabled": req.enabled}

@app_harness.post("/api/providers/update_key")
async def api_update_key(req: UpdateKeyRequest):
    target_channels = ["harness", "codex"] if req.channel == "both" else [req.channel or "harness"]
    updated = False
    for ch in target_channels:
        cfg = state.get_config(ch)
        for p in cfg.get("providers", []):
            if p.get("name") == req.name:
                p["api_key"] = req.api_key
                if req.api_key and not req.api_key.startswith("YOUR_"):
                    p["enabled"] = True
                updated = True
                save_config(cfg, channel=ch, force_key_updates={req.name: req.api_key})
                break
    if not updated:
        raise HTTPException(status_code=404, detail=f"未找到渠道: {req.name}")
    state.reload_config()
    return {"status": "ok", "name": req.name}

@app_harness.post("/api/providers/delete")
async def api_delete_provider(req: DeleteProviderRequest):
    target_channels = ["harness", "codex"] if req.channel == "both" else [req.channel or "harness"]
    updated = False
    for ch in target_channels:
        cfg = state.get_config(ch)
        providers = cfg.get("providers", [])
        new_providers = [p for p in providers if p.get("name") != req.name]
        if len(new_providers) != len(providers):
            cfg["providers"] = new_providers
            save_config(cfg, channel=ch)
            updated = True
    if not updated:
        raise HTTPException(status_code=404, detail=f"未找到渠道: {req.name}")
    state.reload_config()
    return {"status": "ok", "deleted": req.name}

@app_harness.get("/api/logs")
async def api_get_logs(channel: str = "all"):
    if channel == "all":
        return state.request_logs
    return [l for l in state.request_logs if l.get("channel") == channel]

@app_harness.post("/api/logs/clear")
async def api_clear_logs():
    state.request_logs.clear()
    return {"status": "ok", "message": "Logs cleared"}

@app_harness.get("/api/stats")
async def api_get_stats():
    state._init_stats()
    last_hit = None
    for l in state.request_logs:
        p_name = l.get("final_provider") or l.get("provider")
        m_name = l.get("final_model") or l.get("upstream_model")
        if p_name and p_name not in ("Exhausted", "None") and m_name and m_name not in ("None", ""):
            last_hit = {
                "channel": l.get("channel", "global"),
                "requested_model": l.get("requested_model", l.get("model", "auto")),
                "provider": p_name,
                "model": m_name,
                "latency_ms": l.get("latency_ms", l.get("latency", 0)),
                "time": l.get("time", "")
            }
            break

    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "global": {
            "total_requests": state.stats.get("total_requests", 0),
            "success_requests": state.stats.get("success_requests", 0),
            "failed_requests": state.stats.get("failed_requests", 0),
            "failover_events": state.stats.get("failover_events", 0),
            "tier_fallback_events": state.stats.get("tier_fallback_events", 0),
            "total_latency_sum": state.stats.get("total_latency_sum", 0),
            "model_hits": state.stats.get("model_hits", {}),
        },
        "harness": state.stats.get("harness", {}),
        "codex": state.stats.get("codex", {}),
        "last_hit": last_hit,
        "harness_port": state.harness_config.get("server", {}).get("port", 8000),
        "codex_port": state.codex_config.get("server", {}).get("port", 8001),
        "active_providers": {
            "harness": [p.get("name") for p in state.harness_config.get("providers", []) if p.get("enabled")],
            "codex": [p.get("name") for p in state.codex_config.get("providers", []) if p.get("enabled")]
        }
    }

@app_harness.get("/api/config/harness")
async def api_get_harness_config():
    if not os.path.exists(HARNESS_CONFIG_PATH):
        _ensure_channel_configs()
    with open(HARNESS_CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    return {"status": "ok", "channel": "harness", "path": HARNESS_CONFIG_PATH, "content": content}

@app_harness.post("/api/config/harness")
async def api_save_harness_config(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    content = body.get("content")
    if not content or not isinstance(content, str):
        raise HTTPException(status_code=400, detail="Missing or invalid 'content' field")
    try:
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            raise ValueError("YAML content must be a dictionary")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"YAML 语法解析错误: {str(e)}")
    
    if os.path.exists(HARNESS_CONFIG_PATH):
        shutil.copy2(HARNESS_CONFIG_PATH, f"{HARNESS_CONFIG_PATH}.bak")
    with open(HARNESS_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    state.reload_config("harness")
    logger.info("config.harness.yaml updated and hot-reloaded.")
    return {"status": "ok", "message": "DeepSeek Harness 配置已成功保存并即时热重载！"}

@app_harness.get("/api/config/codex")
async def api_get_codex_config():
    if not os.path.exists(CODEX_CONFIG_PATH):
        _ensure_channel_configs()
    with open(CODEX_CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    return {"status": "ok", "channel": "codex", "path": CODEX_CONFIG_PATH, "content": content}

@app_harness.post("/api/config/codex")
async def api_save_codex_config(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    content = body.get("content")
    if not content or not isinstance(content, str):
        raise HTTPException(status_code=400, detail="Missing or invalid 'content' field")
    try:
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            raise ValueError("YAML content must be a dictionary")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"YAML 语法解析错误: {str(e)}")
    
    if os.path.exists(CODEX_CONFIG_PATH):
        shutil.copy2(CODEX_CONFIG_PATH, f"{CODEX_CONFIG_PATH}.bak")
    with open(CODEX_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    state.reload_config("codex")
    logger.info("config.codex.yaml updated and hot-reloaded.")
    return {"status": "ok", "message": "Codex CLI 配置已成功保存并即时热重载！"}

@app_harness.post("/api/tools/sync-codex-config")
async def api_sync_codex_config():
    codex_conf_path = os.path.expanduser("~/.codex/config.toml")
    target_port = state.codex_config.get("server", {}).get("port", 8001)
    target_url = f"http://127.0.0.1:{target_port}/v1"
    
    if not os.path.exists(codex_conf_path):
        os.makedirs(os.path.dirname(codex_conf_path), exist_ok=True)
        default_toml = f'''model = "auto"
model_provider = "custom"

[model_providers.custom]
name = "FreeToken Gateway"
base_url = "{target_url}"
wire_api = "responses"
'''
        with open(codex_conf_path, "w", encoding="utf-8") as f:
            f.write(default_toml)
        return {
            "status": "ok",
            "message": f"已自动创建 ~/.codex/config.toml 并设置 base_url 为 {target_url}",
            "base_url": target_url
        }
    
    with open(codex_conf_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    shutil.copy2(codex_conf_path, f"{codex_conf_path}.bak")
    
    new_content, n = re.subn(
        r'(base_url\s*=\s*["\'])http://(?:127\.0\.0\.1|localhost):\d+/v1(["\'])',
        rf'\g<1>{target_url}\g<2>',
        content
    )
    if n == 0:
        if "base_url" in content:
            new_content = re.sub(
                r'(base_url\s*=\s*["\']).*?(["\'])',
                rf'\g<1>{target_url}\g<2>',
                content,
                count=1
            )
        else:
            new_content = content + f'\n[model_providers.custom]\nname = "FreeToken Gateway"\nbase_url = "{target_url}"\nwire_api = "responses"\n'

    with open(codex_conf_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    return {
        "status": "ok",
        "message": f"~/.codex/config.toml 已成功同步至专用端口 {target_port} ({target_url})",
        "base_url": target_url
    }

@app_harness.post("/api/providers/test")
async def api_test_provider(req: TestKeyRequest):
    target_cfg = state.get_config(req.channel or "harness")
    target = None
    for p in target_cfg.get("providers", []):
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

    KNOWN_DEAD_MODELS = {
        "deepseek-ai/deepseek-v4-pro-0813",
        "meta/llama-3.3-70b-instruct",
        "moonshotai/kimi-k2.6",
        "mistralai/codestral-22b-instruct-v0.1"
    }

    # Curated Top Free Models Priorities (最强最新模型置顶排在最前)
    curated_priorities = {
        "NVIDIA NIM": [
            "deepseek-ai/deepseek-v4-flash-0731",
            "z-ai/glm-5.3",
            "z-ai/glm-5.3-flash",
            "moonshotai/kimi-k3",
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "nvidia/nemotron-3-super-120b-a12b",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "meta/llama-3.2-11b-vision-instruct",
            "meta/llama-3.2-90b-vision-instruct",
            "google/gemma-4-31b-it",
            "deepseek-ai/deepseek-coder-6.7b-instruct",
            "openai/gpt-oss-20b",
            "minimaxai/minimax-m3",
            "01-ai/yi-large",
            "mistralai/mistral-large-2-instruct"
        ],
        "Google AI Studio": [
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-flash-lite-latest",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
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
        "OpenRouter (Global)": [
            "thinkingmachines/inkling-small:free",
            "thinkingmachines/inkling:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "nvidia/nemotron-3.5-lightning:free",
            "dots-studio/dots-3-note-preview:free",
            "minimax/minimax-m3:free",
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "inclusionai/ling-3.0-flash-fin:free",
            "inclusionai/ling-3.0-flash-sante:free",
            "poolside/laguna-s-2.1:free",
            "poolside/laguna-xs-2.1:free",
            "cohere/north-mini-code:free",
            "openrouter/free"
        ]
    }

    # Ensure OpenRouter and Groq Cloud exist in providers list so discovered models can be surfaced
    if "OpenRouter (Global)" not in prov_map:
        openrouter_prov = {
            "name": "OpenRouter (Global)",
            "category": "全球聚合",
            "enabled": True,
            "weight": 10,
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "",
            "models": discovered_models.get("OpenRouter (Global)", [
                {"id": m, "upstream_model": m} for m in curated_priorities.get("OpenRouter (Global)", [])
            ]),
            "priority": 85
        }
        providers.append(openrouter_prov)
        prov_map["OpenRouter (Global)"] = openrouter_prov

    if "Groq Cloud" not in prov_map:
        groq_prov = {
            "name": "Groq Cloud",
            "category": "极速芯片",
            "enabled": False,
            "weight": 10,
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": "",
            "models": [
                {"id": m, "upstream_model": m} for m in curated_priorities.get("Groq Cloud", [])
            ],
            "priority": 90
        }
        providers.append(groq_prov)
        prov_map["Groq Cloud"] = groq_prov

    added_count = 0
    updated_providers = []

    # Merge models into providers
    for p in providers:
        p_name = p.get("name", "")
        existing_models = p.get("models", [])
        existing_ids = {m.get("id") for m in existing_models}
        existing_upstreams = {m.get("upstream_model") for m in existing_models}

        # Filter out known dead models
        existing_models = [
            m for m in existing_models
            if m.get("id") not in KNOWN_DEAD_MODELS and m.get("upstream_model") not in KNOWN_DEAD_MODELS
        ]

        candidates = []
        for cur_id in curated_priorities.get(p_name, []):
            if cur_id not in KNOWN_DEAD_MODELS:
                candidates.append({"id": cur_id, "upstream_model": cur_id})

        disc_list = discovered_models.get(p_name, [])
        valid_upstream_ids = {m.get("id") for m in disc_list}
        for disc_m in disc_list:
            did = disc_m.get("id")
            if did and did not in KNOWN_DEAD_MODELS:
                candidates.append(disc_m)

        new_top_models = []
        seen = set()
        for cand in candidates:
            cid = cand.get("id")
            cup = cand.get("upstream_model") or cid
            if cid and cid not in seen:
                # If we have verified active upstream list, filter out candidates not present
                if valid_upstream_ids and cid not in valid_upstream_ids and cup not in valid_upstream_ids:
                    continue
                seen.add(cid)
                if cid not in existing_ids and cup not in existing_upstreams:
                    added_count += 1
                new_top_models.append({"id": cid, "upstream_model": cup})

        for old_m in existing_models:
            old_id = old_m.get("id")
            old_up = old_m.get("upstream_model") or old_id
            if old_id and old_id not in seen:
                if valid_upstream_ids and old_id not in valid_upstream_ids and old_up not in valid_upstream_ids:
                    continue
                seen.add(old_id)
                new_top_models.append(old_m)

        p["models"] = new_top_models
        updated_providers.append(p_name)

    # Synchronize fallback ladders for "auto" and "vision" (严格代码与视觉隔离)
    state.config["fallback_ladders"] = {
        "auto": [
            {
                "tier": "Tier 1: 顶级大厂编程与推理旗舰层 (DeepSeek V4 / GLM 5.3 / Kimi K3 / Nemotron 3.5 / Qwen 3.8 / GPT-OSS 120B)",
                "models": [
                    "deepseek-ai/deepseek-v4-flash-0731",
                    "z-ai/glm-5.3",
                    "z-ai/glm-5.3-flash",
                    "moonshotai/kimi-k3",
                    "nvidia/nemotron-3.5-lightning-30b-a3b",
                    "nvidia/nemotron-3-ultra-550b-a55b",
                    "qwen/qwen3.8-27b",
                    "openai/gpt-oss-120b"
                ]
            },
            {
                "tier": "Tier 2: LPU 极速芯片与全尺寸开源旗舰层 (Nemotron 3.5 / Groq Qwen 3.8 / GPT-OSS 120B)",
                "models": [
                    "nvidia/nemotron-3.5-lightning-30b-a3b",
                    "openai/gpt-oss-120b",
                    "qwen/qwen3.8-27b",
                    "groq/compound-mini",
                    "google/gemma-4-31b-it"
                ]
            },
            {
                "tier": "Tier 3: 开源百万长上下文与深度思维链推理层 (Thinking Machines 1M / Dots 512K / Nemotron 1M)",
                "models": [
                    "thinkingmachines/inkling-small:free",
                    "thinkingmachines/inkling:free",
                    "nvidia/nemotron-3.5-lightning:free",
                    "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "dots-studio/dots-3-note-preview:free",
                    "minimaxai/minimax-m3",
                    "minimax/minimax-m3:free"
                ]
            },
            {
                "tier": "Tier 4: 全球高可用动态免费兜底层 (OpenRouter Free 动态智能路由池)",
                "models": [
                    "openrouter/free"
                ]
            }
        ],
        "vision": [
            {
                "tier": "Tier 1: Google Gemini 顶级多模态视觉旗舰层 (Gemini 3.8 / 3.7 / 3.6 / 3.5 Flash · 100万上下文)",
                "models": [
                    "gemini-3.8-flash",
                    "gemini-3.7-flash",
                    "gemini-3.6-flash",
                    "gemini-3.5-flash",
                    "gemini-flash-latest"
                ]
            },
            {
                "tier": "Tier 2: 开源极速多模态视觉兜底层 (Llama 3.2 11B / 90B Vision)",
                "models": [
                    "meta/llama-3.2-11b-vision-instruct",
                    "meta/llama-3.2-90b-vision-instruct"
                ]
            }
        ]
    }
    state.config["exposed_models"] = [
        "auto",
        "deepseek-v4-flash",
        "glm-5.3",
        "glm-5.3-flash",
        "kimi-k3",
        "nemotron-3.5",
        "vision",
        "image-gen"
    ]

    aliases = state.config.get("model_aliases", {})
    aliases.update({
        "auto": "auto",
        "deepseek-v4-flash": "deepseek-ai/deepseek-v4-flash-0731",
        "deepseek-v4": "deepseek-ai/deepseek-v4-flash-0731",
        "DeepSeek-V4-Flash": "deepseek-ai/deepseek-v4-flash-0731",
        "deepseek": "deepseek-ai/deepseek-v4-flash-0731",
        "glm-5.3": "z-ai/glm-5.3",
        "glm-5.3-flash": "z-ai/glm-5.3-flash",
        "glm": "z-ai/glm-5.3",
        "glm5": "z-ai/glm-5.3",
        "kimi-k3": "moonshotai/kimi-k3",
        "kimi": "moonshotai/kimi-k3",
        "kimi3": "moonshotai/kimi-k3",
        "nemotron-3.5": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nemotron": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nemotron-ultra": "nvidia/nemotron-3-ultra-550b-a55b",
        "gemini-3.8": "gemini-3.8-flash",
        "gemini-3.8-flash": "gemini-3.8-flash",
        "vision": "vision",
        "vision-agent": "vision",
        "codex": "deepseek-ai/deepseek-v4-flash-0731",
        "image-gen": "image-gen",
        "flux": "image-gen",
        "gpt-5.3-codex": "auto",
        "gpt-5.2-codex": "auto",
        "gpt-5.1-codex": "auto",
        "gpt-5-codex": "auto"
    })
    state.config["model_aliases"] = aliases
    state.config["providers"] = providers

    save_config(state.config)
    state.reload_config()

    top_models_summary = [
        {"name": "deepseek-ai/deepseek-v4-flash-0731", "provider": "NVIDIA NIM", "context": "128,000", "tag": "🔥 2026 旗舰代码/推理 · 满血首选"},
        {"name": "z-ai/glm-5.3", "provider": "NVIDIA NIM", "context": "200,000", "tag": "🌟 智谱 GLM 5.3 旗舰 · 深度思考"},
        {"name": "z-ai/glm-5.3-flash", "provider": "NVIDIA NIM", "context": "200,000", "tag": "⚡ GLM 5.3 Flash · 极速推理"},
        {"name": "moonshotai/kimi-k3", "provider": "NVIDIA NIM", "context": "262,144", "tag": "🌙 Kimi K3 推理旗舰 · 满血长上下文"},
        {"name": "nvidia/nemotron-3.5-lightning-30b-a3b", "provider": "NVIDIA NIM", "context": "128,000", "tag": "⚡ Nemotron 3.5 闪电极速推理"},
        {"name": "gemini-3.8-flash", "provider": "Google AI Studio", "context": "1,048,576", "tag": "👁️ Gemini 3.8 · 百万多模态旗舰"},
        {"name": "meta/llama-3.2-11b-vision-instruct", "provider": "NVIDIA NIM", "context": "131,072", "tag": "👁️ Llama 3.2 视觉理解"},
        {"name": "thinkingmachines/inkling-small:free", "provider": "OpenRouter", "context": "1,048,576", "tag": "🧠 100万长上下文 · 思维链"}
    ]

    total_models = sum(len(p.get("models", [])) for p in providers)

    return {
        "status": "ok",
        "message": "成功检索并更新最新最强免费模型矩阵！",
        "added_count": added_count,
        "total_models": total_models,
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

# 3. 精简模型列表接口 (/v1/models)
@app_harness.get("/v1/models")
@app_harness.get("/models")
async def list_models_harness():
    return await list_models(channel="harness")

@app_codex.get("/v1/models")
@app_codex.get("/models")
async def list_models_codex():
    return await list_models(channel="codex")

async def list_models(channel: str = "harness"):
    cfg = state.get_config(channel)
    exposed = cfg.get("exposed_models", ["auto", "deepseek-v4-flash", "codex"])
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

# 💰 兼容 DeepSeek-Harness 与 Codex 虚拟额度接口
@app_harness.get("/v1/dashboard/billing/credit_grants")
@app_harness.get("/dashboard/billing/credit_grants")
@app_harness.get("/v1/dashboard/billing/usage")
@app_harness.get("/dashboard/billing/usage")
@app_harness.get("/v1/users/current")
@app_harness.get("/v1/billing/subscription")
@app_codex.get("/v1/dashboard/billing/credit_grants")
@app_codex.get("/dashboard/billing/credit_grants")
@app_codex.get("/v1/dashboard/billing/usage")
@app_codex.get("/dashboard/billing/usage")
@app_codex.get("/v1/users/current")
@app_codex.get("/v1/billing/subscription")
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

# 流式空闲哨兵：aiter_with_idle 在上游静默时产出该对象，用于注入 SSE 保活
STREAM_IDLE = object()

async def aiter_with_idle(aiter_obj, idle_timeout: float = 5.0):
    """逐块转发上游异步迭代器，上游静默超过 idle_timeout 时产出 STREAM_IDLE 哨兵。

    严禁用 asyncio.wait_for 包裹 __anext__()：超时会取消该协程，把 CancelledError
    抛进上游异步生成器并令其就地关闭，之后再调用 __anext__() 只会得到
    StopAsyncIteration，表现为响应在中途被静默截断且被误判为正常完结。
    这里始终复用同一个 pending task，超时只是返回控制权，绝不取消上游读取。
    """
    pending = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(aiter_obj.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=idle_timeout)
            if not done:
                yield STREAM_IDLE
                continue
            task, pending = pending, None
            try:
                chunk = task.result()
            except StopAsyncIteration:
                return
            yield chunk
    finally:
        if pending is not None:
            pending.cancel()

def stream_peek_has_substance(peek_bytes: bytes) -> bool:
    """精准嗅探 SSE 预读数据是否包含实质有效内容 (非空文本、推理过程、工具调用或完结标识)，排除纯空 assistant 块"""
    try:
        text = peek_bytes.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            payload_str = line[5:].strip()
            if not payload_str:
                continue
            payload = json.loads(payload_str)
            for choice in payload.get("choices", []):
                if choice.get("finish_reason"):
                    return True
                delta = choice.get("delta", {})
                content = delta.get("content")
                if content is not None and len(content) > 0:
                    return True
                rc = delta.get("reasoning_content")
                if rc is not None and len(rc) > 0:
                    return True
                if delta.get("tool_calls"):
                    return True
    except Exception:
        pass
    return False

# 4. 核心转发接口 (/v1/chat/completions)
@app_harness.post("/v1/chat/completions")
@app_harness.post("/chat/completions")
async def chat_completions_harness_route(request: Request):
    return await chat_completions(request, channel="harness")

@app_codex.post("/v1/chat/completions")
@app_codex.post("/chat/completions")
async def chat_completions_codex_route(request: Request):
    return await chat_completions(request, channel="codex")

async def chat_completions(request: Request, channel: Optional[str] = None):
    ua = request.headers.get("user-agent", "").lower()
    if channel:
        eff_channel = channel
    elif request.headers.get("x-channel") == "codex" or (request.url and request.url.port == 8001) or "codex" in ua:
        eff_channel = "codex"
    else:
        eff_channel = "harness"

    req_time_str = time.strftime("%H:%M:%S")
    req_start_time = time.time()
    state.stats["total_requests"] += 1
    if eff_channel in state.stats:
        state.stats[eff_channel]["total_requests"] += 1
    
    body = await request.json()
    requested_model = body.get("model", "auto")
    is_stream = body.get("stream", False)

    client_tag = "Codex-CLI" if eff_channel == "codex" else ("DeepSeek-Harness" if ("harness" in ua or "dsh" in ua or "node" in ua) else "Chat Client")
    logger.info(f"👉 [{client_tag} / Chat Completions Request ({eff_channel})]: model={requested_model}, is_stream={is_stream}")
    
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

    effective_model = requested_model
    if has_image and not is_model_vision_capable(requested_model):
        logger.info(f"👁️ 【多模态视觉智能协同】检测到图像输入！[{requested_model}] 无原生视觉感知能力，已自动无缝切换至多模态视觉专属天梯 (Google Gemini 3.8 / 3.6 / 3.5 Flash)...")
        effective_model = "vision"

    has_tools = bool(forward_body.get("tools"))
    tiered_plan = build_tiered_execution_plan(effective_model, has_image=has_image, has_tools=has_tools, channel=eff_channel)
    if not tiered_plan:
        state.stats["failed_requests"] += 1
        if eff_channel in state.stats:
            state.stats[eff_channel]["failed_requests"] += 1
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

    for tier_idx, tier_obj in enumerate(tiered_plan, 1):
        tier_name = tier_obj["tier_name"]
        candidates = tier_obj["candidates"]
        logger.info(f"🏛️ 【渠道商天梯 Tier {tier_idx}/{len(tiered_plan)}】启动: {tier_name} (包含 {len(candidates)} 个候选模型)")

        now_ts = time.time()
        # 清理已过期的模型熔断冷却
        state.model_cooldowns = {k: v for k, v in state.model_cooldowns.items() if v > now_ts}

        for cand_idx, (provider, upstream_model) in enumerate(candidates, 1):
            p_name = provider.get("name", "Unknown")
            model_key = f"{p_name}:{upstream_model}"
            logger.info(f"👉 [{p_name}] 正在尝试候选模型 ({cand_idx}/{len(candidates)}): {upstream_model}...")

            # 熔断冷却拦截：若模型在冷却期内，只要全局执行计划中还有其它未冷却的可用候选，就坚决跳过
            cooldown_until = state.model_cooldowns.get(model_key, 0)
            if now_ts < cooldown_until:
                has_active_alternative = any(
                    now_ts >= state.model_cooldowns.get(f"{p_alt.get('name')}:{m_alt}", 0)
                    for t_alt in tiered_plan
                    for p_alt, m_alt in t_alt["candidates"]
                    if f"{p_alt.get('name')}:{m_alt}" != model_key
                )
                if has_active_alternative:
                    remain_secs = int(cooldown_until - now_ts)
                    logger.info(f"⏳ [{p_name} | {upstream_model}] 处于熔断冷却中 (剩余 {remain_secs}s)，快速绕行至其它可用候选...")
                    continue
                else:
                    logger.info(f"⚡ [{p_name} | {upstream_model}] 全网候选均处于冷却中，解除冷却作为最终兜底尝试...")
                    state.model_cooldowns.pop(model_key, None)

            base_url = provider.get("base_url", "").rstrip("/")
            api_key = provider.get("api_key", "")

            call_body = dict(forward_body)
            call_body["model"] = upstream_model

            # 1. Google Gemini 特殊协议适配
            if "google" in base_url.lower() or "generativelanguage" in base_url.lower():
                call_body.pop("store", None)
                call_body.pop("metadata", None)

            if call_body.get("tools"):
                action_rule = (
                    "CRITICAL AGENT RULE: You are an autonomous coding agent. "
                    "Whenever your next step involves inspecting, creating, modifying, or testing files or directories, "
                    "you MUST invoke the corresponding tool (e.g. exec_command) immediately in the very same response. "
                    "NEVER output conversational messages saying what you will do (e.g. '开始批量创建...', '我会一次性写入...') "
                    "without issuing the tool call in that same turn. Execute the tool call directly!"
                )
                msgs = list(call_body.get("messages", []))
                if msgs and msgs[0].get("role") == "system":
                    if "CRITICAL AGENT RULE" not in msgs[0].get("content", ""):
                        msgs[0] = dict(msgs[0])
                        msgs[0]["content"] = msgs[0]["content"] + f"\n\n{action_rule}"
                elif msgs:
                    msgs = [{"role": "system", "content": action_rule}] + msgs
                call_body["messages"] = msgs

            # 2. Groq Cloud 协议适配
            if "groq" in base_url.lower():
                # Groq 严格禁止在 messages 中携带 reasoning_content，否则报 400
                messages = call_body.get("messages", [])
                cleaned_messages = []
                for m in messages:
                    if isinstance(m, dict) and "reasoning_content" in m:
                        m_copy = dict(m)
                        m_copy.pop("reasoning_content", None)
                        cleaned_messages.append(m_copy)
                    else:
                        cleaned_messages.append(m)
                call_body["messages"] = cleaned_messages

            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            if "openrouter" in base_url.lower():
                headers["HTTP-Referer"] = "https://github.com/deepseek-ai/deepseek-harness"
                headers["X-Title"] = "DeepSeek-Harness"
                # 防止超长上下文叠加超大 max_tokens (如 32768) 触发 OpenRouter 402 预估额度拦截
                if call_body.get("max_tokens", 0) > 4096:
                    call_body["max_tokens"] = 4096

            p_stat = state.stats["provider_stats"].setdefault(p_name, {
                "calls": 0, "success": 0, "errors": 0, "last_error": "", "last_latency_ms": 0, "status": "Active"
            })
            p_stat["calls"] += 1

            start_time = time.time()
            logger.info(f"🔄 [{tier_name}] 尝试渠道 [{p_name} (P:{provider.get('priority', 50)})] -> 真实模型 [{upstream_model}]...")

            try:
                # 智能两阶段与大上下文自适应超时控制：
                # 1. 阶段一（连接与响应头）：设置 60s 宽裕超时，保障跨境大请求体（200+ 轮历史）网络握手不被误熔断
                # 2. 阶段二（流式生成）：分块流式读取设置 300s 宽裕超时，保障超大上下文与深度思考/海量工具调用永不被误熔断
                p_read_timeout = 300.0 if is_stream else float(provider.get("timeout", 120.0))
                client_timeout = httpx.Timeout(p_read_timeout, connect=30.0, read=p_read_timeout, write=120.0, pool=30.0)
                client = httpx.AsyncClient(timeout=client_timeout)

                if is_stream:
                    req = client.build_request("POST", url, headers=headers, json=call_body)
                    initial_header_timeout = 60.0
                    try:
                        response = await asyncio.wait_for(client.send(req, stream=True), timeout=initial_header_timeout)
                    except Exception as header_err:
                        await client.aclose()
                        model_key = f"{p_name}:{upstream_model}"
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        logger.warning(f"⏱️ [{p_name} | {upstream_model}] 建立流式连接与等待响应头超时 ({header_err})，开启 30s 冷却并秒级转移至下一候选...")
                        raise HTTPException(status_code=504, detail=f"[{p_name}] 等待响应头超时: {header_err}")

                    # 若遇到瞬时超载 (529/503) 或限流 (429)，开启 30s 冷却并秒级故障转移至下一候选
                    if response.status_code in [429, 503, 529]:
                        error_text = await response.aread()
                        error_str = error_text.decode("utf-8", errors="ignore")
                        logger.warning(f"⚠️ [{p_name} | {upstream_model}] 遇到限流/超载 (HTTP {response.status_code})，开启 30s 冷却并秒级转移至下一候选！")
                        await response.aclose()
                        await client.aclose()
                        model_key = f"{p_name}:{upstream_model}"
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        raise HTTPException(status_code=response.status_code, detail=f"[{p_name}] 服务瞬时限流/超载 (HTTP {response.status_code}): {error_str[:200]}")

                    if response.status_code >= 400:
                        error_text = await response.aread()
                        error_str = error_text.decode("utf-8", errors="ignore")
                        logger.warning(f"❌ [{p_name} | {upstream_model}] HTTP {response.status_code}: {error_str[:300]}")
                        await response.aclose()
                        await client.aclose()
                        model_key = f"{p_name}:{upstream_model}"
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        raise HTTPException(status_code=response.status_code, detail=f"[{p_name}] {error_str}")

                    # 🌟 首包深度探针：预读取流数据，必须嗅探到实质有效内容（非空文本、推理过程、工具调用或完结标识）
                    # 依据上下文规模智能自适应延长 TTFT 嗅探窗口，防止超长上下文 GPU 预填充耗时被误判为假死
                    stream_iter = response.aiter_bytes()
                    peek_chunks = []
                    has_substance = False
                    try:
                        base_peek = float(provider.get("peek_timeout", 60.0))
                        msgs_count = len(call_body.get("messages", []))
                        peek_timeout = max(base_peek, 85.0) if msgs_count > 30 else base_peek
                        peek_deadline = time.time() + peek_timeout
                        while time.time() < peek_deadline and len(peek_chunks) < 60:
                            remaining = max(0.5, peek_deadline - time.time())
                            chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=remaining)
                            peek_chunks.append(chunk)
                            if stream_peek_has_substance(b"".join(peek_chunks)):
                                has_substance = True
                                break
                    except (StopIteration, StopAsyncIteration, asyncio.TimeoutError):
                        pass
                    except Exception as peek_err:
                        await response.aclose()
                        await client.aclose()
                        model_key = f"{p_name}:{upstream_model}"
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        logger.warning(f"⚠️ [{p_name} | {upstream_model}] 连接建立后等待有效数据超时/挂死 ({peek_err})，开启 30s 冷却并秒级转移至下一候选...")
                        raise HTTPException(status_code=503, detail=f"[{p_name}] 连接建立后等待有效数据超时: {peek_err}")

                    if not has_substance:
                        await response.aclose()
                        await client.aclose()
                        model_key = f"{p_name}:{upstream_model}"
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        logger.warning(f"⚠️ [{p_name} | {upstream_model}] 连接已建立但在 {peek_timeout}s 内未产出任何实质内容或推理，判定假活挂死，开启 30s 冷却并秒级转移至下一候选...")
                        raise HTTPException(status_code=503, detail=f"[{p_name}] 连接建立但在 {peek_timeout}s 内无任何实质有效内容")

                    # 检查已探测的块是否包含上游超载或报错 (如 OpenRouter / NVIDIA 在 200 SSE 流中推送 error 载荷)
                    combined_peek = b"".join(peek_chunks).lower()
                    if (b'"error"' in combined_peek or b'"detail"' in combined_peek or b'overload' in combined_peek) and b'"choices"' not in combined_peek:
                        await response.aclose()
                        await client.aclose()
                        error_peek_str = b"".join(peek_chunks).decode("utf-8", errors="ignore")
                        logger.warning(f"⚠️ [{p_name} | {upstream_model}] 流式首包检测到服务超载/报错: {error_peek_str[:200]}，开启 60s 冷却并秒级转移至下一候选渠道！")
                        model_key = f"{p_name}:{upstream_model}"
                        state.model_cooldowns[model_key] = time.time() + 60.0
                        raise HTTPException(status_code=503, detail=f"[{p_name}] 流式首包超载: {error_peek_str[:200]}")

                    latency = int((time.time() - start_time) * 1000)
                    total_latency = int((time.time() - req_start_time) * 1000)
                    p_stat["success"] += 1
                    p_stat["last_latency_ms"] = latency
                    state.stats["success_requests"] += 1
                    state.stats["total_latency_sum"] = state.stats.get("total_latency_sum", 0) + latency
                    if tier_idx > 1:
                        state.stats["tier_fallback_events"] = state.stats.get("tier_fallback_events", 0) + 1
                    if eff_channel in state.stats:
                        state.stats[eff_channel]["success_requests"] += 1
                        state.stats[eff_channel]["total_latency_sum"] = state.stats[eff_channel].get("total_latency_sum", 0) + latency
                        if tier_idx > 1:
                            state.stats[eff_channel]["tier_fallback_events"] = state.stats[eff_channel].get("tier_fallback_events", 0) + 1

                    hit_key = f"{p_name} / {upstream_model}"
                    state.stats.setdefault("model_hits", {})
                    state.stats["model_hits"][hit_key] = state.stats["model_hits"].get(hit_key, 0) + 1
                    if eff_channel in state.stats:
                        state.stats[eff_channel].setdefault("model_hits", {})
                        state.stats[eff_channel]["model_hits"][hit_key] = state.stats[eff_channel]["model_hits"].get(hit_key, 0) + 1

                    logger.info(f"✨ [{tier_name}] -> 成功命中渠道商 [{p_name}] 的大模型 [{upstream_model}]！首包耗时: {latency}ms (总耗时: {total_latency}ms)")

                    attempts_trace.append({
                        "tier": f"L{tier_idx}",
                        "provider": p_name,
                        "model": upstream_model,
                        "status": "success",
                        "latency_ms": latency
                    })
                    log_entry = {
                        "time": req_time_str,
                        "channel": eff_channel,
                        "requested_model": requested_model,
                        "model": requested_model,
                        "final_provider": p_name,
                        "provider": p_name,
                        "final_model": upstream_model,
                        "upstream_model": upstream_model,
                        "status": "success" if total_retries == 0 else "failover_success",
                        "status_code": 200,
                        "latency_ms": total_latency,
                        "latency": total_latency,
                        "stream": True,
                        "method": "POST",
                        "path": "/v1/chat/completions" if eff_channel == "harness" else "/v1/responses",
                        "prompt_snippet": prompt_snippet,
                        "attempts": attempts_trace
                    }
                    state.add_log(log_entry, channel=eff_channel)

                    has_tools = bool(call_body.get("tools"))

                    async def combined_bytes_iter():
                        for c in peek_chunks:
                            yield c
                        async for c in stream_iter:
                            yield c

                    async def stream_generator():
                        last_chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                        native_tool_calls_seen = False
                        in_invoke_mode = False
                        invoke_buffer = ""
                        pending_tail = ""

                        def build_tool_calls_chunk(tcs, chunk_id):
                            return {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": requested_model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": i,
                                                "id": tc["id"],
                                                "type": "function",
                                                "function": tc["function"]
                                            }
                                            for i, tc in enumerate(tcs)
                                        ]
                                    },
                                    "finish_reason": None
                                }]
                            }

                        def build_finish_chunk(chunk_id, reason="tool_calls"):
                            return {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": requested_model,
                                "choices": [{"index": 0, "delta": {}, "finish_reason": reason}]
                            }

                        def build_content_chunk(chunk_id, text):
                            return {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": requested_model,
                                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]
                            }

                        try:
                            iter_obj = combined_bytes_iter()
                            if not has_tools:
                                idle_iter = aiter_with_idle(iter_obj, 5.0)
                                try:
                                    async for chunk in idle_iter:
                                        if chunk is STREAM_IDLE:
                                            yield b": keepalive\n\n"
                                        else:
                                            yield chunk
                                finally:
                                    await idle_iter.aclose()
                            else:
                                buffer = ""

                                async def process_sse_msg(msg_raw: str):
                                    nonlocal in_invoke_mode, invoke_buffer, native_tool_calls_seen, pending_tail, last_chunk_id
                                    lines = [l.strip() for l in msg_raw.split("\n") if l.strip()]
                                    data_lines = [l[5:].strip() for l in lines if l.startswith("data:")]
                                    if not data_lines:
                                        yield f"{msg_raw}\n\n".encode("utf-8")
                                        return

                                    data_content = "\n".join(data_lines)
                                    if data_content == "[DONE]":
                                        if in_invoke_mode and invoke_buffer:
                                            tool_calls = parse_xml_to_tool_calls(invoke_buffer)
                                            if tool_calls:
                                                logger.info(f"⚡ [Gateway-Rescue] 成功从长任务流式输出中提取并转换 {len(tool_calls)} 个 XML 工具调用为标准 OpenAI tool_calls: {[tc['function']['name'] for tc in tool_calls]}")
                                                yield f"data: {json.dumps(build_tool_calls_chunk(tool_calls, last_chunk_id))}\n\n".encode("utf-8")
                                                yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'tool_calls'))}\n\n".encode("utf-8")
                                            else:
                                                yield f"data: {json.dumps(build_content_chunk(last_chunk_id, invoke_buffer))}\n\n".encode("utf-8")
                                            invoke_buffer = ""
                                            in_invoke_mode = False
                                        elif pending_tail:
                                            yield f"data: {json.dumps(build_content_chunk(last_chunk_id, pending_tail))}\n\n".encode("utf-8")
                                            pending_tail = ""
                                        yield b"data: [DONE]\n\n"
                                        return

                                    try:
                                        chunk_json = json.loads(data_content)
                                    except Exception:
                                        yield f"data: {data_content}\n\n".encode("utf-8")
                                        return

                                    if "id" in chunk_json:
                                        last_chunk_id = chunk_json["id"]

                                    # 拦截上游在 SSE 块中推送的 error 载荷 (如 OpenRouter 报错 "Upstream error from Nvidia: Service temporarily overloaded")
                                    # 严禁将 error JSON 透传给下游，否则 pi-ai / OpenAI SDK 将直接抛出致命 PI_AI_ERROR 导致整个轮次中断
                                    if "error" in chunk_json or "detail" in chunk_json:
                                        err_msg = str(chunk_json.get("error") or chunk_json.get("detail"))
                                        logger.warning(f"⚠️ [SSE-Error-Intercept] 拦截到上游流中推送的错误载荷: {err_msg[:200]}，安全静默关闭，绝不向客户端抛出 PI_AI_ERROR")
                                        if in_invoke_mode and invoke_buffer:
                                            tool_calls = parse_xml_to_tool_calls(invoke_buffer)
                                            if tool_calls:
                                                yield f"data: {json.dumps(build_tool_calls_chunk(tool_calls, last_chunk_id))}\n\n".encode("utf-8")
                                                yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'tool_calls'))}\n\n".encode("utf-8")
                                            else:
                                                yield f"data: {json.dumps(build_content_chunk(last_chunk_id, invoke_buffer))}\n\n".encode("utf-8")
                                                yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'stop'))}\n\n".encode("utf-8")
                                            invoke_buffer = ""
                                            in_invoke_mode = False
                                        elif pending_tail:
                                            yield f"data: {json.dumps(build_content_chunk(last_chunk_id, pending_tail))}\n\n".encode("utf-8")
                                            yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'stop'))}\n\n".encode("utf-8")
                                            pending_tail = ""
                                        elif not native_tool_calls_seen:
                                            yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'stop'))}\n\n".encode("utf-8")
                                        yield b"data: [DONE]\n\n"
                                        return

                                    choices = chunk_json.get("choices", [])
                                    if not choices:
                                        return

                                    delta = choices[0].get("delta", {})
                                    finish_reason = choices[0].get("finish_reason")

                                    # 规范化异常或非标准 finish_reason (如 Google 返回的 "function_call_filter: MALFORMED_FUNCTION_CALL")
                                    # 避免下游 pi-ai / OpenAI SDK 将非标准 finish_reason 误判为致命 PI_AI_ERROR 导致整个轮次中断
                                    if finish_reason and finish_reason not in ["stop", "length", "tool_calls", "content_filter"]:
                                        if delta.get("tool_calls") or native_tool_calls_seen:
                                            choices[0]["finish_reason"] = "tool_calls"
                                        else:
                                            choices[0]["finish_reason"] = "stop"
                                        finish_reason = choices[0]["finish_reason"]

                                    if delta.get("tool_calls") or native_tool_calls_seen:
                                        native_tool_calls_seen = True
                                        yield f"data: {json.dumps(chunk_json)}\n\n".encode("utf-8")
                                        return

                                    if in_invoke_mode:
                                        content = delta.get("content", "")
                                        if content:
                                            invoke_buffer += content
                                        if finish_reason:
                                            tool_calls = parse_xml_to_tool_calls(invoke_buffer)
                                            if tool_calls:
                                                logger.info(f"⚡ [Gateway-Rescue] 成功从长任务流式输出中提取并转换 {len(tool_calls)} 个 XML 工具调用为标准 OpenAI tool_calls: {[tc['function']['name'] for tc in tool_calls]}")
                                                yield f"data: {json.dumps(build_tool_calls_chunk(tool_calls, last_chunk_id))}\n\n".encode("utf-8")
                                                yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'tool_calls'))}\n\n".encode("utf-8")
                                                invoke_buffer = ""
                                                in_invoke_mode = False
                                                return
                                            else:
                                                if invoke_buffer:
                                                    yield f"data: {json.dumps(build_content_chunk(last_chunk_id, invoke_buffer))}\n\n".encode("utf-8")
                                                    invoke_buffer = ""
                                                in_invoke_mode = False
                                                yield f"data: {json.dumps(chunk_json)}\n\n".encode("utf-8")
                                                return
                                        return

                                    if "content" in delta:
                                        content = delta["content"] or ""
                                        if pending_tail:
                                            content = pending_tail + content
                                            pending_tail = ""

                                        invoke_tag = None
                                        for tag in ("<invoke", "<function_call", "<tool_call", "[Tool Call:", "Previously executed tool"):
                                            if tag in content:
                                                invoke_tag = tag
                                                break

                                        if invoke_tag:
                                            in_invoke_mode = True
                                            parts = content.split(invoke_tag, 1)
                                            before_invoke = parts[0]
                                            invoke_buffer = invoke_tag + parts[1]
                                            if before_invoke:
                                                chunk_json["choices"][0]["delta"]["content"] = before_invoke
                                                yield f"data: {json.dumps(chunk_json)}\n\n".encode("utf-8")
                                            return

                                        if not finish_reason:
                                            has_prefix = False
                                            for pfx in sorted(INVOKE_PREFIXES, key=len, reverse=True):
                                                if content.endswith(pfx):
                                                    pending_tail = pfx
                                                    content = content[:-len(pfx)]
                                                    has_prefix = True
                                                    break
                                            if has_prefix:
                                                if content:
                                                    chunk_json["choices"][0]["delta"]["content"] = content
                                                    yield f"data: {json.dumps(chunk_json)}\n\n".encode("utf-8")
                                                return

                                        chunk_json["choices"][0]["delta"]["content"] = content
                                        yield f"data: {json.dumps(chunk_json)}\n\n".encode("utf-8")
                                    else:
                                        yield f"data: {json.dumps(chunk_json)}\n\n".encode("utf-8")

                                idle_iter = aiter_with_idle(iter_obj, 5.0)
                                try:
                                    async for chunk_bytes in idle_iter:
                                        if chunk_bytes is STREAM_IDLE:
                                            yield b": keepalive\n\n"
                                            continue

                                        buffer += chunk_bytes.decode("utf-8", errors="replace")
                                        while "\n\n" in buffer:
                                            msg_raw, buffer = buffer.split("\n\n", 1)
                                            msg_raw = msg_raw.strip()
                                            if msg_raw:
                                                async for out in process_sse_msg(msg_raw):
                                                    yield out
                                finally:
                                    await idle_iter.aclose()

                                if buffer.strip():
                                    async for out in process_sse_msg(buffer.strip()):
                                        yield out

                                if pending_tail:
                                    yield f"data: {json.dumps(build_content_chunk(last_chunk_id, pending_tail))}\n\n".encode("utf-8")
                                    pending_tail = ""

                                if in_invoke_mode and invoke_buffer:
                                    tool_calls = parse_xml_to_tool_calls(invoke_buffer)
                                    if tool_calls:
                                        logger.info(f"⚡ [Gateway-Rescue] 成功从流末尾提取并转换 {len(tool_calls)} 个 XML 工具调用为标准 OpenAI tool_calls: {[tc['function']['name'] for tc in tool_calls]}")
                                        yield f"data: {json.dumps(build_tool_calls_chunk(tool_calls, last_chunk_id))}\n\n".encode("utf-8")
                                        yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'tool_calls'))}\n\n".encode("utf-8")
                                    else:
                                        yield f"data: {json.dumps(build_content_chunk(last_chunk_id, invoke_buffer))}\n\n".encode("utf-8")
                                        yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'stop'))}\n\n".encode("utf-8")
                                    invoke_buffer = ""
                                    in_invoke_mode = False

                        except Exception as e:
                            logger.warning(f"Streaming chunk interrupted from [{p_name}]: {repr(e)}")
                            if pending_tail:
                                yield f"data: {json.dumps(build_content_chunk(last_chunk_id, pending_tail))}\n\n".encode("utf-8")
                                pending_tail = ""
                            if in_invoke_mode and invoke_buffer:
                                tool_calls = parse_xml_to_tool_calls(invoke_buffer)
                                if tool_calls:
                                    logger.info(f"⚡ [Gateway-Rescue] 异常中断时救援提取 {len(tool_calls)} 个工具调用")
                                    yield f"data: {json.dumps(build_tool_calls_chunk(tool_calls, last_chunk_id))}\n\n".encode("utf-8")
                                    yield f"data: {json.dumps(build_finish_chunk(last_chunk_id, 'tool_calls'))}\n\n".encode("utf-8")
                                else:
                                    yield f"data: {json.dumps(build_content_chunk(last_chunk_id, invoke_buffer))}\n\n".encode("utf-8")
                                    err_chunk = {
                                        "id": last_chunk_id,
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": requested_model,
                                        "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                                        "error": {
                                            "message": f"Stream interrupted from [{p_name}]: {repr(e)}",
                                            "type": "upstream_error",
                                            "code": "stream_interrupted"
                                        }
                                    }
                                    yield f"data: {json.dumps(err_chunk)}\n\n".encode("utf-8")
                                invoke_buffer = ""
                                in_invoke_mode = False
                            elif not native_tool_calls_seen:
                                err_chunk = {
                                    "id": last_chunk_id,
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": requested_model,
                                    "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                                    "error": {
                                        "message": f"Stream interrupted from [{p_name}]: {repr(e)}",
                                        "type": "upstream_error",
                                        "code": "stream_interrupted"
                                    }
                                }
                                yield f"data: {json.dumps(err_chunk)}\n\n".encode("utf-8")
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
                    has_tools = bool(call_body.get("tools"))
                    resp = await client.post(url, headers=headers, json=call_body)
                    latency = int((time.time() - start_time) * 1000)
                    total_latency = int((time.time() - req_start_time) * 1000)
                    p_stat["last_latency_ms"] = latency
                    await client.aclose()

                    model_key = f"{p_name}:{upstream_model}"

                    if resp.status_code in [429, 503, 529] or "overload" in resp.text.lower():
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        error_str = resp.text
                        logger.warning(f"⚠️ [{p_name} | {upstream_model}] 瞬时超载/限流 (HTTP {resp.status_code}): {error_str[:200]}，开启 30s 冷却并秒级转移至下一候选...")
                        raise HTTPException(status_code=resp.status_code, detail=f"[{p_name}] {error_str}")

                    if resp.status_code >= 400:
                        error_str = resp.text
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        logger.warning(f"❌ [{p_name} | {upstream_model}] HTTP {resp.status_code}: {error_str[:300]}")
                        raise HTTPException(status_code=resp.status_code, detail=f"[{p_name}] {error_str}")

                    res_json = resp.json()
                    if isinstance(res_json, dict) and ("error" in res_json or "detail" in res_json) and not res_json.get("choices"):
                        error_str = str(res_json.get("error") or res_json.get("detail"))
                        state.model_cooldowns[model_key] = time.time() + 30.0
                        logger.warning(f"❌ [{p_name} | {upstream_model}] 200 payload error: {error_str[:300]}")
                        raise HTTPException(status_code=502, detail=f"[{p_name}] {error_str}")

                    res_json["model"] = requested_model

                    if has_tools:
                        choices = res_json.get("choices", [])
                        if choices:
                            msg = choices[0].get("message", {})
                            content = msg.get("content", "")
                            if not msg.get("tool_calls") and any(k in (content or "") for k in ("<invoke", "<function_call", "<tool_call")):
                                cleaned_text, tool_calls = extract_and_convert_xml_tool_calls(content)
                                if tool_calls:
                                    logger.info(f"⚡ [Gateway-Rescue] (Non-stream) 成功将 XML 工具调用转换为 OpenAI tool_calls: {[tc['function']['name'] for tc in tool_calls]}")
                                    msg["content"] = cleaned_text or None
                                    msg["tool_calls"] = tool_calls
                                    choices[0]["finish_reason"] = "tool_calls"

                    p_stat["success"] += 1
                    state.stats["success_requests"] += 1
                    state.stats["total_latency_sum"] = state.stats.get("total_latency_sum", 0) + latency
                    if tier_idx > 1:
                        state.stats["tier_fallback_events"] = state.stats.get("tier_fallback_events", 0) + 1
                    if eff_channel in state.stats:
                        state.stats[eff_channel]["success_requests"] += 1
                        state.stats[eff_channel]["total_latency_sum"] = state.stats[eff_channel].get("total_latency_sum", 0) + latency
                        if tier_idx > 1:
                            state.stats[eff_channel]["tier_fallback_events"] = state.stats[eff_channel].get("tier_fallback_events", 0) + 1

                    hit_key = f"{p_name} / {upstream_model}"
                    state.stats.setdefault("model_hits", {})
                    state.stats["model_hits"][hit_key] = state.stats["model_hits"].get(hit_key, 0) + 1
                    if eff_channel in state.stats:
                        state.stats[eff_channel].setdefault("model_hits", {})
                        state.stats[eff_channel]["model_hits"][hit_key] = state.stats[eff_channel]["model_hits"].get(hit_key, 0) + 1

                    logger.info(f"✨ [{tier_name}] -> 成功命中渠道商 [{p_name}] 的大模型 [{upstream_model}]！耗时: {latency}ms")

                    attempts_trace.append({
                        "tier": f"L{tier_idx}",
                        "provider": p_name,
                        "model": upstream_model,
                        "status": "success",
                        "latency_ms": latency
                    })
                    log_entry = {
                        "time": req_time_str,
                        "channel": eff_channel,
                        "requested_model": requested_model,
                        "model": requested_model,
                        "final_provider": p_name,
                        "provider": p_name,
                        "final_model": upstream_model,
                        "upstream_model": upstream_model,
                        "status": "success" if total_retries == 0 else "failover_success",
                        "status_code": 200,
                        "latency_ms": total_latency,
                        "latency": total_latency,
                        "stream": False,
                        "method": "POST",
                        "path": "/v1/chat/completions" if eff_channel == "harness" else "/v1/responses",
                        "prompt_snippet": prompt_snippet,
                        "attempts": attempts_trace
                    }
                    state.add_log(log_entry, channel=eff_channel)

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
                # 无论发生何种异常（超时、网络断开、4xx、5xx），均对该故障模型设置 60s 冷却，防止后续轮次重复踩雷卡死
                model_key = f"{p_name}:{upstream_model}"
                state.model_cooldowns[model_key] = time.time() + 60.0

                if isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError)):
                    error_msg = f"Timeout after {latency}ms ({type(e).__name__})"
                    logger.warning(f"⏱️ [{p_name} | {upstream_model}] 响应超时 ({latency}ms)，拉入 60s 冷却并立即极速转移 (Failover) 至下一候选...")
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
                if eff_channel in state.stats:
                    state.stats[eff_channel]["failover_events"] += 1
                continue
        logger.warning(f"⚠️ 【渠道商天梯 Tier {tier_idx} - {tier_name}】内所有 {len(candidates)} 个候选模型均已尝试失败或处于冷却中，自动晋级切换至下一个渠道商...")

    total_latency = int((time.time() - req_start_time) * 1000)
    state.stats["failed_requests"] += 1
    if eff_channel in state.stats:
        state.stats[eff_channel]["failed_requests"] += 1
    
    log_entry = {
        "time": req_time_str,
        "channel": eff_channel,
        "requested_model": requested_model,
        "model": requested_model,
        "final_provider": "Exhausted",
        "provider": "Exhausted",
        "final_model": "None",
        "upstream_model": "None",
        "status": "failed",
        "status_code": 502,
        "latency_ms": total_latency,
        "latency": total_latency,
        "stream": is_stream,
        "method": "POST",
        "path": "/v1/chat/completions" if eff_channel == "harness" else "/v1/responses",
        "prompt_snippet": prompt_snippet,
        "attempts": attempts_trace
    }
    state.add_log(log_entry, channel=eff_channel)

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

# ==============================================================================
# 🌐 Chrome 驱动全网实时搜索引擎 (通过 Playwright CDP 调用 Chromium)
# ==============================================================================

# --- Chrome 浏览器实例管理 (全局复用，惰性初始化) ---
_chrome_browser = None
_chrome_lock = asyncio.Lock()

async def _get_chrome_browser():
    """获取或创建全局复用的 Headless Chromium 浏览器实例 (通过 Playwright CDP 驱动)"""
    global _chrome_browser
    if _chrome_browser is not None and _chrome_browser.is_connected():
        return _chrome_browser
    async with _chrome_lock:
        # Double-check after acquiring lock
        if _chrome_browser is not None and _chrome_browser.is_connected():
            return _chrome_browser
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            _chrome_browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--lang=zh-CN,zh,en-US,en",
                ]
            )
            logger.info("🌐 [Chrome] Headless Chromium 浏览器实例已通过 Playwright CDP 启动")
            return _chrome_browser
        except Exception as e:
            logger.warning(f"⚠️ [Chrome] Chromium 启动失败: {e}")
            return None


async def _chrome_google_search(query: str, max_results: int = 8) -> List[Dict[str, str]]:
    """通过 Headless Chrome 执行 Google 搜索并提取结构化结果"""
    browser = await _get_chrome_browser()
    if browser is None:
        return []

    results = []
    context = None
    try:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # 构造 Google 搜索 URL
        search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}&hl=zh-CN&num={max_results + 5}"
        logger.info(f"🌐 [Chrome] 正在通过 Headless Chromium 访问 Google 搜索: '{query}'...")

        await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        # 等待搜索结果容器出现
        try:
            await page.wait_for_selector("#search", timeout=8000)
        except Exception:
            # 可能遇到 consent 页面或 CAPTCHA，尝试点击同意按钮
            consent_btn = page.locator("button:has-text('全部接受'), button:has-text('Accept all'), button:has-text('I agree')")
            if await consent_btn.count() > 0:
                await consent_btn.first.click()
                await page.wait_for_selector("#search", timeout=8000)

        # 提取搜索结果 (在浏览器 JS 上下文中执行)
        raw_results = await page.evaluate("""() => {
            const items = [];
            // Google 搜索结果的标准选择器
            const resultEls = document.querySelectorAll('#search .g, #rso .g, div[data-hveid] .g');
            for (const el of resultEls) {
                const linkEl = el.querySelector('a[href^="http"]');
                const titleEl = el.querySelector('h3');
                // 摘要可能在多种容器中
                const snippetEl = el.querySelector('[data-sncf], .VwiC3b, .IsZvec, [style*="-webkit-line-clamp"]');
                const dateEl = el.querySelector('.LEwnzc, .f, span.MUxGbd');
                if (linkEl && titleEl) {
                    const url = linkEl.href;
                    // 过滤 Google 内部链接
                    if (url.includes('google.com/search') || url.includes('accounts.google')) continue;
                    items.push({
                        title: titleEl.innerText.trim(),
                        url: url,
                        snippet: snippetEl ? snippetEl.innerText.trim() : '',
                        publishedAt: dateEl ? dateEl.innerText.trim() : ''
                    });
                }
                if (items.length >= """ + str(max_results) + """) break;
            }
            return items;
        }""")

        for item in raw_results:
            pub = item.get("publishedAt", "")
            if not pub or len(pub) > 30:
                pub = time.strftime("%Y-%m-%d")
            results.append({
                "title": item["title"],
                "url": item["url"],
                "snippet": item.get("snippet", ""),
                "publishedAt": pub,
            })

        logger.info(f"✅ [Chrome] Google 搜索完成，成功提取 {len(results)} 条结果")

    except Exception as e:
        logger.warning(f"⚠️ [Chrome] Google 搜索异常: {e}")
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

    return results


async def _duckduckgo_fallback_search(query: str, max_results: int = 8) -> List[Dict[str, str]]:
    """DuckDuckGo HTML 兜底搜索 (当 Chrome 不可用或失败时)"""
    results = []
    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, data={"q": query})
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.select(".result"):
                    title_el = item.select_one(".result__title .result__a")
                    snippet_el = item.select_one(".result__snippet")
                    if not title_el:
                        continue
                    raw_url = title_el.get("href", "")
                    title = title_el.get_text(strip=True)
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    if "uddg=" in raw_url:
                        parsed = urllib.parse.urlparse(raw_url)
                        params = urllib.parse.parse_qs(parsed.query)
                        clean_url = params.get("uddg", [raw_url])[0]
                    elif raw_url.startswith("//"):
                        clean_url = "https:" + raw_url
                    else:
                        clean_url = raw_url
                    if clean_url and not clean_url.startswith("https://duckduckgo.com"):
                        results.append({
                            "title": title,
                            "url": clean_url,
                            "snippet": snippet,
                            "publishedAt": time.strftime("%Y-%m-%d")
                        })
                        if len(results) >= max_results:
                            break
    except Exception as e:
        logger.warning(f"⚠️ [WebSearch] DuckDuckGo 兜底检索异常: {e}")
    return results


async def execute_web_search(query: str, max_results: int = 8) -> List[Dict[str, str]]:
    """主搜索入口：Chrome Google 优先，DuckDuckGo 兜底"""
    query_clean = query.strip()
    if not query_clean:
        return []

    logger.info(f"🔍 [WebSearch] 正在为 DeepSeek-Harness 执行实时全网检索: '{query_clean}' (最大条数: {max_results})...")

    # 1. 首选：通过 Headless Chrome (Playwright CDP) 调用 Google 搜索
    results = await _chrome_google_search(query_clean, max_results)

    # 2. 兜底：如果 Chrome 失败或结果不足，使用 DuckDuckGo HTTP 抓取
    if len(results) < 3:
        logger.info(f"🔄 [WebSearch] Chrome 结果不足 ({len(results)} 条)，切换至 DuckDuckGo 兜底引擎...")
        ddg_results = await _duckduckgo_fallback_search(query_clean, max_results)
        # 合并去重
        seen_urls = {r["url"] for r in results}
        for r in ddg_results:
            if r["url"] not in seen_urls:
                results.append(r)
                seen_urls.add(r["url"])
                if len(results) >= max_results:
                    break

    logger.info(f"✅ [WebSearch] 检索完成，成功捕获 {len(results)} 条实时有效网页索引！")
    return results

@app.post("/anthropic/v1/messages")
@app.post("/messages")
@app.post("/v1/messages")
async def handle_anthropic_messages(request: Request):
    req_body = await request.json()
    model = req_body.get("model", "deepseek-v4-flash")
    messages = req_body.get("messages", [])
    tools = req_body.get("tools", [])

    # 检测是否为 DeepSeek-Harness 的 web_search 调用
    is_search = any(
        t.get("name") == "web_search" or t.get("type") == "web_search_20250305"
        for t in tools
    )

    prompt_text = ""
    for m in reversed(messages):
        content = m.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    prompt_text = part.get("text", "")
                    break
        elif isinstance(content, str):
            prompt_text = content
        if prompt_text:
            break

    if "Perform a web search for the query:" in prompt_text:
        is_search = True

    if is_search:
        query = prompt_text
        if "Perform a web search for the query:" in query:
            query = query.split("Perform a web search for the query:")[-1].strip()
        query = query.strip().strip("'\"")

        search_results = await execute_web_search(query, max_results=8)

        tool_results = []
        citations = []
        summary_lines = [f"Web search results for '{query}':\n"]

        for idx, item in enumerate(search_results, 1):
            url = item["url"]
            title = item["title"]
            snippet = item.get("snippet", "")
            page_age = item.get("publishedAt", time.strftime("%Y-%m-%d"))

            tool_results.append({
                "type": "web_search_result",
                "url": url,
                "title": title,
                "page_age": page_age
            })
            if snippet:
                citations.append({
                    "type": "web_search_citation",
                    "url": url,
                    "cited_text": snippet
                })
            summary_lines.append(f"{idx}. [{title}]({url})\n   {snippet}")

        if not search_results:
            summary_lines.append("No relevant results found for the query.")

        text_summary = "\n".join(summary_lines)
        text_summary += "\n\nCite the relevant URLs above as markdown links in your answer."

        anthropic_response = {
            "id": f"msg_{uuid.uuid4().hex[:16]}",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [
                {
                    "type": "web_search_tool_result",
                    "content": tool_results
                },
                {
                    "type": "text",
                    "text": text_summary,
                    "citations": citations
                }
            ],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": max(1, len(prompt_text) // 4),
                "output_tokens": max(1, len(text_summary) // 4)
            }
        }
        return JSONResponse(status_code=200, content=anthropic_response)

    # 普通 Anthropic 协议兼容：转换为 OpenAI completions
    return JSONResponse(status_code=200, content={
        "id": f"msg_{uuid.uuid4().hex[:16]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": "OK"}],
        "stop_reason": "end_turn"
    })

def extract_clean_patch(raw_args: str) -> str:
    """从原始模型参数中精准提取或还原 Codex 原生期望的 plaintext 裸补丁格式"""
    clean_patch = (raw_args or "").strip()
    if clean_patch.startswith("{") and clean_patch.endswith("}"):
        try:
            parsed_json = json.loads(clean_patch)
            for key in ["patch", "content", "diff", "input"]:
                if key in parsed_json and isinstance(parsed_json[key], str):
                    clean_patch = parsed_json[key]
                    break
        except Exception:
            pass
    if "*** Begin Patch" in clean_patch:
        start_idx = clean_patch.find("*** Begin Patch")
        end_idx = clean_patch.find("*** End Patch")
        if end_idx != -1:
            clean_patch = clean_patch[start_idx : end_idx + len("*** End Patch")]
        else:
            clean_patch = clean_patch[start_idx:]
    return clean_patch

# ==============================================================================
# 🤖 OpenAI Responses API 协议适配器 (/v1/responses)
# 专为 ChatGPT Codex CLI 及新一代 Agentic 工具设计，支持 instructions/input/tools
# 双模式流式 (SSE 语义事件流) 与非流式输出
# ==============================================================================
@app_codex.post("/v1/responses")
@app_codex.post("/responses")
@app_harness.post("/v1/responses")
@app_harness.post("/responses")
async def handle_openai_responses(request: Request):
    try:
        req_body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    model = req_body.get("model", "auto")
    instructions = req_body.get("instructions")
    raw_input = req_body.get("input", [])
    raw_tools = req_body.get("tools", [])
    
    accept_header = request.headers.get("accept", "")
    stream_param = req_body.get("stream")
    if stream_param is not None:
        is_stream = bool(stream_param)
    elif "text/event-stream" in accept_header:
        is_stream = True
    else:
        is_stream = True  # Responses API 默认流式 SSE

    logger.info(f"👉 [Codex / Responses API Request]: model={model}, is_stream={is_stream}, accept={accept_header}")
    logger.info(f"👉 [Codex Raw Tools]: {json.dumps(raw_tools, ensure_ascii=False)}")

    converted_messages = []
    if instructions and isinstance(instructions, str):
        converted_messages.append({"role": "system", "content": instructions})

    if raw_tools:
        action_rule = (
            "CRITICAL AGENT RULE: You are an autonomous coding agent running inside Codex. "
            "Whenever your next step involves inspecting, creating, modifying, or testing files or directories, "
            "you MUST invoke the appropriate tool (such as exec_command or apply_patch) immediately in the very same response. "
            "NEVER merely state your intention or say what you will do in text without issuing the tool call in that turn. "
            "When using apply_patch, you must provide the complete patch string starting with '*** Begin Patch\\n' and ending with '\\n*** End Patch'. "
            "You may also use exec_command to create or modify files using shell commands (e.g. cat << 'EOF' > file). Execute the tool call directly!"
        )
        if converted_messages and converted_messages[0].get("role") == "system":
            converted_messages[0]["content"] += f"\n\n{action_rule}"
        else:
            converted_messages.insert(0, {"role": "system", "content": action_rule})

    if isinstance(raw_input, str):
        converted_messages.append({"role": "user", "content": raw_input})
    elif isinstance(raw_input, list):
        for item in raw_input:
            if isinstance(item, str):
                converted_messages.append({"role": "user", "content": item})
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type in ("function_call", "custom_tool_call"):
                    call_id = item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    fn_name = item.get("name", "")
                    args = item.get("arguments") or item.get("input") or "{}"
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    elif isinstance(args, str):
                        args_str = args.strip()
                        if not (args_str.startswith("{") and args_str.endswith("}")):
                            args = json.dumps({"patch": args} if fn_name == "apply_patch" else {"input": args})
                    # 如果前一条消息也是 assistant，合并进同一次 assistant 调用的 tool_calls 列表（符合标准 OpenAI Chat 规范）
                    if converted_messages and converted_messages[-1].get("role") == "assistant":
                        if "tool_calls" not in converted_messages[-1]:
                            converted_messages[-1]["tool_calls"] = []
                        converted_messages[-1]["tool_calls"].append({
                            "id": call_id,
                            "type": "function",
                            "function": {"name": fn_name, "arguments": args}
                        })
                    else:
                        converted_messages.append({
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [{
                                "id": call_id,
                                "type": "function",
                                "function": {"name": fn_name, "arguments": args}
                            }]
                        })
                elif item_type in ("function_call_output", "custom_tool_call_output"):
                    call_id = item.get("call_id") or item.get("id") or "call_default"
                    output = item.get("output", "")
                    if isinstance(output, (dict, list)):
                        output = json.dumps(output)
                    converted_messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": str(output)
                    })
                elif item_type == "message" or "role" in item:
                    role = item.get("role", "user")
                    c = item.get("content", "")
                    if isinstance(c, list):
                        text_parts = []
                        for part in c:
                            if isinstance(part, dict) and part.get("type") in ("input_text", "text", "output_text", "reasoning", "thought"):
                                text_parts.append(part.get("text", "") or part.get("reasoning", ""))
                            elif isinstance(part, str):
                                text_parts.append(part)
                        c = "\n".join(text_parts) if text_parts else ""
                    converted_messages.append({"role": role, "content": c})
                else:
                    converted_messages.append({"role": "user", "content": json.dumps(item)})

    # 严格清洗 messages，移除 Codex 内部私有字段 (如 reasoning_details, encrypted_content 等)
    clean_messages = []
    for m in converted_messages:
        role = m.get("role", "user")
        clean_m = {"role": role}
        if "content" in m:
            clean_m["content"] = m["content"]
        if role == "assistant" and "tool_calls" in m:
            clean_m["tool_calls"] = m["tool_calls"]
            if clean_m.get("content") is None:
                clean_m["content"] = ""
        if role == "tool" and "tool_call_id" in m:
            clean_m["tool_call_id"] = m["tool_call_id"] or "call_default"
        clean_messages.append(clean_m)
    logger.info(f"👉 [Codex Converted Messages]: count={len(clean_messages)}, roles={[m.get('role') for m in clean_messages]}")

    converted_tools = []
    for t in raw_tools:
        if isinstance(t, dict):
            t_type = t.get("type")
            t_name = t.get("name") or (t.get("function", {}).get("name") if isinstance(t.get("function"), dict) else "")

            # 针对 Codex 特有的 apply_patch 工具：为其注入标准 JSON Schema，杜绝大模型输出 {} 空参数
            if t_name == "apply_patch":
                converted_tools.append({
                    "type": "function",
                    "function": {
                        "name": "apply_patch",
                        "description": (
                            "Use the apply_patch tool to edit files. Your patch language is a stripped-down, file-oriented diff format. "
                            "You must provide the entire patch starting with '*** Begin Patch\\n' and ending with '\\n*** End Patch'."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "patch": {
                                    "type": "string",
                                    "description": "The complete patch content enclosed between '*** Begin Patch\\n' and '\\n*** End Patch'."
                                }
                            },
                            "required": ["patch"]
                        }
                    }
                })
            elif t_type == "function":
                if "function" in t:
                    converted_tools.append(t)
                elif "name" in t:
                    converted_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.get("name"),
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {})
                        }
                    })
            elif t.get("name"):
                # 兼容 Codex 内部的非 function 专属工具定义，规范化为标准 OpenAI Function
                converted_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.get("name"),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters") or t.get("inputSchema", {})
                    }
                })

    chat_payload = {
        "model": model,
        "messages": clean_messages,
        "stream": is_stream
    }
    if converted_tools:
        chat_payload["tools"] = converted_tools
    if "temperature" in req_body:
        chat_payload["temperature"] = req_body["temperature"]

    auth_header = request.headers.get("Authorization", "Bearer sk-free-token")
    headers = {"Authorization": auth_header, "Content-Type": "application/json", "X-Channel": "codex"}

    # 1. 非流式处理 (stream: false)
    if not is_stream:
        transport = httpx.ASGITransport(app=app_codex)
        async with httpx.AsyncClient(transport=transport, base_url="http://internal", timeout=600.0) as client:
            res = await client.post("/v1/chat/completions", json=chat_payload, headers=headers)
        if res.status_code != 200:
            return JSONResponse(status_code=res.status_code, content=res.json())

        chat_data = res.json()
        resp_id = f"resp_{uuid.uuid4().hex[:16]}"
        choice = chat_data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content_text = message.get("content")
        reasoning_text = message.get("reasoning_content")
        if not content_text and reasoning_text:
            content_text = reasoning_text
        elif content_text and reasoning_text:
            content_text = f"{reasoning_text}\n\n{content_text}"
        tool_calls = message.get("tool_calls", [])

        output_items = []
        if content_text:
            output_items.append({
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": content_text
                    }
                ]
            })

        for tc in tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            fn_args = fn.get("arguments", "{}")
            if fn_name == "apply_patch":
                state.stats["codex"]["tool_calls"]["apply_patch"] += 1
            elif fn_name == "exec_command":
                state.stats["codex"]["tool_calls"]["exec_command"] += 1
            else:
                state.stats["codex"]["tool_calls"]["other"] += 1
            if fn_name == "apply_patch":
                clean_patch = extract_clean_patch(fn_args)
                output_items.append({
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:16]}",
                    "type": "custom_tool_call",
                    "call_id": tc.get("id") or f"call_{uuid.uuid4().hex[:16]}",
                    "name": fn_name,
                    "input": clean_patch
                })
            else:
                output_items.append({
                    "id": tc.get("id") or f"call_{uuid.uuid4().hex[:16]}",
                    "type": "function_call",
                    "call_id": tc.get("id") or f"call_{uuid.uuid4().hex[:16]}",
                    "name": fn_name,
                    "arguments": fn_args
                })

        final_provider = res.headers.get("X-Gateway-Provider", "Upstream")
        final_model = res.headers.get("X-Gateway-Model", chat_data.get("model", model))
        logger.info(f"✨ [Responses API] 成功完成响应！客户端模型: [{model}] -> 命中渠道商 [{final_provider}] 的具体大模型 [{final_model}]")

        responses_data = {
            "id": resp_id,
            "object": "response",
            "created_at": int(time.time()),
            "model": final_model,
            "status": "completed",
            "output": output_items,
            "usage": chat_data.get("usage", {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            })
        }
        res_headers = {
            "X-Gateway-Provider": final_provider,
            "X-Gateway-Model": final_model
        }
        return JSONResponse(status_code=200, content=responses_data, headers=res_headers)

    # 2. 流式处理 (stream: true) -> 转换为 Responses API SSE 规范事件流
    async def stream_responses_generator():
        resp_id = f"resp_{uuid.uuid4().hex[:16]}"
        created_at = int(time.time())
        output_index = 0
        next_output_index = 0
        msg_started = False
        msg_id = f"msg_{uuid.uuid4().hex[:16]}"
        accumulated_text = []
        tool_calls_map = {}
        final_model = model

        # 立即发射 response.created，0ms 握手防客户端超时
        created_event = {
            "type": "response.created",
            "response": {
                "id": resp_id,
                "object": "response",
                "status": "in_progress",
                "model": model,
                "created_at": created_at
            }
        }
        yield f"event: response.created\ndata: {json.dumps(created_event)}\n\n"

        transport = httpx.ASGITransport(app=app_codex)
        internal_client = httpx.AsyncClient(transport=transport, base_url="http://internal", timeout=600.0)

        # 候选重试链：优先请求模型，若因上游挂起断流未产出任何有效内容，则通过同一 SSE 连接秒级无缝接力备用旗舰
        candidate_models = [model]
        for fb in ["z-ai/glm-5.3", "moonshotai/kimi-k3", "nvidia/nemotron-3.5-lightning-30b-a3b"]:
            if fb not in candidate_models:
                candidate_models.append(fb)

        upstream_res = None
        line_iter = None
        upstream_provider = "Upstream"
        stream_interrupted = False
        stream_err_msg = ""
        try:
            for try_idx, curr_model in enumerate(candidate_models):
                curr_payload = dict(chat_payload)
                curr_payload["model"] = curr_model
                req = internal_client.build_request("POST", "/v1/chat/completions", json=curr_payload, headers=headers)
                pending_leading_ws = ""
                stream_interrupted = False
                stream_err_msg = ""
                try:
                    send_task = asyncio.create_task(internal_client.send(req, stream=True))
                    while not send_task.done():
                        try:
                            await asyncio.wait_for(asyncio.shield(send_task), timeout=1.2)
                        except asyncio.TimeoutError:
                            yield ": keepalive\n\n"
                    upstream_res = await send_task
                    if upstream_res.status_code != 200:
                        err_content = await upstream_res.aread()
                        err_str = err_content.decode("utf-8", errors="ignore")
                        logger.warning(f"⚠️ [Responses API Streaming] 内部模型 [{curr_model}] 返回 HTTP {upstream_res.status_code}: {err_str[:200]}，尝试下一候选...")
                        await upstream_res.aclose()
                        upstream_res = None
                        continue

                    upstream_provider = upstream_res.headers.get("X-Gateway-Provider", upstream_provider)
                    line_iter = aiter_with_idle(upstream_res.aiter_lines(), 5.0)
                    idle_ticks = 0
                    while True:
                        try:
                            line = await line_iter.__anext__()
                        except StopAsyncIteration:
                            break

                        if line is STREAM_IDLE:
                            idle_ticks += 1
                            # SSE 注释只能保活中间代理，无法重置 Codex 客户端自身的流空闲计时，
                            # 因此每约 20s 再补发一个真实的 response.in_progress 生命周期事件
                            yield ": keepalive\n\n"
                            if idle_ticks % 4 == 0:
                                in_progress_event = {
                                    "type": "response.in_progress",
                                    "response": {
                                        "id": resp_id,
                                        "object": "response",
                                        "status": "in_progress",
                                        "model": final_model,
                                        "created_at": created_at
                                    }
                                }
                                yield f"event: response.in_progress\ndata: {json.dumps(in_progress_event)}\n\n"
                            continue
                        idle_ticks = 0

                        line_str = line.strip()
                        if not line_str or line_str.startswith(":"):
                            continue
                        if line_str == "data: [DONE]":
                            break
                        if not line_str.startswith("data: "):
                            continue

                        chunk_payload = line_str[6:].strip()
                        try:
                            chunk_obj = json.loads(chunk_payload)
                        except Exception:
                            continue

                        if "model" in chunk_obj:
                            final_model = chunk_obj["model"]

                        choices = chunk_obj.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})

                        # 文本增量推流 (兼容 content 与 reasoning_content)
                        raw_content = delta.get("content") or ""
                        raw_reasoning = delta.get("reasoning_content") or ""
                        text_chunk = (raw_reasoning + raw_content) if (raw_content and raw_reasoning) else (raw_content or raw_reasoning)
                        if text_chunk:
                            if not msg_started:
                                pending_leading_ws += text_chunk
                                if not pending_leading_ws.strip():
                                    continue
                                msg_started = True
                                output_index = next_output_index
                                next_output_index += 1
                                item_added = {
                                    "type": "response.output_item.added",
                                    "output_index": output_index,
                                    "item": {
                                        "id": msg_id,
                                        "type": "message",
                                        "status": "in_progress",
                                        "role": "assistant",
                                        "content": []
                                    }
                                }
                                yield f"event: response.output_item.added\ndata: {json.dumps(item_added)}\n\n"
                                part_added = {
                                    "type": "response.content_part.added",
                                    "output_index": output_index,
                                    "content_index": 0,
                                    "part": {"type": "output_text", "text": ""}
                                }
                                yield f"event: response.content_part.added\ndata: {json.dumps(part_added)}\n\n"
                                text_chunk = pending_leading_ws
                                pending_leading_ws = ""

                            accumulated_text.append(text_chunk)
                            delta_event = {
                                "type": "response.output_text.delta",
                                "output_index": output_index,
                                "content_index": 0,
                                "delta": text_chunk
                            }
                            yield f"event: response.output_text.delta\ndata: {json.dumps(delta_event)}\n\n"

                        # 工具调用增量推流
                        tool_deltas = delta.get("tool_calls")
                        if tool_deltas and isinstance(tool_deltas, list):
                            for td in tool_deltas:
                                t_idx = td.get("index", 0)
                                t_id = td.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                                fn = td.get("function", {})
                                fn_name = fn.get("name", "")
                                fn_args = fn.get("arguments", "")

                                if t_idx not in tool_calls_map:
                                    tool_out_idx = next_output_index
                                    next_output_index += 1
                                    is_custom = (fn_name == "apply_patch")
                                    tool_calls_map[t_idx] = {
                                        "output_idx": tool_out_idx,
                                        "id": t_id,
                                        "name": fn_name,
                                        "is_custom": is_custom,
                                        "args": []
                                    }
                                    if is_custom:
                                        item_added = {
                                            "type": "response.output_item.added",
                                            "output_index": tool_out_idx,
                                            "item": {
                                                "id": t_id,
                                                "type": "custom_tool_call",
                                                "call_id": t_id,
                                                "name": fn_name,
                                                "input": ""
                                            }
                                        }
                                    else:
                                        item_added = {
                                            "type": "response.output_item.added",
                                            "output_index": tool_out_idx,
                                            "item": {
                                                "id": t_id,
                                                "type": "function_call",
                                                "call_id": t_id,
                                                "name": fn_name,
                                                "arguments": ""
                                            }
                                        }
                                    yield f"event: response.output_item.added\ndata: {json.dumps(item_added)}\n\n"

                                entry = tool_calls_map[t_idx]
                                if fn_name and not entry["name"]:
                                    entry["name"] = fn_name
                                if fn_args:
                                    entry["args"].append(fn_args)
                                    # 针对 apply_patch：由于三方模型会输出 JSON 如 {"patch": "..."}，
                                    # 而 Codex 官方 router 要求 arguments 为纯文本 plaintext 裸补丁格式，
                                    # 不能将 JSON 符号 `{"patch": "` 逐字透传给 Codex，
                                    # 否则 Codex router 接收到非 patch 字符会报 incompatible payload！
                                    if entry["name"] != "apply_patch":
                                        arg_event = {
                                            "type": "response.function_call_arguments.delta",
                                            "output_index": entry["output_idx"],
                                            "call_id": entry["id"],
                                            "delta": fn_args
                                        }
                                        yield f"event: response.function_call_arguments.delta\ndata: {json.dumps(arg_event)}\n\n"

                    # 若当前模型已成功产出实质文本或工具调用，判定流式响应成功并结束候选重试
                    valid_text = "".join(accumulated_text).strip()
                    if valid_text or tool_calls_map:
                        logger.info(f"✅ [Responses API Streaming] 模型 [{curr_model}] 成功产出实质响应 (文本: {len(valid_text)} 字符, 工具: {len(tool_calls_map)} 个)")
                        break
                    else:
                        logger.warning(f"⚠️ [Responses API Streaming] 模型 [{curr_model}] 未产出任何实质内容或工具调用，秒级转移至下一模型...")
                        msg_started = False
                        accumulated_text = []
                        tool_calls_map = {}
                        next_output_index = 0
                except Exception as loop_err:
                    logger.warning(f"⚠️ [Responses API Streaming] 尝试模型 [{curr_model}] 异常: {repr(loop_err)}")
                    stream_interrupted = True
                    stream_err_msg = str(loop_err)
                    if msg_started or tool_calls_map:
                        # 已向客户端推送过部分事件，换模型重来会产生重复 / 错乱的 output_index，
                        # 只能如实上报 response.failed 让 Codex 客户端自行重试整轮
                        break
                    # 尚未推送任何事件，清空状态后继续下一个候选
                    msg_started = False
                    accumulated_text = []
                    tool_calls_map = {}
                    next_output_index = 0
                finally:
                    if line_iter is not None:
                        try:
                            await line_iter.aclose()
                        except Exception:
                            pass
                        line_iter = None
                    if upstream_res:
                        try:
                            await upstream_res.aclose()
                        except Exception:
                            pass
                        upstream_res = None

            # 若在流式推送中途（已发送部分文本或工具调用后）遭遇底层网络或 upstream 异常断开，严禁误报 completed，必须按规范发射 response.failed
            if stream_interrupted and (msg_started or tool_calls_map):
                logger.error(f"❌ [Responses API Streaming] 模型在流式生成中途异常中断，发射 response.failed 事件通知客户端")
                failed_event = {
                    "type": "response.failed",
                    "response": {
                        "id": resp_id,
                        "object": "response",
                        "status": "failed",
                        "model": final_model,
                        "created_at": created_at,
                        "error": {
                            "type": "server_error",
                            "code": "stream_interrupted",
                            "message": f"Upstream stream interrupted mid-flight: {stream_err_msg}"
                        }
                    }
                }
                yield f"event: response.failed\ndata: {json.dumps(failed_event)}\n\n"
                return

            # 所有候选均未产出任何内容：必须如实发射 response.failed，让 Codex 自行重试本轮。
            # 绝不能补发一条伪造的 assistant 文本 —— Codex 会把“有文本、无工具调用”判定为本轮
            # 正常收尾，从而直接静默终止整个任务（表现为“执行一段就停止”）。
            if not msg_started and not tool_calls_map:
                logger.error("❌ [Responses API Streaming] 所有候选模型均未产出任何内容，发射 response.failed 让客户端重试本轮")
                empty_failed_event = {
                    "type": "response.failed",
                    "response": {
                        "id": resp_id,
                        "object": "response",
                        "status": "failed",
                        "model": final_model,
                        "created_at": created_at,
                        "error": {
                            "type": "server_error",
                            "code": "empty_upstream_response",
                            "message": "All upstream candidates returned an empty stream, please retry."
                        }
                    }
                }
                yield f"event: response.failed\ndata: {json.dumps(empty_failed_event)}\n\n"
                return

            # 文本结束事件
            if msg_started:
                full_text = "".join(accumulated_text)
                text_done = {
                    "type": "response.output_text.done",
                    "output_index": output_index,
                    "content_index": 0,
                    "text": full_text
                }
                yield f"event: response.output_text.done\ndata: {json.dumps(text_done)}\n\n"
                part_done = {
                    "type": "response.content_part.done",
                    "output_index": output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": full_text}
                }
                yield f"event: response.content_part.done\ndata: {json.dumps(part_done)}\n\n"
                item_done = {
                    "type": "response.output_item.done",
                    "output_index": output_index,
                    "item": {
                        "id": msg_id,
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": full_text}]
                    }
                }
                yield f"event: response.output_item.done\ndata: {json.dumps(item_done)}\n\n"

            # 工具调用结束事件
            for t_idx, entry in tool_calls_map.items():
                full_args = "".join(entry["args"])
                if entry.get("is_custom") or entry["name"] == "apply_patch":
                    # 智能解包 apply_patch 参数：
                    # 若模型输出了 JSON 格式 {"patch": "...", ...} 或 {"content": "..."}，
                    # 提取其中的 patch 纯文本，转换为 Codex 原生期望的 custom_tool_call (input: 纯文本裸补丁)
                    try:
                        clean_patch = extract_clean_patch(full_args)
                    except Exception as ex:
                        logger.warning(f"⚠️ [Codex] extract_clean_patch error: {ex}")
                        clean_patch = full_args
                    entry["final_args"] = clean_patch
                    item_done = {
                        "type": "response.output_item.done",
                        "output_index": entry["output_idx"],
                        "item": {
                            "id": entry["id"],
                            "type": "custom_tool_call",
                            "call_id": entry["id"],
                            "name": entry["name"],
                            "input": clean_patch
                        }
                    }
                    yield f"event: response.output_item.done\ndata: {json.dumps(item_done)}\n\n"
                else:
                    entry["final_args"] = full_args
                    arg_done = {
                        "type": "response.function_call_arguments.done",
                        "output_index": entry["output_idx"],
                        "call_id": entry["id"],
                        "arguments": full_args
                    }
                    yield f"event: response.function_call_arguments.done\ndata: {json.dumps(arg_done)}\n\n"
                    item_done = {
                        "type": "response.output_item.done",
                        "output_index": entry["output_idx"],
                        "item": {
                            "id": entry["id"],
                            "type": "function_call",
                            "call_id": entry["id"],
                            "name": entry["name"],
                            "arguments": full_args
                        }
                    }
                    yield f"event: response.output_item.done\ndata: {json.dumps(item_done)}\n\n"

            # response.completed 终结事件 (规范不带 data: [DONE])
            final_outputs = []
            full_text = "".join(accumulated_text)
            if msg_started and full_text.strip():
                final_outputs.append({
                    "id": msg_id,
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": full_text}]
                })
            for t_idx, entry in tool_calls_map.items():
                fn_name = entry.get("name")
                if fn_name == "apply_patch":
                    state.stats["codex"]["tool_calls"]["apply_patch"] += 1
                elif fn_name == "exec_command":
                    state.stats["codex"]["tool_calls"]["exec_command"] += 1
                else:
                    state.stats["codex"]["tool_calls"]["other"] += 1

                if entry.get("is_custom") or entry["name"] == "apply_patch":
                    final_outputs.append({
                        "id": entry["id"],
                        "type": "custom_tool_call",
                        "call_id": entry["id"],
                        "name": entry["name"],
                        "input": entry.get("final_args", extract_clean_patch("".join(entry["args"])))
                    })
                else:
                    final_outputs.append({
                        "id": entry["id"],
                        "type": "function_call",
                        "call_id": entry["id"],
                        "name": entry["name"],
                        "arguments": entry.get("final_args", "".join(entry["args"]))
                    })

            total_comp_tokens = max(1, len("".join(accumulated_text)) // 4)
            state.stats["codex"]["tokens"] += 15 + total_comp_tokens
            final_provider = upstream_provider
            logger.info(f"✨ [Responses API Streaming] 成功完成流式响应！客户端模型: [{model}] -> 命中渠道商 [{final_provider}] 的具体大模型 [{final_model}] (输出文本: {len(''.join(accumulated_text))} 字符, 工具调用: {len(tool_calls_map)} 个)")
            completed_event = {
                "type": "response.completed",
                "response": {
                    "id": resp_id,
                    "object": "response",
                    "status": "completed",
                    "model": final_model,
                    "output": final_outputs,
                    "usage": {
                        "input_tokens": 15,
                        "output_tokens": total_comp_tokens,
                        "total_tokens": 15 + total_comp_tokens
                    }
                }
            }
            yield f"event: response.completed\ndata: {json.dumps(completed_event)}\n\n"
        finally:
            if upstream_res:
                await upstream_res.aclose()
            await internal_client.aclose()

    return StreamingResponse(stream_responses_generator(), media_type="text/event-stream")

@app.get("/v1/search")
@app.post("/v1/search")
async def direct_web_search(request: Request, q: Optional[str] = None):
    query = q
    if not query:
        try:
            body = await request.json()
            query = body.get("query") or body.get("q")
        except:
            pass
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter 'q' or JSON field 'query' is required")
    results = await execute_web_search(query)
# ==============================================================================
# 🎨 官方 Google Imagen 3 图像生成引擎与 OpenAI 图像协议适配 (/v1/images/generations)
# 原生 100% 零水印，官方直出高质量摄影与艺术图像 (支持 1:1, 16:9, 9:16, 4:3, 3:4)
# ==============================================================================
def get_google_api_key(explicit_key: Optional[str] = None) -> Optional[str]:
    """获取可用的 Google API Key (请求头参数 > 环境变量 > 配置渠道)"""
    if explicit_key and not explicit_key.startswith("YOUR_"):
        return explicit_key.strip()
    for env_var in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_STUDIO_KEY"]:
        val = os.environ.get(env_var, "").strip()
        if val and not val.startswith("YOUR_"):
            return val
    for p in state.config.get("providers", []):
        p_name = p.get("name", "").lower()
        if "google" in p_name:
            key = (p.get("api_key") or "").strip()
            if key and not key.startswith("YOUR_"):
                return key
    return None

def get_imagen_aspect_ratio(width: int, height: int) -> str:
    """根据宽高映射为 Google Imagen 3 支持的标准宽高比 (1:1, 16:9, 9:16, 4:3, 3:4)"""
    if width == height:
        return "1:1"
    ratio = width / height
    if ratio > 1.0:
        return "16:9" if ratio >= 1.5 else "4:3"
    else:
        inv_ratio = height / width
        return "9:16" if inv_ratio >= 1.5 else "3:4"

async def generate_with_google_imagen(
    prompt: str,
    aspect_ratio: str = "1:1",
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> Optional[bytes]:
    """通过 Google AI Studio 官方 Imagen 3 扩散模型生成图像 (原生 100% 零水印)"""
    key = get_google_api_key(api_key)
    if not key:
        logger.error("❌ [ImageGen/Imagen3] 未检测到有效的 Google API Key，无法调用 Google Imagen 3 引擎")
        return None

    # 获取 Google AI Studio 自定义 Base URL (若存在代理或测试服务器)
    base_endpoint = "https://generativelanguage.googleapis.com"
    for p in state.config.get("providers", []):
        if "google" in p.get("name", "").lower():
            p_base = (p.get("base_url") or "").rstrip("/")
            if p_base and "generativelanguage.googleapis.com" not in p_base:
                base_endpoint = p_base
                break

    models_to_try = [
        "imagen-3.0-generate-002",
        "imagen-3.0-fast-generate-001"
    ]
    if model:
        m_clean = model.strip().lower()
        if "fast" in m_clean:
            models_to_try = ["imagen-3.0-fast-generate-001", "imagen-3.0-generate-002"]
        elif "imagen-3.0-generate-002" in m_clean:
            models_to_try = ["imagen-3.0-generate-002", "imagen-3.0-fast-generate-001"]
    
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": key
    }
    payload = {
        "instances": [
            {"prompt": prompt}
        ],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": aspect_ratio,
            "personGeneration": "ALLOW_ADULT",
            "outputMimeType": "image/jpeg"
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for m_id in models_to_try:
            url = f"{base_endpoint}/v1beta/models/{m_id}:predict"
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    preds = data.get("predictions", [])
                    if preds and "bytesBase64Encoded" in preds[0]:
                        logger.info(f"✨ [ImageGen/Imagen3] 成功使用 Google Imagen 3 ({m_id}) 生成高清零水印图像！")
                        return base64.b64decode(preds[0]["bytesBase64Encoded"])
                logger.warning(f"⚠️ [ImageGen/Imagen3] {m_id} 响应状态码: {resp.status_code}, 内容: {resp.text[:150]}")
            except Exception as e:
                logger.warning(f"⚠️ [ImageGen/Imagen3] 网络调用异常 ({m_id}): {e}")
    return None

async def execute_image_generation(
    prompt: str,
    size: str = "1024x1024",
    model: str = "imagen-3",
    n: int = 1,
    response_format: str = "url",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    prompt_clean = prompt.strip()
    if not prompt_clean:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    width, height = 1024, 1024
    if size and "x" in size:
        try:
            parts = size.lower().split("x")
            width, height = int(parts[0]), int(parts[1])
            width = max(256, min(2048, width))
            height = max(256, min(2048, height))
        except Exception:
            width, height = 1024, 1024

    aspect_ratio = get_imagen_aspect_ratio(width, height)
    target_model = (model or "imagen-3").strip().lower()
    if target_model in ["auto", "flux", "turbo", "sdxl", "default"]:
        target_model = "imagen-3"

    logger.info(f"🎨 [ImageGen] 正在通过 Google Imagen 3 生成图像: '{prompt_clean[:60]}...' (尺寸: {width}x{height}, 比例: {aspect_ratio}, 模型: {target_model}, 数量: {n})")

    data_items = []
    max_count = max(1, min(4, int(n or 1)))

    for i in range(max_count):
        img_bytes = await generate_with_google_imagen(
            prompt_clean,
            aspect_ratio=aspect_ratio,
            api_key=api_key,
            model=target_model
        )

        if not img_bytes:
            raise HTTPException(
                status_code=502,
                detail="Google Imagen 3 图像生成失败。请检查 Google AI Studio API Key 是否已正确配置并有效。"
            )

        file_id = f"img_{uuid.uuid4().hex[:12]}.jpg"
        file_path = os.path.join(GENERATED_IMAGES_DIR, file_id)
        with open(file_path, "wb") as f:
            f.write(img_bytes)

        local_url = f"/generated_images/{file_id}"

        item = {
            "revised_prompt": prompt_clean,
            "engine": "google-imagen-3"
        }
        if response_format == "b64_json":
            item["b64_json"] = base64.b64encode(img_bytes).decode("utf-8")
        else:
            item["url"] = local_url

        data_items.append(item)

    return {
        "created": int(time.time()),
        "data": data_items
    }

@app.get("/generated_images/{filename}")
async def get_generated_image(filename: str):
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(GENERATED_IMAGES_DIR, safe_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(file_path, media_type="image/jpeg")

@app.post("/v1/images/generations")
@app.post("/images/generations")
async def create_image_generation(request: Request):
    try:
        req_body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    prompt = req_body.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing required parameter 'prompt'")

    size = req_body.get("size", "1024x1024")
    model = req_body.get("model", "imagen-3")
    n = req_body.get("n", 1)
    response_format = req_body.get("response_format", "url")

    # 提取请求头可能附带的 Google / 自定义 API Key
    custom_key = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "").strip()
        if token and not token.startswith("sk-free-"):
            custom_key = token
    if not custom_key:
        custom_key = request.headers.get("x-goog-api-key") or request.headers.get("x-api-key")

    result = await execute_image_generation(
        prompt=prompt,
        size=size,
        model=model,
        n=n,
        response_format=response_format,
        api_key=custom_key
    )

    base_url_str = str(request.base_url).rstrip("/")
    for item in result.get("data", []):
        if "url" in item and item["url"].startswith("/"):
            item["url"] = f"{base_url_str}{item['url']}"

    return JSONResponse(status_code=200, content=result)

@app_harness.get("/v1/status")
async def get_status_harness():
    return {
        "status": "healthy",
        "service": "deepseek-harness",
        "port": state.harness_config.get("server", {}).get("port", 8000),
        "timestamp": int(time.time()),
        "stats": state.stats.get("harness", {}),
        "global_stats": state.stats,
        "config_providers": len(state.harness_config.get("providers", [])),
        "recent_logs_count": len(state.request_logs)
    }

@app_codex.get("/v1/status")
async def get_status_codex():
    return {
        "status": "healthy",
        "service": "codex-cli",
        "port": state.codex_config.get("server", {}).get("port", 8001),
        "timestamp": int(time.time()),
        "stats": state.stats.get("codex", {}),
        "global_stats": state.stats,
        "config_providers": len(state.codex_config.get("providers", [])),
        "recent_logs_count": len([l for l in state.request_logs if l.get("channel") == "codex"])
    }

async def run_servers():
    import uvicorn
    host_h = state.harness_config.get("server", {}).get("host", "127.0.0.1")
    port_h = int(state.harness_config.get("server", {}).get("port", 8000))

    host_c = state.codex_config.get("server", {}).get("host", "127.0.0.1")
    port_c = int(state.codex_config.get("server", {}).get("port", 8001))

    cfg_h = uvicorn.Config(app_harness, host=host_h, port=port_h, log_level="warning", timeout_keep_alive=120)
    cfg_c = uvicorn.Config(app_codex, host=host_c, port=port_c, log_level="warning", timeout_keep_alive=120)

    server_h = uvicorn.Server(cfg_h)
    server_c = uvicorn.Server(cfg_c)

    logger.info("=" * 70)
    logger.info("🚀 [Free Token Gateway] 双轨分离服务已并发就绪：")
    logger.info(f"   👉 DeepSeek Harness & Web 控制台 : http://{host_h}:{port_h}")
    logger.info(f"   👉 ChatGPT Codex CLI 专用服务    : http://{host_c}:{port_c}")
    logger.info("=" * 70)

    await asyncio.gather(
        server_h.serve(),
        server_c.serve()
    )

if __name__ == "__main__":
    try:
        asyncio.run(run_servers())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Gateway servers gracefully stopped.")
