"""FCF 质量 alpha 优化批处理：baseline + 4 个变体（B2–B5）。

变体定义保持不变；模拟 / 轮询 / 门槛判定统一走 `wq_api`。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, print_row, simulate_one  # noqa: E402

BASE = {
    "region": "USA", "universe": "TOP3000", "delay": 1,
    "decay": 0, "neutralization": "SUBINDUSTRY", "truncation": 0.08,
    "nanHandling": "ON",
}

VARIANTS = {
    "B2_window252": "group_rank(ts_rank((est_cashflow_op-est_capex)/close, 252), subindustry)",
    "B3_decay10": "group_rank(ts_decay_linear(ts_rank((est_cashflow_op-est_capex)/close, 126), 10), subindustry)",
    "B4_mix_oi": (
        "0.5*group_rank(ts_rank((est_cashflow_op-est_capex)/close,126),subindustry)"
        "+0.5*group_rank(ts_rank(operating_income/equity,126),subindustry)"
    ),
    "B5_inv126": (
        "0.5*group_rank(ts_rank((est_cashflow_op-est_capex)/close,126),subindustry)"
        "+0.5*group_rank(ts_rank(inventory_turnover,126),subindustry)"
    ),
}

# 变体 C 表达式内已有 22 天平滑，外部 decay 也用 0；其余同。


def main() -> int:
    brain = BrainSession()
    brain.authenticate()
    print(f"auth ok | 剩余额度={brain.remaining_simulations}", flush=True)

    results = {}
    for name, expr in VARIANTS.items():
        print(f"\n=== 模拟 {name} ===", flush=True)
        row = simulate_one(brain, expr, name=name, base_settings=BASE)
        print_row(row)
        results[name] = {k: v for k, v in row.items() if k != "payload"}

    out = Path(__file__).resolve().parent / "_fcf_opt_results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n完成，结果已保存 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
