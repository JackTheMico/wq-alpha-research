"""优化 0.5*IV skew180 + 0.5*ROE（LLMbXVjn: S=1.59 F=0.95 LOW_FITNESS FAIL）。

分两条线：
  Track 1 —— 原表达式做参数邻域搜索（Fitness 优化）
  Track 2 —— 换腿（IV 腿 / 质量腿都换成池内未占用的字段），规避 SELF_CORRELATION

Fitness 公式已实测确认：F = Sharpe * sqrt(Returns / max(TO, 0.125))
=> TO < 12.5% 时降 TO 对 Fitness 毫无贡献，只有提 Sharpe 或提 Returns 才有效。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from wq_api import BrainSession, SimulationCache, build_payload  # noqa: E402

FIELDS_JSON = REPO / "references" / "wq_usa_top3000_delay1_data_fields.json"

BASE_EXPR = (
    "0.5 * rank(ts_mean((implied_volatility_call_180 - implied_volatility_put_180) "
    "/ implied_volatility_mean_180, 5))\n"
    "+ 0.5 * group_rank(ts_rank(operating_income / equity, 126), subindustry)"
)

IV_SKEW_270 = "rank(ts_mean(implied_volatility_mean_skew_270, 5))"
IV_SKEW_360 = "rank(ts_mean(implied_volatility_mean_skew_360, 5))"
IV_CP_270 = (
    "rank(ts_mean((implied_volatility_call_270 - implied_volatility_put_270) "
    "/ implied_volatility_mean_270, 5))"
)
IV_CP_120 = (
    "rank(ts_mean((implied_volatility_call_120 - implied_volatility_put_120) "
    "/ implied_volatility_mean_120, 5))"
)
PCR_270 = "group_rank(ts_rank(pcr_oi_270, 126), industry)"

Q_CF_E = "group_rank(ts_rank(cashflow_op / equity, 126), subindustry)"
Q_CF_A = "group_rank(ts_rank(cashflow_op / assets, 126), subindustry)"
Q_CF_S = "group_rank(ts_rank(cashflow_op / sales, 126), subindustry)"
Q_OI_A = "group_rank(ts_rank(operating_income / assets, 126), subindustry)"
Q_EV = "group_rank(ts_rank(ebitda / enterprise_value, 126), subindustry)"

MIX = "0.5 * {a}\n+ 0.5 * {b}"

CANDIDATES: list[tuple[str, str, dict]] = [
    # ---- Track 1：原表达式参数邻域 ----
    ("T1a base decay=6", BASE_EXPR, {"decay": 6}),
    ("T1b base decay=15 INDUSTRY", BASE_EXPR, {"decay": 15, "neutralization": "INDUSTRY"}),
    ("T1c base decay=0 trunc=0.10", BASE_EXPR, {"decay": 0, "truncation": 0.10}),
    # ---- Track 2：换腿 ----
    ("T2a skew270 + CF/equity", MIX.format(a=IV_SKEW_270, b=Q_CF_E), {"decay": 10}),
    ("T2b skew270 + OI/assets", MIX.format(a=IV_SKEW_270, b=Q_OI_A), {"decay": 10}),
    ("T2c skew360 + EBITDA/EV", MIX.format(a=IV_SKEW_360, b=Q_EV), {"decay": 10}),
    ("T2d cp270 + CF/assets", MIX.format(a=IV_CP_270, b=Q_CF_A), {"decay": 10}),
    ("T2e cp120 + CF/equity", MIX.format(a=IV_CP_120, b=Q_CF_E), {"decay": 10}),
    ("T2f pcr270 + CF/equity", MIX.format(a=PCR_270, b=Q_CF_E), {"decay": 10}),
    ("T2g skew270 + CF/sales", MIX.format(a=IV_SKEW_270, b=Q_CF_S), {"decay": 10}),
]


# ---------------------------------------------------------------------------
# Round 2：把 Round 1 的两个发现叠加起来
#   ① INDUSTRY 中性化是 Fitness 的解药（T1b: F 0.95 -> 1.08，Returns 4.47% -> 5.32%）
#   ② 换腿后仍卡 LOW_SUB_UNIVERSE_SHARPE（T2e: 0.29 vs 0.73）→ 用更弱的中性化 / 更低的
#      truncation / 换期限去修，同时保持腿的独占性
# ---------------------------------------------------------------------------
IV_CP_90 = (
    "rank(ts_mean((implied_volatility_call_90 - implied_volatility_put_90) "
    "/ implied_volatility_mean_90, 5))"
)
IV_CP_120_W20 = (
    "rank(ts_mean((implied_volatility_call_120 - implied_volatility_put_120) "
    "/ implied_volatility_mean_120, 20))"
)
Q_CF_E_IND = "group_rank(ts_rank(cashflow_op / equity, 126), industry)"
Q_FCF_A = "group_rank(ts_rank(free_cash_flow_reported_value / assets, 126), subindustry)"
# pv1 反转腿：ACTIVE 池里无人使用（omEe0Gdl 是 UNSUBMITTED，不构成冲突源）
REV = "rank(-(close / open - 1))"

CANDIDATES_R2: list[tuple[str, str, dict]] = [
    # A. 修 T2e 的 LOW_SUB_UNIVERSE_SHARPE（0.29 vs 0.73）
    ("R2-1 cp120+CF/E INDUSTRY d10", MIX.format(a=IV_CP_120, b=Q_CF_E),
     {"decay": 10, "neutralization": "INDUSTRY"}),
    ("R2-2 cp120+CF/E INDUSTRY d15", MIX.format(a=IV_CP_120, b=Q_CF_E),
     {"decay": 15, "neutralization": "INDUSTRY"}),
    ("R2-3 cp120+CF/E SUBIND trunc0.05", MIX.format(a=IV_CP_120, b=Q_CF_E),
     {"decay": 10, "neutralization": "SUBINDUSTRY", "truncation": 0.05}),
    ("R2-4 cp120+CF/E(ind) INDUSTRY d10", MIX.format(a=IV_CP_120, b=Q_CF_E_IND),
     {"decay": 10, "neutralization": "INDUSTRY"}),
    ("R2-5 cp270+CF/E INDUSTRY d10", MIX.format(a=IV_CP_270, b=Q_CF_E),
     {"decay": 10, "neutralization": "INDUSTRY"}),
    ("R2-6 cp90+CF/E INDUSTRY d10", MIX.format(a=IV_CP_90, b=Q_CF_E),
     {"decay": 10, "neutralization": "INDUSTRY"}),
    ("R2-7 cp120+FCF/assets INDUSTRY d10", MIX.format(a=IV_CP_120, b=Q_FCF_A),
     {"decay": 10, "neutralization": "INDUSTRY"}),
    # B. 降相关：稀释 IV 腿 / 换成池内无人用的 pv1 反转腿
    ("R2-8 0.3cp120+0.7OI/assets IND", f"0.3 * {IV_CP_120}\n+ 0.7 * {Q_OI_A}",
     {"decay": 10, "neutralization": "INDUSTRY"}),
    ("R2-9 0.4cp120+0.6reversal IND d15", f"0.4 * {IV_CP_120}\n+ 0.6 * {REV}",
     {"decay": 15, "neutralization": "INDUSTRY"}),
    ("R2-10 0.4rev+0.6CF/E IND d10", f"0.4 * {REV}\n+ 0.6 * {Q_CF_E}",
     {"decay": 10, "neutralization": "INDUSTRY"}),
]


def preflight_fields(exprs: list[str]) -> None:
    """跑之前先用本地字段快照核一遍，避免把仿真槽浪费在拼错的字段上。"""
    known = {f["id"] for f in json.loads(FIELDS_JSON.read_text(encoding="utf-8"))}
    import re

    tokens = set()
    for e in exprs:
        for t in re.findall(r"[a-z_][a-z0-9_]*", e):
            tokens.add(t)
    builtin = {
        "rank", "group_rank", "ts_rank", "ts_mean", "ts_delta", "ts_std_dev", "ts_zscore",
        "ts_decay_linear", "ts_backfill", "group_backfill", "group_neutralize", "group_zscore",
        "zscore", "normalize", "scale", "winsorize", "if_else", "trade_when", "vec_avg",
        "vec_sum", "subindustry", "industry", "sector", "market", "bucket", "abs", "log",
        "sqrt", "sign", "min", "max", "inverse", "mean", "std", "sum", "power", "and", "or",
        "not", "is", "nan", "otherwise", "range", "std", "densify", "quantile", "regression_neut",
    }
    unknown = sorted(t for t in tokens if t not in known and t not in builtin and not t.isdigit())
    print(f"[preflight] 未知 token: {unknown if unknown else '无'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑名字含该子串的候选")
    ap.add_argument("--round", type=int, default=1, choices=(1, 2))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pool = CANDIDATES if args.round == 1 else CANDIDATES_R2
    cands = [c for c in pool if args.only in c[0]] if args.only else pool
    preflight_fields([c[1] for c in pool])

    if args.dry_run:
        for name, expr, ov in cands:
            print(f"\n--- {name}  overrides={ov}")
            print(expr)
        return

    brain = BrainSession()
    brain.authenticate()
    print(f"user={brain.user_id} perms={brain.permissions} thresholds={brain.thresholds(1)}")

    cache = SimulationCache(REPO / ".workbuddy" / "simulation_cache.jsonl")
    payloads = [build_payload(expr, **ov) for _, expr, ov in cands]

    results = brain.run_many(payloads, batch_size=10, verbose=True)

    out = []
    print("\n" + "=" * 96)
    for (name, expr, ov), res in zip(cands, results):
        if not res.alpha_id:
            print(f"❌ [{name}] 无 alpha: status={res.status} msg={res.message[:160]}")
            out.append({"name": name, "error": res.message})
            continue
        alpha = brain.alpha(res.alpha_id)
        isd = alpha.get("is") or {}
        s, f = isd.get("sharpe") or 0, isd.get("fitness") or 0
        to, ret = isd.get("turnover") or 0, isd.get("returns") or 0
        ok, msgs = brain.gate_report(alpha)
        f_calc = s * math.sqrt(ret / max(to, 0.125)) if s and ret else 0
        flag = "✅" if ok else "❌"
        print(
            f"{flag} [{name}] {res.alpha_id}  S={s:.3f} F={f:.3f}(calc {f_calc:.3f}) "
            f"TO={to*100:.1f}% Ret={ret*100:.2f}% DD={(isd.get('drawdown') or 0)*100:.1f}%"
        )
        for m in msgs:
            print(f"      · {m}")
        for c in isd.get("checks", []):
            if c.get("result") in ("FAIL", "ERROR"):
                print(f"      ✗ {c.get('name')}: {c.get('value')} vs limit {c.get('limit')}")
        out.append({
            "name": name, "alpha_id": res.alpha_id, "expression": expr, "overrides": ov,
            "sharpe": s, "fitness": f, "turnover": to, "returns": ret,
            "drawdown": isd.get("drawdown"), "gate_ok": ok, "gate_msgs": msgs,
        })

    dest = REPO / ".workbuddy" / f"opt_ivskew_results_r{args.round}.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n结果已写入 {dest}")


if __name__ == "__main__":
    main()
