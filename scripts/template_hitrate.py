#!/usr/bin/env python3
"""零仿真成本反查：哪些模板/信号簇最容易产出「可提交」的 alpha。

用法:
    python template_hitrate.py                 # 按信号簇 + 腿数统计过线率
    python template_hitrate.py --stock         # 只看已过顾问门槛但未提交的存货
    python template_hitrate.py --dup           # 找出重复仿真（同表达式不同 decay/settings）

口径:
    过门槛 = Sharpe >= 1.58 且 Fitness >= 1.0 且 1% <= Turnover <= 70%（顾问 USA D1）
    不含 SELF_CORRELATION / PROD_CORRELATION —— 这两项只在提交后被平台计算，
    未提交 alpha 恒为 PENDING，历史库无法预知，需另跑 §7.2 护栏 2。

只依赖标准库 + 本地 alpha_db.json，不联网、不消耗仿真额度。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

DB_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "alpha_db.json",
    Path.home() / ".workbuddy/skills/wq-alpha-research/alpha_db.json",
]

SHARPE_GATE = 1.58
FITNESS_GATE = 1.0
TO_LO, TO_HI = 0.01, 0.70


def load_db() -> dict:
    for p in DB_CANDIDATES:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise SystemExit(f"找不到 alpha_db.json，检查过: {[str(p) for p in DB_CANDIDATES]}")


def norm(e: str) -> str:
    return (e or "").replace(" ", "").replace("\n", "").replace("\r", "")


def clusters(expr: str) -> set[str]:
    """把表达式映射到信号簇。多腿表达式会命中多个簇（可重复计数）。"""
    e = norm(expr)
    tags: set[str] = set()
    if "implied_volatility" in e or "pcr_oi" in e:
        tags.add("期权IV")
    if "operating_income/equity" in e or "operating_income/liabilities" in e:
        tags.add("OI质量")
    if "cashflow_op" in e or "free_cash_flow" in e or "enterprise_value/cashflow" in e:
        tags.add("现金流EV")
    if "est_eps" in e:
        tags.add("分析师EPS")
    if "news" in e:
        tags.add("新闻")
    if "mdl77" in e or "mdl175" in e:
        tags.add("model字段")
    if "close/open" in e or "-(close-open)" in e or "-ts_delta(close" in e:
        tags.add("价量反转")
    if "bucket(rank(cap)" in e:
        tags.add("cap分桶")
    return tags or {"其他"}


def passes(a: dict) -> bool | None:
    s, f, to = a.get("sharpe"), a.get("fitness"), a.get("turnover")
    if s is None or f is None or to is None:
        return None
    return s >= SHARPE_GATE and f >= FITNESS_GATE and TO_LO <= to <= TO_HI


def n_legs(expr: str) -> int:
    """顶层加权腿数：数表达式里的 '+'（排除 ++ / 科学计数法）。粗略但够用。"""
    return len(re.findall(r"(?<![\d+eE])\+(?!\+)", norm(expr)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", action="store_true", help="列出已过门槛但未 ACTIVE 的存货")
    ap.add_argument("--dup", action="store_true", help="列出重复仿真（同表达式）")
    args = ap.parse_args()

    alphas = load_db()["alphas"]
    print(f"样本 {len(alphas)} 条 | 状态分布 {dict(Counter(a.get('status') for a in alphas.values()))}")

    if args.stock:
        print("\n=== 已过顾问门槛但未 ACTIVE（零成本可提交存货）===")
        rows = [(k, a) for k, a in alphas.items() if passes(a) and a.get("status") != "ACTIVE"]
        rows.sort(key=lambda kv: -(kv[1].get("sharpe") or 0))
        for k, a in rows:
            print(f"  {k} [{a.get('status')}] S={a.get('sharpe')} F={a.get('fitness')} "
                  f"TO={a.get('turnover'):.3f} | {norm(a.get('expression'))[:130]}")
        print(f"\n  共 {len(rows)} 条。提交前跑 §7.2 护栏 2（信号成分重叠），同簇只留最高 Sharpe 一条。")
        return

    if args.dup:
        print("\n=== 重复仿真（同一表达式被跑了多次）===")
        by_expr = defaultdict(list)
        for k, a in alphas.items():
            by_expr[norm(a.get("expression"))].append((k, a))
        found = 0
        for e, items in by_expr.items():
            if len(items) > 1:
                found += 1
                ids = ", ".join(f"{k}[{a.get('status')}]" for k, a in items)
                print(f"  {ids}\n    {e[:130]}")
        print(f"\n  共 {found} 组重复——批量脚本请强制启用 SimulationCache 去重。")
        return

    stat = defaultdict(Counter)
    for a in alphas.values():
        for t in clusters(a.get("expression")):
            stat[t]["n"] += 1
            if passes(a):
                stat[t]["gate"] += 1
            if a.get("status") == "ACTIVE":
                stat[t]["ACTIVE"] += 1

    print("\n=== 按信号簇（多腿表达式会重复计数）===")
    print(f"{'信号簇':<12}{'尝试':>6}{'过门槛':>8}{'过门槛率':>10}{'ACTIVE':>8}")
    rows = sorted(stat.items(), key=lambda kv: (-(kv[1]["gate"] / kv[1]["n"]), -kv[1]["n"]))
    for t, c in rows:
        print(f"{t:<12}{c['n']:>6}{c['gate']:>8}{c['gate'] / c['n']:>9.1%}{c['ACTIVE']:>8}")

    print("\n=== 按腿数 ===")
    g = defaultdict(Counter)
    for a in alphas.values():
        g["双腿+" if n_legs(a.get("expression")) >= 1 else "单腿"][a.get("status")] += 1
    for l in ("单腿", "双腿+"):
        c = g[l]
        n = sum(c.values())
        if n:
            print(f"  {l}: 尝试 {n}, 过门槛 {c.get('ACTIVE', 0)} 个 ACTIVE, 命中率 {c.get('ACTIVE', 0) / n:.1%}")


if __name__ == "__main__":
    main()
