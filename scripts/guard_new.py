"""对新候选 alpha 跑双层相关性护栏（对 14 个 ACTIVE）。

护栏 2（信号成分重叠）—— 便宜、先跑：候选核心信号若是某 ACTIVE 表达式的子串，
信号级相关≈0.9，SELF_CORRELATION 必 FAIL。
护栏 1（日收益相关）—— proxy，按日期交集对齐；<0.7 才安全，0.5~0.7 需新 Sharpe ≥ 冲突 ×1.1。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from wq_api import BrainSession, aligned_corr, to_returns  # noqa: E402


def _balanced_close(s: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def main_signal(expr: str) -> str:
    e = re.sub(r"\s+", " ", (expr or "")).strip()
    idx = e.find("group_rank(")
    if idx >= 0:
        k = e.find("(", idx)
        j = _balanced_close(e, k)
        if j > 0:
            return e[idx : j + 1]
    for fn in ("rank(", "ts_rank(", "ts_zscore(", "zscore("):
        idx = e.find(fn)
        if idx >= 0:
            k = e.find("(", idx)
            j = _balanced_close(e, k)
            if j > 0:
                return e[idx : j + 1]
    return e


def norm(e: str) -> str:
    return re.sub(r"\s+", "", (e or "")).lower()


def signal_overlap(cand: str, active: dict[str, str]) -> list[str]:
    """候选里任一 0.5 腿的核心信号 ⊂ 某 ACTIVE 表达式 → 命中。"""
    hits = []
    cn = norm(cand)
    # 取候选的全部 rank/group_rank 片段逐个比对
    frags = []
    for fn in ("group_rank(", "rank("):
        start = 0
        while True:
            i = cn.find(fn, start)
            if i < 0:
                break
            k = cn.find("(", i)
            j = _balanced_close(cn, k)
            if j < 0:
                break
            frags.append(cn[i : j + 1])
            start = j + 1
    for oid, oexpr in active.items():
        on = norm(oexpr)
        for fr in frags:
            if len(fr) > 20 and fr in on:
                hits.append((oid, fr[:70]))
                break
    return hits


def main() -> None:
    brain = BrainSession()
    brain.authenticate()

    cands = []
    for res_file in sorted((REPO / ".workbuddy").glob("opt_ivskew_results*.json")):
        cands.extend(json.loads(res_file.read_text(encoding="utf-8")))
    print(f"载入候选 {len(cands)} 条")

    act = {}
    offset = 0
    while True:
        d = brain.request("GET", "/users/self/alphas",
                          params={"status": "ACTIVE", "limit": 100, "offset": offset}).json()
        batch = d.get("results", [])
        act.update({a["id"]: a for a in batch})
        if len(batch) < 100:
            break
        offset += 100
    active_exprs = {k: (v.get("regular") or {}).get("code", "") for k, v in act.items()}
    print(f"ACTIVE 池: {len(active_exprs)}")

    for c in cands:
        if not c.get("alpha_id"):
            continue
        expr = c["expression"]
        s = c.get("sharpe") or 0
        ov = signal_overlap(expr, active_exprs)
        print(f"\n=== {c['name']}  {c['alpha_id']}  S={s:.3f} F={c.get('fitness')}")
        if ov:
            print("   ❌ 信号成分重叠（SELF_CORRELATION 将 FAIL）：")
            for oid, fr in ov:
                print(f"      vs {oid} (S={act[oid].get('is', {}).get('sharpe')}) 片段={fr}")
        else:
            print("   ✅ 无信号成分重叠")

    # ---- 护栏 1：日收益相关 ----
    print("\n\n===== 护栏 1：日收益相关（按日期交集）")
    act_ret = {}
    for aid in active_exprs:
        pnl = brain.pnl_series(aid)
        r = to_returns(pnl)
        if r:
            act_ret[aid] = r
    print(f"取到 {len(act_ret)} 条 ACTIVE 日收益序列")

    for c in cands:
        if not c.get("alpha_id"):
            continue
        nr = to_returns(brain.pnl_series(c["alpha_id"]))
        if not nr:
            print(f"{c['name']}: PnL 未就绪")
            continue
        cs = []
        for aid, orr in act_ret.items():
            v = aligned_corr(nr, orr)
            if v is not None:
                cs.append((abs(v), v, aid, act[aid].get("is", {}).get("sharpe") or 0))
        cs.sort(reverse=True)
        s = c.get("sharpe") or 0
        print(f"\n{c['name']} ({c['alpha_id']}) S={s:.3f}")
        for ab, v, aid, os_ in cs[:3]:
            need = os_ * 1.1
            verdict = "✅" if ab < 0.5 else ("⚠️需 S≥%.2f %s" % (need, "可" if s >= need else "不可") if ab < 0.7 else "❌")
            print(f"   {verdict} {aid} corr={v:+.3f} (冲突 S={os_:.2f}, 豁免需 ≥{need:.2f})")


if __name__ == "__main__":
    main()
