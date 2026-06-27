#!/usr/bin/env python3
"""
历史大跌回测：检验模型在著名大跌上的「同步确认」与「提前量」。
对每次大跌：展示崩盘当天及前若干交易日的评分/等级，
并标注是否出现领先信号（隐性破位 / 顶部派发形态）。
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
    compute_risk_score,
    _trade_dates_upto,
    _index_pct_chg,
    _index_bars_upto,
    _margin_ratio_raw,
    warm_market_cache,
)

# (名称, 崩盘日, 备注)
EVENTS = [
    ("2015股灾·6/19", "20150619", "-6.4% 杠杆牛见顶"),
    ("2015股灾·6/26", "20150626", "-7.4%"),
    ("2015·7/27", "20150727", "-8.5%"),
    ("2015·8/24黑周一", "20150824", "-8.5%"),
    ("2016熔断·1/4", "20160104", "-6.9% 熔断首日"),
    ("2016熔断·1/7", "20160107", "-7.0%"),
    ("2018·2/9", "20180209", "-4.1% 贸易战"),
    ("2018·10/11", "20181011", "-5.2%"),
    ("2020·2/3疫情", "20200203", "-7.7% 节后跳空"),
    ("2024·2/5微盘", "20240205", "小盘流动性危机"),
]

PRE = 6  # 崩盘前观察的交易日数


def quiet(d):
    with contextlib.redirect_stdout(io.StringIO()):
        return compute_risk_score(d, sentiment_score=0.08)


def warm(peak):
    days = _trade_dates_upto(peak, PRE + 4)
    _index_bars_upto(peak, 250)
    for d in days:
        _index_bars_upto(d, 60)
        _margin_ratio_raw(d)
    warm_market_cache(days, throttle_sec=0.12)


def lead_tag(r):
    ids = {s["id"] for s in r.get("signals", [])}
    tags = []
    if "covert_breakdown" in ids:
        tags.append("隐性破位")
    for p in r.get("distribution_patterns", []):
        tags.append(p["label"])
    return "、".join(tags) or "-"


def main():
    if PRO is None:
        print("需要 TUSHARE_TOKEN")
        sys.exit(1)

    print("预热缓存 …")
    t0 = time.time()
    for _, d, _ in EVENTS:
        warm(d)
    print(f"  完成，耗时 {time.time()-t0:.0f}s")

    print("\n" + "=" * 86)
    print("历史大跌回测 — 崩盘当天能否确认 + 前几日是否有领先信号")
    print("=" * 86)

    for name, crash, note in EVENTS:
        days = [d for d in _trade_dates_upto(crash, PRE) if d <= crash]
        print(f"\n【{name}】{note}")
        for d in days:
            r = quiet(d)
            pct = _index_pct_chg(d)
            mark = " <<<崩盘" if d == crash else ""
            print(
                f"  {d}  上证{(pct if pct is not None else 0):+6.2f}%  "
                f"总{r['total_score']:5.1f} 结{r['structure_score']:4.1f} 破{r['breakdown_score']:4.1f}  "
                f"{r['level'][:8]:<8}  {lead_tag(r)}{mark}"
            )


if __name__ == "__main__":
    main()
