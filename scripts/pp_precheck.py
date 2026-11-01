#!/usr/bin/env python3
"""Power Pool 资格预检（零仿真消耗）。

对给定 alpha_id 或表达式，按官方四条硬约束 + 实测的 tag/description 机制打分：
  1. Sharpe >= 1.0
  2. 算子总数 <= 8（ts_backfill / group_backfill 不计）
  3. 唯一数据字段 <= 3（分组字段不计）
  4. Power Pool Correlation < 0.5（或 Sharpe 比最相关 alpha 高 10%）
  附加实测项：是否为 FULL 模式（QUICK 不能提交）、是否带 POWER_POOL tag、
             checks 里 POWER_POOL_DESCRIPTION_FORMAT 是否仍为 WARNING。

用法：
    python scripts/pp_precheck.py <alpha_id> [alpha_id ...]
    python scripts/pp_precheck.py --expr "rank(ts_decay_linear((a-b)/c, 5))"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FIELD_JSON = Path(__file__).resolve().parent.parent / "references" / "fields_usa_top3000_delay1.json"

GROUP_FIELDS = {
    "country", "industry", "subindustry", "currency", "market",
    "sector", "exchange", "split", "adjfactor",
}
FREE_OPS = {"ts_backfill", "group_backfill"}
ARITH = set("+-*/")

_FIELD_CACHE: set[str] | None = None


def field_universe() -> set[str]:
    global _FIELD_CACHE
    if _FIELD_CACHE is None:
        data = json.loads(FIELD_JSON.read_text(encoding="utf-8"))
        _FIELD_CACHE = {f["id"] for f in data}
    return _FIELD_CACHE


def strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    code = re.sub(r"//[^\n]*", " ", code)
    code = re.sub(r"#[^\n]*", " ", code)
    return code


def analyze(expr: str) -> dict:
    """统计字段数、算子数、变量赋值。"""
    code = strip_comments(expr)
    # 去掉字符串字面量（range="0.1,1,0.1" 之类）
    code = re.sub(r'"[^"]*"', '""', code)

    # 赋值左侧的局部变量名不算字段
    locals_ = set(re.findall(r"(?:^|[;\n])\s*([A-Za-z_]\w*)\s*=", code))

    idents = re.findall(r"[A-Za-z_]\w*", code)
    univ = field_universe()

    fields, ops, unknown = set(), set(), set()
    for name in idents:
        if name in locals_:
            continue
        if name in univ:
            fields.add(name)
        else:
            unknown.add(name)

    # 函数调用形式 -> 算子；裸标识符若不在字段集，也按算子计（如 true/false 常量忽略）
    consts = {"true", "false", "nan", "inf", "null"}
    for name in list(unknown):
        if name.lower() in consts:
            unknown.discard(name)
    ops = {n for n in unknown}
    counted_ops = {o for o in ops if o not in FREE_OPS}

    # 算术运算符
    arith_count = sum(1 for ch in code if ch in ARITH)
    # '-5' 这种一元负号会多算，粗略修正：负号紧跟 ( 或 , 或 行首 的不算
    unary = len(re.findall(r"(?:^|[(,;]\s*)-", code))
    arith_count = max(0, arith_count - unary)

    data_fields = {f for f in fields if f not in GROUP_FIELDS}
    group_used = {f for f in fields if f in GROUP_FIELDS}

    total_ops = len(counted_ops) + arith_count
    return {
        "data_fields": sorted(data_fields),
        "group_fields": sorted(group_used),
        "operators": sorted(counted_ops),
        "arith_ops": arith_count,
        "total_ops": total_ops,
        "free_ops": sorted(ops & FREE_OPS),
        "unknown_idents": sorted(unknown - ops),
    }


def report_expr(expr: str) -> bool:
    info = analyze(expr)
    print("  data fields   :", info["data_fields"], f"({len(info['data_fields'])})")
    print("  group fields  :", info["group_fields"], "(不计入)")
    print("  operators     :", info["operators"])
    print("  arithmetic    :", info["arith_ops"])
    print("  total ops     :", info["total_ops"])
    if info["free_ops"]:
        print("  free ops      :", info["free_ops"], "(官方不计入)")
    if info["unknown_idents"]:
        print("  unknown       :", info["unknown_idents"])

    ok_fields = len(info["data_fields"]) <= 3
    ok_ops = info["total_ops"] <= 8
    print(f"  -> fields<=3 : {'PASS' if ok_fields else 'FAIL'}"
          f"   ops<=8 : {'PASS' if ok_ops else 'FAIL'}")

    # 结构提示：(A-B)/mean(A,B) 形状
    # 分子要有 A-B 差分；分母要同源——三种合法写法都要认：
    #   1) 分母是名字里含 mean/avg 的字段（如 implied_volatility_mean_180）
    #   2) 分母是 (A+B)/2 的显式写法
    #   3) 分母是 mean(...) / vec_avg(...) 算子
    has_diff = bool(re.search(r"\(\s*[\w.]+\s*-\s*[\w.]+\s*\)", expr))
    same_src_denom = (
        bool(re.search(r"/\s*\(?\s*\w*(?:mean|avg)\w*", expr, re.I))
        or bool(re.search(r"\(\s*[\w.]+\s*\+\s*[\w.]+\s*\)\s*/\s*2", expr))
    )
    shape = has_diff and same_src_denom
    if shape:
        print("  -> (A-B)/mean 形状: 是（≤3 字段下唯一能稳定破 1.0 的结构）")
    elif has_diff:
        print("  -> (A-B)/mean 形状: 半 —— 有差分但分母不同源，Sharpe 会打折")
    else:
        print("  -> (A-B)/mean 形状: 否（单比率/单字段，PP 的 Sharpe 通常打不到 1.0）")
    return ok_fields and ok_ops


def report_alpha(brain, aid: str) -> None:
    a = brain.request("GET", f"/alphas/{aid}").json()
    is_ = a.get("is") or {}
    st = a.get("settings") or {}
    print(f"\n{'=' * 70}\n{aid}  status={a.get('status')}  tags={a.get('tags')}")
    print(f"  mode={st.get('simulationMode')} region={st.get('region')} "
          f"universe={st.get('universe')} delay={st.get('delay')} "
          f"neutral={st.get('neutralization')} decay={st.get('decay')}")
    print(f"  Sharpe={is_.get('sharpe')} Fitness={is_.get('fitness')} "
          f"TO={is_.get('turnover')} returns={is_.get('returns')}")

    checks = {c.get("name"): c for c in (is_.get("checks") or [])}
    print(f"  SELF_CORR={checks.get('SELF_CORRELATION', {}).get('value')} "
          f"PROD_CORR={checks.get('PROD_CORRELATION', {}).get('value')} "
          f"PP_CORR={checks.get('POWER_POOL_CORRELATION', {}).get('value')}")

    tags = a.get("tags") or []
    has_pp_tag = "POWER_POOL" in tags
    print(f"\n  [PP 资格]")
    s = is_.get("sharpe")
    print(f"    {'Sharpe>=1.0':<18}: {'PASS' if isinstance(s, (int, float)) and s >= 1.0 else 'FAIL'} ({s})")
    if st.get("simulationMode") != "FULL":
        print(f"    {'FULL mode':<18}: FAIL —— QUICK 模式无法提交，需 FULL 重跑")
    else:
        print(f"    {'FULL mode':<18}: PASS")
    print(f"    {'PP tag':<18}: {'有' if has_pp_tag else '无 —— 提交会被按常规 1.58 门槛拒'}")

    # PP 只放宽 LOW_SHARPE，以下三项仍按常规阈值卡（2026-10-31 实测）
    for nm, label in (
        ("LOW_FITNESS", "Fitness>=1.0"),
        ("CONCENTRATED_WEIGHT", "WeightConc<=0.1"),
        ("LOW_SUB_UNIVERSE_SHARPE", "SubUniv Sharpe"),
        ("HIGH_TURNOVER", "Turnover<=0.7"),
        ("LOW_2Y_SHARPE", "2Y Sharpe"),
    ):
        c = checks.get(nm)
        if not c:
            continue
        res = c.get("result")
        flag = "PASS" if res in ("PASS", "WARNING", "PENDING") else "FAIL"
        print(f"    {label:<18}: {flag:<5} ({res} value={c.get('value')} limit={c.get('limit')})")

    ppdesc = checks.get("POWER_POOL_DESCRIPTION_FORMAT")
    if ppdesc is None:
        print(f"    {'PP description':<18}: 未检查（checks 里无该项；通常因未带 tag 或未提交过）")
    else:
        print(f"    {'PP description':<18}: {ppdesc.get('result')} —— "
              f"{'需在网页端补 Idea/数据理由/算子理由' if ppdesc.get('result') != 'PASS' else '合规'}")

    expr = (a.get("regular") or {}).get("code") or ""
    print("\n  [表达式]")
    report_expr(expr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Power Pool 资格预检")
    ap.add_argument("alpha_ids", nargs="*")
    ap.add_argument("--expr", help="直接分析表达式，不查 API")
    args = ap.parse_args()

    if args.expr:
        report_expr(args.expr)
        return 0
    if not args.alpha_ids:
        ap.print_help()
        return 1

    from wq_api import BrainSession

    brain = BrainSession()
    brain.authenticate()
    for aid in args.alpha_ids:
        report_alpha(brain, aid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
