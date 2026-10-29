"""WQ Alpha Research Skill self-evolution helper.

自包含：只依赖 `requests` / `numpy`，凭据来自环境变量或未跟踪的 `credential.txt`。

Usage:
    cd <skill-dir>
    python scripts/evolve_skill.py            # 预览
    python scripts/evolve_skill.py --apply    # 追加到 SKILL.md 并更新 alpha_db.json

Behavior:
    - First run (empty alpha_db.json): bulk snapshot.
    - Subsequent runs: incremental entries for new/changed alphas.
    - Without --apply: prints proposed markdown snippet, modifies nothing.
    - With --apply: appends snippet to SKILL.md Section 12 and saves alpha_db.json.

对齐 2026-09 官方文档的改动（详见 scripts/wq_api.py 头注释）:
    - 记录集读取遵循 `Retry-After`，不再盲等固定秒数；
    - PnL 保存为 [(date, value)]，相关性按**日期交集**对齐（位置对齐会低估相关）；
    - ACTIVE alpha 走服务端 `status=ACTIVE` 过滤，避免每次拉全量再本地筛选；
    - 指标评价采用**顾问级阈值**（D1: Sharpe>1.58 / Fitness>1.0），不再写死 1.1/1.5。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, aligned_corr, to_returns  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ALPHA_DB_PATH = SKILL_DIR / "alpha_db.json"
SKILL_PATH = SKILL_DIR / "SKILL.md"
CREDENTIAL_PATH = SKILL_DIR / "credential.txt"


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------
def fetch_pnl(brain: BrainSession, alpha_id: str) -> list[list[Any]]:
    """返回 [[date, value], ...]；失败返回空列表。"""
    try:
        series = brain.pnl_series(alpha_id)
    except Exception:
        return []
    return [[d, v] for d, v in series]


def _as_pairs(pnl: Any) -> list[tuple[str, float]]:
    """Deprecated: 保留别名以兼容旧调用，实际实现在 wq_api.as_pairs。"""
    from wq_api import as_pairs

    return as_pairs(pnl)


def load_alpha_db() -> dict[str, Any]:
    if ALPHA_DB_PATH.exists():
        return json.loads(ALPHA_DB_PATH.read_text(encoding="utf-8"))
    return {"alphas": {}, "last_update": None, "version": 2}


def save_alpha_db(db: dict[str, Any]) -> None:
    ALPHA_DB_PATH.write_text(json.dumps(db, indent=2, default=str), encoding="utf-8")


def compute_alpha_fingerprint(alpha: dict) -> dict[str, Any]:
    """Stable snapshot of an alpha that we can compare across runs."""
    is_ = alpha.get("is", {}) if isinstance(alpha.get("is"), dict) else {}
    expr_obj = alpha.get("regular", alpha.get("expression", {}))
    expr = expr_obj.get("code") if isinstance(expr_obj, dict) else str(expr_obj)
    settings = alpha.get("settings", {})
    return {
        "status": alpha.get("status"),
        "expression": expr,
        "settings": settings,
        "sharpe": is_.get("sharpe"),
        "fitness": is_.get("fitness"),
        "returns": is_.get("returns"),
        "turnover": is_.get("turnover"),
        "drawdown": is_.get("drawdown"),
        "margin": is_.get("margin"),
        "long_count": is_.get("longCount"),
        "short_count": is_.get("shortCount"),
    }


def classify_alpha(expr: str) -> str:
    """Rough family classification based on expression tokens."""
    expr_lower = (expr or "").lower()
    tokens = []
    if any(f in expr_lower for f in ["operating_income/equity", "oi/equity", "operating_income/sales"]):
        tokens.append("profitability")
    if any(f in expr_lower for f in ["est_eps", "est_fcf", "est_revenue", "est_ebitda", "est_ptp"]):
        tokens.append("analyst")
    if any(f in expr_lower for f in ["free_cash_flow", "cashflow_op", "cash_flow"]):
        tokens.append("cashflow")
    if any(f in expr_lower for f in ["close/open", "open/close", "vwap", "returns", "volume", "high + low"]):
        tokens.append("technical")
    if any(f in expr_lower for f in ["scl12_buzz", "scl12_sentiment", "sentiment"]):
        tokens.append("sentiment")
    if any(f in expr_lower for f in ["equity/assets", "liabilities/assets", "sales/assets"]):
        tokens.append("quality/leverage")
    return "+".join(tokens) if tokens else "other"


def correlation_with_existing(
    new_pnl: Any, db: dict[str, Any], min_records: int = 50
) -> list[dict[str, Any]]:
    """New alpha 与库内 ACTIVE alpha 的日收益相关（按日期交集对齐）。"""
    new_ret = to_returns(new_pnl)
    if len(new_ret) < min_records:
        return []
    results: list[dict[str, Any]] = []
    for old_id, old in db.get("alphas", {}).items():
        if old.get("status") != "ACTIVE" or not old.get("pnl"):
            continue
        corr = aligned_corr(new_ret, to_returns(old["pnl"]))
        if corr is None:
            continue
        results.append(
            {"alpha_id": old_id, "corr": corr, "sharpe": old.get("sharpe"), "fitness": old.get("fitness")}
        )
    results.sort(key=lambda x: abs(x["corr"]), reverse=True)
    return results


def generate_lesson(
    fp: dict[str, Any], top_corr: list[dict[str, Any]], thresholds: dict | None = None
) -> str:
    """Generate a one-line lesson from this alpha（阈值随顾问权限自适应）。"""
    family = classify_alpha(fp["expression"])
    th = thresholds or {"sharpe": 1.58, "fitness": 1.0, "turnover": (0.01, 0.70)}
    sharpe, fitness, turnover = fp.get("sharpe"), fp.get("fitness"), fp.get("turnover")

    if fitness is None:
        metric_note = "模拟失败或数据缺失"
    elif sharpe is not None and sharpe >= th["sharpe"] and fitness >= th["fitness"] and (
        turnover is None or turnover <= th["turnover"][1]
    ):
        metric_note = f"通过顾问级门槛（Sharpe≥{th['sharpe']:.2f}, Fitness≥{th['fitness']:.2f}）"
    elif turnover is not None and turnover > th["turnover"][1]:
        metric_note = "换手偏高，需增大 decay 或混合稳定信号"
    elif fitness < th["fitness"]:
        metric_note = f"Fitness 未达 {th['fitness']:.2f}，通常是换手或信号强度问题"
    else:
        metric_note = "指标一般，需继续优化"

    if not top_corr:
        corr_note = "暂无 ACTIVE alpha 可比相关"
    elif abs(top_corr[0]["corr"]) >= 0.7:
        corr_note = f"与 {top_corr[0]['alpha_id']} 高度相关 ({top_corr[0]['corr']:.2f})，需换信号簇"
    elif abs(top_corr[0]["corr"]) >= 0.5:
        corr_note = f"与 {top_corr[0]['alpha_id']} 中等相关 ({top_corr[0]['corr']:.2f})，谨慎提交"
    else:
        corr_note = f"与现有 ACTIVE alpha 低相关 ({top_corr[0]['corr']:.2f})，分散价值较高"

    return f"{family} 簇：{metric_note}；{corr_note}"


def truncate_expr(expr: str, max_len: int = 120) -> str:
    expr = expr or ""
    lines = expr.strip().splitlines()
    first = lines[0].strip() if lines else ""
    if len(first) > max_len:
        first = first[: max_len - 3] + "..."
    return first


def build_bulk_summary(alphas: list[dict], active_correlations: dict[str, list[dict[str, Any]]]) -> str:
    """Build a compact summary for the first (bulk) run."""
    from collections import Counter

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(alphas)
    active = [a for a in alphas if a.get("status") == "ACTIVE"]
    unsubmitted = [a for a in alphas if a.get("status") != "ACTIVE"]
    families = Counter(classify_alpha((a.get("regular") or {}).get("code", "")) for a in alphas)

    top_active = sorted(
        active, key=lambda a: (a.get("is") or {}).get("fitness") or 0, reverse=True
    )[:5]
    failures = [
        a for a in alphas
        if (a.get("is") or {}).get("fitness") is not None and (a.get("is") or {}).get("fitness") < 0.5
    ]
    high_to = [
        a for a in alphas
        if (a.get("is") or {}).get("turnover") is not None and (a.get("is") or {}).get("turnover") > 0.50
    ]

    lines = [
        f"\n### {now} — 批量初始化快照\n",
        f"- 总 alpha：{total} | ACTIVE：{len(active)} | 非 ACTIVE：{len(unsubmitted)}",
        f"- 信号簇分布：{dict(families.most_common(8))}",
        "",
        "**ACTIVE 高 Fitness Top 5**：",
    ]
    for a in top_active:
        is_ = a.get("is") or {}
        expr = truncate_expr((a.get("regular") or {}).get("code", ""))
        sharpe = is_.get("sharpe")
        fitness = is_.get("fitness")
        turnover = is_.get("turnover")
        lines.append(
            f"- `{a['id']}` ({classify_alpha((a.get('regular') or {}).get('code', ''))}): "
            f"Sharpe={sharpe:.2f}, Fitness={fitness:.2f}, TO={turnover:.3f} — `{expr}`"
            if None not in (sharpe, fitness, turnover)
            else f"- `{a['id']}`: 指标缺失 — `{expr}`"
        )

    if active_correlations:
        high_corr_pairs = []
        ids = sorted(active_correlations.keys())
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                corr = next((c["corr"] for c in active_correlations[a] if c["alpha_id"] == b), None)
                if corr is None:
                    corr = next((c["corr"] for c in active_correlations[b] if c["alpha_id"] == a), 0.0)
                if abs(corr) >= 0.7:
                    high_corr_pairs.append((a, b, corr))
        if high_corr_pairs:
            lines.extend(["", "**ACTIVE 中日收益高相关对（≥ 0.7）**："])
            for a, b, c in high_corr_pairs[:10]:
                lines.append(f"- `{a}` vs `{b}`: {c:.3f}")
        else:
            lines.extend(["", "**ACTIVE 中日收益高相关对**：无 ≥ 0.7 的对（或 PnL 不足）"])

    if failures:
        lines.extend(["", f"**明显失效信号（Fitness < 0.5，共 {len(failures)} 个）**："])
        families_fail = Counter(classify_alpha((a.get("regular") or {}).get("code", "")) for a in failures)
        lines.append(f"- 簇分布：{dict(families_fail.most_common(5))}")

    if high_to:
        lines.extend(["", f"**高换手（TO > 50%，共 {len(high_to)} 个）**："])
        families_to = Counter(classify_alpha((a.get("regular") or {}).get("code", "")) for a in high_to)
        lines.append(f"- 簇分布：{dict(families_to.most_common(5))}")

    lines.append("\n---\n")
    return "\n".join(lines)


def build_incremental_report(entries: list[dict[str, Any]]) -> str:
    """Build per-alpha markdown for incremental updates."""
    if not entries:
        return ""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"\n### {now}\n"]
    for e in entries:
        if e.get("event") == "status_or_metric_changed":
            lines.append(
                f"- **{e['alpha_id']}** 状态变化：{e['old_status']} → {e['new_status']}；"
                f"Sharpe={e['sharpe']}, Fitness={e['fitness']}, TO={e['turnover']}。{e['lesson']}"
            )
        else:
            lines.append(
                f"- **{e['alpha_id']}** ({e['status']}, {e['family']}): "
                f"Sharpe={e['sharpe']}, Fitness={e['fitness']}, TO={e['turnover']}, DD={e['drawdown']}。"
                f"{e['lesson']}"
            )
            if e["top_corr"]:
                corr_strs = [f"{c['alpha_id']}({c['corr']:+.2f})" for c in e["top_corr"]]
                lines.append(f"  - 相关：{', '.join(corr_strs)}")
            expr = truncate_expr(e["expression"])
            if expr:
                lines.append(f"  - 表达式：`{expr}`")
    lines.append("\n---\n")
    return "\n".join(lines)


def append_to_skill(snippet: str) -> None:
    """Append snippet to the end of SKILL.md (Section 12 is the last section)."""
    if not SKILL_PATH.exists():
        raise FileNotFoundError(f"SKILL.md not found at {SKILL_PATH}")
    content = SKILL_PATH.read_text(encoding="utf-8")
    marker = "## 12. 实证记录（自动更新）"
    if marker not in content:
        content += f"\n\n{marker}\n\n{snippet}"
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += snippet + "\n"
    SKILL_PATH.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evolve WQ Alpha Research SKILL with new empirical data."
    )
    parser.add_argument("--apply", action="store_true", help="Append the snippet to SKILL.md")
    parser.add_argument(
        "--max-pnl-fetch",
        type=int,
        default=60,
        help="最多为多少个 alpha 拉取 PnL 做相关性（默认 60，按创建时间倒序取最近的）",
    )
    args = parser.parse_args()

    brain = BrainSession(credential_file=str(CREDENTIAL_PATH))
    brain.authenticate()
    print(
        f"auth ok | user={brain.user_id} | consultant={brain.is_consultant} | "
        f"每日额度剩余={brain.remaining_simulations}",
        flush=True,
    )
    thresholds = brain.thresholds(1)

    db = load_alpha_db()
    known_ids = set(db.get("alphas", {}).keys())
    is_first_run = len(known_ids) == 0

    all_alphas = brain.alphas()
    print(f"fetched {len(all_alphas)} alphas, known={len(known_ids)}", flush=True)

    new_alphas: list[dict] = []
    changed_alphas: list[tuple[dict, dict]] = []

    for alpha in all_alphas:
        aid = alpha.get("id")
        if not aid:
            continue
        fp = compute_alpha_fingerprint(alpha)

        if aid not in known_ids:
            new_alphas.append(alpha)
        else:
            old = db["alphas"][aid]
            if old.get("status") != fp["status"] or old.get("sharpe") != fp["sharpe"]:
                changed_alphas.append((old, {**fp, "alpha_id": aid}))

    # ------------------------------------------------------------------
    # Preview mode: compute snippet without mutating DB
    # ------------------------------------------------------------------
    if is_first_run:
        print("first run: building bulk snapshot...", flush=True)
        active_alphas = [a for a in all_alphas if a.get("status") == "ACTIVE"]
        active_correlations: dict[str, list[dict[str, Any]]] = {}

        preview_db: dict[str, Any] = {"alphas": {}}
        # 仅对 ACTIVE 与最近的新 alpha 拉 PnL，避免 500+ 次串行请求
        pnl_targets = {a.get("id") for a in active_alphas}
        pnl_targets |= {a.get("id") for a in new_alphas[: args.max_pnl_fetch]}
        pnl_targets.discard(None)

        for idx, alpha in enumerate(all_alphas):
            aid = alpha.get("id")
            fp = compute_alpha_fingerprint(alpha)
            pnl = fetch_pnl(brain, aid) if aid in pnl_targets else []
            preview_db["alphas"][aid] = {**fp, "pnl": pnl}
            if idx % 20 == 0:
                print(f"  scanned {idx + 1}/{len(all_alphas)}", flush=True)

        active_ids = [a.get("id") for a in active_alphas if a.get("id")]
        for aid in active_ids:
            pnl = preview_db["alphas"][aid].get("pnl", [])
            active_correlations[aid] = correlation_with_existing(pnl, preview_db)

        snippet = build_bulk_summary(all_alphas, active_correlations)

        if args.apply:
            db["alphas"] = preview_db["alphas"]
    else:
        # ------------------------------------------------------------------
        # Incremental run: per-alpha entries for new/changed only
        # ------------------------------------------------------------------
        print(f"incremental: {len(new_alphas)} new, {len(changed_alphas)} changed", flush=True)
        entries: list[dict[str, Any]] = []

        # 新 alpha 可能成百上千，只对最近 N 个拉 PnL 做相关性，其余仅登记指标
        new_alphas.sort(key=lambda a: a.get("dateCreated") or "", reverse=True)
        for idx, alpha in enumerate(new_alphas):
            aid = alpha.get("id")
            fp = compute_alpha_fingerprint(alpha)
            pnl = fetch_pnl(brain, aid) if idx < args.max_pnl_fetch else []

            top_corr = correlation_with_existing(pnl, db)
            lesson = generate_lesson(fp, top_corr, thresholds)
            if not pnl:
                lesson += "（未拉取 PnL，相关性未评估）"
            entries.append(
                {
                    "alpha_id": aid,
                    "status": fp["status"],
                    "family": classify_alpha(fp["expression"]),
                    "sharpe": fp["sharpe"],
                    "fitness": fp["fitness"],
                    "turnover": fp["turnover"],
                    "drawdown": fp["drawdown"],
                    "expression": fp["expression"],
                    "top_corr": top_corr[:3],
                    "lesson": lesson,
                }
            )
            if args.apply:
                db["alphas"][aid] = {**fp, "pnl": pnl}
            print(f"  new: {aid} | sharpe={fp['sharpe']} | fitness={fp['fitness']} | to={fp['turnover']}")
            time.sleep(0.2)

        for old, new in changed_alphas:
            aid = new["alpha_id"]
            if aid in db["alphas"] and "pnl" in db["alphas"][aid]:
                new["pnl"] = db["alphas"][aid]["pnl"]
            entries.append(
                {
                    "alpha_id": aid,
                    "event": "status_or_metric_changed",
                    "old_status": old.get("status"),
                    "new_status": new["status"],
                    "sharpe": new["sharpe"],
                    "fitness": new["fitness"],
                    "turnover": new["turnover"],
                    "lesson": f"状态从 {old.get('status')} 变为 {new['status']}",
                }
            )
            if args.apply:
                db["alphas"][aid] = new
            print(f"  changed: {aid} | {old.get('status')} -> {new['status']}")

        snippet = build_incremental_report(entries)

    if not snippet.strip():
        print("\nNo new empirical findings to record.")
        return 0

    print("\n" + "=" * 60)
    print("PROPOSED SKILL.md APPEND SNIPPET")
    print("=" * 60)
    print(snippet)
    print("=" * 60)

    if args.apply:
        append_to_skill(snippet)
        db["last_update"] = datetime.now(timezone.utc).isoformat()
        db["version"] = 2
        save_alpha_db(db)
        print(f"\nAppended to {SKILL_PATH}")
        print(f"alpha_db.json updated: {len(db['alphas'])} alphas tracked.")
    else:
        print("\nDry-run: SKILL.md and alpha_db.json were NOT modified. Use --apply to commit.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
