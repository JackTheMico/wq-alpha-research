"""提交 B4（MPGx5EZk）并监控至 ACTIVE 或相关性检查定论。

提交 + 二次确认统一走 `wq_api.submit_verified`（201 只代表请求被接受，
必须等到 status == ACTIVE；SELF_CORRELATION / PROD_CORRELATION FAIL 即判死）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, submit_verified  # noqa: E402

ALPHA_ID = "KPGLLpPE"


def main() -> int:
    brain = BrainSession()
    brain.authenticate()
    print("认证成功", flush=True)

    alpha = brain.alpha(ALPHA_ID)
    is_ = alpha.get("is") or {}
    print(
        f"{ALPHA_ID} 当前 status={alpha.get('status')} "
        f"Sharpe={is_.get('sharpe')} Fitness={is_.get('fitness')} TO={is_.get('turnover')}"
    )
    ok, msgs = brain.gate_report(alpha)
    print("本地门槛:", "PASS" if ok else "FAIL")
    for m in msgs:
        print("  ·", m)
    if not ok:
        print("未通过本地门槛，放弃提交。")
        return 1

    outcome = submit_verified(brain, ALPHA_ID)
    print("提交结果:", outcome)
    return 0 if outcome == "ACTIVE" else 1


if __name__ == "__main__":
    sys.exit(main())
