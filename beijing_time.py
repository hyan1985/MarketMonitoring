"""全项目统一使用北京时间 (Asia/Shanghai)。"""

from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_beijing():
    """当前北京时间（带时区）。"""
    return datetime.now(BEIJING_TZ)


def now_beijing_naive():
    """当前北京时间（无时区，供旧逻辑兼容）。"""
    return now_beijing().replace(tzinfo=None)


def today_beijing():
    """当前北京日期。"""
    return now_beijing().date()


def format_beijing(dt=None, fmt="%Y-%m-%d %H:%M:%S"):
    """格式化为北京时间字符串。"""
    if dt is None:
        dt = now_beijing()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        dt = dt.astimezone(BEIJING_TZ)
    return dt.strftime(fmt)


def epoch_to_beijing_str(ts, fmt="%m-%d %H:%M"):
    """Unix 时间戳 → 北京时间字符串。"""
    try:
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(float(ts), BEIJING_TZ).strftime(fmt)
    except Exception:
        return ""
