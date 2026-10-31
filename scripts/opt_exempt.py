"""豁免路径：克隆 proven 高 Sharpe 结构，换掉饱和腿，扫 neut/decay，目标 2.5+。

设计依据（实时 ACTIVE 池 22 条）：
- Gre2WN65 (S=2.75): 0.5*group_rank(-ts_rank(enterprise_value/cashflow,126),industry)
                       + 0.5*group_rank(ts_rank(operating_income/equity,126),subindustry)
  → 估值腿 + 质量腿，INDUSTRY/decay=0 是冠军结构。
- bldLbe6R (S=2.22,F=2.12): 4 腿混合，SECTOR/decay=4，完全不含 OI/equity，最分化。
- operating_income/equity 在 9 条 ACTIVE 出现 = 饱和源；豁免若要撞 Gre2WN65(2.75) 需 3.03，
  故本批把质量腿换成 FCF/equity、FCF/liabilities、return_equity/close 等未饱和腿。

所有字段均来自 ACTIVE 池已验证存在的字段，preflight 必过。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wq_api import BrainSession, build_payload, DEFAULT_SETTINGS, SimulationCache

REPO = Path(__file__).resolve().parent.parent

# 基准中性化 / decay：Gre2WN65=INDUSTRY/d0，bldLbe6R=SECTOR/d4
CANDIDATES: list[tuple[str, str, dict]] = [
    # ---- A 组：Gre2WN65 估值腿 + 未饱和质量腿（换掉 OI/equity）----
    ("A1 EV/cf+FCF/eq INDUSTRY d0",
     "0.5*group_rank(-ts_rank(enterprise_value/cashflow,126),industry)"
     "+0.5*group_rank(ts_rank(free_cash_flow_reported_value/equity,126),subindustry)",
     {"decay": 0, "neutralization": "INDUSTRY", "truncation": 0.08}),
    ("A2 EV/cf+FCF/eq SECTOR d4",
     "0.5*group_rank(-ts_rank(enterprise_value/cashflow,126),sector)"
     "+0.5*group_rank(ts_rank(free_cash_flow_reported_value/equity,126),sector)",
     {"decay": 4, "neutralization": "SECTOR", "truncation": 0.08}),
    ("A3 EV/cf+FCF/liab INDUSTRY d0",
     "0.5*group_rank(-ts_rank(enterprise_value/cashflow,126),industry)"
     "+0.5*group_rank(ts_rank(free_cash_flow_reported_value/liabilities,126),industry)",
     {"decay": 0, "neutralization": "INDUSTRY", "truncation": 0.08}),

    # ---- B 组：bldLbe6R 4 腿混合（无 OI/equity），扫 neut/decay ----
    ("B1 4leg INDUSTRY d0 (sweep)",
     "0.25*group_rank(ts_rank(est_eps/close,126),industry)"
     "+0.25*group_rank(ts_rank(free_cash_flow_reported_value/liabilities,126),industry)"
     "+0.25*group_rank(ts_rank(-liabilities/assets,126),industry)"
     "+0.25*group_rank(ts_rank(-close/ts_mean(close,252),63),subindustry)",
     {"decay": 0, "neutralization": "INDUSTRY", "truncation": 0.08}),
    ("B2 4leg EV/cf swapped SECTOR d4",
     "0.25*group_rank(ts_rank(est_eps/close,126),sector)"
     "+0.25*group_rank(ts_rank(enterprise_value/cashflow,126),sector)"
     "+0.25*group_rank(ts_rank(-liabilities/assets,126),sector)"
     "+0.25*group_rank(ts_rank(-close/ts_mean(close,252),63),subindustry)",
     {"decay": 4, "neutralization": "SECTOR", "truncation": 0.08}),
    ("B3 3leg EV/cf+eps+FCF/liab SECTOR d4",
     "0.34*group_rank(ts_rank(enterprise_value/cashflow,126),sector)"
     "+0.33*group_rank(ts_rank(est_eps/close,126),sector)"
     "+0.33*group_rank(ts_rank(free_cash_flow_reported_value/liabilities,126),sector)",
     {"decay": 4, "neutralization": "SECTOR", "truncation": 0.08}),

    # ---- C 组：2 腿未饱和质量组合（无 OI/equity）----
    ("C1 eps/close+FCF/liab INDUSTRY d0",
     "0.5*group_rank(ts_rank(est_eps/close,126),industry)"
     "+0.5*group_rank(ts_rank(free_cash_flow_reported_value/liabilities,126),industry)",
     {"decay": 0, "neutralization": "INDUSTRY", "truncation": 0.08}),
    ("C2 ROE/close+analyst SECTOR d4",
     "0.5*group_rank(ts_rank(return_equity/close,252),sector)"
     "+0.5*group_rank(ts_rank(anl4_fs_detail_estimates_basic_qf_v4_nd_cfps_number,252),sector)",
     {"decay": 4, "neutralization": "SECTOR", "truncation": 0.08}),
    ("C3 (cf-capex)/close+FCF/eq SUBIND d0",
     "0.5*group_rank(ts_rank((est_cashflow_op-est_capex)/close,126),subindustry)"
     "+0.5*group_rank(ts_rank(free_cash_flow_reported_value/equity,126),subindustry)",
     {"decay": 0, "neutralization": "SUBINDUSTRY", "truncation": 0.08}),
    ("C4 4leg fresh (no OI/eq,no FCF/liab) SECTOR d4",
     "0.25*group_rank(ts_rank(enterprise_value/cashflow,126),sector)"
     "+0.25*group_rank(ts_rank(est_eps/close,126),sector)"
     "+0.25*group_rank(ts_rank(return_equity/close,126),sector)"
     "+0.25*group_rank(ts_rank(-close/ts_mean(close,252),63),subindustry)",
     {"decay": 4, "neutralization": "SECTOR", "truncation": 0.08}),
]


def preflight_fields(exprs: list[str]) -> None:
    known = set()
    for name, expr, _ in CANDIDATES:
        known.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr))
    builtin = {
        "rank", "group_rank", "ts_rank", "ts_mean", "ts_delta", "ts_std_dev", "ts_zscore",
        "ts_decay_linear", "ts_backfill", "group_backfill", "group_neutralize", "group_zscore",
        "zscore", "normalize", "scale", "winsorize", "if_else", "trade_when", "vec_avg",
        "vec_sum", "subindustry", "industry", "sector", "market", "bucket", "abs", "log",
        "sqrt", "sign", "min", "max", "inverse", "mean", "std", "sum", "power", "and", "or",
        "not", "is", "nan", "otherwise", "range", "densify", "quantile", "regression_neut",
    }
    unknown = sorted(t for t in known if t not in builtin and not t.isdigit())
    # 注：preflight 只校验 token 合法性，字段存在性由仿真 API 判定
    print(f"[preflight] 非内置 token（含字段名，需仿真确认存在性）: {unknown}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑名字含该子串的候选")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cands = [c for c in CANDIDATES if args.only in c[0]] if args.only else CANDIDATES
    preflight_fields(CANDIDATES)

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

    # batch_size=1：每条独立单仿真，一条报错不会连坐整批（多仿真父任务失败会 CANCEL 同批所有子任务）
    results = brain.run_many(payloads, batch_size=1, verbose=True)

    # 兜底：偶发 API 返回空 alpha_id（仿真实际已创建），重试一次
    for i, (name, expr, ov), res in zip(range(len(cands)), cands, results):
        if not res.alpha_id:
            print(f"  ↻ 重试 [{name}]（首次 alpha_id 为空）")
            try:
                res2 = brain.run(payloads[i], verbose=False)
                if res2.alpha_id:
                    results[i] = res2
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ 重试失败 [{name}]: {e}")

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

    dest = REPO / ".workbuddy" / "opt_exempt_results.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n结果已写入 {dest}")


if __name__ == "__main__":
    main()
