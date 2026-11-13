#!/usr/bin/env python3
"""提交前硬闸门 —— 在花掉提交额度之前给出 GO / NO-GO。

为什么需要它
------------
2026-11-03 的实测教训：一条 EUR alpha 的本地 `gate_report` 返回 True、
四项指标全部过线（Sharpe 1.80 / Fitness 1.26 / TO 16%），提交时却因为两项被拒：

  * `IS_LADDER_SHARPE = 0.88 / 1.58` —— 仿真后是 WARNING，提交时被判 FAIL；
  * `PROD_CORRELATION = 0.8314 / 0.7` —— 仿真后是 PENDING，平台只在提交那刻回算。

2026-11-13 又补一条：`LOW_DURATION = 50 / 500`。字段只有 50 天可回测历史时，
Sharpe 2.05 / Fitness 2.22 / Margin 65.5‱ 也照样被拒；这一项在 QUICK/FULL 的
`is.checks` 里完全不出现，只能靠快照 `dateCreated` 的年龄提前估算（见年龄闸门）。

也就是说：**"指标全绿" 和 "能提交" 之间还隔着一道本地看不见的闸门。**
这个脚本把已知的可见部分全部前移，把不可见部分（生产池相关性）用拥挤度先验
量化成风险等级，避免继续用提交额度做盲试。

用法
----
    # 挖掘前先确认主题作用域（region/delay/universe）
    python scripts/preflight.py --themes

    # 常规：从 alpha id 判定（需要联网，会查拥挤度先验）
    python scripts/preflight.py RREmY1Qe KPJG6Jwj

    # 只看离线指标，不查拥挤度（省请求）
    python scripts/preflight.py RREmY1Qe --skip-crowding

    # 从研究脚本落盘的结果里批量判定
    python scripts/preflight.py --from-json .workbuddy/eur_mine3.json

    # 机器可读
    python scripts/preflight.py RREmY1Qe --json

退出码：0 = 至少一个 GO；1 = 全部 NO-GO；2 = 运行错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wq_api import (  # noqa: E402
    MIN_DURATION_DAYS,
    QUALITY_FITNESS_MIN,
    QUALITY_MARGIN_MIN,
    BrainError,
    BrainSession,
    field_availability,
    quality_blockers,
    quality_notes,
    theme_blockers,
    theme_entries,
)
from static_check import (  # noqa: E402
    BASE_PRICE_FIELDS,
    GROUP_OPERATORS,
    SIGNAL_OPERATORS,
    extract_signal_fields,
)

GROUP_KEY_TOKENS = {
    "country", "region", "industry", "subindustry", "sector", "market", "exchange",
}

# 拥挤度先验：用 alphaCount 近似 PROD_CORRELATION 风险。
# 标定样本（同一字段 `star_val_sector_rank`，同一账户）：
#   EUR/TOP2500 alphaCount=19800 → PROD_CORRELATION 0.8314 FAIL
#   AMR/TOP600  alphaCount=  256 → 只有 Sharpe 不达标，未触及相关性闸门
# 所以这里只做风险分级，不做概率预测——平台不对 prod corr 做任何本地可算的回算。
CROWD_HIGH = 5000
CROWD_MID = 1000

# 闸门用到的 ladder 类检查：仿真后可能只是 WARNING，提交时按 FAIL 判
LADDER_CHECKS = ("IS_LADDER_SHARPE", "LOW_2Y_SHARPE")


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _age_days(date_created: Any) -> Optional[float]:
    """字段 dateCreated 距今多少天。解析失败返回 None（当作未知，不阻断）。"""
    if not isinstance(date_created, str) or len(date_created) < 10:
        return None
    try:
        created = datetime.strptime(date_created[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - created).total_seconds() / 86400


def signal_fields(expression: str) -> list[str]:
    """表达式里的信号字段（保持出现顺序）。

    `extract_signal_fields` 把 `vector_neut` 当分组算子，ATOM 骨架
    `vector_neut(ts_mean(f,20), ts_mean(f,250))` 会抽出空集，导致拥挤度与
    字段年龄闸门被静默跳过。这里在空集时按标识符兜底。
    """
    fields = [f for f in extract_signal_fields(expression) if f not in BASE_PRICE_FIELDS]
    if fields:
        return sorted(fields)
    skip = SIGNAL_OPERATORS | GROUP_OPERATORS | GROUP_KEY_TOKENS | {"vector_neut", "neut"}
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression or "")
    return [t for t in dict.fromkeys(tokens)
            if t not in skip and t not in BASE_PRICE_FIELDS]


def crowding_prior(
    field_counts: dict[str, Optional[int]],
    field_ages: Optional[dict[str, Optional[float]]] = None,
) -> dict:
    """把字段 alphaCount 归成风险等级，并带上最年轻字段的年龄。纯函数，便于单测。"""
    known = {k: v for k, v in field_counts.items() if v is not None}
    ages = {k: v for k, v in (field_ages or {}).items() if v is not None}
    facts = {
        "field_ages": ages,
        "min_age_days": min(ages.values()) if ages else None,
        "youngest_field": min(ages, key=ages.get) if ages else None,
    }
    if not known:
        return {"level": "unknown", "max_alpha_count": None,
                "detail": "未能取到 alphaCount", **facts}
    worst_field, worst = max(known.items(), key=lambda kv: kv[1])
    if worst >= CROWD_HIGH:
        level, hint = "high", f"{worst_field} 已有 {worst} 个 alpha，同族极易撞 PROD_CORRELATION"
    elif worst >= CROWD_MID:
        level, hint = "mid", f"{worst_field} 已有 {worst} 个 alpha，形态必须与主流量化因子不同"
    else:
        level, hint = "low", f"最拥挤字段 {worst_field} 仅 {worst} 个 alpha（冷门≠有效，仍需看信号）"
    return {"level": level, "max_alpha_count": worst, "worst_field": worst_field,
            "detail": hint, **facts}


def evaluate(
    alpha: dict,
    thresholds: dict,
    *,
    strict: bool = True,
    crowding: Optional[dict] = None,
    quality: bool = True,
    theme: bool = True,
) -> dict:
    """纯函数判定：给定 alpha 与阈值，返回 GO / NO-GO 及全部理由。

    与 `BrainSession.gate_report` 的差别：
      * ladder 类检查即使在 `is.checks` 里是 WARNING，只要 value < limit 就算阻断；
      * 把阻断（blockers）与提示（warnings）分开，前者一票否决；
      * 把拥挤度先验并入结论（`PROD_CORRELATION` 唯一可用的本地代理）；
      * 质量闸门（默认开启）：Fitness < 2.0 或 Margin < 10‱ 一票否决——
        与平台「允许提交」线（Fitness 1.0）不是一回事，低质量提交会拉低 VF。
    """
    is_ = alpha.get("is") or {}
    settings = alpha.get("settings") or {}
    checks = {
        c.get("name"): c
        for c in (is_.get("checks") or [])
        if c.get("name")
    }
    blockers: list[str] = []
    warnings: list[str] = []

    sharpe = _num(is_.get("sharpe"))
    fitness = _num(is_.get("fitness"))
    turnover = _num(is_.get("turnover"))
    returns = _num(is_.get("returns"))
    drawdown = _num(is_.get("drawdown"))
    margin = _num(is_.get("margin"))

    if sharpe is not None and sharpe < thresholds["sharpe"]:
        blockers.append(f"Sharpe {sharpe:.2f} < {thresholds['sharpe']:.2f}")
    if fitness is not None and fitness < thresholds["fitness"]:
        blockers.append(f"Fitness {fitness:.2f} < {thresholds['fitness']:.2f}")
    if turnover is not None:
        lo, hi = thresholds["turnover"]
        if not lo <= turnover <= hi:
            blockers.append(f"Turnover {turnover:.2%} 不在 [{lo:.0%}, {hi:.0%}]")

    # 质量闸门（质量 > 数量）：Fitness / Margin / PnL 形态
    if quality:
        blockers.extend(quality_blockers(is_))
        warnings.extend(quality_notes(is_))

    # 主题闸门：优先挖主题内 alpha（主题外拿不到 multiplier）
    themes = theme_entries(is_.get("checks") or [])
    if theme:
        blockers.extend(theme_blockers(is_.get("checks") or []))
        for t in themes:
            if t.get("result") == "PASS":
                warnings.append(f"命中主题 {t.get('name')}（x{t.get('multiplier')}）")

    # ladder 类：WARNING 不可采信
    ladder: dict[str, dict] = {}
    for name in LADDER_CHECKS:
        check = checks.get(name)
        if not check:
            continue
        value, limit = _num(check.get("value")), _num(check.get("limit"))
        result = check.get("result")
        ladder[name] = {"result": result, "value": value, "limit": limit}
        if result in ("FAIL", "ERROR"):
            blockers.append(f"{name} = {result} {value}/{limit}")
        elif result == "WARNING":
            if value is None or limit is None or value < limit:
                if strict:
                    blockers.append(
                        f"{name} = WARNING {value}/{limit} —— 提交时会被裁定为 FAIL"
                    )
                else:
                    warnings.append(f"{name} = WARNING {value}/{limit}（strict 已关闭）")

    # 其余阻断项
    for name in ("LOW_SUB_UNIVERSE_SHARPE", "CONCENTRATED_WEIGHT", "LOW_TURNOVER",
                 "HIGH_TURNOVER", "OLD_SIMULATION", "DATA_DIVERSITY", "LOW_DURATION"):
        check = checks.get(name)
        if check and check.get("result") in ("FAIL", "ERROR"):
            blockers.append(f"{name} = {check.get('result')} {check.get('value')}/{check.get('limit')}")

    # 相关性：仿真后恒 PENDING，只能提示
    for name in ("SELF_CORRELATION", "PROD_CORRELATION", "POWER_POOL_CORRELATION"):
        check = checks.get(name)
        if check and check.get("result") == "PENDING":
            warnings.append(f"{name} 仿真后必为 PENDING，只有提交那一刻才有真值")

    # 拥挤度先验（prod corr 的唯一本地代理）
    if crowding:
        level = crowding.get("level")
        if level == "high":
            blockers.append(f"拥挤度先验 HIGH：{crowding.get('detail')}")
        elif level == "mid":
            warnings.append(f"拥挤度先验 MID：{crowding.get('detail')}")
        elif level == "low":
            warnings.append(f"拥挤度先验 LOW：{crowding.get('detail')}")

    # 数据历史闸门：LOW_DURATION 只有提交那一刻才回算，本地只能按 dateCreated 年龄估
    if crowding:
        min_age = crowding.get("min_age_days")
        youngest = crowding.get("youngest_field")
        if min_age is not None and min_age < MIN_DURATION_DAYS:
            blockers.append(
                f"{youngest} 上线约 {int(min_age)} 天 < {MIN_DURATION_DAYS} 天，"
                f"提交时 LOW_DURATION 必拒（字段可回测历史不足）"
            )

    return {
        "alpha_id": alpha.get("id"),
        "region": settings.get("region"),
        "universe": settings.get("universe"),
        "delay": settings.get("delay"),
        "decay": settings.get("decay"),
        "neutralization": settings.get("neutralization"),
        "truncation": settings.get("truncation"),
        "status": alpha.get("status"),
        "metrics": {
            "sharpe": sharpe, "fitness": fitness, "turnover": turnover,
            "returns": returns, "drawdown": drawdown, "margin": margin,
        },
        "ladder": ladder,
        "themes": themes,
        "crowding": crowding,
        "blockers": blockers,
        "warnings": warnings,
        "verdict": "GO" if not blockers else "NO-GO",
    }


def collect_crowding(brain: BrainSession, alpha: dict) -> Optional[dict]:
    """联网查信号字段在该 region/universe 下的 alphaCount，给出拥挤度先验。"""
    expression = (alpha.get("regular") or {}).get("code") or ""
    settings = alpha.get("settings") or {}
    region = settings.get("region")
    universe = settings.get("universe")
    delay = settings.get("delay")
    if not expression or not region:
        return None
    fields = signal_fields(expression)
    counts: dict[str, Optional[int]] = {}
    ages: dict[str, Optional[float]] = {}
    for fid in fields:
        entries = field_availability(brain, fid, region=region, universe=universe, delay=delay)
        if not entries:
            # 该宇宙下没有条目时退一步：同 region 取最大 alphaCount
            entries = field_availability(brain, fid, region=region, delay=delay)
        values = [e.get("alphaCount") for e in entries if e.get("alphaCount") is not None]
        counts[fid] = max(values) if values else None
        field_ages = [_age_days(e.get("dateCreated")) for e in entries]
        known_ages = [a for a in field_ages if a is not None]
        ages[fid] = max(known_ages) if known_ages else None
    return crowding_prior(counts, ages)


def render(result: dict) -> str:
    m = result["metrics"]

    def pct(x: Optional[float]) -> str:
        return f"{x * 100:.2f}%" if x is not None else "—"

    def bps(x: Optional[float]) -> str:
        """Margin 用万分比（‱）显示：0.0015 → 15.0‱。"""
        return f"{x * 10000:.1f}‱" if x is not None else "—"

    lines = [
        f"{'=' * 68}",
        f"{result['alpha_id']}  {result['region']}/{result['universe']} "
        f"delay={result['delay']} decay={result['decay']} {result['neutralization']}",
        f"  Sharpe {m['sharpe']:.2f}  Fitness {m['fitness']:.2f}  TO {pct(m['turnover'])}  "
        f"Ret {pct(m['returns'])}  DD {pct(m['drawdown'])}  Margin {bps(m['margin'])}"
        if m["sharpe"] is not None else "",
        f"  质量线: Fitness ≥ {QUALITY_FITNESS_MIN:.1f}  Margin ≥ {QUALITY_MARGIN_MIN * 10000:.0f}‱",
    ]
    for name, info in result["ladder"].items():
        lines.append(
            f"  {name}: {info['result']} {info['value']}/{info['limit']}"
        )
    for t in result.get("themes") or []:
        scope = ""
        if t.get("region"):
            scope = f" [{t['region']}/D{t['delay']}"
            if t.get("universe"):
                scope += f"/{t['universe']}"
            scope += "]"
        mult = f" x{t['multiplier']:g}" if isinstance(t.get("multiplier"), (int, float)) else ""
        lines.append(f"  主题: {t.get('name')}{mult}{scope} → {t.get('result')}")
    if result.get("crowding"):
        lines.append(f"  拥挤度先验: {result['crowding']['level'].upper()} — {result['crowding']['detail']}")
        age = result["crowding"].get("min_age_days")
        if age is not None:
            mark = "✗" if age < MIN_DURATION_DAYS else "✓"
            lines.append(
                f"  数据历史: 最年轻字段 {int(age)} 天 {mark} 下限 {MIN_DURATION_DAYS} 天"
                f"（LOW_DURATION 只在提交时回算）"
            )
    for msg in result["blockers"]:
        lines.append(f"  ✗ 阻断: {msg}")
    for msg in result["warnings"]:
        lines.append(f"  · 提示: {msg}")
    lines.append(f"  => {result['verdict']}")
    return "\n".join(line for line in lines if line)


def render_themes(themes: list[dict]) -> str:
    """挖掘前先看这张表：主题作用域就是该优先挖的 region/delay/universe。"""
    if not themes:
        return "未发现主题（最近 alpha 的 MATCHES_THEMES 为空）"
    lines = [f"{'=' * 68}", "当前主题（按 MATCHES_THEMES 聚合，PASS > WARNING > PENDING）"]
    for t in themes:
        scope = f"{t.get('region') or '?'}/D{t.get('delay') or '?'}"
        if t.get("universe"):
            scope += f"/{t['universe']}"
        mult = f"x{t['multiplier']:g}" if isinstance(t.get("multiplier"), (int, float)) else "x?"
        lines.append(f"  {scope:<22s} {mult:<5s} {t.get('result'):<8s} {t.get('name')}")
    lines.append("挖掘时优先以上作用域；换 region/universe 前先确认主题，别在主题外白跑。")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="提交前硬闸门：GO / NO-GO 判定")
    ap.add_argument("alpha_ids", nargs="*", help="alpha id 列表")
    ap.add_argument("--from-json", help="从研究脚本落盘的 JSON 里取 alpha_id")
    ap.add_argument("--no-strict", action="store_true", help="不把 ladder WARNING 当阻断（仅复盘用）")
    ap.add_argument("--no-theme", action="store_true", help="不把主题未命中当阻断（仅复盘用）")
    ap.add_argument("--skip-crowding", action="store_true", help="不查拥挤度（省请求）")
    ap.add_argument("--themes", action="store_true", help="只列出当前主题作用域后退出")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if args.themes:
        brain = BrainSession()
        brain.authenticate()
        themes = brain.active_themes()
        if args.json:
            print(json.dumps(themes, ensure_ascii=False, indent=2))
        else:
            print(render_themes(themes))
        return 0 if themes else 1

    ids = list(args.alpha_ids)
    if args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
        ids += [r["alpha_id"] for r in rows if isinstance(r, dict) and r.get("alpha_id")]
    if not ids:
        ap.error("没有可判定的 alpha：请给 alpha_id 或 --from-json")

    brain = BrainSession()
    brain.authenticate()
    results = []
    for aid in ids:
        try:
            alpha = brain.alpha(aid)
        except BrainError as exc:
            print(f"[{aid}] 读取失败：{exc}", file=sys.stderr)
            continue
        delay = int((alpha.get("settings") or {}).get("delay", 1))
        crowding = None if args.skip_crowding else collect_crowding(brain, alpha)
        results.append(
            evaluate(alpha, brain.thresholds(delay), strict=not args.no_strict,
                     crowding=crowding, theme=not args.no_theme)
        )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for res in results:
            print(render(res))
        go = [r for r in results if r["verdict"] == "GO"]
        print(f"{'=' * 68}\nGO {len(go)} / {len(results)}")
    return 0 if any(r["verdict"] == "GO" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
