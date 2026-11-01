#!/usr/bin/env python3
"""低拥挤字段推荐引擎。

从字段快照中筛选 alphaCount 低、覆盖度高、有经济学意义的字段，
按经济学维度分组输出，帮助 AI 从源头降低 PROD_CORRELATION。

用法：
    python scripts/recommend_fields.py --region usa --universe top3000
    python scripts/recommend_fields.py --region glb --universe top3000 --refresh
    python scripts/recommend_fields.py --region chn --universe top2000 --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from field_snapshot import (  # noqa: E402
    check_snapshot_age,
    get_snapshot_path,
    load_snapshot,
    refresh_snapshot,
    snapshot_exists,
)

# === 配置常量 ===
ALPHA_COUNT_PREFERRED = 100      # 🟢 首选
ALPHA_COUNT_FALLBACK = 500       # 🟡 回退上限
COVERAGE_MIN = 0.7
USERCOUNT_RARE = 100             # 极冷门：userCount < 此值
ALPHACOUNT_RARE = 5              # 极冷门：alphaCount < 此值

# 衍生信号字段黑名单（id 或 description 中含任一关键词即排除）
BLACKLIST_KEYWORDS = {
    "rank", "percentile", "score", "signal", "factor", "zscore",
    "normalized", "standardized", "decay", "neutralized", "adjusted",
}

# 饱和数据集（SKILL §4.1.3 已标记）
SATURATED_DATASETS = {"fundamental6", "analyst4", "pv1"}

# 11 个经济学维度的关键词映射。
# 顺序很重要：更具体的维度在前，避免宽泛关键词（如 price/earn）误匹配。
DIMENSION_KEYWORDS: dict[str, list[str]] = {
    "event": ["surprise", "dividend", "split", "merger", "acquisition", "insider", "earnings_ann", "corporate_action"],
    "momentum": ["momentum", "return_", "price_", "trend", "reversal", "mean_revert"],
    "volatility": ["volatil", "iv_", "implied_vol", "realized_vol", "skew", "variance"],
    "sentiment": ["sentiment", "buzz", "tone", "news_", "social", "mood", "emotion"],
    "analyst": ["estimate", "eps_est", "consensus", "recommend", "target_price", "revision", "dispersion"],
    "efficiency": ["turnover", "asset_turn", "inventory", "receivable", "cycle", "productivity"],
    "cashflow": ["cash_flow", "ocf", "fcf", "free_cash", "operating_cash"],
    "leverage": ["debt", "equity", "liabil", "leverage", "solvency", "current_ratio", "borrow"],
    "growth": ["growth", "change", "delta", "increase", "expansion", "yoy"],
    "valuation": ["yield", "p_e", "p_b", "ev_", "book_to", "earnings_yield", "market_cap", "price_to"],
    "profitability": ["income", "profit", "margin", "roa", "roe", "ebit", "ebitda", "gross", "net_income"],
}


def passes_gates(f: dict) -> bool:
    """三道闸门：alphaCount ≤ 500 ∧ coverage ≥ 0.7 ∧ type == MATRIX。"""
    alpha_count = f.get("alphaCount", 0) or 0
    coverage = f.get("coverage", 0) or 0
    ftype = f.get("type", "")
    return alpha_count <= ALPHA_COUNT_FALLBACK and coverage >= COVERAGE_MIN and ftype == "MATRIX"


def is_blacklisted(f: dict) -> bool:
    """检查字段 id 或 description 是否含黑名单关键词。"""
    text = (f.get("id", "") + " " + f.get("description", "")).lower()
    return any(kw in text for kw in BLACKLIST_KEYWORDS)


def is_saturated_dataset(f: dict) -> bool:
    ds = (f.get("dataset") or {}).get("id", "")
    return ds in SATURATED_DATASETS


def is_very_rare(f: dict) -> bool:
    """极冷门：userCount < 100 且 alphaCount < 5。"""
    return (f.get("userCount", 0) or 0) < USERCOUNT_RARE and (f.get("alphaCount", 0) or 0) < ALPHACOUNT_RARE


def filter_fields(fields: list[dict]) -> list[dict]:
    """应用三道闸门 + 粗筛，返回通过的字段列表（按 alphaCount 升序）。"""
    result = []
    for f in fields:
        if not passes_gates(f):
            continue
        if is_blacklisted(f):
            continue
        if is_saturated_dataset(f):
            continue
        result.append(f)
    result.sort(key=lambda x: x.get("alphaCount", 0))
    return result


def classify_dimension(f: dict) -> str:
    """将字段分类到 11 个经济学维度之一。"""
    text = (f.get("id", "") + " " + f.get("description", "")).lower()
    for dim, keywords in DIMENSION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return dim
    return "other"


def group_by_dimension(fields: list[dict]) -> dict[str, list[dict]]:
    """按维度分组。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in fields:
        dim = classify_dimension(f)
        groups[dim].append(f)
    return dict(groups)


def format_markdown_table(grouped: dict[str, list[dict]], *, top_n: int = 15) -> str:
    """生成按维度分组的 Markdown 表格输出。"""
    lines = []
    lines.append("| 字段名 | alphaCount | coverage | userCount | dataset | category | description |")
    lines.append("|--------|-----------|----------|-----------|---------|----------|-------------|")
    for dim in sorted(grouped.keys()):
        fields = grouped[dim][:top_n]
        if not fields:
            continue
        lines.append(f"")
        lines.append(f"### {dim}")
        for f in fields:
            ds = (f.get("dataset") or {}).get("id", "")
            cat = (f.get("category") or {}).get("id", "")
            desc = (f.get("description") or "")[:80]
            rare_marker = " ⚠️极冷门" if is_very_rare(f) else ""
            lines.append(
                f"| {f['id']}{rare_marker} | {f.get('alphaCount', 0)} | "
                f"{f.get('coverage', 0):.2f} | {f.get('userCount', 0)} | "
                f"{ds} | {cat} | {desc} |"
            )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="低拥挤字段推荐")
    ap.add_argument("--region", required=True, help="区域，如 usa/glb/chn")
    ap.add_argument("--universe", required=True, help="宇宙，如 top3000/top2000")
    ap.add_argument("--delay", type=int, default=1, help="延迟（默认 1）")
    ap.add_argument("--refresh", action="store_true", help="强制重新拉取快照")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--top", type=int, default=15, help="每维度输出字段数")
    args = ap.parse_args()

    from wq_api import BrainSession  # 延迟导入，避免无凭据时报错

    brain = BrainSession(credential_file=str(REPO / "credential.txt"))
    brain.authenticate()

    if args.refresh or not snapshot_exists(args.region, args.universe, args.delay):
        print(f"拉取 {args.region}/{args.universe} delay={args.delay} 字段快照...")
        fields = refresh_snapshot(brain, args.region, args.universe, args.delay)
        print(f"已保存 {len(fields)} 个字段")
    else:
        fields = load_snapshot(args.region, args.universe, args.delay, brain=brain)

    # 快照有效期检查
    path = get_snapshot_path(args.region, args.universe, args.delay)
    is_stale, age_days = check_snapshot_age(path)
    if is_stale:
        print(f"⚠️ 字段快照已 {age_days:.0f} 天未更新（超过 30 天），alphaCount 可能已变化。")
        print(f"   请运行 --refresh 更新。")

    # 拉取 ACTIVE 池已用字段并剔除
    import re as _re
    actives = brain.alphas(status="ACTIVE", page_size=100)
    active_used: set[str] = set()
    for a in actives:
        code = (a.get("regular") or {}).get("code") or ""
        active_used.update(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
    print(f"ACTIVE 池已用字段: {len(active_used)} 个（将从推荐中剔除）")

    # 筛选
    filtered = filter_fields(fields)
    before_active = len(filtered)
    filtered = [f for f in filtered if f["id"] not in active_used]
    excluded_by_active = before_active - len(filtered)
    if excluded_by_active:
        print(f"已剔除 ACTIVE 池字段: {excluded_by_active} 个")

    grouped = group_by_dimension(filtered)

    if args.json:
        out = {
            "region": args.region,
            "universe": args.universe,
            "delay": args.delay,
            "snapshot_age_days": round(age_days, 1),
            "active_fields_count": len(active_used),
            "excluded_by_active": excluded_by_active,
            "total_filtered": len(filtered),
            "dimensions": {
                dim: [
                    {
                        "id": f["id"],
                        "alphaCount": f.get("alphaCount"),
                        "coverage": f.get("coverage"),
                        "userCount": f.get("userCount"),
                        "dataset": (f.get("dataset") or {}).get("id"),
                        "category": (f.get("category") or {}).get("id"),
                        "description": f.get("description"),
                        "very_rare": is_very_rare(f),
                    }
                    for f in fs[:args.top]
                ]
                for dim, fs in grouped.items()
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"=== 低拥挤字段推荐 ({args.region.upper()}/{args.universe.upper()} delay={args.delay}) ===")
        print(f"快照年龄: {age_days:.0f} 天 {'⚠️ 已超 30 天' if is_stale else '✓'}")
        print(f"ACTIVE 池已用: {len(active_used)} 个字段")
        print(f"筛选结果: {len(filtered)} 个字段（从 {len(fields)} 个中筛选，剔除 {excluded_by_active} 个 ACTIVE 池字段）\n")
        print(format_markdown_table(grouped, top_n=args.top))

    return 0


if __name__ == "__main__":
    sys.exit(main())
