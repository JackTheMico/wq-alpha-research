#!/usr/bin/env python3
"""WQ Bull Trap 优化 第三轮 — V10 vs V6，并做 SELF_CORRELATION 前置检查。

相关性改用共享实现：`status=ACTIVE` 服务端过滤 + 日收益按**日期交集**对齐
（旧版要求 len 完全相等，日期错位时会静默跳过大量对比）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import (  # noqa: E402
    BrainSession,
    aligned_corr,
    print_row,
    simulate_one,
    to_returns,
)

BASE = {
    "region": "USA", "universe": "TOP3000", "delay": 1,
    "decay": 0, "neutralization": "INDUSTRY", "truncation": 0.08,
    "nanHandling": "ON",
}

NEWS_PART = (
    "winsorize(-ts_backfill(news_max_up_ret,60) * "
    "abs(ts_regression(ts_backfill(news_pct_1min,60), ts_step(1), 5, rettype=2)),std = 4)"
)
FUND = "group_rank(ts_rank(operating_income/equity, 126), subindustry)"


def main() -> int:
    brain = BrainSession()
    brain.authenticate()
    print(f"auth ok | 剩余额度={brain.remaining_simulations}", flush=True)

    v10 = simulate_one(
        brain, f"0.3 * ts_decay_linear({NEWS_PART}, 5) + 0.7 * {FUND}",
        name="V10_final_smooth", base_settings=BASE,
    )
    print_row(v10)

    v6 = simulate_one(brain, f"0.3 * {NEWS_PART} + 0.7 * {FUND}", name="V6_final", base_settings=BASE)
    print_row(v6)

    cands = [r for r in (v10, v6) if r.get("alpha_id")]
    if not cands:
        print("无可用 alpha")
        return 1
    best = max(cands, key=lambda r: (r.get("is") or {}).get("sharpe") or 0)
    print(f"\n候选 {best['alpha_id']}（Sharpe 最高）")

    new_ret = to_returns(brain.pnl_series(best["alpha_id"]))
    print(f"日收益点数: {len(new_ret)}")
    active = brain.alphas(status="ACTIVE")
    print(f"ACTIVE alphas: {len(active)}")

    pairs = []
    for a in active:
        aid = a.get("id")
        if not aid or aid == best["alpha_id"]:
            continue
        corr = aligned_corr(new_ret, to_returns(brain.pnl_series(aid)))
        if corr is None:
            continue
        pairs.append((aid, corr))
        tag = " ❌ HIGH" if abs(corr) >= 0.7 else (" ⚠️" if abs(corr) >= 0.5 else "")
        print(f"  {aid}: corr={corr:+.3f}{tag}")

    pairs.sort(key=lambda x: abs(x[1]), reverse=True)
    high = [p for p in pairs if abs(p[1]) >= 0.7]
    print(f"\n最高相关: {pairs[0] if pairs else 'n/a'}")
    if high:
        print(f"⚠️ {len(high)} 个 ACTIVE alpha 日收益相关 ≥0.7：{high}")
    else:
        print("✅ 无 ≥0.7 高相关（注意：WQ 用信号级相关，仍需信号成分重叠护栏）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
