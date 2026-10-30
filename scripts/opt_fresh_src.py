"""第三轮：换数据源，绕开 PROD_CORRELATION。

背景：`E560gqE1`（0.4×pv1 反转 + 0.6×cashflow_op/equity）指标全 PASS，却被
`PROD_CORRELATION 0.8045` 否决。判读是「两条腿都太拥挤」，而同族内换参数/换期限
不改变相关性量级（IV 簇 7 次仿真的结论）。所以本轮只做一件事：**换数据源**。

数据源选择依据 `scripts/datasource_scan.py` 的零成本盘点（我方 22 条 ACTIVE 的占用）：
  * pv/pv13      供应链/竞品关系          我方 0 次，cov 0.71–0.99
  * model/model51 系统性/特质风险指标     我方 0 次，cov 0.94–0.98
  * news/news18  Ravenpack 新闻情绪      我方 1 次，cov 0.50
  * socialmedia/socialmedia8 社交情绪     我方 0 次，cov 1.00
对比之下被放弃的：pv/pv1（我方 37 次）、fundamental6（36）、analyst4（11）、option8（12）。

结构仍用已被验证的双腿混合；settings 用本轮最优的 INDUSTRY + decay 10 + trunc 0.08。
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

# ---- 腿定义（全部来自我方 ACTIVE 零/低占用 dataset）----
# pv13：竞品 / 合作伙伴的当日收益与关系数量
REL_COMP = "rank(ts_mean(rel_ret_comp, 5))"          # 竞争对手平均当日收益（领先-滞后）
REL_PART = "rank(ts_mean(rel_ret_part, 5))"          # 合作伙伴平均当日收益
REL_NUM = "rank(rel_num_all)"                        # 产品重叠公司数（竞争强度）

# model51：风险分解指标（低特质波动 / 低 beta 异象）
LOW_IDIO_360 = "rank(-unsystematic_risk_last_360_days)"
LOW_IDIO_90 = "rank(-unsystematic_risk_last_90_days)"
LOW_BETA = "rank(-beta_last_360_days_spy)"

# news18：Ravenpack 新闻情绪
RP_CSS = "rank(ts_mean(rp_css_business, 20))"        # 商业类新闻综合情绪
RP_ESS = "rank(ts_mean(rp_ess_ratings, 20))"         # 分析师评级类新闻事件情绪

# socialmedia8：社交情绪
SNT = "rank(ts_mean(snt_social_value, 20))"

MIX = "{a}\n+ {b}"
DEFAULT = {"decay": 10, "neutralization": "INDUSTRY", "truncation": 0.08}

CANDIDATES: list[tuple[str, str, dict]] = [
    # A. pv13（供应链/竞品） × model51（风险）
    ("F1 0.5comp+0.5lowIdio360", MIX.format(a=f"0.5 * {REL_COMP}", b=f"0.5 * {LOW_IDIO_360}"), dict(DEFAULT)),
    ("F2 0.4comp+0.6lowIdio360", MIX.format(a=f"0.4 * {REL_COMP}", b=f"0.6 * {LOW_IDIO_360}"), dict(DEFAULT)),
    ("F3 0.5comp+0.5lowBeta", MIX.format(a=f"0.5 * {REL_COMP}", b=f"0.5 * {LOW_BETA}"), dict(DEFAULT)),
    ("F4 0.5part+0.5lowIdio360", MIX.format(a=f"0.5 * {REL_PART}", b=f"0.5 * {LOW_IDIO_360}"), dict(DEFAULT)),
    ("F9 0.5relNum+0.5lowIdio360", MIX.format(a=f"0.5 * {REL_NUM}", b=f"0.5 * {LOW_IDIO_360}"), dict(DEFAULT)),
    # B. news18（新闻情绪） × model51 / pv13
    ("F5 0.5comp+0.5RPcss", MIX.format(a=f"0.5 * {REL_COMP}", b=f"0.5 * {RP_CSS}"), dict(DEFAULT)),
    ("F6 0.5RPess+0.5lowIdio90", MIX.format(a=f"0.5 * {RP_ESS}", b=f"0.5 * {LOW_IDIO_90}"), dict(DEFAULT)),
    ("F10 0.5RPcss+0.5lowBeta", MIX.format(a=f"0.5 * {RP_CSS}", b=f"0.5 * {LOW_BETA}"), dict(DEFAULT)),
    # C. socialmedia8（社交情绪） × model51 / pv13
    ("F7 0.5snt+0.5lowIdio360", MIX.format(a=f"0.5 * {SNT}", b=f"0.5 * {LOW_IDIO_360}"), dict(DEFAULT)),
    ("F8 0.5snt+0.5comp", MIX.format(a=f"0.5 * {SNT}", b=f"0.5 * {REL_COMP}"), dict(DEFAULT)),
]

# ---------------------------------------------------------------------------
# 第四轮：修正选源口径 —— 「全局热门（userCount≥1500）」∩「我方零使用」
#
# 第三轮只按「我方零使用」挑，结果选中了全局也冷门的字段（model51 最高 4140、
# pv13 2818、socialmedia8 2783、news18 1238），10 条全部 Sharpe 0.10–0.52，
# 且 model51 腿普遍带 46%–64% 回撤 + CONCENTRATED_WEIGHT FAIL。
# ⇒ 冷门是有原因的：全局冷门 ≈ 本来就弱。真正的甜点区是**别人验证过、我没用过**。
#
# 注：anl4_*_flag / *_ft 是「forecast type」分类标记（revision/new/...），不是
# 数值预测值，不能做 ts_rank；同族只有 *_number（覆盖数量）、anl4_dts_rspe
# （估计标准差=分析师分歧）、anl4_ebit_value（公告实际值）是数值字段。
# ---------------------------------------------------------------------------
ILLIQ = "rank(-adv20)"                                              # 低流动性溢价
DISP = "group_rank(ts_rank(-anl4_dts_rspe, 126), subindustry)"      # 分析师分歧（分歧大 → 高估）
COVER = "rank(-anl4_netprofit_number)"                              # 低分析师覆盖度
CAPEX = "group_rank(ts_rank(-capex / sales, 126), subindustry)"     # 低资本开支强度
RANGE = "rank(-ts_mean((high - low) / close, 20))"                  # 低日内波动
SHRS = "rank(-ts_delta(sharesout, 250))"                            # 净回购（股本收缩）

CANDIDATES_R4: list[tuple[str, str, dict]] = [
    ("R4-1 0.5illiq+0.5disp", MIX.format(a=f"0.5 * {ILLIQ}", b=f"0.5 * {DISP}"), dict(DEFAULT)),
    ("R4-2 0.5illiq+0.5cover", MIX.format(a=f"0.5 * {ILLIQ}", b=f"0.5 * {COVER}"), dict(DEFAULT)),
    ("R4-3 0.5disp+0.5capex", MIX.format(a=f"0.5 * {DISP}", b=f"0.5 * {CAPEX}"), dict(DEFAULT)),
    ("R4-4 0.5illiq+0.5capex", MIX.format(a=f"0.5 * {ILLIQ}", b=f"0.5 * {CAPEX}"), dict(DEFAULT)),
    ("R4-5 0.5range+0.5disp", MIX.format(a=f"0.5 * {RANGE}", b=f"0.5 * {DISP}"), dict(DEFAULT)),
    ("R4-6 0.5shrs+0.5disp", MIX.format(a=f"0.5 * {SHRS}", b=f"0.5 * {DISP}"), dict(DEFAULT)),
    ("R4-7 0.4illiq+0.3disp+0.3capex",
     f"0.4 * {ILLIQ}\n+ 0.3 * {DISP}\n+ 0.3 * {CAPEX}", dict(DEFAULT)),
    ("R4-8 0.5cover+0.5disp", MIX.format(a=f"0.5 * {COVER}", b=f"0.5 * {DISP}"), dict(DEFAULT)),
    ("R4-9 0.5illiq+0.5range", MIX.format(a=f"0.5 * {ILLIQ}", b=f"0.5 * {RANGE}"), dict(DEFAULT)),
    ("R4-10 0.6disp+0.4shrs", MIX.format(a=f"0.6 * {DISP}", b=f"0.4 * {SHRS}"), dict(DEFAULT)),
]


def preflight_fields(exprs: list[str]) -> None:
    """跑之前先用本地字段快照核一遍，避免把仿真槽浪费在拼错的字段上。"""
    import re

    known = {f["id"] for f in json.loads(FIELDS_JSON.read_text(encoding="utf-8"))}
    tokens: set[str] = set()
    for e in exprs:
        tokens.update(re.findall(r"[a-z_][a-z0-9_]*", e))
    builtin = {
        "rank", "group_rank", "ts_rank", "ts_mean", "ts_delta", "ts_std_dev", "ts_zscore",
        "ts_decay_linear", "ts_backfill", "group_backfill", "group_neutralize", "group_zscore",
        "zscore", "normalize", "scale", "winsorize", "if_else", "trade_when", "vec_avg",
        "vec_sum", "subindustry", "industry", "sector", "market", "bucket", "abs", "log",
        "sqrt", "sign", "min", "max", "inverse", "mean", "std", "sum", "power", "and", "or",
        "not", "is", "nan", "otherwise", "range", "densify", "quantile", "regression_neut",
    }
    unknown = sorted(t for t in tokens if t not in known and t not in builtin and not t.isdigit())
    print(f"[preflight] 未知 token: {unknown if unknown else '无'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑名字含该子串的候选")
    ap.add_argument("--round", type=int, default=3, choices=(3, 4))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pool = CANDIDATES if args.round == 3 else CANDIDATES_R4
    cands = [c for c in pool if args.only in c[0]] if args.only else pool
    preflight_fields([c[1] for c in pool])

    if args.dry_run:
        for name, expr, ov in cands:
            print(f"\n--- {name}  overrides={ov}")
            print(expr)
        return 0

    brain = BrainSession(credential_file=str(REPO / "credential.txt"))
    brain.authenticate()
    print(f"user={brain.user_id} consultant={brain.is_consultant} "
          f"thresholds={brain.thresholds(1)}", flush=True)

    cache = SimulationCache(REPO / ".workbuddy" / "simulation_cache.jsonl")
    payloads = [build_payload(expr, **ov) for _, expr, ov in cands]
    results = brain.run_cached(payloads, cache, batch_size=10, verbose=True)

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
        # 反算校验用；returns 可能为负（亏损 alpha），此时不做开根
        f_calc = s * math.sqrt(ret / max(to, 0.125)) if s and ret and ret > 0 else 0
        print(
            f"{'✅' if ok else '❌'} [{name}] {res.alpha_id}  S={s:.3f} F={f:.3f}(calc {f_calc:.3f}) "
            f"TO={to * 100:.1f}% Ret={ret * 100:.2f}% DD={(isd.get('drawdown') or 0) * 100:.1f}%",
            flush=True,
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

    dest = REPO / ".workbuddy" / f"opt_fresh_results_r{args.round}.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n结果已写入 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
