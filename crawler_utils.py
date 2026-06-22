import random
import re
from datetime import datetime

from beijing_time import today_beijing, epoch_to_beijing_str

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


def random_user_agent():
    return random.choice(USER_AGENTS)


def parse_number(text):
    """Parse counts like 1.2万 / 3k from forum listings."""
    if not text:
        return 0
    text = str(text).strip().lower()
    try:
        if "万" in text or "w" in text:
            num_str = re.findall(r"[\d\.]+", text)
            if num_str:
                return int(float(num_str[0]) * 10000)
        if "k" in text:
            num_str = re.findall(r"[\d\.]+", text)
            if num_str:
                return int(float(num_str[0]) * 1000)
        num_str = re.findall(r"\d+", text)
        if num_str:
            return int(num_str[0])
    except Exception:
        pass
    return 0


def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def format_timestamp_ms(ts_ms):
    """Format millisecond epoch to MM-DD HH:MM (北京时间)."""
    return epoch_to_beijing_str(ts_ms)


def format_timestamp_sec(ts_sec):
    return epoch_to_beijing_str(ts_sec)


def calc_pages(target_posts, per_page):
    if target_posts <= 0 or per_page <= 0:
        return 1
    return max(1, (target_posts + per_page - 1) // per_page)


def normalize_post_date(time_str, reference_date=None):
    """Parse forum time strings into YYYY-MM-DD (uses reference_date's year when needed)."""
    reference_date = reference_date or today_beijing()
    time_str = (time_str or "").strip()
    if not time_str:
        return None

    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", time_str)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    current_year = reference_date.year

    match = re.search(r"(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", time_str)
    if match:
        month, day = match.group(1), match.group(2)
        return f"{current_year}-{month}-{day}"

    match = re.search(r"(\d{2})-(\d{2})", time_str)
    if match:
        month, day = match.group(1), match.group(2)
        return f"{current_year}-{month}-{day}"

    if re.search(r"\d{2}:\d{2}", time_str):
        return reference_date.strftime("%Y-%m-%d")

    return None


def filter_posts_for_run_date(posts, run_date=None):
    """Keep only posts whose timestamp falls on the script run date."""
    run_date = run_date or today_beijing()
    target = run_date.strftime("%Y-%m-%d")
    kept = []
    skipped_by_source = {}

    for post in posts:
        post_date = normalize_post_date(post.get("time", ""), reference_date=run_date)
        if post_date == target:
            kept.append(post)
        else:
            source = post.get("source", "unknown")
            skipped_by_source[source] = skipped_by_source.get(source, 0) + 1

    return kept, len(posts) - len(kept), skipped_by_source, target


def page_dates_for_run_date(posts, run_date):
    """Normalize listing timestamps on one page to YYYY-MM-DD strings."""
    dates = []
    for post in posts:
        post_date = normalize_post_date(post.get("time", ""), reference_date=run_date)
        if post_date:
            dates.append(post_date)
    return dates


def should_stop_crawl_for_run_date(page_posts, run_date, found_target_date):
    """
    Return True when crawling should stop after this page.
    Stop once we've seen the run_date and this page reaches the previous day.
    """
    if not found_target_date:
        return False
    dates = page_dates_for_run_date(page_posts, run_date)
    if not dates:
        return False
    target = run_date.strftime("%Y-%m-%d")
    return min(dates) < target


def merge_posts(post_lists):
    """Merge posts from multiple crawlers, dedupe by source + post_id."""
    merged = []
    seen = set()
    for posts in post_lists:
        for post in posts:
            source = post.get("source", "unknown")
            post_id = str(post.get("post_id", ""))
            title = post.get("title", "")
            key = (source, post_id) if post_id else (source, title)
            if key in seen:
                continue
            seen.add(key)
            merged.append(post)
    return merged
