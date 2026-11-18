"""Tests for stage_check.py — 一二三阶结构检查。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from stage_check import (  # noqa: E402
    analyze,
    check_vector_aggregation,
    collect_ops,
    find_pollution,
    stage_of,
)


# ---- 算子分阶 ---------------------------------------------------------------

def test_stage_assignment():
    assert stage_of("trade_when") == 3
    assert stage_of("group_rank") == 2
    assert stage_of("group_neutralize") == 2
    assert stage_of("ts_rank") == 1
    assert stage_of("ts_delta") == 1
    assert stage_of("ts_backfill") == 0
    assert stage_of("winsorize") == 0
    assert stage_of("vec_avg") == 0
    assert stage_of("hump") == 4
    assert stage_of("vector_neut") == 4
    assert stage_of("unknown_op_xyz") is None


def test_collect_ops_skips_unknown():
    ops = [op for _, op in collect_ops("foo(ts_rank(bar, 10))")]
    assert "foo" not in ops
    assert "bar" not in ops
    assert "ts_rank" in ops


# ---- 阶数判定 ---------------------------------------------------------------

def test_golden_combo_is_stage2():
    r = analyze("group_rank(ts_rank(operating_income/equity,126),subindustry)")
    assert r["stage"] == 2
    assert r["verdict"] == "OK"


def test_full_three_stage():
    expr = ("trade_when(volume>ts_mean(volume,20), "
            "group_rank(ts_delta(cashflow_op,63),subindustry), -1)")
    r = analyze(expr)
    assert r["stage"] == 3
    assert r["verdict"] == "OK"


def test_bare_field_is_stage0_with_warn():
    r = analyze("rank(ts_backfill(foo,120))")
    assert r["stage"] == 0
    assert r["verdict"] == "WARN"
    assert any("裸字段" in w for w in r["warnings"])


# ---- 跨阶污染 ---------------------------------------------------------------

def test_group_wrapping_trade_when_is_pollution():
    expr = ("group_rank(trade_when(volume>ts_mean(volume,20), "
            "rank(cashflow_op), -1), subindustry)")
    errs = find_pollution(expr)
    assert errs and "跨阶污染" in errs[0]
    assert analyze(expr)["verdict"] == "FAIL"


def test_ts_wrapping_trade_when_is_pollution():
    expr = "ts_mean(trade_when(volume>ts_mean(volume,20), rank(x), -1), 10)"
    assert find_pollution(expr)


def test_correct_three_stage_has_no_pollution():
    expr = ("trade_when(volume>ts_mean(volume,20), "
            "group_rank(ts_delta(cashflow_op,63),subindustry), -1)")
    assert find_pollution(expr) == []


def test_group_inside_trade_when_is_fine():
    """二阶在门控内部是正确顺序，不是污染。"""
    expr = "trade_when(cond, group_rank(ts_rank(f,126), industry), -1)"
    assert find_pollution(expr) == []


# ---- 复杂度 ---------------------------------------------------------------

def test_complexity_budget_exceeded():
    expr = ("group_neutralize(ts_zscore(ts_rank(ts_delta(ts_mean("
            "ts_std_dev(ts_delta(operating_income,20),20),20),63),126),250),subindustry)")
    r = analyze(expr)
    assert r["verdict"] == "FAIL"
    assert any("复杂度" in e for e in r["errors"])


def test_complexity_budget_configurable():
    expr = "group_rank(ts_rank(f,126),subindustry)"
    assert analyze(expr, max_complexity=1.0)["verdict"] == "FAIL"
    assert analyze(expr, max_complexity=10.0)["verdict"] == "OK"


def test_same_op_repeat_detected():
    r = analyze("rank(zscore(zscore(zscore(ts_rank(f,126)))))")
    assert r["verdict"] == "FAIL"
    assert any("zscore" in e for e in r["errors"])


def test_same_op_limit_configurable():
    expr = "rank(zscore(zscore(ts_rank(f,126))))"
    assert analyze(expr, max_same_op=1)["verdict"] == "FAIL"
    assert analyze(expr, max_same_op=2)["verdict"] != "FAIL"


# ---- VECTOR 聚合 ------------------------------------------------------------

def test_vector_field_without_aggregation_warns():
    warns = check_vector_aggregation("ts_delta(nws20_sentiment, 20)")
    assert warns and "nws20_sentiment" in warns[0]


def test_vector_field_with_aggregation_ok():
    warns = check_vector_aggregation("ts_delta(vec_avg(nws20_sentiment), 20)")
    assert warns == []


def test_normal_field_no_vector_warning():
    assert check_vector_aggregation("ts_rank(operating_income, 126)") == []


# ---- 层次分工提示 ------------------------------------------------------------

def test_gate_without_cross_section_warns():
    r = analyze("trade_when(cond, ts_rank(f,126), -1)")
    assert any("缺二阶" in w for w in r["warnings"])


def test_layers_reported_per_stage():
    r = analyze("group_rank(ts_rank(f,126),subindustry)")
    keys = list(r["layers"].keys())
    assert any("一阶" in k for k in keys)
    assert any("二阶" in k for k in keys)


# ---- 空输入 ---------------------------------------------------------------

def test_empty_expr():
    r = analyze("")
    assert r["stage"] == 0
    assert r["errors"] == []
