"""Tests for kb.py 检索——中文子串必须可查，英文仍走 FTS。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from kb import _snippet, _terms, add_post, con, search  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    c = con(tmp_path / "kb.db")
    add_post(c, {
        "id": 1, "title": "关于一二三阶的一些理解", "url": "u1",
        "text": "一阶做时序变换，二阶做截面分组，三阶用 trade_when 控制持仓。",
        "source": "forum", "created_at": "", "votes": 0, "comments": 0,
    })
    add_post(c, {
        "id": 2, "title": "换手治理经验", "url": "u2",
        "text": "低换手不等于稳健，ts_decay_linear 压换手常常掉 sharpe。",
        "source": "forum", "created_at": "", "votes": 0, "comments": 0,
    })
    c.execute("INSERT INTO comment(post_id,author,created_at,text) VALUES(2,'a','','这帖讲的三阶 trade_when 用法值得看')")
    c.execute("INSERT INTO comment_fts(comment_fts) VALUES('rebuild')")
    c.commit()
    return c


def test_cjk_substring_hits_where_fts_would_miss(db):
    """FTS 把连续中文当一个整词，整串不等于查询词时必须靠子串兜底。"""
    rows = search(db, "一二三阶")
    assert [r["id"] for r in rows] == [1]


def test_cjk_terms_are_anded(db):
    assert [r["id"] for r in search(db, "一二三阶 trade_when")] == [1]
    assert search(db, "一二三阶 换手治理") == []


def test_ascii_query_uses_fts(db):
    assert [r["id"] for r in search(db, "trade_when")] == [1]


def test_comment_only_hit_surfaces_post(db):
    rows = search(db, "值得看")
    assert rows and rows[0]["id"] == 2
    assert rows[0]["snippet"].startswith("[回复]")


def test_title_outranks_body(db):
    rows = search(db, "换手")
    assert rows[0]["id"] == 2


def test_no_hit_and_empty_query(db):
    assert search(db, "完全不存在的词") == []
    assert search(db, "   ") == []


def test_terms_split():
    assert _terms("  一阶  二阶 ") == ["一阶", "二阶"]


def test_snippet_centers_on_term():
    s = _snippet("x" * 100 + "一二三阶" + "y" * 100, "一二三阶")
    assert "一二三阶" in s and s.startswith("…") and s.endswith("…")
