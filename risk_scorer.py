"""
大盘风险值综合评分模块
使用 TuShare Pro API 获取多维数据，计算 0-100 的综合风险分。

五个维度（各 0-20 分）：
1. 资金集中度 — 前5%个股成交额/全市场成交额
2. 融资占比 — 融资余额/总市值
3. 行业集中度 — 通信+电子成交额/全市场
4. 恐慌扩散 — 大跌家数占比（结构性行情下比单纯宽度更能反映抛压）
5. 情绪分 — 论坛情绪反向映射（太乐观→高风险）

另：变动性信号（最多 +15 分）+ 累积风险（最多 +18 分）+ 硬触发底线分。

双轨合成（0–100）：
- 结构拥挤分（0–50）：资金/行业/杠杆/情绪亢奋 + 结构类信号 → 主升期常偏高，偏「观察」
- 破位风险分（0–50）：恐慌扩散 + 宽度骤降/隐性走弱 → 真正减仓信号
多头趋势（MA5>MA10>MA20）下总分熔断：破位 <20 时总分上限 55，避免结构性牛市天天 70–90。
"""

import os
import json
from datetime import datetime, timedelta

import tushare as ts

from beijing_time import today_beijing

TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
if TUSHARE_TOKEN:
    ts.set_token(TUSHARE_TOKEN)
    PRO = ts.pro_api()
else:
    PRO = None

# 行业缓存（首次加载后不会重复请求）
_INDUSTRY_MAP = None
_CONC_CACHE = {}
_MARGIN_CACHE = {}
_DAILY_STATS_CACHE = {}
_INDEX_PCT_CACHE = {}
_INDEX_BARS_CACHE = {}
_TRADE_CAL_CACHE = {}


def _load_industry_map():
    """加载股票 → 行业映射（缓存）"""
    global _INDUSTRY_MAP
    if _INDUSTRY_MAP is not None:
        return _INDUSTRY_MAP
    df = PRO.stock_basic(
        exchange="",
        list_status="L",
        fields="ts_code,industry",
    )
    _INDUSTRY_MAP = dict(zip(df["ts_code"], df["industry"]))
    return _INDUSTRY_MAP


def _is_trade_day(d):
    """判断是否为上交所交易日。"""
    if PRO is None:
        return False
    ds = d.strftime("%Y%m%d")
    try:
        df = PRO.trade_cal(exchange="SSE", start_date=ds, end_date=ds)
        return not df.empty and df.iloc[0].get("is_open", 0) == 1
    except Exception:
        return False


def _has_daily_data(trade_date_str):
    """TuShare daily 是否已有该日全市场行情（未入库时返回 False）。"""
    if PRO is None:
        return False
    try:
        df = PRO.daily(trade_date=trade_date_str, fields="ts_code")
        return not df.empty
    except Exception:
        return False


def _last_trade_date(target_date=None, require_data=False):
    """
    找到最近的交易日。
    require_data=True 时，继续往前找直到 daily 行情实际可用（避免当日未收盘/T+1 未入库显示 0%）。
    """
    if target_date is None:
        target = today_beijing()
    elif isinstance(target_date, str):
        if len(target_date) == 8:
            target = datetime.strptime(target_date, "%Y%m%d").date()
        else:
            target = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        target = target_date

    lookback = 15 if require_data else 10
    for i in range(lookback):
        d = target - timedelta(days=i)
        if not _is_trade_day(d):
            continue
        if require_data and not _has_daily_data(d.strftime("%Y%m%d")):
            continue
        return d

    return target


def _trade_dates_upto(trade_date_str, count):
    """含当日在内，向前取 count 个交易日（升序）。"""
    if PRO is None:
        return []
    cache_key = (trade_date_str, count)
    if cache_key in _TRADE_CAL_CACHE:
        return _TRADE_CAL_CACHE[cache_key]
    target = datetime.strptime(trade_date_str, "%Y%m%d").date()
    start = (target - timedelta(days=count * 3 + 14)).strftime("%Y%m%d")
    try:
        cal = PRO.trade_cal(
            exchange="SSE", start_date=start, end_date=trade_date_str, is_open="1"
        )
        days = sorted(cal["cal_date"].tolist())
    except Exception:
        return []
    if trade_date_str not in days:
        days = [d for d in days if d <= trade_date_str]
    result = days[-count:]
    _TRADE_CAL_CACHE[cache_key] = result
    return result


def _tech_codes():
    industry_map = _load_industry_map()
    return {
        code
        for code, ind in industry_map.items()
        if ind in ("通信设备", "通信服务", "电子元器件", "半导体", "元器件")
    }


def _get_daily_stats(trade_date_str):
    """
    单日全市场行情统计（一次 daily 请求，多处复用）。
    返回 dict: up_ratio, severe_ratio, concentration_ratio, industry_ratio
    """
    if trade_date_str in _DAILY_STATS_CACHE:
        return _DAILY_STATS_CACHE[trade_date_str]
    if PRO is None:
        return None
    try:
        df = PRO.daily(
            trade_date=trade_date_str, fields="ts_code,pct_chg,amount"
        )
    except Exception:
        return None
    if df.empty:
        return None

    total = len(df)
    up_ratio = float(len(df[df["pct_chg"] > 0]) / total) if total else None
    severe_ratio = (
        float(len(df[df["pct_chg"] <= -5]) / total) if total else None
    )

    conc_ratio = None
    ind_ratio = None
    df_amt = df.dropna(subset=["amount"])
    total_amount = df_amt["amount"].sum()
    if total_amount > 0:
        sorted_df = df_amt.sort_values("amount", ascending=False)
        top_n = max(1, int(len(sorted_df) * 0.05))
        conc_ratio = float(
            sorted_df["amount"].iloc[:top_n].sum() / total_amount
        )
        tech = _tech_codes()
        ind_ratio = float(
            df_amt[df_amt["ts_code"].isin(tech)]["amount"].sum() / total_amount
        )

    stats = {
        "up_ratio": up_ratio,
        "severe_ratio": severe_ratio,
        "concentration_ratio": conc_ratio,
        "industry_ratio": ind_ratio,
    }
    _DAILY_STATS_CACHE[trade_date_str] = stats
    if conc_ratio is not None:
        _CONC_CACHE[trade_date_str] = conc_ratio
    return stats


def warm_market_cache(trade_dates, throttle_sec=0.13):
    """
    批量预热行情缓存，避免回测时触发 TuShare 频率限制。
    throttle_sec≈0.13 → 约 460 次/分钟上限。
    """
    import time

    warmed = 0
    for d in sorted(set(trade_dates)):
        if d in _DAILY_STATS_CACHE:
            continue
        _get_daily_stats(d)
        warmed += 1
        if throttle_sec > 0:
            time.sleep(throttle_sec)
    return warmed


def cache_stats():
    """返回当前缓存规模（调试用）。"""
    return {
        "daily": len(_DAILY_STATS_CACHE),
        "concentration": len(_CONC_CACHE),
        "margin": len(_MARGIN_CACHE),
        "index_bars": len(_INDEX_BARS_CACHE),
        "trade_cal": len(_TRADE_CAL_CACHE),
    }


def _index_pct_chg(trade_date_str):
    if PRO is None:
        return None
    if trade_date_str in _INDEX_PCT_CACHE:
        return _INDEX_PCT_CACHE[trade_date_str]
    try:
        df = PRO.index_daily(
            ts_code="000001.SH", trade_date=trade_date_str, fields="pct_chg"
        )
        if df.empty:
            return None
        val = float(df.iloc[0]["pct_chg"])
        _INDEX_PCT_CACHE[trade_date_str] = val
        return val
    except Exception:
        return None


def _index_bars_upto(trade_date_str, window=250):
    """缓存：截至 trade_date_str 的指数收盘价序列。"""
    key = (trade_date_str, window)
    if key in _INDEX_BARS_CACHE:
        return _INDEX_BARS_CACHE[key]
    if PRO is None:
        return None
    target = datetime.strptime(trade_date_str, "%Y%m%d").date()
    start = (target - timedelta(days=window * 2)).strftime("%Y%m%d")
    try:
        df = PRO.index_daily(
            ts_code="000001.SH",
            start_date=start,
            end_date=trade_date_str,
            fields="trade_date,close,pct_chg,amount",
        )
    except Exception:
        return None
    if df.empty:
        return None
    bars = df.sort_values("trade_date").tail(window)
    _INDEX_BARS_CACHE[key] = bars
    for _, row in bars.iterrows():
        d = row["trade_date"]
        if d not in _INDEX_PCT_CACHE and row.get("pct_chg") is not None:
            _INDEX_PCT_CACHE[d] = float(row["pct_chg"])
    return bars


def _concentration_ratio(trade_date_str):
    if trade_date_str in _CONC_CACHE:
        return _CONC_CACHE[trade_date_str]
    stats = _get_daily_stats(trade_date_str)
    if not stats:
        return None
    return stats.get("concentration_ratio")


def _sampled_concentration_history(trade_date_str, window=60, step=5):
    days = _trade_dates_upto(trade_date_str, window)
    if not days:
        return []
    return [_concentration_ratio(days[i]) for i in range(0, len(days), step)]


def _industry_ratio(trade_date_str):
    stats = _get_daily_stats(trade_date_str)
    if not stats:
        return None
    return stats.get("industry_ratio")


def _up_ratio(trade_date_str):
    stats = _get_daily_stats(trade_date_str)
    if not stats:
        return None
    return stats.get("up_ratio")


def _margin_ratio_raw(trade_date_str):
    if PRO is None:
        return None
    if trade_date_str in _MARGIN_CACHE:
        return _MARGIN_CACHE[trade_date_str]
    try:
        mg = PRO.margin(trade_date=trade_date_str, fields="exchange_id,rzye")
        db = PRO.daily_basic(trade_date=trade_date_str, fields="ts_code,total_mv")
    except Exception:
        return None
    if mg is None or mg.empty or db is None or db.empty:
        return None
    total_mv = db["total_mv"].sum() * 10000
    if total_mv == 0:
        return None
    ratio = float(mg["rzye"].sum() / total_mv)
    _MARGIN_CACHE[trade_date_str] = ratio
    return ratio


_STRUCTURE_SIGNAL_IDS = {
    "conc_rising_3d",
    "tech_rising_3d",
    "structural_divergence",
    "near_250d_high",
    "elevated_250d",
    "conc_crowding",
    "margin_buildup",
    "breadth_narrowing",
}
_BREAKDOWN_SIGNAL_IDS = {"hidden_weakness", "breadth_collapse_3d"}
_STRUCTURE_TRIGGER_IDS = {
    "top_divergence",
    "crowding_at_high",
    "euphoria_top",
    "background_risk",
}
_BREAKDOWN_TRIGGER_IDS = {"leverage_blowoff"}


def _is_bull_trend(trade_date_str):
    """上证 MA5 > MA10 > MA20 视为多头趋势。"""
    bars = _index_bars_upto(trade_date_str, 30)
    if bars is None or len(bars) < 20:
        return False
    closes = bars["close"].astype(float).tolist()
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    return ma5 > ma10 > ma20


def _split_signals(signals, trade_date_str=None):
    index_pct = _index_pct_chg(trade_date_str) if trade_date_str else None
    structure, breakdown = [], []
    for s in signals:
        if s["id"] in _BREAKDOWN_SIGNAL_IDS:
            if s["id"] == "hidden_weakness" and index_pct is not None and index_pct >= 0:
                structure.append(s)
            elif s["id"] == "breadth_collapse_3d" and index_pct is not None and index_pct >= -0.1:
                structure.append(s)
            else:
                breakdown.append(s)
        elif s["id"] in _STRUCTURE_SIGNAL_IDS:
            structure.append(s)
        else:
            structure.append(s)
    return structure, breakdown


def _breakdown_index_boost(trade_date_str):
    """指数大跌 / 恐慌扩散时抬高破位分（弥补 market_stress 单维上限 20）。"""
    index_pct = _index_pct_chg(trade_date_str)
    stats = _get_daily_stats(trade_date_str)
    severe = stats.get("severe_ratio") if stats else None
    boost = 0.0
    if index_pct is not None:
        if index_pct <= -1.5:
            boost += 12.0
        elif index_pct <= -0.8:
            boost += 7.0
        elif index_pct <= -0.3:
            boost += 3.0
    if severe is not None:
        if severe >= 0.15:
            boost += 10.0
        elif severe >= 0.10:
            boost += 5.0
    return boost


def _cap_signal_bonus(signals, cap):
    total = sum(s["points"] for s in signals)
    if total <= cap:
        return round(total, 1)
    kept, used = [], 0.0
    for s in sorted(signals, key=lambda x: x["points"], reverse=True):
        if used + s["points"] <= cap:
            kept.append(s)
            used += s["points"]
    return round(used, 1)


def _structure_from_dimensions(dimensions):
    """基础维度 → 结构拥挤分（0–40 量级）。"""
    struct = (
        dimensions["concentration"]["score"] * 0.5
        + dimensions["industry"]["score"] * 0.5
    )
    # 融资数据缺失时（value=None 取了占位中位分）不计入，避免虚增结构分
    if dimensions["margin"].get("value") is not None:
        struct += dimensions["margin"]["score"] * 0.5
    sent = dimensions["sentiment"]["score"]
    if sent > 10:
        struct += min((sent - 10) * 0.5, 5.0)
    else:
        struct += sent * 0.15
    return struct


def _breakdown_from_dimensions(dimensions):
    return float(dimensions["market_stress"]["score"])


def _dual_total(structure_score, breakdown_score, bull_trend):
    raw = structure_score + breakdown_score
    if not bull_trend:
        return round(min(raw, 100), 1)
    if breakdown_score < 20:
        return round(min(raw, 55), 1)
    if breakdown_score < 28:
        return round(min(raw, 50 + breakdown_score * 0.45), 1)
    return round(min(raw, 100), 1)


def _index_distance_from_high(trade_date_str, window=250):
    """距 window 日高点百分比，0 表示在高点，-5 表示低 5%。"""
    bars = _index_bars_upto(trade_date_str, window)
    if bars is None or bars.empty:
        return None
    high = float(bars["close"].max())
    current = float(bars.iloc[-1]["close"])
    if high == 0:
        return None
    return (current / high - 1) * 100


def _percentile_rank(value, series):
    valid = [v for v in series if v is not None]
    if not valid or value is None:
        return None
    below = sum(1 for v in valid if v <= value)
    return below / len(valid)


def _vol_price_divergence_score(trade_date_str):
    """
    量价背离领先信号（顶部派发的领先特征）。
    思路：指数在高位区，但「成交量退潮 + 参与面走弱」，
    即指数靠权重撑着、底下却在缩量背离 —— 顶部派发的典型领先形态。

    返回 (score0to3, detail or None)：
      score 表示当日背离强度（0~3），用于上层判断是否持续。
    """
    bars = _index_bars_upto(trade_date_str, 60)
    if bars is None or len(bars) < 25 or "amount" not in bars.columns:
        return 0, None

    closes = bars["close"].astype(float).tolist()
    amounts = bars["amount"].astype(float).tolist()
    if any(a is None or a <= 0 for a in amounts[-20:]):
        return 0, None

    cur_close = closes[-1]
    high20 = max(closes[-20:])
    # 高位：当日收盘在近20日高点的 -1.5% 以内
    near_high = high20 > 0 and (cur_close / high20 - 1) * 100 >= -1.5
    if not near_high:
        return 0, None

    vol5 = sum(amounts[-5:]) / 5
    vol20 = sum(amounts[-20:]) / 20
    if vol20 <= 0:
        return 0, None
    vol_contraction = (vol20 - vol5) / vol20  # >0 表示近5日量能低于20日均

    # 参与面：近5日上涨家数均值
    up5 = _avg_up_ratio(_trade_dates_upto(trade_date_str, 5))

    score = 0
    reasons = []
    # 条件1：高位缩量（量能退潮 ≥8%）
    if vol_contraction >= 0.08:
        score += 1
        reasons.append(f"高位缩量{vol_contraction*100:.0f}%")
    if vol_contraction >= 0.18:
        score += 1  # 缩量更明显，权重加重
    # 条件2：参与面退潮（上涨家数偏少）
    if up5 is not None and up5 < 0.42:
        score += 1
        reasons.append(f"5日上涨家数均{up5*100:.0f}%")

    # 必须「高位 + 缩量」同时成立才算背离（避免单纯宽度低误报）
    if vol_contraction < 0.08:
        return 0, None
    if score < 2:
        return 0, None

    detail = "指数高位但量能/参与退潮：" + "、".join(reasons)
    return min(score, 3), detail


def _vp_divergence_persistence(trade_date_str, window=5, need=3):
    """近 window 个交易日内，量价背离成立的天数（领先信号需持续才确认）。"""
    days = _trade_dates_upto(trade_date_str, window)
    if not days:
        return 0, None
    last_detail = None
    hits = 0
    for d in days:
        sc, det = _vol_price_divergence_score(d)
        if sc >= 2:
            hits += 1
            last_detail = det
    return hits, last_detail


def _avg_up_ratio(days):
    vals = [_up_ratio(d) for d in days]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


# -------------------------------------------------------
# 维度 1：资金集中度（前 5% 个股成交额占全市场比）
# -------------------------------------------------------
def _score_concentration(trade_date_str):
    """
    TuShare: daily 接口获取当日全市场所有股票的成交额
    取成交额排名前 5% 的个股，计算其成交额之和 / 全市场成交额
    """
    if PRO is None:
        return 10, None
    ratio = _concentration_ratio(trade_date_str)
    if ratio is None:
        return 10, None

    # 映射：50% → 10分, 52.1%(历史极值) → 20分, 45%以下 → 0分
    if ratio <= 0.45:
        score = 0
    elif ratio >= 0.521:
        score = 20
    else:
        score = (ratio - 0.45) / (0.521 - 0.45) * 20

    return round(score, 1), round(ratio * 100, 2)


# -------------------------------------------------------
# 维度 2：融资余额 / 总市值
# -------------------------------------------------------
def _score_margin(trade_date_str):
    """
    TuShare: margin 获取融资余额, daily_basic 获取总市值
    风险逻辑：融资占比越高 → 杠杆资金参与度越高 → 风险越大
    """
    if PRO is None:
        return 10, None
    try:
        mg = PRO.margin(trade_date=trade_date_str, fields="exchange_id,rzye")
    except Exception:
        mg = None
    try:
        db = PRO.daily_basic(trade_date=trade_date_str, fields="ts_code,total_mv")
    except Exception:
        db = None

    if mg is None or mg.empty or db is None or db.empty:
        return 10, None

    total_margin = mg["rzye"].sum()
    total_mv = db["total_mv"].sum() * 10000  # daily_basic 单位万元→元
    if total_mv == 0:
        return 10, None

    ratio = total_margin / total_mv  # e.g. 0.028

    # 映射：2.0% → 5分, 2.8% → 15分, 3.5% → 20分
    if ratio <= 0.02:
        score = 5
    elif ratio >= 0.035:
        score = 20
    else:
        score = 5 + (ratio - 0.02) / (0.035 - 0.02) * 15

    return round(score, 1), round(ratio * 100, 2)


# -------------------------------------------------------
# 维度 3：行业集中度（通信 + 电子成交额 / 全市场）
# -------------------------------------------------------
def _score_industry_concentration(trade_date_str):
    """
    TuShare: daily + stock_basic.industry
    筛选通信、电子行业，计算其成交额占比
    """
    if PRO is None:
        return 10, None
    ratio = _industry_ratio(trade_date_str)
    if ratio is None:
        return 10, None

    # 映射：15% → 5分(历史均值), 40% → 15分(当前), 50% → 20分
    if ratio <= 0.15:
        score = 5
    elif ratio >= 0.50:
        score = 20
    else:
        score = 5 + (ratio - 0.15) / (0.50 - 0.15) * 15

    return round(score, 1), round(ratio * 100, 2)


def _breadth_risk_score(up_ratio):
    """由上涨家数占比映射风险分（仅用于指数走弱时的同步杀跌）。"""
    if up_ratio >= 0.70:
        return 0.0
    if up_ratio >= 0.50:
        return 5 * (0.70 - up_ratio) / 0.20
    if up_ratio >= 0.25:
        return 5 + (0.50 - up_ratio) / 0.25 * 10
    return min(15 + (0.25 - up_ratio) / 0.25 * 5, 20)


def _severe_drop_score(severe_ratio):
    """跌幅≥5%个股占比 → 风险分。"""
    if severe_ratio <= 0.03:
        return 0.0
    if severe_ratio >= 0.15:
        return 20.0
    return (severe_ratio - 0.03) / (0.15 - 0.03) * 20


# -------------------------------------------------------
# 维度 4：恐慌扩散（大跌家数占比 + 指数走弱时的宽度修正）
# -------------------------------------------------------
def _score_market_stress(trade_date_str):
    """
    主指标：全市场跌幅≥5%个股占比。
    辅修正：指数收跌且上涨家数<40%时，叠加宽度惩罚（双杀日）。
    """
    if PRO is None:
        return 10, None

    stats = _get_daily_stats(trade_date_str)
    if not stats:
        return 10, None

    up_ratio = stats.get("up_ratio")
    severe_ratio = stats.get("severe_ratio")
    if up_ratio is None or severe_ratio is None:
        return 10, None

    severe_score = _severe_drop_score(severe_ratio)

    index_pct = _index_pct_chg(trade_date_str)
    sync_score = 0.0
    if index_pct is not None and index_pct < -0.3 and up_ratio < 0.40:
        sync_score = _breadth_risk_score(up_ratio)

    score = max(severe_score, sync_score)
    return round(score, 1), round(severe_ratio * 100, 2)


# -------------------------------------------------------
# 变动性信号（连续恶化 / 结构背离，最多 +15 分）
# -------------------------------------------------------
def _is_strictly_rising(values):
    return len(values) >= 2 and all(
        values[i] < values[i + 1] for i in range(len(values) - 1)
    )


def _score_momentum_signals(trade_date_str, industry_score):
    """
    捕捉「水平不高但趋势恶化」的风险，比单日静态值更有领先性。
    """
    signals = []
    if PRO is None:
        return signals, 0.0

    days4 = _trade_dates_upto(trade_date_str, 4)
    days5 = _trade_dates_upto(trade_date_str, 5)

    # 1. 资金集中度连续 3 日上升（5 日则加重）
    if len(days4) == 4:
        conc = [_concentration_ratio(d) for d in days4]
        if all(v is not None for v in conc) and _is_strictly_rising(conc):
            pts = 5.0
            if len(days5) == 5:
                conc5 = [_concentration_ratio(d) for d in days5]
                if all(v is not None for v in conc5) and _is_strictly_rising(conc5):
                    pts = 7.0
            signals.append(
                {
                    "id": "conc_rising_3d",
                    "label": "资金集中度连升",
                    "points": pts,
                    "detail": (
                        f"前5%成交占比 {conc[0]*100:.2f}%→{conc[-1]*100:.2f}%"
                        f"（连续{len(conc)-1}日上升）"
                    ),
                }
            )

    # 2. 科技成交占比连续 3 日上升（结构性抱团加剧）
    if len(days4) == 4:
        tech = [_industry_ratio(d) for d in days4]
        if all(v is not None for v in tech) and _is_strictly_rising(tech):
            signals.append(
                {
                    "id": "tech_rising_3d",
                    "label": "科技成交连升",
                    "points": 4.0,
                    "detail": (
                        f"通信+电子成交 {tech[0]*100:.1f}%→{tech[-1]*100:.1f}%"
                        f"（连续3日上升）"
                    ),
                }
            )

    # 3. 结构背离：指数收涨 + 上涨家数偏少 + 科技成交偏高
    up_ratio = _up_ratio(trade_date_str)
    index_pct = _index_pct_chg(trade_date_str)
    if (
        index_pct is not None
        and index_pct >= 0
        and up_ratio is not None
        and up_ratio < 0.35
        and industry_score >= 11
    ):
        signals.append(
            {
                "id": "structural_divergence",
                "label": "结构背离",
                "points": 5.0,
                "detail": (
                    f"上证{index_pct:+.2f}%但上涨家数仅{up_ratio*100:.1f}%，"
                    f"科技主线成交偏高"
                ),
            }
        )

    # 3b. 隐性走弱：指数平稳但大跌家数已扩散（3/2 型）
    stats = _get_daily_stats(trade_date_str)
    if stats and up_ratio is not None and index_pct is not None:
        severe_ratio = stats.get("severe_ratio")
        if (
            severe_ratio is not None
            and index_pct >= -0.1
            and up_ratio < 0.32
            and severe_ratio >= 0.05
        ):
            signals.append(
                {
                    "id": "hidden_weakness",
                    "label": "隐性走弱",
                    "points": 6.0,
                    "detail": (
                        f"上证{index_pct:+.2f}%但上涨仅{up_ratio*100:.1f}%、"
                        f"大跌家数{severe_ratio*100:.1f}%"
                    ),
                }
            )

    # 4. 宽度骤降：3 个交易日内上涨家数占比下降 ≥12pp
    if len(days4) == 4:
        breadths = [_up_ratio(d) for d in days4]
        if all(v is not None for v in breadths):
            drop = breadths[0] - breadths[-1]
            idx_vals = [_index_pct_chg(d) for d in days4]
            idx_sum = sum(v for v in idx_vals if v is not None)
            if drop >= 0.12 and idx_sum >= -0.5:
                signals.append(
                    {
                        "id": "breadth_collapse_3d",
                        "label": "宽度骤降",
                        "points": 4.0,
                        "detail": (
                            f"上涨家数占比 {breadths[0]*100:.1f}%→{breadths[-1]*100:.1f}%"
                            f"（3日降{drop*100:.1f}pp）"
                        ),
                    }
                )

    bonus = min(sum(s["points"] for s in signals), 15.0)
    if bonus < sum(s["points"] for s in signals):
        # 按 points 降序保留，使总和不超过 15
        kept, used = [], 0.0
        for s in sorted(signals, key=lambda x: x["points"], reverse=True):
            if used + s["points"] <= 15.0:
                kept.append(s)
                used += s["points"]
        signals = kept
        bonus = used

    return signals, round(bonus, 1)


# -------------------------------------------------------
# 累积风险（慢变量，最多 +18 分，不因单日反弹清零）
# -------------------------------------------------------
def _score_accumulation_risk(trade_date_str):
    signals = []
    if PRO is None:
        return signals, 0.0

    dist250 = _index_distance_from_high(trade_date_str, 250)
    dist60 = _index_distance_from_high(trade_date_str, 60)
    bonus = 0.0

    if dist250 is not None:
        if dist250 >= -2:
            bonus += 6
            signals.append(
                {
                    "id": "near_250d_high",
                    "label": "近一年高位",
                    "points": 6,
                    "detail": f"距250日高点仅 {abs(dist250):.1f}%",
                }
            )
        elif dist250 >= -5:
            bonus += 4
            signals.append(
                {
                    "id": "elevated_250d",
                    "label": "一年高位区",
                    "points": 4,
                    "detail": f"距250日高点 {abs(dist250):.1f}%",
                }
            )

    near_high = (dist250 is not None and dist250 >= -8) or (
        dist60 is not None and dist60 >= -3
    )
    if not near_high:
        return signals, round(min(bonus, 18.0), 1)

    days5 = _trade_dates_upto(trade_date_str, 5)
    days20 = _trade_dates_upto(trade_date_str, 20)

    if len(days20) == 20:
        concs = [_concentration_ratio(d) for d in days20]
        valid = [c for c in concs if c is not None]
        if valid:
            avg_conc = sum(valid) / len(valid)
            lookback = _sampled_concentration_history(trade_date_str, window=60, step=5)
            pct = _percentile_rank(avg_conc, lookback)
            if pct is not None and pct >= 0.75:
                bonus += 5
                signals.append(
                    {
                        "id": "conc_crowding",
                        "label": "资金长期拥挤",
                        "points": 5,
                        "detail": f"20日均成交集中度 {avg_conc*100:.1f}%（近60日高位）",
                    }
                )

    if len(days20) >= 2:
        m0 = _margin_ratio_raw(days20[0])
        m1 = _margin_ratio_raw(days20[-1])
        if m0 and m1 and m0 > 0:
            chg = (m1 - m0) / m0 * 100
            if chg >= 8:
                bonus += 6
                signals.append(
                    {
                        "id": "margin_buildup",
                        "label": "杠杆累积",
                        "points": 6,
                        "detail": f"融资占比20日升 {chg:.1f}%",
                    }
                )

    if len(days5) == 5 and len(days20) == 20:
        avg5 = _avg_up_ratio(days5)
        avg20 = _avg_up_ratio(days20)
        if avg5 is not None and avg20 is not None and avg5 < avg20 - 0.06:
            bonus += 4
            signals.append(
                {
                    "id": "breadth_narrowing",
                    "label": "宽度持续收窄",
                    "points": 4,
                    "detail": (
                        f"5日上涨占比 {avg5*100:.1f}% < 20日均 {avg20*100:.1f}%"
                    ),
                }
            )

    bonus = min(bonus, 18.0)
    if bonus < sum(s["points"] for s in signals):
        kept, used = [], 0.0
        for s in sorted(signals, key=lambda x: x["points"], reverse=True):
            if used + s["points"] <= 18.0:
                kept.append(s)
                used += s["points"]
        signals = kept
        bonus = used

    return signals, round(bonus, 1)


# -------------------------------------------------------
# 硬触发（结构/破位分轨底线）
# -------------------------------------------------------
def _evaluate_hard_triggers(trade_date_str, dimensions, sentiment_score, bull_trend=False):
    triggers = []
    if PRO is None:
        return triggers, 0.0, 0.0

    dist60 = _index_distance_from_high(trade_date_str, 60)
    dist250 = _index_distance_from_high(trade_date_str, 250)
    up = _up_ratio(trade_date_str)
    index_pct = _index_pct_chg(trade_date_str)
    stats = _get_daily_stats(trade_date_str)
    severe_ratio = stats.get("severe_ratio") if stats else None
    days5 = _trade_dates_upto(trade_date_str, 5)
    days20 = _trade_dates_upto(trade_date_str, 20)
    avg5 = _avg_up_ratio(days5) if len(days5) == 5 else None
    avg20 = _avg_up_ratio(days20) if len(days20) == 20 else None

    conc_val = dimensions.get("concentration", {}).get("value")
    conc_ratio = conc_val / 100 if conc_val else _concentration_ratio(trade_date_str)

    near60 = dist60 is not None and dist60 >= -1.5
    near250 = dist250 is not None and dist250 >= -3
    breakdown_confirmed = (
        (index_pct is not None and index_pct < -0.3)
        or (
            severe_ratio is not None
            and severe_ratio >= 0.08
            and index_pct is not None
            and index_pct < 0.15
        )
        or (
            up is not None
            and up < 0.32
            and index_pct is not None
            and index_pct < -0.1
        )
    )

    # 顶背离：新高区域 + 参与面收窄
    if (
        near60
        and avg5 is not None
        and avg20 is not None
        and avg5 < avg20 - 0.05
        and (up is None or up < 0.55)
    ):
        triggers.append(
            {
                "id": "top_divergence",
                "track": "structure",
                "label": "高位顶背离",
                "floor": 58.0,
                "detail": "指数高位但上涨家数趋势收窄",
            }
        )

    # 高位拥挤：一年高位 + 资金集中偏高
    if near250 and conc_ratio is not None:
        lookback = _sampled_concentration_history(trade_date_str, window=60, step=5)
        cur = _concentration_ratio(trade_date_str)
        pct = _percentile_rank(cur, lookback) if cur is not None else None
        if (conc_ratio >= 0.46) or (pct is not None and pct >= 0.80):
            triggers.append(
                {
                    "id": "crowding_at_high",
                    "track": "structure",
                    "label": "高位拥挤",
                    "floor": 62.0,
                    "detail": f"近一年高位区，成交集中度 {conc_ratio*100:.1f}%",
                }
            )

    # 杠杆冲刺：2015 型
    if len(days20) >= 2 and near60:
        m0 = _margin_ratio_raw(days20[0])
        m1 = _margin_ratio_raw(days20[-1])
        if m0 and m1 and m0 > 0 and (m1 - m0) / m0 >= 0.10:
            triggers.append(
                {
                    "id": "leverage_blowoff",
                    "track": "breakdown",
                    "label": "杠杆冲刺",
                    "floor": 68.0,
                    "detail": f"融资占比20日升 {(m1-m0)/m0*100:.1f}%",
                }
            )

    # 亢奋见顶：高位 + 情绪过热
    sent_score = dimensions.get("sentiment", {}).get("score", 10)
    if near60 and sentiment_score is not None and sentiment_score >= 0.35:
        if sent_score >= 13 or (conc_ratio and conc_ratio >= 0.45):
            triggers.append(
                {
                    "id": "euphoria_top",
                    "track": "structure",
                    "label": "亢奋见顶",
                    "floor": 60.0,
                    "detail": f"高位区情绪 {sentiment_score:+.2f} 偏亢奋",
                }
            )

    # 长期背景高危：250日高位 + 两维以上基础分偏高
    high_dims = sum(
        1
        for k in ("concentration", "industry", "margin")
        if dimensions.get(k, {}).get("score", 0) >= 12
    )
    if near250 and high_dims >= 2:
        triggers.append(
            {
                "id": "background_risk",
                "track": "structure",
                "label": "顶部背景风险",
                "floor": 60.0,
                "detail": "高位区多维度风险共振",
            }
        )

    core_struct = [t for t in triggers if t.get("track") == "structure"]
    core_break = [t for t in triggers if t.get("track") == "breakdown"]
    core_count = len(core_struct) + len(core_break)
    if core_count >= 2 and (breakdown_confirmed or not bull_trend):
        max_floor = max(t["floor"] for t in triggers)
        triggers.append(
            {
                "id": "extreme_combo",
                "track": "breakdown" if breakdown_confirmed else "structure",
                "label": "复合极端",
                "floor": min(max(max_floor, 72.0), 85.0),
                "detail": f"{core_count}项顶部信号共振",
            }
        )
    elif core_count >= 2 and bull_trend:
        triggers.append(
            {
                "id": "extreme_combo",
                "track": "structure",
                "label": "结构共振",
                "floor": 48.0,
                "detail": f"{core_count}项拥挤信号共振（主升趋势，观察为主）",
            }
        )

    structure_floor = 0.0
    breakdown_floor = 0.0
    for t in triggers:
        f = t["floor"]
        if t.get("track") == "breakdown":
            breakdown_floor = max(breakdown_floor, f * 0.45)
        else:
            structure_floor = max(structure_floor, f * 0.5)

    structure_floor = min(structure_floor, 50.0)
    breakdown_floor = min(breakdown_floor, 50.0)
    floor_score = round(structure_floor + breakdown_floor, 1)
    return triggers, floor_score, structure_floor, breakdown_floor


# -------------------------------------------------------
# 维度 5：论坛情绪（反向映射：太乐观 → 高风险）
# -------------------------------------------------------
def _score_sentiment(sentiment_score):
    """
    将现有的 -1 到 +1 情绪分反向映射到风险分
    极度乐观(+0.5) → 高风险 → 20分
    极度悲观(-0.3) → 低风险 → 0分
    中性(0) → 中位 → 10分
    """
    # 把 [-1, 1] 线性映射到 [0, 20]，但正向 = 20 表示更危险
    # 乐观端(+1) → 20，中性(0) → 10，悲观端(-1) → 0
    if sentiment_score >= 1.0:
        score = 20
    elif sentiment_score <= -1.0:
        score = 0
    else:
        score = (sentiment_score + 1) / 2 * 20  # [-1,1] → [0,20]

    return round(score, 1), round(sentiment_score, 4)


# -------------------------------------------------------
# 综合评分 & 风险等级
# -------------------------------------------------------
def risk_level(structure_score, breakdown_score, total_score):
    """等级由破位分主导，结构分高仅预警。"""
    if breakdown_score >= 35 or (total_score >= 72 and breakdown_score >= 25):
        return "⛔ 极端", "破位风险极高，建议大幅减仓/对冲"
    if breakdown_score >= 22 or (total_score >= 58 and breakdown_score >= 15):
        return "🔴 紧急", "市场出现扩散性走弱，建议尽快减仓"
    if structure_score >= 30 or total_score >= 42:
        if breakdown_score < 15 and structure_score >= 30:
            return (
                "🟡 预警",
                "结构拥挤偏高，主升趋势中观察为主，不宜追高",
            )
        return "🟡 预警", "风险升高，逐步收紧仓位、收紧止盈"
    if total_score >= 28:
        return "🟢 中性", "正常持仓，密切关注"
    return "🟢 安全", "市场健康，可正常操作"


def compute_risk_score(trade_date_str=None, sentiment_score=None):
    """
    计算大盘综合风险分 (0-100)

    参数:
        trade_date_str: YYYYMMDD 格式交易日，默认最近交易日
        sentiment_score: 论坛情绪分 -1 到 +1，None 则此维度取中位分

    返回:
        dict {
            "total_score": 68.5,
            "level": "🟡 预警",
            "advice": "逐步收紧仓位，收紧止盈",
            "dimensions": {
                "concentration": {"score": 18, "value": 51.2, "label": "资金集中度"},
                ...
            },
            "details": { ... }
        }
    """
    if trade_date_str is None:
        target = _last_trade_date(require_data=True)
        trade_date_str = target.strftime("%Y%m%d")
    else:
        target = datetime.strptime(trade_date_str, "%Y%m%d").date()
        target = _last_trade_date(target, require_data=True)
        trade_date_str = target.strftime("%Y%m%d")

    if PRO is None:
        print("  [RiskScorer] 警告: 未配置 TUSHARE_TOKEN，风险维度将使用中位分占位。")

    print(f"\n  [RiskScorer] 计算 {target} 大盘风险分...")

    dimensions = {}

    # 1. 资金集中度
    s1, v1 = _score_concentration(trade_date_str)
    dimensions["concentration"] = {
        "score": s1,
        "value": v1,
        "label": "资金集中度",
        "detail": (f"前5%个股成交额占全市场 {v1}%" if v1 is not None else "成交数据暂无（取中位分）"),
        "thresholds": {"warning": 50, "danger": 52},
    }

    # 2. 融资占比
    s2, v2 = _score_margin(trade_date_str)
    dimensions["margin"] = {
        "score": s2,
        "value": v2,
        "label": "融资余额占比",
        "detail": (f"融资余额/总市值 = {v2}%" if v2 is not None else "融资数据暂无（取中位分）"),
        "thresholds": {"warning": 2.5, "danger": 3.0},
    }

    # 3. 行业集中度
    s3, v3 = _score_industry_concentration(trade_date_str)
    dimensions["industry"] = {
        "score": s3,
        "value": v3,
        "label": "行业集中度",
        "detail": (f"通信+电子成交占全市场 {v3}%" if v3 is not None else "行业成交数据暂无（取中位分）"),
        "thresholds": {"warning": 30, "danger": 40},
    }

    # 4. 恐慌扩散
    s4, v4 = _score_market_stress(trade_date_str)
    dimensions["market_stress"] = {
        "score": s4,
        "value": v4,
        "label": "恐慌扩散",
        "detail": (f"跌幅≥5%个股占比 {v4}%" if v4 is not None else "行情数据暂无（取中位分）"),
        "thresholds": {"warning": 8, "danger": 12},
    }

    # 5. 情绪分
    if sentiment_score is not None:
        s5, v5 = _score_sentiment(sentiment_score)
    else:
        s5, v5 = 10, 0  # 默认中位
    dimensions["sentiment"] = {
        "score": s5,
        "value": v5,
        "label": "论坛情绪",
        "detail": f"情绪分 {v5:+.4f}",
        "thresholds": {"warning": 0.3, "danger": 0.5},
    }

    base_score = round(sum(d["score"] for d in dimensions.values()), 1)
    signals, momentum_bonus = _score_momentum_signals(trade_date_str, s3)
    accum_signals, accum_bonus = _score_accumulation_risk(trade_date_str)
    all_signals = signals + accum_signals
    bull_trend = _is_bull_trend(trade_date_str)
    hard_triggers, floor_score, structure_floor, breakdown_floor = _evaluate_hard_triggers(
        trade_date_str, dimensions, sentiment_score, bull_trend=bull_trend
    )

    struct_mom_signals, break_mom_signals = _split_signals(signals, trade_date_str)
    struct_accum_signals, _ = _split_signals(accum_signals, trade_date_str)
    struct_mom = _cap_signal_bonus(struct_mom_signals, 10.0)
    break_mom = _cap_signal_bonus(break_mom_signals, 15.0)
    struct_accum = _cap_signal_bonus(struct_accum_signals, 10.0)

    structure_raw = (
        _structure_from_dimensions(dimensions) + struct_mom + struct_accum
    )
    breakdown_raw = (
        _breakdown_from_dimensions(dimensions)
        + break_mom
        + _breakdown_index_boost(trade_date_str)
    )

    structure_score = round(min(max(structure_raw, structure_floor), 50), 1)
    breakdown_score = round(min(max(breakdown_raw, breakdown_floor), 50), 1)

    # 顶部派发领先信号：高位量价背离持续（近5日≥3天）
    # 回测显示零误报、对缩量派发型顶部可提前数日，故确认时拉一档结构预警，
    # 但不顶到紧急/极端（那两档仍保留给真实破位）。
    vp_hits, vp_detail = _vp_divergence_persistence(trade_date_str, window=5, need=3)
    distribution_leading = vp_hits >= 3
    if distribution_leading:
        structure_score = round(min(max(structure_score, 42.0), 50), 1)

    total_score = _dual_total(structure_score, breakdown_score, bull_trend)

    snapshot_score = round(min(base_score + momentum_bonus + accum_bonus, 100), 1)
    level, advice = risk_level(structure_score, breakdown_score, total_score)
    if distribution_leading and breakdown_score < 22:
        # 破位未确认时，用派发专属建议覆盖泛化的结构建议
        if "安全" in level or "中性" in level:
            level = "🟡 预警"
        advice = "高位量价背离持续（顶部派发领先信号），建议分批减仓、严守止盈、勿追高"

    print(f"  [RiskScorer] 综合风险分: {total_score} — {level}")
    print(
        f"    结构拥挤 {structure_score} + 破位风险 {breakdown_score}"
        + (" | 多头趋势熔断" if bull_trend else "")
    )
    print(
        f"    (旧口径参考: 基础 {base_score} + 变动 {momentum_bonus} + 累积 {accum_bonus}"
        + (f" | 硬触发底线 {floor_score}" if floor_score else "")
        + ")"
    )
    if distribution_leading:
        print(f"    🔻 顶部派发(领先) | {vp_detail}（近5日{vp_hits}天背离）")
    for sig in all_signals:
        print(f"    ⚡ {sig['label']} +{sig['points']} | {sig['detail']}")
    for trig in hard_triggers:
        if trig["id"] != "extreme_combo" or len(hard_triggers) >= 2:
            print(f"    🚨 {trig['label']} → 底线 {trig['floor']} | {trig['detail']}")

    return {
        "total_score": total_score,
        "structure_score": structure_score,
        "breakdown_score": breakdown_score,
        "bull_trend": bull_trend,
        "distribution_leading": distribution_leading,
        "distribution_detail": (vp_detail if distribution_leading else None),
        "distribution_days": vp_hits,
        "base_score": base_score,
        "momentum_bonus": momentum_bonus,
        "accumulation_bonus": accum_bonus,
        "floor_score": floor_score,
        "structure_floor": structure_floor,
        "breakdown_floor": breakdown_floor,
        "snapshot_score": snapshot_score,
        "signals": all_signals,
        "hard_triggers": hard_triggers,
        "level": level,
        "advice": advice,
        "trade_date": target.strftime("%Y-%m-%d"),
        "dimensions": dimensions,
    }


# -------------------------------------------------------
# 独立测试
# -------------------------------------------------------
if __name__ == "__main__":
    result = compute_risk_score(sentiment_score=0.08)
    print(json.dumps(result, ensure_ascii=False, indent=2))
