"""Tests for 提交闸门相关逻辑（2026-11 实测修复的回归保护）。

锁住四件事：
1. `gate_report` / `preflight.evaluate` 把 ladder 的 WARNING 当阻断（提交时会判 FAIL）；
2. `run_many` 跨 region 自动分组，不再整批失败；
3. `build_payload` 拦下漏进 settings 的 `name`（否则平台 400）；
4. 提交判定书能区分「相关性 FAIL」与「配额耗尽」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from wq_api import (  # noqa: E402
    BrainError,
    BrainSession,
    build_payload,
    submit_verdict,
    submit_verdict_checks,
)
import preflight  # noqa: E402

CONSULTANT_D1 = {"sharpe": 1.58, "fitness": 1.00, "turnover": (0.01, 0.70)}


def make_alpha(
    *,
    sharpe=1.80,
    fitness=2.10,
    turnover=0.16,
    returns=0.079,
    drawdown=0.044,
    margin=0.0020,
    checks=None,
    region="EUR",
    universe="TOP2500",
):
    return {
        "id": "TEST0001",
        "status": "UNSUBMITTED",
        "settings": {
            "region": region,
            "universe": universe,
            "delay": 1,
            "decay": 6,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.10,
        },
        "regular": {"code": "rank(ts_backfill(star_val_sector_rank, 60))"},
        "is": {
            "sharpe": sharpe,
            "fitness": fitness,
            "turnover": turnover,
            "returns": returns,
            "drawdown": drawdown,
            "margin": margin,
            "checks": checks if checks is not None else [],
        },
    }


def check(name, result, value=None, limit=None):
    return {"name": name, "result": result, "value": value, "limit": limit}


class FakeResponse:
    """最小 requests.Response 替身，只实现 submit 判定书用到的接口。"""

    def __init__(self, status_code=403, body=None):
        self.status_code = status_code
        self._body = body
        self.headers = {}
        self.text = ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


# --------------------------------------------------------------------------
# 1. ladder WARNING 必须在本地就当阻断
# --------------------------------------------------------------------------
class TestLadderStrict:
    def test_gate_report_blocks_warning_ladder(self):
        """实测 IS_LADDER_SHARPE 0.88/1.58 是 WARNING，提交时却 FAIL。"""
        brain = BrainSession(username="u", password="p")
        alpha = make_alpha(checks=[check("IS_LADDER_SHARPE", "WARNING", 0.88, 1.58)])
        ok, msgs = brain.gate_report(alpha, delay=1)
        assert ok is False
        assert any("IS_LADDER_SHARPE" in m for m in msgs)

    def test_gate_report_nonstrict_allows_warning(self):
        """strict=False 退回旧口径，便于复盘对照。"""
        brain = BrainSession(username="u", password="p")
        alpha = make_alpha(checks=[check("IS_LADDER_SHARPE", "WARNING", 0.88, 1.58)])
        ok, _ = brain.gate_report(alpha, delay=1, strict=False)
        assert ok is True

    def test_gate_report_passing_ladder_warning_is_fine(self):
        """WARNING 但 value >= limit 时不误伤。"""
        brain = BrainSession(username="u", password="p")
        alpha = make_alpha(checks=[check("IS_LADDER_SHARPE", "WARNING", 1.70, 1.58)])
        ok, _ = brain.gate_report(alpha, delay=1)
        assert ok is True

    def test_preflight_evaluate_rejects_ladder(self):
        res = preflight.evaluate(
            make_alpha(checks=[check("IS_LADDER_SHARPE", "WARNING", 0.88, 1.58)]),
            CONSULTANT_D1,
        )
        assert res["verdict"] == "NO-GO"
        assert any("IS_LADDER_SHARPE" in b for b in res["blockers"])

    def test_preflight_evaluate_go_on_clean_alpha(self):
        res = preflight.evaluate(make_alpha(checks=[check("IS_LADDER_SHARPE", "PASS", 1.80, 1.58)]),
                                 CONSULTANT_D1)
        assert res["verdict"] == "GO"

    def test_preflight_no_go_on_low_sharpe(self):
        res = preflight.evaluate(make_alpha(sharpe=1.20), CONSULTANT_D1)
        assert res["verdict"] == "NO-GO"

    def test_preflight_no_go_on_turnover_out_of_band(self):
        res = preflight.evaluate(make_alpha(turnover=0.85), CONSULTANT_D1)
        assert res["verdict"] == "NO-GO"


# --------------------------------------------------------------------------
# 1.1 质量闸门：平台线之上再卡 Fitness / Margin（质量 > 数量）
# --------------------------------------------------------------------------
class TestQualityGate:
    def test_gate_report_blocks_low_fitness(self):
        """平台 Fitness 1.0 只是允许提交；本地质量线要 2.0。"""
        brain = BrainSession(username="u", password="p")
        ok, msgs = brain.gate_report(make_alpha(fitness=1.60), delay=1)
        assert ok is False
        assert any("质量线" in m and "Fitness" in m for m in msgs)

    def test_gate_report_allows_low_fitness_when_quality_off(self):
        brain = BrainSession(username="u", password="p")
        ok, _ = brain.gate_report(make_alpha(fitness=1.60), delay=1, quality=False)
        assert ok is True

    def test_gate_report_blocks_low_margin(self):
        """Margin < 10‱ 赚不过手续费。"""
        brain = BrainSession(username="u", password="p")
        ok, msgs = brain.gate_report(make_alpha(margin=0.0005), delay=1)
        assert ok is False
        assert any("Margin" in m and "10‱" in m for m in msgs)

    def test_gate_report_missing_margin_is_note_not_blocker(self):
        brain = BrainSession(username="u", password="p")
        alpha = make_alpha()
        alpha["is"].pop("margin")
        ok, msgs = brain.gate_report(alpha, delay=1)
        assert ok is True
        assert any("Margin 缺失" in m for m in msgs)

    def test_gate_report_blocks_drawdown_larger_than_returns(self):
        """回撤大于收益的 PnL 形态不可接受。"""
        brain = BrainSession(username="u", password="p")
        ok, msgs = brain.gate_report(make_alpha(returns=0.05, drawdown=0.12), delay=1)
        assert ok is False
        assert any("Drawdown" in m for m in msgs)

    def test_preflight_no_go_on_low_margin(self):
        res = preflight.evaluate(make_alpha(margin=0.0004), CONSULTANT_D1)
        assert res["verdict"] == "NO-GO"
        assert any("Margin" in b for b in res["blockers"])

    def test_preflight_go_on_good_quality(self):
        res = preflight.evaluate(make_alpha(fitness=2.60, margin=0.0035), CONSULTANT_D1)
        assert res["verdict"] == "GO"
        assert any("质量线" in line for line in preflight.render(res).splitlines())


# --------------------------------------------------------------------------
# 1.2 数据历史闸门：LOW_DURATION < 500 天不能提交（2026-11-13 实测）
# --------------------------------------------------------------------------
class TestDurationGate:
    def test_duration_blockers_reads_check(self):
        from wq_api import MIN_DURATION_DAYS, duration_blockers

        assert MIN_DURATION_DAYS == 500
        assert duration_blockers({}) == []
        msgs = duration_blockers({"LOW_DURATION": check("LOW_DURATION", "FAIL", 50, 500)})
        assert msgs and "LOW_DURATION" in msgs[0]

    def test_gate_report_blocks_low_duration(self):
        """Sharpe 2.05 / Fitness 2.22 / Margin 65.5‱ 全绿也照样阻断。"""
        brain = BrainSession(username="u", password="p")
        alpha = make_alpha(checks=[check("LOW_DURATION", "FAIL", 50, 500)])
        ok, msgs = brain.gate_report(alpha, delay=1)
        assert ok is False
        assert any("LOW_DURATION" in m for m in msgs)

    def test_preflight_blocks_low_duration_check(self):
        res = preflight.evaluate(
            make_alpha(checks=[check("LOW_DURATION", "FAIL", 50, 500)]),
            CONSULTANT_D1,
        )
        assert res["verdict"] == "NO-GO"
        assert any("LOW_DURATION" in b for b in res["blockers"])

    def test_preflight_blocks_young_field_by_age(self):
        """LOW_DURATION 不在 is.checks 里时，用 dateCreated 年龄兜底。"""
        prior = preflight.crowding_prior(
            {"ebg_sector_18mo_marketcap_percent": 2},
            {"ebg_sector_18mo_marketcap_percent": 50.0},
        )
        res = preflight.evaluate(make_alpha(), CONSULTANT_D1, crowding=prior)
        assert res["verdict"] == "NO-GO"
        assert any("LOW_DURATION" in b for b in res["blockers"])
        assert "最年轻字段 50 天" in preflight.render(res)

    def test_preflight_allows_mature_field(self):
        prior = preflight.crowding_prior({"old_field": 3}, {"old_field": 900.0})
        res = preflight.evaluate(make_alpha(), CONSULTANT_D1, crowding=prior)
        assert res["verdict"] == "GO"
        assert any("数据历史" in line for line in preflight.render(res).splitlines())

    def test_unknown_age_does_not_block(self):
        prior = preflight.crowding_prior({"f": 3})
        res = preflight.evaluate(make_alpha(), CONSULTANT_D1, crowding=prior)
        assert res["verdict"] == "GO"

    def test_atom_expression_fields_are_extracted(self):
        """ATOM 骨架里的 vector_neut 会被 extract_signal_fields 当成分组算子，
        导致字段漏抽；preflight 必须兜底，否则拥挤度/年龄闸门被静默跳过。"""
        fields = preflight.signal_fields(
            "group_neutralize(vector_neut(ts_mean(ebg_sector_18mo_marketcap_percent, 20), "
            "ts_mean(ebg_sector_18mo_marketcap_percent, 250)), country)"
        )
        assert fields == ["ebg_sector_18mo_marketcap_percent"]


# --------------------------------------------------------------------------
# 2. 拥挤度先验
# --------------------------------------------------------------------------
class TestCrowdingPrior:
    def test_high_level_blocks(self):
        prior = preflight.crowding_prior({"star_val_sector_rank": 19800})
        assert prior["level"] == "high"
        res = preflight.evaluate(make_alpha(), CONSULTANT_D1, crowding=prior)
        assert res["verdict"] == "NO-GO"
        assert any("拥挤度" in b for b in res["blockers"])

    def test_mid_level_only_warns(self):
        prior = preflight.crowding_prior({"some_field": 2000})
        assert prior["level"] == "mid"
        res = preflight.evaluate(make_alpha(), CONSULTANT_D1, crowding=prior)
        assert res["verdict"] == "GO"
        assert any("拥挤度" in w for w in res["warnings"])

    def test_unknown_counts(self):
        assert preflight.crowding_prior({})["level"] == "unknown"
        assert preflight.crowding_prior({"f": None})["level"] == "unknown"


# --------------------------------------------------------------------------
# 3. run_many 跨 region 自动分组
# --------------------------------------------------------------------------
class TestRunManyGrouping:
    def test_groups_by_region_and_preserves_order(self):
        brain = BrainSession(username="u", password="p")
        brain.permissions = ["MULTI_SIMULATION"]
        batches: list[list[str]] = []

        def fake_run_batch(payloads, *, batch_size=8, verbose=False):
            batches.append([p["settings"]["region"] for p in payloads])
            from wq_api import SimulationResult

            return [
                SimulationResult("s", "COMPLETE", alpha_id=f"a{i}", payload=p)
                for i, p in enumerate(payloads)
            ]

        brain._run_batch = fake_run_batch  # type: ignore[method-assign]
        payloads = [
            build_payload("rank(close)", region="AMR"),
            build_payload("rank(close)", region="EUR"),
            build_payload("rank(close)", region="AMR"),
            build_payload("rank(close)", region="ASI"),
        ]
        results = brain.run_many(payloads, verbose=False)

        # 不再整批失败，而是分成 3 组（AMR×2 / EUR×1 / ASI×1）
        assert len(batches) == 3
        assert sorted(sum(batches, [])) == ["AMR", "AMR", "ASI", "EUR"]
        # 返回顺序与入参一致
        assert [r.payload["settings"]["region"] for r in results] == ["AMR", "EUR", "AMR", "ASI"]

    def test_single_group_stays_one_batch(self):
        brain = BrainSession(username="u", password="p")
        brain.permissions = ["MULTI_SIMULATION"]
        calls: list[int] = []

        def fake_run_batch(payloads, *, batch_size=8, verbose=False):
            calls.append(len(payloads))
            from wq_api import SimulationResult

            return [SimulationResult("s", "COMPLETE", alpha_id="a", payload=p) for p in payloads]

        brain._run_batch = fake_run_batch  # type: ignore[method-assign]
        payloads = [build_payload("rank(close)", universe=u, decay=d)
                    for u, d in (("TOP3000", 4), ("TOP1200", 6))]
        brain.run_many(payloads)
        assert calls == [2]


# --------------------------------------------------------------------------
# 4. build_payload 键校验
# --------------------------------------------------------------------------
class TestBuildPayloadValidation:
    def test_name_rejected_with_hint(self):
        with pytest.raises(BrainError) as exc:
            build_payload("rank(close)", name="V1")
        assert "name" in str(exc.value)

    def test_unknown_key_rejected(self):
        with pytest.raises(BrainError):
            build_payload("rank(close)", universeX="TOP3000")

    def test_valid_overrides_ok(self):
        payload = build_payload("rank(close)", region="EUR", decay=5, universe="TOP2500")
        assert payload["settings"]["region"] == "EUR"
        assert payload["settings"]["decay"] == 5
        assert payload["regular"] == "rank(close)"


# --------------------------------------------------------------------------
# 5. 提交判定书解析
# --------------------------------------------------------------------------
class TestSubmitVerdict:
    def test_parse_fails(self):
        resp = FakeResponse(
            body={"is": {"checks": [
                check("IS_LADDER_SHARPE", "FAIL", 0.88, 1.58),
                check("PROD_CORRELATION", "FAIL", 0.8314, 0.7),
                check("LOW_SHARPE", "PASS", 1.80, 1.58),
            ]}}
        )
        verdict = submit_verdict(resp)
        assert "IS_LADDER_SHARPE=0.88" in verdict
        assert "PROD_CORRELATION=0.8314" in verdict
        assert "LOW_SHARPE" not in verdict
        assert len(submit_verdict_checks(resp)["fails"]) == 2

    def test_quota_exhausted_is_empty_fails(self):
        """403 但 body 里没有 FAIL ⇒ 真的是配额耗尽，不能叫"相关性不过"。"""
        resp = FakeResponse(body={"is": {"checks": [check("LOW_SHARPE", "PASS", 1.8, 1.58)]}})
        assert submit_verdict(resp) == ""
        assert submit_verdict_checks(resp)["fails"] == []

    def test_non_json_body(self):
        resp = FakeResponse(body=None)
        assert submit_verdict(resp) == ""
        assert submit_verdict_checks(resp)["fails"] == []


# --------------------------------------------------------------------------
# 6. PENDING 相关性不能被当成 0
# --------------------------------------------------------------------------
class TestPendingChecks:
    def test_pending_listed(self):
        alpha = make_alpha(checks=[
            check("SELF_CORRELATION", "PENDING"),
            check("PROD_CORRELATION", "PENDING"),
            check("LOW_SHARPE", "PASS", 1.8, 1.58),
        ])
        assert set(BrainSession.pending_checks(alpha)) == {"SELF_CORRELATION", "PROD_CORRELATION"}

    def test_gate_report_flags_pending_as_note(self):
        brain = BrainSession(username="u", password="p")
        alpha = make_alpha(checks=[check("PROD_CORRELATION", "PENDING")])
        ok, msgs = brain.gate_report(alpha, delay=1)
        assert ok is True  # PENDING 不是阻断，但也绝不能当成 0
        assert any("PENDING" in m for m in msgs)


# ---------------------------------------------------------------------------
# submit_verified 的循环语义（2026-11-04 实测：成功 vs 失败的 POST 次数极不对称）
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, code: int, body: dict | None = None):
        self.status_code = code
        self._body = body or {}
        self.headers: dict = {}
        self.text = ""

    def json(self):
        return self._body


class _FakeBrain:
    """最小替身：只实现 submit_verified 用到的 submit / alpha。"""

    def __init__(self, codes, statuses):
        self.codes = codes
        self.statuses = statuses
        self.posts = 0
        self.alpha_lookups = 0

    def submit(self, alpha_id):
        code = self.codes[min(self.posts, len(self.codes) - 1)]
        self.posts += 1
        body = {"is": {"checks": []}}
        if code == 403:
            body = {"is": {"checks": [
                {"name": "PROD_CORRELATION", "result": "FAIL", "value": 0.7621, "limit": 0.7}
            ]}}
        return _FakeResp(code, body)

    def alpha(self, alpha_id):
        st = self.statuses[min(self.alpha_lookups, len(self.statuses) - 1)]
        self.alpha_lookups += 1
        return {"status": st, "dateSubmitted": "2026-11-04T03:47:19" if st == "ACTIVE" else None}


def test_submit_verified_exits_early_when_alpha_turns_active(monkeypatch):
    """成功路径：几十次 200 之后转 ACTIVE —— 必须中途收工，不能把 max_posts 烧满。"""
    import wq_api

    monkeypatch.setattr(wq_api.time, "sleep", lambda *_: None)
    brain = _FakeBrain(
        codes=[200],
        # 每 5 次 POST 查一次状态：第 1、2 次查还是 UNSUBMITTED，第 3 次转 ACTIVE
        statuses=["UNSUBMITTED", "UNSUBMITTED", "ACTIVE"],
    )
    outcome = wq_api.submit_verified(brain, "TEST0001", max_posts=100, status_check_every=5)

    assert outcome == "ACTIVE"
    assert brain.posts == 15, f"应在第三次状态检查（第 15 次 POST）收工，实际 POST {brain.posts} 次"


def test_submit_verified_returns_verdict_on_403(monkeypatch):
    """失败路径：403 判定书要立即返回，且带出 prod corr 数值。"""
    import wq_api

    monkeypatch.setattr(wq_api.time, "sleep", lambda *_: None)
    brain = _FakeBrain(codes=[200, 403], statuses=["UNSUBMITTED"])

    outcome = wq_api.submit_verified(brain, "TEST0001", max_posts=100)

    assert outcome.startswith("submit_blocked(")
    assert "PROD_CORRELATION=0.7621" in outcome
    assert brain.posts == 2
