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
| GLB | model109 慢变量（FCF/EV 20v250 正交） | **CLOSED** | 1.03 | AMER 0.68 单腿不足；2Y 2.25、TO 2.8% 很好 | §17 |
| GLB | pv1 reversal（SUBINDUSTRY） | **BLOCKED** | 1.88 | AMER 1.01、2Y 1.08（ATOM 需 2Y）、PP corr 0.9673 | §17 |
| GLB | model109 FCF/EV + pv1 REV252 | **OPEN** | 1.65 | AMER 1.01 / EMEA 1.40 / APAC 1.20 / Ladder PASS；Fitness 0.80、PP corr 未知 | §17 |
| GLB | analyst15 / model26 / model38 / model77 慢字段 | **CLOSED** | ≤0.43 | 单字段与模板形态在 AMER 均 <0.26 | §17 |

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
| EUR | other460 | `rank(oth460_3l_caic)`（财报科目趋势预测概率） | −0.50 | 2Y 0.37 FAIL | CLOSED | §16.2 |
| EUR | news20 | `rank(nws20_multiple_comp_d1_qep)`（新闻情绪分） | — | **ERROR** `rank` 不支持 event 输入，需先事件聚合 | UNTESTED | §16.2 |
| EUR | analyst9 | `rank(vec_avg(anl9_sconsensusv2span_cashflowstatement_dataitemvalue))` | 0.49 | 7 个 value 字段全测，最高 0.52（除 cap）；2Y 1.41 差 0.17；28 个字段中 21 个是时间戳/拆股因子非信号 | CLOSED | §16.6 |
| EUR | other455 | Node2Vec 竞争者聚类标签 168 个 | — | 与 pv30 同类分组字段，预期同 unit 问题 | UNTESTED | §16.1 |
| CHN | fundamental27 | `rank(fnd27_..._cash_pay_goods_purch_serv_rec_value / ts_mean(...,252))` | −0.82 | 加负号无效（−1.60）；2Y 0.02 FAIL | CLOSED | §16.3 |
| CHN | fundamental5 | `rank(fnd5_cur_212_21_af_si)`（净利率） | −0.19 | 2Y −1.03 FAIL | CLOSED | §16.3 |
| CHN | analyst14 | `rank(anl14_high_opp_fy2)` | −0.50 | 加负号/backfill 均无效（−0.19 / −0.27） | CLOSED | §16.3 |
| CHN | model31 | `rank(mdl31_erq_re_rk_chg_1_fy)` | −0.55 | 加负号变 −1.98 | CLOSED | §16.3 |

---

## 3. 通用规则（从实测和论坛评论沉淀）

| 规则 | 证据 |
|---|---|
| **计数类字段（`*_count` / `*_number` / `*_num`）不要做主信号** | 论坛 `post 36093116182423` 评论：纯计数因子同批 Sharpe 仅 0.10；本仓 IND `analyst_upward_revision_count_*` 实测 0.63 |
| **计数类字段做过滤项也要看 coverage**，覆盖不足的变体会整批 `LOW_ROBUST` 失败 | 同上 |
| **PCA / 聚类分组字段在 IND 不可用于 `group_rank`** | §15.6：报 `Unit[Group:1]`，`densify` 也报同样错误 |
| **日内/微观结构思路必须蒸馏成日频稳定代理**，直接用会死 | 论坛 `post 36223563506839`；本仓 `intraday_pv_feats` 实测 −0.08 |
| **期权希腊字母类思路在 IND 不可实现**（该区无期权数据集） | §15.1 字段池扫描 |
| **加负号翻符号不可靠**：同一字段的 `rank(x)` 与 `rank(-x)` / `-rank(x)` 可能**同号同幅**（rank 对 NaN 的填充不对称）。翻方向必须实测，不能靠推导 | §16.3：`anl14` −0.50 / −0.19 / −0.27 三者同号 |
| **VECTOR/event 字段必须先 `vec_avg` / `vec_sum` / `vec_count` 聚合，再进普通算子链**；任何 `ts_*` 直接包原始字段都会被拒 | §16.5：`rank(vec_avg(qep))` OK，其余 6 种包装全 ERROR；EUR 上限 S=0.38 |

---

## 4. GLB / Power Pool Nov'26（2026-11-11 实测，§17）

> 主题：GLB/D1 Power Pool Nov'26（2026-10-26 ~ 11-22），条件 = GLB · D1 · AMER Sharpe > 1。
> 统一设置：TOP3000 / delay 1 / decay 4 / truncation 0.08 / MARKET，表达式内 `group_neutralize(..., country)`。
> 结论是“GLB AMER 由反转腿驱动，慢变量单数据集过不了 AMER”。

| 类型 | 表达式（摘要） | S | AMER | EMEA | APAC | TO | 卡点 |
|---|---|---|---|---|---|---|---|
| ATOM 模板（model109 FCF/EV） | `group_neutralize(vector_neut(ts_mean(ts_backfill(FCF_EV,60),20), ts_mean(ts_backfill(FCF_EV,60),250)), country)` | 1.03 | 0.68 | 1.05 | 0.33 | 2.8% | AMER 不足；2Y 2.25 很好 |
| ATOM 模板（model38 StarMine 慢字段） | 同上，F = `backfill_forward_10yr_eps_growth` 等 | ≤0.38 | ≤0.18 | — | — | 1–3% | 慢字段信号几乎为 0 |
| ATOM 反转 | `group_rank(-ts_rank(returns,126), subindustry)`，decay 20 | 1.67 | 1.04 | 0.14 | 1.70 | 45% | 2Y 0.72；PP corr 0.9673 |
| ATOM 反转（252） | `group_rank(-ts_rank(returns,252), subindustry)`，decay 10 | 1.88 | 1.01 | 0.26 | 1.96 | 61% | 2Y 1.08；PP corr 高 |
| 纯 PP 候选 A | `group_neutralize(0.7*rank(ts_delta(FCF_EV,126)) + 0.3*rank(-ts_rank(returns,252)), country)` | 1.62 | **1.06** | 1.13 | 1.21 | 18% | Fitness 0.84 / Ladder 1.40；PP corr 未测 |
| 纯 PP 候选 B（更稳） | `group_neutralize(0.6*rank(vector_neut(ts_mean(ts_backfill(FCF_EV,60),20), ts_mean(ts_backfill(FCF_EV,60),250))) + 0.4*rank(-ts_rank(returns,252)), country)` | 1.65 | 1.01 | 1.40 | 1.20 | 25% | Fitness 0.80；Ladder PASS |

- `ts_median` 在本账号不可用（`Inaccessible or unknown operator`），模板需改 `ts_mean`；`ts_backfill` 仍不计入 8 算子限制。
- 未打 `POWER_POOL` tag 时 `MATCHES_THEMES` 恒为 WARNING/PENDING，即使 AMER 1.06；主题匹配需要在提交前打 tag 才能验证。
- ATOM 路径要求 2Y Sharpe，本区单数据集候选 2Y 最高 1.51（`rev21`，AMER 0.91）→ 单数据集 GLB ATOM 在本批字段池内不可行。
- **2026-11-11 提交实测**：`O0AVoLa1`（MINVOL10M / COUNTRY / d4 / S 2.31 / F 1.37 / TO 25.0%，三子区全 PASS）打 `POWER_POOL` tag + 1128 字符 description 后提交，403 = **`PROD_CORRELATION=0.8698(limit=0.7)`**，其余全 PASS。`MATCHES_THEMES` 在 PATCH tag 后仍是 WARNING（checks 是仿真快照，不随 PATCH 重算）⇒ **打 tag 并未把该族切到 PP 相关性闸门**；MINVOL10M 同族 prod 0.8698 高于 TOP3000 的 0.7903。

### 4.1 低拥挤族 + 价格结构变体（2026-11-11 夜间，GLB D1 TOP3000）

**低拥挤慢变量族**（按 `data-sets` 的 alphaCount 从低到高扫了 138 个 GLB 数据集，选 cov≥0.5 的族）：

| 数据集（alphaCount） | 单腿最佳 | AMER | 结论 |
|---|---|---|---|
| model16 Fundamental Scores（56） | `-analyst_revision_rank_derivative` 翻转 S 0.62 | 0.57 | CLOSED |
| model28 Structural Credit Risk（29） | `default_probability_one_year_pct` 反向 S 0.24 | 0.60 | CLOSED |
| model36 SmartRatios（48） | `-credit_risk_leverage_score_main` S 0.28 | 0.51 | CLOSED |
| model37 Text Mining（21） | `-credit_risk_global_percentile_score_float_5` S 0.24 | 0.49 | CLOSED |
| model50 International Scorings（25） | `+dispersion` / `+beta` / `+downside` 翻转后 S≈0.47–0.68 | 0.68 | CLOSED |
| model140 Inflation Sensitivity（1） | `mdl140_qes_sinc_comp` S 0.54 | 0.56 | CLOSED |
| analyst82 EPS Prediction（35） | `anl82_delta_epsq_q1_predict` S 0.17 | -0.10 | CLOSED |

- 3 腿组合 6 条（model50 rev+disp+beta / rev+beta+model140 / rev+model36 / rev+model37 / rev+model28 / model16 两腿+model140）：**S 0.23–0.44**，T1–T5 的 AMER/EMEA 直接 ERROR（子区样本不足），T6 AMER 0.13。
- 低覆盖数据集（other546/567、search_interest、hiring_trends、other699、model239、analyst45、news73、finnews_nlp_scores、other384、option_chart_model、model307、fundamental22/25）在 GLB TOP3000 的 coverage 全 <0.5，无法用。

**价格结构变体**（decay 10 / SUBINDUSTRY）：

| 表达式 | S | F | TO | AMER | 2Y | id |
|---|---|---|---|---|---|---|
| 残差反转 21d `-ts_rank(returns - group_mean(returns,1,country),21)` | 1.68 | 0.59 | 60% | 0.80 | 1.13 | A1xjOWGg |
| 日内反转 21d `-ts_rank(close/vwap-1,21)` | 1.19 | 0.45 | 57% | 0.59 | 0.71 | vRAwe5Vz |
| 隔夜反转 `-ts_rank(open/ts_delay(close,1)-1,21)` | 0.41 | 0.09 | 57% | -0.13 | 0.28 | O0WQWpjJ |
| 量价条件反转 `-ts_rank(returns,21)*ts_rank(volume/adv20,21)` | 1.28 | 0.50 | 46% | 0.73 | 1.77 | 9qlZGzNd |
| 低波 `-ts_rank(ts_std_dev(returns,60),252)` | 0.12 | 0.03 | 8% | -0.33 | -0.28 | ZYaPXALj |
| 区间反转 `-ts_rank((high-low)/close,21)` | -0.34 | -0.07 | 48% | -0.07 | 0.25 | YPaLlYXA |
| **残差反转 126d** 同上窗口 126 | **1.92** | 0.76 | 59% | **1.07** | 1.15 | E5QONjVP |
| 日内反转 126d | 未跑（后台被中止） | — | — | — | — | UNTESTED |

- `E5QONjVP` 三子区 PASS（AMER 1.07 / EMEA 1.36 / APAC 1.52），打 `POWER_POOL` tag 后提交，403 = **`LOW_FITNESS=0.76` + `PROD_CORRELATION=0.8789` + `LOW_2Y_SHARPE=1.15`**。
- **GLB D1 结构性结论**：唯一能过 AMER>1 的两个族（裸反转 252d、残差反转 126d）prod corr 均在 0.87–0.88；所有慢变量族 AMER ≤0.68。调窗口/中性化/组合都无法同时满足 AMER>1 与 corr<0.7。
- 算子坑：`ts_median` / `ts_skewness` / `ts_max` 本账号不可用；`group_mean` 必须 3 参 `(x, weight, group)`；同一 `run_many` 批次内一条 ERROR 会把同批其他任务标 CANCELLED，筛选时应逐条提交或小批。

## 5. EUR D1（2026-11-11 实测，TOP2500 / decay 10 / SUBINDUSTRY）

> 当前 Power Pool 主题是 GLB D1，EUR 候选 `MATCHES_THEMES` 恒为 WARNING，只能走 ATOM/Regular。

| 表达式 | S | F | TO | 2Y | SubU | 结论 |
|---|---|---|---|---|---|---|
| 残差反转 126d `group_rank(-ts_rank(returns-group_mean(returns,1,country),126),subindustry)` | 2.00 | 0.79 | 62% | 0.76 | 1.31 | 可看，Fitness/2Y 不足 |
| 裸反转 252d `group_rank(-ts_rank(returns,252),subindustry)` | 2.07 | 0.83 | 63% | 1.06 | 1.46 | 最优，仍需降 TO |
| 裸反转 21d | 1.44 | 0.44 | 63% | 0.84 | 1.19 | 换手过高 |
| FCF/EV `ts_backfill(fnd23_ofc/cap,60)` | 0.09 | 0.02 | 1.9% | — | 0.59 | 无效 |
| model16 `-analyst_revision_rank_derivative` | -0.19 | -0.05 | 0.8% | 0.01 | -0.13 | 无效 |
| model50 `-analyst_forecast_revision_score_4` | -0.40 | -0.15 | 1.3% | -0.26 | -0.34 | 无效 |
| model50 `+analyst_forecast_dispersion_score` | 0.44 | 0.17 | 1.2% | 0.28 | 0.37 | 无效 |
| model37 `-credit_risk_global_percentile_score_float_5` | -0.61 | -0.25 | 2.2% | -0.52 | -0.41 | 无效 |

- EUR 与 GLB 同构：只有价格反转族有效，慢变量族更弱；EUR 反转候选 Fitness 0.79–0.83（TO 62%），需 decay 30–40 压换手后再测，且 prod corr 未知。
- 未继续执行（用户选择归档）：EUR decay 40 变体、EUR 提交测相关、USA D1 方向。

## 6. 冷门字段 × ATOM（2026-11-12/13 实测）

> 骨架统一为 `group_neutralize(vector_neut(ts_mean(f,20), ts_mean(f,250)), country)`，
> 未注明时 region/universe = EUR/TOP2500、MARKET、decay=0、QUICK。

### 6.1 单腿（同骨架）

| 字段 | 数据集 | S | SubU | 结论 |
|---|---|---|---|---|
| `ebg_sector_18mo_marketcap_percent` | analyst15 | 2.05 | PASS | 指标最好，但历史仅 50 天（见 6.3） |
| `default_risk_region_percentile_d1` | model28 | 0.78 | PASS | 可用弱腿 |
| `country_relative_investment_rank_d1` | model238 | 0.75 | FAIL | SubU 挂，不可单独用 |
| `anl10_nerinnovate_increase_fy1` | analyst10 | 0.40 | PASS | 可做辅腿 |
| `anl10_nernormal_increase_fy1` | analyst10 | 0.34 | PASS | 可做辅腿 |
| `anl4_fs_detail_estimates_advanced_af_nd_bvps_mean` | analyst4 | 0.24 | PASS | 弱 |
| `confidence_bucket0_pricevol_monthquarter_20d` | global_seasonal_model | -0.57 | FAIL | 反向可取 |
| `analyst_downward_revision_count_fq1_earnings_7d_5` | predictive_starmine | -0.77 | PASS | 反向可取 |
| `country_level_analyst_forecast_revision_score` | model50 | -0.83 | PASS | 反向最强 |

GBR/TOP700 的 model264 单腿顶配只有 S 0.43（`mdl264_1l_ist`），analyst7 / predictive_starmine / model26 单腿 ≤0.16 —— **GBR 冷门族整体弱于 EUR**。

### 6.2 多腿

| 组合 | S | F | TO | Margin | SubU |
|---|---|---|---|---|---|
| GBR model264 8 腿（4 正 + 4 反，40/60） | 1.07 | 0.71 | 11.6% | 9.5‱ | PASS |
| GBR model264 8 腿 + decay10 | 1.03 | 0.68 | 8.8% | 12.3‱ | PASS |
| GBR model264 11 腿（去 backfill） | 1.02 | 0.66 | 10.4% | 10.2‱ | PASS |
| EUR 5 正腿等权 | 0.67 | 0.43 | 10.2% | 9.9‱ | FAIL |
| EUR 2 正腿（analyst15 + model28） | 0.77 | 0.54 | 2.6% | 47.7‱ | PASS |
| EUR 0.6/0.2/0.2（analyst15 + 两条 analyst10） | 1.10 | 0.48 | 18.8% | 3.9‱ | PASS |
| EUR 0.8/0.2（analyst15 + model28） | 0.77 | 0.54 | 2.6% | 47.7‱ | PASS |

- 多腿能把单腿 0.43 放大到 1.07，但**加腿会摊薄 Margin / SubU**，且弱腿会把 Fitness 拉回 0.5 量级；
- 单腿集中度过高时 `CONCENTRATED_WEIGHT` 在 QUICK 报 FAIL、FULL 报 WARNING，提交仍被拒。

### 6.3 提交实测：LOW_DURATION 才是新字段的死因

`analyst15 / ebg_sector_18mo_marketcap_percent`（FULL，alpha `RReWar7g`）：
S 2.05 / F 2.22 / Margin 65.5‱ / SubU PASS，`CONCENTRATED_WEIGHT` 与 `LOW_2Y_SHARPE` 在 FULL 只是 WARNING，
提交 403 判定书：

```
CONCENTRATED_WEIGHT = FAIL
LOW_2Y_SHARPE      = 0.0 / 1.58
LOW_DURATION       = 50 / 500     ← 真凶
```

- **`LOW_DURATION` 在 QUICK/FULL 的 `is.checks` 里完全不出现**，只有 `POST /submit` 才回算；
- 字段只有 50 天历史 → 不可提交，与指标无关；
- 因此「最新 onboard 字段」在攒满 500 天前只能研究，不能变现：选字段先卡 `dateCreated` 年龄 ≥ 500 天
  （`recommend_fields.py --min-age 500`，`preflight` 用字段年龄兜底阻断）。

## 7. analyst10 / EUR/TOPCS1600：全量单腿 + 论坛模板复活（2026-11-13）

### 7.1 全量单腿（561 字段，ATOM `vector_neut(ts_mean20, ts_mean250)`）

| 指标 | 值 |
|---|---|
| 有效 | 551 / 561 |
| Sharpe | max 1.43，中位 0.15，>1.0 共 24 条 |
| Fitness | max 0.83，**≥1.0 一条都没有** |
| Margin | max 43.9‱，中位 2.2‱ |
| Top30 SubU | 25 PASS / 5 FAIL |
| Top30 2Y | **30 条全 FAIL** |

最强族 `anl10_*innovation_score_fy2`（gps 1.43 / prr 1.38 / ebt 1.32 / net 1.32 / pre 1.31），
换手稳定 17–21%。同族 `*innovate_decrease_fy2` 全部强负：prr **-1.57**、net -1.45、ebt -1.41、pre -1.38、ebi -1.35。

### 7.2 论坛知识驱动的第二轮（11 条）

来源：`kb.py pull "ATOM template"` / `atom模板分享`(24) / `ATOM模板分享`(28) / `ASI broker Pyramid`(96) /
`How to Increase or Reduce Sharpe...`(40) / `ts_backfill AND ts_rank`(103)。详见 templates-core.md §4.1.4。

| 变体 | S | F | TO | Margin | SubU | 结论 |
|---|---:|---:|---:|---:|---|---|
| **rev_prr_decrease**（-1.57 取反） | **1.57** | **0.96** | 17.9% | 7.5‱ | FAIL | 单腿最强，但 SubU 挂 |
| **2leg_gps_revnet** | **1.50** | **0.90** | 19.5% | 7.1‱ | **PASS** | 本轮最优可复现骨架 |
| 2leg_gps_revprr | 1.46 | 0.86 | 20.3% | 7.0‱ | PASS | 次优 |
| signed_power_atom | 1.39 | 0.81 | 16.7% | 6.8‱ | PASS | 0.618 幂次无增益（基线 1.43） |
| 2leg_gps_cshrev | 1.08 | 0.60 | 24.5% | 6.2‱ | PASS | 异族腿拖累 |
| div_5_60 | 0.18 | 0.02 | 66.5% | 0.3‱ | PASS | divide 插槽无效且换手爆炸 |
| div_20_120 | -0.04 | 0.00 | 30.7% | -0.1‱ | PASS | 同上 |
| tsrank_div_20_250 | -0.51 | -0.08 | 176.0% | -0.5‱ | PASS | ts_rank 插槽灾难 |
| tsrank_sub_20_250 | -0.78 | -0.14 | 171.2% | -0.7‱ | PASS | 同上 |
| decay_exp_20_250 | ERROR | — | — | — | — | 本账户无 `ts_decay_exp_window` |

**三条硬结论：**
1. **反向 decrease 族确实是最强腿**（-1.57 → 取反 1.57），比正向 `innovation_score`(1.43) 更强；
2. **插槽扫描必须做，但不能盲目**：该字段只有 `ts_mean × vector_neut` 存活，`
   divide` 换手 30–66%，`ts_rank` 换手 171–176% —— 换手一崩、Margin 归零；
3. **2 腿组合能救 SubU**：单腿 rev_prr SubU FAIL，加 gps 后 PASS（1.50 / F 0.90），
   这是本轮唯一同时满足「S>1.4 + SubU PASS + TO<20%」的骨架。

仍未提交：Fitness 0.90 < 1.0（平台线）且 < 2.0（质量线），Margin 7.1‱ < 10‱，2Y Sharpe 全族 FAIL。

## 8. analyst15 / analyst7 × EUR/TOPCS1600：低换手高 Margin 族（2026-11-13）

### 8.1 单腿筛选（60 条，30+30，ATOM 20v250）

| 字段 | S | F | TO | Margin | SubU | 2Y |
|---|---:|---:|---:|---:|---|---|
| **anl15_bps_gr_18_m_mean** | **1.12** | 0.82 | **2.9%** | **46.2‱** | PASS | **PASS** |
| anl15_bps_gr_cal_fy3_mean | 0.96 | 0.63 | 3.4% | 31.9‱ | PASS | PASS |
| anl15_bps_gr_18_m_cos_up | 0.74 | 0.33 | 8.5% | 5.9‱ | PASS | FAIL |
| act_q_bps_surprisenum (analyst7) | 0.65 | 0.40 | 2.2% | 41.5‱ | PASS | FAIL |

60 条里 Sharpe 中位 **0.00**、换手中位 **3.0%**、Margin ≥10‱ 仅 7 条 —— 这一族是**低换手、高单笔利润、低 Sharpe** 的形态，
与 analyst10（换手 19%、Margin 7‱）完全相反。

**关键差异：analyst15 这条 2Y Sharpe = PASS（1.73/1.58），analyst10 全族 FAIL。**
即 analyst15 的信号在近两年仍有效，只是全周期 Sharpe 被更早的低效期拖到 1.12。

### 8.2 反向 + 多腿（11 条）

| 变体 | S | F | TO | Margin | SubU |
|---|---:|---:|---:|---:|---|
| rev(analyst7 负腿) ×3 | 0.31 / 0.34 / 0.41 | 0.12–0.22 | 2.6% | 14–28‱ | PASS |
| 2leg_2（anl15 mean + 0.5×rev(act_q_dps_surprisenum)） | **1.00** | 0.72 | 2.8% | 46.3‱ | PASS |
| 2leg_1 / 3leg_1 / 3leg_2 | 0.93 / 0.90 / 0.85 | 0.58–0.66 | ~3% | 36–41‱ | PASS |
| signed_power(anl15) | 0.94 | 0.56 | 2.7% | 32.9‱ | PASS |

**结论：组合没有跑赢单腿（1.00 < 1.12）。** analyst7 反向腿虽能补 SubU，但把 Sharpe 拉低——
这一族的瓶颈不是相关性，是信号强度本身。

### 8.3 decay 是这一族唯一有效的强杠杆（14 条）

| 配置 | S | F | TO | Margin | DD | 2Y |
|---|---:|---:|---:|---:|---:|---|
| decay 0 | 1.12 | 0.82 | 2.9% | 46‱ | 13.2% | PASS |
| decay 20 | 1.25 | 0.97 | 2.3% | 66‱ | 13.5% | PASS |
| decay 50 | 1.35 | 1.09 | 1.9% | 86‱ | 13.5% | PASS |
| **decay 150** | **1.41** | **1.17** | 1.4% | **120‱** | 13.3% | PASS |
| decay 200 | 1.40 | 1.16 | 1.3% | 129‱ | 13.4% | PASS |
| decay 300 | 1.28 | 1.01 | 1.1% | 136‱ | 14.2% | FAIL |
| decay 50 + trunc 0.04 | 1.23 | 0.87 | 1.8% | 69‱ | **8.6%** | PASS |
| decay 200 + 10v250 | 1.40 | 1.16 | 1.3% | 131‱ | **12.4%** | PASS |

**decay 0→150 把 Sharpe 从 1.12 提到 1.41、Fitness 0.82→1.17、Margin 46→120‱**（+0.29 Sharpe）。
交换律：`truncation` 降回撤（13.4%→8.6%）但同样降 Sharpe（1.40→1.23）；`decay` 超过 150 开始反噬（300 时 2Y 掉回 FAIL）。
中性化换 INDUSTRY / subindustry 反而崩到 0.65–0.93 —— 这条信号需要国家维度保留。

### 8.4 仍未提交的原因

`d150`（`npab9Qj3`）：S 1.41 < 1.58、F 1.17（过平台 1.0，但 < 质量线 2.0）、DD 13.3% > Ret 8.6%。
**这是目前 Margin 最充裕的一条（120‱，是质量线 10‱ 的 12 倍）**，差的是收益幅度而非成本覆盖。
下一步该找一个「高收益率腿」与它互补（而不是继续在同一族里加 decay）。

## 9. EUR/TOPCS1600 的低相关候选（2026-11-14）

以 `anl15_bps_gr_18_m_mean`（decay150, `npab9Qj3`）为基准，筛非 analyst15/7/10 的冷字段做 PnL 相关性检测：

| 字段 | 数据集 | S | Margin | 与基准 corr |
|---|---|---:|---:|---:|
| anl4_rd_exp_flag | analyst4 | 0.32 | 27.1‱ | 0.02 |
| debt_st | fundamental23 | 0.29 | 26.8‱ | 0.00 |
| anl69_roe_best_crncy_iso | analyst69 | 0.18 | 25.6‱ | 0.03 |
| anl9_scaleconversionflag | analyst9 | 0.09 | 35.0‱ | 0.03 |
| debt_lt_curr / cost_of_revenue | fundamental23 | -0.29 / -0.68 | 负 | 0.04 / 0.02 |

24 个候选的 |corr| **全部 ≤ 0.11**——相关性上完美，但 **Sharpe 最高只有 0.32**，没有一条能把基准从 1.41 推到 1.58。

### 9.1 结构性约束：主题宇宙里可提交的字段只剩 analyst 族

| 数据集 | 冷字段数（MATRIX cov≥0.5 α≤50） | 年龄 | 可提交 |
|---|---:|---|---|
| analyst15 | 1,719 | 1658d+ | ✅ |
| analyst7 | 1,048 | 1658d+ | ✅ |
| analyst10 | 588 | 865d | ✅ |
| analyst11 / 4 / 69 / 14 / 9 | 309 / 349 / 153 / 114 / 56 | 500d+ | ✅（信号弱） |
| fundamental17 / 23 | 354 / 156 | 部分 1658d | ✅（信号弱） |
| **pv20 / pv30 / model26 / model50 / predictive_starmine / continuation_score / multifactor_return_pred / intraday_pv_feats / pattern_scores** | **30 / 31 / 144 / 65 / 222 / 272 / 89 / 156 / 156** | **227–409d** | ❌ 全部卡 LOW_DURATION |

**含义：想在 TOPCS1600 里找高收益腿，目前没有可用字段。** 价量/模型/短周期这几族（共 1,165 个冷字段）要等 3–9 个月跨过 500 天才可用，
届时才是「高收益腿 + analyst15 高 Margin 腿」组合的正确时机。
