import argparse
import json
import os
import subprocess
import sys
import webbrowser
from datetime import datetime, time, timedelta
from pathlib import Path

from beijing_time import BEIJING_TZ, now_beijing

PROJECT_DIR = Path(__file__).resolve().parent
from guba_crawler import GubaCrawler
from xueqiu_crawler import XueqiuCrawler
from ths_crawler import ThsCrawler
from crawler_utils import merge_posts, calc_pages, filter_posts_for_run_date
from sentiment_analyzer import SentimentAnalyzer
from dashboard_generator import DashboardGenerator
from data_store import load_bundle, save_bundle
from risk_scorer import compute_risk_score

# ANSI escape codes for beautiful terminal progress prints
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_step(title):
    print(f"\n{Colors.OKBLUE}{Colors.BOLD}=== {title} ==={Colors.ENDC}")

def print_success(message):
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

def print_error(message):
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}", file=sys.stderr)

def parse_args():
    parser = argparse.ArgumentParser(description="大A情绪分参考模型 - 自动化分析")
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="按指定日期过滤帖子并计入日线（补跑历史日用）",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="分析北京时间当天的帖子",
    )
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="分析北京时间昨天的帖子（定时任务用：0 点后跑前一天全天）",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="完成后不自动打开 Dashboard",
    )
    return parser.parse_args()

def resolve_run_date(args):
    """Return (run_date, reference_time) in Asia/Shanghai."""
    now_sh = now_beijing()
    if args.date:
        run_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    elif args.today:
        run_date = now_sh.date()
    elif args.yesterday:
        run_date = (now_sh - timedelta(days=1)).date()
    else:
        # 本地默认跑昨天（早上手动跑时数据更完整）
        run_date = (now_sh - timedelta(days=1)).date()
    reference_time = datetime.combine(run_date, time(23, 59, 59), tzinfo=BEIJING_TZ)
    return run_date, reference_time.replace(tzinfo=None)

def main():
    args = parse_args()
    if sum([bool(args.date), args.today, args.yesterday]) > 1:
        print_error("--date、--today、--yesterday 只能三选一。")
        sys.exit(1)
    print(f"{Colors.HEADER}{Colors.BOLD}====================================================")
    print("      大A情绪分参考模型 - 自动化分析运行系统        ")
    print(f"===================================================={Colors.ENDC}")

    workspace_dir = str(PROJECT_DIR)
    config_path = os.path.join(workspace_dir, "config.json")
    data_path = os.path.join(workspace_dir, "data.json")
    html_path = os.path.join(workspace_dir, "index.html")

    # Step 1: Load configurations
    print_step("步骤 1: 加载系统配置及情绪词典")
    if not os.path.exists(config_path):
        print_error(f"配置文件 config.json 未在 {config_path} 找到。")
        sys.exit(1)
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        guba_code = config.get("guba_code", "zssh000001")
        posts_per_source = config.get("posts_per_source", 1000)
        sources = config.get("sources", {"eastmoney": True, "xueqiu": True, "ths": True})
        xueqiu_symbol = config.get("xueqiu_symbol", "SH000001")
        ths_code = config.get("ths_code", "1a0001")
        ths_cookie = config.get("ths_cookie", "")
        ths_hexin_v = config.get("ths_hexin_v", "")
        xueqiu_cookie = config.get("xueqiu_cookie", "")
        filter_run_date_only = config.get("filter_run_date_only", True)
        run_date, reference_time = resolve_run_date(args)

        pages_to_crawl = config.get("pages_to_crawl") or calc_pages(posts_per_source, 80)
        max_crawl_pages = config.get("max_crawl_pages", 80)
        xueqiu_pages = config.get("xueqiu_pages") or calc_pages(posts_per_source, 10)
        ths_pages = config.get("ths_pages") or calc_pages(posts_per_source, 20)

        enabled = [k for k, v in sources.items() if v]
        print_success(
            f"已加载配置。每源目标 {posts_per_source} 条；数据源: {', '.join(enabled)}。"
        )
        if filter_run_date_only:
            print(
                f"  抓取计划 → 按日边界翻页（最多 {max_crawl_pages} 页），"
                f"覆盖 {run_date.strftime('%Y-%m-%d')} 全天后再停止"
            )
        else:
            print(
                f"  抓取计划 → 东财 {pages_to_crawl} 页，雪球 {xueqiu_pages} 页 ({xueqiu_symbol})，"
                f"同花顺 {ths_pages} 页 ({ths_code})"
            )
        if filter_run_date_only:
            print(f"  时间过滤 → 仅保留运行日 {run_date.strftime('%Y-%m-%d')} 的帖子")
    except Exception as e:
        print_error(f"读取配置文件失败: {e}")
        sys.exit(1)

    # Step 2: Crawl all enabled forum sources
    print_step("步骤 2: 爬取多平台论坛实时讨论帖子")
    post_batches = []

    if sources.get("eastmoney", True):
        print(f"\n{Colors.BOLD}>> 东方财富股吧{Colors.ENDC}")
        guba_crawler = GubaCrawler(code=guba_code)
        if filter_run_date_only:
            guba_posts = guba_crawler.crawl_until_run_date(
                run_date=run_date, max_pages=max_crawl_pages
            )
        else:
            guba_posts = guba_crawler.crawl_multiple_pages(
                num_pages=pages_to_crawl, max_posts=posts_per_source
            )
        post_batches.append(guba_posts)
        print_success(f"东财股吧: {len(guba_posts)} 条")

    if sources.get("xueqiu", True):
        print(f"\n{Colors.BOLD}>> 雪球讨论区{Colors.ENDC}")
        if not (xueqiu_cookie or "").strip():
            print(
                f"  {Colors.WARNING}提示: 未配置 xueqiu_cookie，雪球可能抓不到数据。"
                f"复制浏览器 Cookie 后运行: python3 setup_xueqiu_cookie.py{Colors.ENDC}"
            )
        xq_crawler = XueqiuCrawler(symbol=xueqiu_symbol, cookie=xueqiu_cookie)
        xq_posts = xq_crawler.crawl_multiple_pages(
            num_pages=xueqiu_pages, max_posts=posts_per_source
        )
        post_batches.append(xq_posts)
        print_success(f"雪球: {len(xq_posts)} 条")

    if sources.get("ths", False):
        print(f"\n{Colors.BOLD}>> 同花顺论股堂{Colors.ENDC}")
        ths_crawler = ThsCrawler(code=ths_code, cookie=ths_cookie, hexin_v=ths_hexin_v)
        ths_posts = ths_crawler.crawl_multiple_pages(
            num_pages=ths_pages, max_posts=posts_per_source
        )
        post_batches.append(ths_posts)
        print_success(f"同花顺: {len(ths_posts)} 条")

    raw_posts = merge_posts(post_batches)

    if not raw_posts:
        print_error("抓取失败，未获得任何平台的有效帖子。请检查网络或数据源配置。")
        sys.exit(1)

    source_counts = {}
    for p in raw_posts:
        src = p.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
    breakdown = "，".join(f"{k}:{v}" for k, v in sorted(source_counts.items()))
    crawled_total = len(raw_posts)
    print_success(f"多源合并完成，共 {crawled_total} 条（{breakdown}）。")

    date_skipped = 0
    skipped_by_source = {}
    scan_date = run_date.strftime("%Y-%m-%d")
    if filter_run_date_only:
        raw_posts, date_skipped, skipped_by_source, scan_date = filter_posts_for_run_date(
            raw_posts, run_date=run_date
        )
        skip_detail = "，".join(f"{k}:{v}" for k, v in sorted(skipped_by_source.items())) or "无"
        print(
            f"{Colors.WARNING}  当日过滤: 保留 {len(raw_posts)} 条，剔除非当日 {date_skipped} 条"
            f"（剔除分布: {skip_detail}）{Colors.ENDC}"
        )
        if not raw_posts:
            print_error(
                f"当日 ({scan_date}) 无有效帖子。可能是非交易日、数据源时间字段异常，"
                "或同花顺返回了历史归档帖。可暂时设置 filter_run_date_only: false 排查。"
            )
            sys.exit(1)

    # Step 3: Run sentiment analyzer NLP engine
    print_step("步骤 3: 运行 NLP 情绪分析与指数算力引擎")
    try:
        analyzer = SentimentAnalyzer(config_path=config_path)
        sentiment_results = analyzer.analyze_posts(raw_posts, reference_time=reference_time)
        sentiment_results["summary"]["scan_date"] = scan_date
        sentiment_results["summary"]["crawled_posts"] = crawled_total
        sentiment_results["summary"]["date_filtered_posts"] = date_skipped
        
        # Display short summary in terminal
        summary = sentiment_results["summary"]
        print(f"\n{Colors.BOLD}【多空情绪计算报告】{Colors.ENDC}")
        print(f"  - 大A加权情绪分 (Weighted Score): {Colors.OKCYAN}{summary['overall_weighted_score']}{Colors.ENDC}  [-1.0 至 +1.0]")
        
        score = summary['overall_weighted_score']
        if score <= -0.3:
            verdict = f"{Colors.OKGREEN}【极度悲观 / 黄金买点】建议逐步逆向建仓 +10% ~ +20% 位置{Colors.ENDC}"
        elif score >= 0.5:
            verdict = f"{Colors.FAIL}【极度乐观 / 防御警报】随时可能见顶，建议防守防微 -10% ~ -20% 并兑现盈利{Colors.ENDC}"
        else:
            verdict = f"{Colors.WARNING}【情绪中性 / 卧倒装死】属于情绪噪音，保持底仓，持股不动{Colors.ENDC}"
        
        print(f"  - 策略操作倾向: {verdict}")
        print(f"  - 抓取原始样本: {summary['total_posts']} 篇")
        print(f"  - 过滤广告系统: {Colors.WARNING}{summary['spam_posts']}{Colors.ENDC} 篇")
        print(f"  - 评分有效帖数: {summary['valid_posts']} 篇")
        if summary['valid_posts'] > 0:
            print(f"  - 看多帖子占比: {summary['bullish_posts']} 篇 ({(summary['bullish_posts']/summary['valid_posts']*100):.1f}%)")
            print(f"  - 看空帖子占比: {summary['bearish_posts']} 篇 ({(summary['bearish_posts']/summary['valid_posts']*100):.1f}%)")
            print(f"  - 中性噪音占比: {summary['neutral_posts']} 篇 ({(summary['neutral_posts']/summary['valid_posts']*100):.1f}%)")
        
        # Save results
        analyzer.save_results(sentiment_results, output_path=data_path)
        print_success("情绪指数数据计算成功并导出至 data.json。")
    except Exception as e:
        print_error(f"运行情绪分析引擎失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 3.5: Compute market risk score via TuShare
    print_step("步骤 3.5: 计算大盘综合风险值 (TuShare 多维数据)")
    risk_data = None
    try:
        # 与帖子统计日对齐：取该日或之前最近一个有行情的交易日
        risk_data = compute_risk_score(
            trade_date_str=run_date.strftime("%Y%m%d"),
            sentiment_score=sentiment_results["summary"]["overall_weighted_score"],
        )
        print(f"\n{Colors.BOLD}【大盘风险值报告】{Colors.ENDC}")
        print(f"  - 综合风险分 (Risk Score): {Colors.OKCYAN}{risk_data['total_score']}{Colors.ENDC}  [0-100]")
        print(
            f"  - 双轨: 结构拥挤 {risk_data.get('structure_score')} "
            f"+ 破位风险 {risk_data.get('breakdown_score')}"
            + (" (主升趋势熔断)" if risk_data.get("bull_trend") else "")
        )
        print(f"  - 风险等级: {risk_data['level']}")
        for p in risk_data.get("distribution_patterns", []):
            flag = "🔻" if p.get("alert") else "🔸"
            print(
                f"  - {Colors.WARNING}{flag} 顶部派发·{p['label']}（{p['kind']}）: "
                f"{p['detail']}{Colors.ENDC}"
            )
        print(f"  - 策略建议: {risk_data['advice']}")
        if risk_data.get("momentum_bonus") or risk_data.get("accumulation_bonus"):
            print(
                f"  - 加成: 变动 +{risk_data.get('momentum_bonus', 0)} "
                f"累积 +{risk_data.get('accumulation_bonus', 0)}"
                f" (基础分 {risk_data.get('base_score')})"
            )
        if risk_data.get("floor_score"):
            print(f"  - 硬触发底线: {risk_data['floor_score']}")
        if risk_data.get("aftershock"):
            for sig in risk_data.get("signals", []):
                if sig.get("id") == "aftershock":
                    print(f"  - {Colors.WARNING}⚡ 余震警戒: {sig['detail']}{Colors.ENDC}")
        for sig in risk_data.get("signals", []):
            if sig.get("id") == "aftershock":
                continue
            print(f"    ⚡ {sig['label']} +{sig['points']} | {sig['detail']}")
        for trig in risk_data.get("hard_triggers", []):
            print(f"    🚨 {trig['label']} → 底线 {trig['floor']} | {trig['detail']}")
        for key, dim in risk_data["dimensions"].items():
            bar = "█" * int(dim["score"]) + "░" * (20 - int(dim["score"]))
            print(f"    {dim['label']}: [{bar}] {dim['score']}分  |  {dim['detail']}")

        # Append risk data to data.json (posts stay in posts.json)
        bundle = load_bundle(data_path, include_posts=False)
        bundle["risk"] = risk_data
        save_bundle(bundle, data_path)
        print_success("大盘风险值已合并写入 data.json。")
    except Exception as e:
        print_error(f"大盘风险值计算失败: {e}")
        import traceback
        traceback.print_exc()
        # 不阻断主流程，继续生成 Dashboard

    # Step 4: Generate HTML dashboard
    print_step("步骤 4: 构建可视化玻璃拟物交互 Dashboard")
    try:
        generator = DashboardGenerator(data_path=data_path, config_path=config_path)
        success = generator.generate_html(output_path=html_path)
        if success:
            print_success(f"美化版可视化网页构建成功：{html_path}")
        else:
            print_error("构建 Dashboard HTML 失败。")
            sys.exit(1)
    except Exception as e:
        print_error(f"构建网页可视化文件失败: {e}")
        sys.exit(1)

    # Step 5: Automatically open dashboard in browser
    if args.no_browser:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}====================================================")
        print("      所有分析与报表处理完毕！系统成功退出。        ")
        print(f"===================================================={Colors.ENDC}\n")
        return

    print_step("步骤 5: 自动打开情绪分 Dashboard 浏览器页面")
    try:
        port = 8765
        server = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port)],
            cwd=workspace_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        url = f"http://127.0.0.1:{port}/index.html"
        print(f"正在打开本地看板：{url}")
        webbrowser.open(url)
        print_success("已启动本地 HTTP 服务并打开看板（帖子从 posts.json 加载）。")
        print(f"  若需手动访问: cd {workspace_dir} && python -m http.server {port}")
    except Exception as e:
        print_error(f"拉起浏览器失败: {e}，您可以手动运行 python -m http.server 8765 后访问 index.html。")

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}====================================================")
    print("      所有分析与报表处理完毕！系统成功退出。        ")
    print(f"===================================================={Colors.ENDC}\n")

if __name__ == "__main__":
    main()
