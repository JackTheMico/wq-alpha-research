#!/usr/bin/env python3
"""WQ Bull Trap alpha 优化 — 第一轮变体（V0–V4）。

历史实验脚本，保留变体定义以便复现；模拟/轮询/门槛判定统一走 `wq_api`，
不再各自复制一份（旧版固定 sleep(8)、只认 COMPLETE/ERROR/FAILED）。

注意 FastExpr 语义：`slope = ...; <最终表达式>` 中赋值必须是独立语句，
不能把 `slope = ...;` 塞进算子参数里，因此下面把「声明」与「信号体」分开拼。
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

FUND = "group_rank(ts_rank(operating_income/equity, 126), subindustry)"


def decl(win: int, reg: int) -> str:
    return f"slope = ts_regression(ts_backfill(news_pct_1min,{win}), ts_step(1), {reg}, rettype=2);\n"


def body(win: int) -> str:
    return (
        f"winsorize(-ts_backfill(news_max_up_ret,{win}) * abs(slope),std = 4)"
    )


VARIANTS = {
    # V0: 原始 Bull Trap
    "V0_base": decl(60, 5) + body(60),
    # V1: 拉长回归窗口 + backfill（斜率更平滑 -> 低换手）
    "V1_long_win": decl(120, 20) + body(120),
    # V2: 加时序平滑衰减
    "V2_decay_lin": decl(60, 5) + f"ts_decay_linear({body(60)}, 10)",
    # V3: 50/50 混合基本面锚定
    "V3_mix_fund": decl(60, 5) + f"0.5 * {body(60)} + 0.5 * {FUND}",
    # V4: 长窗口 + 平滑 + 基本面混合（组合拳）
    "V4_combo": decl(120, 20) + f"0.5 * ts_decay_linear({body(120)}, 10) + 0.5 * {FUND}",
}


def main() -> int:
    brain = BrainSession()
    brain.authenticate()
    print(f"auth ok | 剩余额度={brain.remaining_simulations}", flush=True)

    for name, expr in VARIANTS.items():
        print_row(simulate_one(brain, expr, name=name, base_settings=BASE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
