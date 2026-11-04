#!/usr/bin/env python3
"""顾问论坛（support.worldquantbrain.com / Zendesk）读取工具。

2026-10-31 实测打通：Cloudflare 用 curl_cffi 的 TLS 指纹过；
登录用平台 /authentication/support 换 Zendesk SSO 票。

用法（CLI）：
    python wq_forum.py search 七十二变
    python wq_forum.py post 36805947935895
    python wq_forum.py comments 36805947935895
    python wq_forum.py profile 32902101088407
    python wq_forum.py images 36805947935895 -o ./img
也可当库用：from wq_forum import forum_session, search_posts, get_post ...
"""
from __future__ import annotations

import argparse
import html as _html
import re
import sys
from pathlib import Path

from curl_cffi import requests as creq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession  # noqa: E402

SUPPORT = "https://support.worldquantbrain.com"
SSO = "https://api.worldquantbrain.com/authentication/support"


def forum_session(return_to: str = f"{SUPPORT}/hc/zh-cn") -> creq.Session:
    """返回已登录 Zendesk 的 session。impersonate 必须是 'chrome'（新版），'chrome124' 会被 CF 拦。"""
    brain = BrainSession()
    brain.authenticate()
    token = brain.http.cookies.get("t")
    if not token:
        raise RuntimeError("平台认证没拿到 t cookie")
    s = creq.Session(impersonate="chrome")
    r = s.get(SSO, params={"return_to": return_to}, cookies={"t": token}, timeout=60)
    if "_zendesk_authenticated" not in s.cookies.get_dict():
        raise RuntimeError(f"SSO 失败：{r.status_code} {r.url[:120]}")
    return s


def _clean(x: str) -> str:
    x = re.sub(r"<br\s*/?>", "\n", x or "")
    x = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", x)
    x = re.sub(r"<[^>]+>", "", x)
    return _html.unescape(x).strip()


def search_posts(q: str, session=None, limit: int = 20) -> list[dict]:
    s = session or forum_session()
    r = s.get(f"{SUPPORT}/api/v2/help_center/community_posts/search.json",
              params={"query": q, "per_page": limit}, timeout=40)
    r.raise_for_status()
    d = r.json()
    return [{"id": it["id"], "title": _clean(it.get("title") or ""),
             "created_at": it.get("created_at"), "author_id": it.get("author_id"),
             "votes": it.get("vote_sum"), "comments": it.get("comment_count")}
            for it in d.get("results", [])]


def get_post(post_id: str | int, session=None) -> dict:
    s = session or forum_session()
    r = s.get(f"{SUPPORT}/api/v2/community/posts/{post_id}.json", timeout=40)
    r.raise_for_status()
    p = r.json()["post"]
    return {"id": p["id"], "title": p["title"], "html": p["details"], "text": _clean(p["details"]),
            "author_id": p["author_id"], "created_at": p["created_at"],
            "votes": p["vote_sum"], "comments": p["comment_count"],
            "url": p["html_url"],
            "images": re.findall(r'src="([^"]+\.(?:png|jpg|jpeg|gif))"', p["details"], re.I)}


def get_comments(post_id: str | int, session=None) -> list[dict]:
    s = session or forum_session()
    r = s.get(f"{SUPPORT}/api/v2/community/posts/{post_id}/comments.json",
              params={"per_page": 100}, timeout=40)
    r.raise_for_status()
    return [{"author_id": c["author_id"], "created_at": c["created_at"],
             "text": _clean(c["body"]), "votes": c.get("vote_sum")}
            for c in r.json().get("comments", [])]


def get_profile(user_id: str | int, session=None) -> dict:
    """用户 id 走后门：profile HTML 的 <title> 是 '名字 的用户个人资料'。"""
    s = session or forum_session()
    r = s.get(f"{SUPPORT}/hc/zh-cn/profiles/{user_id}", timeout=45)
    r.raise_for_status()
    m = re.search(r"<title>(.*?)</title>", r.text, re.S)
    name = _html.unescape(m.group(1)).split(" 的")[0].strip() if m else ""
    txt = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)))
    stats = {}
    for key in ("活动总数", "帖子（", "评论（", "投票数", "关注者数", "成员加入日期"):
        i = txt.find(key)
        if i > 0:
            stats[key] = txt[i:i + 40]
    return {"user_id": str(user_id), "name": name, "stats": stats}


def download_images(post_id: str | int, out_dir: str, session=None) -> list[str]:
    s = session or forum_session()
    p = get_post(post_id, session=s)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, url in enumerate(p["images"], 1):
        rr = s.get(url, timeout=60)
        fp = out / f"p{i}{Path(url).suffix or '.png'}"
        fp.write_bytes(rr.content)
        paths.append(str(fp))
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="读顾问论坛（Zendesk）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("search"); p1.add_argument("query"); p1.add_argument("-n", type=int, default=20)
    p2 = sub.add_parser("post"); p2.add_argument("id")
    p3 = sub.add_parser("comments"); p3.add_argument("id")
    p4 = sub.add_parser("profile"); p4.add_argument("user_id")
    p5 = sub.add_parser("images"); p5.add_argument("id"); p5.add_argument("-o", default="./forum_img")
    a = ap.parse_args()

    if a.cmd == "search":
        for it in search_posts(a.query, limit=a.n):
            print(f"[{it['id']}] {it['title'][:70]} | {str(it['created_at'])[:10]} | a={it['author_id']} | v={it['votes']}")
    elif a.cmd == "post":
        p = get_post(a.id)
        print(f"# {p['title']}\n{p['created_at']} | votes={p['votes']} | comments={p['comments']} | author={p['author_id']}\n{p['url']}\n")
        print(p["text"])
        if p["images"]:
            print("\n[images]", *p["images"], sep="\n  ")
    elif a.cmd == "comments":
        for c in get_comments(a.id):
            print(f"--- a={c['author_id']} {str(c['created_at'])[:10]} v={c['votes']}\n{c['text'][:600]}\n")
    elif a.cmd == "profile":
        print(get_profile(a.user_id))
    elif a.cmd == "images":
        print("\n".join(download_images(a.id, a.o)))


if __name__ == "__main__":
    main()
