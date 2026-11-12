#!/usr/bin/env python3
"""字段推荐引擎（Onboard 蓝海优先）。

核心策略：Onboard 时间 × alphaCount 双轮筛选

  真正的无人区蓝海 = dateCreated（onboard 时间）近 × alphaCount 低
  
  刚上线的新数据集/新扩充字段，全平台还没几个人跑过，具备三大优势：
  ① Prod Correlation 极低（先发优势）
  ② Dynamic Pyramid 倍率极高（冷门金字塔常 1.3x–1.8x）
  ③ ATOM 模板（vector_neut + ts_mean/ts_backfill）二阶结构即可直接过检
  
  典型蓝海实例（实测快照）：
  • USA 2026-03 analyst4 新扩充 503 字段 → αCount=0, userCount=0（没人跑过！）
  • GBR predictive_starmine 全新数据集 → 2150 字段 αCount=0
  • EUR pv20 / analyst10 新字段 → αCount=1–3

降级策略：
  当没有足够新蓝海字段时，回退到 VF（Value Factor）经典数据集的冷字段——
  即经典数据集内最近扩充/还没被大量使用的字段。

用法：
    python scripts/recommend_fields.py --region usa --universe top3000
    python scripts/recommend_fields.py --region gbr --universe top700    # GBR 蓝海多
    python scripts/recommend_fields.py --region glb --universe top3000 --refresh
    python scripts/recommend_fields.py --region usa --universe top3000 --days 365 --max-alpha 50
    python scripts/recommend_fields.py --region usa --universe top3000 --mode vf      # VF 兜底
    python scripts/recommend_fields.py --region usa --universe top3000 --pyramid       # 估算倍率
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
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

# 低质量数据集（映射表、账本过短、无研究信号）
LOW_QUALITY_DATASETS = {
    # 映射表类：RIC↔Bloomberg BBID
    "other321", "other10", "news90", "model218", "shortinterest21",
    "analyst11", "analyst16", "fundamental88", "analyst95", "model255",
}

# VF 经典数据集（蓝海耗尽时兜底）
VF_CLASSIC_DATASETS = {
    "pv1", "pv13", "fundamental6", "fundamental23", "fundamental90",
    "analyst4", "analyst15", "analyst90", "analyst91", "analyst92",
    "model26", "model38", "model51", "model77", "model109", "model110",
    "model238", "risk70", "risk87", "option8", "option9",
    "news12", "news18", "socialmedia8", "socialmedia12",
}

# ATOM 适配度检查：排除纯分类/标记类字段（没有时间序列信号）
ATOM_EXCLUDE_KEYWORDS = {
    "flag", "type", "category", "class", "label", "bucket_id",
    "is_", "has_", "dummy", "indicat", "group_id", "theme_id",
}

# 蓝海闸门默认值
BLUESEA_DAYS_MAX = 365          # onboard 时间窗口：1 年内
BLUESEA_ALPHA_MAX = 100         # alphaCount 上限
BLUESEA_COV_MIN = 0.5           # 覆盖度下限

# 衍生信号字段黑名单
BLACKLIST_KEYWORDS = {
    "rank", "percentile", "score", "signal", "factor", "zscore",
    "normalized", "standardized", "decay", "neutralized", "adjusted",
}

# 11 个经济学维度
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


# ---------------------------------------------------------------------------
# 日期解析
# ---------------------------------------------------------------------------

def _parse_date(date_str: str | None) -> datetime | None:
    """解析 API 返回的 dateCreated（格式 '2026-03-01'）。"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _days_since(date_str: str | None, *, now: datetime | None = None) -> float:
    """距离 onboard 的天数。无 dateCreated 返回一个巨大值（999999）。"""
    dt = _parse_date(date_str)
    if dt is None:
        return 999999
    if now is None:
        now = datetime.now(timezone.utc)
    return (now - dt).days


# ---------------------------------------------------------------------------
# 核心属性判断
# ---------------------------------------------------------------------------

def is_atom_ready(f: dict) -> bool:
    """ATOM 模板适配性：MATRIX + coverage ≥ 0.5 + 非分类标记。"""
    if f.get("type") != "MATRIX":
        return False
    cov = f.get("coverage", 0) or 0
    if cov < 0.5:
        return False
    text = (f.get("id", "") + " " + f.get("description", "")).lower()
    return not any(kw in text for kw in ATOM_EXCLUDE_KEYWORDS)


def is_low_quality(f: dict) -> bool:
    """已知低质量数据集（映射表、账本过短等）。"""
    ds = (f.get("dataset") or {}).get("id", "")
    return ds in LOW_QUALITY_DATASETS


def is_vf_classic(f: dict) -> bool:
    """VF 经典数据集。"""
    ds = (f.get("dataset") or {}).get("id", "")
    return ds in VF_CLASSIC_DATASETS


def is_blue_sea(f: dict, *, days_max: float = BLUESEA_DAYS_MAX,
                alpha_max: int = BLUESEA_ALPHA_MAX) -> bool:
    """真正的蓝海：新上线 + 低 alphaCount + MATRIX + 覆盖够 + 非低质量。"""
    if is_low_quality(f):
        return False
    if f.get("type") != "MATRIX":
        return False
    cov = f.get("coverage", 0) or 0
    if cov < BLUESEA_COV_MIN:
        return False
    d = _days_since(f.get("dateCreated"))
    if d > days_max:
        return False
    ac = f.get("alphaCount", 0) or 0
    if ac > alpha_max:
        return False
    return True


def _pyramid_multiplier(alpha_count: int) -> float:
    """估算 Dynamic Pyramid 倍率。

    经验公式（基于社区观测）：
    • alphaCount < 10  → 倍率约 1.6–1.8x（极冷门金字塔）
    • alphaCount 10–50 → 倍率约 1.3–1.5x
    • alphaCount 50–200 → 倍率约 1.1–1.2x
    • alphaCount > 200 → 倍率约 1.0x（已热门）

    用指数衰减模型近似：multiplier = 1.0 + 0.8 × exp(-alphaCount / 30)
    这样：αCount=0 → 1.8x；αCount=10 → 1.57x；αCount=50 → 1.14x；αCount=200 → 1.003x
    """
    return round(1.0 + 0.8 * math.exp(-alpha_count / 30.0), 2)


# ---------------------------------------------------------------------------
# 排序
# ---------------------------------------------------------------------------

def _bluesea_sort_key(f: dict, now: datetime) -> tuple:
    """蓝海排序：(days_since, alphaCount, -coverage, -userCount)"""
    d = _days_since(f.get("dateCreated"), now=now)
    ac = f.get("alphaCount", 0) or 0
    cov = f.get("coverage", 0) or 0
    uc = f.get("userCount", 0) or 0
    return (d, ac, -cov, -uc)


def _vf_fallback_sort_key(f: dict, now: datetime) -> tuple:
    """VF 兜底排序：先经典数据集内新→冷，再非经典新→冷。"""
    ds = (f.get("dataset") or {}).get("id", "")
    is_vf = ds in VF_CLASSIC_DATASETS
    d = _days_since(f.get("dateCreated"), now=now)
    ac = f.get("alphaCount", 0) or 0
    cov = f.get("coverage", 0) or 0
    uc = f.get("userCount", 0) or 0
    return (not is_vf, d, ac, -cov, -uc)


def _old_cold_sort_key(f: dict, now: datetime) -> tuple:
    """旧式冷门排序（保留兼容）：alphaCount 升序。"""
    return (f.get("alphaCount", 0) or 0, -_days_since(f.get("dateCreated"), now=now))


# ---------------------------------------------------------------------------
# 主筛选
# ---------------------------------------------------------------------------

def filter_fields(
    fields: list[dict],
    *,
    mode: str = "bluesea",
    days_max: float = BLUESEA_DAYS_MAX,
    alpha_max: int = BLUESEA_ALPHA_MAX,
) -> list[dict]:
    """按 mode 筛选 + 排序。

    modes:
      bluesea  — 蓝海优先：新上线 × 低 αCount（按 onboard 时间升序 + αCount 升序）
      vf       — VF 兜底：经典数据集内的冷字段（先经典内新冷，再非经典新冷）
      cold     — 旧式冷门：纯 alphaCount 升序（仅当快照无 dateCreated 数据时用）
    """
    now = datetime.now(timezone.utc)
    result: list[dict] = []

    for f in fields:
        # 通用硬闸门：非低质量 + MATRIX + 覆盖够（所有模式都要求）
        if is_low_quality(f):
            continue
        if f.get("type") != "MATRIX":
            continue
        cov = f.get("coverage", 0) or 0
        if cov < BLUESEA_COV_MIN:
            continue
        # 衍生信号黑名单
        text = (f.get("id", "") + " " + f.get("description", "")).lower()
        if any(kw in text for kw in BLACKLIST_KEYWORDS):
            continue

        if mode == "bluesea":
            # 时间 + αCount 双闸门
            d = _days_since(f.get("dateCreated"), now=now)
            ac = f.get("alphaCount", 0) or 0
            if d > days_max or ac > alpha_max:
                continue
        elif mode == "vf":
            # VF 兜底：不卡时间和 αCount，经典数据集内的冷字段优先
            # 但还是排除太热门（αCount > 5000）的字段——那些已经完全饱和
            ac = f.get("alphaCount", 0) or 0
            if ac > 5000 and not is_vf_classic(f):
                continue
        elif mode == "cold":
            # 冷门模式：只看 αCount 极低
            ac = f.get("alphaCount", 0) or 0
            uc = f.get("userCount", 0) or 0
            if ac > 200 or uc == 0:
                continue

        result.append(f)

    # 排序
    if mode == "bluesea":
        result.sort(key=lambda f: _bluesea_sort_key(f, now))
    elif mode == "vf":
        result.sort(key=lambda f: _vf_fallback_sort_key(f, now))
    else:
        result.sort(key=lambda f: _old_cold_sort_key(f, now))

    return result


# ---------------------------------------------------------------------------
# Dataset 级聚合分析
# ---------------------------------------------------------------------------

def _dataset_summary(fields: list[dict], now: datetime) -> list[dict]:
    """按 dataset 聚合蓝海程度。返回 (dataset, 新字段数, 平均 αCount, 中位覆盖, 倍率中值)。"""
    by_ds: dict[str, list[dict]] = defaultdict(list)
    for f in fields:
        ds = (f.get("dataset") or {}).get("id", "")
        by_ds[ds].append(f)

    summary = []
    for ds, fs in by_ds.items():
        fs_atom = [f for f in fs if is_atom_ready(f)]
        if not fs_atom:
            continue
        dcs = [_days_since(f.get("dateCreated"), now=now) for f in fs_atom]
        acs = [(f.get("alphaCount", 0) or 0) for f in fs_atom]
        cove = [(f.get("coverage", 0) or 0) for f in fs_atom]
        mul = [_pyramid_multiplier(a) for a in acs]
        summary.append({
            "dataset": ds,
            "category": (fs_atom[0].get("category") or {}).get("id", ""),
            "field_count": len(fs_atom),
            "newest_days": min(dcs),
            "oldest_days": max(dcs),
            "avg_alpha": round(sum(acs) / len(acs)),
            "median_alpha": sorted(acs)[len(acs) // 2],
            "median_cov": round(sorted(cove)[len(cove) // 2], 2),
            "median_multiplier": sorted(mul)[len(mul) // 2],
            "bluesea_score": round(
                # 蓝海分：新 (→0) + 冷 (→0)  → 越低越蓝
                math.log(min(max(min(dcs), 1), 500)) * 2
                + math.log(max(sum(acs) / len(acs), 1)) * 1.5
                - sum(mul) / len(mul) * 1,  # 倍率高加分
                2,
            ),
        })
    return summary


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------

def classify_dimension(f: dict) -> str:
    text = (f.get("id", "") + " " + f.get("description", "")).lower()
    for dim, keywords in DIMENSION_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return dim
    return "other"


def group_by_dimension(fields: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in fields:
        groups[classify_dimension(f)].append(f)
    return dict(groups)


def _field_markers(f: dict, now: datetime) -> str:
    d = _days_since(f.get("dateCreated"), now=now)
    ac = f.get("alphaCount", 0) or 0
    markers = []
    if d < 90 and ac < 10:
        markers.append("🌊超新")
    elif d < 365 and ac < 100:
        markers.append("🌊新")
    if ac < 10:
        markers.append(f"🧊α{ac}")
    if is_vf_classic(f):
        markers.append("📀VF")
    return " ".join(markers)


def _format_dataset_table(summary: list[dict], *, top_n: int = 20) -> str:
    """Dataset 级蓝海排行表。"""
    lines = [
        "| dataset | category | 新字段数 | 最老→最新 | αCount 中位 | 覆盖中位 | 倍率中位 | 蓝海分 |",
        "|---------|----------|---------:|----------|-----------:|--------:|--------:|------:|",
    ]
    # 按蓝海分升序（越低越蓝）
    summary.sort(key=lambda s: (s["bluesea_score"], s["newest_days"]))
    for s in summary[:top_n]:
        lines.append(
            f"| {s['dataset']:<20s} | {s['category']:<10s} | {s['field_count']:>6d} | "
            f"{s['newest_days']:>4d}→{s['oldest_days']:>4d}d | {s['median_alpha']:>8d} | "
            f"{s['median_cov']:>7.2f} | {s['median_multiplier']:>6.2f}x | "
            f"{s['bluesea_score']:>6.2f} |"
        )
    return "\n".join(lines)


def _format_field_table(
    grouped: dict[str, list[dict]],
    *,
    top_n: int = 12,
    now: datetime,
    show_pyramid: bool = False,
) -> str:
    lines = [
        "| 字段名 | onboard天 | αCount | 覆盖 | users | dataset | markers | Pyramid× | desc |",
        "|--------|---------:|-------:|-----:|------:|---------|---------|--------:|------|",
    ]
    for dim in sorted(grouped.keys()):
        fields = grouped[dim][:top_n]
        if not fields:
            continue
        lines.append("")
        lines.append(f"### {dim}")
        for f in fields:
            d = _days_since(f.get("dateCreated"), now=now)
            ac = f.get("alphaCount", 0) or 0
            cov = f.get("coverage", 0) or 0
            uc = f.get("userCount", 0) or 0
            ds = (f.get("dataset") or {}).get("id", "")
            desc = (f.get("description") or "")[:55]
            markers = _field_markers(f, now)
            pyr = f"{_pyramid_multiplier(ac):.2f}" if show_pyramid else ""
            lines.append(
                f"| {f['id']} | {d:>7.0f} | {ac:>5d} | {cov:.2f} | {uc:>6d} | "
                f"{ds:<20s} | {markers} | {pyr} | {desc} |"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="字段推荐引擎（Onboard 蓝海优先）"
    )
    ap.add_argument("--region", required=True, help="区域，如 usa/gbr/eur/glb")
    ap.add_argument("--universe", required=True, help="宇宙，如 top3000/top700/top2500")
    ap.add_argument("--delay", type=int, default=1)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=12, help="每维度输出字段数")
    ap.add_argument(
        "--mode",
        choices=("bluesea", "vf", "cold"),
        default="bluesea",
        help="bluesea=新上线×低αCount（默认）；vf=VF 经典兜底；cold=旧式冷门",
    )
    ap.add_argument(
        "--days", type=int, default=BLUESEA_DAYS_MAX,
        help=f"bluesea 模式 onboard 时间窗口（默认 {BLUESEA_DAYS_MAX} 天）",
    )
    ap.add_argument(
        "--max-alpha", type=int, default=BLUESEA_ALPHA_MAX,
        help=f"bluesea 模式 alphaCount 上限（默认 {BLUESEA_ALPHA_MAX}）",
    )
    ap.add_argument("--pyramid", action="store_true", help="显示 Pyramid 倍率估算")
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

    path = get_snapshot_path(args.region, args.universe, args.delay)
    is_stale, age_days = check_snapshot_age(path)
    if is_stale:
        print(f"⚠️ 快照已 {age_days:.0f} 天未更新，alphaCount 可能偏高。建议 --refresh。")

    # 拉取 ACTIVE 池已用字段并剔除
    import re as _re
    actives = brain.alphas(status="ACTIVE", page_size=100)
    active_used: set[str] = set()
    for a in actives:
        code = (a.get("regular") or {}).get("code") or ""
        active_used.update(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
    print(f"ACTIVE 池已用字段: {len(active_used)} 个")

    # 筛选
    filtered = filter_fields(
        fields, mode=args.mode, days_max=args.days, alpha_max=args.max_alpha,
    )
    before_active = len(filtered)
    filtered = [f for f in filtered if f["id"] not in active_used]
    excluded_by_active = before_active - len(filtered)

    now = datetime.now(timezone.utc)
    has_date_created = any(_days_since(f.get("dateCreated"), now=now) < 999999 for f in fields)

    # 数据集聚合
    ds_summary = _dataset_summary(filtered, now)

    grouped = group_by_dimension(filtered)

    if args.json:
        out = {
            "region": args.region,
            "universe": args.universe,
            "delay": args.delay,
            "mode": args.mode,
            "days_window": args.days,
            "max_alpha": args.max_alpha,
            "snapshot_age_days": round(age_days, 1),
            "has_dateCreated": has_date_created,
            "active_fields_count": len(active_used),
            "excluded_by_active": excluded_by_active,
            "total_filtered": len(filtered),
            "dataset_summary": ds_summary[:30],
            "dimensions": {
                dim: [
                    {
                        "id": f["id"],
                        "alphaCount": f.get("alphaCount"),
                        "coverage": f.get("coverage"),
                        "userCount": f.get("userCount"),
                        "dataset": (f.get("dataset") or {}).get("id"),
                        "dateCreated": f.get("dateCreated"),
                        "days_since": int(_days_since(f.get("dateCreated"), now=now)),
                        "description": f.get("description"),
                        "pyramid_multiplier": _pyramid_multiplier(f.get("alphaCount", 0) or 0),
                        "atom_ready": is_atom_ready(f),
                        "vf_classic": is_vf_classic(f),
                    }
                    for f in fs[:args.top]
                ]
                for dim, fs in grouped.items()
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # 文本输出
    mode_label = {
        "bluesea": f"🌊 蓝海优先（< {args.days} 天 + αCount < {args.max_alpha}）",
        "vf": "📀 VF 经典兜底",
        "cold": "❄️ 旧式冷门备用",
    }[args.mode]

    print(f"=== 字段推荐 ({args.region.upper()}/{args.universe.upper()} delay={args.delay}) ===")
    print(f"模式: {mode_label}")
    print(f"快照年龄: {age_days:.0f} 天 {'⚠️ 已超 30 天' if is_stale else '✓'}")
    print(f"ACTIVE 池已用: {len(active_used)} 个字段")
    print(f"筛选结果: {len(filtered)} 个字段")
    if excluded_by_active:
        print(f"已剔除 ACTIVE 池字段: {excluded_by_active} 个")
    if not has_date_created:
        print("⚠️ 快照无 dateCreated 数据，无法做时间维度筛选！请 --refresh 拉取最新快照。")
    print()

    # Dataset 级排行
    if ds_summary:
        print("--- 📂 Dataset 级蓝海排行（蓝海分越低越蓝）---")
        print(_format_dataset_table(ds_summary, top_n=min(20, args.top)))
        print()

    # 字段级详情
    print("--- 📊 字段级详情 ---")
    print(_format_field_table(grouped, top_n=args.top, now=now, show_pyramid=args.pyramid))

    return 0


if __name__ == "__main__":
    sys.exit(main())
