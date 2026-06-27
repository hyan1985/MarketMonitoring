"""Lightweight persistence: small data.json + compact posts.json."""

from __future__ import annotations

import json
import os

POSTS_FILENAME = "posts.json"


def posts_path_for(data_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(data_path)), POSTS_FILENAME)


def load_bundle(data_path: str, *, include_posts: bool = False) -> dict:
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not include_posts:
        data.pop("posts", None)
        return data
    posts_file = posts_path_for(data_path)
    if os.path.exists(posts_file):
        with open(posts_file, "r", encoding="utf-8") as f:
            data["posts"] = json.load(f)
    return data


def save_bundle(data: dict, data_path: str) -> None:
    payload = dict(data)
    posts = payload.pop("posts", None)
    os.makedirs(os.path.dirname(os.path.abspath(data_path)) or ".", exist_ok=True)
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if posts is not None:
        with open(posts_path_for(data_path), "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, separators=(",", ":"))


def migrate_inline_posts(data_path: str) -> bool:
    """Move legacy inline posts from data.json into posts.json."""
    if not os.path.exists(data_path):
        return False
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    posts = data.get("posts")
    if not posts:
        return False
    if os.path.exists(posts_path_for(data_path)):
        data.pop("posts", None)
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    save_bundle(data, data_path)
    return True
