"""批量回测 / 提交工具（多仿真 + hash 去重 + 顾问级门槛）。

替代此前每个 `wq_*_opt*.py` 中各自复制一份的 simulate() 样板代码。

用法
----
    # 1) 快速验证单个表达式
    python scripts/simulate_batch.py --expr "group_rank(ts_rank(operating_income/equity,126),subindustry)"

    # 2) 跑一个变体文件（JSON：{"名称": "表达式"} 或 {"名称": {"expression":..., "decay":...}}）
    python scripts/simulate_batch.py --file variants.json --batch-size 8

    # 3) 只模拟不提交（默认）；加 --submit 把通过门槛且相关性安全的 alpha 提交
    python scripts/simulate_batch.py --file variants.json --submit

    # 4) 只看默认设置、不真正跑
    python scripts/simulate_batch.py --file variants.json --dry-run

设计要点（对齐 2026-09 文档）
--------------------------
* 多仿真一批 2..10 个，同批 `type/region/delay/language/instrumentType` 必须一致；
* 轮询由 `Retry-After` 驱动；
* `--cache` 默认开启（simulation_cache.jsonl），重复配置直接复用 alpha_id，不烧额度；
* 提交前先用本地门槛（顾问级 Sharpe>1.58 / Fitness>1.0 / TO 1%–70%）筛一遍；
* 提交后必须二次确认 `status == ACTIVE`（201 不等于上线）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import (  # noqa: E402
    BrainSession,
    DEFAULT_SETTINGS,
    SimulationCache,
    build_payload,
    submit_verified,
)
from static_check import run_static_check  # noqa: E402
from field_snapshot import load_snapshot, snapshot_exists  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ACTIVE_CACHE_PATH = SKILL_DIR / ".active_fields_cache.json"
ACTIVE_CACHE_TTL = 3600  # 1 小时


def load_variants(path: Path) -> list[tuple[str, dict]]:
    """读取变体文件，返回 [(名称, payload_kwargs)]。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[tuple[str, dict]] = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, str):
                items.append((f"v{i + 1}", {"expression": item}))
            else:
                name = item.get("name") or f"v{i + 1}"
                items.append((name, item))
    elif isinstance(data, dict):
        for name, spec in data.items():
            items.append((name, {"expression": spec} if isinstance(spec, str) else dict(spec)))
    else:
        raise SystemExit("变体文件格式错误：需为对象或数组")
    return items


def fmt_metrics(alpha: dict) -> str:
    is_ = alpha.get("is") or {}
    vals = [
        ("Sh", is_.get("sharpe")),
        ("Fit", is_.get("fitness")),
        ("TO", is_.get("turnover")),
        ("Ret", is_.get("returns")),
        ("DD", is_.get("drawdown")),
    ]
    parts = []
    for label, v in vals:
        if v is None:
            parts.append(f"{label}=n/a")
        elif label == "TO":
            parts.append(f"{label}={v:.1%}")
        else:
            parts.append(f"{label}={v:.2f}")
    return " ".join(parts)


def load_active_fields(brain: BrainSession, region: str) -> set[str]:
    """加载当前区域 ACTIVE 池已用字段（带 1 小时本地缓存）。"""
    import time as _time
    if ACTIVE_CACHE_PATH.exists():
        cache = json.loads(ACTIVE_CACHE_PATH.read_text(encoding="utf-8"))
        if cache.get("region") == region and (_time.time() - cache.get("ts", 0)) < ACTIVE_CACHE_TTL:
            return set(cache.get("fields", []))
    actives = brain.alphas(status="ACTIVE", page_size=100)
    valid_ids: set[str] = set()
    for a in actives:
        code = (a.get("regular") or {}).get("code") or ""
        valid_ids.update(__import__("re").findall(r"[A-Za-z_][A-Za-z0-9_]*", code))
    ACTIVE_CACHE_PATH.write_text(
        json.dumps({"region": region, "ts": _time.time(), "fields": sorted(valid_ids)}),
        encoding="utf-8",
    )
    return valid_ids


def print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("（无结果）")
        return
    w = max(len(str(r.get("name", "?"))) for r in rows)
    for r in rows:
        alpha = r.get("alpha") or {}
        flag = "✅" if r.get("gate_ok") else "❌"
        # alpha_id 可能为 None（仿真 ERROR/未完成），不能直接用于格式化，
        # 否则 TypeError 会让整个批次的结果在落盘前丢失。
        aid = str(r.get("alpha_id") or "-")
        print(f"{flag} {str(r.get('name', '?')):<{w}} {aid:<10} {fmt_metrics(alpha)}")
        if r.get("message"):
            print(f"     ! {str(r['message'])[:200]}")
        for msg in r.get("gate_msgs", []):
            print(f"     · {msg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="BRAIN 批量回测 / 提交")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--expr", help="单个表达式")
    src.add_argument("--file", help="变体 JSON 文件")
    ap.add_argument("--name", default="adhoc", help="--expr 时的名称")
    ap.add_argument("--batch-size", type=int, default=8, help="多仿真每批数量（2..10）")
    ap.add_argument("--decay", type=int, default=None)
    ap.add_argument("--neutralization", default=None)
    ap.add_argument("--region", default=None)
    ap.add_argument("--universe", default=None)
    ap.add_argument("--delay", type=int, default=None)
    ap.add_argument("--truncation", type=float, default=None)
    ap.add_argument("--nan-handling", default=None, choices=["ON", "OFF"])
    ap.add_argument("--quick", action="store_true", help="QUICK 模式（需 QUICK_MODE 权限，快但精度低）")
    ap.add_argument("--cache", default="simulation_cache.jsonl", help="去重缓存路径；传空串关闭")
    ap.add_argument("--submit", action="store_true", help="把通过本地门槛的 alpha 提交")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要提交的 payload")
    ap.add_argument("--out", default="batch_results.json", help="结果落盘路径")
    # 静态检查参数
    ap.add_argument("--field-rationale", default=None,
                    help='信号字段经济学解释，JSON 格式：{"字段名": "解释"}')
    ap.add_argument("--allow-crowded", action="store_true",
                    help="豁免字段拥挤度检查（alphaCount > 500 的信号字段）")
    ap.add_argument("--allow-unknown-field", action="store_true",
                    help="豁免快照外字段检查")
    ap.add_argument("--skip-static-check", action="store_true",
                    help="跳过静态检查（不推荐）")
    args = ap.parse_args()

    if args.file:
        items = load_variants(Path(args.file))
    elif args.expr:
        items = [(args.name, {"expression": args.expr})]
    else:
        ap.error("需要 --expr 或 --file")

    # 全局覆盖
    overrides: dict[str, Any] = {}
    for key, val in (
        ("decay", args.decay),
        ("neutralization", args.neutralization),
        ("region", args.region),
        ("universe", args.universe),
        ("delay", args.delay),
        ("truncation", args.truncation),
        ("nanHandling", args.nan_handling),
    ):
        if val is not None:
            overrides[key] = val
    if args.quick:
        overrides["simulationMode"] = "QUICK"

    payloads: list[tuple[str, dict]] = []
    for name, spec in items:
        spec = dict(spec)
        expr = spec.pop("expression")
        settings = dict(DEFAULT_SETTINGS)
        settings.update(overrides)
        per_variant = {k: spec.pop(k) for k in list(spec) if k in DEFAULT_SETTINGS or k in (
            "simulationMode", "testPeriod", "maxTrade", "maxPosition", "lookback",
        )}
        settings.update(per_variant)
        payloads.append((name, build_payload(expr, settings=settings)))

    # 确定区域/宇宙/延迟（用于静态检查）
    region = overrides.get("region", DEFAULT_SETTINGS["region"])
    universe = overrides.get("universe", DEFAULT_SETTINGS["universe"])
    delay = overrides.get("delay", DEFAULT_SETTINGS["delay"])

    if not args.skip_static_check:
        brain = BrainSession(credential_file=str(SKILL_DIR / "credential.txt"))
        brain.authenticate()
        print(
            f"user={brain.user_id} consultant={brain.is_consultant} "
            f"剩余额度={brain.remaining_simulations}"
        )

        # 加载字段快照
        if snapshot_exists(region, universe, delay):
            fields = load_snapshot(region, universe, delay, brain=brain)
            field_lookup = {f["id"]: f for f in fields}
        else:
            field_lookup = {}

        # 加载 ACTIVE 池
        active_fields = load_active_fields(brain, region)
        print(f"ACTIVE 池已用字段: {len(active_fields)} 个")

        # 解析 field-rationale
        field_rationale = {}
        if args.field_rationale:
            try:
                field_rationale = json.loads(args.field_rationale)
            except json.JSONDecodeError:
                ap.error("--field-rationale 必须是合法 JSON")

        # 对每个表达式做静态检查
        all_errors = []
        for name, payload in payloads:
            expr = payload.get("regular", "")
            errors = run_static_check(
                expr, field_lookup, active_fields,
                field_rationale=field_rationale if field_rationale else None,
                allow_crowded=args.allow_crowded,
                allow_unknown=args.allow_unknown_field,
            )
            if errors:
                all_errors.append((name, errors))

        if all_errors:
            print("\n❌ 静态检查未通过：")
            for name, errors in all_errors:
                print(f"\n  [{name}]")
                for e in errors:
                    print(f"    · {e}")
            print("\n请修复后重试，或加 --skip-static-check 跳过（不推荐）。")
            return 1
        print("✅ 静态检查通过")

    if args.dry_run:
        print(json.dumps([{"name": n, "payload": p} for n, p in payloads], indent=2, ensure_ascii=False))
        return 0

    if args.skip_static_check:
        brain = BrainSession(credential_file=str(SKILL_DIR / "credential.txt"))
        brain.authenticate()
        print(
            f"user={brain.user_id} consultant={brain.is_consultant} "
            f"剩余额度={brain.remaining_simulations}"
        )
    th = brain.thresholds(int(overrides.get("delay", DEFAULT_SETTINGS["delay"])))
    print(f"门槛（D{overrides.get('delay', DEFAULT_SETTINGS['delay'])}）: {th}")

    cache = SimulationCache(args.cache) if args.cache else None
    if cache and len(cache):
        print(f"去重缓存: {len(cache)} 条记录（{args.cache}）")

    results = []
    if cache:
        named_payloads = payloads
        fresh = [(n, p) for n, p in named_payloads if not cache.get(p)]
        cached = [(n, p) for n, p in named_payloads if cache.get(p)]
        for name, p in cached:
            aid = cache.get(p)
            print(f"命中缓存 {name} -> {aid}")
            results.append({"name": name, "payload": p, "alpha_id": aid, "cached": True})
        sim_results = brain.run_many([p for _, p in fresh], batch_size=args.batch_size, verbose=True)
        for (name, p), res in zip(fresh, sim_results):
            if res.alpha_id:
                cache.add(p, res.alpha_id)
            results.append(
                {
                    "name": name,
                    "payload": p,
                    "alpha_id": res.alpha_id,
                    "status": res.status,
                    "message": res.message,
                    "location": res.location,
                }
            )
    else:
        sim_results = brain.run_many([p for _, p in payloads], batch_size=args.batch_size, verbose=True)
        for (name, p), res in zip(payloads, sim_results):
            results.append(
                {
                    "name": name,
                    "payload": p,
                    "alpha_id": res.alpha_id,
                    "status": res.status,
                    "message": res.message,
                    "location": res.location,
                }
            )

    # 拉指标 + 门槛判定
    for row in results:
        aid = row.get("alpha_id")
        if not aid:
            continue
        alpha = brain.alpha(aid)
        ok, msgs = brain.gate_report(alpha)
        row.update({"alpha": alpha, "gate_ok": ok, "gate_msgs": msgs})

    # 先落盘再打印：打印环节若抛异常，成果不至于丢失。
    out_path = Path(args.out) if Path(args.out).is_absolute() else (SKILL_DIR / args.out)
    out_path.write_text(
        json.dumps(
            [
                {k: v for k, v in r.items() if k != "alpha"}
                | {"metrics": (r.get("alpha") or {}).get("is", {}), "expression": (r["payload"] or {}).get("regular")}
                for r in results
            ],
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"结果已写入 {out_path}")

    print("\n=== 结果 ===")
    print_table(results)
    print(f"\n剩余额度: {brain.remaining_simulations}（reset in {brain.rate_limit.get('reset')}s）")

    if args.submit:
        winners = [r for r in results if r.get("gate_ok") and r.get("alpha_id")]
        if not winners:
            print("\n没有通过门槛的候选，未提交。")
            return 0
        print(f"\n准备提交 {len(winners)} 个候选：")
        for r in winners:
            print(f"  {r['name']} -> {r['alpha_id']}")
        for r in winners:
            outcome = submit_verified(brain, r["alpha_id"])
            r["submit_result"] = outcome
            print(f"  {r['alpha_id']}: {outcome}")
            time.sleep(3)

    return 0


if __name__ == "__main__":
    sys.exit(main())
