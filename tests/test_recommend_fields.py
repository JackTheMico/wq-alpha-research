"""Tests for recommend_fields.py 筛选与推荐引擎。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from recommend_fields import (  # noqa: E402
    BLACKLIST_KEYWORDS,
    SATURATED_DATASETS,
    classify_dimension,
    filter_fields,
    is_very_rare,
    passes_gates,
)


def _field(id, alphaCount=100, coverage=0.9, type="MATRIX", dataset="fundamental2",
           category="fundamental", userCount=500, description=""):
    return {
        "id": id,
        "alphaCount": alphaCount,
        "coverage": coverage,
        "type": type,
        "dataset": {"id": dataset, "name": dataset},
        "category": {"id": category, "name": category},
        "userCount": userCount,
        "description": description,
    }


class TestPassesGates:
    def test_alpha_count_too_high_fails(self):
        f = _field("x", alphaCount=600)
        assert passes_gates(f) is False

    def test_alpha_count_at_threshold_passes(self):
        f = _field("x", alphaCount=500)
        assert passes_gates(f) is True

    def test_coverage_too_low_fails(self):
        f = _field("x", coverage=0.5)
        assert passes_gates(f) is False

    def test_coverage_at_threshold_passes(self):
        f = _field("x", coverage=0.7)
        assert passes_gates(f) is True

    def test_non_matrix_type_fails(self):
        f = _field("x", type="VECTOR")
        assert passes_gates(f) is False

    def test_matrix_type_passes(self):
        f = _field("x", type="MATRIX")
        assert passes_gates(f) is True


class TestFilterFields:
    def test_excludes_blacklist_keywords(self):
        f = _field("rank_score_field", description="rank based score")
        assert filter_fields([f]) == []

    def test_excludes_saturated_datasets(self):
        for ds in SATURATED_DATASETS:
            f = _field("x", dataset=ds)
            assert filter_fields([f]) == [], f"should exclude {ds}"

    def test_includes_clean_field(self):
        f = _field("cashflow_to_assets", description="operating cash flow to assets")
        result = filter_fields([f])
        assert len(result) == 1
        assert result[0]["id"] == "cashflow_to_assets"

    def test_sorts_by_alpha_count_ascending(self):
        f1 = _field("a", alphaCount=300)
        f2 = _field("b", alphaCount=50)
        f3 = _field("c", alphaCount=150)
        result = filter_fields([f1, f2, f3])
        assert [r["alphaCount"] for r in result] == [50, 150, 300]


class TestIsVeryRare:
    def test_very_rare_when_low_usercount_and_low_alphacount(self):
        f = _field("x", userCount=50, alphaCount=3)
        assert is_very_rare(f) is True

    def test_not_rare_when_high_usercount(self):
        f = _field("x", userCount=500, alphaCount=3)
        assert is_very_rare(f) is False

    def test_not_rare_when_high_alphacount(self):
        f = _field("x", userCount=50, alphaCount=10)
        assert is_very_rare(f) is False


class TestClassifyDimension:
    def test_profitability(self):
        f = _field("ebit_to_assets", description="Earnings before interest and tax to total assets")
        assert classify_dimension(f) == "profitability"

    def test_growth(self):
        f = _field("revenue_growth", description="Revenue year-over-year growth rate")
        assert classify_dimension(f) == "growth"

    def test_valuation(self):
        f = _field("book_to_price", description="Book value per share to price")
        assert classify_dimension(f) == "valuation"

    def test_leverage(self):
        f = _field("debt_to_equity", description="Total debt to shareholders equity")
        assert classify_dimension(f) == "leverage"

    def test_cashflow(self):
        f = _field("operating_cash_flow", description="Cash flow from operations")
        assert classify_dimension(f) == "cashflow"

    def test_efficiency(self):
        f = _field("asset_turnover", description="Total asset turnover ratio")
        assert classify_dimension(f) == "efficiency"

    def test_analyst(self):
        f = _field("eps_estimate", description="Analyst consensus EPS estimate")
        assert classify_dimension(f) == "analyst"

    def test_volatility(self):
        f = _field("realized_volatility", description="Realized stock return volatility")
        assert classify_dimension(f) == "volatility"

    def test_sentiment(self):
        f = _field("news_sentiment", description="News article sentiment score")
        assert classify_dimension(f) == "sentiment"

    def test_momentum(self):
        f = _field("price_momentum", description="Stock price momentum over 20 days")
        assert classify_dimension(f) == "momentum"

    def test_event(self):
        f = _field("earnings_surprise", description="Earnings per share surprise")
        assert classify_dimension(f) == "event"

    def test_unknown_falls_to_other(self):
        f = _field("random_metric", description="Some random metric")
        assert classify_dimension(f) == "other"
