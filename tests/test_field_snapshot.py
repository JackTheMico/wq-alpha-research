"""Tests for field_snapshot.py — 多区域字段快照基础设施。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from field_snapshot import (  # noqa: E402
    check_snapshot_age,
    get_snapshot_path,
    load_snapshot,
    snapshot_exists,
)

SNAPSHOT_DIR = REPO / "references"


def test_get_snapshot_path_naming_convention():
    path = get_snapshot_path("usa", "top3000", 1)
    assert path.name == "fields_usa_top3000_delay1.json"


def test_get_snapshot_path_case_insensitive_region():
    path = get_snapshot_path("USA", "TOP3000", 1)
    assert path.name == "fields_usa_top3000_delay1.json"


def test_snapshot_exists_for_usa():
    assert snapshot_exists("usa", "top3000", 1) is True


def test_snapshot_exists_for_unknown_region():
    assert snapshot_exists("zzz", "top9999", 1) is False


def test_load_snapshot_returns_field_list():
    fields = load_snapshot("usa", "top3000", 1)
    assert isinstance(fields, list)
    assert len(fields) > 0
    assert "id" in fields[0]
    assert "alphaCount" in fields[0]


def test_load_snapshot_caches_index(tmp_path, monkeypatch):
    """首次加载后 fields_index.json 应被创建/更新。"""
    monkeypatch.setattr("field_snapshot.SNAPSHOT_DIR", SNAPSHOT_DIR)
    load_snapshot("usa", "top3000", 1)
    index_path = SNAPSHOT_DIR / "fields_index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert any(s["region"] == "usa" for s in index["snapshots"])


def test_check_snapshot_age_fresh(tmp_path):
    fresh = tmp_path / "fresh.json"
    fresh.write_text("[]", encoding="utf-8")
    is_stale, age_days = check_snapshot_age(fresh)
    assert is_stale is False
    assert age_days < 1


def test_check_snapshot_age_stale(tmp_path):
    old = tmp_path / "old.json"
    old.write_text("[]", encoding="utf-8")
    # 把修改时间设为 60 天前
    old_time = time.time() - 60 * 86400
    old.touch()
    import os
    os.utime(old, (old_time, old_time))
    is_stale, age_days = check_snapshot_age(old)
    assert is_stale is True
    assert age_days >= 30


def test_check_snapshot_age_custom_threshold(tmp_path):
    mid = tmp_path / "mid.json"
    mid.write_text("[]", encoding="utf-8")
    mid_time = time.time() - 10 * 86400
    import os
    os.utime(mid, (mid_time, mid_time))
    is_stale, _ = check_snapshot_age(mid, max_days=5)
    assert is_stale is True
    is_stale, _ = check_snapshot_age(mid, max_days=15)
    assert is_stale is False
