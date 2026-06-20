import random
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from crawler_utils import parse_number, random_user_agent, strip_html

SOURCE = "ths"


def extract_hexin_v(cookie="", hexin_v=""):
    """hexin-v 与同花顺 Cookie 里的 v= 相同，无需单独找请求头。"""
    hexin_v = (hexin_v or "").strip()
    if hexin_v:
        return hexin_v
    if not cookie:
        return ""
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("v="):
            return part[2:].strip()
    return ""


class ThsCrawler:
    """Crawl Tonghuashun (同花顺) 论股堂 via getPostList (returns HTML fragments)."""

    API_URL = "https://t.10jqka.com.cn/newcircle/post/getPostList/"

    def __init__(self, code="1a0001", cookie="", hexin_v=""):
        self.code = code.lower()
        self.cookie = cookie.strip()
        self.hexin_v = extract_hexin_v(cookie=self.cookie, hexin_v=hexin_v)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "User-Agent": random_user_agent(),
                "Referer": f"https://t.10jqka.com.cn/pc/newgroup/stock/{self.code}/",
            }
        )
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie
        if self.hexin_v:
            self.session.headers["hexin-v"] = self.hexin_v

    def _auth_ready(self):
        return bool(self.cookie and self.hexin_v)

    def fetch_page(self, page_num, page_size=20):
        print(f"  [THS] Fetching page {page_num} (stockcode={self.code})...")
        if not self._auth_ready():
            print(
                "  [THS] 未配置 ths_cookie。请在浏览器登录同花顺论股堂后，"
                "复制完整 Cookie 到 config.json（脚本会自动从 v= 生成 hexin-v）",
                file=sys.stderr,
            )
            return []

        try:
            response = self.session.get(
                self.API_URL,
                params={"stockcode": self.code, "page": page_num, "limit": page_size},
                timeout=12,
            )
            if response.status_code != 200:
                print(f"  [THS] Error: status {response.status_code}", file=sys.stderr)
                return []

            data = response.json()
            if data.get("errorCode") not in (0, "0"):
                msg = data.get("errorMsg") or data.get("errorCode")
                print(f"  [THS] API error: {msg}", file=sys.stderr)
                if data.get("errorCode") in (-10001, -1):
                    print(
                        "  [THS] 提示: Cookie 可能过期或未登录，请重新复制浏览器 Cookie",
                        file=sys.stderr,
                    )
                return []

            result = data.get("result") or {}
            html = result.get("html") if isinstance(result, dict) else ""
            if not html:
                return []

            posts = self._parse_html(html)
            print(f"  [THS] Parsed {len(posts)} posts from page {page_num}.")
            return posts
        except Exception as e:
            print(f"  [THS] Exception on page {page_num}: {e}", file=sys.stderr)
            return []

    def _parse_html(self, html):
        soup = BeautifulSoup(html, "html.parser")
        posts = []
        for li in soup.select("li.post-single"):
            post = self._parse_item(li)
            if post:
                posts.append(post)
        return posts

    def _parse_item(self, li):
        main_a = li.select_one("a.single-main")
        if not main_a:
            return None

        post_id = main_a.get("data-pid") or ""
        title = strip_html(main_a.select_one(".post-title").get_text() if main_a.select_one(".post-title") else "")
        content = strip_html(main_a.select_one(".post-content").get_text() if main_a.select_one(".post-content") else "")
        display_title = title or content
        if content and content not in display_title and len(content) > 10:
            display_title = f"{display_title} {content[:80]}".strip()
        if len(display_title) > 160:
            display_title = display_title[:160] + "..."
        if not display_title:
            return None

        author = "匿名"
        img = li.select_one("img[usercard]")
        if img and img.get("usercard"):
            m = re.search(r"userid=(\d+)", img.get("usercard", ""))
            if m:
                author = f"股友{m.group(1)}"

        time_raw = strip_html(li.select_one(".post-time").get_text() if li.select_one(".post-time") else "")
        time_str = self._normalize_time(time_raw)

        read_count = 0
        scan = li.select_one(".scan-count")
        if scan:
            read_count = parse_number(scan.get_text())

        href = main_a.get("href") or ""
        if href and not href.startswith("http"):
            href = "https://t.10jqka.com.cn" + href

        return {
            "post_id": f"ths_{post_id}" if post_id else f"ths_{hash(display_title)}",
            "title": display_title,
            "read_count": read_count,
            "reply_count": 0,
            "author": author,
            "time": time_str,
            "href": href,
            "source": SOURCE,
        }

    def _normalize_time(self, time_raw):
        time_raw = (time_raw or "").strip()
        if not time_raw:
            return ""
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", time_raw)
        if m:
            return f"{m.group(2)}-{m.group(3)} 00:00"
        m = re.match(r"(\d{2})-(\d{2})\s+(\d{2}:\d{2})", time_raw)
        if m:
            return f"{m.group(1)}-{m.group(2)} {m.group(3)}"
        if re.match(r"\d{2}:\d{2}", time_raw):
            return time_raw
        return time_raw

    def crawl_multiple_pages(self, num_pages=5, page_size=20, max_posts=None):
        if not self._auth_ready():
            print("[THS] Completed. Total unique posts collected: 0 (未配置 Cookie)")
            return []

        all_posts = []
        seen_ids = set()
        for page in range(1, num_pages + 1):
            posts = self.fetch_page(page, page_size=page_size)
            if not posts:
                break
            for post in posts:
                pid = post["post_id"]
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_posts.append(post)
                    if max_posts and len(all_posts) >= max_posts:
                        print(f"[THS] Reached max_posts={max_posts}, stopping early.")
                        print(f"[THS] Completed. Total unique posts collected: {len(all_posts)}")
                        return all_posts
            if page < num_pages:
                time.sleep(random.uniform(0.4, 1.0))

        print(f"[THS] Completed. Total unique posts collected: {len(all_posts)}")
        return all_posts


if __name__ == "__main__":
    import json
    import os

    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    crawler = ThsCrawler(
        code=cfg.get("ths_code", "1a0001"),
        cookie=cfg.get("ths_cookie", ""),
        hexin_v=cfg.get("ths_hexin_v", ""),
    )
    print(crawler.crawl_multiple_pages(2))
