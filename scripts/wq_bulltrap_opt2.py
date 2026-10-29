#!/usr/bin/env python3
"""WQ Bull Trap 优化 第二轮 — 精细调优（V5–V9）。

V8 走设置层 decay=15，V9 换 SUBINDUSTRY 中性化；其余默认 INDUSTRY / decay=0。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, print_row, simulate_one  # noqa: E402

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

# 名称 -> (表达式, 设置覆盖)
VARIANTS = {
    # V5: V3 基础上新闻部分轻度平滑(5日)
    "V5_light_smooth": (f"0.5 * ts_decay_linear({NEWS_PART}, 5) + 0.5 * {FUND}", {}),
    # V6: 基本面权重加大到 0.7, 新闻 0.3（进一步压换手）
    "V6_fund70": (f"0.3 * {NEWS_PART} + 0.7 * {FUND}", {}),
    # V7: 回归窗口 5->10（中等平滑），保持 50/50
    "V7_win10": (
        "slope = ts_regression(ts_backfill(news_pct_1min,60), ts_step(1), 10, rettype=2);\n"
        f"0.5 * winsorize(-ts_backfill(news_max_up_ret,60) * abs(slope),std = 4) + 0.5 * {FUND}",
        {},
    ),
    # V8: V0 纯表达式 + 设置层 decay=15
    "V8_setting_decay": (
        "slope = ts_regression(ts_backfill(news_pct_1min,60), ts_step(1), 5, rettype=2);\n"
        "winsorize(-ts_backfill(news_max_up_ret,60) * abs(slope),std = 4)",
        {"decay": 15},
    ),
    # V9: V5 + SUBINDUSTRY 中性化（skill: SUBINDUSTRY 通过率最高）
    "V9_subind": (f"0.5 * ts_decay_linear({NEWS_PART}, 5) + 0.5 * {FUND}", {"neutralization": "SUBINDUSTRY"}),
}


def main() -> int:
    brain = BrainSession()
    brain.authenticate()
    print(f"auth ok | 剩余额度={brain.remaining_simulations}", flush=True)

    for name, (expr, overrides) in VARIANTS.items():
        print_row(simulate_one(brain, expr, name=name, base_settings=BASE, **overrides))
    return 0


if __name__ == "__main__":
    sys.exit(main())
