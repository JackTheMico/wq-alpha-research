#!/usr/bin/env python3
"""阶数检查器：判一二三阶、拦跨阶污染、控算子复杂度。

为什么需要它（three 个真实坑，都能在烧额度前拦掉）：

1. **跨阶污染**：三阶结果被二阶 factory 重套一层 group，或二阶结果被再次 ts，
   表达式越滚越长，指标却不变——纯浪费额度。
2. **复杂度失控**：一阶堆 5–6 个算子，robust / prod corr 都难看。
   （论坛实测：把条件挪到三阶、平滑挪到二阶后指标才回来）
3. **层次放错**：条件逻辑写进一阶、平滑写进三阶，导致失败原因无法归因。

分阶口径（社区共识，见 SKILL.md §13）：

    零阶  预处理   ts_backfill / winsorize / vec_* / 基础代数
    一阶  时序     ts_rank / ts_delta / ts_mean / ts_zscore / ...
    二阶  截面     group_rank / group_neutralize / group_zscore / group_scale
    三阶  门控     trade_when
    四阶  组合     hump / vector_neut / regression_neut / ts_target_tvr ...

用法（CLI）：
    python stage_check.py "<expr>"
    python stage_check.py "<expr>" --json
    python stage_check.py --file variants.json          # 逐条检查
    python stage_check.py "<expr>" --quiet              # 只输出结论行

也可当库用：from stage_check import analyze, find_pollution
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from static_check import _find_matching_paren, _split_args  # noqa: E402

# ---------------------------------------------------------------------------
# 算子分阶表
# ---------------------------------------------------------------------------

# 零阶：预处理与基础变换。重复出现不视为"层叠"
STAGE0_PREP = {
    "ts_backfill", "group_backfill", "winsorize", "pasteurize", "densify",
    "vec_avg", "vec_sum", "vec_min", "vec_max", "vec_count", "vec_stddev",
    "vec_range",
}
STAGE0_BASIC = {
    "log", "sqrt", "abs", "sign", "inverse", "reverse", "s_log_1p", "log_diff",
    "fraction", "normalize", "scale", "scale_down", "add", "subtract",
    "multiply", "divide", "max", "min", "power", "if_else",
    # 截面代数（全市场，不带分组）：同一阶的归一化，与 group_* 分属不同层
    "rank", "zscore", "quantile", "signed_power",
}
STAGE0 = STAGE0_PREP | STAGE0_BASIC

# 一阶：时序变换
STAGE1 = {
    "ts_rank", "ts_delta", "ts_mean", "ts_zscore", "ts_sum", "ts_product",
    "ts_std_dev", "ts_ir", "ts_arg_min", "ts_arg_max", "ts_min_diff",
    "ts_max_diff", "ts_returns", "ts_scale", "ts_skewness", "ts_kurtosis",
    "ts_quantile", "ts_corr", "ts_covariance", "ts_decay_linear",
    "ts_decay_exp_window", "ts_min", "ts_max", "ts_median", "ts_count_nans",
    "ts_delay", "ts_step", "ts_av_diff", "ts_regression", "ts_moment",
    "ts_entropy", "ts_percentage", "ts_min_max_cps", "ts_min_max_diff",
    "ts_theilsen", "ts_triple_corr", "ts_weighted_delay", "days_from_last_change",
    "last_diff_value",
}

# 二阶：截面分组
STAGE2 = {
    "group_rank", "group_neutralize", "group_zscore", "group_scale",
    "group_normalize", "group_mean", "group_median", "group_sum",
    "group_max", "group_min", "group_std_dev", "group_count",
}

# 三阶：条件交易（门控）
STAGE3 = {"trade_when"}

# 四阶：组合 / 风险调整
STAGE4 = {
    "hump", "hump_decay", "vector_neut", "vector_proj", "regression_neut",
    "ts_target_tvr", "ts_target_tvr_decay", "ts_target_tvr_hump",
    "bucket", "clamp", "keep", "filter",
}

STAGE_NAMES = {0: "零阶/预处理", 1: "一阶/时序", 2: "二阶/截面", 3: "三阶/门控", 4: "四阶/组合"}

# 复杂度权重（借鉴论坛做法：按算子族给权重，总和超阈值即判过拟合风险）
COMPLEXITY_WEIGHT = {
    0: 1.0,   # 预处理/代数：便宜
    1: 1.5,   # 时序：需历史窗口
    2: 1.5,   # 分组：需截面
    3: 2.0,   # 门控：改变交易时点，影响最大
    4: 2.0,   # 组合/风险调整
}
# ts_rank / ts_zscore / ts_ir 等"带估计"的时序算子再加 0.5
EXPENSIVE_TS = {"ts_rank", "ts_zscore", "ts_ir", "ts_regression", "ts_theilsen",
                "ts_entropy", "ts_kurtosis", "ts_skewness", "ts_std_dev"}

DEFAULT_MAX_COMPLEXITY = 8.0
DEFAULT_MAX_SAME_OP = 2

# 分组字段白名单（不计入算子复杂度，也不当作信号层）
GROUP_KEYS = {
    "market", "sector", "industry", "subindustry", "country", "currency",
    "exchange", "split", "adjfactor", "cap", "custom_group",
}

# VECTOR 类字段前缀（需要先 vec_* 聚合）
VECTOR_PREFIXES = ("nws", "oth", "rsk", "brk", "anl", "mdl", "scl", "soc", "sen")

FUNC_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def stage_of(op: str) -> int | None:
    """返回算子所属阶数；未知算子返回 None。"""
    if op in STAGE3:
        return 3
    if op in STAGE2:
        return 2
    if op in STAGE1:
        return 1
    if op in STAGE4:
        return 4
    if op in STAGE0:
        return 0
    return None


def iter_calls(expr: str):
    """遍历表达式中的所有函数调用，产出 (op, args)。"""
    for m in FUNC_RE.finditer(expr or ""):
        op = m.group(1)
        open_idx = m.end() - 1
        close_idx = _find_matching_paren(expr, open_idx)
        if close_idx < 0:
            continue
        yield op, _split_args(expr[open_idx + 1:close_idx])


def collect_ops(expr: str) -> list[tuple[int, str]]:
    """按出现次数收集所有算子（含重复），返回 [(阶数, 算子名)]。"""
    out: list[tuple[int, str]] = []
    for op, _ in iter_calls(expr):
        s = stage_of(op)
        if s is not None:
            out.append((s, op))
    return out


def analyze(expr: str, *, max_complexity: float = DEFAULT_MAX_COMPLEXITY,
            max_same_op: int = DEFAULT_MAX_SAME_OP) -> dict[str, Any]:
    """分析一条表达式的阶结构，返回诊断结果。

    返回字段：
        stage        : 最高阶数（0–4）。0 表示只有预处理/代数，即"裸字段"
        layers       : 各阶出现的算子清单
        complexity   : 算子复杂度总分
        errors       : 硬错误（污染、复杂度超限）
        warnings     : 软提示（层次缺失、向量未聚合）
        verdict      : "OK" / "WARN" / "FAIL"
    """
    expr = (expr or "").strip()
    ops = collect_ops(expr)

    layers: dict[int, list[str]] = {}
    counts: dict[str, int] = {}
    complexity = 0.0
    for stage, op in ops:
        layers.setdefault(stage, []).append(op)
        counts[op] = counts.get(op, 0) + 1
        w = COMPLEXITY_WEIGHT[stage]
        if op in EXPENSIVE_TS:
            w += 0.5
        complexity += w

    errors: list[str] = []
    warnings: list[str] = []

    # ---- 1. 跨阶污染 ----
    errors.extend(find_pollution(expr, layers))

    # ---- 2. 复杂度预算 ----
    if complexity > max_complexity:
        errors.append(
            f"算子复杂度 {complexity:.1f} 超过上限 {max_complexity:.1f}（过拟合风险）。"
            f"按阶拆解：{_fmt_layers(layers)}。请删掉不带来增量的层。"
        )

    # ---- 3. 同算子重复 ----
    for op, n in sorted(counts.items()):
        if n > max_same_op:
            errors.append(
                f"算子 {op} 出现 {n} 次（上限 {max_same_op}），疑似无意义嵌套（如 zscore(zscore(x))）。"
            )

    # ---- 4. 层次分工提示 ----
    stage_max = max(layers) if layers else 0
    if stage_max == 0 and expr:
        warnings.append("裸字段/仅预处理（零阶）。建议先看它有没有 PnL 形状，再决定是否进一阶。")
    if 3 in layers and 2 not in layers:
        warnings.append("有三阶门控但缺二阶截面层。门控前通常应先做截面分组，否则暴露未清理。")
    if 2 in layers and 1 not in layers and 0 not in layers:
        warnings.append("只有二阶分组、没有一阶时序。确认这是有意的（forum 案例：跳过一阶直接二阶是可行的，但要有理由）。")
    if 4 in layers and 3 not in layers:
        warnings.append("有四阶组合/风险调整但无三阶门控。四阶建议只用于顶级候选。")

    # ---- 5. VECTOR 字段是否已聚合 ----
    warnings.extend(check_vector_aggregation(expr))

    verdict = "FAIL" if errors else ("WARN" if warnings else "OK")
    return {
        "expr": expr,
        "stage": stage_max,
        "stage_name": STAGE_NAMES.get(stage_max, "未知"),
        "layers": {STAGE_NAMES[k]: v for k, v in sorted(layers.items())},
        "complexity": round(complexity, 1),
        "op_counts": counts,
        "errors": errors,
        "warnings": warnings,
        "verdict": verdict,
    }


def find_pollution(expr: str, layers: dict[int, list[str]] | None = None) -> list[str]:
    """检测跨阶污染：后一阶的产出被前一阶的算子再次包裹。

    两类典型污染：
      1. trade_when 出现在 ts_* / group_* 的参数里 → 三阶结果被二阶/一阶重套
      2. 表达式末尾已有 trade_when，但外层还在套 ts_/group_ → 同上
    """
    layers = layers if layers is not None else {}
    errs: list[str] = []
    if not expr:
        return errs

    for op, args in iter_calls(expr):
        s = stage_of(op)
        if s is None:
            continue
        for arg in args:
            inner = [stage_of(f) for f, _ in iter_calls(arg)]
            inner = [i for i in inner if i is not None]
            if not inner:
                continue
            # 一阶/二阶算子包裹三阶门控 = 污染
            if s in (1, 2) and 3 in inner:
                errs.append(
                    f"跨阶污染：{op}（{STAGE_NAMES[s]}）包裹了 trade_when（三阶）。"
                    f"三阶应是最后一步——先去掉外层 {op}，否则只是在给门控结果加噪声。"
                )
            # 二阶算子包裹四阶组合 = 顺序可疑
            if s == 2 and 4 in inner:
                errs.append(
                    f"层次倒置：{op}（二阶截面）包裹了四阶组合算子。"
                    f"组合/风险调整应在截面之后，检查是否套反了。"
                )
    # 去重（同一污染可能被多层检出）
    seen, uniq = set(), []
    for e in errs:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq


def check_vector_aggregation(expr: str) -> list[str]:
    """检测 VECTOR 类字段是否未经 vec_* 聚合就直接进入 ts_* 算子。"""
    warns: list[str] = []
    vec_ok: set[str] = set()
    for op, args in iter_calls(expr):
        if op.startswith("vec_") and args:
            vec_ok.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", " ".join(args)))

    for op, args in iter_calls(expr):
        if stage_of(op) != 1:
            continue
        for arg in args:
            for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", arg):
                low = name.lower()
                if name in vec_ok or name in GROUP_KEYS:
                    continue
                if any(low.startswith(p) and "_" in low for p in VECTOR_PREFIXES):
                    msg = (
                        f"字段 {name} 疑似 VECTOR 类，被 {op} 直接包裹而未先 vec_* 聚合。"
                        f"VECTOR 字段须先聚合为标量，否则报 'does not support event inputs'。"
                    )
                    if msg not in warns:
                        warns.append(msg)
    return warns


def _fmt_layers(layers: dict[int, list[str]]) -> str:
    if not layers:
        return "无"
    return " | ".join(f"{STAGE_NAMES[k]}:{len(v)}个" for k, v in sorted(layers.items()))


# 供其他模块导入的别名（语义更明确的入口名）
analyze_stage = analyze
render_stage = None  # 在 render 定义后赋值，见文件末尾


def stage_gate(expr: str, *, max_complexity: float = DEFAULT_MAX_COMPLEXITY,
               max_same_op: int = DEFAULT_MAX_SAME_OP) -> tuple[bool, list[str]]:
    """仿真前置闸门：返回 (是否放行, 错误列表)。

    只把 errors 当阻断项；warnings 交给调用方决定是否打印。
    与 static_check.run_static_check 同签名风格，便于串接。
    """
    r = analyze(expr, max_complexity=max_complexity, max_same_op=max_same_op)
    return (r["verdict"] != "FAIL"), list(r["errors"])


def render(result: dict[str, Any]) -> str:
    icon = {"OK": "✅", "WARN": "⚠️", "FAIL": "❌"}[result["verdict"]]
    lines = [
        f"{icon} 阶数={result['stage']}（{result['stage_name']}）  "
        f"复杂度={result['complexity']}  {result['verdict']}",
    ]
    if result["layers"]:
        for name, ops in result["layers"].items():
            uniq = sorted(set(ops))
            lines.append(f"   {name}: {' '.join(uniq)}")
    for e in result["errors"]:
        lines.append(f"   ❌ {e}")
    for w in result["warnings"]:
        lines.append(f"   ⚠️ {w}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="一二三阶结构检查（仿真前跑，零额度）")
    ap.add_argument("expr", nargs="?", help="待检查的表达式")
    ap.add_argument("--file", help="variants.json，逐条检查")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--quiet", action="store_true", help="只输出结论行")
    ap.add_argument("--max-complexity", type=float, default=DEFAULT_MAX_COMPLEXITY)
    ap.add_argument("--max-same-op", type=int, default=DEFAULT_MAX_SAME_OP)
    a = ap.parse_args(argv)

    exprs: list[str] = []
    if a.file:
        raw = json.loads(Path(a.file).read_text(encoding="utf-8"))
        for item in raw if isinstance(raw, list) else raw.get("variants", []):
            if isinstance(item, str):
                exprs.append(item)
            elif isinstance(item, dict):
                exprs.append(item.get("regular") or item.get("expr") or "")
    elif a.expr:
        exprs = [a.expr]
    else:
        ap.error("需要 expr 或 --file")

    results = [
        analyze(e, max_complexity=a.max_complexity, max_same_op=a.max_same_op)
        for e in exprs
    ]

    if a.json:
        print(json.dumps(results if len(results) > 1 else results[0],
                         ensure_ascii=False, indent=2))
    elif a.quiet:
        for r in results:
            print(f"{r['verdict']}\t阶{r['stage']}\t复杂度{r['complexity']}\t{r['expr'][:70]}")
    else:
        for r in results:
            print(render(r))
            print()

    return 0 if all(r["verdict"] != "FAIL" for r in results) else 1


# 供其他模块导入的别名（render 定义之后赋值，避免 NameError）
render_stage = render


if __name__ == "__main__":
    sys.exit(main())
