"""提交前检查：候选 alpha 与所有 ACTIVE alpha 的日收益相关性。

改进点（相对旧版）：
  * ACTIVE 列表走服务端 `status=ACTIVE` 过滤，不再拉全量 500+ 再本地筛；
  * 相关按**日期交集**对齐，不再要求两条 PnL 长度完全相等；
  * 记录集读取遵循 `Retry-After`。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, aligned_corr, to_returns  # noqa: E402

NEW_ALPHA_ID = "KPGLLpPE"


def main() -> int:
    brain = BrainSession()
    brain.authenticate()
    print("认证成功", flush=True)

    new_ret = to_returns(brain.pnl_series(NEW_ALPHA_ID))
    print(f"候选 {NEW_ALPHA_ID} 日收益点数: {len(new_ret)}")
    if len(new_ret) < 30:
        print("PnL 数据不足，无法比较")
        return 1

    active = brain.alphas(status="ACTIVE")
    print(f"ACTIVE alphas: {len(active)}")

    pairs = []
    for a in active:
        aid = a.get("id")
        if not aid or aid == NEW_ALPHA_ID:
            continue
        corr = aligned_corr(new_ret, to_returns(brain.pnl_series(aid)))
        if corr is None:
            print(f"  {aid}: PnL 不可用/日期无交集，跳过")
            continue
        pairs.append((aid, corr))
        tag = " ❌ HIGH" if abs(corr) >= 0.7 else (" ⚠️" if abs(corr) >= 0.5 else "")
        print(f"  {aid}: corr={corr:+.3f}{tag}")

    pairs.sort(key=lambda x: abs(x[1]), reverse=True)
    high = [(a, c) for a, c in pairs if abs(c) >= 0.7]
    mid = [(a, c) for a, c in pairs if 0.5 <= abs(c) < 0.7]
    print(f"\n最高相关: {pairs[0] if pairs else 'n/a'}")
    if high:
        print(f"⚠️ {len(high)} 个日收益相关 ≥0.7：{high}")
        print("   → 放弃或重构；除非新 Sharpe ≥ 冲突因子 × 1.1")
    elif mid:
        print(f"⚠️ 有 {len(mid)} 个在 0.5–0.7 区间，谨慎提交：{mid}")
    else:
        print("✅ 无 ≥0.5 相关")
    print("提醒：日收益相关只是 proxy，WQ 用信号级相关，提交前仍需信号成分重叠护栏。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
