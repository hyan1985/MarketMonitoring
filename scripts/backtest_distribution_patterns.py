#!/usr/bin/env python3
"""
顶部派发形态库回测：逐形态衡量「提前量」与「误报率」。
- 对每个历史顶部：见顶前 25 个交易日窗口内，记录各形态首次命中日及距顶提前交易日数。
- 对最近 60 个交易日（当前结构牛）：统计各形态命中天数（误报压力）。
"""
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from risk_scorer import (  # noqa: E402
    PRO,
    _trade_dates_upto,
    _index_bars_upto,
    _margin_ratio_raw,
    detect_distribution_patterns,
    _DISTRIBUTION_DETECTORS,
    warm_market_cache,
)

EVENTS = [
    ("2015牛转熊", "20150612"),
    ("2021核心资产", "20210218"),
    ("2026/3回撤", "20260303"),
    ("2026/5回撤", "20260514"),
]
PRE_WINDOW = 25
RECENT_PEAK = "20260625"
RECENT_WINDOW = 60

PATTERN_LABELS = {
    "shrink_divergence": "缩量背离派发",
    "huge_vol_stall": "天量滞涨派发",
    "upper_shadow": "冲高回落派发",
    "exhaustion_gap": "跳空衰竭派发",
    "high_vol_bear": "高位放量长阴",
    "margin_drain": "融资退潮派发",
}


def warm_for(peak, n):
    days = _trade_dates_upto(peak, n + 10)
    _index_bars_upto(peak, 60)
    for d in days:
        _index_bars_upto(d, 60)
        _margin_ratio_raw(d)
    warm_market_cache(days, throttle_sec=0.13)


def main():
    if PRO is None:
        print("需要 TUSHARE_TOKEN")
        sys.exit(1)

    print("预热缓存 …")
    t0 = time.time()
    for _, peak in EVENTS:
        warm_for(peak, PRE_WINDOW)
    warm_for(RECENT_PEAK, RECENT_WINDOW)
    print(f"  完成，耗时 {time.time()-t0:.0f}s")

    print("\n" + "=" * 74)
    print("顶部派发形态回测 — 各形态见顶前首次命中（提前交易日数）")
    print("=" * 74)

    for name, peak in EVENTS:
        days = [d for d in _trade_dates_upto(peak, PRE_WINDOW) if d <= peak]
        first_hit = {}  # id -> (date, lead_days)
        peak_hits = []
        for d in days:
            for pat in detect_distribution_patterns(d):
                pid = pat["id"]
                if pid not in first_hit and d < peak:
                    lead = (len(days) - 1) - days.index(d)
                    first_hit[pid] = (d, lead)
                if d == peak:
                    peak_hits.append(pat["label"])
        print(f"\n【{name}】见顶 {peak[:4]}-{peak[4:6]}-{peak[6:]}")
        if first_hit:
            for pid, (d, lead) in sorted(first_hit.items(), key=lambda x: -x[1][1]):
                print(f"  {PATTERN_LABELS.get(pid, pid):<12} 首次 {d} 提前 {lead} 日")
        else:
            print("  见顶前无形态命中")
        print(f"  见顶日命中: {('、'.join(peak_hits)) or '无'}")

    print("\n" + "=" * 74)
    print(f"最近{RECENT_WINDOW}个交易日：各形态命中天数（误报压力）")
    print("=" * 74)
    days_recent = _trade_dates_upto(RECENT_PEAK, RECENT_WINDOW)
    counts = defaultdict(int)
    sample = defaultdict(list)
    for d in days_recent:
        for pat in detect_distribution_patterns(d):
            counts[pat["id"]] += 1
            if len(sample[pat["id"]]) < 4:
                sample[pat["id"]].append(d)
    for det in _DISTRIBUTION_DETECTORS:
        # 通过命中样本推断 id 名称
        pass
    for pid in PATTERN_LABELS:
        n = counts.get(pid, 0)
        eg = ("，例: " + "、".join(sample[pid])) if sample[pid] else ""
        print(f"  {PATTERN_LABELS[pid]:<12} {n:>2}/{RECENT_WINDOW}{eg}")


if __name__ == "__main__":
    main()
