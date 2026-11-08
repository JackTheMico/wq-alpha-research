#!/usr/bin/env python3
"""结论账本查询：选族/选字段前先问「这个试过没、结论是什么」。

用法：
    python redflag.py eps_flag                 # 关键词模糊匹配 region/dataset/field/expr
    python redflag.py --region IND --open      # 只看 IND 还没关闭的族
    python redflag.py --dataset fundamental28  # 精确看某个 dataset 的所有记录

只在 references/ledger.md 上做只读解析，无依赖、不联网。
若命中的族状态是 CLOSED / BLOCKED，退出码为 1 —— 提醒不要再烧仿真。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "references" / "ledger.md"
BAD = {"CLOSED", "BLOCKED"}


def _clean(cell: str) -> str:
    return cell.strip().replace("**", "").replace("`", "")


def rows(path: Path = LEDGER) -> list[dict]:
    """解析 ledger.md 的两张表（族级 / 字段级）。"""
    out, section, header = [], "", None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section, header = line[3:].strip(), None
            continue
        if not line.startswith("|"):
            header = None
            continue
        cells = [_clean(c) for c in line.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue
        if header is None:
            header = cells
            continue
        rec = dict(zip(header, cells))
        rec["_section"] = section
        out.append(rec)
    return out


def match(rec: dict, kw: str) -> bool:
    hay = " ".join(rec.values()).lower()
    return kw.lower() in hay


def fmt(rec: dict) -> str:
    if rec.get("_section", "").startswith("1"):
        return (f"[族] {rec.get('region','')}/{rec.get('dataset','')}  "
                f"status={rec.get('status','')}  best_S={rec.get('最优单腿 S','')}  "
                f"卡点={rec.get('卡在哪','')}  证据={rec.get('证据','')}")
    return (f"[字段] {rec.get('region','')}/{rec.get('dataset','')}  {rec.get('field / expr','')}"
            f"\n        S={rec.get('S','')}  checks={rec.get('checks','')}  "
            f"status={rec.get('status','')}  {rec.get('§','')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="查 ledger：这个字段/族试过没")
    ap.add_argument("keyword", nargs="*", help="关键词（模糊匹配任意列）")
    ap.add_argument("--region", help="IND / AMR / USA …")
    ap.add_argument("--dataset", help="精确 dataset id")
    ap.add_argument("--open", action="store_true", help="只列未关闭的族")
    a = ap.parse_args()

    rs = rows()
    hit = []
    for r in rs:
        if a.region and r.get("region") != a.region:
            continue
        if a.dataset and r.get("dataset") != a.dataset:
            continue
        if a.keyword and not all(match(r, k) for k in a.keyword):
            continue
        hit.append(r)

    if a.open:
        hit = [r for r in hit if r.get("_section", "").startswith("1")
               and r.get("status") not in BAD and r.get("status") != "ACTIVE"]

    if not hit:
        print("未命中：ledger 里没有这个字段/族的记录 → 可能是新族，可以扫（先单腿 batch_size<=2）")
        return 0

    for r in hit:
        print(fmt(r))

    bad = [r for r in hit if r.get("status") in BAD]
    if bad:
        print(f"\n⚠️  命中 {len(bad)} 条 CLOSED/BLOCKED —— 不要重烧，除非有新骨架或新中性化维度")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
