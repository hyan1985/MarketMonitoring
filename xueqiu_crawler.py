import random
import re
import sys
import time

import requests

from crawler_utils import format_timestamp_ms, random_user_agent, strip_html

SOURCE = "xueqiu"


class XueqiuCrawler:
    """Crawl Xueqiu (雪球) symbol discussion feed via the public status API."""

    API_URL = "https://xueqiu.com/query/v1/symbol/search/status"

    def __init__(self, symbol="SH000001", cookie=""):
        self.symbol = symbol
        self.cookie = (cookie or "").strip()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "User-Agent": random_user_agent(),
                "Referer": f"https://xueqiu.com/S/{self.symbol}",
            }
        )
        if self.cookie:
            self.session.headers["Cookie"] = self.cookie

    def _has_auth_cookie(self):
        """Rough check that login-related cookies are present."""
        lower = self.cookie.lower()
        return any(k in lower for k in ("xq_a_token", "xqat", "xq_r_token", "u="))

    def _warn_missing_cookie(self):
        print(
            "  [Xueqiu] 未配置 xueqiu_cookie。请在浏览器登录雪球后，"
            "从开发者工具复制 Cookie 填入 config.json 的 xueqiu_cookie 字段。",
            file=sys.stderr,
        )

    def _warmup(self):
        self.session.get(
            f"https://xueqiu.com/S/{self.symbol}",
            headers={"Referer": "https://xueqiu.com/"},
            timeout=10,
        )

    def fetch_page(self, page_num, page_size=20):
        print(f"  [Xueqiu] Fetching page {page_num} (symbol={self.symbol})...")
        try:
            response = self.session.get(
                self.API_URL,
                params={"symbol": self.symbol, "page": page_num, "size": page_size},
                headers={"Referer": f"https://xueqiu.com/S/{self.symbol}"},
                timeout=12,
            )
            if response.status_code != 200:
                print(
                    f"  [Xueqiu] Error: status {response.status_code} on page {page_num}",
                    file=sys.stderr,
                )
                if page_num == 1 and not self.cookie:
                    self._warn_missing_cookie()
                elif page_num == 1 and response.status_code in (401, 403):
                    print(
                        "  [Xueqiu] Cookie 可能已过期，请重新登录雪球并更新 xueqiu_cookie。",
                        file=sys.stderr,
                    )
                return []

            text = (response.text or "").strip()
            if not text or text[0] not in "{[":
                # Xueqiu API is protected by Aliyun WAF and returns an HTML challenge page.
                # In this case, requests.json() will never work reliably without running JS in a real browser.
                if "aliyun_waf" in text.lower():
                    print(
                        "  [Xueqiu] 接口被 Aliyun WAF 拦截：返回 HTML challenge（非 JSON）。"
                        "仅靠 Cookie 可能也无法通过；需要改用浏览器/Playwright 渲染抓取，"
                        "或暂时关闭 xueqiu 数据源。",
                        file=sys.stderr,
                    )
                    return []
                if page_num == 1:
                    print(
                        f"  [Xueqiu] 返回非 JSON（前 80 字）: {text[:80]!r}",
                        file=sys.stderr,
                    )
                    if not self._has_auth_cookie():
                        self._warn_missing_cookie()
                    else:
                        print(
                            "  [Xueqiu] Cookie 可能失效，请重新复制并更新 xueqiu_cookie。",
                            file=sys.stderr,
                        )
                return []

            data = response.json()
            items = data.get("list") or []
            posts = []
            for item in items:
                post = self._parse_item(item)
                if post:
                    posts.append(post)
            print(f"  [Xueqiu] Parsed {len(posts)} posts from page {page_num}.")
            return posts
        except Exception as e:
            print(f"  [Xueqiu] Exception on page {page_num}: {e}", file=sys.stderr)
            return []

    def _parse_item(self, item):
        post_id = item.get("id")
        if not post_id:
            return None

        title = strip_html(item.get("title") or "")
        body = strip_html(item.get("description") or item.get("text") or "")
        display_title = title or body
        if len(display_title) > 120:
            display_title = display_title[:120] + "..."

        user = item.get("user") or {}
        author = user.get("screen_name") or str(item.get("user_id", "匿名"))

        user_id = item.get("user_id") or user.get("id") or ""
        href = f"https://xueqiu.com/{user_id}/{post_id}" if user_id else f"https://xueqiu.com/{post_id}"

        return {
            "post_id": f"xq_{post_id}",
            "title": display_title,
            "read_count": int(item.get("view_count") or 0),
            "reply_count": int(item.get("reply_count") or 0),
            "author": author,
            "time": format_timestamp_ms(item.get("created_at")),
            "href": href,
            "source": SOURCE,
        }

    def crawl_multiple_pages(self, num_pages=5, page_size=20, max_posts=None):
        if not self.cookie:
            self._warn_missing_cookie()
        self._warmup()
        all_posts = []
        seen_ids = set()

        for page in range(1, num_pages + 1):
            posts = self.fetch_page(page, page_size=page_size)
            for post in posts:
                pid = post["post_id"]
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_posts.append(post)
                    if max_posts and len(all_posts) >= max_posts:
                        print(f"[Xueqiu] Reached max_posts={max_posts}, stopping early.")
                        print(f"[Xueqiu] Completed. Total unique posts collected: {len(all_posts)}")
                        return all_posts

            if page < num_pages:
                time.sleep(random.uniform(0.4, 1.0))

        print(f"[Xueqiu] Completed. Total unique posts collected: {len(all_posts)}")
        return all_posts


if __name__ == "__main__":
    crawler = XueqiuCrawler(symbol="SH000001")
    results = crawler.crawl_multiple_pages(2)
    if results:
        print(results[0])
