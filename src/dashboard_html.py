# -*- coding: utf-8 -*-
"""
Linear Dashboard HTML Generator
提供一站式 Linear 风格双 Tab 单页控制台：
1. DeepSeek Harness 专区 (Port 8000, config.harness.yaml, 独立渠道商)
2. ChatGPT Codex CLI 专区 (Port 8001, config.codex.yaml, 独立渠道商)
"""

def get_dashboard_html(harness_providers_json: str, codex_providers_json: str, harness_port: int = 8000, codex_port: int = 8001) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Linear Gateway · Free Token 聚合调度控制台</title>
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
            padding: 24px 24px 80px;
            letter-spacing: -0.012em;
            -webkit-font-smoothing: antialiased;
        }}

        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: rgba(255, 255, 255, 0.12); border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: rgba(255, 255, 255, 0.25); }}

        .container {{ max-width: 1400px; margin: 0 auto; }}

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

        /* 头部与品牌 */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding: 4px 0;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .brand-icon {{
            width: 38px;
            height: 38px;
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
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 20px;
            background: rgba(94, 106, 210, 0.15);
            color: #818cf8;
            border: 1px solid rgba(94, 106, 210, 0.3);
        }}

        /* Linear 顶层 Tab 导航器 */
        .nav-tabs {{
            display: inline-flex;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-card);
            border-radius: 10px;
            padding: 4px;
            gap: 4px;
        }}
        .nav-tab-btn {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 500;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.18s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .nav-tab-btn:hover {{
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.05);
        }}
        .nav-tab-btn.active {{
            background: var(--linear-brand);
            color: #ffffff;
            box-shadow: 0 2px 10px rgba(94, 106, 210, 0.4);
        }}
        .port-badge {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 4px;
            background: rgba(0, 0, 0, 0.35);
            color: rgba(255, 255, 255, 0.85);
        }}

        .header-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .live-status {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 20px;
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.2);
            font-size: 12px;
            color: var(--accent-emerald);
            font-weight: 500;
        }}
        .pulse-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-emerald);
            box-shadow: 0 0 10px var(--accent-emerald);
            animation: pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }}
        @keyframes pulse-ring {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.4; transform: scale(0.95); }}
        }}

        .btn {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-primary);
            border: 1px solid var(--border-card);
            padding: 7px 14px;
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
        .btn:active {{ transform: translateY(0); }}
        .btn-primary {{
            background: var(--linear-brand);
            border-color: var(--linear-brand);
            color: #ffffff;
            box-shadow: 0 0 14px var(--glow-brand);
        }}
        .btn-primary:hover {{
            background: var(--linear-brand-hover);
            border-color: var(--linear-brand-hover);
        }}
        .btn-success {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border-color: rgba(16, 185, 129, 0.3);
        }}
        .btn-success:hover {{
            background: rgba(16, 185, 129, 0.25);
            border-color: rgba(16, 185, 129, 0.4);
        }}

        /* 通用卡片与容器 */
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 14px;
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .card-title {{
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
            letter-spacing: -0.01em;
        }}
        .card-sub {{
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 2px;
        }}

        /* KPI 指标网格 */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }}
        .metric-box {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 12px;
            padding: 16px 18px;
            backdrop-filter: blur(20px);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}
        .metric-box:hover {{
            transform: translateY(-2px);
            border-color: rgba(255, 255, 255, 0.15);
        }}
        .metric-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }}
        .metric-label {{
            font-size: 12px;
            font-weight: 500;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .metric-val {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 26px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.03em;
        }}
        .metric-foot {{
            font-size: 11px;
            color: var(--text-tertiary);
            margin-top: 4px;
        }}

        /* 专属通道横幅 Banner */
        .channel-banner {{
            background: linear-gradient(135deg, rgba(94, 106, 210, 0.12) 0%, rgba(56, 189, 248, 0.08) 100%);
            border: 1px solid rgba(94, 106, 210, 0.3);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .channel-banner-info {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}
        .channel-badge-icon {{
            width: 42px;
            height: 42px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }}
        .endpoint-pill {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 4px 10px;
            border-radius: 6px;
            color: #38bdf8;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}

        /* 表格样式 */
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

        /* Switch */
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
            border: 1px solid var(--border-card);
            color: var(--text-secondary);
        }}
        .badge-harness {{
            background: rgba(94, 106, 210, 0.15);
            border-color: rgba(94, 106, 210, 0.35);
            color: #a5b4fc;
        }}
        .badge-codex {{
            background: rgba(16, 185, 129, 0.15);
            border-color: rgba(16, 185, 129, 0.35);
            color: #6ee7b7;
        }}

        /* 实时日志流 */
        .log-terminal {{
            background: #090a0f;
            border: 1px solid var(--border-card);
            border-radius: 10px;
            padding: 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11.5px;
            line-height: 1.6;
            max-height: 380px;
            overflow-y: auto;
            color: #c9d1d9;
        }}
        .log-item {{
            padding: 4px 6px;
            border-radius: 4px;
            display: flex;
            align-items: baseline;
            gap: 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        }}
        .log-item:hover {{ background: rgba(255, 255, 255, 0.03); }}
        .log-time {{ color: var(--text-tertiary); font-size: 10.5px; flex-shrink: 0; }}

        .badge-model-hit {{
            background: rgba(56, 189, 248, 0.12);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 7px;
            border-radius: 4px;
        }}

        /* YAML 配置文件在线编辑器 */
        .yaml-editor-box {{
            width: 100%;
            height: 480px;
            background: #090a0f;
            border: 1px solid var(--border-card);
            border-radius: 10px;
            padding: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12.5px;
            line-height: 1.6;
            color: #e6edf3;
            resize: vertical;
            outline: none;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.5);
            white-space: pre;
        }}
        .yaml-editor-box:focus {{
            border-color: var(--linear-brand);
            box-shadow: 0 0 0 2px var(--glow-brand), inset 0 2px 8px rgba(0,0,0,0.5);
        }}

        /* Toast 提示 */
        #toast {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #1e2230;
            color: #ffffff;
            padding: 12px 20px;
            border-radius: 8px;
            border: 1px solid var(--border-focus);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            font-size: 13px;
            font-weight: 500;
            display: none;
            z-index: 1000;
            animation: toast-in 0.2s ease;
        }}
        @keyframes toast-in {{
            from {{ transform: translateY(20px); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}

        /* 双轨流量卡片 */
        .dual-channel-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 20px;
        }}
        @media (max-width: 860px) {{
            .dual-channel-grid {{ grid-template-columns: 1fr; }}
        }}
        .channel-summary-card {{
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-card);
            border-radius: 10px;
            padding: 16px;
        }}

        /* 工具调用分类小球 */
        .tool-pill {{
            padding: 4px 10px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11.5px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-card);
        }}

        .card.collapsed .card-header {{ margin-bottom: 0; }}
        .yaml-body {{ display: none; }}
        .yaml-body.open {{ display: block; }}
        .yaml-toggle {{
            cursor: pointer;
            user-select: none;
        }}
        .yaml-toggle:hover .card-title {{ color: #c7c9d1; }}
        .collapse-hint {{
            font-size: 11px;
            color: var(--text-tertiary);
            font-weight: 500;
        }}
        .queue-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 10px;
        }}
        .queue-box {{
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 10px 12px;
        }}
        .queue-title {{
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }}
        .queue-item {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: var(--text-primary);
            line-height: 1.45;
            margin-bottom: 4px;
        }}
        .cooldown {{
            color: var(--accent-amber);
            font-size: 10px;
        }}
        .log-item.fail {{
            background: rgba(244, 63, 94, 0.08);
            border-radius: 6px;
            padding: 4px 6px;
        }}
        .key-vis-label {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--text-secondary);
        }}

        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 顶栏与品牌 -->
        <div class="header">
            <div class="brand">
                <div>
                    <div class="brand-title">
                        Linear Gateway
                        <span class="brand-badge">Free Token 双轨调度</span>
                    </div>
                    <div class="card-sub">DeepSeek-Harness 与 Codex CLI 物理隔离、渠道商独立配置</div>
                </div>
            </div>

            <!-- Linear 风格 2-Tab 切换器 -->
            <div class="nav-tabs">
                <button class="nav-tab-btn active" id="btn-tab-harness" onclick="switchTab('harness')">
                    <span>DeepSeek Harness</span>
                    <span class="port-badge">:{harness_port}</span>
                </button>
                <button class="nav-tab-btn" id="btn-tab-codex" onclick="switchTab('codex')">
                    <span>ChatGPT Codex CLI</span>
                    <span class="port-badge">:{codex_port}</span>
                </button>
            </div>

            <div class="header-actions">
                <div class="live-status">
                    <span class="pulse-dot"></span>
                    <span id="header-status-text">双轨并发服务正常</span>
                </div>
                <button class="btn btn-primary" onclick="refreshActiveTab()">刷新</button>
            </div>
        </div>

        <!-- ======================================================= -->
        <!-- TAB 1: DeepSeek Harness 专区                            -->
        <!-- ======================================================= -->
        <div id="tab-harness" class="tab-content active">
            <!-- Harness 横幅 -->
            <div class="channel-banner" style="border-color:rgba(94, 106, 210, 0.4);">
                <div class="channel-banner-info">
                    <div>
                        <div style="font-size:14px;font-weight:700;color:var(--text-primary);">DeepSeek Harness 专属接入端点</div>
                        <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">
                            原生 OpenAI 协议代理 · 适配 DeepSeek 官方客户端与 Web 3080 服务 · 独立渠道商配置
                        </div>
                    </div>
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <span class="endpoint-pill" style="font-size:13px;padding:6px 14px;">http://127.0.0.1:{harness_port}/v1</span>
                </div>
            </div>

            <!-- Harness KPI -->
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-top"><span class="metric-label">Harness 请求次数</span></div>
                    <div class="metric-val" id="h-total-req">0</div>
                    <div class="metric-foot">端口 {harness_port} 独立计数</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top"><span class="metric-label">Harness 成功率</span></div>
                    <div class="metric-val" style="color:var(--accent-emerald);" id="h-success-rate">100%</div>
                    <div class="metric-foot" id="h-success-foot">成功 0 / 失败 0</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top"><span class="metric-label">Harness 降级重试</span></div>
                    <div class="metric-val" style="color:var(--accent-violet);" id="h-failover-count">0</div>
                    <div class="metric-foot">多渠道热备容灾触发</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top"><span class="metric-label">平均响应时间</span></div>
                    <div class="metric-val" style="color:var(--accent-amber);" id="h-avg-latency">0ms</div>
                    <div class="metric-foot">Harness 链路平均时延</div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">调度队列</div>
                        <div class="card-sub">最近命中、冷却中的上游，以及 auto / deepseek / glm / kimi 的优先候选</div>
                    </div>
                </div>
                <div id="harness-dispatch"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">Harness 独立渠道商</div>
                        <div class="card-sub">仅作用于 <code>config.harness.yaml</code>，不会改动 Codex 渠道开关与 Key</div>
                    </div>
                    <div style="display:flex;gap:12px;align-items:center;">
                        <div class="key-vis-label">
                            <span>显示 Key</span>
                            <label class="switch">
                                <input type="checkbox" onchange="setKeyVisibility('harness', this.checked)">
                                <span class="slider"></span>
                            </label>
                        </div>
                        <button class="btn" onclick="enableAllProviders('harness')">全部启用</button>
                    </div>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>状态</th>
                                <th>渠道服务商</th>
                                <th>API Key 配置</th>
                                <th>网络延迟</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="harness-providers-table-body"></tbody>
                    </table>
                </div>
            </div>

            <!-- Harness 配置编辑器 -->
            <div class="card collapsed" id="harness-yaml-card">
                <div class="card-header yaml-toggle" onclick="toggleYamlEditor('harness')">
                    <div>
                        <div class="card-title">Harness 专用配置 (<code>config.harness.yaml</code>)</div>
                        <div class="card-sub">物理独立配置文件，修改保存后即时热重载生效，不影响 Codex 渠道与别名</div>
                    </div>
                    <span class="collapse-hint" id="harness-yaml-toggle-hint">展开</span>
                </div>
                <div class="yaml-body" id="harness-yaml-body">
                    <div style="display:flex;gap:8px;justify-content:flex-end;margin-bottom:10px;">
                        <button class="btn" onclick="event.stopPropagation(); loadConfigYaml('harness')">重新读取</button>
                        <button class="btn btn-primary" onclick="event.stopPropagation(); saveConfigYaml('harness')">保存并即时热重载</button>
                    </div>
                    <textarea id="harness-yaml-editor" class="yaml-editor-box" spellcheck="false" placeholder="正在加载 config.harness.yaml..."></textarea>
                </div>
            </div>

            <!-- Harness 专属实时日志 -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Harness 专属链路日志 (Port {harness_port})</div>
                    <button class="btn" onclick="clearLogs()">清空日志</button>
                </div>
                <div class="log-terminal" id="harness-log-stream">
                    <div style="color:var(--text-tertiary);text-align:center;padding:20px;">正在监听 Harness 专属日志...</div>
                </div>
            </div>
        </div>

        <!-- ======================================================= -->
        <!-- TAB 3: ChatGPT Codex CLI 专区                           -->
        <!-- ======================================================= -->
        <div id="tab-codex" class="tab-content">
            <!-- Codex 横幅 -->
            <div class="channel-banner" style="border-color:rgba(16, 185, 129, 0.4);">
                <div class="channel-banner-info">
                    <div>
                        <div style="font-size:14px;font-weight:700;color:var(--text-primary);">ChatGPT Codex CLI 专属接入端点</div>
                        <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">
                            支持 OpenAI 2026 Responses Wire API 适配协议 (`/v1/responses`) · 工具调用极速中转
                        </div>
                    </div>
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <span class="endpoint-pill" style="font-size:13px;padding:6px 14px;color:#34d399;">http://127.0.0.1:{codex_port}/v1</span>
                    <button class="btn btn-success" onclick="syncCodexConfig()">一键同步至 ~/.codex/config.toml</button>
                </div>
            </div>

            <!-- Codex KPI -->
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-top"><span class="metric-label">Codex 总请求数</span></div>
                    <div class="metric-val" id="c-total-req">0</div>
                    <div class="metric-foot">端口 {codex_port} 独立计数</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top"><span class="metric-label">工具调用总数</span></div>
                    <div class="metric-val" style="color:var(--accent-cyan);" id="c-total-tools">0</div>
                    <div class="metric-foot" id="c-tool-foot">apply_patch / exec_command</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top"><span class="metric-label">apply_patch 次数</span></div>
                    <div class="metric-val" style="color:#a855f7;" id="c-apply-patch">0</div>
                    <div class="metric-foot">文件精准补丁合成</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top"><span class="metric-label">exec_command 次数</span></div>
                    <div class="metric-val" style="color:var(--accent-amber);" id="c-exec-cmd">0</div>
                    <div class="metric-foot">终端安全命令执行</div>
                </div>
            </div>

            <!-- Codex 工具执行明细卡片 -->
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">Codex CLI 工具调用统计</div>
                        <div class="card-sub">自动拦截并聚合 Responses Wire 协议中的 Agent 工具调用</div>
                    </div>
                </div>
                <div style="display:flex;gap:12px;flex-wrap:wrap;">
                    <div class="tool-pill">
                        <span style="color:#a855f7;font-weight:600;">apply_patch:</span>
                        <span id="pill-apply-patch" style="font-weight:700;color:var(--text-primary);">0</span>
                    </div>
                    <div class="tool-pill">
                        <span style="color:var(--accent-amber);font-weight:600;">exec_command:</span>
                        <span id="pill-exec-cmd" style="font-weight:700;color:var(--text-primary);">0</span>
                    </div>
                    <div class="tool-pill">
                        <span style="color:var(--accent-cyan);font-weight:600;">其他 Tools:</span>
                        <span id="pill-other-tools" style="font-weight:700;color:var(--text-primary);">0</span>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">调度队列</div>
                        <div class="card-sub">最近命中、冷却中的上游，以及 auto / deepseek / glm / kimi 的优先候选</div>
                    </div>
                </div>
                <div id="codex-dispatch"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">Codex 独立渠道商</div>
                        <div class="card-sub">仅作用于 <code>config.codex.yaml</code>，不会改动 Harness 渠道开关与 Key</div>
                    </div>
                    <div style="display:flex;gap:12px;align-items:center;">
                        <div class="key-vis-label">
                            <span>显示 Key</span>
                            <label class="switch">
                                <input type="checkbox" onchange="setKeyVisibility('codex', this.checked)">
                                <span class="slider"></span>
                            </label>
                        </div>
                        <button class="btn" onclick="enableAllProviders('codex')">全部启用</button>
                    </div>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>状态</th>
                                <th>渠道服务商</th>
                                <th>API Key 配置</th>
                                <th>网络延迟</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="codex-providers-table-body"></tbody>
                    </table>
                </div>
            </div>

            <!-- Codex 配置编辑器 -->
            <div class="card collapsed" id="codex-yaml-card">
                <div class="card-header yaml-toggle" onclick="toggleYamlEditor('codex')">
                    <div>
                        <div class="card-title">Codex 专用配置 (<code>config.codex.yaml</code>)</div>
                        <div class="card-sub">物理独立配置文件，定制 Codex 专属模型别名与多级保活梯队</div>
                    </div>
                    <span class="collapse-hint" id="codex-yaml-toggle-hint">展开</span>
                </div>
                <div class="yaml-body" id="codex-yaml-body">
                    <div style="display:flex;gap:8px;justify-content:flex-end;margin-bottom:10px;">
                        <button class="btn" onclick="event.stopPropagation(); loadConfigYaml('codex')">重新读取</button>
                        <button class="btn btn-primary" onclick="event.stopPropagation(); saveConfigYaml('codex')">保存并即时热重载</button>
                    </div>
                    <textarea id="codex-yaml-editor" class="yaml-editor-box" spellcheck="false" placeholder="正在加载 config.codex.yaml..."></textarea>
                </div>
            </div>

            <!-- Codex 专属实时日志 -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">Codex 专属链路日志 (Port {codex_port})</div>
                    <button class="btn" onclick="clearLogs()">清空日志</button>
                </div>
                <div class="log-terminal" id="codex-log-stream">
                    <div style="color:var(--text-tertiary);text-align:center;padding:20px;">正在监听 Codex 专属日志...</div>
                </div>
            </div>
        </div>
    </div>

    <div id="toast"></div>

    <script>
        const initialProviders = {{
            harness: {harness_providers_json},
            codex: {codex_providers_json}
        }};
        let activeTab = 'harness';
        let isConfigLoaded = {{ harness: false, codex: false }};
        let keyVisible = {{ harness: false, codex: false }};
        let yamlOpen = {{ harness: false, codex: false }};

        function showToast(msg) {{
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.style.display = 'block';
            setTimeout(() => {{ t.style.display = 'none'; }}, 3200);
        }}

        function setText(id, value) {{
            const el = document.getElementById(id);
            if (el) el.innerText = value;
        }}

        function switchTab(tab) {{
            activeTab = tab;
            ['harness', 'codex'].forEach(t => {{
                const btn = document.getElementById('btn-tab-' + t);
                const content = document.getElementById('tab-' + t);
                if (!btn || !content) return;
                if (t === tab) {{
                    btn.classList.add('active');
                    content.classList.add('active');
                }} else {{
                    btn.classList.remove('active');
                    content.classList.remove('active');
                }}
            }});

            if (tab === 'harness' && yamlOpen.harness && !isConfigLoaded.harness) {{
                loadConfigYaml('harness');
            }} else if (tab === 'codex' && yamlOpen.codex && !isConfigLoaded.codex) {{
                loadConfigYaml('codex');
            }}
            refreshActiveTab();
        }}

        function escapeHtml(s) {{
            return String(s || '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
        }}

        function renderProviders(providers, channel) {{
            const tbody = document.getElementById(channel + '-providers-table-body');
            if (!tbody) return;
            tbody.innerHTML = '';
            (providers || []).forEach(p => {{
                const tr = document.createElement('tr');
                const isEnabled = !!p.enabled;
                const safeName = escapeHtml(p.name);
                const models = (p.models || []).map(m => typeof m === 'string' ? m : (m.upstream_model || m.id || '')).filter(Boolean);
                const modelsHtml = models.length > 0
                    ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:6px;">` +
                      models.slice(0, 3).map(m => `<span class="badge" style="font-size:10px;padding:1px 6px;color:#94a3b8;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);font-family:'JetBrains Mono',monospace;">${{escapeHtml(m)}}</span>`).join('') +
                      (models.length > 3 ? `<span class="badge" style="font-size:10px;padding:1px 5px;color:var(--text-tertiary);">+${{models.length - 3}}</span>` : '') +
                      `</div>`
                    : '';

                tr.innerHTML = `
                    <td>
                        <label class="switch">
                            <input type="checkbox" ${{isEnabled ? 'checked' : ''}} onchange="toggleProvider('${{safeName}}', this.checked, '${{channel}}')">
                            <span class="slider"></span>
                        </label>
                    </td>
                    <td>
                        <strong style="color:var(--text-primary);font-size:13px;">${{safeName}}</strong>
                        <div style="font-size:10.5px;color:var(--text-tertiary);font-family:'JetBrains Mono'">${{escapeHtml(p.base_url || 'https://api.openai.com/v1')}}</div>
                        ${{modelsHtml}}
                    </td>
                    <td>
                        <div class="key-group">
                            <input type="${{keyVisible[channel] ? 'text' : 'password'}}" class="key-input" id="key-${{channel}}-${{safeName}}" placeholder="${{escapeHtml(p.api_key_masked || '未配置')}}" value="${{escapeHtml(p.api_key || '')}}" data-masked="${{p.api_key && String(p.api_key).includes('••••') ? '1' : '0'}}" />
                            <button class="btn" style="padding:4px 8px;" onclick="updateKey('${{safeName}}', '${{channel}}')">更新</button>
                        </div>
                    </td>
                    <td id="lat-${{channel}}-${{safeName}}" style="font-family:'JetBrains Mono';font-size:11.5px;color:var(--text-tertiary);">-</td>
                    <td>
                        <button class="btn" style="padding:4px 8px;" onclick="testProviderLatency('${{safeName}}', '${{channel}}')">测速</button>
                        <button class="btn" style="padding:4px 8px;color:var(--accent-rose);" onclick="deleteProvider('${{safeName}}', '${{channel}}')">删除</button>
                    </td>
                `;
                tbody.appendChild(tr);
            }});
            applyKeyVisibility(channel);
        }}

        async function fetchStats() {{
            try {{
                const res = await fetch('/api/stats');
                if (!res.ok) return;
                const d = await res.json();

                const h = d.harness || {{}};
                const hReq = h.total_requests || 0;
                const hSucc = h.success_requests || 0;
                const hFail = h.failed_requests || 0;
                const hRate = hReq > 0 ? ((hSucc / hReq) * 100).toFixed(1) + '%' : '100%';
                const hLat = hSucc > 0 ? Math.round((h.total_latency_sum || 0) / hSucc) + 'ms' : '0ms';

                setText('h-total-req', hReq);
                setText('h-success-rate', hRate);
                setText('h-success-foot', `成功 ${{hSucc}} / 失败 ${{hFail}}`);
                setText('h-failover-count', (h.failover_events || 0));
                setText('h-avg-latency', hLat);

                const c = d.codex || {{}};
                const cReq = c.total_requests || 0;
                const cSucc = c.success_requests || 0;
                const cRate = cReq > 0 ? ((cSucc / cReq) * 100).toFixed(1) + '%' : '100%';
                const tools = c.tool_calls || {{}};
                const cPatch = tools.apply_patch || 0;
                const cExec = tools.exec_command || 0;
                const cOther = tools.other || 0;
                const cTools = cPatch + cExec + cOther;

                setText('c-total-req', cReq);
                setText('c-total-tools', cTools);
                setText('c-apply-patch', cPatch);
                setText('c-exec-cmd', cExec);
                setText('pill-apply-patch', cPatch);
                setText('pill-exec-cmd', cExec);
                setText('pill-other-tools', cOther);

                renderDispatch(d.dispatch && d.dispatch.harness, 'harness');
                renderDispatch(d.dispatch && d.dispatch.codex, 'codex');
                applyHealth(d.health);
            }} catch (e) {{
                console.error("fetchStats error:", e);
            }}
        }}

        async function fetchLogs() {{
            try {{
                const channel = activeTab;
                const res = await fetch(`/api/logs?channel=${{channel}}`);
                if (!res.ok) return;
                const logs = await res.json();
                const containerId = channel === 'harness' ? 'harness-log-stream' : 'codex-log-stream';
                const el = document.getElementById(containerId);
                if (!el) return;

                if (!logs || logs.length === 0) {{
                    el.innerHTML = '<div style="color:var(--text-tertiary);text-align:center;padding:20px;">暂无日志记录</div>';
                    return;
                }}

                el.innerHTML = logs.slice(-50).reverse().map(l => {{
                    const statusVal = l.status_code || (typeof l.status === 'number' ? l.status : 200);
                    const isOk = statusVal < 400;
                    const statusColor = isOk ? 'var(--accent-emerald)' : 'var(--accent-rose)';
                    const chBadge = l.channel === 'codex'
                        ? '<span class="badge badge-codex">CODEX</span>'
                        : '<span class="badge badge-harness">HARNESS</span>';
                    const reqModel = l.requested_model || l.model || 'auto';
                    const hitProvider = l.final_provider || l.provider || 'Gateway';
                    const hitModel = l.final_model || l.upstream_model || '';
                    const streamBadge = l.stream
                        ? '<span class="badge" style="font-size:10px;padding:1px 5px;color:#a78bfa;border-color:rgba(167,139,250,0.3);">SSE</span>'
                        : '<span class="badge" style="font-size:10px;padding:1px 5px;color:#94a3b8;">REST</span>';
                    const toolsInfo = l.tool_calls ? `<span style="color:var(--accent-cyan);font-size:11px;">[Tools: ${{l.tool_calls}}]</span>` : '';
                    const hitModelPill = hitModel && hitModel !== 'None'
                        ? `<span class="badge-model-hit" title="命中的真实大模型">${{hitModel}}</span>`
                        : `<span style="color:var(--accent-rose);font-size:11px;">(未命中模型)</span>`;

                    const failHint = String(l.status || '').toLowerCase().includes('fail')
                        || String(l.status || '').toLowerCase().includes('error')
                        || !!l.error;
                    const rowClass = (!isOk || failHint) ? 'log-item fail' : 'log-item';
                    const failTag = failHint ? `<span class="badge" style="color:var(--accent-rose);border-color:rgba(244,63,94,0.35);">${{escapeHtml(l.status || 'failed')}}</span>` : '';

                    return `
                        <div class="${{rowClass}}">
                            <span class="log-time">${{l.time || ''}}</span>
                            ${{chBadge}}
                            <span style="color:${{statusColor}};font-weight:700;font-size:11.5px;">${{statusVal}}</span>
                            ${{failTag}}
                            <span style="color:var(--text-secondary);font-size:11px;font-family:'JetBrains Mono';">${{l.method || 'POST'}}</span>
                            <span style="color:#818cf8;font-weight:600;font-family:'JetBrains Mono';font-size:11.5px;" title="客户端请求模型">${{reqModel}}</span>
                            <span style="color:var(--text-tertiary);font-size:11px;">→</span>
                            <span style="color:var(--text-primary);font-weight:600;font-size:11.5px;" title="命中的渠道商">${{hitProvider}}</span>
                            ${{hitModelPill}}
                            <span style="color:var(--accent-amber);font-family:'JetBrains Mono';font-size:11px;">${{l.latency_ms || l.latency || 0}}ms</span>
                            ${{streamBadge}}
                            ${{toolsInfo}}
                        </div>
                    `;
                }}).join('');
            }} catch (e) {{
                console.error("fetchLogs error:", e);
            }}
        }}

        async function setKeyVisibility(channel, visible) {{
            keyVisible[channel] = !!visible;
            try {{
                const res = await fetch(`/api/providers?channel=${{channel}}&reveal=${{visible ? 'true' : 'false'}}`);
                const d = await res.json();
                if (res.ok) {{
                    renderProviders(d.providers || [], channel);
                    const stats = await fetch('/api/stats').then(r => r.json());
                    applyHealth(stats.health);
                }}
            }} catch (e) {{
                showToast('读取渠道商失败: ' + e.message);
            }}
        }}

        function applyKeyVisibility(channel) {{
            const show = !!keyVisible[channel];
            document.querySelectorAll('#' + channel + '-providers-table-body .key-input').forEach(el => {{
                el.type = show ? 'text' : 'password';
            }});
        }}

        function renderDispatch(data, channel) {{
            const el = document.getElementById(channel + '-dispatch');
            if (!el) return;
            const hit = (data && data.last_hit) || null;
            const queues = (data && data.queues) || {{}};
            const cds = (data && data.cooldowns) || [];
            const hitHtml = hit
                ? `<div style="margin-bottom:12px;font-size:12.5px;">最近命中: <strong>${{escapeHtml(hit.provider)}}</strong> / <span class="badge-model-hit">${{escapeHtml(hit.model)}}</span> · ${{hit.latency_ms || 0}}ms · 请求 ${{escapeHtml(hit.requested_model || '')}}</div>`
                : `<div style="margin-bottom:12px;font-size:12px;color:var(--text-tertiary);">暂无命中记录</div>`;
            const cdHtml = cds.length
                ? `<div style="margin-bottom:10px;font-size:11px;color:var(--accent-amber);">冷却: ${{cds.map(c => escapeHtml(c.provider) + '/' + escapeHtml(c.model) + ' ' + c.remaining_s + 's').join(' · ')}}</div>`
                : '';
            const boxes = ['auto', 'deepseek', 'glm', 'kimi'].map(group => {{
                const items = queues[group] || [];
                const rows = items.length
                    ? items.map((it, idx) => `<div class="queue-item">${{idx + 1}}. ${{escapeHtml(it.provider)}} / ${{escapeHtml(it.model)}}${{it.cooldown_s ? ` <span class="cooldown">${{it.cooldown_s}}s</span>` : ''}}</div>`).join('')
                    : `<div class="queue-item" style="color:var(--text-tertiary);">暂无候选</div>`;
                return `<div class="queue-box"><div class="queue-title">${{group}}</div>${{rows}}</div>`;
            }}).join('');
            el.innerHTML = hitHtml + cdHtml + `<div class="queue-grid">${{boxes}}</div>`;
        }}

        function applyHealth(health) {{
            Object.values(health || {{}}).forEach(h => {{
                if (!h || !h.channel || !h.name) return;
                const el = document.getElementById(`lat-${{h.channel}}-${{h.name}}`);
                if (!el) return;
                if (h.status === 'ok') {{
                    el.innerHTML = `<span style="color:var(--accent-emerald);font-weight:600;">${{h.latency_ms || 0}}ms</span>`;
                }} else if (h.status === 'skip') {{
                    el.innerHTML = `<span style="color:var(--text-tertiary);">未配置</span>`;
                }} else if (h.message) {{
                    el.innerHTML = `<span style="color:var(--accent-rose);" title="${{escapeHtml(h.message)}}">失败</span>`;
                }}
            }});
        }}

        function toggleYamlEditor(channel) {{
            yamlOpen[channel] = !yamlOpen[channel];
            const open = yamlOpen[channel];
            const body = document.getElementById(channel + '-yaml-body');
            const card = document.getElementById(channel + '-yaml-card');
            const hint = document.getElementById(channel + '-yaml-toggle-hint');
            if (body) body.classList.toggle('open', open);
            if (card) card.classList.toggle('collapsed', !open);
            if (hint) hint.innerText = open ? '收起' : '展开';
            if (open && !isConfigLoaded[channel]) {{
                loadConfigYaml(channel);
            }}
        }}

        async function loadConfigYaml(channel) {{
            try {{
                const res = await fetch(`/api/config/${{channel}}`);
                if (!res.ok) throw new Error("获取配置失败");
                const d = await res.json();
                const editor = document.getElementById(`${{channel}}-yaml-editor`);
                if (editor) {{
                    editor.value = d.content;
                    isConfigLoaded[channel] = true;
                }}
            }} catch (e) {{
                showToast(`加载 ${{channel}} 配置失败: ` + e.message);
            }}
        }}

        async function saveConfigYaml(channel) {{
            const editor = document.getElementById(`${{channel}}-yaml-editor`);
            if (!editor) return;
            const content = editor.value;
            try {{
                const preview = await fetch('/api/config/validate', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ content: content }})
                }});
                const previewData = await preview.json();
                if (!preview.ok) {{
                    showToast("校验失败: " + (previewData.detail || preview.statusText));
                    return;
                }}
                const s = previewData.summary || {{}};
                const ok = confirm(
                    `即将写入 ${{channel}} 配置并热重载。\\n` +
                    `启用渠道 ${{(s.enabled || []).length}} 个: ${{(s.enabled || []).join(', ') || '无'}}\\n` +
                    `停用渠道 ${{(s.disabled || []).length}} 个 · 模型条目 ${{s.models_total || 0}} · 暴露 ${{(s.exposed_models || []).join(', ')}}\\n\\n` +
                    `确认保存？`
                );
                if (!ok) return;
                const res = await fetch(`/api/config/${{channel}}`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ content: content }})
                }});
                const d = await res.json();
                if (res.ok) {{
                    showToast(d.message || "配置已保存并即时热重载！");
                    loadConfigYaml(channel);
                    if (keyVisible[channel]) {{
                        await setKeyVisibility(channel, true);
                    }} else {{
                        const stats = await fetch('/api/stats').then(r => r.json());
                        if (stats.providers && stats.providers[channel]) {{
                            renderProviders(stats.providers[channel], channel);
                        }}
                        applyHealth(stats.health);
                    }}
                }} else {{
                    showToast("保存失败: " + (d.detail || res.statusText));
                }}
            }} catch (e) {{
                showToast("保存异常: " + e.message);
            }}
        }}

        async function syncCodexConfig() {{
            try {{
                const res = await fetch('/api/tools/sync-codex-config', {{ method: 'POST' }});
                const d = await res.json();
                if (res.ok) {{
                    showToast(d.message || "已成功同步至 ~/.codex/config.toml！");
                }} else {{
                    showToast("同步失败: " + (d.detail || res.statusText));
                }}
            }} catch (e) {{
                showToast("同步异常: " + e.message);
            }}
        }}

        async function toggleProvider(name, enabled, channel) {{
            try {{
                const res = await fetch('/api/providers/toggle', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name, enabled: enabled, channel: channel }})
                }});
                if (res.ok) {{
                    showToast(`[${{channel}}] 渠道 [${{name}}] 已设为: ${{enabled ? '启用' : '禁用'}}`);
                }}
            }} catch (e) {{
                showToast("切换失败: " + e.message);
            }}
        }}

        async function updateKey(name, channel) {{
            const input = document.getElementById(`key-${{channel}}-${{name}}`);
            if (!input) return;
            const key = input.value.trim();
            if (!key || key.includes('••••')) {{
                showToast('请先打开「显示 Key」，或直接填入完整新密钥后再更新');
                return;
            }}
            try {{
                const res = await fetch('/api/providers/update_key', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name, api_key: key, channel: channel }})
                }});
                if (res.ok) {{
                    showToast(`[${{channel}}] 渠道 [${{name}}] API Key 已更新`);
                }}
            }} catch (e) {{
                showToast("更新失败: " + e.message);
            }}
        }}

        async function testProviderLatency(name, channel) {{
            const latEl = document.getElementById(`lat-${{channel}}-${{name}}`);
            if (latEl) latEl.innerText = '测试中...';
            try {{
                const res = await fetch('/api/providers/test', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name, channel: channel }})
                }});
                const d = await res.json();
                if (latEl) {{
                    if (d.status === 'ok') {{
                        latEl.innerHTML = `<span style="color:var(--accent-emerald);font-weight:600;">${{d.latency_ms}}ms</span>`;
                    }} else {{
                        latEl.innerHTML = `<span style="color:var(--accent-rose);">失败</span>`;
                    }}
                }}
            }} catch (e) {{
                if (latEl) latEl.innerHTML = `<span style="color:var(--accent-rose);">超时</span>`;
            }}
        }}

        async function deleteProvider(name, channel) {{
            if (!confirm(`确定要从 ${{channel}} 配置中删除渠道 [${{name}}] 吗？此操作不会影响另一条通道。`)) return;
            try {{
                const res = await fetch('/api/providers/delete', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name, channel: channel }})
                }});
                if (res.ok) {{
                    showToast(`[${{channel}}] 渠道 [${{name}}] 已删除`);
                    const stats = await fetch('/api/stats').then(r => r.json());
                    if (stats.providers && stats.providers[channel]) {{
                        renderProviders(stats.providers[channel], channel);
                    }}
                }}
            }} catch (e) {{
                showToast("删除失败: " + e.message);
            }}
        }}

        async function enableAllProviders(channel) {{
            const checkboxes = document.querySelectorAll('#' + channel + '-providers-table-body input[type="checkbox"]');
            for (let cb of checkboxes) {{
                if (!cb.checked) {{
                    cb.checked = true;
                    cb.dispatchEvent(new Event('change'));
                }}
            }}
            showToast(`已批量请求启用 ${{channel}} 全部渠道`);
        }}

        async function clearLogs() {{
            try {{
                await fetch('/api/logs/clear?channel=' + activeTab, {{ method: 'POST' }});
                fetchLogs();
                showToast(activeTab + " 实时日志已清空");
            }} catch (e) {{}}
        }}

        function refreshActiveTab() {{
            fetchStats();
            fetchLogs();
        }}

        renderProviders(initialProviders.harness, 'harness');
        renderProviders(initialProviders.codex, 'codex');
        fetchStats();
        fetchLogs();
        setInterval(fetchStats, 3000);
        setInterval(fetchLogs, 3000);
    </script>
</body>
</html>"""
