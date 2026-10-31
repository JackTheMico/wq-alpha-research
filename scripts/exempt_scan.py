"""零成本：拉取 ACTIVE alpha，按 IS Sharpe 排序，提取结构特征。

用于"豁免路径"选基：找出哪些信号结构能稳定出 2.0+ Sharpe，
作为 clone-and-push（新 Sharpe >= 1.1x 冲突 alpha）的基底。
不消耗任何仿真额度，纯读 API。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wq_api import BrainSession

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    b = BrainSession()
    b.authenticate()
    actives = b.alphas(status="ACTIVE")
    print(f"ACTIVE 总数: {len(actives)}")

    rows = []
    for a in actives:
        is_ = a.get("is") or {}
        s = is_.get("sharpe") or 0
        code = (a.get("regular") or {}).get("code", "") or ""
        st = a.get("settings") or {}
        rows.append({
            "id": a.get("id"),
            "sharpe": s,
            "fitness": is_.get("fitness") or 0,
            "turnover": is_.get("turnover") or 0,
            "returns": is_.get("returns") or 0,
            "drawdown": is_.get("drawdown") or 0,
            "decay": st.get("decay"),
            "neutralization": st.get("neutralization"),
            "truncation": st.get("truncation"),
            "nanHandling": st.get("nanHandling"),
            "code": code,
        })

    rows.sort(key=lambda r: r["sharpe"], reverse=True)

    print("\n=== 全部 ACTIVE 按 Sharpe 降序 ===")
    for r in rows:
        print(f"  {r['sharpe']:.2f} | F={r['fitness']:.2f} TO={r['turnover']*100:.1f}% "
              f"Ret={r['returns']*100:.1f}% DD={r['drawdown']*100:.1f}% | "
              f"decay={r['decay']} neut={r['neutralization']} trunc={r['truncation']} | {r['id']}")

    # 高 Sharpe（>=1.8）的完整表达式，供结构分析
    hi = [r for r in rows if r["sharpe"] >= 1.8]
    print(f"\n=== 高 Sharpe（>=1.8）共 {len(hi)} 条，完整表达式 ===")
    for r in hi:
        print(f"\n--- {r['id']}  S={r['sharpe']:.2f} F={r['fitness']:.2f} "
              f"TO={r['turnover']*100:.1f}% neut={r['neutralization']} decay={r['decay']} trunc={r['truncation']}")
        print(r["code"])

    # 落盘
    out = REPO / ".workbuddy" / "active_structures.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n完整数据已写入 {out}")


if __name__ == "__main__":
    main()
