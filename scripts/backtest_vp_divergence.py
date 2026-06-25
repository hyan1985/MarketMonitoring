#!/usr/bin/env python3
"""
量价背离领先信号回测：衡量「提前量」与「误报率」。
- 对每个历史顶部：在见顶前 25 个交易日窗口内，找首次满足
  「近5日内背离≥need 天」的日期，计算距顶提前几个交易日。
- 对最近 30 个交易日（当前结构牛）：统计背离持续触发的天数（误报压力）。
"""
import io
import contextlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from risk_scorer import (  # noqa: E402
    PRO,
    _trade_dates_upto,
    _vp_divergence_persistence,
    _vol_price_divergence_score,
    _index_bars_upto,
    warm_market_cache,
)

EVENTS = [
    ("2015牛转熊", "20150612"),
    ("2021核心资产", "20210218"),
    ("2026/3回撤", "20260303"),
    ("2026/5回撤", "20260514"),
]

PRE_WINDOW = 25
NEED = 3  # 近5日内背离≥3天 视为领先确认


def trade_dates_between(peak, n):
    return [d for d in _trade_dates_upto(peak, n) if d <= peak]


def warm_for(peak, n):
    days = _trade_dates_upto(peak, n + 8)
    _index_bars_upto(peak, 60)
    for d in days:
        _index_bars_upto(d, 60)
    warm_market_cache(days, throttle_sec=0.13)


def analyze_event(name, peak):
    days = trade_dates_between(peak, PRE_WINDOW)
    pre = [d for d in days if d < peak]
    first_lead = None
    rows = []
    for d in days:
        hits, det = _vp_divergence_persistence(d, window=5, need=NEED)
        sc, _ = _vol_price_divergence_score(d)
        confirmed = hits >= NEED
        if d in pre and confirmed and first_lead is None:
            first_lead = d
        rows.append((d, sc, hits, confirmed, det, d == peak))
    lead_days = None
    if first_lead is not None:
        lead_days = pre[::-1].index(first_lead) if first_lead in pre else None
        # 距顶提前交易日数 = 顶前序列里从后往前数的位置+1
        idx = days.index(first_lead)
        lead_days = (len(days) - 1) - idx
    return name, peak, first_lead, lead_days, rows


def main():
    if PRO is None:
        print("需要 TUSHARE_TOKEN")
        sys.exit(1)

    print("预热缓存 …")
    t0 = time.time()
    for _, peak in EVENTS:
        warm_for(peak, PRE_WINDOW)
    warm_for("20260625", 35)
    print(f"  完成，耗时 {time.time()-t0:.0f}s")

    print("\n" + "=" * 72)
    print(f"量价背离领先信号回测（确认条件：近5日内背离≥{NEED}天）")
    print("=" * 72)

    for name, peak in EVENTS:
        nm, pk, first_lead, lead_days, rows = analyze_event(name, peak)
        print(f"\n【{nm}】见顶 {pk[:4]}-{pk[4:6]}-{pk[6:]}")
        if first_lead:
            print(f"  首次领先确认: {first_lead}  →  提前 {lead_days} 个交易日")
        else:
            print("  首次领先确认: 无（窗口内未触发）")
        for d, sc, hits, conf, det, is_peak in rows:
            if sc >= 2 or conf or is_peak:
                mark = " <<<顶" if is_peak else (" ★确认" if conf else "")
                print(f"    {d}  日强度{sc} 近5日{hits}天  {det or '-'}{mark}")

    # 最近30个交易日误报压力
    print("\n" + "=" * 72)
    print("最近30个交易日：背离确认天数（误报压力）")
    print("=" * 72)
    days30 = _trade_dates_upto("20260625", 30)
    conf_days = 0
    sig_days = 0
    for d in days30:
        hits, det = _vp_divergence_persistence(d, window=5, need=NEED)
        sc, _ = _vol_price_divergence_score(d)
        if sc >= 2:
            sig_days += 1
        if hits >= NEED:
            conf_days += 1
            print(f"    {d}  日强度{sc} 近5日{hits}天 ★确认  {det or '-'}")
    print(f"\n  近30日：单日背离 {sig_days}/30，领先确认 {conf_days}/30")


if __name__ == "__main__":
    main()
