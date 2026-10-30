#!/usr/bin/env python3
"""提交前复核 + 提交 + 轮询确认（不写入任何新仿真，零仿真额度消耗）。

用法：
    python scripts/submit_one.py <alpha_id>            # 只复核，不提交
    python scripts/submit_one.py <alpha_id> --do-submit # 复核通过后提交并轮询

复核内容包括：
  1. status 必须是 UNSUBMITTED（避免重复提交）
  2. gate_report 全部通过
  3. 打印 SELF/PROD/POWER_POOL 相关性的当前值（提交前通常为 PENDING）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, submit_verified  # noqa: E402


def review(brain: BrainSession, alpha_id: str) -> tuple[bool, dict]:
    alpha = brain.alpha(alpha_id)
    st = alpha.get("status")
    print(f"alpha      : {alpha_id}")
    print(f"status     : {st}")
    print(f"dateSubm   : {alpha.get('dateSubmitted')}")
    s = alpha.get("settings") or {}
    print(f"settings   : region={s.get('region')} universe={s.get('universe')} "
          f"delay={s.get('delay')} decay={s.get('decay')} "
          f"neutral={s.get('neutralization')} trunc={s.get('truncation')}")
    print(f"expression :")
    for line in (alpha.get("regular") or {}).get("code", "").splitlines():
        print("    " + line)

    is_ = alpha.get("is") or {}
    print(f"metrics    : sharpe={is_.get('sharpe')} fitness={is_.get('fitness')} "
          f"returns={is_.get('returns')} turnover={is_.get('turnover')} "
          f"drawdown={is_.get('drawdown')} margin={is_.get('margin')}")

    ok, msgs = brain.gate_report(alpha)
    print(f"gate       : {'PASS' if ok else 'FAIL'}")
    for m in msgs:
        print(f"    - {m}")

    print("checks     :")
    for name, c in sorted(brain.checks(alpha).items()):
        print(f"    {name:<26} {c.get('result'):<8} value={c.get('value')} limit={c.get('limit')}")

    print(f"corr       : self={brain.self_correlation(alpha)} "
          f"prod={brain.prod_correlation(alpha)} "
          f"powerpool={(is_.get('powerPoolCorrelation'))}")

    if st != "UNSUBMITTED":
        ok = False
        print(f"!! status={st}，不是 UNSUBMITTED，拒绝提交")
    return ok, alpha


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("alpha_id")
    ap.add_argument("--do-submit", action="store_true", help="复核通过后真正提交")
    ap.add_argument("--polls", type=int, default=24)
    ap.add_argument("--interval", type=float, default=10.0)
    args = ap.parse_args()

    brain = BrainSession(credential_file=str(Path(__file__).resolve().parent.parent / "credential.txt"))
    brain.authenticate()
    print(f"认证成功：consultant={brain.is_consultant}\n", flush=True)
    ok, _ = review(brain, args.alpha_id)
    if not ok:
        print("\n>>> 复核未通过，未提交。")
        return 1
    if not args.do_submit:
        print("\n>>> 复核通过。加 --do-submit 才会真正提交。")
        return 0

    print("\n>>> 提交中 ...")
    outcome = submit_verified(brain, args.alpha_id, polls=args.polls, interval=args.interval)
    print(f">>> 结果: {outcome}")

    alpha = brain.alpha(args.alpha_id)
    print("\n--- 提交后状态 ---")
    print(f"status     : {alpha.get('status')}")
    print(f"dateSubm   : {alpha.get('dateSubmitted')}")
    is_ = alpha.get("is") or {}
    print(f"corr       : self={brain.self_correlation(alpha)} prod={brain.prod_correlation(alpha)}")
    for name, c in sorted(brain.checks(alpha).items()):
        if c.get("result") in ("FAIL", "ERROR"):
            print(f"    FAIL {name}: value={c.get('value')} limit={c.get('limit')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
