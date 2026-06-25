#!/usr/bin/env python3
"""
历史顶部 / 回撤节点风险模型回测。
先预热 TuShare 日线缓存，再逐日计算，避免频率超限。
"""
import io
import contextlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from risk_scorer import (  # noqa: E402
    compute_risk_score,
    _trade_dates_upto,
    warm_market_cache,
    cache_stats,
    PRO,
    _index_bars_upto,
    _margin_ratio_raw,
)

EVENTS = [
    ("2001牛转熊", "20010614", 2245.44),
    ("2007牛转熊", "20071016", 6124.04),
    ("2015牛转熊", "20150612", 5178.19),
    ("2021核心资产", "20210218", 3731.69),
    ("2026/3回撤", "20260303", 4183.0),
    ("2026/5回撤", "20260514", 4243.0),
]

LOOKBACK = 20


def quiet_score(trade_date, sentiment=None):
    with contextlib.redirect_stdout(io.StringIO()):
        return compute_risk_score(trade_date, sentiment_score=sentiment)


def collect_dates(peak, lookback=LOOKBACK):
    days = _trade_dates_upto(peak, lookback)
    # 指数 K 线、融资等辅助窗口
    extra = set()
    for d in days:
        for w in (60, 250):
            bars_days = _trade_dates_upto(d, w)
            extra.update(bars_days[-5:])
    return sorted(set(days) | extra)


def idx_pct(trade_date):
    bars = _index_bars_upto(trade_date, 60)
    if bars is None or bars.empty:
        return 0.0
    row = bars[bars["trade_date"] == trade_date]
    if row.empty:
        return 0.0
    return float(row.iloc[-1].get("pct_chg", 0))


def post_drawdown(peak, peak_close, n=60):
    cal = PRO.trade_cal(
        exchange="SSE",
        start_date=peak,
        end_date=str(int(peak[:4]) + 2) + peak[4:],
        is_open="1",
    )
    future = [d for d in sorted(cal["cal_date"].tolist()) if d > peak]
    out = {}
    for label, k in [("20日", 20), ("60日", 60)]:
        if len(future) >= k:
            d = future[k - 1]
            bars = _index_bars_upto(d, 5)
            if bars is not None and not bars.empty:
                c = float(bars.iloc[-1]["close"])
                out[label] = (d, c, (c / peak_close - 1) * 100)
    return out


def analyze_event(name, peak, peak_close):
    days = [d for d in _trade_dates_upto(peak, LOOKBACK) if d <= peak]
    pre = [d for d in days if d < peak]

    first45 = first60 = first75 = None
    max_pre = 0.0
    rows = []

    for d in days:
        r = quiet_score(d)
        total = r["total_score"]
        if d in pre:
            if total >= 45 and first45 is None:
                first45 = d
            if total >= 60 and first60 is None:
                first60 = d
            if total >= 75 and first75 is None:
                first75 = d
            max_pre = max(max_pre, total)
        ht = [
            t["label"]
            for t in r.get("hard_triggers", [])
            if t["id"] != "extreme_combo"
        ]
        rows.append((d, total, r["level"], ht, d == peak))

    r_peak = quiet_score(peak)
    r_sent = quiet_score(peak, 0.5)
    dd = post_drawdown(peak, peak_close)

    return {
        "name": name,
        "peak": peak,
        "rows": rows,
        "first45": first45,
        "first60": first60,
        "first75": first75,
        "max_pre": max_pre,
        "peak_score": r_peak["total_score"],
        "peak_level": r_peak["level"],
        "peak_sent": r_sent["total_score"],
        "drawdown": dd,
    }


def main():
    if PRO is None:
        print("需要 TUSHARE_TOKEN")
        sys.exit(1)

    all_dates = set()
    for _, peak, _ in EVENTS:
        all_dates.update(collect_dates(peak))

    print(f"预热行情缓存：{len(all_dates)} 个交易日 …")
    t0 = time.time()
    warmed = warm_market_cache(all_dates, throttle_sec=0.13)
    print(f"  新拉取 {warmed} 日，耗时 {time.time()-t0:.0f}s，缓存 {cache_stats()}")

    # 预热指数 K 线（每峰值日 250 日窗口）
    for _, peak, _ in EVENTS:
        _index_bars_upto(peak, 250)
        for d in _trade_dates_upto(peak, LOOKBACK):
            _index_bars_upto(d, 60)
            _margin_ratio_raw(d)

    print("\n" + "=" * 76)
    print("风险模型回测 — 累积风险 + 硬触发（情绪中性，论坛维度=10）")
    print("=" * 76)

    summary = []
    for name, peak, ref_close in EVENTS:
        res = analyze_event(name, peak, ref_close)
        summary.append(res)
        print(f"\n【{name}】见顶 {peak[:4]}-{peak[4:6]}-{peak[6:]}")
        print(
            f"  见顶前: 首次预警≥45={res['first45'] or '无'} | "
            f"紧急≥60={res['first60'] or '无'} | "
            f"极端≥75={res['first75'] or '无'} | "
            f"前{LOOKBACK}日最高={res['max_pre']:.1f}"
        )
        print(
            f"  见顶日: {res['peak_score']:.1f} {res['peak_level']} | "
            f"情绪0.5假设→{res['peak_sent']:.1f}"
        )
        for label, (d, c, pct) in res["drawdown"].items():
            print(f"  见顶后{label}({d}): 上证{c:.0f} 较顶 {pct:+.1f}%")

        print("  关键日程:")
        for d, total, lvl, ht, is_peak in res["rows"]:
            if total >= 45 or is_peak or d in (res["first60"], res["first45"]):
                mark = " <<<" if is_peak else ""
                print(f"    {d}  {total:5.1f}  {lvl[:8]:<8}  {','.join(ht) or '-'}{mark}")

    print("\n" + "=" * 76)
    print("汇总表")
    print("=" * 76)
    print(
        f"{'事件':<12} {'预警日':<10} {'紧急日':<10} {'见顶分':>6} {'顶+亢奋':>7} {'60日跌幅':>8}"
    )
    for res in summary:
        dd60 = res["drawdown"].get("60日", (None, None, None))[2]
        dd_str = f"{dd60:+.1f}%" if dd60 is not None else "—"
        print(
            f"{res['name']:<12} {str(res['first45'] or '无'):<10} "
            f"{str(res['first60'] or '无'):<10} "
            f"{res['peak_score']:6.1f} {res['peak_sent']:7.1f} {dd_str:>8}"
        )


if __name__ == "__main__":
    main()
