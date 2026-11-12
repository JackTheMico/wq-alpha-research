"""Tests for recommend_fields.py 筛选与推荐引擎。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from recommend_fields import (  # noqa: E402
    VF_CLASSIC_DATASETS,
    LOW_QUALITY_DATASETS,
    _days_since,
    _parse_date,
    _pyramid_multiplier,
    classify_dimension,
    filter_fields,
    is_atom_ready,
    is_blue_sea,
    is_low_quality,
)


# sentinel: 区分"没传 dateCreated"和"显式传了 None"
_SENTINEL = object()

def _field(
    id, alphaCount=100, coverage=0.9, type="MATRIX", dataset="fundamental2",
    category="fundamental", userCount=500, description="", dateCreated=_SENTINEL,
):
    """快速构造测试字段。dateCreated 默认为 180 天前（蓝海外）。
    显式传 dateCreated=None 会得到真的 None（模拟无 dateCreated 的旧快照）。"""
    if dateCreated is _SENTINEL:
        dateCreated = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%d")
    return {
        "id": id,
        "alphaCount": alphaCount,
        "coverage": coverage,
        "type": type,
        "dataset": {"id": dataset, "name": dataset},
        "category": {"id": category, "name": category},
        "userCount": userCount,
        "description": description,
        "dateCreated": dateCreated,
    }


# ---------------------------------------------------------------------------
# 日期解析
# ---------------------------------------------------------------------------

class TestDateParsing:
    def test_parse_iso_date(self):
        dt = _parse_date("2026-03-01")
        assert dt.year == 2026 and dt.month == 3 and dt.day == 1

    def test_parse_none_returns_none(self):
        assert _parse_date(None) is None

    def test_parse_bad_format_returns_none(self):
        assert _parse_date("not-a-date") is None

    def test_days_since_accurate(self):
        now = datetime(2026, 11, 12, tzinfo=timezone.utc)
        # 2026-03-01 距今 = 256 天
        d = _days_since("2026-03-01", now=now)
        assert d == pytest.approx(256, abs=1)

    def test_days_since_none_is_big(self):
        assert _days_since(None) == 999999


# ---------------------------------------------------------------------------
# is_blue_sea 核心闸门
# ---------------------------------------------------------------------------

class TestIsBlueSea:
    def test_new_cold_matrix_passes(self):
        """新上线 (30d) + 低 αCount (5) + MATRIX + 高覆盖 → 蓝"""
        f = _field("x", alphaCount=5, coverage=0.9, dateCreated=_recent_days(30))
        assert is_blue_sea(f)

    def test_old_field_fails(self):
        """距今 > 365 天 → 不是蓝海"""
        f = _field("x", alphaCount=5, coverage=0.9, dateCreated=_recent_days(400))
        assert not is_blue_sea(f)

    def test_high_alpha_fails(self):
        """αCount > 100 → 不是蓝海"""
        f = _field("x", alphaCount=200, coverage=0.9, dateCreated=_recent_days(30))
        assert not is_blue_sea(f)

    def test_non_matrix_fails(self):
        f = _field("x", type="VECTOR", alphaCount=5, coverage=0.9, dateCreated=_recent_days(30))
        assert not is_blue_sea(f)

    def test_low_coverage_fails(self):
        f = _field("x", alphaCount=5, coverage=0.3, dateCreated=_recent_days(30))
        assert not is_blue_sea(f)

    def test_low_quality_dataset_fails(self):
        f = _field("x", dataset="other321", alphaCount=5, coverage=0.9, dateCreated=_recent_days(30))
        assert not is_blue_sea(f)

    def test_custom_thresholds(self):
        """自定义 days_max 和 alpha_max"""
        f = _field("x", alphaCount=80, coverage=0.9, dateCreated=_recent_days(200))
        # 默认 365d + 100α → pass
        assert is_blue_sea(f)
        # 改严 → fail
        assert not is_blue_sea(f, days_max=100, alpha_max=50)


# ---------------------------------------------------------------------------
# filter_fields 主筛选
# ---------------------------------------------------------------------------

class TestFilterFields:
    def _make_mix(self):
        """构造混合场景：新/旧 × 冷/热 × VF/非VF"""
        now = datetime.now(timezone.utc)
        return [
            # 🌊 超新超冷
            _field("new_cold_1", alphaCount=0, coverage=0.95, dataset="analyst4",
                   dateCreated=_recent_days(10)),
            _field("new_cold_2", alphaCount=3, coverage=0.88, dataset="predictive_starmine",
                   dateCreated=_recent_days(60)),
            # 新但较热
            _field("new_hot", alphaCount=800, coverage=0.95, dataset="pv1",
                   dateCreated=_recent_days(30)),
            # 旧但冷
            _field("old_cold", alphaCount=50, coverage=0.7, dataset="fundamental6",
                   dateCreated=_recent_days(500)),
            # 旧且热
            _field("old_hot", alphaCount=15000, coverage=1.0, dataset="pv1",
                   dateCreated=_recent_days(1500)),
            # 低质量
            _field("bad_mapping", dataset="other321", alphaCount=0, coverage=0.95,
                   dateCreated=_recent_days(30)),
            # VECTOR
            _field("vec_field", type="VECTOR", alphaCount=5, coverage=0.95,
                   dateCreated=_recent_days(30)),
            # 低覆盖
            _field("low_cov", alphaCount=5, coverage=0.3, dateCreated=_recent_days(30)),
            # 衍生信号黑名单
            _field("rank_score", alphaCount=5, coverage=0.9,
                   description="rank based zscore signal factor",
                   dateCreated=_recent_days(30)),
        ]

    def test_bluesea_mode(self):
        """bluesea 模式：新×冷优先"""
        fields = self._make_mix()
        result = filter_fields(fields, mode="bluesea")
        ids = [f["id"] for f in result]
        # bad_mapping / vec_field / low_cov / rank_score 被通用闸门排除
        # old_cold / old_hot 因日期太旧被时间闸门排除
        # new_hot 因 αCount 太高被 αCount 闸门排除
        # 只剩 new_cold_1 / new_cold_2
        assert set(ids) == {"new_cold_1", "new_cold_2"}
        # 按时间升序
        assert result[0]["id"] == "new_cold_1"  # 10 天前

    def test_vf_mode(self):
        """vf 模式：经典数据集内的字段优先（不受时间+αCount闸门限制）"""
        fields = self._make_mix()
        result = filter_fields(fields, mode="vf")
        ids = [f["id"] for f in result]
        # 通用闸门仍排除 bad_mapping / vec_field / low_cov / rank_score
        # new_hot(pv1) 也因为 αCount > 5000 被排除
        # old_hot(pv1, αCount=15000) 也 > 5000，排除
        # 经典数据集（analyst4 / fundamental6）优先
        assert "old_cold" in ids  # fundamental6 在 VF 内
        assert "new_cold_1" in ids  # analyst4 在 VF 内
        assert "new_cold_2" in ids  # predictive_starmine 不在 VF 但通过闸门

    def test_no_datecreated_falls_back(self):
        """无 dateCreated 的旧快照 → bluesea 模式几乎过不了，vf/cold 还行"""
        fields = [
            _field("a", alphaCount=5, dateCreated=None),
            _field("b", alphaCount=3000, dataset="fundamental6", dateCreated=None),
            _field("c", alphaCount=15000, dataset="pv1", dateCreated=None),
        ]
        blue = filter_fields(fields, mode="bluesea")
        # 没 dateCreated = 999999 天前 → 都过不了时间闸门
        assert blue == []

        vf = filter_fields(fields, mode="vf")
        # VF 经典数据集（fundamental6 / pv1）的字段能进
        assert {"b", "c"} <= {f["id"] for f in vf}

    def test_excludes_blacklist(self):
        f = _field("rank_score_field", description="rank based zscore normalized signal factor",
                   dateCreated=_recent_days(10))
        assert filter_fields([f], mode="bluesea") == []

    def test_excludes_low_quality(self):
        for ds in LOW_QUALITY_DATASETS:
            f = _field("x", dataset=ds, dateCreated=_recent_days(10))
            assert filter_fields([f], mode="bluesea") == [], f"should exclude {ds}"

    def test_vf_classic_not_excluded(self):
        """经典数据集是首选，不是饱和！"""
        for ds in list(VF_CLASSIC_DATASETS)[:3]:
            f = _field("x", dataset=ds, alphaCount=3, dateCreated=_recent_days(20))
            result = filter_fields([f], mode="bluesea")
            assert len(result) == 1, f"VF classic {ds} should NOT be excluded"


# ---------------------------------------------------------------------------
# is_low_quality / is_atom_ready
# ---------------------------------------------------------------------------

class TestIsLowQuality:
    def test_known_mapping_datasets(self):
        for ds in LOW_QUALITY_DATASETS:
            f = _field("x", dataset=ds)
            assert is_low_quality(f), f"{ds} should be low quality"

    def test_vf_not_low_quality(self):
        f = _field("x", dataset="analyst4")
        assert not is_low_quality(f)


class TestIsAtomReady:
    def test_matrix_high_cov(self):
        f = _field("x", type="MATRIX", coverage=0.8)
        assert is_atom_ready(f)

    def test_vector_not_atom_ready(self):
        f = _field("x", type="VECTOR", coverage=0.9)
        assert not is_atom_ready(f)

    def test_low_cov_not_atom_ready(self):
        f = _field("x", type="MATRIX", coverage=0.3)
        assert not is_atom_ready(f)

    def test_flag_classifier_not_atom_ready(self):
        f = _field("is_earnings_surprise_flag", description="flag for earnings surprise",
                   type="MATRIX", coverage=0.95)
        assert not is_atom_ready(f)


# ---------------------------------------------------------------------------
# Pyramid 倍率估算
# ---------------------------------------------------------------------------

class TestPyramidMultiplier:
    def test_zero_alpha_high_multiplier(self):
        m = _pyramid_multiplier(0)
        assert m > 1.7  # ≈ 1.8x

    def test_low_alpha_decent_multiplier(self):
        m = _pyramid_multiplier(20)
        assert m > 1.2  # ≈ 1.3x

    def test_high_alpha_low_multiplier(self):
        m = _pyramid_multiplier(1000)
        assert m < 1.05  # ≈ 1.0x

    def test_monotonically_decreasing(self):
        """倍率随 alphaCount 单调递减"""
        prev = 100.0
        for ac in [0, 5, 20, 100, 500, 2000]:
            m = _pyramid_multiplier(ac)
            assert m <= prev
            prev = m


# ---------------------------------------------------------------------------
# 经济学维度分类（保持不变）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _recent_days(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
