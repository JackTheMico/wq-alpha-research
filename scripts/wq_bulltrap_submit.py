#!/usr/bin/env python3
"""WQ Bull Trap 优化 — V6 / V10 提交脚本。

模拟 + 门槛判定 + 提交确认全部走 `wq_api`；提交后必须二次确认 ACTIVE。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, print_row, simulate_one, submit_verified  # noqa: E402

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

VARIANTS = {
    "V6_final": f"0.3 * {NEWS_PART} + 0.7 * {FUND}",
    "V10_final_smooth": f"0.3 * ts_decay_linear({NEWS_PART}, 5) + 0.7 * {FUND}",
}


def main() -> int:
    brain = BrainSession()
    brain.authenticate()
    print(f"auth ok | 剩余额度={brain.remaining_simulations}", flush=True)

    rows = []
    for name, expr in VARIANTS.items():
        row = simulate_one(brain, expr, name=name, base_settings=BASE)
        print_row(row)
        rows.append(row)

    winners = [r for r in rows if r.get("gate_ok") and r.get("alpha_id")]
    if not winners:
        print("\n没有通过门槛的候选，未提交。")
        return 1

    # 同一信号簇的候选只提交 Sharpe 最高的那个（避免自撞 SELF_CORRELATION）
    best = max(winners, key=lambda r: (r.get("is") or {}).get("sharpe") or 0)
    print(f"\n提交 {best['name']} ({best['alpha_id']})")
    outcome = submit_verified(brain, best["alpha_id"])
    print("提交结果:", outcome)
    return 0 if outcome == "ACTIVE" else 1


if __name__ == "__main__":
    sys.exit(main())
