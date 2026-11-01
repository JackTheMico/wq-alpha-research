#!/usr/bin/env python3
"""搜索低 alphaCount 但有经济学意义的字段，用于 F1c 模板。

1. 从本地 USA TOP3000 delay=1 字段快照中筛选
2. 从 BRAIN API 拉 GLB TOP3000 delay=1 字段（新数据集）
3. 输出候选字段清单（低 alphaCount + 高覆盖 + 清晰经济学意义）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession  # noqa: E402

FIELDS_JSON = Path(__file__).resolve().parent.parent / "references" / "fields_usa_top3000_delay1.json"


def search_usa_fields():
    """从本地 USA 字段快照筛选低 alphaCount 候选。"""
    data = json.loads(FIELDS_JSON.read_text(encoding="utf-8"))

    # 筛选条件
    # - coverage >= 0.7（覆盖率够高）
    # - alphaCount 尽量低（< 200 算冷门，< 50 算超冷门）
    # - 不是太老的数据集（排除 fundamental6 / analyst4 等已饱和）
    saturated_datasets = {
        "fundamental6", "analyst4", "pv1", "model77", "option8", "model110",
    }

    candidates = []
    for f in data:
        cov = f.get("coverage", 0) or 0
        alpha_count = f.get("alphaCount", 0) or 0
        dataset_id = (f.get("dataset") or {}).get("id", "")
        cat_id = (f.get("category") or {}).get("id", "")

        if cov < 0.7:
            continue
        if dataset_id in saturated_datasets:
            continue
        if alpha_count > 500:
            continue

        candidates.append({
            "id": f["id"],
            "dataset": dataset_id,
            "category": cat_id,
            "coverage": cov,
            "alphaCount": alpha_count,
            "userCount": f.get("userCount", 0),
            "description": (f.get("description") or "")[:100],
        })

    # 按 alphaCount 升序
    candidates.sort(key=lambda x: x["alphaCount"])
    return candidates


def search_glb_fields(brain: BrainSession):
    """从 BRAIN API 拉 GLB TOP3000 字段，找低 alphaCount 的。"""
    results = []
    # 按 dataset 逐个拉，避免 search= 返回无关结果
    datasets_to_check = [
        "fundamental17", "fundamental23", "analyst14", "analyst69",
        "model26", "model38", "risk70", "risk87",
        "ai_funda_synth", "ai_funda_llm", "global_sl_pred",
        "news95", "news13", "institutions22", "fundamental90",
        "analyst90", "analyst91", "analyst92",
        "crowding_scores", "model266", "cyber_risk_ratings",
        "option2", "insider_agg_matrix",
    ]

    for ds in datasets_to_check:
        try:
            r = brain.http.get(
                "https://api.worldquantbrain.com/data-fields",
                params={
                    "region": "GLB", "delay": 1, "universe": "TOP3000",
                    "dataset.id": ds, "limit": 30, "order": "alphaCount",
                },
                timeout=15,
            )
            if r.status_code != 200:
                continue
            items = r.json().get("results", [])
            for item in items[:15]:  # 每个 dataset 取 alphaCount 最低的 15 个
                results.append({
                    "id": item["id"],
                    "dataset": ds,
                    "coverage": item.get("coverage", 0),
                    "alphaCount": item.get("alphaCount", 0),
                    "userCount": item.get("userCount", 0),
                    "description": (item.get("description") or "")[:100],
                })
        except Exception as e:
            print(f"  [WARN] {ds}: {e}")
            continue

    results.sort(key=lambda x: x["alphaCount"])
    return results


def main():
    brain = BrainSession()
    brain.authenticate()
    print(f"账号: {brain.user_id}, 权限: {brain.permissions}\n")

    # === USA 字段 ===
    print("=" * 60)
    print("USA TOP3000 delay=1 低 alphaCount 字段候选")
    print("=" * 60)
    usa = search_usa_fields()
    print(f"共 {len(usa)} 个候选\n")

    # 按类别分组展示
    from collections import defaultdict
    by_cat = defaultdict(list)
    for f in usa:
        by_cat[f["category"]].append(f)

    for cat in sorted(by_cat.keys()):
        fields = by_cat[cat][:8]  # 每类最多 8 个
        print(f"\n--- {cat} ({len(by_cat[cat])} total) ---")
        for f in fields:
            print(f"  {f['id']:<55s} cov={f['coverage']:.2f}  alpha={f['alphaCount']:<5d}  ds={f['dataset']}")

    # === GLB 字段 ===
    print("\n" + "=" * 60)
    print("GLB TOP3000 delay=1 低 alphaCount 字段候选（API 实时拉取）")
    print("=" * 60)
    glb = search_glb_fields(brain)
    print(f"共 {len(glb)} 个候选\n")

    # 只展示 alphaCount < 100 的
    for f in glb:
        if f["alphaCount"] < 100 and f["coverage"] >= 0.5:
            print(f"  {f['id']:<55s} cov={f['coverage']:.2f}  alpha={f['alphaCount']:<5d}  ds={f['dataset']:<20s}  users={f['userCount']}")

    # 保存完整结果
    out = {
        "usa": usa[:80],  # 前 80 个
        "glb": [f for f in glb if f["coverage"] >= 0.5][:80],
    }
    out_path = Path(__file__).resolve().parent.parent / "low_alpha_fields.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n完整结果已保存到 {out_path}")

    # === 检查 ts_decay_exp_window 算子权限 ===
    print("\n" + "=" * 60)
    print("算子权限检查")
    print("=" * 60)
    test_exprs = [
        ("ts_decay_exp_window", "ts_decay_exp_window(close, 5, factor=0.6)"),
        ("vector_neut + ts_arg_min", "vector_neut(rank(close), rank(ts_delta(close, 1)))"),
        ("ts_arg_min + ts_backfill", "rank(ts_arg_min(ts_backfill(close, 60), 120))"),
        ("简化版（无 decay_exp）", "vector_neut(rank(ts_arg_min(ts_backfill(close, 60), 120)), rank(ts_delta(close, 1)))"),
    ]
    for name, expr in test_exprs:
        payload = {
            "type": "REGULAR",
            "settings": {
                "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
                "delay": 1, "decay": 0, "neutralization": "SUBINDUSTRY",
                "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY",
                "nanHandling": "ON", "language": "FASTEXPR", "visualization": False,
                "simulationMode": "QUICK",
            },
            "regular": expr,
        }
        r = brain.http.post("https://api.worldquantbrain.com/simulations", json=payload, timeout=30)
        icon = "✅" if r.status_code == 201 else "❌"
        detail = ""
        if r.status_code != 201:
            detail = r.text[:200].replace("\n", " ")
        print(f"  {icon} {name:<30s} HTTP {r.status_code} {detail}")


if __name__ == "__main__":
    main()
