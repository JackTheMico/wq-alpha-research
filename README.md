# WQ Alpha Research Skill — 4 Days, Zero Human Intervention, From Zero to WorldQuant BRAIN Gold Medal 


<p align="center"><img src="pic/20260626094115.png" width="600"></p>


A self-evolving WorldQuant BRAIN alpha research skill. It helps agents design WQ Alpha expressions, search fields, diagnose simulation failures, check IS metrics, manage self-correlation, and turn each BRAIN interaction into reusable research rules.

The core idea is simple: do not let alpha research stay as scattered one-off prompts. Use the skill to build alphas, test them, inspect failures, compare daily-return correlations, and then distill the useful lessons back into `SKILL.md`.

This repository is a reusable agent skill, not a credential bundle. Keep all account credentials, raw alpha IDs, PnL records, and private candidate expressions local.

## Why This Skill Exists

WQ Alpha mining is not only about writing more expressions. The bottleneck is usually the research loop:

- finding usable fields fast enough;
- avoiding repeated low-Sharpe templates;
- controlling turnover before submission;
- checking SELF_CORRELATION against existing ACTIVE alphas;
- preserving lessons from failed simulations instead of rediscovering them later.

This skill packages that loop into an agent-readable playbook plus scripts. It gives the agent local field context, practical expression templates, IS failure diagnostics, submission checks, and a self-evolution mechanism for turning new runs into better future behavior.

## Mining Effect

The current playbook is built around USA TOP3000 delay=1 and includes a local snapshot of 4,367 BRAIN data fields. It has already distilled several practical mining rules:

- Fundamental fields are usually the strongest starting point; `group_rank + ts_rank` with `SUBINDUSTRY` neutralization is the default baseline.
- Analyst expectation fields are useful but need more turnover control, usually via modest decay and industry/subindustry neutralization.
- Pure technical signals fail more often unless decay is high or they are mixed with slower fundamental signals.
- Fitness failures are often turnover problems in disguise; decay and signal mixing are the first levers to check.
- Self-correlation must be measured on daily PnL changes, not cumulative PnL curves.
- Changing windows, weights, or neutralization rarely creates truly low-correlation alphas by itself; low correlation usually needs a different data source or economic logic.

The goal is not to promise a fixed Sharpe or submission pass rate. The value is a faster, cleaner alpha mining loop: fewer invalid-field attempts, less repeated correlation failure, better default templates, and a growing memory of what worked or failed.

## Pre-Submit Gate: Green Metrics Are Not Enough

The single most expensive lesson in this repo. An EUR alpha passed every locally visible
check (`Sharpe 1.80 / Fitness 1.26 / Turnover 16.02%`, local gate `True`) and was still
rejected on submission:

| Check | After simulation | At submission |
|---|---|---|
| `IS_LADDER_SHARPE` | `WARNING 0.88 / 1.58` | **`FAIL 0.88 / 1.58`** |
| `PROD_CORRELATION` | `PENDING` | **`FAIL 0.8314 / 0.7`** |

Two mechanisms are invisible from simulation output:

1. **A `WARNING` can be re-judged as `FAIL` at submission** — same value, same limit, different verdict.
   So read the number, never the label.
2. **`PROD_CORRELATION` is only computed at submission time** — it is `PENDING` forever in
   `is.checks`, so no local correlation proxy can predict it. The only usable signal is field
   crowding: that field already had 19,800 alphas in `EUR/TOP2500`.

`scripts/preflight.py` encodes both, so quota is spent only after the gate says GO:

```bash
python scripts/preflight.py RREmY1Qe KPJG6Jwj
python scripts/preflight.py --from-json results.json     # batch
python scripts/preflight.py RREmY1Qe --json --skip-crowding
```

Exit code `0` means at least one GO; `1` means all NO-GO. `gate_report(strict=True)` is now the
default in `wq_api.py`, and `submit_verified()` re-POSTs the submit endpoint until the 403 verdict
document appears (a `GET`-polling loop misreads "still computing" as "submission swallowed").

**Field crowding is a proxy, not the cause.** `PROD_CORRELATION` is judged per *signal family*
(dataset × economic logic), not per numeric correlation — so changing windows, decay or field
names inside the same family moves it by nothing. The one calibrated dial is the weight of an
orthogonal family, and the response is **convex**: 25% orthogonal weight bought only 0.011 on a
0.7621-rejected alpha, while the next 10 points bought 0.036. In practice that weight also
collapses `IS_LADDER_SHARPE` below 65%, so the feasible window is narrow. Full procedure, the
measured weight ladder, and the GBR/TOP700 family map live in **SKILL.md §8.4**.

## Self-Evolution Loop

`scripts/evolve_skill.py` is the feedback engine. After simulations, submissions, or status checks, it can fetch the user's alpha list, compare new/changed alphas with the local snapshot, compute daily-return correlations against ACTIVE alphas, and generate a Markdown lesson snippet.

Recommended loop:

1. Generate or modify candidate expressions from `SKILL.md`.
2. Simulate and inspect IS checks on BRAIN.
3. Pull all ACTIVE alphas and compare daily-return correlation.
4. Run `python scripts/evolve_skill.py` to preview new lessons.
5. Review the output manually.
6. Run `python scripts/evolve_skill.py --apply` only for local/private updates.
7. Publish only sanitized general rules, never raw account-linked records.

## Contents

```text
wq-alpha-research/
├── SKILL.md
├── scripts/
│   ├── wq_api.py            # shared BRAIN client (auth, multi-sim, rate limits, recordsets)
│   ├── preflight.py         # pre-submit gate: GO / NO-GO before burning a submit quota
│   ├── simulate_batch.py    # batch simulate / optional submit, with dedup cache
│   ├── static_check.py      # pre-simulation checks: field crowding, rationale
│   ├── recommend_fields.py  # low-crowding field recommendation
│   ├── evolve_skill.py      # self-evolution: diff alphas, correlations, lesson snippets
│   ├── wq_forum.py          # consultant forum (Zendesk) reader: search / post / comments
│   ├── validate_templates.py# batch-validate community template expressions (--dry-run)
│   └── wq_*.py              # archived per-experiment variant runners
├── references/
│   ├── empirical-log.md     # full experiment log (background, metrics, reasoning)
│   ├── wq_usa_top3000_delay1_data_fields.csv
│   ├── fields_usa_top3000_delay1.json
│   └── wq_usa_top3000_delay1_data_fields_summary.json
├── reports/                 # long-form research notes
└── tests/                   # pytest: field snapshot, static check, submit gate
```

## What It Helps With

- Search USA TOP3000 delay=1 BRAIN fields locally.
- Build Alpha expressions from common WQ operator patterns.
- Diagnose low Sharpe, low Fitness, high Turnover, concentrated weights, and sub-universe failures.
- Compare candidate alphas against existing ACTIVE alphas using daily-return correlation.
- Automate simulation/submission workflows with explicit post-submit status checks.
- Evolve the skill from local alpha research notes without committing private records.

## Quick Start

Read `SKILL.md` first. It contains the actual playbook and trigger instructions.

For local field lookup:

```python
import json
from pathlib import Path

fields = json.loads(
    Path("references/fields_usa_top3000_delay1.json").read_text(encoding="utf-8")
)

keyword = "operating_income"
matches = [
    f for f in fields
    if keyword in f["id"].lower()
    or keyword in (f.get("description") or "").lower()
]
print(matches[:5])
```

## BRAIN Credentials

Use environment variables:

```bash
export WQ_BRAIN_USERNAME="your_username"
export WQ_BRAIN_PASSWORD="your_password"
```

Or create a local `credential.txt` file:

```json
["your_username", "your_password"]
```

`credential.txt` is ignored by git. Do not commit real credentials, cookies, sessions, tokens, alpha databases, or submission results.

## Scripts

All scripts share one client, `scripts/wq_api.py`, which follows the current BRAIN API docs
(2026-09): `Retry-After`-driven polling, the full terminal-status set
(`COMPLETE` / `WARNING` / `TIMEOUT` / `FAIL` / `CANCELLED` / ...), multi-simulation via an array
POST, `X-Ratelimit-*` tracking, server-side `?status=` filtering, and date-aligned PnL correlation.

Batch simulate a variant file (dedup cache on by default, so identical configs never burn quota twice):

```bash
python scripts/simulate_batch.py --file variants.json --batch-size 8
python scripts/simulate_batch.py --expr "group_rank(ts_rank(operating_income/equity,126),subindustry)"
python scripts/simulate_batch.py --file variants.json --dry-run     # print payloads only
python scripts/simulate_batch.py --file variants.json --submit      # submit gate-passing alphas
```

Preview skill evolution output without modifying files:

```bash
python scripts/evolve_skill.py
```

Apply updates to local `SKILL.md` and `alpha_db.json` after reviewing the preview:

```bash
python scripts/evolve_skill.py --apply
```

The scripts require `requests` and `numpy`. `alpha_db.json` and `simulation_cache.jsonl` are local
memory files and are intentionally ignored by git.

## Safety Notes

The following files are intentionally ignored:

- `credential.txt`
- `alpha_db.json`
- `batch_submit_results.json`
- `.env`
- Python caches and virtual environments

If you want to publish research lessons from local runs, summarize them into general rules before adding them to `SKILL.md`. Do not publish raw alpha IDs, PnL series, account-linked submission statuses, or private candidate expressions.

## Get in Touch

Join the QuantML factor-research WeChat group, or scan the personal QR code to add me as a friend.

| WeChat Group: QuantML Factor Research | Add Me as Friend |
| :---: | :---: |
| <img src="pic/20260624124943.jpg" width="300" alt="QuantML Factor Research Group QR"> | <img src="pic/20260624125220.jpg" width="300" alt="Add Friend QR"> |


## License & Attribution

This project is licensed under the [Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

You are free to use, modify, and share the code and content for non-commercial purposes, provided that you clearly cite the source and provide attribution to the original author.

If you use this work in your research, project, or publication, please include a link or reference back to this repository.