#!/usr/bin/env python3
"""将雪球 Cookie 写入 config.json 的 xueqiu_cookie 字段。"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


def read_clipboard():
    try:
        if sys.platform == "darwin":
            return subprocess.check_output(["pbpaste"], text=True).strip()
        if sys.platform.startswith("linux"):
            for cmd in (["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]):
                try:
                    return subprocess.check_output(cmd, text=True).strip()
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
    except Exception:
        pass
    return ""

def read_from_stdin():
    """
    Fallback when clipboard is unavailable in this environment.
    User can paste the full Cookie header value and finish with Ctrl+D.
    """
    try:
        print("未检测到 Cookie（剪贴板不可用？）。请在终端粘贴 Cookie 整段，然后按 Ctrl+D（结束输入）：")
        data = sys.stdin.read()
        return (data or "").strip()
    except Exception:
        return ""


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def test_cookie(cookie):
    """
    Return (posts_count, debug_info)
    """
    import requests
    from xueqiu_crawler import XueqiuCrawler

    crawler = XueqiuCrawler(symbol="SH000001", cookie=cookie)

    # Direct probe so we can see status / body when blocked.
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": crawler.session.headers.get("User-Agent", "Mozilla/5.0"),
            "Referer": f"https://xueqiu.com/S/{crawler.symbol}",
        }
    )
    if crawler.cookie:
        session.headers["Cookie"] = crawler.cookie

    debug_info = {}
    try:
        resp = session.get(
            crawler.API_URL,
            params={"symbol": crawler.symbol, "page": 1, "size": 10},
            timeout=12,
        )
        text = (resp.text or "").strip()
        snippet = text[:200]

        # Also run crawler's parsing path.
        posts = crawler.fetch_page(1, page_size=10)
        posts_count = len(posts)

        debug_info = {
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type"),
            "parsed_json_ok": bool(text) and text[0] in "{[",
            "first_200": snippet,
        }
        return posts_count, debug_info
    except Exception as e:
        posts = crawler.fetch_page(1, page_size=10)
        return len(posts), {"error": str(e)}


def main():
    cookie = ""
    if len(sys.argv) > 1:
        cookie = " ".join(sys.argv[1:]).strip()
    else:
        cookie = read_clipboard()

    if not cookie:
        cookie = read_from_stdin()
        if not cookie:
            print("仍未获取到 Cookie。请按下面步骤操作：")
            print("  1. 浏览器打开 https://xueqiu.com 并登录")
            print("  2. 打开 https://xueqiu.com/S/SH000001")
            print("  3. F12 → 网络 → 刷新 → 点任意 xueqiu.com 请求 → 复制 Request Headers 里的 Cookie")
            print("  4. 在终端执行: python3 setup_xueqiu_cookie.py，然后粘贴 Cookie 整段（Ctrl+D 结束输入）")
            print("或: python3 setup_xueqiu_cookie.py '粘贴的cookie整段'")
            sys.exit(1)

    if "xq_a_token" not in cookie.lower() and "xqat" not in cookie.lower():
        print("警告: Cookie 里未见 xq_a_token，可能未登录或复制不完整，仍将尝试写入。")

    config = load_config()
    config["xueqiu_cookie"] = cookie
    save_config(config)
    print(f"已写入 {CONFIG_PATH} → xueqiu_cookie（长度 {len(cookie)} 字符）")

    print("正在测试雪球接口…")
    try:
        n, dbg = test_cookie(cookie)
        if dbg:
            print("测试探针结果：")
            if "status_code" in dbg:
                print(
                    f"  status={dbg.get('status_code')}, content_type={dbg.get('content_type')}, "
                    f"parsed_json_ok={dbg.get('parsed_json_ok')}, posts_count={n}"
                )
            if dbg.get("first_200"):
                print(f"  response 前 200 字符: {dbg.get('first_200')!r}")
            if dbg.get("error"):
                print(f"  error: {dbg.get('error')}")
        if n > 0:
            print(f"测试成功：第 1 页抓到 {n} 条帖子。可运行 python3 main.py")
        else:
            print("已保存，但测试未抓到帖子。请确认已登录且 Cookie 未过期，重新复制后再运行本脚本。")
            sys.exit(2)
    except Exception as e:
        print(f"已保存，但测试异常: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
