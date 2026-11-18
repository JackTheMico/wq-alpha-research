#!/usr/bin/env python3
"""论坛知识库：帖子/回复/模板入库 + 全文检索。唯一读写入口，纯 stdlib。

为什么不是 markdown：帖子是 O(N) 增长的原始语料，agent 只该拿 top-k。
蒸馏后的、需要常驻的内容放 references/playbook.md；验证结论放 references/ledger.md。

用法：
    python kb.py init                      # 建库（幂等）
    python kb.py pull "alpha template" -n 10   # 论坛搜索 + 抓正文/回复入库
    python kb.py sync-md references/*.md   # 把已保存的社区模板 md 入库
    python kb.py search "regression_neut"  # FTS 全文检索
    python kb.py show <post_id>            # 看正文 + 回复 + 抽出的模板
    python kb.py templates --dataset fundamental6
    python kb.py mark <tpl_id> VALIDATED --note "IND d4 S=1.7"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "wq_knowledge.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS post(
  id INTEGER PRIMARY KEY, title TEXT, author TEXT, created_at TEXT,
  votes INTEGER, comments INTEGER, url TEXT, text TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS comment(
  id INTEGER PRIMARY KEY, post_id INTEGER, author TEXT, created_at TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS template(
  id INTEGER PRIMARY KEY, post_id INTEGER, fingerprint TEXT UNIQUE,
  expr TEXT, dataset TEXT, region TEXT, settings TEXT,
  status TEXT DEFAULT 'UNVALIDATED', note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE VIRTUAL TABLE IF NOT EXISTS post_fts USING fts5(title, text, content='post', content_rowid='id');
CREATE VIRTUAL TABLE IF NOT EXISTS comment_fts USING fts5(text, content='comment', content_rowid='id');
"""

EXPR = re.compile(r"(rank|group_|ts_|vec_|regression_|trade_when|zscore|ts_rank)\(", re.I)


def con(path: Path = DB) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.executescript(SCHEMA)
    return c


def fp(expr: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", "", expr).encode()).hexdigest()[:16]


def add_post(c: sqlite3.Connection, p: dict) -> int:
    c.execute("""INSERT INTO post(id,title,author,created_at,votes,comments,url,text,source)
                 VALUES(?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(id) DO UPDATE SET title=excluded.title, text=excluded.text,
                   votes=excluded.votes, comments=excluded.comments, source=excluded.source""",
              (p.get("id"), p.get("title"), p.get("author"), p.get("created_at"),
               p.get("votes"), p.get("comments"), p.get("url"), p.get("text"), p.get("source")))
    c.execute("INSERT INTO post_fts(post_fts) VALUES('rebuild')")
    return p.get("id")


def add_templates(c: sqlite3.Connection, post_id: int, text: str, source: str = "") -> int:
    """从正文里抽表达式行（论坛帖常带续行反斜杠，先合并）。"""
    if not text:
        return 0
    merged = re.sub(r"\\\s*\n\s*", "", text)
    cand = []
    for line in merged.splitlines():
        s = line.strip().strip("`")
        if len(s) > 8 and EXPR.search(s) and not s.startswith("#"):
            cand.append(s)
    n = 0
    for expr in cand:
        try:
            c.execute("""INSERT INTO template(post_id,fingerprint,expr,region,settings)
                         VALUES(?,?,?,?,?)""",
                      (post_id, fp(expr), expr, _region(expr, source), _settings(merged)))
            n += 1
        except sqlite3.IntegrityError:
            pass
    return n


def _region(expr: str, src: str) -> str:
    if re.search(r"\bCHN\b|chn", expr + src):
        return "CHN"
    if re.search(r"\bGLB\b|glb", expr + src):
        return "GLB"
    return ""


def _settings(blob: str) -> str:
    m = re.search(r"decay[\s:=]*(\d+)", blob, re.I)
    neu = re.search(r"(industry|subindustry|sector|market|country)", blob, re.I)
    out = {}
    if m:
        out["decay"] = int(m.group(1))
    if neu:
        out["neutralization"] = neu.group(1).upper()
    return json.dumps(out) if out else ""


def sync_md(c: sqlite3.Connection, path: Path) -> tuple[int, int]:
    raw = path.read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:text|fastexpr)\n(.*?)```", raw, re.S)
    body = "\n".join(blocks) or raw
    pid = 900000 + (int(hashlib.sha1(path.name.encode()).hexdigest()[:6], 16) % 99999)
    title = next((l.lstrip("# ").strip() for l in raw.splitlines() if l.startswith("# ")), path.name)
    posts = c.execute("SELECT count(*) FROM post").fetchone()[0]
    add_post(c, {"id": pid, "title": f"[md] {title}", "text": body,
                 "source": path.name, "created_at": "", "votes": 0, "comments": 0, "url": ""})
    return pid, add_templates(c, pid, body, path.name)


def pull(c: sqlite3.Connection, query: str, limit: int) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from wq_forum import forum_session, search_posts, get_post, get_comments  # noqa: E402

    s = forum_session()
    n = 0
    for hit in search_posts(query, session=s, limit=limit):
        try:
            full = get_post(hit["id"], session=s)
            full["author"], full["source"] = str(full.get("author_id")), "forum"
            add_post(c, full)
            for cm in get_comments(hit["id"], session=s):
                c.execute("INSERT INTO comment(post_id,author,created_at,text) VALUES(?,?,?,?)",
                          (hit["id"], str(cm.get("author_id")), cm.get("created_at"),
                           cm.get("text") or cm.get("body")))
            c.execute("INSERT INTO comment_fts(comment_fts) VALUES('rebuild')")
            n += add_templates(c, hit["id"], full.get("text", ""), "")
        except Exception as e:  # 单帖失败不拖垮整批
            print(f"  ! {hit['id']} {e}")
    c.commit()
    return n


# --- 检索 -------------------------------------------------------------------
# FTS5 默认 unicode61 分词器把连续 CJK 当一个整词：「关于一二三阶的一些理解」只有
# 整串 token，查「一二三阶」命中 0。中文语料占绝对多数，所以 CJK 查询走 LIKE 子串，
# ASCII 查询仍走 FTS（`trade_when` 这类靠下划线切词的效果很好）。
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _terms(query: str) -> list[str]:
    """空格切词，词间 AND，与 FTS 默认语义一致。"""
    return [t for t in re.split(r"\s+", (query or "").strip()) if t]


def _snippet(text: str, term: str, width: int = 60) -> str:
    """截取命中词上下文，供 CLI 展示。"""
    text = (text or "").replace("\n", " ")
    i = text.lower().find(term.lower())
    if i < 0:
        return text[: width * 2]
    s, e = max(0, i - width // 2), min(len(text), i + len(term) + width)
    return ("…" if s > 0 else "") + text[s:e] + ("…" if e < len(text) else "")


def _like_posts(c: sqlite3.Connection, terms: list[str], limit: int) -> list[dict]:
    """标题/正文命中：所有词都要出现（AND），标题命中加权最高。"""
    cond = " AND ".join(["(p.title LIKE ? OR p.text LIKE ?)"] * len(terms))
    args: list[str] = []
    for t in terms:
        args += [f"%{t}%", f"%{t}%"]
    rows = c.execute(
        f"SELECT p.id,p.title,p.url,COALESCE(p.text,'') FROM post p WHERE {cond}", args
    ).fetchall()
    out = []
    for pid, title, url, text in rows:
        score = sum(6 for t in terms if t in (title or ""))
        score += sum(2 for t in terms if t in text)
        out.append({"id": pid, "title": title, "url": url,
                    "snippet": _snippet(text or title or "", terms[0]), "score": score})
    out.sort(key=lambda r: (-r["score"], r["id"]))
    return out[:limit]


def _like_comments(c: sqlite3.Connection, terms: list[str]) -> dict[int, dict]:
    """只在回复里命中的帖：正文可能不含关键词，但对检索有价值。"""
    cond = " AND ".join(["c.text LIKE ?"] * len(terms))
    args = [f"%{t}%" for t in terms]
    rows = c.execute(
        f"""SELECT p.id,p.title,p.url,c.text FROM comment c JOIN post p ON p.id=c.post_id
            WHERE {cond}""", args
    ).fetchall()
    hit: dict[int, dict] = {}
    for pid, title, url, text in rows:
        if pid not in hit:
            hit[pid] = {"id": pid, "title": title, "url": url,
                        "snippet": f"[回复] {_snippet(text, terms[0])}", "score": 1}
    return hit


def search(c: sqlite3.Connection, query: str, limit: int = 8) -> list[dict]:
    """统一检索入口：ASCII 走 FTS，含 CJK 或 FTS 无命中则走 LIKE 子串。"""
    terms = _terms(query)
    if not terms:
        return []
    if not any(CJK.search(t) for t in terms):
        try:
            rows = c.execute(
                """SELECT p.id, p.title, p.url, snippet(post_fts, 1, '[', ']', '…', 12)
                   FROM post_fts JOIN post p ON p.id=post_fts.rowid
                   WHERE post_fts MATCH ? LIMIT ?""", (query, limit)).fetchall()
        except sqlite3.OperationalError:  # 语法错误（括号/引号等）时不当作无结果
            rows = []
        if rows:
            return [{"id": r[0], "title": r[1], "url": r[2],
                     "snippet": r[3] or "", "score": 0} for r in rows]
    # CJK，或 ASCII 查询 FTS 没命中 → 子串兜底（语料规模小，全表扫可接受）
    merged = {r["id"]: r for r in _like_posts(c, terms, limit)}
    for pid, r in _like_comments(c, terms).items():
        merged.setdefault(pid, r)
    out = sorted(merged.values(), key=lambda r: (-r["score"], r["id"]))
    return out[:limit]


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p1 = sub.add_parser("pull"); p1.add_argument("query"); p1.add_argument("-n", type=int, default=10)
    p2 = sub.add_parser("sync-md"); p2.add_argument("paths", nargs="+")
    p3 = sub.add_parser("search"); p3.add_argument("query"); p3.add_argument("-n", type=int, default=8)
    p4 = sub.add_parser("show"); p4.add_argument("post_id", type=int)
    p5 = sub.add_parser("templates"); p5.add_argument("--dataset"); p5.add_argument("-n", type=int, default=20)
    p6 = sub.add_parser("mark"); p6.add_argument("tpl_id", type=int)
    p6.add_argument("status", choices=["UNVALIDATED", "VALIDATED", "FAILED"])
    p6.add_argument("--note", default="")
    a = ap.parse_args()
    c = con()

    if a.cmd == "init":
        print(f"ok: {DB} ({DB.stat().st_size} bytes)")
    elif a.cmd == "pull":
        print(f"ingested {pull(c, a.query, a.n)} templates")
    elif a.cmd == "sync-md":
        for pth in a.paths:
            pid, n = sync_md(c, Path(pth))
            print(f"{Path(pth).name} -> post {pid}, {n} templates")
        c.commit()
    elif a.cmd == "search":
        rows = search(c, a.query, a.n)
        for r in rows:
            print(f"{r['id']}\t{r['title']}\n\t{(r['snippet'] or '')[:160]}\n\t{r['url'] or ''}")
        if not rows:
            print("无命中")
    elif a.cmd == "show":
        p = c.execute("SELECT title,url,text,source FROM post WHERE id=?", (a.post_id,)).fetchone()
        if not p:
            sys.exit("没有这个 post")
        print(f"# {p[0]}\n{p[1] or ''}\n[{p[3]}]\n\n{p[2]}\n")
        for r in c.execute("SELECT id,expr,status,note FROM template WHERE post_id=?", (a.post_id,)):
            print(f"  tpl {r[0]} [{r[2]}] {r[1][:110]} {r[3]}")
        for r in c.execute("SELECT author,text FROM comment WHERE post_id=? ORDER BY created_at", (a.post_id,)):
            print(f"\n> {r[0]}: {(r[1] or '')[:200]}")
    elif a.cmd == "templates":
        q = "SELECT id,post_id,expr,status,note FROM template"
        args = (a.n,)
        if a.dataset:
            q, args = q + " WHERE expr LIKE ? LIMIT ?", (f"%{a.dataset}%", a.n)
        else:
            q += " LIMIT ?"
        for r in c.execute(q, args):
            print(f"{r[0]}\tpost {r[1]}\t[{r[3]}]\t{r[2][:150]}\t{r[4]}")
    elif a.cmd == "mark":
        c.execute("UPDATE template SET status=?, note=? WHERE id=?", (a.status, a.note, a.tpl_id))
        c.commit()
        print(f"tpl {a.tpl_id} -> {a.status}")


if __name__ == "__main__":
    main()
