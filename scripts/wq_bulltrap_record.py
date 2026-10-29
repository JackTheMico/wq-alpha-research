#!/usr/bin/env python3
"""把指定的 alpha 结果写入 alpha_db.json（skill 自进化的轻量入口）。

与 `evolve_skill.py` 的区别：这里只登记显式列出的 alpha_id，不做全库 diff。
PnL 存为 [[date, value], ...]，供按日期交集算相关。
"""
import datetime
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from wq_api import BrainSession  # noqa: E402

DB_PATH = SKILL_DIR / "alpha_db.json"

NEWS_PART = (
    "winsorize(-ts_backfill(news_max_up_ret,60) * "
    "abs(ts_regression(ts_backfill(news_pct_1min,60), ts_step(1), 5, rettype=2)),std = 4)"
)
FUND = "group_rank(ts_rank(operating_income/equity, 126), subindustry)"

EXPRESSIONS = {
    "j26np5Jj": f"0.3 * {NEWS_PART} + 0.7 * {FUND}",                      # V6
    "A1GnpxGl": f"0.3 * ts_decay_linear({NEWS_PART}, 5) + 0.7 * {FUND}",  # V10
}
SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 0, "neutralization": "INDUSTRY",
    "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY",
    "nanHandling": "ON", "maxTrade": "OFF", "maxPosition": "OFF",
    "language": "FASTEXPR", "visualization": False,
    "startDate": "2019-01-01", "endDate": "2023-12-31",
}


def main() -> int:
    brain = BrainSession()
    brain.authenticate()

    db = json.loads(DB_PATH.read_text(encoding="utf-8")) if DB_PATH.exists() else {"alphas": {}}
    db.setdefault("alphas", {})

    for aid, expr in EXPRESSIONS.items():
        a = brain.alpha(aid)
        is_ = a.get("is") or {}
        pnl = [[d, v] for d, v in brain.pnl_series(aid)]
        db["alphas"][aid] = {
            "status": a.get("status"),
            "expression": expr,
            "settings": a.get("settings") or SETTINGS,
            "sharpe": is_.get("sharpe"),
            "fitness": is_.get("fitness"),
            "returns": is_.get("returns"),
            "turnover": is_.get("turnover"),
            "drawdown": is_.get("drawdown"),
            "margin": is_.get("margin"),
            "long_count": is_.get("longCount"),
            "short_count": is_.get("shortCount"),
            "checks": {k: v.get("result") for k, v in brain.checks(a).items()},
            "pnl": pnl,
        }
        print(f"{aid}: status={a.get('status')} pnl_len={len(pnl)}", flush=True)

    db["last_update"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db["version"] = 2
    DB_PATH.write_text(json.dumps(db, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print("alpha_db.json updated, total alphas:", len(db["alphas"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
