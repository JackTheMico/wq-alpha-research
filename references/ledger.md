# 结论账本（ledger）

> **用途**：选族 / 选字段**之前**先查这里，避免重烧已经关闭的族。实证过程与推理留在
> `empirical-log.md`（人读散文），本文件只保留**可反查的一行一结论**（机器读）。
> 查法：`python scripts/redflag.py <字段或关键词>`，或 `python scripts/redflag.py --open`。
>
> **维护规则**：每跑完一批仿真，把新结论追加到 `## 2. 字段级`，并同步更新 `## 1. 族级` 的
> 最优值与状态。同一个字段只保留最新一行，旧行用 `superseded` 标记。
>
> **迁移阈值**：字段级行数超过 500 时迁到 SQLite（`kb.py`），本文件改为生成的只读视图。

状态取值：

| status | 含义 |
|---|---|
| `ACTIVE` | 已提交且 ACTIVE |
| `BLOCKED` | 指标够，但被 2Y / ladder / Robust / 相关性卡死，同族不要重跑 |
| `CLOSED` | 单腿天花板远低于门槛，整族无信号 |
| `OPEN` | 尚未扫描，或扫描未完成 |
| `UNTESTED` | 已知存在但本轮未实测 |

---

## 1. 族级（region × dataset）

| region | dataset | status | 最优单腿 S | 卡在哪 | 证据 |
|---|---|---|---|---|---|
| IND | reversal + eps 修正（`RREKPjQ1`） | **ACTIVE** | 1.71 | — | §14 |
| IND | analyst_revision_horizons（surprise） | **BLOCKED** | 1.69（group_rank） | LOW_2Y 0.80；混腿 ladder 1.32 | §15.3 |
| IND | predictive_starmine | **BLOCKED** | 1.18（EM 20 日均） | 2Y 0.55；revision_count 单腿 0.63 | §15.2 |
| IND | ai_news_scores | **CLOSED** | 0.27 | 单腿即死 | §15.2 |
| IND | intraday_pv_feats | **CLOSED** | −0.08 | 单腿即死 | §15.2 |
| IND | model28 | **CLOSED** | 0.02 | 单腿即死 | §15.2 |
| IND | analyst11 | **CLOSED** | 0.22 | 单腿即死 | §15.2 |
| IND | pv30 | **CLOSED** | −0.25 | 41 个字段全是 PCA/聚类**分组标签**，非价量因子；`group_rank` 报 `Unit[Group:1]` 不匹配，`densify` 同样拒绝；`bucket(...)` 强转后 ladder 0.63 | §15.6 |
| AMR | reversal 126/252 + INDUSTRY | **CLOSED** | 1.39 | 封顶 1.39；14 条正交腿全 ≤0.59；混腿 0.79 | §14 |
| AMR | fundamental28 | **CLOSED** | 0.51 | 13 个 ratio 全部 2Y FAIL | §15.4 |
| AMR | fundamental23 | **UNTESTED** | — | 与 fundamental28 同类切面，预计同死 | §15.4 |
| AMR | analyst4 | **CLOSED** | 0.42（混腿） | SubU ≤0.3，2Y 负 | §15.4 |
| AMR | model30（SmartEstimate surprise） | **CLOSED** | 0.90 | 2Y 1.48，差 0.1 仍 FAIL | §15.4 |
| AMR | model31（Earnings Quality） | **CLOSED** | 0.05 | 与 §14 复测一致，全负或零 | §15.4 |
| AMR | model28 / model50 / model16 | **CLOSED** | 0.05 / 0.01 / — | 违约风险、基本面稳定性无信号 | §15.4 |
| AMR | fundamental6 / analyst11 / model25 / model26 / model38 | **UNTESTED** | — | 非反转族，同 AMR 非反转上限 0.90 预期 | §15.4 |

---

## 2. 字段级（region × field → 最优结论）

> 表达式为 `rank(field)` 或 `group_rank(field, industry)`（最快的那条），设置统一
> `delay 1 / INDUSTRY / decay 4 / truncation 0.08 / FULL`，除非 `设置` 列另有标注。

| region | dataset | field / expr | S | checks | status | § |
|---|---|---|---|---|---|---|
| IND | analyst_revision_horizons | `group_rank(forecasted_earnings_surprise_fy1_long, industry)` | 1.69 | 2Y 0.80 WARN / Robust 0.73 FAIL | BLOCKED | §15.3 |
| IND | analyst_revision_horizons | `rank(forecasted_earnings_surprise_fy1_long)` | 1.35 | 2Y 0.94 | BLOCKED | §15.2 |
| IND | analyst_revision_horizons | `forecasted_earnings_surprise_pct_fy2_long` | −0.04 | — | CLOSED | §15.5 |
| IND | analyst_revision_horizons | `anticipated_earnings_surprise_q1_short` | 0.12 | — | CLOSED | §15.5 |
| IND | analyst_revision_horizons | `anticipated_earnings_surprise_pct_fy1_short` | 0.21 | — | CLOSED | §15.5 |
| IND | analyst_revision_horizons | `growth_next_vs_this_year_earnings_weighted_long_4` | −0.44 | — | CLOSED | §15.2 |
| IND | analyst_revision_horizons | `peg_ratio_industry_percentile_f12m_long_term`（反向） | 0.69 | — | CLOSED | §15.2 |
| IND | analyst_revision_horizons | `price_to_estimate_ratio_next_12m_operating_long`（反向） | 0.53 | — | CLOSED | §15.2 |
| IND | analyst_revision_horizons | `price_to_mean_estimate_fy1_earnings_long_term_2`（反向） | 0.49 | — | CLOSED | §15.2 |
| IND | predictive_starmine | `ts_mean(mean_estimate_change_pct_fy1_earnings_7d_3, 20)` | 1.18 | 2Y 0.55 | BLOCKED | §15.2 |
| IND | predictive_starmine | `mean_estimate_change_pct_fy1_earnings_7d_3` | 1.02 | — | BLOCKED | §15.2 |
| IND | predictive_starmine | `analyst_upward_revision_count_fy1_earnings_14d_3` | 0.63 | — | CLOSED | §15.2 |
| IND | predictive_starmine | `projected_earnings_fy5_3 / close` | 0.62 | — | CLOSED | §15.2 |
| IND | ai_news_scores | `neutral_score_*` / `positive_score_*`（35 个） | 0.27 | — | CLOSED | §15.2 |
| IND | intraday_pv_feats | `mean_slippage_60m_pre_close_2` 比值类 | −0.08 | — | CLOSED | §15.2 |
| IND | model28 | `mdl28_sm_structural_*_pd_percent`（反向） | 0.02 | — | CLOSED | §15.2 |
| IND | analyst11 | `resource_efficiency_subsector_rank` | 0.22 | — | CLOSED | §15.2 |
| IND | reversal | `rank(-ts_delta(close,126)) + eps 修正`（`RREKPjQ1`） | 1.71 | prod 0.6684 / self 0.0 | **ACTIVE** | §14 |
| IND | reversal | 同族 eps 权重 0.15 + decay 6（`LLMr3x3v`） | — | SELF = PROD = 0.9535 | BLOCKED | §14 补记 |
| AMR | model30 | `group_rank(star_eps_surprise_prediction_fy1, industry)` | 0.90 | 2Y 1.48 | CLOSED | §15.4 |
| AMR | model30 | `star_eps_surprise_prediction_fy1` | 0.76 | — | CLOSED | §15.4 |
| AMR | model30 | `star_eps_surprise_prediction_fq2` | 0.51 | SubU 0.58 PASS | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08221`（Total Debt % Total Capital） | 0.51 | 2Y 0.35 | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_annstts2_value_09404`（Dividend Yield） | 0.32 | 2Y 1.12 | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08636`（Net Income Growth） | 0.14 | — | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08605`（EPS Growth） | 0.09 | — | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08225`（Debt % Capital 5Y） | 0.07 | — | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08106`（Current Ratio） | 0.02 | — | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08101`（Quick Ratio） | −0.02 | — | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08251`（Fixed Charge Coverage） | −0.09 | — | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08316`（Operating Profit Margin） | −0.20 | — | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_value_08306`（Gross Profit Margin） | −0.45 | — | CLOSED | §15.4 |
| AMR | fundamental28 | `fnd28_prof_value_08371`（ROE per share） | 0.27 | — | CLOSED | §15.4 |
| AMR | analyst4 | `0.6*eps/close + 0.4*eps_flag` | 0.42 | — | CLOSED | §15.4 |
| AMR | analyst4 | `anl4_qfv4_eps_flag`（revision/new 标志） | 0.32 | 2Y −0.11 / TO 7.3% | CLOSED | §15.4 |
| AMR | analyst4 | `anl4_qfv4_median_eps / close`（ts_rank 252） | 0.43 | SubU ≤0.3 | CLOSED | §15.4 |
| AMR | analyst4 | `anl4_qfv4_median_eps / close` | 0.31 | — | CLOSED | §15.4 |
| AMR | analyst4 | `anl4_afv4_cfps_median / close` | 0.31 | — | CLOSED | §15.4 |
| AMR | analyst4 | `anl4_bvps_median / close` | 0.21 | — | CLOSED | §15.4 |
| AMR | analyst4 | `anl4_fcf_median / close` | 0.18 | — | CLOSED | §15.4 |
| AMR | analyst4 | `anl4_netprofita_median / close` | 0.15 | — | CLOSED | §15.4 |
| AMR | model31 | `mdl31_a1_erq_re_rk_prior_qtr`（group_rank） | 0.02 | — | CLOSED | §15.4 |
| AMR | model31 | `mdl31_a1_acc_prior_qtr`（反向） | −0.04 | — | CLOSED | §15.4 |
| AMR | model28 | `star_cr_region_rank` / `star_cr_dist_to_default`（反向） | 0.05 / −0.06 | — | CLOSED | §15.4 |
| AMR | model50 | `mdl50_bk_fund_stab`（反向） | 0.01 | — | CLOSED | §15.4 |
| AMR | model16 | `fscore_momentum` | 0.30 | — | CLOSED | §14 |
| AMR | reversal | `rank(-ts_delta(close,252))` + INDUSTRY | 1.38 | 封顶；正交腿全 ≤0.59 | CLOSED | §14 |
| AMR | reversal | `rank(-ts_delta(close,126))` + SUBINDUSTRY | 1.25 | INDUSTRY 更好 | CLOSED | §14 |
| IND | pv30 | `rank(principal_component_3_top1200_xjp_513)` | −0.25 | 2Y −0.66 / Robust −0.11 / SubU −0.22 | CLOSED | §15.6 |
| IND | pv30 | `group_rank(surprise, bucket(top500_industry_grouping_method4_20, range="0,20,1"))` | 1.58 | Ladder 0.63 / Robust 0.70 FAIL | CLOSED | §15.6 |

---

## 3. 通用规则（从实测和论坛评论沉淀）

| 规则 | 证据 |
|---|---|
| **计数类字段（`*_count` / `*_number` / `*_num`）不要做主信号** | 论坛 `post 36093116182423` 评论：纯计数因子同批 Sharpe 仅 0.10；本仓 IND `analyst_upward_revision_count_*` 实测 0.63 |
| **计数类字段做过滤项也要看 coverage**，覆盖不足的变体会整批 `LOW_ROBUST` 失败 | 同上 |
| **PCA / 聚类分组字段在 IND 不可用于 `group_rank`** | §15.6：报 `Unit[Group:1]`，`densify` 也报同样错误 |
| **日内/微观结构思路必须蒸馏成日频稳定代理**，直接用会死 | 论坛 `post 36223563506839`；本仓 `intraday_pv_feats` 实测 −0.08 |
| **期权希腊字母类思路在 IND 不可实现**（该区无期权数据集） | §15.1 字段池扫描 |
