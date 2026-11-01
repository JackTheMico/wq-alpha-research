"""仿真前静态检查：字段拥挤度 + ACTIVE 池 + field-rationale。

在 simulate_batch.py 仿真前运行，拦截高 alphaCount 字段和 ACTIVE 池已用字段，
避免浪费仿真额度。
"""
from __future__ import annotations

import re
from typing import Optional

# 信号算子白名单：出现在这些算子直接参数中的字段视为信号字段
SIGNAL_OPERATORS = {
    "rank", "group_rank", "ts_rank", "ts_zscore", "ts_delta", "ts_returns",
    "ts_mean", "ts_std_dev", "ts_corr", "ts_arg_min", "ts_arg_max",
    "ts_backfill", "ts_decay_linear", "ts_decay_exp_window", "ts_sum",
    "ts_product", "ts_min", "ts_max", "ts_avg", "abs", "log", "sign",
    "scale", "signed_power", "winsorize", "pasteurize",
}

# 分组算子：第二个参数（分组键）不是信号
GROUP_OPERATORS = {"group_rank", "group_neutralize", "group_zscore", "group_scale"}

# 基础价量白名单：天然高 alphaCount，不检查
BASE_PRICE_FIELDS = {
    "close", "open", "high", "low", "volume", "vwap", "returns",
    "adj_close", "adj_volume",
}

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
RATIONALE_MIN_LEN = 10


def _tokenize(expr: str) -> list[str]:
    """提取表达式中的所有标识符。"""
    return TOKEN_RE.findall(expr or "")


def _find_matching_paren(expr: str, open_idx: int) -> int:
    """从 open_idx（'(' 的位置）找到匹配的 ')' 的索引。"""
    depth = 0
    for i in range(open_idx, len(expr)):
        if expr[i] == "(":
            depth += 1
        elif expr[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_args(arg_str: str) -> list[str]:
    """按顶层逗号分割参数字符串（忽略嵌套括号内的逗号）。"""
    args: list[str] = []
    depth = 0
    current = []
    for ch in arg_str:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append("".join(current).strip())
    return args


def extract_signal_fields(expr: str) -> set[str]:
    """从表达式中提取信号字段（4 条规则）。

    规则：
    1. 信号算子白名单内的字段视为信号字段
    2. 除法右侧字段视为分母，不检查
    3. 分组算子的分组键参数不检查
    4. 基础价量白名单不检查
    """
    if not expr:
        return set()

    signal_fields: set[str] = set()
    denom_fields: set[str] = set()
    group_key_fields: set[str] = set()

    # 遍历所有函数调用：name(args)
    func_pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    for m in func_pattern.finditer(expr):
        op = m.group(1)
        open_idx = m.end() - 1  # '(' 的位置
        close_idx = _find_matching_paren(expr, open_idx)
        if close_idx < 0:
            continue
        args_str = expr[open_idx + 1 : close_idx]
        args = _split_args(args_str)

        is_group_op = op in GROUP_OPERATORS or op in ("neut", "vector_neut")

        for i, arg in enumerate(args):
            # 分组算子的第二个参数是分组键，跳过
            if is_group_op and i >= 1:
                group_key_fields.update(_tokenize(arg))
                continue

            # 检查该参数是否以除法形式出现：a/b
            # 如果 arg 是简单的 a/b，a 是信号，b 是分母
            div_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*/\s*(.+)$", arg)
            if div_match:
                numerator = div_match.group(1)
                denominator = div_match.group(2)
                denom_fields.update(_tokenize(denominator))
                # 分子如果是信号算子的直接参数，视为信号
                if op in SIGNAL_OPERATORS and numerator not in BASE_PRICE_FIELDS:
                    signal_fields.add(numerator)
                continue

            # 参数是单个标识符且在信号算子内
            if op in SIGNAL_OPERATORS:
                # 如果参数本身就是单个字段
                id_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)$", arg.strip())
                if id_match:
                    field = id_match.group(1)
                    if field not in BASE_PRICE_FIELDS:
                        signal_fields.add(field)
                else:
                    # 参数是嵌套表达式，递归提取
                    signal_fields.update(extract_signal_fields(arg))

    # 移除分母和分组键
    signal_fields -= denom_fields
    signal_fields -= group_key_fields
    signal_fields -= BASE_PRICE_FIELDS

    return signal_fields


def validate_field_rationale(
    signal_fields: set[str],
    field_rationale: dict[str, str],
) -> list[str]:
    """验证 field-rationale：每个信号字段必须有 ≥10 字解释。"""
    errors = []
    for field in sorted(signal_fields):
        rationale = field_rationale.get(field, "")
        if not rationale or len(rationale.strip()) < RATIONALE_MIN_LEN:
            errors.append(
                f"字段 {field} 缺少经济学解释（需 ≥{RATIONALE_MIN_LEN} 字）。"
                f"请在 --field-rationale 中提供。"
            )
    return errors


def check_crowding(
    signal_fields: set[str],
    field_lookup: dict[str, dict],
    active_fields: set[str],
    *,
    allow_crowded: bool = False,
    allow_unknown: bool = False,
    alpha_count_threshold: int = 500,
) -> list[str]:
    """检查信号字段的拥挤度和 ACTIVE 池使用情况。"""
    errors = []
    for field in sorted(signal_fields):
        meta = field_lookup.get(field)
        if meta is None:
            if not allow_unknown:
                errors.append(
                    f"字段 {field} 不在本地快照中，无法验证拥挤度。"
                    f"请确认字段名拼写或加 --allow-unknown-field。"
                )
            continue

        alpha_count = meta.get("alphaCount", 0) or 0
        if alpha_count > alpha_count_threshold and not allow_crowded:
            errors.append(
                f"字段 {field} 的 alphaCount={alpha_count} 超过阈值 {alpha_count_threshold}，"
                f"撞 PROD_CORRELATION 风险高。"
                f"请运行 recommend_fields.py 选择低拥挤字段，或加 --allow-crowded 并说明理由。"
            )

        if field in active_fields:
            errors.append(
                f"字段 {field} 已在你的 ACTIVE 池中使用，撞 SELF_CORRELATION 风险高。"
                f"请选择其他字段。"
            )
    return errors


def run_static_check(
    expr: str,
    field_lookup: dict[str, dict],
    active_fields: set[str],
    field_rationale: Optional[dict[str, str]] = None,
    *,
    allow_crowded: bool = False,
    allow_unknown: bool = False,
) -> list[str]:
    """执行完整静态检查，返回错误列表（空列表表示通过）。"""
    errors: list[str] = []

    signal_fields = extract_signal_fields(expr)
    if not signal_fields:
        return errors  # 没有信号字段，跳过检查

    # 1. field-rationale 校验（有信号字段时必须提供）
    if field_rationale is None:
        errors.append(
            "缺少 --field-rationale 参数。每个信号字段必须提供 ≥10 字的经济学解释。"
        )
    else:
        errors.extend(validate_field_rationale(signal_fields, field_rationale))

    # 2. 拥挤度 + ACTIVE 池检查
    errors.extend(
        check_crowding(
            signal_fields, field_lookup, active_fields,
            allow_crowded=allow_crowded, allow_unknown=allow_unknown,
        )
    )

    return errors
