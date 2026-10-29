"""长期投资趋势 alpha 优化批处理：变体 P / Q / R。

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

SALES_TREND = (
    "group_rank(ts_rank(ts_delta(actual_sales_value_quarterly,126)"
    "/ts_delay(actual_sales_value_quarterly,126),{win}),subindustry)"
)

VARIANTS = {
    "P_sales_rank126": SALES_TREND.format(win=126),
    "Q_sales70_oi30": (
        "0.7*" + SALES_TREND.format(win=63)
        + "+0.3*group_rank(ts_rank(operating_income/equity,126),subindustry)"
    ),
    "R_sales_decay5": (
        "group_rank(ts_decay_linear(ts_rank(ts_delta(actual_sales_value_quarterly,126)"
        "/ts_delay(actual_sales_value_quarterly,126),63),5),subindustry)"
    ),
}


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

    out = Path(__file__).resolve().parent / "_ltinv_opt_results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n完成，结果已保存 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
