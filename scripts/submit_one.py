#!/usr/bin/env python3
"""提交前复核 + 提交 + 轮询确认（不写入任何新仿真，零仿真额度消耗）。

用法：
    python scripts/submit_one.py <alpha_id>                       # 只复核，不提交
    python scripts/submit_one.py <alpha_id> --do-submit           # 复核通过后提交并轮询
    python scripts/submit_one.py <alpha_id> --do-submit --pool-size 12  # 候选池 ≥10 才可当天多次提交

每日提交配额（SKILL.md 硬性声明）：
  - 默认每个自然日（Asia/Shanghai）最多提交 1 条；
  - 仅当可提交候选池 ≥ 10 条时解除该限制（用 --pool-size 声明，且要求 ≥ 10）。

复核内容包括：
  1. 当日提交配额
  2. status 必须是 UNSUBMITTED（避免重复提交）
  3. gate_report 全部通过
  4. 打印 SELF/PROD/POWER_POOL 相关性的当前值（提交前通常为 PENDING）
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, submit_verified  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
DAILY_LIMIT = 1        # 每天最多提交 1 条
POOL_UNLOCK_SIZE = 10  # 可提交候选池达到两位数才解除限制


def today_submitted_count(brain: BrainSession) -> int | None:
    """统计当天（Asia/Shanghai）已提交的 alpha 条数；端点不可用时返回 None。

    账户 alpha 总数已过千，`/users/self/alphas` 不带 order 会 400
    （Cannot display more than the first 1,000 alphas），因此按 dateSubmitted 倒序取前 50 条。
    """
    today = datetime.now(TZ).date()
    try:
        rows = brain.request(
            "GET", "/users/self/alphas", params={"limit": 50, "order": "-dateSubmitted"}
        ).json().get("results", [])
    except Exception as exc:  # 集合端点可能 405/400（SKILL §7.7.2 坑三）
        print(f"!! 无法枚举 alpha（{exc}），无法统计当日配额")
        return None
    n = 0
    for a in rows:
        ds = a.get("dateSubmitted")
        if not ds:
            continue
        try:
            d = datetime.fromisoformat(ds.replace("Z", "+00:00")).astimezone(TZ).date()
        except ValueError:
            continue
        if d == today:
            n += 1
        elif d < today:
            break  # 已按时间倒序，遇到更早的日期即结束
    return n


def check_daily_quota(brain: BrainSession, pool_size: int) -> bool:
    """当日配额校验。返回 True 表示允许提交。"""
    used = today_submitted_count(brain)
    print(f"quota      : 今日已提交={used} / 每日上限={DAILY_LIMIT} （候选池={pool_size}）")
    if used is None:
        print("!! 当日已提交条数无法确认 → 默认拒绝提交（请先用 --pool-size 与人工核对）")
        return False
    if used < DAILY_LIMIT:
        return True
    if pool_size >= POOL_UNLOCK_SIZE:
        print(f"quota      : 候选池 {pool_size} ≥ {POOL_UNLOCK_SIZE}，解除每日 1 条限制")
        return True
    print(f"!! 今日已达 {DAILY_LIMIT} 条上限，且候选池 {pool_size} < {POOL_UNLOCK_SIZE}，拒绝提交")
    return False


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
    ap.add_argument("--max-posts", type=int, default=100, help="反复 POST submit 的上限（FAIL 约 1-3 次出判定，PASS 要 40-80 次转 ACTIVE）")
    ap.add_argument("--max-wait", type=float, default=300.0, help="等待判定书的总秒数")
    ap.add_argument("--pool-size", type=int, default=0,
                    help=f"可提交候选池大小；≥{POOL_UNLOCK_SIZE} 时解除每日 {DAILY_LIMIT} 条限制")
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
    if not check_daily_quota(brain, args.pool_size):
        print("\n>>> 当日配额不足，未提交（见 SKILL.md「提交需要显式授权，且每天最多 1 条」）。")
        return 2

    print("\n>>> 提交中 ...")
    outcome = submit_verified(
        brain, args.alpha_id, max_posts=args.max_posts, max_wait=args.max_wait, verbose=True
    )
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
