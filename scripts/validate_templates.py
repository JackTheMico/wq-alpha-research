#!/usr/bin/env python3
"""批量验证帖子 43499065604247 的 ARC/GLB 模板表达式语法。

用法：python validate_templates.py [--dry-run]
  --dry-run: 只生成 payload 不实际提交仿真（省额度）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wq_api import BrainSession, build_payload  # noqa: E402

# 帖子 43499065604247 提取的模板
# 占位符字段替换成实际字段用于语法检查
TEMPLATES = [
    {
        "id": "F1a",
        "name": "vector_neut/ts_arg_min 主模板",
        "expr": (
            "alpha = ts_decay_exp_window(\n"
            "    vector_neut(\n"
            "         rank( ts_arg_min( ts_backfill( close, 60 ), 120 ) ),\n"
            "         rank( ts_delta( ts_backfill( mdl26_market_cap_u, 2 ), 1 ) )\n"
            "    ),\n"
            "    5, factor = 0.7 );\n"
            "group_neutralize(\n"
            "    trade_when( rank( ts_std_dev( mdl26_market_cap_u, 60 ) ) > 0.3,\n"
            "                alpha, -1 ),\n"
            "    subindustry );"
        ),
        "notes": "成熟骨架，GLB 主流。但 ts_decay_exp_window 可能需要 Gold 权限",
    },
    {
        "id": "F1b",
        "name": "ts_rank/ts_arg_max 变体",
        "expr": (
            "alpha = ts_decay_exp_window(\n"
            "    vector_neut(\n"
            "         ts_rank( ts_arg_max( ts_backfill( close, 60 ), 120 ), 60 ),\n"
            "         rank( ts_delta( ts_backfill( mdl26_market_cap_l, 2 ), 1 ) )\n"
            "    ),\n"
            "    5, factor = 0.9 );\n"
            "group_neutralize( trade_when( rank( ts_std_dev( returns, 66 ) ) > 0.5, alpha, -1 ), industry );"
        ),
        "notes": "注意 mdl26_market_cap_l 字段是否存在",
    },
    {
        "id": "F1c",
        "name": "F1 简化版（省略外层 group_neutralize）",
        "expr": (
            "ts_decay_exp_window(\n"
            "    vector_neut(\n"
            "        rank( ts_arg_min( ts_backfill( close, 60 ), 120 ) ),\n"
            "        rank( ts_delta( ts_backfill( close, 2 ), 1 ) )\n"
            "    ),\n"
            "    5, factor = 0.6 )"
        ),
        "notes": "最小消融骨架，建议先在 F1c 上验证信号方向",
    },
    {
        "id": "F2",
        "name": "clamp/jump_decay 截面模板",
        "expr": (
            "a = clamp( -jump_decay( close, 120, sensitivity = 0.5, force = 0.1 ),\n"
            "            lower = -0.5, upper = 0.5 );\n"
            "group_vector_neut( rank( close ), rank( a ), subindustry )"
        ),
        "notes": "jump_decay/clamp/group_vector_neut 很多账号没权限",
    },
    {
        "id": "F3",
        "name": "残差回归管道",
        "expr": (
            "df = close;\n"
            "group_med = group_median( df, subindustry );\n"
            "resid = ts_regression( df, group_med, 500, lag = 0, rettype = 0 );\n"
            "resid_gpr = group_rank( resid, subindustry );\n"
            "alpha = vector_neut( resid_gpr,\n"
            "                  rank( ts_delta( ts_backfill( mdl26_market_cap_u, 2 ), 1 ) ) );\n"
            "group_neutralize( trade_when( rank( ts_std_dev( returns, 270 ) ) > 0.3,\n"
            "                  signed_power( alpha, 2 ), -1 ), industry )"
        ),
        "notes": "group_median 在很多账号算子清单里不存在。可换成 group_neutralize",
    },
    {
        "id": "F4",
        "name": "model110 多因子复合信号",
        "expr": (
            "a = ts_quantile( mdl110_score, 5120 )\n"
            "      * ts_rank( mdl110_analyst_sentiment, 60 )\n"
            "      * power( ts_arg_max( mdl110_quality, 1200 ), 3 );\n"
            "group_backfill( a, 90, 90 )"
        ),
        "notes": "三连乘建议逐件消融。model110 为特定数据集",
    },
    {
        "id": "F5",
        "name": "STAR 盈余惊喜排序器",
        "expr": (
            "a = ts_quantile( close, 252 )\n"
            "      * rank( close )\n"
            "      * rank( close );\n"
            "ts_backfill( a, 60 )"
        ),
        "notes": "rank(x)*rank(x) 是冗余的——同字段 rank 自乘不增加截面信息，建议删除一个",
    },
    {
        "id": "F6",
        "name": "rank/ts_rank 动量切换",
        "expr": (
            "alpha = rank( ts_rank( close, 242 ) );\n"
            "a = if_else( alpha > 0.5, 1, rank( -ts_delta( close, 2 ) ) );\n"
            "lastalpha = group_count( is_nan( a ), market ) > 40 ? a : nan;\n"
            "ts_backfill( lastalpha, 2 )"
        ),
        "notes": "group_count 很多账号没权限。用了三元运算符 ? : 需验证 FASTEXPR 是否支持",
    },
    {
        "id": "F7",
        "name": "ts_median vector_neut（ATOM 风格）",
        "expr": (
            "group_neutralize(\n"
            "    vector_neut( ts_median( close, 60 ), ts_median( close, 120 ) ),\n"
            "    close, COUNTRY )"
        ),
        "notes": "ts_median 很多账号没权限",
    },
    {
        "id": "F10",
        "name": "多步命名赋值构建",
        "expr": (
            "df = vec_avg( close );\n"
            "normalize( df, useStd = false, limit = 0.0 );\n"
            "pt = close;\n"
            "alpha = ts_decay_exp_window(\n"
            "            vector_neut(\n"
            "                rank( ts_arg_min( ts_backfill( df, 60 ), 122 ) ),\n"
            "                rank( ts_delta( ts_backfill( pt, 2 ), 1 ) ) ),\n"
            "            5, factor = 0.6 );\n"
            "group_neutralize( trade_when( rank( ts_std_dev( pt, 120 ) ) > 0.3, alpha, -1 ), subindustry )"
        ),
        "notes": "vec_avg(close) 对标量字段可能不行，normalize 算子也需验证",
    },
    # 评论区发现的额外模板
    {
        "id": "C1",
        "name": "评论：tm_16 + tema 双因子",
        "expr": (
            "rank( ts_zscore( close, 300 ) ) + rank( ts_zscore( close, 300 ) )"
        ),
        "notes": "评论区分享的模板，原字段是 tm_16_r1_r5_r10_rh_d1_r10_q1 + tcm_ta50_d1_tema，Sharpe 8.29/8.37。需验证 tm_16/tcm_ta50 数据集权限",
    },
    {
        "id": "C2",
        "name": "评论：简化版 vector_neut (无 decay_exp)",
        "expr": (
            "vector_neut( rank( close ), rank( ts_delta( ts_backfill( close, 2 ), 1 ) ) )"
        ),
        "notes": "从评论区权限讨论提取的可用简化版",
    },
]


def check_syntax(session: BrainSession, expr: str, settings_override: dict | None = None) -> dict:
    """提交一个 QUICK 仿真来验证表达式语法（不消耗 FULL 额度）。"""
    settings = {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "decay": 0,
        "neutralization": "SUBINDUSTRY",
        "truncation": 0.08,
        "pasteurization": "ON",
        "unitHandling": "VERIFY",
        "nanHandling": "ON",
        "language": "FASTEXPR",
        "visualization": False,
        "simulationMode": "QUICK",
    }
    if settings_override:
        settings.update(settings_override)

    # 合并多行表达式为单行
    one_line = " ".join(line.strip() for line in expr.split("\n") if line.strip())
    # 去掉末尾分号
    one_line = one_line.rstrip(";")

    payload = {
        "type": "REGULAR",
        "settings": settings,
        "regular": one_line,
    }

    try:
        resp = session.http.post(
            "https://api.worldquantbrain.com/simulations",
            json=payload,
            timeout=30,
        )
        status = resp.status_code
        if status == 201:
            # 语法通过，位置有资源号
            loc = resp.headers.get("Location", "")
            return {"ok": True, "status": status, "location": loc, "error": None}
        else:
            body = resp.text[:500]
            return {"ok": False, "status": status, "location": None, "error": body}
    except Exception as e:
        return {"ok": False, "status": 0, "location": None, "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印表达式不提交")
    ap.add_argument("--region", default="USA", choices=["USA", "GLB"])
    args = ap.parse_args()

    if args.dry_run:
        print("=== DRY RUN：只打印表达式，不提交仿真 ===\n")
        for t in TEMPLATES:
            print(f"[{t['id']}] {t['name']}")
            print(f"  {t['expr'][:120]}...")
            print(f"  备注: {t['notes']}")
            print()
        return

    brain = BrainSession()
    brain.authenticate()
    print(f"已认证 user={brain.user_id}, permissions={brain.permissions}\n")

    results = []
    for i, t in enumerate(TEMPLATES):
        print(f"[{i+1}/{len(TEMPLATES)}] 验证 {t['id']} {t['name']} ...")
        # GLB 用不同设置
        override = {"region": args.region} if args.region == "GLB" else None
        r = check_syntax(brain, t["expr"], override)
        results.append({"id": t["id"], "name": t["name"], **r, "notes": t["notes"]})

        icon = "✅" if r["ok"] else "❌"
        if r["ok"]:
            print(f"  {icon} 语法通过 (HTTP {r['status']})")
        else:
            # 尝试从错误信息中提取关键报错
            err = r.get("error", "")
            # 截断到关键部分
            short_err = err[:200].replace("\n", " ")
            print(f"  {icon} 语法错误 (HTTP {r['status']}): {short_err}")
        print()

    # 汇总
    print("\n" + "=" * 60)
    print("汇总：")
    ok_count = sum(1 for r in results if r["ok"])
    print(f"  通过: {ok_count}/{len(results)}")
    print(f"  失败: {len(results) - ok_count}/{len(results)}")

    print("\n失败详情：")
    for r in results:
        if not r["ok"]:
            print(f"  [{r['id']}] {r['name']}")
            err = r.get("error", "")[:300].replace("\n", " ")
            print(f"    HTTP {r['status']}: {err}")
            print(f"    备注: {r['notes']}")

    # 保存结果
    out = Path("template_validation_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n完整结果已保存到 {out.resolve()}")


if __name__ == "__main__":
    main()
