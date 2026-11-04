#!/usr/bin/env python3
"""提交前硬闸门 —— 在花掉提交额度之前给出 GO / NO-GO。

为什么需要它
------------
2026-11-03 的实测教训：一条 EUR alpha 的本地 `gate_report` 返回 True、
四项指标全部过线（Sharpe 1.80 / Fitness 1.26 / TO 16%），提交时却因为两项被拒：

  * `IS_LADDER_SHARPE = 0.88 / 1.58` —— 仿真后是 WARNING，提交时被判 FAIL；
  * `PROD_CORRELATION = 0.8314 / 0.7` —— 仿真后是 PENDING，平台只在提交那刻回算。

也就是说：**"指标全绿" 和 "能提交" 之间还隔着一道本地看不见的闸门。**
这个脚本把已知的可见部分全部前移，把不可见部分（生产池相关性）用拥挤度先验
量化成风险等级，避免继续用提交额度做盲试。

用法
----
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
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wq_api import BrainError, BrainSession, field_availability  # noqa: E402
from static_check import BASE_PRICE_FIELDS, extract_signal_fields  # noqa: E402

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


def crowding_prior(field_counts: dict[str, Optional[int]]) -> dict:
    """把字段 alphaCount 归成风险等级。纯函数，便于单测。"""
    known = {k: v for k, v in field_counts.items() if v is not None}
    if not known:
        return {"level": "unknown", "max_alpha_count": None, "detail": "未能取到 alphaCount"}
    worst_field, worst = max(known.items(), key=lambda kv: kv[1])
    if worst >= CROWD_HIGH:
        level, hint = "high", f"{worst_field} 已有 {worst} 个 alpha，同族极易撞 PROD_CORRELATION"
    elif worst >= CROWD_MID:
        level, hint = "mid", f"{worst_field} 已有 {worst} 个 alpha，形态必须与主流量化因子不同"
    else:
        level, hint = "low", f"最拥挤字段 {worst_field} 仅 {worst} 个 alpha（冷门≠有效，仍需看信号）"
    return {"level": level, "max_alpha_count": worst, "worst_field": worst_field, "detail": hint}


def evaluate(
    alpha: dict,
    thresholds: dict,
    *,
    strict: bool = True,
    crowding: Optional[dict] = None,
) -> dict:
    """纯函数判定：给定 alpha 与阈值，返回 GO / NO-GO 及全部理由。

    与 `BrainSession.gate_report` 的差别：
      * ladder 类检查即使在 `is.checks` 里是 WARNING，只要 value < limit 就算阻断；
      * 把阻断（blockers）与提示（warnings）分开，前者一票否决；
      * 把拥挤度先验并入结论（`PROD_CORRELATION` 唯一可用的本地代理）。
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
                 "HIGH_TURNOVER", "OLD_SIMULATION", "DATA_DIVERSITY"):
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
    fields = [f for f in extract_signal_fields(expression) if f not in BASE_PRICE_FIELDS]
    counts: dict[str, Optional[int]] = {}
    for fid in fields:
        entries = field_availability(brain, fid, region=region, universe=universe, delay=delay)
        if not entries:
            # 该宇宙下没有条目时退一步：同 region 取最大 alphaCount
            entries = field_availability(brain, fid, region=region, delay=delay)
        values = [e.get("alphaCount") for e in entries if e.get("alphaCount") is not None]
        counts[fid] = max(values) if values else None
    return crowding_prior(counts)


def render(result: dict) -> str:
    m = result["metrics"]

    def pct(x: Optional[float]) -> str:
        return f"{x * 100:.2f}%" if x is not None else "—"

    lines = [
        f"{'=' * 68}",
        f"{result['alpha_id']}  {result['region']}/{result['universe']} "
        f"delay={result['delay']} decay={result['decay']} {result['neutralization']}",
        f"  Sharpe {m['sharpe']:.2f}  Fitness {m['fitness']:.2f}  TO {pct(m['turnover'])}  "
        f"Ret {pct(m['returns'])}  DD {pct(m['drawdown'])}" if m["sharpe"] is not None else "",
    ]
    for name, info in result["ladder"].items():
        lines.append(
            f"  {name}: {info['result']} {info['value']}/{info['limit']}"
        )
    if result.get("crowding"):
        lines.append(f"  拥挤度先验: {result['crowding']['level'].upper()} — {result['crowding']['detail']}")
    for msg in result["blockers"]:
        lines.append(f"  ✗ 阻断: {msg}")
    for msg in result["warnings"]:
        lines.append(f"  · 提示: {msg}")
    lines.append(f"  => {result['verdict']}")
    return "\n".join(line for line in lines if line)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="提交前硬闸门：GO / NO-GO 判定")
    ap.add_argument("alpha_ids", nargs="*", help="alpha id 列表")
    ap.add_argument("--from-json", help="从研究脚本落盘的 JSON 里取 alpha_id")
    ap.add_argument("--no-strict", action="store_true", help="不把 ladder WARNING 当阻断（仅复盘用）")
    ap.add_argument("--skip-crowding", action="store_true", help="不查拥挤度（省请求）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

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
            evaluate(alpha, brain.thresholds(delay), strict=not args.no_strict, crowding=crowding)
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
