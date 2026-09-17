# -*- coding: utf-8 -*-
"""
Linear Dashboard HTML Generator
提供一站式 Linear 风格三 Tab 单页控制台：
1. 全局总览 (Dual-Channel Overview & Providers)
2. DeepSeek Harness 专区 (Port 8000, config.harness.yaml, Logs)
3. ChatGPT Codex CLI 专区 (Port 8001, config.codex.yaml, Tool breakdown, One-click sync)
"""

def get_dashboard_html(providers_json: str, harness_port: int = 8000, codex_port: int = 8001) -> str:
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

        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 顶栏与品牌 -->
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
                        <span class="brand-badge">Free Token 双轨调度</span>
                    </div>
                    <div class="card-sub">DeepSeek-Harness & Codex CLI 物理隔离、独立配置、统一全景监控</div>
                </div>
            </div>

            <!-- Linear 风格 3-Tab 切换器 -->
            <div class="nav-tabs">
                <button class="nav-tab-btn active" id="btn-tab-overview" onclick="switchTab('overview')">
                    <span class="svg-icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1 4-10z"></path></svg></span>
                    <span>全局总览</span>
                </button>
                <button class="nav-tab-btn" id="btn-tab-harness" onclick="switchTab('harness')">
                    <span class="svg-icon"><svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg></span>
                    <span>DeepSeek Harness</span>
                    <span class="port-badge">:{harness_port}</span>
                </button>
                <button class="nav-tab-btn" id="btn-tab-codex" onclick="switchTab('codex')">
                    <span class="svg-icon"><svg viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg></span>
                    <span>ChatGPT Codex CLI</span>
                    <span class="port-badge">:{codex_port}</span>
                </button>
            </div>

            <div class="header-actions">
                <div class="live-status">
                    <span class="pulse-dot"></span>
                    <span id="header-status-text">双轨并发服务正常</span>
                </div>
                <button class="btn btn-primary" onclick="refreshActiveTab()">
                    <span class="svg-icon"><svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg></span>
                    <span>刷新</span>
                </button>
            </div>
        </div>

        <!-- ======================================================= -->
        <!-- TAB 1: 全局总览 (Overview)                              -->
        <!-- ======================================================= -->
        <div id="tab-overview" class="tab-content active">
            <!-- 双端口服务状态概览 -->
            <div class="channel-banner">
                <div class="channel-banner-info">
                    <div class="channel-badge-icon" style="background:rgba(94, 106, 210, 0.2);color:#818cf8;">⚡</div>
                    <div>
                        <div style="font-size:13px;font-weight:600;color:var(--text-primary);">DeepSeek Harness 代理服务</div>
                        <div style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;">
                            端点: <span class="endpoint-pill">http://127.0.0.1:{harness_port}/v1</span>
                            &nbsp;· 配置文件: <code>config.harness.yaml</code>
                        </div>
                    </div>
                </div>
                <div class="channel-banner-info">
                    <div class="channel-badge-icon" style="background:rgba(16, 185, 129, 0.2);color:#34d399;">💻</div>
                    <div>
                        <div style="font-size:13px;font-weight:600;color:var(--text-primary);">ChatGPT Codex CLI 专用服务</div>
                        <div style="font-size:11.5px;color:var(--text-secondary);margin-top:2px;">
                            端点: <span class="endpoint-pill">http://127.0.0.1:{codex_port}/v1</span>
                            &nbsp;· 配置文件: <code>config.codex.yaml</code>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Global KPI Cards -->
            <div class="metrics-grid">
                <div class="metric-box">
                    <div class="metric-top">
                        <span class="metric-label">
                            <span class="svg-icon" style="color:var(--linear-brand);"><svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg></span>
                            全网总请求数
                        </span>
                    </div>
                    <div class="metric-val" id="g-total-req">0</div>
                    <div class="metric-foot">双轨流量实时汇总聚合</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top">
                        <span class="metric-label">
                            <span class="svg-icon" style="color:var(--accent-emerald);"><svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg></span>
                            全局成功率
                        </span>
                    </div>
                    <div class="metric-val" style="color:var(--accent-emerald);" id="g-success-rate">100%</div>
                    <div class="metric-foot" id="g-success-foot">成功 0 次 / 失败 0 次</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top">
                        <span class="metric-label">
                            <span class="svg-icon" style="color:var(--accent-violet);"><svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg></span>
                            容灾降级总数
                        </span>
                    </div>
                    <div class="metric-val" style="color:var(--accent-violet);" id="g-failover-count">0</div>
                    <div class="metric-foot">故障自动跨渠道/跨梯队保活</div>
                </div>
                <div class="metric-box">
                    <div class="metric-top">
                        <span class="metric-label">
                            <span class="svg-icon" style="color:var(--accent-amber);"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg></span>
                            平均首字时延
                        </span>
                    </div>
                    <div class="metric-val" style="color:var(--accent-amber);" id="g-avg-latency">0ms</div>
                    <div class="metric-foot">Google / Groq 直连极速响应</div>
                </div>
            </div>

            <!-- 双轨流量对比卡片 -->
            <div class="dual-channel-grid">
                <div class="channel-summary-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <span style="font-size:13px;font-weight:600;color:#818cf8;display:flex;align-items:center;gap:6px;">
                            ⚡ DeepSeek Harness 流量
                        </span>
                        <span class="badge badge-harness">Port {harness_port}</span>
                    </div>
                    <div style="display:flex;gap:20px;align-items:baseline;">
                        <div>
                            <div style="font-size:11px;color:var(--text-secondary);">请求次数</div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--text-primary);" id="ov-harness-req">0</div>
                        </div>
                        <div>
                            <div style="font-size:11px;color:var(--text-secondary);">成功率</div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--accent-emerald);" id="ov-harness-rate">100%</div>
                        </div>
                        <div>
                            <div style="font-size:11px;color:var(--text-secondary);">平均耗时</div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--accent-amber);" id="ov-harness-lat">0ms</div>
                        </div>
                    </div>
                </div>

                <div class="channel-summary-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <span style="font-size:13px;font-weight:600;color:#34d399;display:flex;align-items:center;gap:6px;">
                            💻 ChatGPT Codex CLI 流量
                        </span>
                        <span class="badge badge-codex">Port {codex_port}</span>
                    </div>
                    <div style="display:flex;gap:20px;align-items:baseline;">
                        <div>
                            <div style="font-size:11px;color:var(--text-secondary);">请求次数</div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--text-primary);" id="ov-codex-req">0</div>
                        </div>
                        <div>
                            <div style="font-size:11px;color:var(--text-secondary);">Tool 调用</div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--accent-cyan);" id="ov-codex-tools">0</div>
                        </div>
                        <div>
                            <div style="font-size:11px;color:var(--text-secondary);">成功率</div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:var(--accent-emerald);" id="ov-codex-rate">100%</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Provider 列表卡片 -->
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span class="svg-icon" style="color:var(--linear-brand);"><svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg></span>
                            <span>全局上游大厂渠道矩阵</span>
                        </div>
                        <div class="card-sub">在此开关渠道或更新 API Key，将同步作用于双轨调度引擎</div>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button class="btn" onclick="enableAllProviders()">全部启用</button>
                    </div>
                </div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>状态</th>
                                <th>渠道服务商</th>
                                <th>类别</th>
                                <th>API Key 配置</th>
                                <th>网络延迟</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="providers-table-body">
                            <!-- 动态渲染 -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- 全局实时日志 -->
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span class="svg-icon" style="color:var(--accent-cyan);"><svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg></span>
                            <span>全景双轨实时请求流</span>
                        </div>
                        <div class="card-sub">显示最近调度的所有 Harness 和 Codex 请求明细</div>
                    </div>
                    <button class="btn" onclick="clearLogs()">清空日志</button>
                </div>
                <div class="log-terminal" id="overview-log-stream">
                    <div style="color:var(--text-tertiary);text-align:center;padding:20px;">正在监听实时流量日志...</div>
                </div>
            </div>
        </div>

        <!-- ======================================================= -->
        <!-- TAB 2: DeepSeek Harness 专区                            -->
        <!-- ======================================================= -->
        <div id="tab-harness" class="tab-content">
            <!-- Harness 横幅 -->
            <div class="channel-banner" style="border-color:rgba(94, 106, 210, 0.4);">
                <div class="channel-banner-info">
                    <div class="channel-badge-icon" style="background:rgba(94, 106, 210, 0.25);color:#818cf8;">⚡</div>
                    <div>
                        <div style="font-size:14px;font-weight:700;color:var(--text-primary);">DeepSeek Harness 专属接入端点</div>
                        <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">
                            原生 OpenAI 协议代理 · 适配 DeepSeek 官方客户端与 Web 3080 服务
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

            <!-- Harness 配置编辑器 -->
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span class="svg-icon" style="color:#818cf8;"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg></span>
                            <span>Harness 专用配置 (<code>config.harness.yaml</code>)</span>
                        </div>
                        <div class="card-sub">物理独立配置文件，修改保存后即时热重载生效，不影响 Codex 渠道与别名</div>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button class="btn" onclick="loadConfigYaml('harness')">🔄 重新读取</button>
                        <button class="btn btn-primary" onclick="saveConfigYaml('harness')">💾 保存并即时热重载</button>
                    </div>
                </div>
                <textarea id="harness-yaml-editor" class="yaml-editor-box" spellcheck="false" placeholder="正在加载 config.harness.yaml..."></textarea>
            </div>

            <!-- Harness 专属实时日志 -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span class="svg-icon" style="color:#818cf8;"><svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg></span>
                        <span>Harness 专属链路日志 (Port {harness_port})</span>
                    </div>
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
                    <div class="channel-badge-icon" style="background:rgba(16, 185, 129, 0.25);color:#34d399;">💻</div>
                    <div>
                        <div style="font-size:14px;font-weight:700;color:var(--text-primary);">ChatGPT Codex CLI 专属接入端点</div>
                        <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">
                            支持 OpenAI 2026 Responses Wire API 适配协议 (`/v1/responses`) · 工具调用极速中转
                        </div>
                    </div>
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <span class="endpoint-pill" style="font-size:13px;padding:6px 14px;color:#34d399;">http://127.0.0.1:{codex_port}/v1</span>
                    <button class="btn btn-success" onclick="syncCodexConfig()">
                        <span class="svg-icon"><svg viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg></span>
                        <span>一键同步至 ~/.codex/config.toml</span>
                    </button>
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
                        <div class="card-title">
                            <span class="svg-icon" style="color:#34d399;"><svg viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg></span>
                            <span>Codex CLI 工具调用统计</span>
                        </div>
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

            <!-- Codex 配置编辑器 -->
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="card-title">
                            <span class="svg-icon" style="color:#34d399;"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg></span>
                            <span>Codex 专用配置 (<code>config.codex.yaml</code>)</span>
                        </div>
                        <div class="card-sub">物理独立配置文件，定制 Codex 专属模型别名与多级保活梯队</div>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button class="btn" onclick="loadConfigYaml('codex')">🔄 重新读取</button>
                        <button class="btn btn-primary" onclick="saveConfigYaml('codex')">💾 保存并即时热重载</button>
                    </div>
                </div>
                <textarea id="codex-yaml-editor" class="yaml-editor-box" spellcheck="false" placeholder="正在加载 config.codex.yaml..."></textarea>
            </div>

            <!-- Codex 专属实时日志 -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span class="svg-icon" style="color:#34d399;"><svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg></span>
                        <span>Codex 专属链路日志 (Port {codex_port})</span>
                    </div>
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
        const initialProviders = {providers_json};
        let activeTab = 'overview';
        let isConfigLoaded = {{ harness: false, codex: false }};

        function showToast(msg) {{
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.style.display = 'block';
            setTimeout(() => {{ t.style.display = 'none'; }}, 3200);
        }}

        function switchTab(tab) {{
            activeTab = tab;
            ['overview', 'harness', 'codex'].forEach(t => {{
                const btn = document.getElementById('btn-tab-' + t);
                const content = document.getElementById('tab-' + t);
                if (t === tab) {{
                    btn.classList.add('active');
                    content.classList.add('active');
                }} else {{
                    btn.classList.remove('active');
                    content.classList.remove('active');
                }}
            }});

            if (tab === 'harness' && !isConfigLoaded.harness) {{
                loadConfigYaml('harness');
            }} else if (tab === 'codex' && !isConfigLoaded.codex) {{
                loadConfigYaml('codex');
            }}
            refreshActiveTab();
        }}

        function renderProviders(providers) {{
            const tbody = document.getElementById('providers-table-body');
            if (!tbody) return;
            tbody.innerHTML = '';
            providers.forEach(p => {{
                const tr = document.createElement('tr');
                const isEnabled = !!p.enabled;
                const typeBadge = p.priority === 1 ? '<span class="badge" style="color:#818cf8;border-color:rgba(94,106,210,0.3);">官方大厂旗舰</span>' : '<span class="badge">快速备用</span>';
                
                tr.innerHTML = `
                    <td>
                        <label class="switch">
                            <input type="checkbox" ${{isEnabled ? 'checked' : ''}} onchange="toggleProvider('${{p.name}}', this.checked)">
                            <span class="slider"></span>
                        </label>
                    </td>
                    <td>
                        <strong style="color:var(--text-primary);font-size:13px;">${{p.name}}</strong>
                        <div style="font-size:10.5px;color:var(--text-tertiary);font-family:'JetBrains Mono'">${{p.base_url || 'https://api.openai.com/v1'}}</div>
                    </td>
                    <td>${{typeBadge}}</td>
                    <td>
                        <div class="key-group">
                            <input type="password" class="key-input" id="key-${{p.name}}" placeholder="sk-..." value="${{p.api_key || ''}}" />
                            <button class="btn" style="padding:4px 8px;" onclick="updateKey('${{p.name}}')">更新</button>
                        </div>
                    </td>
                    <td id="lat-${{p.name}}" style="font-family:'JetBrains Mono';font-size:11.5px;color:var(--text-tertiary);">-</td>
                    <td>
                        <button class="btn" style="padding:4px 8px;" onclick="testProviderLatency('${{p.name}}')">测速</button>
                        <button class="btn" style="padding:4px 8px;color:var(--accent-rose);" onclick="deleteProvider('${{p.name}}')">删除</button>
                    </td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        async function fetchStats() {{
            try {{
                const res = await fetch('/api/stats');
                if (!res.ok) return;
                const d = await res.json();
                
                // 全局统计
                const g = d.global || {{}};
                const totalReq = g.total_requests || 0;
                const succReq = g.success_requests || 0;
                const failReq = g.failed_requests || 0;
                const rate = totalReq > 0 ? ((succReq / totalReq) * 100).toFixed(1) + '%' : '100%';
                const avgLat = succReq > 0 ? Math.round((g.total_latency_sum || 0) / succReq) + 'ms' : '0ms';

                document.getElementById('g-total-req').innerText = totalReq;
                document.getElementById('g-success-rate').innerText = rate;
                document.getElementById('g-success-foot').innerText = `成功 ${{succReq}} 次 / 失败 ${{failReq}} 次`;
                document.getElementById('g-failover-count').innerText = (g.failover_events || 0) + (g.tier_fallback_events || 0);
                document.getElementById('g-avg-latency').innerText = avgLat;

                // Harness 统计
                const h = d.harness || {{}};
                const hReq = h.total_requests || 0;
                const hSucc = h.success_requests || 0;
                const hFail = h.failed_requests || 0;
                const hRate = hReq > 0 ? ((hSucc / hReq) * 100).toFixed(1) + '%' : '100%';
                const hLat = hSucc > 0 ? Math.round((h.total_latency_sum || 0) / hSucc) + 'ms' : '0ms';

                document.getElementById('ov-harness-req').innerText = hReq;
                document.getElementById('ov-harness-rate').innerText = hRate;
                document.getElementById('ov-harness-lat').innerText = hLat;

                document.getElementById('h-total-req').innerText = hReq;
                document.getElementById('h-success-rate').innerText = hRate;
                document.getElementById('h-success-foot').innerText = `成功 ${{hSucc}} / 失败 ${{hFail}}`;
                document.getElementById('h-failover-count').innerText = (h.failover_events || 0);
                document.getElementById('h-avg-latency').innerText = hLat;

                // Codex 统计
                const c = d.codex || {{}};
                const cReq = c.total_requests || 0;
                const cSucc = c.success_requests || 0;
                const cRate = cReq > 0 ? ((cSucc / cReq) * 100).toFixed(1) + '%' : '100%';
                const cTools = c.tool_calls_total || 0;
                const cPatch = c.tool_apply_patch || 0;
                const cExec = c.tool_exec_command || 0;
                const cOther = Math.max(0, cTools - cPatch - cExec);

                document.getElementById('ov-codex-req').innerText = cReq;
                document.getElementById('ov-codex-tools').innerText = cTools;
                document.getElementById('ov-codex-rate').innerText = cRate;

                document.getElementById('c-total-req').innerText = cReq;
                document.getElementById('c-total-tools').innerText = cTools;
                document.getElementById('c-apply-patch').innerText = cPatch;
                document.getElementById('c-exec-cmd').innerText = cExec;

                document.getElementById('pill-apply-patch').innerText = cPatch;
                document.getElementById('pill-exec-cmd').innerText = cExec;
                document.getElementById('pill-other-tools').innerText = cOther;

            }} catch (e) {{
                console.error("fetchStats error:", e);
            }}
        }}

        async function fetchLogs() {{
            try {{
                const channel = activeTab === 'overview' ? 'all' : activeTab;
                const res = await fetch(`/api/logs?channel=${{channel}}`);
                if (!res.ok) return;
                const logs = await res.json();
                
                const containerId = activeTab === 'overview' ? 'overview-log-stream' 
                                  : activeTab === 'harness' ? 'harness-log-stream' 
                                  : 'codex-log-stream';
                const el = document.getElementById(containerId);
                if (!el) return;

                if (!logs || logs.length === 0) {{
                    el.innerHTML = '<div style="color:var(--text-tertiary);text-align:center;padding:20px;">暂无日志记录</div>';
                    return;
                }}

                el.innerHTML = logs.slice(-50).reverse().map(l => {{
                    const isOk = l.status < 400;
                    const statusColor = isOk ? 'var(--accent-emerald)' : 'var(--accent-rose)';
                    const chBadge = l.channel === 'codex' 
                        ? '<span class="badge badge-codex">CODEX</span>' 
                        : '<span class="badge badge-harness">HARNESS</span>';
                    const toolsInfo = l.tool_calls ? `<span style="color:var(--accent-cyan);">[Tools: ${{l.tool_calls}}]</span>` : '';
                    return `
                        <div class="log-item">
                            <span class="log-time">${{l.time || ''}}</span>
                            ${{chBadge}}
                            <span style="color:${{statusColor}};font-weight:600;">${{l.status}}</span>
                            <span style="color:var(--text-primary);font-weight:500;">${{l.method}} ${{l.path}}</span>
                            <span style="color:#818cf8;">${{l.model || ''}}</span>
                            <span style="color:var(--text-tertiary);">→ ${{l.provider || ''}}</span>
                            <span style="color:var(--accent-amber);">${{l.latency || 0}}ms</span>
                            ${{toolsInfo}}
                        </div>
                    `;
                }}).join('');
            }} catch (e) {{
                console.error("fetchLogs error:", e);
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
                const res = await fetch(`/api/config/${{channel}}`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ content: content }})
                }});
                const d = await res.json();
                if (res.ok) {{
                    showToast(d.message || "配置已保存并即时热重载！");
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

        async function toggleProvider(name, enabled) {{
            try {{
                const res = await fetch('/api/providers/toggle', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name, enabled: enabled, channel: 'both' }})
                }});
                if (res.ok) {{
                    showToast(`渠道 [${{name}}] 状态已设为: ${{enabled ? '启用' : '禁用'}}`);
                }}
            }} catch (e) {{
                showToast("切换失败: " + e.message);
            }}
        }}

        async function updateKey(name) {{
            const input = document.getElementById(`key-${{name}}`);
            if (!input) return;
            const key = input.value.trim();
            try {{
                const res = await fetch('/api/providers/update_key', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name, api_key: key, channel: 'both' }})
                }});
                if (res.ok) {{
                    showToast(`渠道 [${{name}}] API Key 已更新`);
                }}
            }} catch (e) {{
                showToast("更新失败: " + e.message);
            }}
        }}

        async function testProviderLatency(name) {{
            const latEl = document.getElementById(`lat-${{name}}`);
            if (latEl) latEl.innerText = '测试中...';
            try {{
                const res = await fetch('/api/providers/test', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name, channel: 'both' }})
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

        async function deleteProvider(name) {{
            if (!confirm(`确定要从双轨配置中删除渠道 [${{name}}] 吗？`)) return;
            try {{
                const res = await fetch('/api/providers/delete', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ name: name, channel: 'both' }})
                }});
                if (res.ok) {{
                    showToast(`渠道 [${{name}}] 已成功删除`);
                    setTimeout(() => location.reload(), 800);
                }}
            }} catch (e) {{
                showToast("删除失败: " + e.message);
            }}
        }}

        async function enableAllProviders() {{
            const checkboxes = document.querySelectorAll('#providers-table-body input[type="checkbox"]');
            for (let cb of checkboxes) {{
                if (!cb.checked) {{
                    cb.checked = true;
                    cb.dispatchEvent(new Event('change'));
                }}
            }}
            showToast("已批量请求启用所有渠道！");
        }}

        async function clearLogs() {{
            try {{
                await fetch('/api/logs/clear', {{ method: 'POST' }});
                fetchLogs();
                showToast("实时日志已清空");
            }} catch (e) {{}}
        }}

        function refreshActiveTab() {{
            fetchStats();
            fetchLogs();
        }}

        // 初始化
        renderProviders(initialProviders);
        fetchStats();
        fetchLogs();
        setInterval(fetchStats, 3000);
        setInterval(fetchLogs, 3000);
    </script>
</body>
</html>"""
