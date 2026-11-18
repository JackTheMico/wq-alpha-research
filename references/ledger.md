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
| EUR | ai_news_scores | **CLOSED** | 0.71（`ts_decay_linear(rank(-F),20)`） | 信息半衰期 1 天：任何减速都杀掉信号；换手恒定 148–175%（覆盖空缺驱动）；backfill 降 TO 但符号翻转 −0.30。8 轮 40 条实测，S 天花板 0.71 vs 门槛 1.58 | §20 |
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
| **GLB** | **model109 加工比率 + `ts_delta63` 快骨架** | **BLOCKED** | **1.31**（FCF/EV）/ 0.87（EBIT/EV） | 总 S 账本最高，但 **AMER 只有 0.32**（EMEA 1.00 / APAC 0.94）；基本面族 AMER 天花板 ≈0.68，混反转腿最高只到 0.66 | §17.7–17.9 |
| **EUR** | **analyst15（`anl15_bps_gr_18_m_mean` / `..._cal_fy3_mean`）** | **ACTIVE** | **1.35**（旧双平滑 d200），2Y **2.20**、SubU 1.46 | — **EUR 唯一能供 ladder 的族**；已占住三条 ACTIVE 的载体位 | §18.5 |
| **EUR** | `cashflow_op/assets` | **BLOCKED** | 1.28 | **2Y 天花板 0.92–1.04**（独立复现§11.1 的 0.95），距 1.58 差 0.55，整族在 EUR 永久排除 | §18.4 |
| **EUR** | `est_12m_sal` / `est_12m_ebt` 修正族 | **OPEN** | — | 与 `vRAa38Jb` 相关仅 0.43，是压相关的主要配重来源；已作为 0.35 权重进 `npaZdvR3` | §18.10 |
| **EUR** | `enterprise_value` 作分母 | **CLOSED** | 0.12 | 覆盖率 0.737 是硬伤，SubU 直接 −0.20；EUR 无 model109，自算比率必撞覆盖 | §18.3–18.4 |

> **EUR 已出货的结构（第四条要避开）**：`vRAa38Jb` 0.62 a15 + 0.38 sal / `6XM3GqWp` 0.48 a15 + 0.52 cfo
> / `npaZdvR3` 0.50 fy3 + 0.35 sal + 0.15 cfo（sector 分组）。四条必须同时避开 a15 高权重、cfo ≥0.4、sal ≥0.5。

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
| EUR | ai_news_scores | `negative_score_confidence_upper_bound_2`（原式 `-rank(...)`，`j2a191MW`） | 0.59 | TO 164% / F 0.09 / 2Y 0.22；唯一 PASS 是 SubU | CLOSED | §20 |
| EUR | ai_news_scores | 同上 `ts_decay_linear(rank(-F),20)` SUBIND（`pwa88KaX`） | **0.71** | 族内最高 S，但 TO 149.6% 撞上限；MARKET 中性化反而 −0.14 | CLOSED | §20 |
| EUR | ai_news_scores | `ts_mean(rank(pos_avg-neg_avg),5)`（`RReddgMz`） | 0.62 | 形态最优（TO 57% / DD 4.6% / 2Y 1.00）但幅度差 0.96；纯幅度问题非鲁棒性问题 | CLOSED | §20 |
| EUR | ai_news_scores | `rank(-neg_avg)` / `rank(pos_avg)` / `rank(-neut_avg)` | 0.50 / **−0.47** / **−0.53** | 三腿同指「有无新闻」=关注度折价；合成 `-rank(pos+neg)` 仅 0.53，不优于单腿 | CLOSED | §20 |
| EUR | ai_news_scores | `rank(-ts_backfill(F,20))` | −0.30 | TO 36.3% 但符号翻转：新鲜坏消息动量、陈旧坏消息反转 | CLOSED | §20 |
| EUR | ai_news_scores | `trade_when(F>0, rank(-F), -1)` 持仓保持 | −0.22 | 直接验证"信号只活 1 天"，持有即变反向暴露 | CLOSED | §20 |
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

## 10. 引入「不冷门但信号强」的腿 + zscore 归一化（2026-11-14）

### 10.1 高 αCount 字段单腿（26 条，ATOM 20v250 + decay150）

| 字段 | 数据集 | αCount | S | Margin | 与基准 corr |
|---|---|---:|---:|---:|---:|
| **est_12m_sal_raised_1wk** | analyst7 | 1011 | **1.26** | 29.6‱ | **0.02** |
| est_12m_ebt_raised_1wk | analyst7 | 1011 | 1.20 | 29.8‱ | 0.03 |
| anl69_best_eeps_nxt_yr | analyst69 | 3908 | 0.86 | 95.8‱ | 0.07 |
| close | pv1 | 2392 | 0.54 | 85.1‱ | 0.05 |
| cap / adv20 | pv1 | 1277 / 504 | 0.19 / 0.21 | 29 / 17‱ | 0.03 / 0.04 |

热门字段并不等于拥挤失效：`est_12m_sal_raised_1wk` 被 1,011 个 alpha 用过，
单腿仍有 1.26，且与我们的基准 **corr 0.02**。

### 10.2 组合的第一课：等权 = 自残

| 混合 | S | F | Margin | 与基准 corr |
|---|---:|---:|---:|---:|
| 0.6×基准 + 0.4×sal（原始尺度） | 1.28 | 1.02 | 113.5‱ | 0.97 |
| 0.6×基准 + 0.4×anl69 | 1.34 | 1.12 | 123.2‱ | 0.91 |
| 0.5×rank + 0.5×rank(sal) | 1.19 | 0.70 | 45.8‱ | — |
| **0.7×zscore + 0.3×zscore(sal)** | **1.58** | **1.33** | 97.7‱ | — |

原始尺度等权把 Sharpe 从 1.41 拉到 1.28–1.34（两腿波动率不同，权重不是风险权重）；
`zscore` 归一化后才真正实现分散收益（1.58）。**rank 反而更差**（1.19）——rank 抹掉了幅度信息。

### 10.3 最终参数（`zqdX6a0R`）

```
group_neutralize(0.62*zscore(atom(anl15_bps_gr_18_m_mean))
               + 0.38*zscore(atom(est_12m_sal_raised_1wk)), country)
EUR/TOPCS1600/d1, MARKET, decay=150, truncation=0.05
```

| 配置 | S | F | TO | Margin | DD | Ret |
|---|---:|---:|---:|---:|---:|---:|
| 0.65/0.35 | 1.61 | 1.35 | 1.9% | 92.5‱ | 11.3% | 8.8% |
| 0.62/0.38 | 1.64 | 1.37 | 1.9% | 89.5‱ | 10.9% | 8.7% |
| **0.62/0.38 + trunc 0.05** | **1.62** | **1.27** | 1.9% | 79.5‱ | **7.6%** | **7.7%** |
| 0.65/0.35 + trunc 0.04 | 1.56 | 1.19 | 1.9% | 76.8‱ | 6.7% | 7.2% |

**`zqdX6a0R` 首次全绿**：Sharpe 1.62 ≥ 1.58、SubU PASS、IS_LADDER 2.02/2.02 PASS、
DD 7.6% < Ret 7.7%、Margin 79.5‱、数据 1658 天。唯一未过的是本地质量线 Fitness ≥ 2.0。

> **Fitness 对低换手 alpha 结构性不可达**：平台公式 `F = Sharpe × sqrt(|Ret| / max(TO, 0.125))`，
> 当 TO ≈ 2% 时 `F = S × sqrt(Ret/0.125)`，要 F≥2.0 需 Ret ≈ 19%（当前 7.7%）。
> 即这条 2.0 质量线对低换手族等同于「Ret ≥ 19%」，应改用 Margin ≥ 30‱ + DD < Ret 作为该族的等价质量判据。

### 10.4 提交实录：QUICK → FULL 复跑 + 主题 PASS 放行（2026-11-14）

| 步骤 | alpha | 结果 |
|---|---|---|
| QUICK 直接提交 | `zqdX6a0R` | ❌ `400 {"detail":"Cannot submit QUICK mode alphas"}` |
| FULL 复跑同表达式 | `vRAa38Jb` | 指标与 QUICK **完全一致**（S 1.62 / F 1.27 / TO 1.94% / Margin 79.5‱ / DD 7.58% < Ret 7.72%），约 4 分钟 |
| 提交 | `vRAa38Jb` | ✅ `ACTIVE`，`dateSubmitted=2026-11-14` |

提交后回算：`SELF_CORRELATION 0.1935`、`PROD_CORRELATION 0.5421`（均 PASS）；
`LOW_SHARPE 1.62/1.58`、`IS_LADDER_SHARPE 2.02/2.02`、`LOW_SUB_UNIVERSE_SHARPE 1.5/0.86` 全 PASS，
`CLUSTER_TEST 1.57/1.58` WARNING（差 0.01）。

三条经验：

1. **QUICK 模式 alpha 一律不能提交**，必须用 FULL 重跑（指标可复现，不会漂移）。
2. **主题闸门不能「有 WARNING 就阻断」**：本 alpha 的 `MATCHES_THEMES` 同时有
   PASS（`EUR/D1 TOPCS1600` x2 + `EUR/D1/ANALYST Pyramid` x1.3 = x2.3）与
   WARNING（`GLB/D1 Power Pool` x1）。WARNING 只是「那条主题不适用」，命中任一主题即应放行。
3. **低换手族提交需显式 `--no-quality`**：Fitness 2.0 线结构性不可达（见上），
   等价判据是 Margin ≥ 30‱ 且 DD < Ret。

## 11. EUR/TOPCS1600 的第二条 alpha：2Y ladder 是硬约束（2026-11-14）

### 11.1 扫描结论：除 anl15 外，所有字段族的 2Y Sharpe 都在 0.1–1.1

全量扫过 analyst4 / analyst7 / analyst10 / analyst11 / analyst15 / analyst39 / analyst69、
fundamental17 / fundamental23 / pv1 后，`LOW_2Y_SHARPE`（= 提交时的 `IS_LADDER_SHARPE`）
只有两个字段族能过 1.58：

| 腿 | 全期 S | 2Y Sharpe | 结论 |
|---|---:|---:|---|
| `anl15_bps_gr_18_m_mean` | 1.12 | **1.73** | 唯一稳定过线 |
| `anl15_bps_gr_cal_fy3_mean` | 1.00 | 1.54 | 擦线，单腿不过 |
| `est_12m_ebt_raised_1wk` | 1.20 | 0.15 | 近两年衰减 |
| `est_12m_sal_raised_1wk` | 1.26 | 0.43 | 同上 |
| `anl69_best_eeps_nxt_yr` | 0.84 | 1.06 | 不够 |
| `cashflow_op/assets` | 1.28 | 0.95 | 不够 |
| `anl4_af_eps_mean` | 0.75 | 0.62 | 不够 |
| `fundamental17` 全族（EV/EBITDA、毛利、周转…） | ≤0.66 | 全部为负 | 全灭 |

**推论（硬约束）**：`vRAa38Jb` 已占住 anl15 的 0.62 权重。任何新 alpha 要过 2Y ladder，
anl15 权重大约需要 ≥ 0.5；而 anl15 权重 0.5 时与 `vRAa38Jb` 的日收益相关已是 **0.69**，
再高就会撞 `SELF_CORRELATION 0.7`。**2Y 过线与自相关过线在这个主题内只能同时满足于一个极窄的点。**

### 11.2 可用候选：0.5*anl15 + 0.5*CFO/Assets（FULL `mLae5RXp`）

```
group_neutralize(0.5*zscore(vector_neut(ts_mean(anl15_bps_gr_18_m_mean,20), ts_mean(...,250)))
               + 0.5*zscore(vector_neut(ts_mean(cashflow_op/assets,20), ts_mean(...,250))), country)
EUR/TOPCS1600/d1 · MARKET · decay=150 · truncation=0.05
```

| 指标 | 值 |
|---|---|
| Sharpe | 1.62 |
| Fitness | 1.40 |
| Turnover | 1.86% |
| Margin | 100.9‱ |
| Returns / Drawdown | 9.37% / 12.79%（**DD > Ret**） |
| IS_LADDER_SHARPE | **PASS 1.63 / 1.58** |
| 主题 | PASS x2.1（TOPCS1600 x2 + FUNDAMENTAL Pyramid x1.1） |
| 与 vRAa38Jb 相关 | **0.692**（距 0.7 仅 0.008） |

调参边界（FULL 实测）：decay=100 → ladder **1.57 FAIL**（`vRAajErA`）；
0.45/0.55 → ladder **1.55 FAIL**（`A1xq0GXw`）。50/50 + decay150 是唯一过线组合，
不要随意改权重或 decay。DD 12.8% 是该组合的固有代价，trunc 0.02/0.03 能把 DD 压到 9.7–10.8%，
但 S 同时跌到 1.54–1.57（不过线），无解。

### 11.2.1 实测：本地相关低估平台 SELF_CORRELATION 约 0.015

- `mLae5RXp`（50/50, decay150）本地 PnL 相关 **0.692** → 提交判定 `SELF_CORRELATION=0.7074`，**403 拒绝**（失败不消耗当日额度）。
- 降 anl15 权重救相关时 ladder 立刻掉：0.47→1.57 FAIL、0.48→1.58 FAIL（差 0.001）、0.46→1.56 FAIL。
- **可行解是「降权重 + 提 decay」**：`0.48*anl15 + 0.52*CFO`、**decay=200**（`6XM3GqWp`）→
  S 1.61 / F 1.40 / TO 1.74% / Margin 109‱ / ladder **PASS 1.62/1.61** / 本地相关 0.669，
  提交判定 `SELF_CORRELATION=0.6808` **ACTIVE**（2026-11-14）。
- 经验：想同时压相关和保 ladder，**动 decay 比动权重安全**（decay 100→200 只抬 ladder 不抬相关）；
  本地相关要留 ≥0.02 余量，平台口径比本地高约 0.015。

### 11.3 副产品：CFO/Assets 是本主题内最有价值的新核心

`cashflow_op/assets` 单腿 S 1.28 / Margin 61‱ / 与 `vRAa38Jb` 相关 0.16，
但 2Y 0.95，只能作为「配重」使用。凡是 2Y 弱的强腿（ebt 1.20、sal 1.26、net 1.17、a69 0.84），
与它混到 S 1.6+ 很容易，但 ladder 一定崩——**今后在 EUR 主题内筛选，先看 2Y，再看 Sharpe**。

## 12. EUR 主题「Sharpe 3 / Fitness 2」可行性探测（2026-11-15，全部 QUICK）

> 目标：主题内冷门字段 + 低 αCount 热门字段，冲击 S≥3 / F≥2。
> 结论：**在该主题内两者同时不可达**，原因是 Fitness 公式 + 2Y ladder + 70% 换手上限三者互斥。

### 12.1 先修正一个事实：EUR 的 pv1 有 24 个字段，不是 9 个

`references/fields_eur_topcs1600_delay1.json` 被截断在 10,000 行，漏掉 `open/high/low/volume/vwap/returns`。
用 API 直查（`GET /data-fields?region=EUR&universe=TOPCS1600&delay=1&instrumentType=EQUITY&dataset.id=pv1`，limit 必须 ≤50）：
`adjfactor adv20 cap close country currency cusip dividend exchange high industry isin low market open returns sector sedol sharesout split subindustry ticker volume vwap`。
**今后判断「字段不存在」前必须回 API 复核。**

### 12.2 Fitness 公式已实测确认

`F = S × sqrt(Ret / max(TO, 0.125))`（用 intra_sub：1.97×sqrt(0.105/1.0469)=0.62 完全吻合）。
推论：`S≥3 且 F≥2` ⇒ `Ret/max(TO,0.125) ≥ 0.444`。
EUR 实测最高 `Ret/TO = 10.5%/105% = 0.10`，差 4.4 倍；低换手族 TO≈2.3% 时需 S≥2.26 才有 F=2。

### 12.3 六条路线的实测天花板

统一 EUR/TOPCS1600/d1、trunc 0.05、QUICK。

| 路线 | 最优表达式（摘要） | S | F | TO | Margin | 2Y/ladder | 卡点 |
|---|---|---:|---:|---:|---:|---|---|
| 收盘价反转（5 日） | `rank(-ts_delta(close,5))` INDUSTRY decay0 | 1.47 | 0.52 | 60% | 2.5‱ | 1.12 FAIL | 2Y + margin |
| 冷门 surprise（anl10，10 个 aC=1 字段） | `rank(anl10_*_pred_surps_*)` INDUSTRY decay4 | 0.96 | 0.44 | 6.8% | 7.6‱ | 0.74 FAIL | 单腿太弱 |
| 慢腿多腿等权（6 腿 zscore） | `0.25a15+0.25cfo+0.2ebt+0.2sal+0.1a69` decay150 | **1.78** | **1.57** | 2.3% | 85.8‱ | ladder 1.50 FAIL | 与现有 alpha 相关 0.72/0.81 |
| **日内反转** | `group_neutralize(rank(-(close-open)/open), subindustry)` decay2 | **1.97** | 0.62 | **104.7%** | 2.0‱ | **1.67 PASS** | **HIGH_TURNOVER 0.7** |
| 日内 VWAP 反转 | `group_neutralize(rank(-(close-vwap)/vwap), subindustry)` decay0 | **2.19** | 0.63 | 127% | 1.6‱ | 1.47 FAIL | 换手 + 2Y |
| 日内×慢腿混合（0.5/0.25/0.25） | `0.5*intra+0.25*a15+0.25*cfo` decay2 | 1.85 | 0.62 | 85% | 2.2‱ | ladder 1.37 FAIL | 混合毁掉 2Y |

### 12.4 两个反直觉的硬事实

1. **日内反转的 2Y 优势极度脆弱**：decay=2 → 2Y 1.67 PASS；decay=3 → 1.30 FAIL；decay=10 → 0.41。
   任何降换手的平滑（`ts_mean(...,2)` → 1.49、`ts_mean(...,3)` → 0.72）都保不住 2Y。
   ⇒ 该族只能以 decay≤2、TO≈105% 运行，与 HIGH_TURNOVER 0.7 硬冲突，**无解**。
2. **`hump` 对 rank 类信号等于关灯**：`hump(rank(x), hump=0.02)` 直接 TO 0.9% / S −0.17
   （rank 的变化幅度小于阈值，几乎不再调仓）。降换手必须用 decay/平滑，不能用 hump。

### 12.5 低换手 F 线的四轮调参（2026-11-15，全部 QUICK）

基准组合 `CORE = 0.25a15 + 0.25cfo + 0.20ebt + 0.20sal + 0.10a69`（衰减器 `zscore(vector_neut(ts_mean(f,20), ts_mean(f,250)))`）。

| 轮次 | 变量 | 最优 S | 最优 F | Ret | TO | ladder | 结论 |
|---|---|---:|---:|---:|---:|---|---|
| F1 | trunc 0.02/0.08/0.12、decay 100/200/250 | 1.76 | **1.58** | 10.5% | 1.9% | 1.45–1.55 FAIL | 截断 0.08 与 0.12 完全相同（1600 只股票仓位远小于截断上限），Ret 天花板 ≈10.5% |
| F2 | 中性化分组 country/sector/industry/subindustry | 1.77 | **1.65** | 10.8% | 2.1% | 1.05 FAIL | sector 抬 F、降相关到 0.64，但 ladder 崩到 1.05 |
| F3 | `signed_power(CORE,k)` k=1.5/2/3/4 | 1.59 | 1.54 | 12.0% | 2.0% | 0.63–1.27 FAIL | Ret 能抬到 12%，S 掉得更快，F 不升 |
| F4 | 去掉 a15 改用 a15fy3 重新配权 | 1.64 | 1.41 | 9.4% | 1.9% | 1.2–1.53 FAIL | ladder 更差 |

**F 在 EUR 低换手族的实际上限 ≈1.65**。原因：`F = S×sqrt(Ret/0.125)`，
TO≤2.1% 时 Ret 最多 10.8%，要 F=2 必须 **S≥2.24**；而 EUR 所有族的低换手 S 最高 1.78。

**唯一 ladder 过线的组合**：6 腿等权 `c6eq`（a15/a15fy3/cfo/ebt/sal/a69 各 1/6）
→ S 1.68 / F 1.45 / ladder **2.03 PASS**，但与 `vRAa38Jb`/`6XM3GqWp` 相关 **0.78/0.77**，被 SELF_CORRELATION 卡死。
降 a15 权重救相关的每一步都会把 ladder 打下 1.58（0.25→1.50、0.2→1.48、a15fy3 替代→1.2–1.53）。

### 12.6 结论与下一步

- 主题内 **S≥3 不可达**；**F≥2 也不可达**（低换手族需 S≥2.26，EUR 目前最高 1.78，且该点相关 0.72 超线）。
- 唯一「2Y 过线 + S 1.97 + 相关≈0」的腿是日内反转，但被 70% 换手上限卡死。
  若平台/主题允许 TO>70%，它是现有最优候选；否则本主题已挖尽。
- 想要 S≥3，必须换到数据完整的区域：USA TOP3000 有实证先例
  `0.3ROE+0.2mdl77动量+0.5反转` decay5 → **S 3.15 / F 2.19 / TO 34.3%**（empirical-log §2026-08-16）。
  GLB/D1 Power Pool（x1.0）次之，但需 AMER Sharpe>1，且 §17 实测 GLB 反转 2Y 仅 1.08。

## 13. GLB rev25/rev20 家族的 Fitness 天花板（2026-11-15，全部 QUICK）

> 问题：能否把 `rev25_d8`（`9qlKRLeK`，S 1.68 / F 1.09 / TO 14.54% / Ret 6.14% / Mar 8.5‱）
> 的 Fitness 推过 2.0？
> 结论：**不能。该家族 F 的实测天花板 ≈1.13，F≥2 需要 Margin 提高 3.3 倍，五条杠杆全部被证伪。**

### 13.1 Fitness 换算到 Margin，一眼看出差距

由 `F = S × sqrt(Ret / max(TO,0.125))` 且 `Ret = Mar × 2 × TO × 252`（Mar 为单边 bps），
在 `TO > 12.5%` 区间有：

```
F = S × sqrt(Mar_bps / 10000 × 504)
```

因此固定 S=1.68 时：

| 目标 F | 所需 Margin | 相对当前（8.5‱） |
|---:|---:|---:|
| 1.5 | 15.8‱ | 1.9x |
| **2.0** | **28.1‱** | **3.3x** |
| 2.5 | 43.9‱ | 5.2x |

等价的三条可行解：`S 不变 → Ret 需 17.7%`（2.9x）；`Ret 不变 → S 需 2.85`（+70%）；
`S=2.00 → Ret 需 12.5%`（2.04x）。三条都远超该家族实测能力。

### 13.2 五条杠杆的实测结果

统一 GLB/TOP3000/d1/COUNTRY/trunc 0.08、QUICK。基准 `rev25_d8` = S 1.68 / F 1.09 / TO 14.54% / Mar 8.5‱。

| # | 杠杆 | 配置 | S | F | TO | Margin | ladder | 判定 |
|---|---|---|---:|---:|---:|---:|---|---|
| — | 基准 | decay 8 | 1.68 | 1.09 | 14.54% | 8.5‱ | 2.06/2.02 | — |
| A | 降换手到地板 | decay 12 | 1.61 | **1.08** | 10.79% | **10.5‱** | 1.64/1.61 | ❌ S 同步下滑，F 不变；ladder 逼近限 |
| A' | 降换手过冲 | decay 16 | 1.56 | **1.02** | 8.83% | 12.1‱ | 1.58/1.58 | ❌ 更差；ladder 压线，危险 |
| B | 放大截断 | trunc 0.15 | 1.68 | 1.09 | 14.54% | 8.5‱ | 2.06/2.02 | ❌ **与基准逐位相同**，仓位远未触截断上限 |
| C | 加第四腿（低应计） | +20% `-ts_rank(accruals_percentage_earnings,252)` | 1.69 | 1.09 | 12.56% | 8.3‱ | 1.74/1.61 | ❌ S 仅 +0.01，Ret 反降到 5.23%，ladder 崩 |
| D | 非线性集中 | `signed_power(2A-1, 1.5)` | 1.68 | 1.09 | 15.70% | 8.5‱ | 1.88/1.88 | ❌ F 完全不变，ladder 降 |

**五条杠杆的 F 全部落在 1.02–1.09 区间，无一超过基准。**

### 13.3 三个可复用的硬事实

1. **decay 已在该族的甜点上**：`rev25_d8` 的 TO 14.54% 恰好略高于 12.5% 计分下限。
   继续降 decay 只会把 TO 推入 `max(TO,0.125)` 的截断区——分母不再变化，而 S 与 Ret 同步下滑，
   **F 严格不升**。这与 §12.5 的 EUR 结论（TO≈2% 时 F 只由 Ret 决定）是同一机制的两端。
2. **truncation 对 rank 类多腿信号无效**：0.08→0.15 指标逐位相同。TOPM3000 的 2300 只持仓
   分散度远高于截断上限，截断不构成约束。**(§12.5 F1 在 EUR 也观察到同一现象)**
3. **加腿救不了 Fitness**：低应计腿虽然经济含义正交，但抬 S 只有 +0.01，且 Ret 下降
   （5.23% vs 6.14%），ladder 从 2.06 掉到 1.74。§12.5 的「加腿会摊薄 Margin」在 GLB 同样成立。

### 13.4 家族内真正的 F 最优解

`rev20_d8`（`LLK6prNv`，反转权重 20% + decay 8）是本家族最佳：

| alpha | 表达式要点 | S | F | TO | Ret | Margin | DD | ladder |
|---|---|---:|---:|---:|---:|---:|---:|---|
| **`LLK6prNv`** | 0.80×三腿 + 0.20×反转252，decay 8 | 1.66 | **1.13** | 11.98% | 5.75% | 9.6‱ | **3.7%** | 待 FULL |
| `9qlKRLeK` | 0.75×三腿 + 0.25×反转252，decay 8 | 1.68 | 1.09 | 14.54% | 6.14% | 8.5‱ | 4.2% | 2.06 PASS |
| `E5Qbkb31` | 0.75×三腿 + 0.25×反转252，decay 4 | 1.76 | 0.93 | 24.60% | 6.92% | 5.6‱ | — | 2.15 PASS |

`LLK6prNv` 的 F 1.13 更高、DD 更低，但 **EMEA 尚未在 FULL 下验证**（反转权重 0.20 处于
0.15→0.25 的 EMEA 过线区间内，风险低于 0.25 版本，但仍需实测）。

### 13.5 对「Fitness ≥ 2.0」质量线的处置

- 该家族 F 上限 ≈1.13，**结构性够不到 2.0**，与 §10.3 的低换手族结论一致。
- 同时 **Margin 也只有 8.5–10.5‱，够不到本地质量线的 10‱**（只有 decay 12 的 10.5‱ 过线，
  但它的 F 只有 1.08 且 ladder 压线）。因此这条 alpha 按本地质量闸门是 **NO-GO**，
  需显式 `--no-quality` 才能提交。
- **若确实要 F≥2**，唯一有实证先例的路径是**换区域**：USA/TOP3000
  `0.3ROE+0.2mdl77动量+0.5反转` decay5 → **S 3.15 / F 2.19 / TO 34.3%**（empirical-log §2026-08-16）。
  GLB 主题内不存在第二个解。

## 14. GLB 候选 FULL 定论：`rev25_d8` 全绿，`rev20_d8` 差 0.01（2026-11-15，FULL）

### 14.1 `rev20_d8` 的 EMEA 只有 0.99，且换手率已进计分地板

`rev20_d8`（`LLK6prNv` → FULL `88Nrpx57`）指标与 QUICK 逐位一致
（S 1.66 / F 1.13 / TO 11.98% / Ret 5.75% / Mar 9.6‱ / DD 3.66%），
但 **`LOW_GLB_EMEA_SHARPE` = 0.99 / 1 → FAIL**，差 0.01。AMER 1.21 PASS、APAC 1.09 PASS。

### 14.2 重要修正：Power Pool 通道对该族永久关闭

`MATCHES_THEMES` = WARNING，两个主题（`GLB/D1 Power Pool Nov'26` x1.0、`EUR/D1 TOPCS1600` x2.0）
**一个都没命中**。原因不是 EMEA，而是 §5.1.2 的复杂度约束：

> Power Pool 要求**唯一数据字段 ≤ 3、算子 ≤ 8**。本族用 6 个字段
> （`fnd17_fcf1a` `fnd17_ev_cur` `fnd23_ofc` `fnd23_roe` `cap` `returns`），
> 无论怎么调参都不可能命中 PP 主题。

⇒ **本族只能走 Regular 通道**，硬门槛是 Sharpe ≥ 1.58 + 三子区 ≥ 1（不是 PP 的 Sharpe ≥ 1.0）。
`MATCHES_THEMES` 的 WARNING 在这里是**结构性**的，不是可优化的对象。

### 14.3 EMEA 的经验模型：只由反转权重决定，与 decay 无关

用三条 FULL 数据点回归：

| 配置 | 反转权重 w | decay | EMEA | Fitness |
|---|---:|---:|---:|---:|
| `LLK6n5pe` | 15 | 4 | 0.96 | 1.06 |
| `E5Qbkb31` | 25 | 4 | 1.02 | 0.93 |
| `88Nrpx57` | 20 | 8 | 0.99 | 1.13 |

拟合结果（三点精确解，残差为 0）：

```
EMEA    = 0.87 + 0.006 × w        （decay 系数 = 0）
Fitness = 1.12 - 0.013 × w + 0.03375 × d
```

**两条可复用的结论**：

1. **decay 对 EMEA 无影响**（系数精确为 0）。此前「decay 对该族 EMEA 单调有害」的推断是错的——
   那条证据（checks.md §335，0.73→0.14）来自另一个结构、且 decay 跨度到 10 以上。
2. **要 EMEA ≥ 1.00 必须 w ≥ 21.7**。这解释了为什么 `rev20_d8`（w=20）卡在 0.99，
   而 `rev25_d8`（w=25）能到 1.02。

### 14.4 `rev25_d8` FULL：全部数值检查 PASS

`rev25_d8`（`RReYVQVj`）GLB/TOP3000/D1/COUNTRY/decay 8/trunc 0.08：

| 指标 | 值 | 闸门 | 结果 |
|---|---:|---|---|
| Sharpe | 1.68 | ≥ 1.58 | PASS |
| Fitness | 1.09 | ≥ 1.0（平台） | PASS |
| Turnover | 14.54% | 1%–70% | PASS |
| Margin | 8.5‱ | 本地质量线 ≥ 10‱ | **未过** |
| Drawdown | 4.19% | < Returns 6.14% | PASS |
| Sub-universe | 1.54 | ≥ 1.03 | PASS |
| IS_LADDER | 2.06 | ≥ 2.02 | PASS |
| **AMER** | **1.21** | ≥ 1 | **PASS** |
| **EMEA** | **1.02** | ≥ 1 | **PASS** |
| **APAC** | **1.16** | ≥ 1 | **PASS** |
| CLUSTER_TEST | 0.77 | ≥ 1.58 | WARNING（不阻断） |
| SELF_CORRELATION | 本地 proxy 0.451（平台口径 ≈0.47） | < 0.7 | 预估 PASS |
| PROD_CORRELATION | 未回算 | < 0.7 | 提交后才知道 |

**这是 ledger 首次记录到「GLB 候选在 FULL 下 AMER / EMEA / APAC 三子区全部 ≥1」。**
此前 §4 的「GLB 结构性不可达」判断，限定条件是 SUBINDUSTRY/MARKET 中性化 —— 换成
**settings 级 COUNTRY 中性化 + 基本面为主体 + 25% 慢反转**即可打破。

### 14.5 剩余风险与提交口径

1. **Margin 8.5‱ < 本地质量线 10‱**：按 `gate_report` 是 NO-GO，需显式 `--no-quality`。
   该族的 Margin 上限实测 10.5‱（decay 12），但那会牺牲 Sharpe 且 ladder 压线。
2. **CLUSTER_TEST 0.77 偏低**（EUR 那条是 1.57）。属 WARNING 不阻断，但说明集群内表现弱。
3. **PROD_CORRELATION 无法本地预估**，只能提交后回算。
4. 提交前必须 FULL（QUICK 一律 400 拒绝）；FULL 单条 GLB 约 480s。

**结论：`RReYVQVj` 是本账户第一条 IS 全绿的 GLB 候选，可提交（待用户显式授权）。**

## 15. `RReYVQVj` 提交实录：被 PROD_CORRELATION 0.7283 拦下（2026-11-15）

### 15.1 提交过程与判定

`RReYVQVj`（rev25_d8）FULL 全绿后按用户显式授权提交。平台层复核
（`gate_report(quality=False, theme=False, strict=True)`）= **GO**，主题与质量闸门已按用户决定显式关闭。

```
POST#1  201 Retry-After=1.0
POST#2..#13  200 Retry-After=1.0（反复 POST 同一端点，共约 15 次 / 15s）
POST#14 403  判定书: PROD_CORRELATION=0.7283 (limit=0.7)
```

结果：`status = UNSUBMITTED`、`dateSubmitted = None` —— **提交被拒，未占用当日 1 条配额**。
（`SELF_CORRELATION` 本地 proxy 0.451，未成为问题。）

### 15.2 这个数字的含义

PROD_CORRELATION 是 alpha 日收益与**平台生产池全部 alpha** 的相关性，只能提交时回算。
0.7283 vs 0.7 —— **只超 0.028**，属于「擦线失败」而非「结构性撞车」。

但它暴露一个事实：`价值(FCF/EV, OFC/cap) + 质量(ROE) + 252 日反转` 这个组合在 GLB/TOP3000
是非常标准的因子配方。preflight 的字段拥挤度先验显示 LOW（最拥挤的 `fnd23_roe` 只有 111 个 alpha），
**说明高 prod corr 不是「字段被用烂」，而是「信号形状太常见」** —— 换字段解决不了，得换信号结构。

### 15.3 由此得到的可复用经验（新增到 §5.2 的实践层）

1. **IS 全绿 ≠ 能提交**。PROD_CORRELATION 是本账户目前**唯一**无法本地预估的硬闸门，
   且它只与「信号是否常见」有关，与 Sharpe/Fitness 高低无关（本 alpha F 1.09 依然被拦）。
2. **擦线失败的处置**：0.7283 距离 0.7 仅 0.028，属于可抢救区。有效的降相关杠杆按预期收益排序：
   - 拉长反转腿窗口（252 → 504）或改 `ts_zscore`：改变持仓向量形状，不动 EMEA（EMEA 只由权重决定）
   - 换掉最常见的一条腿（ROE → 投资因子 `fnd23_capex` 或低应计）：改变信号空间
   - 加大非线性（`signed_power`）：改变权重分布 —— 但 §13.2 已证伪它抬不了 F，降相关仍可一试
3. **无效杠杆（已证伪，不要再试）**：truncation（§13.2 B）、加相似腿（§13.2 C）、decay 调参（§13.2 A）。
4. **每次尝试的迭代成本**：FULL 仿真约 480s + 提交探针约 15s。提交被拒不消耗配额，
   因此可以用「FULL → 提交探针」的低成本循环来测 PROD_CORRELATION。

## §16 GLB 抢救：PROD_CORRELATION 的可控下降路径（2026-11-15 晚）

### 16.1 结果：`vRA9OKM3` 提交成功 → ACTIVE

| 项 | 值 |
|---|---|
| alpha | `vRA9OKM3` |
| 表达式 | `0.75*(0.4*rank(ts_rank(fnd17_fcf1a/fnd17_ev_cur,252)) + 0.3*rank(ts_rank(fnd23_ofc/cap,252)) + 0.3*rank(ts_rank(fnd23_roe,252))) + 0.25*(1-group_rank(ts_rank(returns,252),subindustry))` |
| settings | GLB / TOP3000 / D1 / decay 8 / COUNTRY / trunc 0.08 / pasteurization ON |
| IS | S **1.92** / F **1.20** / TO 16.07% / Ret 6.28% / DD **2.83%** / Margin 7.8‱ |
| 子区 | AMER **1.35** / EMEA **1.09** / APAC **1.29** |
| ladder | 2.16（≥2.02 PASS）；SubU 1.73（≥1.18 PASS） |
| **PROD_CORRELATION** | **0.6766**（limit 0.7，**PASS**） |
| SELF_CORRELATION | 0.0 |
| dateSubmitted | 2026-11-15T04:50:35-05:00 |
| 残留 WARNING | CLUSTER_TEST 0.92 / MATCHES_COMPETITION / MATCHES_THEMES / OSMOSIS_ALLOCATION（均非阻断） |

对照被拒的原版 `RReYVQVj`：PROD_CORRELATION **0.7283 → 0.6766**，下降 0.052，跨过 0.7 线。

### 16.2 四条抢救变体的完整对照（全部 FULL）

| 变体 | 相对原版的改动 | S | F | TO | DD | ladder | AMER | EMEA | APAC | 判定 |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|
| 原版 `RReYVQVj` | — | 1.68 | 1.09 | 14.54% | 4.19% | 2.06 | 1.21 | 1.02 | 1.16 | prod 0.7283 拒 |
| `v1_rev504` `npaoPzlw` | 反转腿 252→504 | 1.69 | 1.10 | 14.53% | 4.08% | 2.05 | 1.21 | 1.02 | 1.16 | 全绿，未探 |
| **`v2_rev_grp` `vRA9OKM3`** | 反转腿改 `subindustry` 组内相对 | **1.92** | **1.20** | 16.07% | **2.83%** | **2.16** | **1.35** | **1.09** | **1.29** | **ACTIVE** |
| `v3_capex` `lea2Mjb8` | ROE 腿 → `-ts_rank(fnd23_capex/cap,252)` | 1.03 | 0.60 | 14.58% | 7.09% | — | — | — | — | 崩，弃 |
| `v4_allgrp` `kqaXJYGg` | 全部五腿改组内 rank | **2.13** | **1.28** | 14.33% | **2.19%** | **1.53 FAIL** | 1.77 | **0.57 FAIL** | 1.27 | 双 FAIL，弃 |

### 16.3 可复用的三条结论

**1）降 PROD_CORRELATION 的有效杠杆是「改变比较基准」，不是「改变回看窗口」。**

`v1` 把反转窗口 252→504，S/F/TO/DD 与原版几乎逐位相同（1.69 vs 1.68、14.53% vs 14.54%、DD 4.08% vs 4.19%），说明信号几乎没变——这类「同族平移」对 prod corr 预期无效。真正起作用的是 `v2`：把反转腿从「全球横截面 `ts_rank`」改为「`subindustry` 内相对排名」，持仓向量被重塑，prod corr 才降下来。

**推论**：判断某个改动能否降 prod corr，先看它是否让 IS 指标（尤其 Sharpe/DD）发生可观测变化。若指标几乎不动，说明信号空间没动，改也是白改。

**2）「行业内相对反转」在 GLB 上全面优于「全局反转」。** `v2` 相对原版：S +0.24、F +0.11、DD 从 4.19% 压到 2.83%、EMEA 从 1.02 抬到 1.09（安全边际 0.02→0.09）、APAC +0.13、AMER +0.14、ladder +0.10。这不是取舍，是纯增益。此前把反转腿固定成全局 `ts_rank(returns,252)` 属于过早收敛。

**3）基本面腿不能组内化。** `v4` 把三条基本面腿也改成 `group_rank(...,subindustry)` 后，S 冲到 2.13、DD 2.19%，但 **ladder 1.53（<1.58）与 EMEA 0.57（<1）双 FAIL**。

顺带修正 §14.3 的 EMEA 模型边界：`EMEA = 0.87 + 0.006×w` 只在**全局反转**形态下成立。组内形态下该模型预测 1.02、实测 0.57（基本面腿全组内）或 1.09（仅反转腿组内），说明模型的隐变量不只是「反转权重」，还包括「跨市场可比性」——基本面腿一旦组内化，就丢掉了国别间的相对估值信息，EMEA（多国、行业内差异小）最先受损。

### 16.4 流程成本实测

- FULL 单条：160–346 s（`v4` 最快 160 s，`v2` 最慢 346 s）。
- 提交探针：15 次 POST，约 15 s；**被拒不消耗配额**，成功即占当日 1 条。
- 本轮从「被拒」到「提交成功」共 4 条 FULL（约 17 分钟）+ 1 次探针。

### 16.5 遗留

- `v1_rev504` `npaoPzlw`（S 1.69 / F 1.10 / 三子区全过）与 `v4_allgrp` `kqaXJYGg`（S 2.13 但 ladder/EMEA FAIL）仍是 UNSUBMITTED，可作后续素材。
- `v4` 的 2.13 说明该族在「组内基本面」方向有更高 Sharpe 潜力，但需要单独解决 ladder（1.53→1.58）与 EMEA（0.57→1）。可行方向：只把 1 条基本面腿组内化（折中），或对基本面腿组内后重新标定反转权重。
- Margin 7.8‱ 仍低于本地 10‱ 质量线；但平台无此检查，不影响提交。

## 17. ATOM 批量挖掘：从「换模板」转向「扩字段」（2026-11-15）

> 问题：如何从主题中挖出**更多** ATOM alpha。
> 结论：ATOM 产出量 ≈ 字段召回广度 × 骨架插槽数 × 通过率。骨架固定、无参数调优空间，
> **瓶颈在第一项**。此前反复"换模板 / 调 decay / 换中性化"都在第二项里打转。

### 17.1 删除 1095 天年龄上限（无实证依据）

`recommend_fields.py` 的 `BLUESEA_DAYS_MAX` 原为 1095 天（3 年），
但账本里唯一的硬约束只有 §6.3 的 **≥500 天下限**（LOW_DURATION），上限无任何证据支撑。

GLB/TOP3000 同一天快照实测：

| days_max | 召回字段 | 数据集 | 分布 |
|---:|---:|---:|---|
| 1095（旧） | **141** | 2 | analyst10 独占 95、analyst82 占 30 |
| 36500（新，≈不设限） | **3897** | 8 | analyst14 924 / fundamental28 923 / fundamental17 664 / fundamental23 447 / fundamental6 195 / fundamental72 99 / analyst10 95 / analyst82 30 |

- 候选集中在单一数据集时，产出的 ATOM 彼此同源，**会成批撞 SELF_CORRELATION**——
  这是"挖不出更多 ATOM"的真实机制，不是模板不够。
- 已改默认值并更新测试（commit `2bbdbae`）。「新」只用于排序，不再用于筛除。

### 17.2 字段级 `pyramidMultiplier` 是平台原值，但 1.4 是默认档

字段快照里的 `pyramidMultiplier` 是平台返回的倍率（区别于 `recommend_fields.py`
里 `1.0+0.8·exp(-αCount/30)` 的**估算值**，后者未经标定，只可作排序参考）：

| 区域 | 倍率分布 |
|---|---|
| GLB/TOP3000 | **1.4 占 73.7%**，1.3 占 22.6%，1.0 占 2.7% |
| EUR/TOPCS1600 | 1.3 占 79.2%，1.1 占 14.9%，1.5 占 3.6% |
| GBR/TOP700 | 1.5 占 44.9%，1.6 占 41.6% |

两条直接推论：

1. **GLB 的 1.4 不是稀缺资源**（73.7% 字段都有），「抢高倍率字段」在 GLB 不成立。
2. **`pv1` 全体字段倍率 = 1.0**（24 个字段）。反转族的 Sharpe 最高（1.67–1.88），
   但倍率最低且 prod corr 0.87–0.97（§4.1）⇒ **价格数据是性价比最差的 ATOM 场地**。
   §4/§15 在反转上反复受阻，根因是选错字段族，不是参数。

### 17.3 「低 αCount = 蓝海」证伪（重申 §4.1 的横向证据）

- §4.1：所有低 αCount 数据集（model140 仅 1 个 alpha、model37 21、model50 25、
  model28 29、model36 48、model16 56）单腿 **全部 CLOSED，S ≤ 0.68**。
- GLB/TOP3000 里 `αCount=0 且 coverage≥0.7` 的字段只剩 **3 个** ⇒ 「极度冷门」已不存在。
- §15.2：`vRA9OKM3` 族拥挤度先验全 LOW，prod corr 仍 0.7283。

⇒ 低 αCount 更可能是「信号弱 / 无人做出 alpha」而非价值洼地。
**选字段主排序应回到信号强度先验（数据集类别 + 字段语义），αCount 只作防撞车次级过滤。**

### 17.4 数据集级探针（8 族 × 20 条，QUICK）

骨架统一 `group_neutralize(vector_neut(ts_mean(F,20), ts_mean(F,250)), country)`，
GLB/TOP3000/D1、decay 0、MARKET、trunc 0.08、QUICK。字段筛选：
MATRIX + onboard ≥500 天 + coverage ≥0.5 + 排除计数/时间戳/衍生信号类。

目的不是出货，而是回答「哪个数据集的货能用」——命中率被数据集支配（§6.1 的教训），
一上来铺 3897 条是浪费额度。

### 17.4 实测结果：GLB 基本面慢变量 + ATOM 骨架 ≈ 零信号（负面结论）

20 条中 12 条拿到有效值（5 条 `Your simulation probably took too much resource`、
1 条轮询超 900s、2 条未跑到）。**全部 |S| ≤ 0.58，最佳 0.20：**

| 数据集 | 字段 | S | F | TO |
|---|---|---:|---:|---:|
| analyst14 | `anl14_high_ndebt_fy2` | **0.20** | 0.06 | 5.2% |
| fundamental28 | `fnd28_bdeq_value_03051q` | 0.18 | 0.05 | 3.2% |
| fundamental28 | `fnd28_bdeq_value_03245q` | 0.15 | 0.04 | 2.9% |
| fundamental17 | `fnd17_alldelay1_ata` | 0.12 | 0.03 | 2.1% |
| fundamental23 | `fnd23_intfvalld1_ilti` | 0.09 | 0.02 | 2.6% |
| analyst14 | `anl14_high_cfps_fy4` | 0.00 | 0.00 | 6.2% |
| fundamental23 | `fnd23_intfvalld1_iabs` | −0.27 | −0.13 | 3.8% |
| fundamental17 | `fnd17_alldelay1_atotse` | −0.43 | −0.22 | 2.0% |
| fundamental23 | `fnd23_intfvalld1_fcis` | −0.48 | −0.23 | 2.4% |
| fundamental28 | `fnd28_bdea_value_03506a` | −0.58 | −0.36 | 3.4% |

失败条目全是资源/超时，**不是**字段不可用（无 `unknown variable`）。

**三条诊断：**

1. **TO 全部落在 2–6%**，说明信号几乎不动——`vector_neut(ts_mean20, ts_mean250)`
   在这类字段上输出接近常数。
2. **入选字段本质是"绝对金额"**（`fcis` 融资现金流、`iabs` 无形资产、`ata` 总资产、
   `spvba`）。绝对金额是**规模代理**，跨市场不可比；`group_neutralize(country)`
   只做均值中性，不消除尺度差异。这与 §16.3「基本面腿一旦组内化就丢掉跨国可比性，
   EMEA 最先受损」是同一根因的两个侧面。
3. 对照 §4 的既有结论：GLB 的 ATOM 模板（model109 FCF/EV，**比率型**字段）S 1.03，
   是本次最佳值的 5 倍。**差别不在骨架，在字段是否已做尺度归一化。**

⇒ **「GLB 主题内，原始金额字段 + ATOM 20v250」这条路关闭。** 与 §4 的
「单数据集 GLB ATOM 在本批字段池内不可行」一致，本次是独立复现。

**未验证但成本最低的下一步**：同一批字段换成尺度无关骨架——
`group_neutralize(ts_rank(F,250), country)` 或 `group_rank(F/cap, subindustry)`。
判据：若 TO 仍 <10% 且 |S| <0.5，则 GLB ATOM 彻底关闭，应转 EUR/USA。

### 17.5 尺度归一化对照实验：TO 未动 ⇒ 归一化不是杠杆（关键更正）

§17.4 把低 Sharpe 归因于「绝对金额 = 规模代理」，推测归一化能救。本节点用
**同字段、同骨架、只改 F** 的对照实验验证该推测。**推测被证伪。**

设计：取 §17.4 有结果的 6 个字段，分三种归一化，骨架一字不改
`group_neutralize(vector_neut(ts_mean(F,20), ts_mean(F,250)), country)`，
GLB/TOP3000/D1、decay 0、MARKET、trunc 0.08、QUICK。共 6 条，0/6 达标。

| 字段 | 归一化 | S 前→后 | TO 前→后 | F |
|---|---|---:|---:|---:|
| `fnd28_bdeq_value_03051q` 短债 | ÷cap | 0.18 → **0.56** | 3.2% → 3.9% | 0.39 |
| `fnd17_alldelay1_atotse` 股东权益 | ts_rank | −0.43 → 0.09 | 2.0% → 3.1% | 0.01 |
| `anl14_high_cfps_fy4` CFPS 预测 | ÷close | 0.00 → 0.04 | 6.2% → 4.3% | 0.01 |
| `fnd23_intfvalld1_iabs` EPS | ÷close | −0.27 → 0.01 | 3.8% → 4.8% | 0.00 |
| `fnd23_intfvalld1_fcis` 投资现金流 | ÷cap | −0.48 → −0.01 | 2.4% → 3.5% | −0.00 |
| `fnd17_alldelay1_ata` 总资产 | ts_rank | 0.12 → −0.08 | 2.1% → 3.1% | −0.01 |

**决定性证据是 TO 列，不是 S 列。** 归一化后 6 条 TO 全部落在 3.1%–4.8%，
与归一化前的 2.0%–6.2% 是同一区间。TO 是信号活动度的直接度量——**TO 不动，
说明信号本身没变快，只是数值被重新标定**。S 的上下摆动（−0.48→−0.01、
0.18→0.56）是标定后的噪声重排，不构成方向性改善。

**更正 §17.4 的归因**：「规模污染」只解释了数值不可比，**不是** Sharpe 低的原因。
真正的锁在骨架：`ts_mean(·,20)` 对 `ts_mean(·,250)` 做 `vector_neut`，
两端都是重平滑量，残差的时序变化率被结构性压死在 2–5%。换任何字段、
做任何归一化，只要是慢变量输入，这个上限都在。§17.4 的诊断 1（TO 2–6%）
才是根因，诊断 2（金额=规模）是伴随现象。

**第四个独立复现**：本批 `fnd23_intfvalld1_fcis / cap`（投资现金流/市值）S −0.01，
与 §4.1 第 196 行 `ts_backfill(fnd23_ofc/cap,60)` S 0.09 同量级。而
**同一经济含义**的 model109 现成字段 `FCF_EV` 在同骨架下 S 1.03（§4.1 第 141 行）。
⇒ 分野不在「是否比率化」，在**字段来自加工数据集还是原始财报拼装**。
推测原因：① `cap` 每日变动、`fnd23` 是低频快照，比值的高频成分全部来自分母，
等价于反向价格因子，再被 `ts_mean(20)` + `vector_neut` 削掉；
② model109 是第三方算好并对齐过行业/异常值/时点的字段，信噪比原生更高；
③ GLB 非美公司财报口径不一，原始字段的可比性差。

**结论**：**GLB「原始财报字段（fundamental17/23/28、analyst14）+ ATOM 20v250」整族关闭**，
与归一化方式无关。GLB 能出 Sharpe 1.5+ 的只有两条已知路径——价格反转族
（S 1.67–1.88，但 TO 45–61%、2Y 过不了）与 model109 加工字段（S 1.03，AMER 0.68 不足）。

**下一步不再是挖字段**：§4.1 第 146 行「纯 PP 候选 B」——
`model109 FCF_EV` 慢腿 + `pv1 REV252` 反转腿加权组合，
S 1.65 / AMER 1.01 / EMEA 1.40 / APAC 1.20 / Ladder PASS / Fitness 0.80，
是账本内**唯一三子区全过且状态 OPEN 的 GLB 候选**，唯一未知项是 PROD_CORRELATION。
该检查只能提交时回算、被拒不耗额度，应直接推去测，而不是继续消耗 QUICK 额度换字段。

### 17.6 模板扫描：TO 死锁的解法是 `ts_delta`（本账本首次换手抬升不牺牲 Sharpe）

§17.5 认定瓶颈在骨架而非字段，本节点**固定字段只换骨架**验证。字段固定为
`fnd28_bdeq_value_03051q / cap`（§17.5 六条里唯一 |S|>0.5 者），基线 T0 为 §17.5 的
ATOM 20v250：S 0.56 / F 0.39 / TO 3.9%。设置回收 GLB/TOP3000/D1、decay 0、MARKET、trunc 0.08、QUICK。

| 模板 | 骨架 | S | F | TO | vs 基线 |
|---|---|---:|---:|---:|---:|
| **T1 ts_delta63** | `group_neutralize(ts_delta(F,63), country)` | **0.63** | **0.48** | **13.8%** | **+253%** |
| T6 慢腿+反转 | `0.6*rank(ts_zscore(F,250)) + 0.4*rank(-ts_rank(returns,252))` | 0.49 | 0.10 | 71.9% | +1742% |
| T3 均线变化63 | `group_neutralize(ts_delta(ts_mean(F,20),63), country)` | 0.48 | 0.33 | 5.5% | +40% |
| T7 变化+反转 | `0.7*rank(ts_delta(F,126)) + 0.3*rank(-ts_rank(returns,252))` | 0.16 | 0.02 | 51.1% | +1211% |
| T4 行业内排名 | `group_rank(F, subindustry)` | 0.14 | 0.03 | 2.1% | −47% |
| T5 时序分位中心 | `group_neutralize(ts_rank(F,250)-0.5, country)` | −0.05 | −0.01 | 9.8% | +150% |
| T2 ts_zscore250 | `group_neutralize(ts_zscore(F,250), country)` | 0.02 | 0.00 | 8.8% | +127% |

**四条结论：**

1. **TO 死锁可解。** T1 把 TO 从 3.9% 抬到 13.8%（3.5 倍），同时 S 0.56→0.63、
   F 0.39→0.48 —— **三项同向改善**。这是本账本内第一次出现「换手抬升不牺牲 Sharpe」，
   推翻了此前「GLB 慢变量必然低换手低 Sharpe」的悲观判断。

2. **唯一有效的改法是去掉二次平滑。** T1 = 直接取 63 日差分，中间不经过 `ts_mean`。
   T2 / T5 也抬了 TO（+127% / +150%），但 S 归零——**它们的额外换手是噪声不是信号**，
   说明「抬换手」本身不是目的。T3 在 T1 基础上多套一层 `ts_mean(20)`，S 掉到 0.48、
   TO 回落到 5.5%，反向印证：**每加一层平滑就吃掉一截信号**。

3. **裸反转腿不能用于 PP。** T6/T7 换手 51–72%。§4.1 候选 A/B 记的 18–25% 是加 decay
   之后的结果，裸腿在 51–72%，在这个量级会直接撞 PP 换手约束与 2Y 稳定性检查。

4. **T4 组内化把 TO 降了 47%（2.1%）**，确认 §16.3：组内化降低的是截面离散度，
   不是时序速度，**不能用来治换手**，两者是正交的两个维度。

⇒ 下一轮应把 T1 换成加工数据集（model109）强字段，检验快模板能否把 S 推到 AMER>1 量级。

### 17.7 快模板 × model109 加工字段：GLB 单腿新高 S 1.31 / F 0.85

把 §17.6 胜出的 `group_neutralize(ts_delta(F,63), country)` 套到 model109（第三方加工数据集，
覆盖率 0.81–0.84），F 统一加 `ts_backfill(F,60)`。8 条 QUICK：

| 字段 | αCount | S | F | TO | 2Y (≥1.58) |
|---|---:|---:|---:|---:|---|
| **`free_cash_flow_to_enterprise_value`** | 39 | **1.31** | **0.85** | 10.8% | **1.81 PASS** |
| 同上 + subindustry 组内化 | 39 | 1.14 | 0.64 | 10.5% | 1.37 FAIL |
| `free_cash_flow_yield` | 19 | 1.09 | 0.61 | 11.3% | 1.27 FAIL |
| 同上 + 窗口 126 | 39 | 0.98 | 0.53 | 7.0% | 1.70 PASS |
| `ebit_to_enterprise_value_ratio` | 3 | 0.87 | 0.57 | 14.0% | **2.01 PASS** |
| `operating_cash_flow_return_on_equity` | 4 | 0.78 | 0.39 | 7.1% | 0.66 FAIL |
| `ebitda_to_enterprise_value` | 5 | 0.61 | 0.30 | 15.8% | 1.44 FAIL |
| `revenue_to_enterprise_value` | 8 | 0.59 | 0.31 | 17.7% | 0.96 FAIL |

**五条结论：**

1. **GLB 单腿新高**：`FCF/EV + ts_delta63` 得 S 1.31 / F 0.85 / TO 10.8% / DD **6.35%** /
   2Y 1.81 PASS / SubU 1.0 PASS。对比 §4.1 第 141 行**同一字段的旧模板**
   （ATOM 20v250）S 1.03 / TO 2.8% —— 换骨架后 S +27%，且 TO 从 2.8% 升到 10.8%
   仍在低换手区间。**这是本账本内 GLB 最强的单腿。**

2. **字段决定 Sharpe，模板决定换手。** 同一模板下 8 个字段 S 从 0.59 到 1.31（2.2 倍差），
   而 TO 全部落在 7–18% —— 模板把换手统一抬上来之后，**剩下的差异完全由字段解释**。
   §17.4/§17.5 之所以结论悲观，是因为旧模板把 TO 压在 3%，任何字段都没机会表现。

3. **S 与 2Y 不同序**：`EBIT/EV` S 只有 0.87 但 2Y 2.01（最稳）、αCount 仅 3（最不拥挤）；
   `FCF/EV` S 1.31 但 2Y 1.81。若 PP 的 2Y 检查最难过，EBIT/EV 反而是更稳的底料。

4. **组内化伤 2Y**：同一字段加 `group_rank(..., subindustry)` 后 S 1.31→1.14、
   2Y 1.81→1.37（FAIL）。与 §16.3「基本面腿一旦组内化就丢掉跨国可比性」一致，
   **§16.3 在快模板下依然成立，组内化不是免费增益**（§17.5 表里那条「vRA9OKM3 组内化纯增益」
   只适用于反转腿，不适用于估值比率）。

5. **窗口 63 优于 126**：S 1.31→0.98、TO 10.8%→7.0%。季度窗口是甜点。

**待验证**：QUICK 不返回 `LOW_GLB_AMER/EMEA/APAC_SHARPE`，而 PP 硬门槛是
**GLB·D1·AMER Sharpe > 1**。已提交 2 条 FULL 取子区数据，结果如下。

### 17.8 FULL 子区验证：快腿总 Sharpe 最高，但 AMER 反而掉到 0.32（关键卡点）

两条 FULL（设置同 QUICK，仅 `simulationMode=FULL`）：

| 变体 | S | F | TO | **AMER** | EMEA | APAC | 2Y |
|---|---:|---:|---:|---:|---:|---:|---|
| FCF/EV `ts_delta63` | 1.31 | 0.85 | 10.8% | **0.32** ⚠️ | **1.00** ✅ | 0.94 ⚠️ | 1.81 ✅ |
| EBIT/EV `ts_delta63` | 0.87 | 0.57 | 14.0% | 0.47 ❌ | 0.68 ❌ | 0.59 ❌ | 2.01 ✅ |

**对照 §4.1 第 141 行同一字段的旧慢模板**（ATOM 20v250）：S 1.03 / AMER **0.68** / EMEA 1.05 / APAC **0.33**。

**三条结论：**

1. **快腿买的是亚太、卖的是美洲。** `ts_delta63` 相对旧慢模板：APAC 0.33 → 0.94（+0.61）、
   EMEA 1.05 → 1.00（持平）、**AMER 0.68 → 0.32（−0.36）**。总 S 上涨（1.03→1.31）由亚太贡献，
   而美洲被牺牲。**总 Sharpe 排序与 PP 的通过性排序是反的**——单看总 S 会选错腿。

2. **纯基本面腿在 AMER 天花板约 0.68**（慢模板），快模板更低。这解释 §4.1 第 141 行
   「AMER 0.68 单腿不足」不是参数问题，是**基本面信号在美洲市场本身弱**。

3. **AMER 只能靠反转腿拉起来。** §4.1 第 145/146 行候选 A/B 之所以 AMER 能到 1.06 / 1.01，
   靠的是 `0.3–0.4` 权重的 `rank(-ts_rank(returns,252))`。**这是账本内唯一被验证能把 AMER
   推过 1 的手段。**

⇒ 出货路径明确：**新快腿（保 EMEA/APAC）+ 反转腿（拉 AMER）**，而非继续找基本面字段。
下一轮把 §17.7 的 `ts_delta(...,63)` 快腿与 `-ts_rank(returns,252)` 按 0.5–0.7 权重拼合，
并用 decay 压住反转腿带来的 51–72% 换手（§17.6 结论 3）。目标：AMER>1 且 TO<30%。

### 17.9 快腿 + 反转腿拼合：AMER 仍不过（GLB PP 通道关闭，2026-11-15 晚）

4 条 FULL（A5/A6 因断线未收，任务中断）。表达式
`group_neutralize(w*rank(ts_delta(FCF/EV,win)) + (1-w)*rank(-ts_rank(returns,252)), country)`：

| 组合 | S | F | TO | AMER | EMEA | APAC | ladder |
|---|---:|---:|---:|---|---|---|---|
| A1 w0.7 win63 d0 | 1.54 | 0.50 | 51.8% | **0.66 FAIL** | 1.25 PASS | 1.54 PASS | 1.38 FAIL |
| A2 w0.6 win63 d0 | 1.44 | 0.42 | 72.1% | **0.61 FAIL** | 1.19 PASS | 1.51 PASS | 1.23 FAIL |
| A3 w0.7 win63 d10 | 1.27 | 0.70 | 10.2% | **0.61 FAIL** | 1.02 PASS | 1.17 PASS | 1.54 FAIL |
| A4 w0.7 win63 d20 | 1.06 | 0.53 | 6.7% | 0.56 FAIL | 0.81 FAIL | 0.93 FAIL | 1.44 FAIL |

**结论（关键）**：$4.1 候选 A/B 的 AMER 1.06/1.01 依赖的是 **126 天窗口**的反转腿，
换成 63 天后 AMER 掉到 0.56–0.66，且加 decay 会同时打崩 EMEA/APAC。
**GLB PP（×1.0）的 AMER>1 门槛在 4 次尝试、共 10 条 FULL 后仍未达到，通道关闭。**

反过来暴露一个更重要的方向性错误（见 §18）：GLB 是用户 5 个主题里**倍率最低**的一个（×1.0），
而 4 个 EUR 主题中最值钱的是 ×2.0。整个 §17 的精力投在了最低价值目标上。

## §18 EUR 主题才是主战场：倍率 ×2.0 与完全不同的门槛结构（2026-11-15 晚）

### 18.1 平台实际持有的主题（`active_themes` API 实测，纠正此前的 4 条假设）

| 主题 | 倍率 | 状态 |
|---|---:|---|
| **EUR/D1 TOPCS1600** | **×2.0** | PASS |
| EUR/D1/ANALYST Pyramid | ×1.3 | PASS |
| EUR/D1/FUNDAMENTAL Pyramid | ×1.1 | PASS |
| EUR/D1/PV Pyramid | ×1.1 | PASS |
| GLB/D1 Power Pool Nov'26 | ×1.0 | WARNING |

⇒ **4/5 是高倍率 EUR，GLB 只有 ×1.0。** §17 全程押 GLB 属目标选择错误。

### 18.2 EUR 的检查项结构（与 GLB 有本质差异）

EUR 224 条现存 alpha 的检查项只有 7 条，**没有** `LOW_GLB_AMER/EMEA/APAC_SHARPE`：

| 检查 | 门槛 | 现存最优 |
|---|---|---|
| LOW_SHARPE | 1.58 | 1.64（PASS） |
| LOW_FITNESS | 1.0 | 1.41 |
| LOW_SUB_UNIVERSE_SHARPE | 0.83–0.87 | 1.43 |
| **IS_LADDER_SHARPE** | **1.58** | **1.48（全部 FAIL）** |
| HIGH_TURNOVER | 0.7 | 2.0–2.2%（远离上限） |

⇒ **EUR 的唯一卡点是 ladder（= 2Y Sharpe，QUICK 模式直接返回 `LOW_2Y_SHARPE`，无需 FULL）**，
与 GLB 的「美洲 >1」是**完全不同的病**。GLB 的病是分区偏科，EUR 的病是时间稳定性。

### 18.3 制度性事实：model109 在 EUR 不存在

`fields_of_dataset(model109, region=EUR, universe=TOPCS1600, delay=1)` 返回 **0 字段**。
⇒ §17.7 的 GLB 赢家 `free_cash_flow_to_enterprise_value` **无法搬到 EUR**。
EUR 可用的基本面绝对量字段（fundamental23）：
`cashflow_op` cov .932 / `assets` cov .936 / `enterprise_value` cov .737 / `ebit` cov .849 /
`ebitda` cov .844 / `cashflow_fin` cov .932。

### 18.4 EUR 验证轮（QUICK）：快模板对 EUR 同样无效

用例：E1 旧模板（对照）/ E2–E4 快模板 `rank(ts_delta(F,63))`，字段
`cashflow_op/assets` 与 `cashflow_op/enterprise_value`（FCF/EV 的 EUR 等价物），decay 100/200。
E5/E6 因同族已证伪（EV 覆盖率 0.737 是硬伤）未跑，改为 §18.5。

| 用例 | 模板 | decay | S | F | TO | 2Y(ladder) | SubU |
|---|---|---:|---:|---:|---:|---|---|
| E1 | 旧双平滑 cfo/as | 200 | 1.14 | 0.84 | 2.35% | 0.92 FAIL | PASS 0.74 |
| E2 | 快 ts_delta63 cfo/as | 200 | 0.98 | 0.53 | 2.91% | 0.91 FAIL | PASS 0.74 |
| E3 | 快 ts_delta63 cfo/EV | 200 | 0.12 | 0.02 | 3.04% | 0.76 FAIL | **FAIL −0.20** |
| E4 | 快 ts_delta63 cfo/as | 100 | 1.10 | 0.60 | 3.23% | 1.04 FAIL | PASS 0.83 |

**结论**：

1. **快模板在 EUR 不产生 GLB 那样的抬升。** GLB 上 ts_delta 让 TO 从 3.9%→13.8%、S 0.56→0.63；
   EUR 上 TO 只从 2.35%→2.91%，S 反降（1.14→0.98）。原因是 **decay 200 把快模板的换手全吃掉了**，
   而 EUR 的 HIGH_TURNOVER 上限 0.7 根本不紧（实测 2–3%），decay 完全没必要开这么大。
2. **`cashflow_op/assets` 的 2Y 天花板是 0.92–1.04**，与 §11.1 记的 0.95 一致（本次是独立复现）。
   ⇒ 该族在 EUR 永久排除：S 能到 1.28 但 ladder 差 0.55 以上。
3. **`enterprise_value` 分母在 EUR 不可用**（cov 0.737）：E3 的 SubU 直接 −0.20。
   GLB 上 FCF/EV 表现好，是因为 GLB 的 model109 字段是**第三方算好的比率**；
   EUR 没有 model109（§18.3），自己用绝对量相除就撞上覆盖率。
4. **一个重要机制差异**：EUR 的病是 **2Y 稳定性**，而 2Y 只由 anl15 族提供（§11.1）；
   GLB 的病是**分区偏科**。两者不能用同一套模板策略解决。

### 18.5 第四轮：快模板作用于 anl15（唯一 2Y 过线的腿）

`anl15_bps_gr_18_m_mean` 在 EUR/TOPCS1600 的 coverage 仅 0.5（分析师覆盖一半宇宙），
aC=2（几乎无人使用）。既然 2Y 只认这一族，那就只测它：

| 用例 | 表达式 | decay |
|---|---|---:|
| F1 | `group_neutralize(rank(ts_delta(a15,63)), country)` | 200 |
| F2 | 同上 | 100 |
| F3 | `0.5*fast(a15) + 0.5*fast(cfo/as)` | 200 |
| F4 | 旧双平滑 a15（对照组，校验口径 = §11.1 的 1.12/1.73） | 200 |

实测（QUICK，EUR/TOPCS1600/d1/MARKET/trunc 0.08）：

| 用例 | S | F | TO | 2Y / ladder | SubU |
|---|---:|---:|---:|---|---|
| F1 快 a15 d200 | 0.50 | 0.20 | 1.84% | **PASS 1.83** | 0.29 PASS |
| F2 快 a15 d100 | 0.48 | 0.19 | 2.34% | **PASS 1.79** | 0.27 PASS |
| F3 双快腿 d200 | 0.65 | 0.31 | 2.22% | 1.31 FAIL | 0.51 PASS |
| **F4 旧 a15 d200（对照）** | **1.35** | **1.09** | **1.45%** | **PASS 2.20** | **1.46 PASS** |

**三个结论**：

1. **快模板不可迁移到 EUR。** 同一个 a15，换成 `rank(ts_delta63)` 后 S 从 1.35 崩到 0.50，
   而 2Y 仍在 1.79–1.83。说明 a15 的信号是**水平量（level）**，取 63 天增量等于把水平信息丢掉，
   只留增量 ⇒ 全期 Sharpe 崩，近两年却还成立。**这与 GLB 上 ts_delta 有效的原因正好相反**：
   GLB 的 cfo 在旧模板下被双重平滑磨死（TO 3.9%），EUR 的 a15 在旧模板下本来就活（TO 1.45%）。
   ⇒ **模板选择依赖因子本身的频率特性，不能跨区域套用。**

2. **a15 单腿的 2Y 余量被账本低估。** 统一口径（trunc 0.08/decay 200）下 2Y **2.20**，
   §11.1 记的是 1.73（口径不同）。余量 0.62 意味着 **a15 权重有下压空间**，
   而 §11.2.1 的「权重 0.48 是相关性红线」是基于 ladder 只剩 0.03 余量的前提得出的——
   **那个前提需要用新余量重算**。这是 EUR 能否出第三条 alpha 的关键未知项。

3. **DD/Ret 结构**：F4 的 TO 仅 1.45%，是标准低换手族；F1/F2 抬到 1.8–2.3% 却没有换来 Sharpe。

### 18.6 第五轮：为 a15 搜索「高 2Y 配重腿」

若存在 2Y ≥1.6 且经济含义与 a15 不同的腿，则 a15 权重可降到 0.4 以下，
与 `vRAa38Jb` 的相关性自然下降，从而打开第三条 alpha 的空间。

6 条单腿，统一旧模板 + decay200 + trunc0.08：

| 腿 | 字段 | 选它的理由 |
|---|---|---|
| cfo/cap | `cashflow_op/cap` | 换分母为日频市值，避开 CFO/assets 的拥挤 |
| ebit/assets | `ebit/assets` | 经营利润/资产 |
| ebitda/assets | `ebitda/assets` | EBITDA/资产 |
| cf_fin/assets | `cashflow_fin/assets` | 融资现金流/资产（aC 仅 36） |
| est_ebt_1wk | `est_12m_ebt_raised_1wk` | EBT 一年期预测近一周上调（2Y 原记 0.15，复核） |
| a15fy3 | `anl15_bps_gr_cal_fy3_mean` | a15 变体（2Y 原记 1.54 擦线，复核） |

判据：**2Y ≥1.6 且 S ≥0.8 ⇒ 入配重池**，下一轮与 a15 按 0.4/0.6 试拼。

实测（QUICK / d200 / trunc 0.08 / MARKET）：

| 腿 | S | F | 2Y | 结论 |
|---|---:|---:|---|---|
| `cashflow_op/cap` | −0.09 | −0.02 | **−0.18 FAIL** | 日频市值作分母彻底失败 |
| `ebit/assets` | 0.28 | 0.11 | 0.61 FAIL | 弱 |
| `ebitda/assets` | 0.06 | 0.01 | 0.21 FAIL | 弱 |
| `cashflow_fin/assets` | −0.13 | −0.03 | 0.58 FAIL | 弱 |
| `est_12m_ebt_raised_1wk` | 1.17 | 0.65 | **0.07 FAIL** | S 有，2Y 归零（复现 §11.1 的 0.15） |
| **`anl15_bps_gr_cal_fy3_mean`** | **1.13** | **0.81** | **PASS 2.05** | **唯一入池** |

**关键结论**：

1. **`cashflow_op/cap` 的 S 为负、2Y −0.18，独立复现了 §17.5 的 GLB 结论**：
   用日频市值去除慢变的财报量，测到的是股价波动而不是基本面。
   跨区域、跨字段一致 —— **日频分母 + 季频分子 = 无效**，这条已是稳定规律。
2. **基本面腿在 EUR 的 2Y 普遍 <0.6**（ebit/ebitda/cf_fin 全灭），只有 anl15 族能过。
   `est_12m_ebt` 是典型「S 1.17 但 2Y 0.07」——近两年已失效，不能在 EUR 用。
3. **`a15fy3` 的 2Y 实测 2.05，账本 §11.1 记的 1.54 严重低估**（口径差异 + 单次测量误差）。
   它与 a15 同属 analyst15 数据集但是**不同字段**（FY3 日历口径），
   ⇒ 可作为**替身 ladder 载体**：若它的相关性低于 a15，就能在保住 ladder 的同时绕开
   `vRAa38Jb` 占位的 0.62 a15 权重。这是第三条 alpha 最有希望的方向。

### 18.7 第六轮：a15fy3 作 ladder 载体 + a15 权重边界

两条路线同时测（QUICK / d200 / trunc 0.08）：

| 用例 | 组合 | 路线 |
|---|---|---|
| R1 | 0.46·a15 + 0.54·cfo | A 压 a15 权重 0.02 |
| R2 | 0.42·a15 + 0.58·cfo | A 压 a15 权重 0.06 |
| R3 | 0.60·a15fy3 + 0.40·cfo | B fy3 载体为主 |
| R4 | 0.50·a15fy3 + 0.50·cfo | B 等权 |
| R5 | 0.42·a15fy3 + 0.58·cfo | B 压到底 |
| R6 | 0.25·a15 + 0.35·a15fy3 + 0.40·cfo | 双载体分散（借鉴 c6eq 等权经验） |

判据：ladder ≥1.58 且 S ≥1.58；通过者用 `aligned_corr` 与 `vRAa38Jb`/`6XM3GqWp` 算本地相关
（本地需留 ≥0.02 余量，平台口径高约 0.015，见 §11.2.1）。

实测：

| 用例 | S | F | TO | 2Y（限 2.02） | corr vRAa38Jb | corr 6XM3GqWp |
|---|---:|---:|---:|---|---:|---:|
| R1 0.46a15+0.54cfo | 1.56 | 1.37 | 1.81% | PASS 2.47 | 0.501 | **0.853** |
| R2 0.42a15+0.58cfo | 1.55 | 1.36 | 1.85% | PASS 2.42 | 0.473 | **0.854** |
| R3 0.60fy3+0.40cfo | **1.62** | 1.40 | 1.76% | PASS 2.43 | 0.563 | **0.808** |
| R4 0.50fy3+0.50cfo | **1.60** | 1.39 | 1.84% | PASS 2.39 | 0.506 | **0.837** |
| R5 0.42fy3+0.58cfo | 1.56 | 1.36 | 1.89% | PASS 2.32 | 0.455 | **0.844** |
| R6 双载体 | **1.63** | **1.43** | 1.71% | PASS 2.51 | 0.582 | **0.830** |

**四项关键结论**：

1. **账本 §11.2.1 的「a15 权重 0.48 以下 ladder 必 FAIL」已失效。** 第六轮 6 条全部
   ladder PASS 且余量极大（2.32–2.51 / 限 2.02），包括 a15 权重仅 0.42 的 R2。
   原因有两层：① a15 单腿 2Y 实测 2.20（非 1.73）；② `IS_LADDER_SHARPE` 的 limit 是
   **动态值**（现为 2.02，随已有 alpha 抬升），不是固定 1.58 —— 只要跟着抬就不掉队。
   ⇒ **今后 EUR 的约束只剩 S ≥1.58 与相关性，ladder 不再是瓶颈（余量 ≥0.3）。**

2. **真正的瓶颈换成了相关性，且是与「自己的第二条 alpha」相关。**
   6 条与 `vRAa38Jb` 相关 0.46–0.58（很安全），但与 `6XM3GqWp` 全部 0.81–0.85。
   原因是结构撞车：`6XM3GqWp` = 0.48a15 + 0.52cfo，而本轮全部候选都是 a15 族 + cfo。
   ⇒ **a15 权重不是问题，选 cfo 作配重才是问题。**

3. **`a15fy3` 单独做载体可行**：R3（0.60fy3+0.40cfo）在完全不用 a15 的情况下
   S 1.62 / 2Y 2.43，说明 a15fy3 足以独立承担 ladder。
   ⇒ 它的价值不是替代 a15，而是**让组合可以完全不带 a15**，从而绕开 `vRAa38Jb` 的 0.62 占位。

4. **换手结构稳定在 1.7–1.9%**，F 1.36–1.43（门槛 1.0），说明低换手族的 Fitness 不是约束。

### 18.8 第七轮：第三条 alpha，去掉 cfo 腿

结论 2 直接给出下一步：第三条必须是 **a15 族 + 非 cfo、非 sal 的配重腿**。
可用配重（§18.6 单腿实测）：`est_12m_ebt_raised_1wk` S 1.17、`anl69_best_eeps_nxt_yr` S 0.84。

| 用例 | 组合 |
|---|---|
| S1 | 0.50·a15 + 0.50·ebt |
| S2 | 0.40·a15 + 0.30·fy3 + 0.30·ebt |
| S3 | 0.50·fy3 + 0.50·ebt（完全不用 a15） |
| S4 | 0.30·a15 + 0.25·fy3 + 0.20·ebt + 0.25·a69 |
| S5 | 0.35·a15 + 0.35·ebt + 0.30·a69 |
| S6 | 0.50·a15 + 0.25·ebt + 0.25·a69 |

判据：S ≥1.58、2Y PASS，且对两条 ACTIVE 的本地相关均 <0.66。

实测：**全体 S 1.28–1.38，全部不达标**（S1 1.38 / S3 1.37 / S6 1.34 / S4 1.30 / S5 1.30 / S2 1.28）。
2Y 反而全部 PASS（2.05–2.16），说明 ladder 确实不再是约束。

⇒ **cfo 是唯一的 S 来源，不能砍。** 去掉 cfo 后即使 4 腿分散也只有 1.30，
比 0.46a15+0.54cfo 的 1.56 低 0.26。配重腿 S 太弱（ebt 1.17 / a69 0.84）撑不起 1.58。

### 18.9 第八轮：换中性化分组给 cfo「换皮」降相关（前沿已量化）

同一权重、同一字段，只换 `group_neutralize` 的分组变量：

| 组合 | 分组 | S | F | 2Y | corr #1 | corr #2 |
|---|---|---:|---:|---|---:|---:|
| 0.46a15+0.54cfo | country（=R1） | 1.56 | 1.37 | 2.47 PASS | 0.501 | 0.853 |
| 0.46a15+0.54cfo | **sector** | **1.61** | **1.46** | 2.03 PASS | 0.441 | 0.778 |
| 0.46a15+0.54cfo | subindustry | 1.24 | 0.92 | 0.49 FAIL | 0.297 | 0.662 |
| 0.55fy3+0.45cfo | country（=R3 变体） | 1.62 | 1.41 | 2.42 PASS | 0.536 | 0.826 |
| 0.55fy3+0.45cfo | **sector** | **1.58** | **1.41** | 2.27 PASS | 0.432 | 0.716 |
| 0.55fy3+0.45cfo | industry | 1.32 | 1.03 | 0.51 FAIL | 0.308 | 0.629 |
| 0.55fy3+0.45cfo | subindustry | 1.15 | 0.82 | 0.31 FAIL | 0.279 | 0.596 |

**核心结论：这是一条严格单调的前沿，不是可以同时改善的取舍。**

- 分组收紧 ⇒ 相关单调下降（#2：0.826 → 0.716 → 0.629 → 0.596），
  但 S 与 2Y 同步坍塌（1.62 → 1.58 → 1.32 → 1.15）。
- **缺口量化：在 corr≈0.63 处还差 0.26 的 S；在 corr≈0.72 处差 0.06。**
- `sector` 是唯一保住 2Y 的收紧分组；`industry`/`subindustry` 会把 2Y 打到 0.3–0.5，
  与 §12 F2 的「sector 抬 F、ladder 崩」一致（当时崩到 1.05，现在虽 limit 抬高，仍不够）。
- 对 `vRAa38Jb` 的相关始终只有 0.28–0.54（限 0.66，**余量 0.12 以上**），
  瓶颈完全在自有第二条 `6XM3GqWp`。

⇒ 下一轮不该沿这条前沿滑动（S 换 corr 是等价的），而应**平移前沿**：
把 S 来源从 `cfo`（占 #2 的 0.52 权重）换成 `est_12m_sal`（占 #1 的 0.38 权重）
或 `est_12m_ebt`（尚未被占用）。见 §18.10。

### 18.10 第九轮：更换 S 来源（cfo → sal/ebt）

| 用例 | 组合（group=sector，除 P6） |
|---|---|
| P1 | 0.55·fy3 + 0.45·sal |
| P2 | 0.45·fy3 + 0.30·sal + 0.25·ebt |
| P3 | 0.50·fy3 + 0.25·sal + 0.25·cfo |
| P4 | 0.50·a15 + 0.50·sal |
| P5 | 0.40·fy3 + 0.35·ebt + 0.25·sal |
| P6 | 0.55·fy3 + 0.45·sal（country，对照相关天花板） |

判据：S ≥1.58、2Y PASS、两条相关均 <0.66。

| 用例 | S | F | TO | 2Y | corr #1 | corr #2 |
|---|---:|---:|---:|---|---:|---:|
| P1 fy3+sal sec | 1.42 | 1.10 | 1.97% | 1.42 FAIL | 0.582 | 0.438 |
| P2 fy3+sal+ebt | 1.38 | 1.04 | 2.07% | 1.22 FAIL | 0.588 | 0.451 |
| **P3 fy3+sal+cfo sec** | **1.68** | **1.51** | **1.85%** | **2.33 PASS** | **0.531** | **0.658** |
| P4 a15+sal sec | 1.53 | 1.21 | 1.97% | 2.32 PASS | 0.653 | 0.491 |
| P5 fy3+ebt+sal | 1.36 | 1.00 | 2.13% | 1.09 FAIL | 0.581 | 0.445 |
| P6 fy3+sal cty | 1.54 | 1.19 | 1.98% | 2.15 PASS | 0.733 | 0.510 |

**核心结论（本账本 EUR 的最优解）**：

1. **P3 = 0.50·fy3 + 0.25·sal + 0.25·cfo（group=sector, decay200, trunc0.08）是 EUR 至今最强组合**：
   S **1.68**、F **1.51**、TO 1.85%、2Y **2.33 PASS**，
   且两条本地相关 **0.531 / 0.658** 都在 0.7 之下。这是 224 条存量 alpha 中都不存在的
   「S 1.68 + ladder 过线 + 双相关安全」组合。

2. **平移前沿的做法被验证有效**：把 S 来源从 cfo（占 #2 的 0.52）θ 分散到 sal（占 #1 的 0.38），
   使 #2 相关从 0.716（fy3+cfo sector）降到 **0.658**，同时 S 反而从 1.58 升到 **1.68**。
   ⇒ **不是取舍，是双改善**：因为 sal 的经济含义与 cfo 正交，分散后 S 上升、相关下降。
   这与 §12 的「等权分散抬 ladder」是同一机制。

3. **纯 fy3+sal 反而 2Y FAIL**（P1 1.42）：sal 的 2Y 太弱（单腿 0.43），必须靠 cfo 的
   稳健性托住 ladder。**cfo 不能完全去掉，但降到 0.25 就够**——这是本轮的关键定量结论。

4. **group=sector + country 组的对比**：P6（country）相关 #1 冲到 0.733 超线，
   证实 `sector` 分组是压 #1 相关的有效手段（0.733 → 0.531，代价 S −0.14 但仍有 1.68 余量）。

### 18.11 FULL 定稿与提交决策

V1 = P3 原样；V2 = 0.52·fy3 + 0.26·sal + 0.22·cfo（再压 cfo，换更低的 #2 相关）。
FULL 结果见 `.workbuddy/eur_p3_full_results.json`。

**提交前须知的约束**：`submit_one.py` 的本地质量闸门要求 F ≥2.0，而 §12 已证
EUR 低换手族的 F 上限 ≈1.65（`F = S·sqrt(Ret/0.125)`，TO≤2.1% 时 Ret 最多 10.8%，
要 F=2 需 S≥2.24，EUR 实际最高 1.78）。**该闸门在 EUR 主题内结构性不可达**，
存量 ACTIVE 的 `6XM3GqWp` 也只有 F 1.40。⇒ 若提交需 `--no-quality`，属规则内的已知例外。

### 18.12 提交实录：`mLearjak6` 被 SELF_CORRELATION 0.7408 拒（**平台-本地偏差异常**）

FULL 定稿（`mLearjak6`，P3 原样）：

| 检查 | 值 | 结果 |
|---|---|---|
| LOW_SHARPE | 1.68 / 1.58 | PASS |
| LOW_FITNESS | 1.51 / 1.0 | PASS |
| LOW_SUB_UNIVERSE_SHARPE | 1.47 / 0.89 | PASS |
| **IS_LADDER_SHARPE** | **2.33 / 2.02** | **PASS** |
| LOW_ROBUST_UNIVERSE_SHARPE | 0.96 / 0.7 | PASS |
| CLUSTER_TEST | 1.64 / 1.58 | PASS |
| MATCHES_THEMES | — | WARNING（EUR TOPCS1600 ×2.0 + FUNDAMENTAL ×1.1 均命中） |
| **SELF_CORRELATION** | **0.7408 / 0.7** | **FAIL（403）** |

其他指标：TO 1.85%、Margin 108.7‱、DD 14.16%、Ret 10.06%。
提交 18 次 POST 后出判定；**被拒不消耗当日提交额度**（今日已提交仍为 0）。

**关键方法学修正（覆盖 §11.2.1）**：

- 本地 `aligned_corr` 对 `6XM3GqWp` = **0.658**，平台判定 **0.7408** ⇒ **偏差 +0.083**，
  是 §11.2.1 记的 +0.015 的 **5.5 倍**。
- ⇒ **安全阈值改为：本地 corr ≤0.61**（0.61+0.083≈0.693）。
- 偏差放大的可能原因：平台 SELF_CORRELATION 取的是「与**全部**自有 alpha 的最大相关」，
  且统计窗口/口径与本地的日收益交集不同。**单一 0.015 的经验值不可再用，本轮起按 +0.08 预留。**

**结论**：P3 在指标上完全达标（S 1.68 / F 1.51 / ladder 2.33 / SubU 1.47 / 主题 ×3.1），
**唯一卡点是相关**。方向变成「在保住 S≥1.58 与 2Y PASS 的前提下，把本地 corr 压到 0.61 以下」。

### 18.13 第十轮：定向压 cfo 权重

`6XM3GqWp` 的 0.52 是 cfo，故 P3 的 #2 相关由 cfo 驱动；把 cfo 份额转给 sal
（sal 只占 #1 的 0.38，而 #1 相关仅 0.531，余量充足）。

| 用例 | 组合（sector） | 目标 |
|---|---|---|
| W1 | 0.52·fy3 + 0.30·sal + 0.18·cfo | cfo 降至 0.18 |
| W2 | 0.55·fy3 + 0.30·sal + 0.15·cfo | cfo 降至 0.15 |
| W3 | 0.50·fy3 + 0.35·sal + 0.15·cfo | sal 加重 |
| W4 | 0.52·fy3 + 0.25·sal + 0.23·cfo | 对照（近 P3） |

判据：S ≥1.58、2Y PASS、本地 corr#2 ≤0.61、corr#1 ≤0.62。

| 用例 | S | F | 2Y | corr #1 | corr #2 | 估平台 #2（+0.083） |
|---|---:|---:|---|---:|---:|---:|
| W1 52/30/18 | 1.64 | 1.43 | 2.33 PASS | 0.555 | 0.609 | 0.692（余量 0.008 太薄） |
| W2 55/30/15 | 1.60 | 1.38 | 2.32 PASS | 0.561 | **0.583** | **0.666** |
| **W3 50/35/15** | **1.62** | 1.39 | 2.29 PASS | 0.566 | 0.586 | **0.669** |
| W4 52/25/23 | 1.67 | 1.49 | 2.34 PASS | 0.537 | 0.644 | 0.727（FAIL 风险） |

**结论**：

1. **cfo 权重从 0.25 降到 0.15，只付出 S −0.06 的代价（1.68 → 1.62），换来 #2 相关 −0.072。**
   而 2Y 几乎不动（2.33 → 2.29），说明 **ladder 主要由 fy3 决定，cfo 只提供 S 和少量稳健性**。
   这与 §18.10 结论 3（纯 fy3+sal 时 2Y 掉到 1.42）并不矛盾：**cfo 权重 0.15 足以托住 ladder，
   0 则不行** ⇒ cfo 的作用是**阈值性的**，不是线性的。
2. **相关-S 前沿在 cfo∈[0.15, 0.25] 区间近似平坦**：W1/W2/W3/W4 的 S 在 1.60–1.67，
   相关在 0.58–0.64。**选点的自由度来自 corr，不是 S**，因此优先取相关最低的 W2/W3。
3. W3（0.50 fy3 + 0.35 sal + 0.15 cfo）与 W2（0.55/0.30/0.15）几乎等价，
   W3 的 S 高 0.02、W2 的相关低 0.003 ⇒ **两者都进 FULL 定稿，取先过检者提交**。

### 18.14 出货：`npaZdvR3` ACTIVE（EUR 主题第三条，×3.1 倍率）

**这是本账本在 EUR/D1 TOPCS1600 主题内成功上线的第三条 alpha。**

```
group_neutralize(
  0.50*zscore(vector_neut(ts_mean(ts_backfill(anl15_bps_gr_cal_fy3_mean,60),20), ts_mean(ts_backfill(anl15_bps_gr_cal_fy3_mean,60),250)))
+ 0.35*zscore(vector_neut(ts_mean(ts_backfill(est_12m_sal_raised_1wk,60),20), ts_mean(ts_backfill(est_12m_sal_raised_1wk,60),250)))
+ 0.15*zscore(vector_neut(ts_mean(ts_backfill(cashflow_op/assets,60),20), ts_mean(ts_backfill(cashflow_op/assets,60),250))),
  sector)
EUR / TOPCS1600 / delay 1 / MARKET / decay 200 / truncation 0.08
```

| 项 | 值 |
|---|---|
| status | **ACTIVE**（dateSubmitted 2026-11-16） |
| Sharpe / Fitness | **1.62 / 1.39** |
| Turnover / Margin | 1.92% / 95.0‱ |
| Returns / Drawdown | 9.14% / 13.19% |
| LOW_SHARPE | PASS 1.62 / 1.58 |
| LOW_FITNESS | PASS 1.39 / 1.0 |
| LOW_SUB_UNIVERSE_SHARPE | PASS 1.45 / 0.86 |
| **IS_LADDER_SHARPE** | **PASS 2.29 / 2.02** |
| LOW_ROBUST_UNIVERSE_SHARPE | PASS 0.94 / 0.7 |
| CLUSTER_TEST | WARNING 1.55 / 1.58 |
| **MATCHES_THEMES** | **PASS — EUR/D1 TOPCS1600 ×2.0 + EUR/D1/FUNDAMENTAL Pyramid ×1.1（合计 ×3.1）** |
| SELF_CORRELATION | **0.6754 / 0.7 PASS** |
| PROD_CORRELATION | **0.6927 / 0.7 PASS** |

**平台-本地相关偏差的最终标定（覆盖 §11.2.1，务必以此为准）**：

| 候选 | 本地 max corr | 平台 SELF_CORRELATION | 偏差 |
|---|---:|---:|---:|
| `mLearjak6`（P3，被拒） | 0.658 | 0.7408 | **+0.083** |
| `npaZdvR3`（W3，通过） | 0.586 | 0.6754 | **+0.089** |

⇒ **标定值：平台 ≈ 本地 + 0.086（±0.003）。**
**因此 EUR 主题的安全线是：本地 max corr ≤ 0.61。**（0.61+0.086=0.696，压线但可过；
0.651 以上基本必拒。）之前的 +0.015 是**严重低估**，依它选点必然被拒。

**本主题的三条 ACTIVE 结构对照（用于规划第四条）**：

| alpha | 组成 | S | F | 与后者的关系 |
|---|---|---:|---:|---|
| `vRAa38Jb` | 0.62 a15 + 0.38 sal + decay150 | — | — | 占住 a15 与 sal 的高权重位 |
| `6XM3GqWp` | 0.48 a15 + 0.52 cfo/as + decay200 | 1.61 | 1.40 | 占住 a15+cfo 组合位 |
| **`npaZdvR3`** | **0.50 fy3 + 0.35 sal + 0.15 cfo + sector** | **1.62** | **1.39** | **用 fy3 替 a15、sector 分组降相关** |

⇒ **第四条的唯一可行结构**：必须同时避开 a15（#1/#2 共用）、cfo≥0.4（#2）、sal≥0.5（#1/#3），
即继续走「a15fy3 载体 + 多腿低权重分散 + sector 分组」，并把本地 max corr 压到 ≤0.61。

---

## §19 方法论固化：主题优先（2026-11-16，此后每次开工按此走）

> 本节不是某个族的结论，而是**顺序**。§17–§18 两天烧掉的 40+ 条仿真里，最大的损失不是某个族失败，
> 而是**前 20 条全部花在倍率最低的主题上**。

### 19.1 开工顺序（不可调换）

1. `python scripts/preflight.py --themes` → 列主题，记 `multiplier / region / delay / universe / result`。
2. 按「倍率 × 可达性」选一个战场；主题空/歧义/用户指定区外 ⇒ **问用户**。
3. 在选定 scope 内 `recommend_fields.py` → 扩池。
4. `redflag.py` 查账本 → 排除 CLOSED/BLOCKED 族。
5. 骨架对照扫描（5–7 个）× QUICK → 判 TO 是否解开。
6. 幸存骨架 × 字段横评（6–8 条）× QUICK → 判 2Y / SubU。
7. 本地日收益相关 ≤ 0.61 → FULL 定稿 → 用户授权后提交。

### 19.2 为什么「倍率优先」在 2026-11-15 之前没被执行

旧交接文档把主战场记成 GLB/D1 Power Pool（×1.0），并把它当成唯一未挖的方向；
`active_themes()` 当时还没接进流程，主题清单靠人工推断，于是**推断结果被当成事实沿用三天**。
现在 `preflight.py --themes` 已可一键列出（`MATCHES_THEMES` 反查，零额度）。
⇒ **凡涉及方向切换，必须现查，不许沿用文档里的旧清单。**

### 19.3 两个区域的门槛与病根对照（决定"选哪个主题"的唯一依据）

| | EUR（×2.0 / ×1.3 / ×1.1 / ×1.1） | GLB/D1 PP（×1.0） |
|---|---|---|
| 检查条数 | 7 | 10（多 AMER/EMEA/APAC 各 ≥1） |
| 病根 | **2Y / ladder**（只有 analyst15 能解） | **分区偏科**（基本面 AMER 天花板 ≈0.68） |
| 可用解法 | 多腿低权重 + 换分组压相关 | 混价格反转腿（但撞换手与 prod corr） |
| QUICK 能否预判 | **能**（`LOW_2Y_SHARPE` ≈ ladder） | 不能，必须 FULL 才给子区 |
| 单条仿真成本 | ≈2–4 分钟 | ≈8 分钟；并发 >2 会报资源不足 |

### 19.4 相关性标定（覆盖 §11.2.1 的 +0.015）

平台 `SELF_CORRELATION` ≈ 本地日收益相关 **+0.086**（`mLearjak6` 0.658→0.7408、
`npaZdvR3` 0.586→0.6754 两点标定）。**选点规则：本地 max corr ≤ 0.61。**
旧值 +0.015 低估 5.5 倍，按它选点必然被拒。

---

## §20 `ai_news_scores` 在 EUR/TOPCS1600 的天花板：0.71（2026-11-17，8 轮 40 条）

**任务**：用户给定 `j2a191MW` = `-rank(negative_score_confidence_upper_bound_2)`
（S 0.59 / F 0.09 / TO 164% / 2Y 0.22），要求改造成「优质 ATOM alpha」。

**结论：不可行。** 单数据集信息上限 ≈ 0.71，顾问门槛 1.58。不提交。

### 20.1 四条硬发现（每条都有反证实验）

1. **字段是别名，ATOM 无腿可混。** 数据集列 105 个字段 = 3 情绪 × 7 统计量；
   `_2 / _3 / 无后缀` 三个"变体"在 EUR 上给出**精确相同**的 0.59 / 164.0% / 3.68% / 9.4%。
   ⇒ 「同数据集多腿正交」这条 ATOM 主武器在这里完全无效。

2. **只有负面一侧有信息，且真正被定价的是「有没有新闻」。**
   `rank(pos_avg-neg_avg)` = 0.02（正负相消）；`rank(pos_avg)` = **−0.47**；
   `rank(-neut_avg)` = **−0.53**。三条腿同指「关注度折价」而非情绪极性。
   但合成 `-rank(pos_avg+neg_avg)` 只有 0.53，**不优于单用 `-neg_upper` 的 0.59**。

3. **信息半衰期 ≈ 1 天，任何减速都杀死信号。**
   先平滑再排序：`rank(-ts_mean(F,5))` 0.18、窗口 20 → 0.01；
   先排序再平滑：`ts_mean(rank(-F),5)` 0.16、窗口 10 → −0.10。
   **两种顺序都杀掉** ⇒ 不是算子顺序问题，是信息真的只活一天。

4. **换手 148–175% 是结构性属性，不是构造缺陷。**
   去掉 `rank` 直接用原始分数 `−F`，TO 反而升到 174.7%（排除了"并列值导致 rank 抖动"的假设）；
   唯一能把 TO 压到 36% 的手段是 `ts_backfill`，但**符号翻转为 −0.30**
   —— 新鲜坏消息继续跌、陈旧坏消息反弹。
   `trade_when(F>0, rank(-F), -1)` 持仓保持给出 **−0.22**，直接验证了"持有即反向暴露"。

### 20.2 各角度的最优解（可供将来复用）

（用列表而非表格，避免被 `redflag.py` 误解析成字段行）

- **Sharpe 最高**：`ts_decay_linear(rank(-F),20)` + SUBINDUSTRY → S 0.71 / F 0.12 / TO 149.6% / Margin 6.1‱ / DD 9.8% / 2Y 0.60
- **形态最干净**：`ts_mean(rank(pos_avg-neg_avg),5)` → S 0.62 / F 0.12 / TO 57.0% / Margin 8.1‱ / DD 4.6% / 2Y 1.00
- **2Y 最高**：`-ts_mean(F,5)`（不排序）→ S 0.54 / F 0.13 / TO 58.1% / Margin 11.6‱ / DD 10.7% / 2Y 1.10
- **Margin 最高**：`ts_mean(rank(net),20)` + decay10 → S 0.49 / F 0.16 / TO 13.5% / Margin 22‱ / DD 5.2% / 2Y −0.11

⚠️ **「形态最优」与「分数最优」在这族里是两条不同的路**：`RReddgMz` 的 DD/Ret = 2.0、2Y 1.00 且逐年改善，
问题**纯粹是幅度不足**，不是鲁棒性不足——这在「病根是 2Y」的 EUR 里是稀缺品质。
将来若要拿它当混腿素材，它是唯一值得保留的一条（TO 合格、DD 极低、2Y 达标，只缺 Sharpe）。

### 20.3 机制层面的可迁移教训

- **新闻类快信号的换手来源是「覆盖空缺」而不是「信号波动」**。
  诊断方法：先去 rank 看 TO 是否下降。若不变 ⇒ 换手源于数据可得性，平滑无用，
  只能靠 backfill 或 `trade_when` 持仓；而这两者会改变信号的经济含义（本条族里都导致翻转）。
- **`-rank(field)` 的符号稳定性必须用 `ts_backfill` 版本做对照**：
  同一字段 fresh 版 +0.59、stale 版 −0.30，差 0.89 个 Sharpe ⇒ 该信号是纯同日冲击。
  这个对照（2 条仿真）比 5 个骨架扫描更能定性信号的时间结构。
- **低覆盖率数据集（cov 0.79）在 EUR 小宇宙上天然高换手**，与 USA/TOP3000 的表现不可互推。

