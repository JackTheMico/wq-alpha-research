#!/usr/bin/env python3
"""数据源占用盘点（零仿真成本，只读 GET + 本地字段清单）。

目的：PROD_CORRELATION 无法本地预测，唯一能做的是**避开自己池子里已经用烂的数据源**，
往 ACTIVE 池完全没碰过的 dataset 上走。本脚本回答两件事：

  1. 我自己的 22 条 ACTIVE 用了哪些 dataset / 字段（拥挤度地图）
  2. 字段清单里哪些 dataset 是「我方零使用 + 覆盖度可用」的空白区，并列出其中的热门字段

用法：
    python scripts/datasource_scan.py                 # 默认：打印我方占用 + TOP 空白 dataset
    python scripts/datasource_scan.py --min-cov 0.3   # 覆盖度门槛
    python scripts/datasource_scan.py --show analyst  # 只看 dataset/subcategory 含关键字的字段
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from wq_api import BrainSession  # noqa: E402

FIELDS_JSON = REPO / "references" / "wq_usa_top3000_delay1_data_fields.json"
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def load_fields() -> list[dict]:
    return json.loads(FIELDS_JSON.read_text(encoding="utf-8"))


def tokens(code: str) -> set[str]:
    return set(TOKEN_RE.findall(code or ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-cov", type=float, default=0.30, help="覆盖度门槛")
    ap.add_argument("--min-user", type=int, default=1500, help="甜点区：全局 userCount 门槛")
    ap.add_argument("--show", default="", help="只看 dataset/subcategory 含该关键字的字段")
    ap.add_argument("--top", type=int, default=14)
    args = ap.parse_args()

    fields = load_fields()
    valid_ids = {f["id"] for f in fields}
    print(f"字段清单：{len(fields)} 个字段\n")

    brain = BrainSession(credential_file=str(REPO / "credential.txt"))
    brain.authenticate()
    actives = brain.alphas(status="ACTIVE", page_size=100)
    print(f"我方 ACTIVE：{len(actives)} 条\n")

    # ---- 1) 我方占用 ----
    used_fields: Counter[str] = Counter()
    used_ds: Counter[str] = Counter()
    per_alpha: list[tuple[str, str, list[str]]] = []
    for a in actives:
        code = (a.get("regular") or {}).get("code") or ""
        fs = sorted(tokens(code) & valid_ids)
        used_fields.update(fs)
        dss = {fld_of(fields, f) for f in fs}
        used_ds.update(d for d in dss if d)
        per_alpha.append((a.get("id", ""), str((a.get("is") or {}).get("sharpe")), fs))

    print("=== 1. 我方 ACTIVE 用到的 dataset（按字段次数）===")
    for ds, n in used_ds.most_common():
        print(f"  {ds:<34} {n:>3} 次")
    print("\n  高频字段（≥2 条 alpha 用过）：")
    for f, n in used_fields.most_common():
        if n >= 2:
            print(f"    {f:<44} {n}")

    # ---- 2) 空白 dataset ----
    by_ds: dict[str, list[dict]] = defaultdict(list)
    for f in fields:
        key = f"{f['category']['id']}/{f['dataset']['id']}"
        by_ds[key].append(f)

    blanks = []
    for key, fs in by_ds.items():
        good = [f for f in fs
                if (f.get("coverage") or 0) >= args.min_cov
                and f.get("type") == "MATRIX"]
        if not good:
            continue
        my_use = sum(used_fields.get(f["id"], 0) for f in fs)
        blanks.append({
            "key": key,
            "category": fs[0]["category"]["name"],
            "dataset": fs[0]["dataset"]["name"],
            "n_all": len(fs),
            "n_good": len(good),
            "my_use": my_use,
            "med_cov": sorted(f["coverage"] for f in good)[len(good) // 2],
            "max_user": max(f.get("userCount") or 0 for f in good),
            "top": sorted(good, key=lambda f: (f.get("userCount") or 0), reverse=True)[:6],
        })

    blanks.sort(key=lambda b: (b["my_use"], -b["max_user"], -b["n_good"]))
    print(f"\n=== 2. 空白 dataset（我方使用次数升序；coverage≥{args.min_cov}，仅 MATRIX）===")
    print(f"{'dataset':<38} {'我方用':>6} {'字段':>5} {'好字段':>6} {'中位cov':>8} {'最高user':>8}")
    print("-" * 78)
    for b in blanks[:args.top]:
        print(f"{b['key']:<38} {b['my_use']:>6} {b['n_all']:>5} {b['n_good']:>6} "
              f"{b['med_cov']:>8.2f} {b['max_user']:>8}")

    print("\n  TOP 空白 dataset 的代表字段：")
    for b in blanks[:6]:
        print(f"\n  [{b['key']}] {b['category']} / {b['dataset']}  我方使用={b['my_use']}")
        for f in b["top"]:
            print(f"    {f['id']:<46} cov={f['coverage']:<5} user={f.get('userCount')} "
                  f"| {(f.get('description') or '')[:60]}")

    # ---- 3) 甜点区：别人用得多（信号有效）+ 我方零使用（不撞自己的池）----
    print(f"\n=== 3. 甜点区：全局 userCount≥{args.min_user} 且我方零使用 ===")
    print("（第三轮反证：只挑『我方零使用』会选中全局也冷门的字段，那些多半本来就弱）")
    sweet = [f for f in fields
             if (f.get("userCount") or 0) >= args.min_user
             and (f.get("coverage") or 0) >= args.min_cov
             and f.get("type") == "MATRIX"
             and used_fields.get(f["id"], 0) == 0]
    by_ds2: dict[str, list[dict]] = defaultdict(list)
    for f in sweet:
        by_ds2[f"{f['category']['id']}/{f['dataset']['id']}"].append(f)
    print(f"{'dataset':<38} {'甜点字段数':>10}  {'最高user':>8}")
    print("-" * 62)
    for k, fs in sorted(by_ds2.items(), key=lambda kv: -len(kv[1]))[:args.top]:
        print(f"{k:<38} {len(fs):>10}  {max(x['userCount'] for x in fs):>8}")
    print("\n  甜点字段 TOP（按 userCount）：")
    for f in sorted(sweet, key=lambda f: -(f.get("userCount") or 0))[:24]:
        print(f"    {f['id']:<46} user={f.get('userCount'):<6} cov={f['coverage']:<5} "
              f"[{f['dataset']['id']}] {(f.get('description') or '')[:52]}")

    if args.show:
        kw = args.show.lower()
        print(f"\n=== 3. 字段筛选：dataset/subcategory 含 '{kw}' ===")
        hits = [f for f in fields
                if kw in f"{f['dataset']['id']} {f['dataset']['name']} "
                        f"{f['subcategory']['id']} {f['subcategory']['name']}".lower()
                and (f.get("coverage") or 0) >= args.min_cov
                and f.get("type") == "MATRIX"]
        hits.sort(key=lambda f: -(f.get("userCount") or 0))
        for f in hits[:30]:
            print(f"  {f['id']:<46} cov={f['coverage']:<5} user={f.get('userCount'):<5} "
                  f"我方={used_fields.get(f['id'], 0)} | {(f.get('description') or '')[:58]}")
        print(f"  （共 {len(hits)} 个）")
    return 0


def fld_of(fields: list[dict], fid: str) -> str:
    for f in fields:
        if f["id"] == fid:
            return f"{f['category']['id']}/{f['dataset']['id']}"
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
