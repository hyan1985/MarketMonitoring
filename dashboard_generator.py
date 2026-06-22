import json
import os
import sys

class DashboardGenerator:
    def __init__(self, data_path="/Users/hyan/Desktop/词频情绪/data.json", config_path="/Users/hyan/Desktop/词频情绪/config.json"):
        self.data_path = data_path
        self.config_path = config_path

    def load_data(self):
        """Load analyzed data from data.json"""
        if not os.path.exists(self.data_path):
            print(f"  [Generator] Error: Data file not found at {self.data_path}", file=sys.stderr)
            return None
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  [Generator] Error reading data: {e}", file=sys.stderr)
            return None

    def load_config(self):
        """Load configuration from config.json"""
        if not os.path.exists(self.config_path):
            print(f"  [Generator] Error: Config file not found at {self.config_path}", file=sys.stderr)
            return None
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  [Generator] Error reading config: {e}", file=sys.stderr)
            return None

    def generate_html(self, output_path="/Users/hyan/Desktop/词频情绪/index.html"):
        """Generate a stunning, fully interactive single-page dashboard HTML"""
        data = self.load_data()
        config = self.load_config()
        
        if not data or not config:
            print("  [Generator] Error: Required data or config is missing. HTML generation aborted.", file=sys.stderr)
            return False

        risk = data.get("risk")  # TuShare risk score (optional)

        source_labels = {"eastmoney": "东财股吧", "xueqiu": "雪球", "ths": "同花顺"}
        posts_for_sources = data.get("posts", [])
        actual_sources = sorted({p.get("source", "eastmoney") for p in posts_for_sources})
        if actual_sources:
            sources_text = " + ".join(source_labels.get(s, s) for s in actual_sources)
        else:
            enabled = [source_labels[k] for k, v in (config.get("sources") or {}).items() if v]
            sources_text = " + ".join(enabled) if enabled else "东财股吧"

        conc_value = None
        if risk:
            conc_value = risk.get("dimensions", {}).get("concentration", {}).get("value")
        conc_display = f"{conc_value}" if conc_value is not None else "—"
        conc_unit = "%" if conc_value is not None else ""
        risk_trade_date = (risk or {}).get("trade_date", "")

        # Prepare lexicon for client-side simulator
        bullish_lexicon_json = json.dumps(config.get("bullish_words", []))
        bearish_lexicon_json = json.dumps(config.get("bearish_words", []))
        negation_lexicon_json = json.dumps(config.get("negation_words", []))
        
        # Prepare charts data
        scan_date = (data.get("summary") or {}).get("scan_date", "")
        hourly_all = data.get("hourly_trends", [])
        # Hourly: only today's buckets (avoid merging many days under duplicate "14:00" labels)
        if scan_date:
            hourly_trends = [h for h in hourly_all if (h.get("time") or "").startswith(scan_date)]
        else:
            hourly_trends = hourly_all[-24:] if len(hourly_all) > 24 else hourly_all

        hourly_labels = []
        hourly_tooltips = []
        for item in hourly_trends:
            time_str = item.get("time", "")
            hourly_tooltips.append(time_str)
            if " " in time_str:
                date_part, hour_part = time_str.split(" ", 1)
                try:
                    _, m, d = date_part.split("-")
                    hourly_labels.append(f"{int(m)}/{int(d)} {hour_part}")
                except Exception:
                    hourly_labels.append(hour_part)
            else:
                hourly_labels.append(time_str)
        hourly_scores = [item["sentiment_score"] for item in hourly_trends]

        # Daily: last 14 run-days for readable trend (not sparse multi-week gaps)
        daily_trends = data.get("daily_trends", [])[-14:]
        daily_labels = []
        daily_tooltips = []
        for item in daily_trends:
            date_str = item.get("date", "")
            daily_tooltips.append(date_str)
            try:
                _, month, day = date_str.split("-")
                daily_labels.append(f"{int(month)}月{int(day)}日")
            except Exception:
                daily_labels.append(date_str)
        daily_scores = [item["sentiment_score"] for item in daily_trends]
        
        bullish_words_labels = [item["word"] for item in data.get("top_bullish_words", [])]
        bullish_words_counts = [item["count"] for item in data.get("top_bullish_words", [])]
        
        bearish_words_labels = [item["word"] for item in data.get("top_bearish_words", [])]
        bearish_words_counts = [item["count"] for item in data.get("top_bearish_words", [])]

        html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>大A情绪分参考 Dashboard</title>
    <!-- Tailwind CSS for layout utilities -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Google Fonts: Outfit & Inter -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- Chart.js for premium graphics -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <!-- wordcloud2.js for word cloud -->
    <script src="https://cdn.jsdelivr.net/npm/wordcloud@1.2.2/src/wordcloud2.js"></script>
    <!-- FontAwesome for icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #0b0f19;
            color: #f3f4f6;
            background-image: 
                radial-gradient(at 0% 0%, rgba(17, 24, 39, 0.9) 0, transparent 50%),
                radial-gradient(at 50% 0%, rgba(13, 148, 136, 0.08) 0, transparent 50%),
                radial-gradient(at 100% 0%, rgba(239, 68, 68, 0.05) 0, transparent 50%);
            background-attachment: fixed;
        }}
        h1, h2, h3, .font-outfit {{
            font-family: 'Outfit', sans-serif;
        }}
        .glass-card {{
            background: rgba(18, 25, 41, 0.6);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        }}
        .glass-card-hover:hover {{
            border-color: rgba(255, 255, 255, 0.1);
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.5);
            transform: translateY(-2px);
            transition: all 0.3s ease;
        }}
        .bullish-glow {{
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.15);
        }}
        .bearish-glow {{
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.15);
        }}
        .text-bullish {{
            color: #10b981;
        }}
        .text-bearish {{
            color: #ef4444;
        }}
        .bg-bullish {{
            background-color: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }}
        .bg-bearish {{
            background-color: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }}
        /* Dial Gauge Styling — scales with screen width */
        .gauge-container {{
            --gauge-w: min(260px, calc(100vw - 3rem));
            position: relative;
            width: var(--gauge-w);
            height: calc(var(--gauge-w) * 0.5);
            overflow: hidden;
        }}
        .gauge-body {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 200%;
            border-radius: 50%;
            background: conic-gradient(
                #ef4444 0% 35%, 
                #6b7280 35% 65%, 
                #10b981 65% 100%
            );
            mask: radial-gradient(circle calc(var(--gauge-w) * 0.377) at 50% 50%, transparent 100%, #000 100%);
            -webkit-mask: radial-gradient(circle calc(var(--gauge-w) * 0.377) at 50% 50%, transparent 100%, #000 100%);
        }}
        .gauge-cover {{
            position: absolute;
            top: calc(var(--gauge-w) * 0.058);
            left: calc(var(--gauge-w) * 0.058);
            width: calc(var(--gauge-w) * 0.885);
            height: calc(var(--gauge-w) * 0.885);
            border-radius: 50%;
            background: #0d1220;
            border: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding-top: calc(var(--gauge-w) * 0.192);
        }}
        /* Mobile polish */
        @media (max-width: 639px) {{
            .mobile-card {{ padding: 1rem !important; }}
            .chart-scroll-hint::after {{
                content: '← 左右滑动查看更多 →';
                display: block;
                text-align: center;
                font-size: 10px;
                color: #6b7280;
                padding: 6px 0 2px;
            }}
        }}
        @supports (padding: env(safe-area-inset-bottom)) {{
            body {{
                padding-bottom: env(safe-area-inset-bottom);
            }}
        }}
        /* Custom scrollbar */
        ::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        ::-webkit-scrollbar-track {{
            background: rgba(18, 25, 41, 0.1);
        }}
        ::-webkit-scrollbar-thumb {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: rgba(255, 255, 255, 0.2);
        }}
    </style>
</head>
<body class="min-h-screen overflow-x-hidden px-3 sm:px-4 md:px-8 py-4 sm:py-6">

    <!-- Header -->
    <header class="max-w-7xl mx-auto mb-6 sm:mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div class="min-w-0">
            <div class="flex items-center gap-2.5 sm:gap-3">
                <div class="h-9 w-9 sm:h-10 sm:w-10 shrink-0 rounded-xl bg-gradient-to-tr from-teal-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-teal-500/10">
                    <i class="fa-solid fa-chart-line-up text-white text-lg sm:text-xl"></i>
                </div>
                <h1 class="text-xl sm:text-2xl md:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-teal-400 via-indigo-200 to-rose-400 bg-clip-text text-transparent leading-tight">
                    大A情绪分参考 Dashboard
                </h1>
            </div>
            <p class="text-gray-400 text-xs sm:text-sm mt-2 sm:mt-1 flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                <span>数据源：{sources_text}</span>
                <span class="hidden sm:inline text-gray-500">|</span>
                <span class="text-gray-500">统计日 {data["summary"].get("scan_date", data["summary"]["last_updated"][:10])}（北京时间）</span>
                <span class="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping"></span>
            </p>
        </div>
        <div class="glass-card mobile-card px-4 py-2.5 rounded-xl border border-gray-800 flex items-center gap-4 text-sm text-gray-300 w-full md:w-auto shrink-0">
            <div>
                <span class="text-gray-400 text-xs block">数据更新时间（北京时间）</span>
                <span class="font-mono text-teal-400 font-semibold">{data["summary"]["last_updated"]}</span>
            </div>
            <div class="border-l border-gray-800 h-8"></div>
            <div>
                <span class="text-gray-400 text-xs block">样本帖子数量</span>
                <span class="font-mono text-indigo-400 font-semibold">{data["summary"]["total_posts"]} 篇</span>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6 lg:items-stretch">

        <!-- Sentiment Score Card — 左侧跨两行，与右侧趋势图+词频图底对齐 -->
            <div class="glass-card mobile-card p-4 sm:p-6 rounded-2xl relative overflow-hidden lg:col-span-1 lg:row-span-2 lg:h-full" id="score-card">
                <div class="absolute -right-20 -top-20 w-40 h-40 rounded-full bg-emerald-500/5 blur-3xl" id="bg-glow"></div>
                <div class="relative z-10 w-full">
                    <div class="flex flex-col items-center text-center">
                        <h3 class="text-gray-400 text-xs font-semibold tracking-widest uppercase mb-5 flex items-center justify-center gap-2 w-full">
                            <i class="fa-solid fa-gauge-high text-teal-500"></i> 大盘情绪指数
                        </h3>
                        <div class="gauge-container mb-5">
                            <div class="gauge-body"></div>
                            <div class="gauge-cover">
                                <span class="text-4xl sm:text-5xl font-extrabold tracking-tight text-white font-outfit" id="score-number">{data["summary"]["overall_weighted_score"]}</span>
                                <span class="text-xs text-gray-500 mt-1 font-mono">[-1.0, 1.0]</span>
                            </div>
                        </div>
                        <div class="text-center py-3.5 px-4 rounded-xl transition-all duration-500 mb-5 w-full" id="recommendation-box">
                            <span class="text-xl font-bold font-outfit block mb-1" id="rec-label">Loading...</span>
                            <span class="text-xs leading-relaxed block" id="rec-details">Loading details...</span>
                        </div>
                    </div>
                    <div class="border-t border-gray-800/60 pt-4 mb-4">
                        <div class="flex justify-between items-center mb-3">
                            <h4 class="text-gray-500 text-xs font-semibold uppercase tracking-wider">帖子分类占比</h4>
                            <span class="text-gray-600 text-xs font-mono">{data["summary"]["total_posts"]} 篇</span>
                        </div>
                        <div class="grid grid-cols-3 gap-2.5 mb-3">
                            <div class="bg-emerald-500/8 border border-emerald-500/15 rounded-lg p-2.5 text-center">
                                <span class="text-2xl font-extrabold text-emerald-400 font-mono">{data["summary"]["bullish_posts"]}</span>
                                <span class="text-xs text-emerald-400/60 block mt-0.5">看多</span>
                            </div>
                            <div class="bg-gray-800/20 border border-gray-700/20 rounded-lg p-2.5 text-center">
                                <span class="text-2xl font-extrabold text-gray-300 font-mono">{data["summary"]["neutral_posts"]}</span>
                                <span class="text-xs text-gray-500 block mt-0.5">中性</span>
                            </div>
                            <div class="bg-red-500/8 border border-red-500/15 rounded-lg p-2.5 text-center">
                                <span class="text-2xl font-extrabold text-red-400 font-mono">{data["summary"]["bearish_posts"]}</span>
                                <span class="text-xs text-red-400/60 block mt-0.5">看空</span>
                            </div>
                        </div>
                        <div class="flex justify-between text-xs text-gray-500 mb-1.5 px-1">
                            <span>看多 ({(data["summary"]["bullish_posts"]/data["summary"]["total_posts"]*100):.0f}%)</span>
                            <span>看空 ({(data["summary"]["bearish_posts"]/data["summary"]["total_posts"]*100):.0f}%)</span>
                        </div>
                        <div class="h-2 w-full bg-gray-800/60 rounded-full overflow-hidden flex">
                            <div class="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-l-full" style="width: {(data["summary"]["bullish_posts"]/data["summary"]["total_posts"]*100):.1f}%"></div>
                            <div class="bg-gray-700/50 h-full" style="width: {(data["summary"]["neutral_posts"]/data["summary"]["total_posts"]*100):.1f}%"></div>
                            <div class="bg-gradient-to-r from-rose-500 to-red-500 h-full rounded-r-full" style="width: {(data["summary"]["bearish_posts"]/data["summary"]["total_posts"]*100):.1f}%"></div>
                        </div>
                    </div>
                    <div class="border-t border-gray-800/60 pt-4 text-xs">
                        <h4 class="text-gray-500 font-semibold uppercase tracking-wider mb-3">模型说明</h4>
                        <div class="space-y-2.5">
                            <div class="flex items-start gap-2 bg-emerald-500/5 border border-emerald-500/10 rounded-lg px-3 py-2">
                                <span class="text-emerald-400 font-bold mt-0.5 flex-shrink-0">&lt; -0.3</span>
                                <span class="text-gray-300 leading-relaxed"><span class="text-white font-semibold">极度恐慌 / 黄金买点</span><br>逆向建仓 +10%~+20%</span>
                            </div>
                            <div class="flex items-start gap-2 bg-gray-800/20 border border-gray-700/20 rounded-lg px-3 py-2">
                                <span class="text-gray-400 font-bold mt-0.5 flex-shrink-0">-0.3 ~ 0.5</span>
                                <span class="text-gray-300 leading-relaxed"><span class="text-white font-semibold">情绪中性 / 卧倒装死</span><br>维持底仓，持股不动</span>
                            </div>
                            <div class="flex items-start gap-2 bg-red-500/5 border border-red-500/10 rounded-lg px-3 py-2">
                                <span class="text-red-400 font-bold mt-0.5 flex-shrink-0">&gt; +0.5</span>
                                <span class="text-gray-300 leading-relaxed"><span class="text-white font-semibold">极度亢奋 / 防御警报</span><br>防守减仓 -10%~-20%</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

        <!-- Trend Chart Card (日线) -->
            <div class="glass-card mobile-card p-4 sm:p-6 rounded-2xl lg:col-span-2">
                <div class="flex items-center justify-between mb-2 gap-2">
                    <h3 class="text-white text-sm sm:text-base font-bold flex items-center gap-2">
                        <i class="fa-solid fa-chart-line text-teal-400"></i> 情绪日线趋势
                    </h3>
                    <span class="text-[10px] text-gray-600 font-mono shrink-0">历史日线</span>
                </div>
                <p class="text-xs text-gray-600 mb-3 sm:mb-4">按交易日累计，Y轴自适应缩放。</p>
                
                <div class="h-[200px] sm:h-[280px] relative w-full">
                    <canvas id="trend-chart"></canvas>
                    <p id="trend-chart-empty" class="hidden absolute inset-0 flex items-center justify-center text-sm text-gray-500">暂无趋势数据</p>
                </div>
            </div>

        <!-- Words Analysis Grid -->
            <div class="lg:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
                <!-- Bullish Words Chart -->
                <div class="glass-card mobile-card p-4 sm:p-5 rounded-2xl h-full flex flex-col">
                    <h3 class="text-emerald-400 text-xs sm:text-sm font-bold tracking-wider uppercase mb-3 sm:mb-4 flex items-center gap-2">
                        <i class="fa-solid fa-arrow-trend-up"></i> 活跃多头词频
                    </h3>
                    <div class="h-[150px] sm:h-[180px] w-full flex-1">
                        <canvas id="bullish-words-chart"></canvas>
                    </div>
                </div>
                <!-- Bearish Words Chart -->
                <div class="glass-card mobile-card p-4 sm:p-5 rounded-2xl h-full flex flex-col">
                    <h3 class="text-red-400 text-xs sm:text-sm font-bold tracking-wider uppercase mb-3 sm:mb-4 flex items-center gap-2">
                        <i class="fa-solid fa-arrow-trend-down"></i> 活跃空头词频
                    </h3>
                    <div class="h-[150px] sm:h-[180px] w-full flex-1">
                        <canvas id="bearish-words-chart"></canvas>
                    </div>
                </div>
            </div>

            <!-- Market Risk Score Card (TuShare 多维数据) -->
            {f'''            <div class="glass-card mobile-card p-4 sm:p-6 rounded-2xl lg:col-span-1 lg:h-full" id="risk-card">
                <h3 class="text-gray-400 text-xs sm:text-sm font-semibold tracking-wider uppercase mb-4 flex items-center gap-2">
                    <i class="fa-solid fa-triangle-exclamation text-amber-400"></i> 大盘风险值预估
                </h3>
                <div class="text-center mb-4">
                    <span class="text-4xl sm:text-5xl font-extrabold font-outfit text-white" id="risk-total">{risk["total_score"]}</span>
                    <span class="text-gray-500 text-sm ml-1">/ 100</span>
                </div>
                <div class="h-2.5 w-full bg-gray-800 rounded-full overflow-hidden mb-3">
                    <div class="h-full rounded-full transition-all duration-700" id="risk-bar"
                         style="width:{risk["total_score"]}%;
                                background:{f"#ef4444" if risk["total_score"] >= 70 else "#f59e0b" if risk["total_score"] >= 50 else "#10b981" if risk["total_score"] >= 30 else "#6ee7b7"};">
                    </div>
                </div>
                <div class="text-center mb-4">
                    <span class="px-3 py-1 rounded-full text-sm font-semibold" id="risk-level"
                          style="background:{f"#ef444433" if risk["total_score"] >= 70 else "#f59e0b33" if risk["total_score"] >= 50 else "#10b98133" if risk["total_score"] >= 30 else "#6ee7b733"};
                                 color:{f"#fca5a5" if risk["total_score"] >= 70 else "#fde68a" if risk["total_score"] >= 50 else "#6ee7b7" if risk["total_score"] >= 30 else "#a7f3d0"};">
                        {risk["level"]}
                    </span>
                </div>
                <p class="text-xs text-gray-400 text-center leading-relaxed mb-1">{risk["advice"]}</p>
                {f'<p class="text-[10px] text-gray-600 text-center mb-2">行情数据日 {risk_trade_date}（北京时间）</p>' if risk_trade_date else ''}
                <!-- 资金集中度 → 大号突出 -->
                <div class="mt-3 p-3 rounded-xl bg-gradient-to-br from-amber-500/10 to-amber-500/5 border border-amber-500/20 text-center">
                    <span class="text-[10px] text-amber-400/70 uppercase tracking-wider">核心指标 · 前5%成交占比</span>
                    <div class="text-4xl font-extrabold font-mono text-amber-300 mt-1">{conc_display}<span class="text-lg text-amber-400/60">{conc_unit}</span></div>
                    <span class="text-[10px] text-amber-400/40 mt-0.5 block">历史极值 52.1% · 当前 {risk["dimensions"]["concentration"]["score"]} 分</span>
                </div>
                <!-- 其他维度 -->
                <div class="mt-3 space-y-1.5">
                    ''' + "".join(
                        f'''                    <div>
                        <div class="flex justify-between text-xs text-gray-400 mb-0.5">
                            <span>{d["label"]}</span>
                            <span class="font-mono">{d["score"]}分</span>
                        </div>
                        <div class="h-1.5 w-full bg-gray-800 rounded-full overflow-hidden">
                            <div class="h-full rounded-full" style="width:{d["score"] / 20 * 100}%;
                                background:{("#ef4444" if d["score"] >= 16 else "#f59e0b" if d["score"] >= 10 else "#10b981")};">
                            </div>
                        </div>
                    </div>
                    ''' for d in risk["dimensions"].values()
                    ) + '''                </div>
            </div>
            ''' if risk else '''            <div class="glass-card mobile-card p-4 sm:p-6 rounded-2xl text-center lg:col-span-1 lg:h-full">
                <span class="text-gray-500 text-sm">大盘风险值暂未计算 (需 TuShare API)</span>
            </div>
            '''}

        <!-- Word Cloud — 与左侧风险卡片同行等高 -->
            <div class="glass-card mobile-card p-4 sm:p-6 rounded-2xl lg:col-span-2 lg:h-full flex flex-col">
                <div class="flex items-center justify-between mb-3 sm:mb-4 flex-wrap gap-3">
                    <h3 class="text-white text-sm sm:text-base font-bold flex items-center gap-2">
                        <i class="fa-solid fa-cloud text-indigo-400"></i> 词频云图
                    </h3>
                    <div class="flex bg-gray-800/80 p-0.5 rounded-lg border border-gray-700/50">
                        <button onclick="setWordCloudMode('all')" id="btn-wc-all" class="px-3 py-1.5 sm:px-3.5 sm:py-1 text-xs rounded-md font-semibold transition-all bg-indigo-600 text-white shadow">
                            全部
                        </button>
                        <button onclick="setWordCloudMode('bullish')" id="btn-wc-bullish" class="px-3 py-1.5 sm:px-3.5 sm:py-1 text-xs rounded-md font-semibold transition-all text-gray-400 hover:text-white">
                            多头
                        </button>
                        <button onclick="setWordCloudMode('bearish')" id="btn-wc-bearish" class="px-3 py-1.5 sm:px-3.5 sm:py-1 text-xs rounded-md font-semibold transition-all text-gray-400 hover:text-white">
                            空头
                        </button>
                    </div>
                </div>
                <p class="text-xs text-gray-400 mb-3">词越大代表出现越频繁。云图基于当日样本的多头/空头词库匹配统计。</p>
                <div class="w-full flex-1 min-h-[200px] sm:min-h-[260px] bg-gray-950/30 border border-gray-800 rounded-xl overflow-hidden flex items-center justify-center">
                    <canvas id="wordcloud-canvas" class="w-full h-full"></canvas>
                </div>
            </div>

        <!-- Full Width: Real-time Sentiment Simulator -->
        <section class="lg:col-span-3">
            <div class="glass-card mobile-card p-4 sm:p-6 rounded-2xl relative overflow-hidden">
                <div class="absolute -right-20 -bottom-20 w-40 h-40 rounded-full bg-indigo-500/5 blur-3xl"></div>
                
                <h3 class="text-white text-base font-bold mb-4 flex items-center gap-2">
                    <i class="fa-solid fa-bolt text-amber-400"></i> 大A情绪分模拟测试器 (Real-time Simulator)
                </h3>
                
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div class="lg:col-span-2">
                        <p class="text-sm text-gray-400 mb-2">输入任意炒股话语、股评或讨论内容，实时体验分词匹配与大A情绪打分计算：</p>
                        <textarea id="simulator-input" rows="4" class="w-full bg-gray-950/80 border border-gray-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-white font-sans" placeholder="例如：今天主力太猛了，满仓大干一场，直接起飞，冲涨停！"></textarea>
                        <div class="mt-3 flex justify-between items-center flex-wrap gap-2">
                            <span class="text-xs text-gray-500 font-mono">Lexicon Version: 1.0 (Loaded Locally)</span>
                            <button onclick="runSimulation()" class="bg-gradient-to-r from-teal-500 to-indigo-600 hover:from-teal-600 hover:to-indigo-700 text-white font-bold text-sm px-6 py-2.5 rounded-xl shadow-lg shadow-teal-500/10 hover:shadow-teal-500/20 active:scale-95 transition-all flex items-center gap-2">
                                <i class="fa-solid fa-calculator"></i> 立即运行模拟计算
                            </button>
                        </div>
                    </div>
                    
                    <div class="lg:col-span-1 bg-gray-950/40 border border-gray-900 rounded-xl p-5 flex flex-col justify-between" id="sim-result-box">
                        <div class="text-center py-4 border-b border-gray-900 mb-3">
                            <span class="text-xs text-gray-500 block mb-1 uppercase tracking-wider">模拟打分结果</span>
                            <span class="text-4xl font-extrabold text-gray-400 font-outfit" id="sim-score">0.00</span>
                            <span class="text-xs text-gray-500 block mt-1" id="sim-verdict">等待输入计算...</span>
                        </div>
                        <div class="space-y-2 text-xs">
                            <div class="flex justify-between items-center">
                                <span class="text-emerald-400 font-semibold"><i class="fa-solid fa-plus-circle"></i> 匹配多头词 ({len(bullish_words_labels)}个词库)</span>
                                <span class="bg-emerald-500/10 px-2 py-0.5 rounded font-mono text-emerald-400 font-bold" id="sim-pos-count">0</span>
                            </div>
                            <div class="text-gray-400 bg-gray-950/80 px-2.5 py-1.5 rounded min-h-[32px] max-h-[50px] overflow-y-auto break-all font-mono" id="sim-pos-list">-</div>
                            
                            <div class="flex justify-between items-center">
                                <span class="text-red-400 font-semibold"><i class="fa-solid fa-minus-circle"></i> 匹配空头词 ({len(bearish_words_labels)}个词库)</span>
                                <span class="bg-red-500/10 px-2 py-0.5 rounded font-mono text-red-400 font-bold" id="sim-neg-count">0</span>
                            </div>
                            <div class="text-gray-400 bg-gray-950/80 px-2.5 py-1.5 rounded min-h-[32px] max-h-[50px] overflow-y-auto break-all font-mono" id="sim-neg-list">-</div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- Full Width: Scraped Posts Database Table -->
        <section class="lg:col-span-3">
            <div class="glass-card rounded-2xl overflow-hidden">
                
                <!-- Table Controls -->
                <div class="p-6 border-b border-gray-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <h3 class="text-white text-base font-bold flex items-center gap-2">
                            <i class="fa-solid fa-database text-teal-400"></i> Guba 实时解析帖子库
                        </h3>
                        <p class="text-xs text-gray-400 mt-1">您可以筛选、搜索以及排序获取到的情绪样本帖子明细。</p>
                    </div>
                    
                    <div class="flex flex-col sm:flex-row gap-3 items-stretch md:items-center">
                        <!-- Search bar -->
                        <div class="relative">
                            <i class="fa-solid fa-search absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500 text-sm"></i>
                            <input type="text" id="post-search" oninput="filterAndRenderTable()" class="bg-gray-950/80 border border-gray-800 rounded-xl pl-9 pr-4 py-2 text-xs focus:outline-none focus:border-indigo-500 text-white w-full sm:w-48 placeholder-gray-500" placeholder="搜索标题或内容...">
                        </div>
                        
                        <!-- Filter select -->
                        <select id="post-filter-type" onchange="filterAndRenderTable()" class="bg-gray-950/80 border border-gray-800 rounded-xl px-3 py-2 text-xs text-gray-300 focus:outline-none focus:border-indigo-500">
                            <option value="all">全部帖子</option>
                            <option value="bullish">看多帖子 (Score &gt; 0)</option>
                            <option value="bearish">看空帖子 (Score &lt; 0)</option>
                            <option value="neutral">中性帖子 (Score = 0)</option>
                        </select>
                        
                        <!-- Sort select -->
                        <select id="post-sort-by" onchange="filterAndRenderTable()" class="bg-gray-950/80 border border-gray-800 rounded-xl px-3 py-2 text-xs text-gray-300 focus:outline-none focus:border-indigo-500">
                            <option value="time-desc">发布时间 (最新)</option>
                            <option value="read-desc">阅读量 (由高到低)</option>
                            <option value="reply-desc">评论量 (由高到低)</option>
                            <option value="score-desc">情绪值 (看多优先)</option>
                            <option value="score-asc">情绪值 (看空优先)</option>
                        </select>
                    </div>
                </div>

                <!-- Table Content Container -->
                <div class="overflow-x-auto max-h-[360px] sm:max-h-[480px] chart-scroll-hint">
                    <table class="w-full text-left text-sm border-collapse min-w-[320px]">
                        <thead>
                            <tr class="bg-gray-950/30 text-gray-400 border-b border-gray-800 font-semibold text-xs tracking-wider">
                                <th class="py-3 px-3 sm:px-6 w-20 hidden sm:table-cell">阅读</th>
                                <th class="py-3 px-3 sm:px-4 w-20 hidden sm:table-cell">评论</th>
                                <th class="py-3 px-3 sm:px-4">帖子标题</th>
                                <th class="py-3 px-3 sm:px-4 w-16 hidden md:table-cell">来源</th>
                                <th class="py-3 px-3 sm:px-4 w-32 hidden sm:table-cell">情绪匹配</th>
                                <th class="py-3 px-3 sm:px-4 w-20 sm:w-24 text-center">得分</th>
                                <th class="py-3 px-3 sm:px-4 w-24 hidden md:table-cell">作者</th>
                                <th class="py-3 px-3 sm:px-6 w-28 sm:w-32">时间</th>
                            </tr>
                        </thead>
                        <tbody id="posts-table-body" class="divide-y divide-gray-800/40">
                            <!-- Table Rows will be rendered dynamically by JavaScript -->
                        </tbody>
                    </table>
                </div>
                
                <!-- Table Footer/Stats -->
                <div class="px-4 sm:px-6 py-3 sm:py-4 border-t border-gray-800 bg-gray-950/20 text-xs text-gray-500 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-1">
                    <span id="showing-posts-count">Showing 0 of 0 posts</span>
                    <span class="hidden sm:inline">点击帖子标题可跳转至原平台讨论页 ↗</span>
                </div>
                
            </div>
        </section>

    </main>

    <footer class="max-w-7xl mx-auto mt-12 mb-6 text-center text-xs text-gray-500 border-t border-gray-900 pt-6">
        <p>大A情绪分参考工具 © 2026. 基于知乎情绪模型逆向指标公式构建.</p>
        <p class="mt-1">入市有风险，投资需谨慎。本工具仅为情绪因子回测与展示，不构成任何实质性买卖操作建议。</p>
    </footer>

    <!-- EMBEDDED DATA & CODE -->
    <script>
        // Inject data from generator
        const rawPosts = {json.dumps(data["posts"])};
        const bullishLexicon = {bullish_lexicon_json};
        const bearishLexicon = {bearish_lexicon_json};
        const negationLexicon = {negation_lexicon_json};
        
        // Setup Score Gauge Animation
        const score = {data["summary"]["overall_weighted_score"]};
        
        function initGauge() {{
            const card = document.getElementById("score-card");
            const bgGlow = document.getElementById("bg-glow");
            const recBox = document.getElementById("recommendation-box");
            const recLabel = document.getElementById("rec-label");
            const recDetails = document.getElementById("rec-details");
            
            // Determine styling & recommendations based on thresholds
            if (score <= -0.3) {{
                // Panicked Market (Bullish Contarian action)
                card.style.boxShadow = "0 0 20px rgba(16, 185, 129, 0.2)";
                bgGlow.className = "absolute -right-20 -top-20 w-40 h-40 rounded-full bg-emerald-500/10 blur-3xl";
                
                recBox.className = "w-full text-center py-4 px-5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 bullish-glow";
                recLabel.innerHTML = `<i class="fa-solid fa-circle-arrow-up"></i> 极度悲观 / 黄金买点`;
                recDetails.textContent = "建议逐步逆向建仓，加仓 +10% ~ +20% 优质筹码。";
            }} else if (score >= 0.5) {{
                // Greedy Market (Bearish Contrarian action)
                card.style.boxShadow = "0 0 20px rgba(239, 68, 68, 0.2)";
                bgGlow.className = "absolute -right-20 -top-20 w-40 h-40 rounded-full bg-rose-500/10 blur-3xl";
                
                recBox.className = "w-full text-center py-4 px-5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-red-400 bearish-glow";
                recLabel.innerHTML = `<i class="fa-solid fa-circle-arrow-down"></i> 极度乐观 / 防御警报`;
                recDetails.textContent = "市场风险极高，注意保护利润，建议防守防御，减仓 -10% ~ -20% 并收缩战线。";
            }} else {{
                // Neutral
                card.style.boxShadow = "0 0 20px rgba(99, 102, 241, 0.15)";
                bgGlow.className = "absolute -right-20 -top-20 w-40 h-40 rounded-full bg-indigo-500/10 blur-3xl";
                
                recBox.className = "w-full text-center py-4 px-5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-300";
                recLabel.innerHTML = `<i class="fa-solid fa-circle-pause"></i> 情绪中性 / 卧倒装死`;
                recDetails.textContent = "市场为情绪波动噪音，维持当前核心底仓策略不变，持股不动。";
            }}
        }}

        // Setup Charts — daily only
        let trendChartObj = null;

        function calcYAxisRange(scores) {{
            if (!scores || scores.length === 0) {{
                return {{ min: -1, max: 1 }};
            }}
            let mn = Math.min.apply(null, scores);
            let mx = Math.max.apply(null, scores);
            if (mn === mx) {{
                const pad = 0.08;
                return {{
                    min: Math.max(-1, mn - pad),
                    max: Math.min(1, mx + pad)
                }};
            }}
            const span = mx - mn;
            const pad = Math.max(span * 0.2, 0.03);
            return {{
                min: Math.max(-1, mn - pad),
                max: Math.min(1, mx + pad)
            }};
        }}
        
        const chartData = {{
            hourly: {{
                labels: {json.dumps(hourly_labels)},
                tooltips: {json.dumps(hourly_tooltips)},
                scores: {json.dumps(hourly_scores)}
            }},
            daily: {{
                labels: {json.dumps(daily_labels)},
                tooltips: {json.dumps(daily_tooltips)},
                scores: {json.dumps(daily_scores)}
            }}
        }};

        function renderTrendChart() {{
            const canvas = document.getElementById('trend-chart');
            const emptyEl = document.getElementById('trend-chart-empty');
            const dataSet = chartData.daily;
            const scores = dataSet.scores || [];
            const labels = dataSet.labels || [];

            if (!scores.length || scores.length !== labels.length) {{
                if (trendChartObj) {{
                    trendChartObj.destroy();
                    trendChartObj = null;
                }}
                canvas.style.display = 'none';
                if (emptyEl) emptyEl.classList.remove('hidden');
                return;
            }}

            canvas.style.display = 'block';
            if (emptyEl) emptyEl.classList.add('hidden');

            const ctx = canvas.getContext('2d');
            if (trendChartObj) {{
                trendChartObj.destroy();
            }}

            const yRange = calcYAxisRange(scores);
            const gradient = ctx.createLinearGradient(0, 0, 0, 260);
            gradient.addColorStop(0, 'rgba(99, 102, 241, 0.35)');
            gradient.addColorStop(0.5, 'rgba(99, 102, 241, 0.05)');
            gradient.addColorStop(1, 'rgba(11, 15, 25, 0)');

            const pointCount = scores.length;
            trendChartObj = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: '情绪得分',
                        data: scores,
                        borderColor: '#6366f1',
                        borderWidth: 2,
                        pointBackgroundColor: '#818cf8',
                        pointBorderColor: '#0b0f19',
                        pointHoverRadius: 7,
                        pointRadius: pointCount <= 14 ? 5 : 3,
                        fill: true,
                        backgroundColor: gradient,
                        tension: 0.25,
                        spanGaps: true
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: false }},
                        tooltip: {{
                            callbacks: {{
                                title: function(items) {{
                                    if (!items || !items.length) return '';
                                    const idx = items[0].dataIndex;
                                    const tooltips = dataSet.tooltips || [];
                                    if (tooltips[idx]) return tooltips[idx];
                                    return labels[idx] || '';
                                }},
                                label: function(item) {{
                                    return '情绪得分: ' + item.formattedValue;
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        y: {{
                            min: yRange.min,
                            max: yRange.max,
                            grid: {{ color: 'rgba(255,255,255,0.03)' }},
                            ticks: {{ color: '#9ca3af', font: {{ family: 'monospace' }} }}
                        }},
                        x: {{
                            type: 'category',
                            grid: {{ display: false }},
                            ticks: {{ 
                                color: '#9ca3af', 
                                maxRotation: 45,
                                font: {{ size: 9 }},
                                autoSkip: true,
                                maxTicksLimit: 14
                            }}
                        }}
                    }}
                }}
            }});
        }}

        function renderWordCharts() {{
            const bullCtx = document.getElementById('bullish-words-chart').getContext('2d');
            const bearCtx = document.getElementById('bearish-words-chart').getContext('2d');
            
            new Chart(bullCtx, {{
                type: 'bar',
                data: {{
                    labels: {json.dumps(bullish_words_labels)},
                    datasets: [{{
                        data: {json.dumps(bullish_words_counts)},
                        backgroundColor: 'rgba(16, 185, 129, 0.75)',
                        borderColor: '#10b981',
                        borderWidth: 1,
                        borderRadius: 4
                    }}]
                }},
                options: {{
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ grid: {{ display: false }}, ticks: {{ color: '#9ca3af', stepSize: 1, font: {{ family: 'monospace' }} }} }},
                        y: {{ ticks: {{ color: '#e5e7eb', font: {{ size: 10, weight: 'bold' }} }} }}
                    }}
                }}
            }});
            
            new Chart(bearCtx, {{
                type: 'bar',
                data: {{
                    labels: {json.dumps(bearish_words_labels)},
                    datasets: [{{
                        data: {json.dumps(bearish_words_counts)},
                        backgroundColor: 'rgba(239, 68, 68, 0.75)',
                        borderColor: '#ef4444',
                        borderWidth: 1,
                        borderRadius: 4
                    }}]
                }},
                options: {{
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ grid: {{ display: false }}, ticks: {{ color: '#9ca3af', stepSize: 1, font: {{ family: 'monospace' }} }} }},
                        y: {{ ticks: {{ color: '#e5e7eb', font: {{ size: 10, weight: 'bold' }} }} }}
                    }}
                }}
            }});
        }}

        // Word Cloud (wordcloud2.js)
        const bullishWordItems = {json.dumps(data.get("top_bullish_words", []))};
        const bearishWordItems = {json.dumps(data.get("top_bearish_words", []))};
        let currentWordCloudMode = 'all';

        function buildWordCloudList(mode) {{
            const list = [];
            const pushItems = (items, polarity) => {{
                items.forEach(it => {{
                    if (!it || !it.word) return;
                    const weight = Number(it.count || 0);
                    if (!weight) return;
                    list.push([it.word, weight, polarity]);
                }});
            }};
            if (mode === 'bullish') {{
                pushItems(bullishWordItems, 'bullish');
            }} else if (mode === 'bearish') {{
                pushItems(bearishWordItems, 'bearish');
            }} else {{
                pushItems(bullishWordItems, 'bullish');
                pushItems(bearishWordItems, 'bearish');
            }}
            return list;
        }}

        function renderWordCloud() {{
            const canvas = document.getElementById('wordcloud-canvas');
            if (!canvas || typeof WordCloud === 'undefined') return;

            // Fit canvas to container for crisp rendering
            const container = canvas.parentElement;
            const dpr = window.devicePixelRatio || 1;
            const w = Math.max(320, container.clientWidth);
            const h = Math.max(220, container.clientHeight);
            canvas.width = Math.floor(w * dpr);
            canvas.height = Math.floor(h * dpr);
            canvas.style.width = w + 'px';
            canvas.style.height = h + 'px';

            const list = buildWordCloudList(currentWordCloudMode);
            const maxWeight = Math.max(...list.map(x => x[1]), 1);

            WordCloud(canvas, {{
                list: list.map(x => [x[0], x[1]]),
                gridSize: Math.round(8 * dpr),
                weightFactor: (size) => {{
                    // Normalize weights → font px
                    const normalized = size / maxWeight;
                    return Math.max(10, Math.round((12 + normalized * 42) * dpr));
                }},
                minSize: 10,
                fontFamily: 'Outfit, Inter, sans-serif',
                color: (word) => {{
                    // Color by polarity when in mixed mode
                    const item = list.find(x => x[0] === word);
                    const pol = item ? item[2] : 'neutral';
                    if (pol === 'bullish') return 'rgba(16, 185, 129, 0.95)';
                    if (pol === 'bearish') return 'rgba(239, 68, 68, 0.95)';
                    return 'rgba(156, 163, 175, 0.9)';
                }},
                rotateRatio: 0.12,
                rotationSteps: 2,
                minRotation: 0,
                maxRotation: Math.PI / 2,
                backgroundColor: 'rgba(0,0,0,0)',
                drawOutOfBound: false,
                shrinkToFit: true,
            }});
        }}

        function setWordCloudMode(mode) {{
            currentWordCloudMode = mode;
            const btnAll = document.getElementById('btn-wc-all');
            const btnBull = document.getElementById('btn-wc-bullish');
            const btnBear = document.getElementById('btn-wc-bearish');
            const active = "px-3.5 py-1 text-xs rounded-md font-semibold transition-all bg-indigo-600 text-white shadow";
            const inactive = "px-3.5 py-1 text-xs rounded-md font-semibold transition-all text-gray-400 hover:text-white";
            btnAll.className = (mode === 'all') ? active : inactive;
            btnBull.className = (mode === 'bullish') ? active : inactive;
            btnBear.className = (mode === 'bearish') ? active : inactive;
            renderWordCloud();
        }}

        // Simulator Code (Client Side parsing with negation context flipping)
        function runSimulation() {{
            const text = document.getElementById("simulator-input").value.trim();
            const resBox = document.getElementById("sim-result-box");
            const scoreLabel = document.getElementById("sim-score");
            const verdictLabel = document.getElementById("sim-verdict");
            const posListLabel = document.getElementById("sim-pos-list");
            const negListLabel = document.getElementById("sim-neg-list");
            const posCountLabel = document.getElementById("sim-pos-count");
            const negCountLabel = document.getElementById("sim-neg-count");
            
            if (!text) {{
                alert("请输入一些测试句子进行模拟！");
                return;
            }}
            
            const matchedBullish = [];
            const matchedBearish = [];
            const matchedRanges = [];
            
            function isRangeMatched(start, end) {{
                return matchedRanges.some(r => (start >= r.start && start < r.end) || (end > r.start && end <= r.end));
            }}
            
            // Sort keywords by length descending to match longer phrases first (jieba-like)
            const allKeywords = [];
            bullishLexicon.forEach(word => allKeywords.push({{ word, type: 'bullish' }}));
            bearishLexicon.forEach(word => allKeywords.push({{ word, type: 'bearish' }}));
            allKeywords.sort((a, b) => b.word.length - a.word.length);
            
            allKeywords.forEach(kw => {{
                let idx = text.indexOf(kw.word);
                while (idx !== -1) {{
                    const start = idx;
                    const end = idx + kw.word.length;
                    
                    if (!isRangeMatched(start, end)) {{
                        matchedRanges.push({{ start, end }});
                        
                        // Check negation in preceding 1 to 4 characters
                        let hasNegation = false;
                        const precedingText = text.substring(Math.max(0, start - 4), start);
                        
                        for (let neg of negationLexicon) {{
                            if (precedingText.endsWith(neg)) {{
                                hasNegation = true;
                                break;
                            }}
                        }}
                        
                        if (hasNegation) {{
                            // Reversing context
                            if (kw.type === 'bullish') {{
                                matchedBearish.push(`不-${{kw.word}}`);
                            }} else {{
                                matchedBullish.push(`不-${{kw.word}}`);
                            }}
                        }} else {{
                            if (kw.type === 'bullish') {{
                                matchedBullish.push(kw.word);
                            }} else {{
                                matchedBearish.push(kw.word);
                            }}
                        }}
                    }}
                    idx = text.indexOf(kw.word, idx + 1);
                }}
            }});
            
            const pos = matchedBullish.length;
            const neg = matchedBearish.length;
            const total = pos + neg;
            
            let simScore = 0.00;
            if (total > 0) {{
                simScore = (pos - neg) / total;
            }}
            
            // Render simulation details
            scoreLabel.textContent = simScore.toFixed(2);
            posCountLabel.textContent = pos;
            negCountLabel.textContent = neg;
            
            posListLabel.textContent = pos > 0 ? [...new Set(matchedBullish)].join(', ') : "-";
            negListLabel.textContent = neg > 0 ? [...new Set(matchedBearish)].join(', ') : "-";
            
            // Apply color styling to result panel
            resBox.className = "lg:col-span-1 border rounded-xl p-5 flex flex-col justify-between transition-all duration-300 ";
            
            if (simScore > 0) {{
                resBox.classList.add("bg-emerald-950/20", "border-emerald-500/30", "bullish-glow");
                scoreLabel.className = "text-4xl font-extrabold text-emerald-400 font-outfit";
                verdictLabel.innerHTML = "<span class='text-emerald-400 font-semibold'><i class='fa-solid fa-face-smile'></i> 极度乐观/多头情绪</span>";
            }} else if (simScore < 0) {{
                resBox.classList.add("bg-red-950/20", "border-red-500/30", "bearish-glow");
                scoreLabel.className = "text-4xl font-extrabold text-red-400 font-outfit";
                verdictLabel.innerHTML = "<span class='text-red-400 font-semibold'><i class='fa-solid fa-face-sad-tear'></i> 极度悲观/空头情绪</span>";
            }} else {{
                resBox.classList.add("bg-gray-900/40", "border-gray-800");
                scoreLabel.className = "text-4xl font-extrabold text-gray-400 font-outfit";
                verdictLabel.innerHTML = "<span class='text-gray-400 font-semibold'><i class='fa-solid fa-face-meh'></i> 情绪中性/无情绪词匹配</span>";
            }}
        }}

        // Interactive Table Rendering and Filtering
        function highlightKeywords(title, posWords, negWords) {{
            let highlighted = title;
            // Highlight bullish words in green
            posWords.forEach(word => {{
                const regex = new RegExp(word, 'g');
                highlighted = highlighted.replace(regex, `<span class="text-emerald-400 font-bold border-b border-emerald-400/30 bg-emerald-500/5 px-1 rounded">${{word}}</span>`);
            }});
            // Highlight bearish words in red
            negWords.forEach(word => {{
                const regex = new RegExp(word, 'g');
                highlighted = highlighted.replace(regex, `<span class="text-red-400 font-bold border-b border-red-400/30 bg-red-500/5 px-1 rounded">${{word}}</span>`);
            }});
            return highlighted;
        }}

        function filterAndRenderTable() {{
            const searchVal = document.getElementById("post-search").value.trim().toLowerCase();
            const filterType = document.getElementById("post-filter-type").value;
            const sortBy = document.getElementById("post-sort-by").value;
            
            // 1. Filter
            let filtered = rawPosts.filter(post => {{
                // Search keyword
                const matchesSearch = !searchVal || 
                                     post.title.toLowerCase().includes(searchVal) || 
                                     post.author.toLowerCase().includes(searchVal);
                
                // Filter type
                let matchesType = true;
                if (filterType === 'bullish') {{
                    matchesType = post.sentiment_score > 0;
                }} else if (filterType === 'bearish') {{
                    matchesType = post.sentiment_score < 0;
                }} else if (filterType === 'neutral') {{
                    matchesType = post.sentiment_score === 0;
                }}
                
                return matchesSearch && matchesType;
            }});
            
            // 2. Sort
            filtered.sort((a, b) => {{
                if (sortBy === 'time-desc') {{
                    // Assuming time is MM-DD HH:MM
                    return b.time.localeCompare(a.time);
                }} else if (sortBy === 'read-desc') {{
                    return b.read_count - a.read_count;
                }} else if (sortBy === 'reply-desc') {{
                    return b.reply_count - a.reply_count;
                }} else if (sortBy === 'score-desc') {{
                    return b.sentiment_score - a.sentiment_score;
                }} else if (sortBy === 'score-asc') {{
                    return a.sentiment_score - b.sentiment_score;
                }}
                return 0;
            }});
            
            // 3. Render HTML
            const tbody = document.getElementById("posts-table-body");
            tbody.innerHTML = "";
            
            filtered.forEach(post => {{
                const tr = document.createElement("tr");
                tr.className = "hover:bg-gray-800/20 transition-all duration-200 text-gray-300";
                
                // Read cell
                const readTd = `<td class="py-2.5 sm:py-3 px-3 sm:px-6 font-mono text-xs font-semibold text-teal-400 hidden sm:table-cell">${{post.read_count.toLocaleString()}}</td>`;
                // Reply cell
                const replyTd = `<td class="py-2.5 sm:py-3 px-3 sm:px-4 font-mono text-xs text-indigo-400 hidden sm:table-cell">${{post.reply_count.toLocaleString()}}</td>`;
                
                // Title link with highlighted words
                const cleanTitle = highlightKeywords(post.title, post.pos_words, post.neg_words);
                
                // Guba full URL resolver
                let fullUrl = post.href;
                if (fullUrl && !fullUrl.startsWith("http")) {{
                    if (fullUrl.startsWith("//")) {{
                        fullUrl = "https:" + fullUrl;
                    }} else {{
                        fullUrl = "https://guba.eastmoney.com" + fullUrl;
                    }}
                }}
                
                const titleTd = `<td class="py-2.5 sm:py-3 px-3 sm:px-4 text-xs font-medium"><a href="${{fullUrl}}" target="_blank" class="hover:text-teal-300 hover:underline transition-colors block leading-relaxed line-clamp-2 sm:line-clamp-none">${{cleanTitle}}</a></td>`;

                const sourceLabels = {{ eastmoney: '东财', xueqiu: '雪球', ths: '同花顺' }};
                const srcKey = post.source || 'eastmoney';
                const srcLabel = sourceLabels[srcKey] || srcKey;
                const sourceTd = `<td class="py-2.5 sm:py-3 px-3 sm:px-4 text-[10px] text-gray-400 font-semibold hidden md:table-cell">${{srcLabel}}</td>`;
                
                // Badges for matched words
                let badgeHtml = "-";
                if (post.pos_words.length > 0 || post.neg_words.length > 0) {{
                    badgeHtml = "<div class='flex flex-wrap gap-1'>";
                    // Unique tags
                    const uniquePos = [...new Set(post.pos_words)];
                    const uniqueNeg = [...new Set(post.neg_words)];
                    
                    uniquePos.slice(0, 3).forEach(w => {{
                        badgeHtml += `<span class="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[9px] px-1.5 py-0.5 rounded font-medium">${{w}}</span>`;
                    }});
                    uniqueNeg.slice(0, 3).forEach(w => {{
                        badgeHtml += `<span class="bg-rose-500/10 border border-rose-500/20 text-red-400 text-[9px] px-1.5 py-0.5 rounded font-medium">${{w}}</span>`;
                    }});
                    badgeHtml += "</div>";
                }}
                const keywordsTd = `<td class="py-2.5 sm:py-3 px-3 sm:px-4 hidden sm:table-cell">${{badgeHtml}}</td>`;
                
                // Sentiment Score Cell
                let scoreBadgeClass = "bg-gray-800 text-gray-400";
                if (post.sentiment_score > 0) scoreBadgeClass = "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-bold bullish-glow";
                if (post.sentiment_score < 0) scoreBadgeClass = "bg-rose-500/10 border border-rose-500/30 text-red-400 font-bold bearish-glow";
                
                const scoreTd = `<td class="py-2.5 sm:py-3 px-3 sm:px-4 text-center" title="原始权重 (阅读量+1): ${{post.read_count + 1}}\n同账号发布惩罚: ${{post.spammer_penalty}}\n时间衰减因子: ${{post.time_decay}}\n复合量化最终权重: ${{post.final_weight}}"><span class="inline-block text-[10px] px-2 py-0.5 rounded-full font-mono ${{scoreBadgeClass}}">${{post.sentiment_score.toFixed(2)}}</span></td>`;
                
                // Author Cell
                const authorTd = `<td class="py-2.5 sm:py-3 px-3 sm:px-4 text-xs text-gray-400 truncate max-w-[100px] hidden md:table-cell" title="${{post.author}}">${{post.author}}</td>`;
                // Time Cell
                const timeTd = `<td class="py-2.5 sm:py-3 px-3 sm:px-6 text-[10px] sm:text-xs text-gray-500 font-mono whitespace-nowrap">${{post.time}}</td>`;
                
                tr.innerHTML = readTd + replyTd + titleTd + sourceTd + keywordsTd + scoreTd + authorTd + timeTd;
                tbody.appendChild(tr);
            }});
            
            // Update labels
            document.getElementById("showing-posts-count").textContent = `正在展示 ${{filtered.length}} 篇帖子（总样本 ${{rawPosts.length}} 篇）`;
        }}

        // Run on Page Load
        window.addEventListener("load", () => {{
            initGauge();
            renderTrendChart();
            renderWordCharts();
            renderWordCloud();
            filterAndRenderTable();
        }});

        let resizeTimer;
        window.addEventListener("resize", () => {{
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {{
                renderWordCloud();
                if (typeof trendChartObj !== 'undefined' && trendChartObj) trendChartObj.resize();
            }}, 150);
        }});
    </script>
</body>
</html>
"""
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_template)
            print(f"[Generator] Successfully generated A-Share Sentiment Dashboard at: {output_path}")
            return True
        except Exception as e:
            print(f"[Generator] Error generating HTML: {e}", file=sys.stderr)
            return False

if __name__ == "__main__":
    generator = DashboardGenerator()
    generator.generate_html()
