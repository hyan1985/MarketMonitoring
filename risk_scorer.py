"""
大盘风险值综合评分模块
使用 TuShare Pro API 获取多维数据，计算 0-100 的综合风险分。

五个维度（各 0-20 分）：
1. 资金集中度 — 前5%个股成交额/全市场成交额
2. 融资占比 — 融资余额/总市值
3. 行业集中度 — 通信+电子成交额/全市场
4. 市场宽度 — 上涨家数占比
5. 情绪分 — 论坛情绪反向映射（太乐观→高风险）
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
    df = PRO.daily(trade_date=trade_date_str, fields="ts_code,amount")
    if df.empty:
        return 10, None  # 无数据，不显示 0%

    df = df.dropna(subset=["amount"])
    total_amount = df["amount"].sum()
    if total_amount == 0:
        return 10, None

    df_sorted = df.sort_values("amount", ascending=False)
    top_n = max(1, int(len(df_sorted) * 0.05))
    top_amount = df_sorted["amount"].iloc[:top_n].sum()
    ratio = top_amount / total_amount  # 0-1

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
    df = PRO.daily(trade_date=trade_date_str, fields="ts_code,amount")
    if df.empty:
        return 10, None

    industry_map = _load_industry_map()
    tech_codes = {
        code
        for code, ind in industry_map.items()
        if ind in ("通信设备", "通信服务", "电子元器件", "半导体", "元器件")
    }

    df_tech = df[df["ts_code"].isin(tech_codes)]
    total_amount = df["amount"].sum()
    tech_amount = df_tech["amount"].sum()

    if total_amount == 0:
        return 10, None

    ratio = tech_amount / total_amount

    # 映射：15% → 5分(历史均值), 40% → 15分(当前), 50% → 20分
    if ratio <= 0.15:
        score = 5
    elif ratio >= 0.50:
        score = 20
    else:
        score = 5 + (ratio - 0.15) / (0.50 - 0.15) * 15

    return round(score, 1), round(ratio * 100, 2)


# -------------------------------------------------------
# 维度 4：市场宽度（上涨家数占比）
# -------------------------------------------------------
def _score_breadth(trade_date_str):
    """
    TuShare: daily.pct_chg
    统计全市场上涨家数 / 总家数，比值越低 → 市场越弱 → 风险越高
    """
    df = PRO.daily(trade_date=trade_date_str, fields="ts_code,pct_chg")
    if df.empty:
        return 10, None

    total = len(df)
    up = len(df[df["pct_chg"] > 0])
    ratio = up / total if total > 0 else 0.5

    # 映射：上涨>70% → 0分, 50% → 5分, 25% → 15分, <15% → 20分
    if ratio >= 0.70:
        score = 0
    elif ratio >= 0.50:
        score = 5 * (0.70 - ratio) / 0.20
    elif ratio >= 0.25:
        score = 5 + (0.50 - ratio) / 0.25 * 10
    else:
        score = 15 + (0.25 - ratio) / 0.25 * 5
        score = min(score, 20)

    return round(score, 1), round(ratio * 100, 2)


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
def risk_level(total_score):
    if total_score >= 70:
        return "🔴 高危", "建议大幅减仓 / 对冲保护"
    elif total_score >= 50:
        return "🟡 预警", "逐步收紧仓位，收紧止盈"
    elif total_score >= 30:
        return "🟢 中性", "正常持仓，密切关注"
    else:
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
        "detail": f"前5%个股成交额占全市场 {v1}%",
        "thresholds": {"warning": 50, "danger": 52},
    }

    # 2. 融资占比
    s2, v2 = _score_margin(trade_date_str)
    dimensions["margin"] = {
        "score": s2,
        "value": v2,
        "label": "融资余额占比",
        "detail": f"融资余额/总市值 = {v2}%",
        "thresholds": {"warning": 2.5, "danger": 3.0},
    }

    # 3. 行业集中度
    s3, v3 = _score_industry_concentration(trade_date_str)
    dimensions["industry"] = {
        "score": s3,
        "value": v3,
        "label": "行业集中度",
        "detail": f"通信+电子成交占全市场 {v3}%",
        "thresholds": {"warning": 30, "danger": 40},
    }

    # 4. 市场宽度
    s4, v4 = _score_breadth(trade_date_str)
    dimensions["breadth"] = {
        "score": s4,
        "value": v4,
        "label": "市场宽度",
        "detail": f"上涨家数占比 {v4}%",
        "thresholds": {"warning": 35, "danger": 20},
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

    total_score = sum(d["score"] for d in dimensions.values())
    total_score = round(min(total_score, 100), 1)

    level, advice = risk_level(total_score)

    print(f"  [RiskScorer] 综合风险分: {total_score} — {level}")

    return {
        "total_score": total_score,
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
