"""Tests for simulate_batch.py 静态检查护栏。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from static_check import (  # noqa: E402
    BASE_PRICE_FIELDS,
    extract_signal_fields,
    validate_field_rationale,
)


class TestExtractSignalFields:
    def test_rank_wraps_signal_field(self):
        fields = extract_signal_fields("rank(operating_income)")
        assert "operating_income" in fields

    def test_ts_rank_wraps_signal_field(self):
        fields = extract_signal_fields("ts_rank(cashflow_to_assets, 126)")
        assert "cashflow_to_assets" in fields

    def test_denominator_excluded(self):
        # operating_income is numerator (signal), equity is denominator
        fields = extract_signal_fields("rank(operating_income/equity)")
        assert "operating_income" in fields
        assert "equity" not in fields

    def test_group_key_excluded(self):
        # subindustry is the group key, not a signal
        fields = extract_signal_fields("group_rank(ts_rank(close, 20), subindustry)")
        assert "subindustry" not in fields

    def test_base_price_fields_excluded(self):
        for bf in BASE_PRICE_FIELDS:
            fields = extract_signal_fields(f"rank({bf})")
            assert bf not in fields

    def test_neut_second_arg_excluded(self):
        # vector_neut(signal, group) — second arg is group key
        fields = extract_signal_fields("vector_neut(rank(ebit_to_assets), rank(subindustry))")
        assert "ebit_to_assets" in fields
        assert "subindustry" not in fields

    def test_nested_signal_field(self):
        fields = extract_signal_fields("rank(ts_delta(cashflow_op, 5))")
        assert "cashflow_op" in fields

    def test_no_signal_fields(self):
        # Just constants and operators
        fields = extract_signal_fields("rank(1.0)")
        assert fields == set()


class TestValidateFieldRationale:
    def test_missing_rationale_fails(self):
        errors = validate_field_rationale({"operating_income"}, {})
        assert len(errors) > 0

    def test_short_rationale_fails(self):
        errors = validate_field_rationale({"operating_income"}, {"operating_income": "oi"})
        assert len(errors) > 0

    def test_valid_rationale_passes(self):
        errors = validate_field_rationale(
            {"operating_income"},
            {"operating_income": "营业收入，度量公司规模"},
        )
        assert errors == []

    def test_extra_rationale_ignored(self):
        # rationale has extra field not in signal fields — should still pass
        errors = validate_field_rationale(
            {"operating_income"},
            {"operating_income": "营业收入，度量公司经营规模", "extra_field": "额外字段解释说明"},
        )
        assert errors == []
