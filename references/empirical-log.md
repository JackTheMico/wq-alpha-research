# WQ Alpha 实证记录（按时间倒序无关，按日期正序）

> 由 `SKILL.md` §12 迁出，保持原文不动。**结论性规则已上提到 SKILL.md**，
> 这里保留完整的实验背景、原始指标与推理过程，供追溯与复用。
> 每条的结构统一为：背景 → 做法 → 结果表 → 结论。

---

## 12. 实证记录（自动更新）

> 本节仅保留机制说明。真实运行生成的 alpha ID、表达式、PnL、提交状态和相关性记录可能关联个人账号与研究资产，默认写入本地 `alpha_db.json`，不随仓库发布。
> 若需要沉淀通用经验，请人工汇总成脱敏规则后再写回第 4、5、6、8、10 节。

### 2026-08-13 — cap 回归中性化模板挖掘（YPvlEl0l 提交 ACTIVE）

用户模板（Pasted text #5，含 `regression_neut`/`vec_avg({data})`/`group_normalize`/`vec_count`/`rsk82_*` 等）：
```
regression_neut(regression_neut(group_neutralize(group_zscore(vec_avg({data}),sector),bucket(rank(cap),range="0.1,1,0.1")),group_neutralize(group_zscore(cap,sector),bucket(...))),ts_ir(returns-group_median(returns,sector),126))
fear = ts_mean(abs(returns-group_mean(returns,1,market))/(abs(returns)+abs(group_mean(returns,1,market))+0.1),20);-group_neutralize(fear*group_normalize(ts_decay_exp_window(ts_percentage(vec_count(rsk82_...),60,percentage=0.9)-ts_percentage(vec_count({data}),60,percentage=0.1),20,factor=0.8),market)*inverse(abs(ts_entropy(volume,20))),bucket(rank(cap),range="0.1,1,0.1"))
```
USA TOP3000 delay=1 实证结论（`{data}` 占位符，用户建议试 ROE/现金流字段）：
1. **模板算子大面积不可用**（逐个探针验证）：`regression_neut`、`group_normalize`、`vec_count`、`vec_avg`(标量)、`ts_ir`、`ts_percentage`、`ts_decay_exp_window`、`ts_entropy`、`inverse`、`group_median`、`sector` 字段均报 unknown operator/field。可用算子仅 rank/group_rank/ts_rank/ts_mean/group_zscore/group_neutralize/bucket/group_mean。
2. **落地模板核心语义**：Part1 的「data 相对 cap 回归中性」用 `sig = group_zscore({data},subindustry) - group_zscore(cap,subindustry)`（cap zscore 相减近似回归中性）；`sector`→`subindustry`。Part2 的 fear 项依赖算子全不可用，放弃（且 Part1 相对收益分量 `ts_rank(returns-group_mean(returns,1,subindustry),126)` 实测负贡献，Sharpe 1.49→0.94）。
3. **现金流字段最优**：`cashflow_op/equity`（经营现金流/equity）Sharpe 1.63/Fit 1.11/TO 7.6% 过线；`free_cash_flow_reported_value/equity` Fit 0.98 接近；ROE 类（`operating_income/equity`、`return_equity/close`）Fit 仅 0.86-0.88（Returns 4.4% 太低）。**现金流 > ROE**。
4. **group_mean 需 3 参数**：`group_mean(x,1,group)`，写 `group_mean(returns,subindustry)` 会报 "Invalid number of inputs : 2, should be exactly 3"。
5. 复杂多层 group 嵌套表达式模拟极慢（超 8 分钟超时），需精简到与上轮 GrGmXvwx 相当的结构复杂度（约 2 分钟跑完）。
6. 最终提交（**YPvlEl0l ACTIVE**，Sharpe=1.63, Fit=1.11, Returns=5.8%, TO=7.6%, DD=3.0%，全部 IS check PASS，与 19 个 ACTIVE 最高日收益相关 +0.558 vs GrGmXvwx，唯一 ≥0.5 且 <0.7 可提交）：
`group = bucket(rank(cap),range="0.1,1,0.1"); sig = group_zscore(cashflow_op/equity,subindustry) - group_zscore(cap,subindustry); group_neutralize(ts_mean(group_rank(ts_rank(sig,126),subindustry),2),group)`，Decay=10, Neutralize=INDUSTRY。
7. SELF_CORRELATION 提交前显示 PENDING，提交后 status 立即 ACTIVE（提交即触发重新评估并 PASS）——不必等 PENDING 转 PASS 再提交。

---

### 2026-08-13 — bucket(cap) × 期权 breakeven × OI 模板挖掘（GrGmXvwx 提交 ACTIVE）

用户模板（含 `vec_min({Analyst Std})`/`vec_max({OptionHighPrice})` 占位符）：
```
group = bucket(rank(cap),range='0.1,1,0.1');
risk = rank(-ts_av_diff(vec_min({Analyst Std}),360));
alpha = rank((1-risk)*group_rank(ts_scale(vec_max({OptionHighPrice})/close,120),industry));
group_neutralize(ts_mean(alpha,2),group)
Decay=10, Neutralize=industry
```
USA TOP3000 delay=1 实证结论：
1. **`vec_min`/`vec_max` 算子在本 universe 不可用**（"unknown operator"），`vec_avg` 仅接受事件输入——三者均需去除，直接用单字段。
2. `{Analyst Std}` 用 analyst4 预期 std（如 `anl4_fs_detail_estimates_advanced_af_nd_epsr_std`、`..._basic_qf_v4_nd_eps_std`）；`{OptionHighPrice}` 用 Options Analytics 的 `call_breakeven_360/180/1080`（看涨盈亏平衡价/close，贴合"期权隐含高价"语义）效果最好，`forward_price_*` 极弱（Sharpe 0.03）。
3. **risk 项（分析师分歧 ts_av_diff）在本模板是负贡献**：去掉 risk 项后 Sharpe 0.8→1.42；调低 risk 权重（0.3）反而更差。`bucket(rank(cap),range='0.1,1,0.1')` 市值分桶（剔除最小 10% 市值）+ `group_neutralize(ts_mean(alpha,2),group)` 结构保留有效。
4. **关键提升是混合基本面**：`+ 0.5~0.7*group_rank(ts_rank(operating_income/equity,126),subindustry)`，权重 0.6 最优。
5. 最终提交（**GrGmXvwx ACTIVE**，Sharpe=1.50, Fit=1.28, Returns=9.1%, TO=9.2%, DD=4.6%，全部 IS check PASS，与 18 个 ACTIVE 最高日收益相关 0.501）：
`group = bucket(rank(cap),range='0.1,1,0.1'); sig = group_rank(ts_rank(call_breakeven_360/close,120),industry); alpha = rank(sig) + 0.6*group_rank(ts_rank(operating_income/equity,126),subindustry); group_neutralize(ts_mean(alpha,2),group)`，Decay=10, Neutralize=INDUSTRY。
6. 纯期权 breakeven 信号本身只有 0.9 左右 Sharpe，不混合基本面无法过线——再次印证「期权/技术信号必须混合基本面」的经验。

---

### 2026-08-16 — mdl77_2gdna_actrtn12m × ROE × 资产负债率（VkGQxanA / QPGRvdV5 提交 ACTIVE）

用户指定字段 `mdl77_2gdna_actrtn12m`（想表达「低估+好盈利→做多」）。USA TOP3000 delay=1 实证结论：

1. **新模型字段以 API 精确查询为准**：`GET /data-fields/{id}` 命中（Analysts' Factor Model, MATRIX, 12-Month Active Return with 1-Month Lag = t-13→t-1 价格变化）；本地字段快照（4367 个）不含 mdl77 系列与 `total_liabilities`/`total_assets`。search 端点对短词返回 400 "Invalid query"，精确查询更可靠。
2. **MATRIX 字段可直接 rank/group_rank**：`mdl77_2gdna_actrtn12m`、`assets`、`liabilities` 均无需 vec_avg/ts_backfill 即可用于截面算子。
3. **`trade_when(x, matrix_field<0, 1)` 会零交易**（longCount=0、TO=0）：MATRIX 与标量比较恒 False；条件需先转换，如 `rank(matrix_field)<0.5`。
4. **12 个月滞后收益是动量不是低估**：正方向 `group_rank(mdl77_2gdna_actrtn12m,subindustry)` Sharpe 1.07；反转方向（做多跌得多的）无效（-0.22 到 0.47）——「做多被低估股」的直觉在 USA TOP3000 不成立。
5. **低负债率单独是负 alpha（-0.72）**：高杠杆有正风险溢价；「低负债=稳健」只能作 ≤0.2 小权重质量过滤，不能当主信号。
6. **ROE 分量已过载 + est_eps 是相关性炸弹**：ACTIVE 池至少 4 个 alpha 含 ROE（wpEr87Ax/MPGx5EZk/KPGLLpPE/pwN5e7KX），新 alpha ROE 权重 >0.3 必撞相关线（0.799）；`est_eps/close` 撞分析师簇（与 9q7nYrZe/blQ8Q7kN/MPGx5EZk 相关 0.69-0.74）。
7. **降相关配方 = 独特信号高权重 + 过载信号低权重**：mdl77 动量与现有池不同源，权重 0.5-0.7；ROE 压到 0.3——相关从 0.799 降到 0.68。
8. **提交判据**：模拟 8 checks 全 PASS + 日收益相关 <0.7 → 提交后 SELF_CORRELATION 基本一次过、90s 内 ACTIVE（两次提交 VkGQxanA、QPGRvdV5 均验证）。
9. 提交 F（**VkGQxanA ACTIVE**，Sharpe=1.41, Fit=1.03, TO=6.3%, DD=6.4%，最高相关 0.678）：
`0.3*group_rank(ts_rank(operating_income/equity,126),subindustry)+0.5*group_rank(mdl77_2gdna_actrtn12m,subindustry)+0.2*group_rank(-liabilities/assets,subindustry)`（decay=0, SUBINDUSTRY）
10. 备选 E（**QPGRvdV5 提交**，Sharpe=1.44, Fit=1.17, TO=5.7%，最高相关 0.692）：`0.3*ROE+0.7*动量`（无负债率分量）。强指标版（0.6ROE+0.4动量 Sharpe 2.05、加 est_eps 后 2.58）均因相关 ≥0.74 被否。
11. **SELF_CORRELATION 血泪教训（E 被拒 0.9622）**：E 与刚 ACTIVE 的 F（VkGQxanA）同簇（共享 0.3ROE + mdl77 主信号），F 先上线后 E 提交必撞 0.96。**对照池包含提交时刻所有 ACTIVE，刚提交的 alpha 立即成为冲突源**；多候选时先提交最优，其余同簇候选直接放弃，不要逐个试。提交豁免：新 Sharpe ≥ 冲突 alpha × 1.1 可过。
12. **与已上线同簇 alpha 降相关的有效杠杆 = 换信号主导权**：mdl77 权重 0.7→0.2 + 反转（`rank(-(close-open)/open)`）权重 0.5，相关 0.962→<0.5；decay 反而让组合贴近旧 alpha 的慢信号形状（0.757→0.918）；换中性化/换 ROA 无效（0.933）。
13. **反转分量 + decay=5 是 TO/Fitness 甜点**：`0.3*ROE+0.2*mdl77动量+0.5*反转` decay=5 → Sharpe 3.15/Fit 2.19/TO 34.3%（decay=0 时 TO 56%、Fitness 1.23）。反转主导组合（超跌+高ROE+弱趋势确认）本身就是「错杀好公司」的低相关实现。
14. **SELF_CORRELATION 检查代码**：必须按**日期交集**对齐算日收益相关（位置对齐会低估相关）；PnL recordset 空结果重试 ≥3 次；高相关时打印冲突源表达式。

### 2026-10-29 — 按最新官方文档对齐 API 层（顾问权限）

依据：`GET /tutorial-pages/brain-api`（lastModified **2026-09-21**）、`consultant-submission-tests` / `understanding-simulation-limits` / `multi-alpha-simulation` / `consultant-features`（均 2026-09-18），并用顾问账号在真实 API 上逐项验证。

**验证到的事实（改动旧认知的部分）**

1. **顾问阈值远高于旧文档**：真实 check 的 `limit` 为 `LOW_SHARPE=1.58`、`LOW_FITNESS=1.0`、`HIGH_TURNOVER=0.7`、`LOW_SUB_UNIVERSE_SHARPE=1.05`（USA TOP3000 D1）。旧 SKILL 里写的 1.25 / 1.1 是普通账号标准。
2. **新增两类 check**：`IS_LADDER_SHARPE`（带 `year`/`startDate`/`endDate`）与 `LOW_2Y_SHARPE`（近 2 年 Sharpe，limit 同为 1.58）；弱信号会直接卡在 `LOW_2Y_SHARPE`。另有 `OLD_SIMULATION`（FAIL 表示需重模拟）、`DATA_DIVERSITY`、`PROD_CORRELATION`、`REGULAR_SUBMISSION`、`CLUSTER_TEST`（`ERROR` 也不阻断）。
3. **仿真进行中的 GET 不返回 `status`**：只有 `progress`。把"无 status"当异常会误判超时；正确做法是以 `Retry-After` 是否归零判断终态。
4. **多仿真确实可用**：`POST /simulations` 传 2 元素数组 → 父 sim 返回 `children` → 子 sim 各自带 `alpha`。实测 2 路 QUICK 模式约 95 秒完成。额度**按子仿真逐个计数**（4998→4994），多仿真只省时间不省额度。
5. **额度响应头**：`X-Ratelimit-Limit=5000` / `Remaining` / `Reset`（顾问账号实测）。
6. **列表可服务端过滤**：`GET /users/self/alphas?status=ACTIVE` 直接返回 22 条，不必拉全量 564 条再本地筛。
7. `OPTIONS /simulations` 的 settings 比正文文档多出 `maxTrade` / `maxPosition` / `testPeriod` / `lookback` / `simulationMode` / `selectionHandling` / `selectionLimit`；`type` 实为 `REGULAR` / `REGION_AGNOSTIC`（不是文档写的 `SUPER`）。

**代码改动**

- 新增 `scripts/wq_api.py`：统一认证/权限、`Retry-After` 轮询、终态机、多仿真、额度跟踪、`status=` 过滤、记录集解析、日期对齐相关、`SimulationCache` 去重、顾问阈值 `gate_report`、`submit_verified`。
- 新增 `scripts/simulate_batch.py`：批量回测 + 去重 + 可选提交（替代各 `wq_*_opt*.py` 里复制的样板）。
- 重写 `evolve_skill.py` / `wq_bulltrap_{opt,opt2,opt3,submit,record}.py` / `wq_fcf_{opt,corr,submit}.py` / `wq_ltinv_opt.py`，删掉各自的 `simulate()` 与固定 `sleep(8)`。

**仍有风险**

- `CLUSTER_TEST` 目前返回 `ERROR`（平台侧无数据），不影响提交但也不提供信息。
- 日收益相关仍是 proxy；`SELF_CORRELATION` 用信号级相关，护栏 2（信号成分重叠）不可省。

### 2026-10-29 — 内置模板 A–F 首次全量实测（顾问账号 USA TOP3000 D1）

依据：用 `scripts/wq_api.py` 对 §4.1.2 的六个内置模板各跑 1 次真实仿真，共消耗日额度 6 次（5000 的 0.12%）。完整数据见 §4.1.2 下的「实测基线」表。

1. **「通过率最高」是失真表述，已修正**：模板 A 实测 Sharpe 1.23 / Fitness 0.58，离顾问门槛 1.58 / 1.0 很远。该注脚的真实含义是「最不容易报错、最容易跑出结果」，与「能过门槛」是两个口径。凡把模板 A 当作高质量样本复用的场合（如 few-shot 示例、默认起点），都会把生成质量锚定在 1.2 量级。
2. **单腿全灭、双腿全过**：A/B/C/F（单信号）4 条全部未过；D/E（两条正交腿相加）2 条全过且分数最高（1.64 / 1.81）。样本仅 6 条不足以称规律，但机制成立——正交腿相加降波动、抬信息比。**在顾问门槛下，双腿混合应作为默认姿势。**
3. **B 差 0.01**（1.57 vs 1.58，Fitness 1.10 已过线），且 TO 11.2% 距上限 70% 有大量余量。这类「贴线」实例的正确处置是**参数邻域搜索**（decay / neutralization / window / truncation），不是换结构。新造模板首跑达标率实测 2/6，邻域搜索的先验成功率显著更高，成本还更低。
4. **未提交 alpha 上 `SELF_CORRELATION` 恒为 `PENDING`**，平台不计算。因此「模板是否值得进 few-shot」在物理上不可能依赖相关性——相关性只在提交动作后才被评估，且它是 **alpha 级**属性而非**模板级**（同一骨架换字段即可绕过）。判定「模板质量」时应显式排除 `SELF_CORRELATION` / `PROD_CORRELATION`。
5. **IS checks 的实际返回集合比 `BLOCKING_CHECKS` 白名单更大**：实测出现 `CLUSTER_TEST`、`OSMOSIS_ALLOCATION`、`MATCHES_THEMES`、`MATCHES_PYRAMID`，均不在旧白名单内。用白名单做「是否达标」判定的实现会静默放行这些项的 FAIL。**正确做法：除相关性两项外，任何 `FAIL`/`ERROR` 都阻断；`WARNING` 不阻断但必须记录**（A 的 `CLUSTER_TEST` 实测为 WARNING，value 1.45 / limit 1.58）。
6. **`CLUSTER_TEST` 在未提交 alpha 上也会给出数值**（本次 A 为 1.45，limit 1.58）。它是「与同簇 alpha 的相似度」的早期信号，可作为提交前低相关的辅助判据，但目前未纳入任何门禁。

### 2026-10-30 — 历史库反查：哪个模板最容易产出可提交 alpha（127 条样本统计，零仿真消耗）

依据：直接对本地 `alpha_db.json`（127 条：14 ACTIVE / 112 UNSUBMITTED / 1 REJECTED）按「顾问 D1 门槛（Sharpe ≥1.58、Fitness ≥1.0、1%≤TO≤70%）」重算，不动用任何仿真额度。完整表格见 §4.1.3。

1. **命中率最高的簇是期权 IV，不是基本面**：期权 IV（skew / pcr_oi）16 次尝试 10 次过线（62.5%）；OI 质量 19 次 8 次（42.1%）；现金流/EV 15 次 4 次（26.7%）；一次性探索的其他 81 次仅 2 次（2.5%）。SKILL 此前把「基本面最稳」当第一起点，是**单腿口径下的结论**，在双腿口径下不成立。
2. **腿数是比数据类型更强的分层变量**：双腿 24 次 / 8 ACTIVE（33.3%），单腿 103 次 / 6 ACTIVE（5.8%），相差 5.7 倍。A–F 首跑「双腿全过、单腿全灭」与历史库独立印证同一机制。
3. **据此新增模板 G（期权 IV skew × 基本面质量）**，写入 §4.1.2。它是库内唯一「多个 50/50 变体全部过线」的骨架：+OI/equity → 2.37/1.89/7.7%（ACTIVE）；+FCF/equity → 2.01/1.57/9.4%（ACTIVE）；+OI/equity 换 decay → 2.37/1.88/9.3%（未提交）。
4. **发现重复仿真**：`2rpzeGab` 与 `ZYE31mzx` 表达式完全相同（仅 decay 10 vs 15），属纯额度浪费——`SimulationCache` 的 hash 去重应在所有批量脚本里强制启用。
5. **9 条「已过线但未提交」存货**（QPGkoVeX 2.16/1.77、pwNrKp3j 2.28/1.62、2rpzeGab 2.37/1.88、1YzMkAdM 1.96/1.37、O0GPG0RR 1.81/1.10、78zb2WGx 1.74/1.32、WjV5Mn5N 1.79/1.45、v27aYRz 1.72/1.04、d5ZVZg5w 1.61/1.19）。**产新 alpha 之前应先把这批提交掉**，零仿真成本；提交前跑 §7.2 护栏 2（信号成分重叠），其中多条共享同一 IV 腿，大概率互撞，按 Sharpe 从高到低只提交首个、同簇其余放弃。
6. **口径提醒**：本节「过门槛」不含 `SELF_CORRELATION` / `PROD_CORRELATION`——这两项只在提交动作后才被平台计算，未提交 alpha 恒为 `PENDING`，因此历史库统计无法预知，只能靠护栏 2 提前拦。

### 2026-10-30 — 存货重跑反证：9 条已过线存货全部掉线（消耗 9 次仿真）

紧接上一条统计，把筛出的 9 条「已过顾问门槛但仍 UNSUBMITTED」的存货按原表达式、原 settings 全部重跑（单批多仿真 9 个，耗时 1m41s，额度 4991→4982）。

| 原 id | 新 id | 旧 S / F | 新 S / F | ΔSharpe | 结论 |
|---|---|---:|---:|---:|---|
| 2rpzeGab | E560aaxm | 2.37 / 1.88 | 1.63 / 1.00 | −0.74 | 唯一指标过线，卡 `LOW_SUB_UNIVERSE_SHARPE` 0.70 vs 0.71 |
| pwNrKp3j | gJeqPP0J | 2.28 / 1.62 | 2.01 / 1.22 | −0.27 | `CONCENTRATED_WEIGHT` 0.154>0.1 + Sub-Universe FAIL |
| QPGkoVeX | MPYl8829 | 2.16 / 1.77 | 1.55 / 1.02 | −0.61 | `LOW_SHARPE` + Sub-Universe FAIL |
| 1YzMkAdM | npvkzzX3 | 1.96 / 1.37 | 1.59 / 0.90 | −0.37 | `LOW_FITNESS`（WARNING 级）0.90 < 1.0 |
| O0GPG0RR | RREZaavz | 1.81 / 1.10 | 1.56 / 0.82 | −0.25 | Sharpe/Fitness/集中度/Sub-Universe 全 FAIL |
| WjV5Mn5N | KPJY88pl | 1.79 / 1.45 | 1.36 / 0.85 | −0.43 | 双指标 FAIL |
| 78zb2WGx | leA6zzY2 | 1.74 / 1.32 | 1.26 / 0.76 | −0.48 | 双指标 + Sub-Universe FAIL |
| v27aYRz | bl62PPgq | 1.72 / 1.04 | 1.44 / 0.74 | −0.28 | 双指标 FAIL |
| d5ZVZg5w | E560aaMm | 1.61 / 1.19 | 1.26 / 0.79 | −0.35 | 双指标 + `LOW_2Y_SHARPE` 1.57 vs 1.58 |

1. **「存货」是伪资产**：历史库里 Sharpe/Fitness 只在**仿真当时**成立。9 条重跑平均 −0.42 Sharpe、无一存活，说明平台在这 3 个月里延长了 IS 窗口 / 加入了新数据，而这些都是 2026-08 前的旧信号。
2. **`OLD_SIMULATION` 是掉线预警而非手续问题**：它不只是「需要重跑一下」，而是强预测「重跑就掉」。现在把它写进 §5.2。
3. **相关性豁免测算全部不成立**：即便把指标修好，9 条的最强冲突 ACTIVE 分别为 Gre2WN65（2.75）、ZYE31mzx（2.37）、9q7nYrZe（2.02）、gJ8kN8kl（1.68），豁免要求新 Sharpe ≥ 冲突 × 1.1，最高的 E560aaxm（1.63）需 ≥ 3.03，全部不可能满足。
4. **ROE 腿是池内最脏的组件**：护栏 2 对 `group_rank(ts_rank(operating_income/equity,126),subindustry)` 命中 12 个 ACTIVE，最强者 Sharpe 2.75。含这条腿的新 alpha 除非自身 Sharpe 能到 3.0+，否则一律别提交。
5. **`IS_LADDER_SHARPE` 的 PASS 阈值确认会打折**：E560aaxm TO=9.1% < 30%，其 limit 实测 2.02 而非 2.22（≈2.38×0.85），与 §5.2.1 一致；`CLUSTER_TEST` 在其上给出 0.63（WARNING），可作为同簇相似度的早期读数。
6. **结论修正**：不要再把「历史过线存货」当作低成本提交来源。真正低成本的路径是——用命中率最高的**骨架**（仍是双腿混合，模板 G 的结构）**换新腿/新字段重新构造**，而不是复用旧表达式。

### 2026-10-30 — 门槛核对：数值未提高，但发现 Power Pool 低门槛通道

用户提出「已是正式顾问，门槛可能被提高」，用实时数据核了一遍。**结论：常规门槛一个数字都没变，真正的新东西是 Power Pool。**

**验证方法**：`GET /alphas/{id}` 的 `is.checks[].limit` 是权威值（不是文档、不是 SKILL 记忆）。取自当天重跑的三个 USA TOP3000 D1 alpha：

| 检查项 | 实测 limit | SKILL 旧值 | 是否变化 |
|---|---:|---:|:---:|
| LOW_SHARPE | 1.58 | 1.58 | 未变 |
| LOW_FITNESS | 1.0 | 1.0 | 未变 |
| LOW_TURNOVER / HIGH_TURNOVER | 0.01 / 0.70 | 同 | 未变 |
| CONCENTRATED_WEIGHT | 0.1 | 0.1 | 未变 |
| CLUSTER_TEST | 1.58 | 1.58 | 未变 |
| LOW_2Y_SHARPE | 1.58 | 1.58 | 未变 |
| IS_LADDER_SHARPE | 2.02（TO 9.1% → 2.38×0.85）/ 1.58 | 与 §5.2.1 一致 | 未变 |

附带确认：`LOW_SUB_UNIVERSE_SHARPE` 的 limit 确实是 `0.75·√(1000/3000)·Sharpe = 0.433·Sharpe`（E560aaxm：0.433×1.63=0.71，实测 limit 0.71 ✓），即**抬高 Sharpe 会同步抬高它的门槛**，不能靠提 Sharpe 硬冲。

**新增（文档来源 `alpha-submission`，2026-09-18）**：Power Pool Alphas 通道，Sharpe 只要 **≥ 1.0**，代价是 ≤8 算子、≤3 唯一字段、Power Pool Correlation < 0.5。已写入 §5.1.2 与 §5.2。

**实测行为**：`POWER_POOL_CORRELATION` 在 22 个 ACTIVE 中的 9 个上出现，但**全部 `PENDING`**，`is.powerPoolCorrelation` 为 `None`。所以它现在不能当判据，只能按 4 条硬约束自己预筛。

**对「门槛提高」这个问题的直接回答**：数值没提高，但**有效门槛确实在上升**，机制是两个——① 信号随时间衰减（9 条存货平均 −0.42 Sharpe）；② 自己的 ACTIVE 池越厚，SELF_CORRELATION 越难过（豁免要求新 Sharpe ≥ 冲突 × 1.1，池里最强已到 2.75，等于要求新 alpha 做到 3.03）。**这是"池子变挤"，不是"分数线变高"。**


### 2026-10-30 — IV skew × ROE（模板 G）优化：Fitness 解法与「换字段」的边界

用户给 `0.5*rank(ts_mean((iv_call_180-iv_put_180)/iv_mean_180,5)) + 0.5*group_rank(ts_rank(operating_income/equity,126),subindustry)`，反馈 Fitness 略低（实测 `LLMbXVjn` S=1.59 / F=0.95 / TO=8.0%，`LOW_FITNESS` FAIL；`E560aaxm` S=1.63 / F=1.00 卡 `LOW_SUB_UNIVERSE_SHARPE` 0.70 vs 0.71）。两轮共 20 次仿真（额度 5000→4971）。

**结论一：Fitness 的解药是 INDUSTRY 中性化，不是 decay。** 同一表达式 SUBINDUSTRY(d15) → INDUSTRY(d15)：`F 0.95→1.08`、`Returns 4.47%→5.32%`、TO 几乎不动（8.0%→7.4%），`mLo2xNm9` 全部 IS check PASS。反向验证：decay 15→0 把 TO 抬到 19.7%、Sharpe 抬到 1.77，Fitness 反而掉到 0.89——因为分母从地板 0.125 变成真实 TO 0.197（+58%）而 Returns 只涨 12%。

**结论二：这条表达式无论如何都提交不了。** 护栏 1 显示 `mLo2xNm9` 与已 ACTIVE 的 `ZYE31mzx`（同一表达式）日收益相关 **0.975**，豁免需 Sharpe ≥ 2.37×1.1 = 2.61，实测 1.66 → 必 FAIL。

**结论三：在 IV 簇内换字段是无效工作量。** 20 次仿真里把 IV 腿换成 90/120/270 天 skew、`implied_volatility_mean_skew_270/360`、`pcr_oi_270`，质量腿换成 `cashflow_op/equity`、`operating_income/assets`、`free_cash_flow_reported_value/assets`、`ebitda/enterprise_value`，与池内 IV 类 ACTIVE（`58p0232N`/`ZYE31mzx`/`XgoQMAq1`）的日收益相关全部落在 **0.55–0.94**，无一低于 0.5。附带发现：IV × 现金流质量腿的组合几乎必然触发 `LOW_SUB_UNIVERSE_SHARPE`（0.29–0.51 vs limit 0.73–0.81），换期限 / 换中性化 / 降 truncation 都救不回来。

**结论四：脱簇后的可行解。** 把第二腿换到池内无人使用的 pv1 反转腿：

```fastexpr
0.4 * rank(-(close / open - 1))
+ 0.6 * group_rank(ts_rank(cashflow_op / equity, 126), subindustry)
-- decay=10, neutralization=INDUSTRY, truncation=0.08, nanHandling=ON
```

`E560gqE1` → **Sharpe 2.10 / Fitness 1.43 / TO 11.7% / Returns 5.81% / DD 2.7%**，全部 IS check PASS；护栏 2 无信号成分重叠；护栏 1 最大相关 **0.509**（vs `YPvlEl0l` S=1.63，豁免门槛 1.79，2.10 已满足），其余 0.401 / 0.373。次优 `bl62oNLK`（0.4×IV120 + 0.6×反转，S=1.71 / F=1.15 / TO 23.6%）与 `58p0232N` 相关 0.684，豁免门槛恰好 1.71——贴线，不建议。

**方法论沉淀**：本轮把「优化」拆成两个独立问题分别验证——① 指标能不能过（参数邻域搜索，3 次仿真定位 INDUSTRY）；② 相关能不能过（护栏 1+2，7 次仿真证明 IV 簇已饱和）。**先用少量仿真确认「指标解」存在，再用护栏判断这个骨架值不值得继续投入，比直接扑在字段排列组合上省得多。**

### 2026-10-30 — 提交 E560gqE1 失败：PROD_CORRELATION 0.8045 硬否决，以及「403 响应体才是判定书」

按上一轮结论提交 `E560gqE1`（0.4×pv1 反转 + 0.6×cashflow_op/equity，S=2.10 / F=1.43 / TO 11.7%）。**结果：未提交成功，被 `PROD_CORRELATION` 一票否决。**

**过程**：复核全绿（本地 gate PASS，13 项 IS check 全 PASS，`CLUSTER_TEST` 仅 WARNING），`POST /submit` 返回 **201**，但轮询 2 分钟 `dateSubmitted` 始终 `None`、status 卡 `UNSUBMITTED` —— 典型的「201 吞提交」。**再 POST 一次拿到 403，响应体给出了真实判定**：

```
PROD_CORRELATION  FAIL    value=0.8045 limit=0.7
SELF_CORRELATION  PASS    value=0.6226 limit=0.7
REGULAR_SUBMISSION PASS   value=0      limit=4      ← 配额根本没用完
```

**三条结论**

1. **指标全 PASS 与「能提交」是两件事。** `E560gqE1` 的每一项本地与平台 IS 指标都过线，`CLUSTER_TEST` 只是 WARNING，照样被生产池相关一票否决。此后评估候选的口径必须改成「指标 + 相关性」双轨，且相关性以提交时的 403 body 为准。

2. **本地护栏只能排除、不能放行。** 护栏用自己的 ACTIVE 池算日收益相关，近似 `SELF_CORRELATION`；它给出 0.509，实际 0.6226（低估 0.11），而真正致命的 `PROD_CORRELATION` 护栏**完全覆盖不到**。护栏 ≥ 0.45 就应按高危处理。

3. **`is.prodCorrelation` 是僵尸字段。** 22 条 ACTIVE 上全部为 `0.0`，平台不回算（`POWER_POOL_CORRELATION` 同样恒 `PENDING`）。因此「按信号族统计生产池拥挤度、挑不拥挤的族去造」这条路**做不出来**，已放弃并删除了相应脚本，不要再试。

**对 `E560gqE1` 的判读**：0.4×反转 + 0.6×现金流质量 这个组合与生产池相关 0.80，说明两条腿各自都是极其拥挤的常见信号，`SELF_CORRELATION` 0.62 也印证了这一点。靠调权重/decay/中性化降不到 0.7 以下——这与 IV 簇那 7 次仿真的结论一致：**同一信号族内换参数/换期限不改变相关性量级**。要过，只能换数据源（ Analyst / Sentiment / 供应链 / 另类数据这类池内无人使用的）。

**代码改动**：`wq_api.submit_verified` 在判定为「201 吞提交」后会自动再 POST 一次，并用新增的 `submit_verdict(resp)` 解析 403 body → 返回 `submit_blocked(PROD_CORRELATION=0.8045(limit=0.7))`；仅当 body 里没有任何 FAIL 项时才报 `submit_403_quota_exhausted`。新增 `scripts/submit_one.py`：先复核（status / gate / 全量 checks / 相关性）再决定是否提交，`--do-submit` 才真正动手，避免误提交与重复提交。

### 2026-10-30 — 换数据源两轮 20 次仿真：0/20，以及「冷门字段」假说的破产

`E560gqE1` 被 `PROD_CORRELATION 0.8045` 否决后的应对是「换数据源」。两轮各 10 次仿真（额度 4961→4941），**全部失败，最高 Sharpe 1.16**。

**第三轮（只按「我方零使用」选源）** — 选出 model51（系统性风险）、pv13（竞品/供应链关系）、news18（Ravenpack）、socialmedia8。结果：Sharpe **0.10–0.52**，含 model51 腿的普遍带 **46%–64% 回撤**并 `CONCENTRATED_WEIGHT FAIL`。

**第四轮（修正为「全局热门 ∩ 我方零使用」）** — 选出 `anl4_dts_rspe`（分析师分歧）、`anl4_netprofit_number`（覆盖度）、`capex/sales`、`adv20`、`sharesout`、`(high-low)/close`。结果：Sharpe **−0.33–1.16**，最好的是 `R4-3 0.5disp+0.5capex`（S=1.16 / F=0.62 / TO=4.9% / DD=3.9%）。

**三条结论**

1. **冷门是有原因的。** 只按「我方零使用」选，会选中全局也冷门的字段（model51 最高 userCount 4140、pv13 2818、socialmedia8 2783、news18 1238），它们本来就弱。改成「全局 userCount≥1500 ∩ 我方零使用」后，最好成绩从 0.52 提升到 1.16——方向对了，但**仍差 0.42 才够 1.58**，而参数邻域搜索历史上只能带来 ~0.07–0.10 的 Sharpe 提升。

2. **pv1 微观结构腿在这批里全灭。** `rank(-adv20)`、`rank(-ts_delta(sharesout,250))`、`rank(-ts_mean((high-low)/close,20))` 单独配对的 Sharpe 是 0.11 / 0.80 / 0.11，回撤最高 81%。真正撑住的是**两条慢速基本面/分析师腿**的组合（disp + capex，DD 3.9%）。

3. **`anl4_*_flag` / `anl4_*_ft` 是分类标记，不是数值预测值**（description 为 "forecast type (revision/new/...)"），不能做 `ts_rank`。同族只有 `*_number`（覆盖数量）、`anl4_dts_rspe`（估计标准差）、`anl4_ebit_value`（公告实际值）是数值字段——选字段前必须读 description，否则白烧仿真。

**由此产生的策略修正（重要）**：既然 `PROD_CORRELATION` 既不可预测也难以靠换源规避，另一条路是**走豁免**——相关性 ≥0.7 时，若新 alpha 的 Sharpe ≥ 冲突 alpha × 1.1 仍可过。我方池内最强 ACTIVE 已达 2.75，说明高 Sharpe 的拥挤信号确实能过关。`E560gqE1` 是败在「Sharpe 2.10 不够高」而不是「信号太像」。下一步应回到**能出高 Sharpe 的成熟信号族**（pv1 / fundamental6 / analyst4 / option8），把目标定在 2.5+ 去撞豁免线，而不是继续在低 Sharpe 的空白区里找。

**工具**：`scripts/datasource_scan.py`（零仿真成本）新增「甜点区」=`userCount≥1500 ∩ 我方零使用`；`--min-cov` 控覆盖度、`--min-user` 控热度、`--show <kw>` 按 dataset 关键字查字段并打印 description。

### 2026-10-31 — 豁免路径实跑：本账户已饱和，IS 与相关性互斥

用户要求「按豁免路径起一轮」：克隆 proven 高 Sharpe 结构（Gre2WN65 估值+质量 S=2.75、bldLbe6R 4 腿 S=2.22），换掉饱和腿 + 扫 neut/decay，目标撞 1.1× 豁免线。新增 `scripts/opt_exempt.py`（10 候选，batch_size=1 防连坐），跑两轮共 ~10 次有效仿真。

**结果（IS 检查 + 日收益 proxy 相关）：**

| 候选 | S | F | TO | IS | 最大 proxy 相关 | 结论 |
|---|---:|---:|---:|:--:|---|---|
| A1 EV/cf+FCF/eq IND d0 | 1.47 | 0.79 | 15.0% | ✗ | 0.651 (Gre2WN65 2.75) | 换腿掉线 |
| A2 EV/cf+FCF/eq SEC d4 | 1.06 | 0.59 | 7.6% | ✗ | — | 换腿掉线 |
| A3 EV/cf+FCF/liab IND d0 | 1.40 | 0.75 | 14.8% | ✗ | 0.635 | 换腿掉线 |
| **B1 4leg IND d0** | **2.12** | 1.29 | 26.6% | ✅ | **0.973** (bldLbe6R 2.22) | 需≥2.44 |
| B2 4leg EV/cf SEC d4 | 1.55 | 1.17 | 13.7% | ✗ | 0.919 | 掉线+相关 |
| B3 3leg SEC d4 | 1.24 | 0.85 | 9.2% | ✗ | 0.732 | 掉线+相关 |
| **C1 eps/close+FCF/liab IND d0** | **2.01** | 1.32 | 17.7% | ✅ | **0.810/0.798/0.750** | 需≥2.44/2.22/2.48 |
| C2 ROE/close+analyst SEC d4 | 0.90 | 0.54 | 5.8% | ✗ | 0.837 | 掉线+相关 |
| C3 (cf-capex)/close+FCF/eq SUBIND | 1.48 | 0.83 | 15.8% | ✗ | 0.807 | 掉线+相关 |
| C4 4leg fresh SEC d4 | 1.56 | 1.16 | 14.6% | ✗ | 0.848 | 掉线+相关 |

**三条铁律：**

1. **OI/equity 腿不可替换**。A 组把质量腿换成 FCF/equity / FCF/liab，Sharpe 直接塌到 1.06–1.47——`operating_income/equity` 才是 Sharpe 引擎，不是可替换组件。
2. **est_eps/close 家族能出清洁 IS passer（B1=2.12 / C1=2.01 全过），但它是 bldLbe6R 的克隆**——B1 与 bldLbe6R 日收益相关 **0.973**（仅 decay 0 vs 4）、C1 与三个 est_eps/close 家族 alpha 相关 0.75–0.81。豁免需 Sharpe ≥ 冲突 × 1.1 = 2.22×1.1 = **2.44**，两条都差 0.3+。
3. **IS 过线与相关性过线在本账户互斥**。达到 S≥1.58 的两条（B1/C1）必然 ≥0.7 相关；相关性 <0.7 的（A1/A3，proxy 0.63–0.65）必然 S<1.58。中间没有「既过 IS 又 <0.7」的甜点区。叠加 proxy 低估 selfCorrelation ~0.11（E560gqE1 实证：proxy 0.509 vs 实测 SELF 0.623）真实相关更高，甜点区更窄。

**根因**：本账户 22 条 ACTIVE 已覆盖两大引擎（OI/equity 9 条、est_eps/close 4 条）及其卫星腿（FCF/liab、ROE/close、动量、-liab/assets、IV skew）。任何基于这些引擎的新 alpha 都 ≥0.7 相关，且无法超越被克隆的冠军（2.22–2.75）的 1.1 倍。换空白数据源（第 3/4 轮）最高只到 1.16，连 IS 都过不了。**结论：本账户在已知家族内已饱和，增量提交期望收益≈0。**

**可行出路（未验证，留给下一轮）：**
- 唯一的数学可能是在 OI/equity/est_eps/close 之外找到**第三个高 Sharpe 引擎**且该引擎在本池无人使用——第 3/4 轮未找到（最高 1.16），需要更系统的因子挖掘而非字段排列。
- 或接受饱和现实，停止在本账户增量提交，转去**挖掘全新数据源的慢信号**（analyst 全文、供应链、另类数据），这类在第 4 轮甜点区里 `anl4_*` 数值字段（分歧/覆盖度）相关最低（0.5 档），是相对不拥挤的方向，但需要更长回看窗口和更精细的构造。

**工具更新**：`scripts/guard_new.py` 增加 `--glob`（默认 `opt_exempt_results.json`）与 `--only` 过滤，可对任意一轮候选跑双层护栏；`scripts/opt_exempt.py` 在 `run_many` 后加了空 alpha_id 重试兜底（偶发 API 返回空 id）。`scripts/exempt_scan.py` 把 22 条 ACTIVE 按 Sharpe 排序、输出结构特征到 `.workbuddy/active_structures.json`，是豁免路径的零成本起点。

### 2026-10-31 — Power Pool 形状的结构性洞察：(A−B)/mean(A,B) 是 ≤3 字段下的唯一高 Sharpe 结构

用户候选 `rank(ts_decay_linear((implied_volatility_call_180 - implied_volatility_put_180) / implied_volatility_mean_180, 5))`，问能否做成 PP alpha。**零仿真消耗判定，结论：形状够格、内容已死。**

**四道 PP 闸门的实际读数**：

| 闸门 | 阈值 | 候选实测 | 判定 |
|---|---|---|:--:|
| 算子数 | ≤ 8 | 4 | ✓ |
| 唯一字段 | ≤ 3 | 3 | ✓ |
| Sharpe | ≥ 1.0 | 同族 1.55（`58p0232N`） | ✓ |
| PP 相关 | < 0.5 | 撞 `58p0232N`，信号级相关 ≈1.0 | ✗ |

**致命点**：池内已有 ACTIVE `58p0232N` = `rank(ts_mean(同一 IV skew, 5))`（S=1.55 / F=1.18 / TO=11.5% / INDUSTRY / decay 10）。候选与它**同字段、同窗口、同 rank 外壳，只差 `ts_mean`→`ts_decay_linear`**。PP 相关门槛 0.5 比 SELF 的 0.7 更严，同一信号换平滑算子必挂。历史佐证：`JjGEGvJA` 即 `rank(ts_decay_linear(skew, 10))`（S=1.56 / F=1.00 / TO=16.1%），早已跑过、从未提交成功。

**核心洞察（可复用）**：IV skew 单腿就能到 Sharpe 1.55，**不是因为 IV 字段，而是因为 `(A − B) / mean(A,B)` 这个「两个同源反向分子 + 一个同源分母」的 3 字段形状**。分母取两分子均值使该指标天然有界，带来低换手、低回撤和稳定排序——这是在 ≤3 字段约束下唯一能同时满足「Sharpe ≥1.0」和「形状合规」的结构。推论：

- **优化 PP 候选应保留这个差分形状、换数据族**，而不是换期限/换窗口（后者已被 §12 的 7 次仿真证伪：同族换期限相关仍在 0.70–0.94）。
- 判定一个 PP 候选有没有希望，先问「它的 3 个字段是否构成一个正向分量对 + 一个归一化分母」；若是单比率（`a/b`）或单字段 rank，Sharpe 几乎必然落在 0.6–0.9（§5.1.2 首批实测 9 条非 model51 候选 0.09–0.92）。

**同构替代候选（零成本从本地字段快照挖出，未仿真）**：

| 族 | 正向分量对 | 覆盖度 | 我方使用 | 备注 |
|---|---|---|---|---|
| news12 | `news_high_exc_stddev` / `news_low_exc_stddev` | 0.965 / 0.971 | 零 | 新闻窗口内「高点→最新价」「最新价→低点」标准化变动；本质是价格量，需警惕与 pv1 振幅/反转隐藏相关 |
| analyst4 | `highest_sales_estimate` / `lowest_sales_estimate` | 1.0 / 1.0 | 零 | 语义是预测区间宽度（分歧），不是方向，需重新设计符号 |
| analyst4 | `anl4_buy` / `anl4_hold` | 0.624 | 零 | 均为 VECTOR，需 `vec_avg`，按旧经验不可直接进标量算子 |

**字段语义陷阱补充**：`implied_volatility_mean_180` 的 description 明确是 "The average of IvCall180 and IvPut180"——分母与分子同源，这正是该指标能稳定的原因。构造同构指标时应显式复刻这一点（用 `(A+B)/2` 作分母），不要换成 `close` / `cap` 之类异源分母。

---

### 2026-11-03 — 社区 ARC/GLB 模板复现：GLB 结构性不可达，EUR 打通后被 PROD_CORRELATION 否决

**背景**：按顾问论坛文章《10 个超级高效好用的 ARC/GLB 模板》复现，目标是从 ARC/GLB 两区挑"冷门但有信号"的字段套模板挖 alpha。
7 批共 47 次 FULL 仿真 + 1 次提交。

**一、文章前提与平台现实冲突（全部 API 实测）**

| 文章声称 | 实测 |
|---|---|
| §03 若干"2026-03 零用户抢跑数据集" | 在 GLB 列表端点**全部 EMPTY**（区域未铺开） |
| 模板 F2 用 `oth176_*`、F5 用 `star_rev_surprise`(model33) | 两个数据集**不在 GLB** |
| 模板依赖 `ts_decay_exp_window` / `group_median` | **GLB 不可用**（unknown/inaccessible operator） |
| 区域写作 "ARC/GLB" | 合法 region 代码里**没有 ARC**（最接近 AMR） |

GLB 实际可用且成熟的数据集：`model26`(388)、`model38`(200)、`model77`(20)、`model110`(8)、`fundamental17`(895)、`fundamental23`(1748)、`insider_agg_matrix`(17)。

**二、GLB 首批 8 候选：EMEA 是结构性短板**

| 候选 | 表达式骨架 | S | F | TO | AMER | APAC | EMEA |
|---|---|---|---|---|---|---|---|
| C7 STAR 估值 | `group_neut(vector_neut(rank(ts_arg_min(ts_backfill(star_val_sector_rank,60),120)), rank(ts_delta(cap,1))), subindustry)` | 1.85 | 0.99 | 26% | 0.95 | 1.75 | **0.61** |
| C5 EBITDA/EV | `group_neut(group_rank(ts_rank(fnd17_ebitda2ev,126),subindustry), industry)` | 1.76 | — | 66% | — | — | <0.6 |
| C4/C8 ROE/ROA | 同 C7 形态换 fnd23_roe | 1.38/1.37 | — | 69% | — | — | <0.6 |
| C2/C6 model77 情绪、insider | — | 0.15/0.10 | — | — | — | — | 死 |

第二批 5 个 EMEA 定向优化（降 decay / 去市值 delta 腿 / 双腿混合 / INDUSTRY 中性化）后，
13 次 GLB 仿真的 EMEA 分布 **−0.31 ~ 0.77，无一达 1.0**；降 decay 到 0 虽把 EMEA 抬到 0.77，
代价是 TO 冲到 79.1%（越 70% 上限）、F 崩到 0.58。**结论：市场结构问题，不是参数问题**，
除非引入 EMEA 专属数据源，否则不再投 GLB 预算。

**三、EUR 打通（单区域没有三子区门槛）**

迁移同信号到 EUR/TOP2500，经两刀优化后 4 个候选全检查通过：

| 改动 | S | F | TO | 说明 |
|---|---|---|---|---|
| 基线（argmin=120，无平滑） | 1.64 | 0.78 | 26.25% | F 差 0.22 |
| 市值腿加 `ts_mean(...,10)` | 1.51 | 0.98 | 15.70% | 只钝化对冲腿，不动主信号 |
| 再收窄 `ts_arg_min` 120→60 | **1.85** | **1.27** | 17.27% | 决定性一刀 |

四个通过者横跨 sm8/10、decay 4/5/6，指标稳定在 S 1.80–1.90 / F 1.26–1.27；
相邻的 a45、a75 则子宇宙检查失败（0.91/0.95、0.85/0.86）⇒ **a60 是真最优点**。

**四、失败的三个方向（都值得记）**

| 尝试 | 结果 | 原因 |
|---|---|---|
| `hump(alpha, 0.01)` 压换手 | S 1.64→**0.08**，TO→0.77% | rank 后数值量级太小，阈值吞掉几乎全部调仓 |
| 提高 decay 5→10 降换手 | TO 26.3%→15.2%，但 S 1.64→1.31，F 0.78→0.73 | 信号衰减快，平滑信号本身就伤 Sharpe |
| 缩宇宙 TOP2500→1200/800 | S 0.59~0.66 | 该信号需要大宇宙才活 |

**五、提交被拒：两项 FAIL，一可见一不可见**

提交 `JjeGme5m`（S 1.80 / F 1.26 / TO 16.02%）→ 403 判定书：

| 检查项 | 仿真后 | 提交判定 |
|---|---|---|
| `IS_LADDER_SHARPE` | WARNING 0.88/1.58 | **FAIL 0.88/1.58**（同一数值，两种裁定） |
| `PROD_CORRELATION` | PENDING | **FAIL 0.8314/0.7** |
| `SELF_CORRELATION` | PENDING | PASS（无值） |
| `REGULAR_SUBMISSION` | PENDING | PASS 0/4（配额未消耗） |

**三条结论**

1. **`gate_report` 通过只是必要条件。** ladder 类检查的 WARNING 不可采信，必须按 value<limit 判 FAIL
   → 已改为 `gate_report(strict=True)` 默认口径，并新增 `scripts/preflight.py`。
2. **`PROD_CORRELATION` 无法本地预测，只能用拥挤度先验分级。** EUR/TOP2500 的 `star_val_sector_rank`
   已有 19,800 个 alpha → 实测 0.8314；同族参考值：EBITDA/EV 0.7785、短周期反转 0.9673。
3. **四个同源候选不必逐个提交。** 只差平滑窗与 decay，prod corr 与 ladder 必然同量级，
   继续提交只是消耗额度，不改变结论（剩余配额保留）。


## 2026-11-04 · GBR/TOP700 价格反转族（analyst_revision_horizons）从 0.82 打到 1.78

起点：用户已有一条 `-ts_rank(price_change_30d_long_term, 22)`（GBR/TOP700/d1/SUBINDUSTRY，
QUICK 模式 S=0.82 / F=0.33 / TO=26.1%，CONCENTRATED_WEIGHT + LOW_2Y_SHARPE 双挂）。

**一、⚠️ QUICK 模式的 Sharpe 在 GBR 上系统性高估 0.4–0.5，不可用于定稿**

同一表达式 QUICK vs FULL 实测（13 组对照，全部同 settings 只改 `simulationMode`）：

| 表达式 | QUICK S | FULL S | 差 |
|---|---:|---:|---:|
| `rank(-ts_rank(短+中+长,126))` d5 | 1.94 | 1.43 | −0.51 |
| `rank(-ts_tscore(短+中+长,126))` d5 | 1.92 | 1.47 | −0.45 |
| `rank(-ts_rank(长,126))` d10 | 1.74 | 1.30 | −0.44 |
| `rank(-ts_rank(短+中+长,126))` d10 INDUSTRY | 1.95 | 1.52 | −0.43 |

逐年看，差异集中在 2014（1.00 vs 0.58）、2020（3.36 vs 1.55）、2023（1.58 vs 0.61）——
QUICK 的抽样显然在波动大的年份偏乐观。**⇒ SKILL §5.1.4 ⑧ 的「QUICK 指标与 FULL 完全相同」
只在个别样本成立，不能当通则。定稿必须 FULL 重跑；QUICK 只用来判断方向。**

**二、决定性杠杆是 `ts_rank` 窗口，不是 decay**

同一 `-ts_rank(price_change_30d_long_term, N)` 的 QUICK 扫描：

| N | 22 | 66 | 126 | 168 | 189 | 252 | 378 |
|---|---|---|---|---|---|---|---|
| S | 0.82 | 1.36 | **1.68** | 1.61 | 1.56 | 1.63 | 1.59 |
| TO | 26.1% | 19.4% | 17.9% | 17.2% | 16.9% | 16.4% | 15.9% |

把 22 天窗拉到 126 天，Sharpe 直接翻倍、换手降 1/3；之后再拉长已无增益（168–378 都在 1.56–1.63）。

**三、GBR 专用冷门字段：`*_vs_ftse100_30d_*` 与 52 周高低点（alphaCount 9–50）**

同一数据集 `analyst_revision_horizons` 内的冷门字段（均在 GBR 可用）：

| 字段 | alphaCount | 单独成腿 FULL S |
|---|---:|---:|
| `price_change_vs_ftse100_30d_{short,medium,long}_term`（3 腿求和） | 9–20 | 1.54 |
| `pct_change_from_52week_high_long_term`（**反号**） | 37 | 1.32 |
| `pct_diff_200day_moving_average_long_term`（**反号**） | 15 | 1.31 |
| `pct_diff_50day_moving_average_long_term`（**反号**） | 25 | 0.94 |
| `pct_change_from_52week_low_long_term`（**正号**，即原方向） | 12 | **−1.23**（反号后 ≈ +1.23） |

- **英国大盘是「反 52 周高点」的**：`+rank(ts_rank(pct_change_from_52week_high))` 使 0.5/0.5 混合
  从 +1.43 直接翻到 **−0.23** ⇒ 该腿单独 Sharpe ≈ −1.9。反号后才是可用腿，与文献（52 周高点动量）相反。
- 换成 ftse100 相对口径（去掉指数 beta）比裸价格好：裸 3 腿求和 1.43 → ftse 相对 1.54。
- 分析师修正类字段（`analyst_revision_percentile_score_long_3` 0.34、
  `model_score_change_30d_long` 0.16、`recommendation_change_component_long` −0.19）
  **单独都不可用**，本数据集里能承载信号的是价格分量，不是修正分量。

**四、最终形态：三腿等权/近似等权，全部检查通过**

```
0.4*rank(-ts_rank(ftse100 相对 短+中+长, 126))
+ 0.3*rank(-ts_rank(pct_change_from_52week_high_long_term, 126))
+ 0.3*rank(-ts_rank(pct_diff_50day_moving_average_long_term, 126))
decay=5, SUBINDUSTRY, truncation=0.08, maxTrade=ON, FULL
```

FULL 实测 `O0ANYnG1`：**S 1.78 / F 1.57 / TO 12.44% / Ret 9.71% / DD 4.81% / 2Y 1.65 / subU 0.90(limit 0.84) / CLUSTER 1.38**，
IS checks 全 PASS（只剩 SELF/PROD_CORRELATION 为 PENDING）。对比起点：S 0.82→1.78、F 0.33→1.57、TO 26.1%→12.4%、
与原 alpha 日收益相关仅 **0.246**（不是同一条曲线的微调）。

同批可选项（全部 IS PASS，供 A/B）：`ftse_h52_med` 1.75/1.51（DD 7.8% 偏差）、
`ftse_h52_low52` 1.71/1.46（subU 1.11 最稳）、`triple` 1.68/1.45（TO 10.5%、DD 4.3%）、
`ftse_h52` 1.70/1.47。

**五、参数邻域不稳，别把它当成"万能骨架"**

w126/d5 是实测峰值，邻域退化明显：`fh50_w168` 2Y 检查 FAIL、`fh50_d10` S 1.78→1.70、
`triple_d10` 1.68→1.61、`ftse_h52_w252` 1.70→1.40。⇒ 交付时报"峰值 + 邻域"，
不要只报单点；且这三腿高度同源（都吃价格），PROD_CORRELATION 预期偏高，提交前按 §9.1 的拥挤度先验分级。

---

### 2026-11-04（第二轮）— `PROD_CORRELATION 0.7621` 被拒 → 换族混腿 → `ZYQbbVnj` ACTIVE

**一、被拒现场**

上一轮定稿的 GBR/TOP700 三腿价格反转 `O0ANYnG1`，IS checks 全 PASS
（S 1.78 / F 1.57 / TO 12.44% / subU 0.90(limit 0.84) / CLUSTER 1.38），
`POST /alphas/{id}/submit` **第 1 次 POST 就 403**：

```
PROD_CORRELATION = 0.7621 (limit 0.7)   ← 唯一 FAIL
SELF_CORRELATION PASS
```

**配额没有消耗**（403 且 `REGULAR_SUBMISSION` 未 FAIL）。三腿全部来自
`analyst_revision_horizons`（`model` category）的**价格分量**，即整个表达式只有
"GBR 大盘价格反转"这一族信号——同族短周期反转在全局池的参考值是 **0.9673**。

**二、第一步：一次扫清 GBR/TOP700 的全部字段**

`/data-fields` 不带 `dataset.id`、`limit=50`（**200 会被 400 拒绝**）+ `offset` 翻页：

| 指标 | 值 |
|---|---|
| 字段总数 | **10,000** |
| dataset 数 | **138** |
| `type=MATRIX` | **6,094** |
| `MATRIX` 且 `coverage≥0.5 且 alphaCount<200` | **1,750** |

⇒ "没有别的族可换"是错误前提。真正的问题不是没有字段，而是**没按族筛过**。

**三、第二步：跨族单腿 FULL 实测排座次（20 条候选）**

设置统一：GBR/TOP700/delay=1/decay=5/SUBINDUSTRY/truncation 0.08/maxTrade ON，
表达式统一 `rank(±ts_rank(field, 126))`（部分改 `group_rank` / 去掉 `ts_rank`）。

| 腿 | dataset / category | 表达式 | FULL S | F | TO |
|---|---|---|---:|---:|---:|
| `breakaway_gap_up_mean_simscore_lookback60` | pattern_scores / pv | `rank(-ts_rank(f,126))` | **1.11** | 0.52 | 18.8% |
| `breakaway_gap_up_dynamic_simscore_lookback60` | pattern_scores / pv | 同上 | **1.05** | 0.47 | 19.4% |
| `common_gap_down_mean_simscore_lookback120` | pattern_scores / pv | `rank(ts_rank(f,126))` | **−1.36** | −0.88 | 10.9% |
| `mean_similarity_continuation_v_bottom` | pattern_scores / pv | 同上 | −0.98 | −0.40 | 22.3% |
| `mdl250_lmt_open_eq_score` / `mdl250_hc_eq_short` | model250 / model | `rank(f)` | 0.46 / 0.47 | 0.11 / 0.22 | 38.8% / 12.4% |
| `credit_risk_leverage_score_d1` | model36 / model | `rank(ts_rank(f,126))` | 0.36 | 0.12 | 9.7% |
| `default_risk_global_percentile_d1_2` | model36 / model | 同上 | 0.10 | 0.02 | 9.3% |
| `mdl238_sector_rank` | model238 / model | `group_rank(f,subindustry)` | 0.23 | 0.07 | 7.3% |
| `mdl238_region_owner_rank` | model238 / model | 同上 | −0.11 | −0.02 | 3.7% |
| `mdl25_eq_ro_v4_2_1_v21` | model25 / model | `rank(ts_rank(f,126))` | 0.23 | 0.06 | 4.2% |
| `mean_loan_rate` / `loaned_share_count`（shortinterest） | model | 同上 | CANCELLED（字段不可用） | — | — |
| `count_institutional_holders_security` / `market_value_*_disposed`（institutions6） | model | 同上 | −0.17 / −0.12 | — | 10% |
| `avg_secondary_top_buy_shares` / `avg_secondary_top_sell_shares`（insider） | model | 同上 | 0.30 / 0.00 | — | **141% / 150%** |
| `directional_indicator_*`（insider） | model | 同上 | −0.31 / 0.18 | — | 115–120% |

结论：

- **全 GBR 非价格池里，单腿 FULL S > 1.0 的只有 `pattern_scores` 这 2 条**
  （`breakaway_gap_up_*`）；其余全在 −0.3 ~ 0.5。
- 但**混腿不需要单腿强**：0.3–0.5 的腿只要"加进来不拖后腿"就有价值。
- **insider / shortinterest 这类腿换手 110–150%**，直接违反 TO < 70%，连混腿都别考虑。
- 反转号检验：`gap_down_mean` 原方向 −1.36，反号后 ≈ +1.36，**比 breakaway 还强**——
  这是下一轮的现成线索（本轮未测）。

**四、第三步：混腿权重梯度（同一骨架，只动权重与正交腿窗口）**

骨架 = `price_change_vs_ftse100_30d_{short+medium+long}`（下称 ftse）+ `pct_change_from_52week_high`（52w）
+ 正交腿 ps（`breakaway_gap_up_mean_simscore_lookback60`）。
设置 decay=5 / SUBINDUSTRY / truncation 0.08 / maxTrade ON 全不变。

| Alpha | 表达式 | 价格族权重 | ps 的 `ts_rank` 窗口 | FULL S | IS_LADDER | PROD_CORR |
|---|---|---:|---:|---:|---|---:|
| `O0ANYnG1` | 0.40 ftse + 0.30 52w + 0.30 MA50 | **100%** | — | 1.78 | PASS | **0.7621** |
| `kqNo1nE6` | 4 腿 0.30/0.225/0.225 + 0.25 ps_dyn | 75% | 126 | 1.78 | PASS 2.12/2.02 | **0.7510** |
| `Xg9b7z7a` | 0.40 ftse + 0.30 52w + 0.30 ps | 70% | 60 | 1.82 | PASS 1.84/1.75 | **0.7232** |
| `omELnaov` | 同上 | 70% | 100 | 1.74 | PASS 1.81/1.75 | **0.7236** |
| `JjeN5nrO` | 同上 | 70% | 126 | 1.73 | PASS 1.80/1.75 | **0.7184** |
| `mLomgpd5` | 同上 | 70% | **252** | 1.80 | PASS 2.09/2.02 | **0.7155** |
| `ZYQbbVnj` ✅ | 0.325 ftse + 0.325 52w + **0.35 ps** | **65%** | 252 | 1.78 | PASS 2.07/2.02 | **PASS（< 0.70，无法读出具体值）** |

三条可量化的规律：

1. **权重→corr 是凸的，前段几乎无效**：100%→75%（正交族 25%）只降 **0.0111**；
   75%→65%（正交族 30%→35%）降 **0.0355** 并直接过线。⇒ "混一点点"不是"不够"，是**基本没用**。
   有效区间斜率 ≈ **−0.03 / 5 个百分点**，但**不可线性外推**到高同族权重区。
2. **正交腿的 `ts_rank` 窗口越长，prod corr 越低**（60/100/126/252 → 0.7232/0.7236/0.7184/0.7155），
   而 Sharpe 反而略升（1.82→1.80，波动属噪音级）。加长窗口让这条腿变成"慢变量"，
   与价格反转的高频结构脱钩——**这是零成本的一刀**。
3. **过线时还压了最拥挤那条腿**：ftse 0.40 → 0.325，同时 52w 0.30 → 0.325。
   ⇒ 除了"总同族权重"，**单条最拥挤腿的权重也是旋钮**。

**五、第四步：双约束把可行窗口压到很窄**

降权重既降 corr，也**打死 `IS_LADDER_SHARPE`**（断崖，不是线性）：

| 价格族权重 | 65% | 60% | 55% | 50% |
|---|---:|---:|---:|---:|
| FULL S | 1.78 | 1.76 | 1.74 | 1.72 |
| IS_LADDER value / limit | **2.07 / 2.02 ✅** | 1.56 / 1.58 ❌ | 1.53 / 1.58 ❌ | 1.49 / 1.58 ❌ |

（`mLom63KX` / `d5Wb1l2v` / `O0AN8NxR`，S 0.06 的变化对应 ladder 0.5 的崩塌）

⇒ **`PROD_CORRELATION ≤ 0.70` 与 `IS_LADDER_SHARPE ≥ 1.58` 的可行交集只有 65%~70%**。
"继续压权重"不是出路，出路是**把正交腿本身做强**。

**六、反例：不是所有非价格腿都能混**

| 混入方案 | 结构 | FULL S | IS_LADDER | 结论 |
|---|---|---:|---|---|
| `pattern_scores` ps1 | 0.325/0.325/0.35 | **1.78** | PASS | ✅ 唯一可用 |
| 4 腿 `model250` + ps1 | 0.25×4 | **0.72** | FAIL 0.08 | ❌ ML 综合分与价格反转反向抵消 |
| 只留 1 条价格腿 | 0.45 ftse + 0.30 ps1 + 0.25 ps_dyn | 1.52 | FAIL 1.28 | ❌ 打散过头 |
| 1 条价格腿 + 0.45 ps1 | 0.30/0.25/0.45 | 1.63 | FAIL 1.48 | ❌ 同上 |
| ps1 套 `group_rank` | 0.40/0.30/0.30 | 1.60 | FAIL 1.43 | ❌ 额外中性化吃掉信号 |
| 换 pattern 字段 `adaptive_similarity` | 0.40/0.30/0.30 | 1.50 | FAIL 1.47 | ❌ 同族内部也分强弱 |

**七、最终形态与验收**

```
0.325*rank(-ts_rank(price_change_vs_ftse100_30d_short_term
                    + price_change_vs_ftse100_30d_medium_term
                    + price_change_vs_ftse100_30d_long_term, 126))
+ 0.325*rank(-ts_rank(pct_change_from_52week_high_long_term, 126))
+ 0.350*rank(-ts_rank(breakaway_gap_up_mean_simscore_lookback60, 252))
```

GBR / TOP700 / delay 1 / decay 5 / SUBINDUSTRY / truncation 0.08 / maxTrade ON / FULL：

| 项 | 值 |
|---|---|
| Sharpe | **1.78** |
| Fitness | **1.51** |
| Turnover | 12.31% |
| Returns | 8.98% |
| Drawdown | 5.53% |
| LOW_SUB_UNIVERSE_SHARPE | PASS 1.12 / 0.84 |
| IS_LADDER_SHARPE | PASS 2.07 / 2.02 |
| CLUSTER_TEST | PASS 1.47 / 1.0 |
| PROD_CORRELATION | **PASS（< 0.70）** |
| status | **ACTIVE**（`dateSubmitted=2026-11-04T03:47:19`） |

**提交过程特征**（值得记住）：FAIL 的候选 1–3 次 POST 就给 403；
成功的 `ZYQbbVnj` 从 POST#1 一路 200 到 POST#80（147 秒）才在 `GET /alphas/{id}`
里显示 `ACTIVE`。⇒ 成功路径的 POST 次数是失败的 20–80 倍，必须中途查状态才能早退。

**八、遗留线索（下一轮直接可用）**

- `common_gap_down_mean_simscore_lookback120` 反号单腿 ≈ **+1.36**，比本轮用的 breakaway（1.11）更强，
  且同样属 `pattern_scores`（pv）。未测过混腿，优先级最高的下一步。
- 若能把正交腿的单腿 S 提到 1.3+，65% 的价格权重就有余量继续往 60% 压，
  从而把 prod corr 进一步往 0.65 推，而不必担心 ladder 崩塌。

---

### 2026-11-04 — 第二条 GBR alpha：纯 pattern 四腿（`rKRergP3` 提交 ACTIVE）

背景：`ZYQbbVnj`（ftse + 52w + breakaway_gap_up，65% 价格族）已是本账号唯一 ACTIVE。
第二条要能提交，必须同时过 `SELF_CORRELATION`（信号级 0.7）与 `PROD_CORRELATION`（族级 0.7）。

**一、族扫描结论（GBR/TOP700 d1，均 FULL）**

- **GBR 有 `shortinterest3`（18 字段，coverage 0.82–0.87）**，但**所有字段都是 event inputs**：
  `ts_rank` → `Operator ts_rank does not support event inputs`；改用 `ts_backfill` **同样报错**。
  即借券族目前无法接入标准 rank/ts_rank 骨架，暂不可作混腿。
- `institutions*` / `insider*` / `model238` / `model53` / `model36` 单腿 S 全部 0.1–0.4，独立不可用；
  且掺进 pattern 骨架 ≥20% 权重会**打死 `IS_LADDER_SHARPE`**（1.28–1.42 vs 1.58）。
- 可用的第二条强腿都在 `pattern_scores`：

| 字段 | 方向表达式 | 单腿 FULL S | 与 ZYQ 日收益 corr |
|---|---|---:|---:|
| `breakaway_gap_down_mean_simscore_lookback60` | `rank(ts_rank(...,252))` | **+1.06** | +0.48 |
| `cont_v_bottom_mean_simscore_lookback60` | `rank(-ts_rank(...,252))` | **+1.10** | — |
| `common_gap_down_mean_simscore_lookback120` | `rank(-ts_rank(...,252))` | +0.93 | +0.15 |
| `desc_triangle_mean_simscore_lookback60` | 反号 | +0.31 | −0.15 |

> `cont_v_bottom` 用正号时 S = **−1.10**，与 BGD 几乎反向对冲（50/50 混出 −0.13）——符号必须反用。

**二、`PROD_CORRELATION` 实测：同族恒定 0.72–0.77，与权重/配比无关**

6 次提交全部 403，**均未消耗配额**（FAIL 1–13 次 POST 即给判定书），且 **`SELF_CORRELATION` 全部 PASS**
（代理日收益 corr 0.42–0.58）。⇒ 自相关不再是闸门，唯一闸门是 prod corr。

| Alpha | 构成（VB / BGD / CGD / 异族） | S | IS_LADDER | 代理 corr | **PROD_CORR** |
|---|---|---:|---|---:|---:|
| `Xg9JXkO5` | .20 / .45 / .35 / — | 1.75 | 2.27 PASS | 0.558 | **0.7245** ✅最低 |
| `npvPwjq8` | .25 / .45 / .30 / — | 1.78 | 2.32 PASS | 0.573 | 0.7354 |
| `zq3bX2WG` | .30 / .40 / .30 / — | 1.76 | 2.45 PASS | 0.554 | 0.7367 |
| `KPJrqvYg` | .15 / .35 / .35 / 13F .15 | 1.69 | 2.10 PASS | 0.498 | 0.7404 |
| `LLMZq1n2` | .25 / .30 / .45 / — | 1.60 | 2.50 PASS | 0.455 | 0.7592 |
| `O0A8qmVq` | .20 / .35 / .45 / — | 1.64 | 2.40 PASS | 0.478 | 0.7680 |
| **`rKRergP3`** ✅ | .20 / .30 / .25 / **分析师 .25** | **1.76** | **2.32 PASS** | 0.534 | **PASS → ACTIVE** |

读法（重要）：

- **GBR 反转/形态族的 prod corr 有 0.72–0.77 的硬地板**：把代理相关从 0.55 压到 0.42 完全没用
  （0.7592 / 0.7680 反而更高）。⇒ 与自研权重无关，是**族级/风格级饱和**。
- 真正把它压下去的是**换经济风格**：唯一过线的那条是掺了 **25% 分析师下调计数**
  （`predictive_starmine` 的 `analyst_downgrade_count_30d_4`，`rank(-ts_delta(...,20))`），
  同时把 pattern 权重降到 75%、并让 VB 与 BGD 各让出 10–15 个点。
- 13F（`market_value_institutional_shares_acquired/(acquired+disposed)`）在 12–15% 只能微降（≈0.74），
  20% 以上 ladder 崩（1.42）；**分量不够，换不来过线**。

**三、最终提交物（`rKRergP3`，2026-11-04T08:47:37-05:00 提交，status=ACTIVE）**

```fastexpr
0.25*rank(-ts_delta(analyst_downgrade_count_30d_4, 20))
+ 0.20*rank(-ts_rank(cont_v_bottom_mean_simscore_lookback60, 252))
+ 0.30*rank(ts_rank(breakaway_gap_down_mean_simscore_lookback60, 252))
+ 0.25*rank(-ts_rank(common_gap_down_mean_simscore_lookback120, 252))
```
GBR / TOP700 / d1 / decay 5 / SUBINDUSTRY / trunc 0.08 / maxTrade ON / FULL：
S=**1.76**、F=**1.18**、TO=14.75%、Ret=6.64%、DD=5.05%、margin=0.0009、long 420 / short 413；
`IS_LADDER_SHARPE` PASS 2.32/2.02、`LOW_SUB_UNIVERSE` PASS 1.06/0.83、`CLUSTER_TEST` PASS 1.35。
与 `ZYQbbVnj` 的日收益 corr = 0.534。

**四、可复用的两条规则**

1. **GBR 第二条 alpha 的必要条件不是"相关性更低"，而是"经济风格不同"**：同族内怎么调权重都在 0.72–0.77。
   可用的风格切换腿 = `predictive_starmine` 的分析师评级下调计数（`ts_delta` 取变化量，cov 0.946）。
2. **提交探测是廉价进度条**：同族 6 条候选 403 总耗时 < 1 分钟、不消耗配额，
   而每条 200-POST 到 ACTIVE 的成功路径要 10–80 次 POST ⇒ 先用 403 把 prod corr 摸清再决定是否继续。

## 2026-11-05 · `fnd6_miisa`（少数股东损益）族的可用性与跨数据集混腿（EUR/TOP2500）

**一、字段可用性（第一道坑）**

- `fnd6_miisa` 在 **USA 不存在**（USA snapshot 4367 字段里没有该 id）；只有
  EUR（TOP400–2500，coverage 0.50，TOP2500 alphaCount=8）、ASI/MINVOL1M（148）、
  CHN/TOP2000U（2）、GBR/TOP700（0.31）、DEU/TOP500（0.44）、ALL。
- **EUR 的 fundamental6 只有 279 条字段，且只剩 NCI 这一支**：裸名 `fnd6_at` / `fnd6_sale` /
  `fnd6_ib` / `fnd6_ceq` 在 EUR 全部 unknown。想构建比率，分母必须来自别的 dataset
  （`equity_to_equityholders`、`assets_total_2`、`dividends_noncontrolling_interest` 等，
  均属 fundamental23，coverage 0.76–0.89）。这正好把"跨数据集搭配"从可选变成必需。

**二、单腿（EUR/TOP2500/d1，decay 0，SUBINDUSTRY，8 条）**

| 信号 | S | TO |
|---|---:|---:|
| `(fnd6_ibmiisa−fnd6_miisa)/equity_to_equityholders`（母公司 ROE） | 0.88 | 2.4% |
| `(fnd6_ibmiisa−fnd6_miisa)/assets_total_2`（母公司 ROA） | 0.82 | 2.1% |
| `fnd6_miisa/equity_to_equityholders` | 0.71 | 2.0% |
| `fnd6_miisa/ibmiisa`（少数股东分走比例） | 0.67 | 1.9% |
| `mibt/(mibt+equity)` | 0.11 | — |
| 同信号套 `group_rank(ts_rank(...,504))` | 0.25 / −0.29 | — |

⇒ **ts_rank 会把该族信号打散**（与价格/分析师族相反），单腿天花板 0.88，不能单独交付。

**三、混腿梯度（12 条，全部 FULL）**

| 结构 | S | F | TO | IS_LADDER | SUB_UNIV |
|---|---:|---:|---:|---|---|
| 0.50 母公司 ROE + 0.50 反转252（INDUSTRY, d10） | 1.57 | 0.85 | 23.2% | FAIL | FAIL |
| 0.4/0.35/0.25（含 EBITDA/EV）（INDUSTRY, d10） | 1.70 | 1.07 | 18.2% | 1.19 FAIL | 0.62 FAIL |
| 同上换 SUBINDUSTRY | 1.85 | 1.14 | 19.1% | 1.12 FAIL | 0.84 FAIL |
| 同上 + 派息腿 0.20（四腿） | 1.87 | 1.19 | 17.3% | 1.58 边界 | 0.87 FAIL |
| 反转腿 0.28→0.33→0.35→0.38（**最终**，末档叠加 d6） | 1.87→1.96→2.00→**2.24** | 1.14 | 33.0% | **PASS 2.39/2.21** | **PASS 1.19/1.16** |

**四、最终提交物（`RREAx3Na`，2026-11-05T00:20:51-05:00，status=ACTIVE）**

```fastexpr
0.27*rank(ts_backfill((fnd6_ibmiisa - fnd6_miisa)/(abs(equity_to_equityholders)+0.01),60))
+ 0.38*group_rank(-ts_rank(returns,252),subindustry)
+ 0.15*group_rank(ts_rank(fnd17_ebitda2ev_a,126),subindustry)
+ 0.20*group_rank(ts_rank(dividends_noncontrolling_interest/(abs(fnd6_mibt)+0.01),252),subindustry)
```
EUR/TOP2500/d1 / **decay 6** / SUBINDUSTRY / trunc 0.08 / FULL：
S **2.24**、F **1.14**、TO 33.0%、Ret 8.48%、DD 4.89%；`IS_LADDER` PASS 2.39/2.21、
`LOW_SUB_UNIVERSE` PASS 1.19/1.16、`CONCENTRATED_WEIGHT` PASS；
`is.selfCorrelation = 0.0`、**`is.prodCorrelation = 0.6761`**（PASS，距 0.7 仅 0.024）。

**五、可复用结论**

1. **decay 对该混合是双刃**：d10→S 1.75 / d6→S 2.24，ladder 由 FAIL 转 PASS；但再低到 d0 换手会破 70% 的风险上升。
   规律与 §5.1.4 ⑩ 一致：表达式已含 `ts_rank` 时，decay 与内部窗口共用一个平滑预算。
2. **`ts_backfill(...,60)` 是免费提升**：S 1.81→1.88、F 1.17→1.24——因为 `fnd6_miisa` 覆盖率只有 0.5，
   补值让有效票数变多，也顺带缓解 `LOW_SUB_UNIVERSE`。
3. **提权反转腿是同时修 Sharpe 与 sub-universe 的唯一一刀**（0.28→0.38：S +0.36、sub 0.87→1.19），
   而换 neutralization（MARKET / cap 中性）全部更差。
4. **提交耗时再创新高**：`max_posts=100`（182 秒）仍是 200/UNSUBMITTED，再补 10 次才转 ACTIVE ⇒
   成功路径可达约 110 次 POST，脚本上限至少设 150。
5. **prod corr 在 ACTIVE 上这次可读（0.6761）**，推翻了"PASS 后恒为 0.0"的旧说法；读数非 0 时应作为同族基线。

---

## 2026-11-06 · 会议出席 × 经营现金流：2014–2020 全亏的根因与 3 腿改造（USA/TOP3000）

**一、用户原式与年度形态**

```fastexpr
trade_when(vec_count(buyside_attendance_count)>0, rank(operating_cash_flow), -1)
```
USA/TOP3000/d1 / decay 0 / SUBINDUSTRY / QUICK，`xArlllWg`：

| 年 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|---|---|---|
| S | −0.28 | −0.15 | −0.51 | −0.54 | −0.25 | −0.45 | **+0.42** | **+2.50** | **+1.62** | +0.14 |

全期 S **0.28**、F **0.06**、TO 1.6%。

**二、根因（三条，均经对照仿真证伪/证实）**

1. **`rank(operating_cash_flow)` 是绝对金额排名 ⇒ 规模/龙头暴露**，不是现金流信号。
   对照：把分母换成 `assets_total_2`（S 0.27）或 `cap`（S 0.15）后，**年度形态完全不变**
   （2015–2020 仍全负）⇒ 不是"规模 tilt"这么简单，而是价值/质量 vs 成长的 regime。
2. **`trade_when(...,-1)` 让信号几乎冻结**：只在电话会议事件日换仓，TO 1.2%，
   等于用几次陈旧的大类 tilt 撑整条曲线。去掉门控后同信号 S 0.27→0.46。
3. **`vec_count` 只数"当天有几条会议记录"**，丢掉"来了多少买方"的强度信息；`nanHandling=OFF`。

**三、可用字段（实测元数据）**

| 字段 | dataset | type | coverage | alphaCount |
|---|---|---|---:|---:|
| `buyside_attendance_count` | analyst83 | VECTOR | 0.763 | **1** |
| `count_questions_buyside_qa` / `buyside_word_count_qa` | analyst83 | VECTOR | 0.76 | 1–2 |
| `operating_cash_flow` | fundamental23 | MATRIX | 1.00 | 88 |
| `assets_total_2` | fundamental23 | MATRIX | 1.00 | 48 |

analyst83 的 sentiment 字段 coverage 只有 **0.0086**，不可用。

**四、改造过程（QUICK 筛选 + FULL 定稿）**

| 候选 | S | F | TO | 判断 |
|---|---:|---:|---:|---|
| 单腿 OCF/assets | 0.27 | 0.06 | 1.8% | 太弱 |
| 单腿 OCF/cap | 0.15 | 0.04 | — | 太弱 |
| 单腿 `ts_rank(OCF/assets,504)` grouped | 0.75 | — | 3.1% | 方向对 |
| 单腿 analyst83 出席强度 `vec_sum` ts_mean60 | 0.48 | — | 14.6% | 有独立信息 |
| OCF + 出席 + 反转126（0.4/0.3/0.3，无 decay） | 1.88 | 0.57 | **73.3%** | TO 超限 |
| 同上改反转252 + decay10（35/30/35） | 1.88 | 1.25 | 12.9% | ✅ **`QPvWNOqW`** |
| 同上 0.40/0.30/0.30 | 1.74 | 1.09 | 10.4% | ✅ `N1NKJL6w` |
| 去反转腿（0.4/0.6 或 0.5/0.5） | 1.08–1.13 | <1.0 | 2–3% | ❌ gate FAIL |
| fundamental23 → model109（`analyst_eps_revision_ntm_3m`） | 1.10–1.38 | <1.0 | — | ❌ Sharpe 掉穿门槛 |

**最终形态（`QPvWNOqW`，FULL）**

```fastexpr
0.35*group_rank(ts_rank(operating_cash_flow/assets_total_2, 504), subindustry)
+ 0.30*group_rank(ts_mean(vec_sum(buyside_attendance_count), 60), subindustry)
+ 0.35*rank(-ts_rank(returns, 252))
```
decay 10 / SUBINDUSTRY / trunc 0.08：S **1.88**、F **1.25**、TO **12.9%**、Ret 5.72%、DD 3.34%；
IS checks 全 PASS（ladder 2.68/2.02、sub-universe 1.40/0.81）；年度 **2014 起十年全正**
（1.69/1.89/0.69/0.41/1.28/1.30/1.43/3.49/2.81/2.56）。

**五、兜底：PROD_CORRELATION 0.7588 拒绝，且权重完全无效**

| 权重（OCF/出席/反转） | S | prod corr |
|---|---:|---:|
| 35/30/35（原版） | 1.88 | **0.7588** |
| 30/35/30 | 1.85 | 0.7613（↑） |
| 40/35/25 | 1.80 | 0.7508（仅 −0.008） |
| 10/40/50（放大反转） | 2.15 | **0.8601**（↑↑） |

⇒ **`fundamental23` 与 `pv1` 反转同时在饱和**，改任一腿权重只是换"哪个拥挤源主导"，
不是降 corr。§8.4.3 的 `−0.03 / 5%` 只对「拥挤源是价格族」的骨架成立。
**本次结论：该三腿混合在 USA/TOP3000 不可提交；要救只能换 region 或换掉其中一个饱和族。**

**六、可复用结论**

1. **先验证"信号是不是它自己"**：`rank(绝对值)` 一律先怀疑规模。判据是换分母后年度形态是否改变；
   不变 ⇒ 不是规模问题，是族级 regime，别在窗口/decay 上浪费时间。
2. **事件类字段不要当开关，要当信号**：`vec_sum(...)` 取强度 + `ts_mean(...,60)`，单腿 0.48 但有独立信息。
3. **`trade_when(...,-1)` 的隐性代价是"零独立下注"**：TO 1–2% 意味着整条曲线由个位数调仓决定。
4. **252 日反转腿是唯一能把 2014–2019 翻正的补丁**，但它同时是 prod corr 的第二拥挤源——
   Sharpe 与 corr 在同一处被锁死，这是本次的死局。

**七、换 region 的实测（2026-11-06，同一批字段族）**

| region/universe | 可用字段 | 最好结果 | 结论 |
|---|---|---:|---|
| USA/TOP3000 | `operating_cash_flow`+`assets_total_2`+analyst83 出席 | S 1.88 / F 1.25 | prod corr 0.7588 ❌ |
| GBR/TOP700 | 仅 pv1 + analyst83 出席（cov **0.32**），无任何基本面 | S 0.16–0.63；出席单腿 **−0.47** | ❌ 宇宙太小 + 覆盖率太低 |
| DEU/TOP500 | 同上（cov 0.33） | S 0.78–0.81；出席单腿 0.09 | ❌ |
| EUR/TOP2500 | `fnd23_ofc`(ac 17)+`assets_total_2`(ac 63)+`fnd23_roe`(ac 10)，**无 analyst83** | S 1.55–1.70 但 **IS_LADDER 0.44–0.68 FAIL**、F 0.7 | ❌ 近年失效 |
| KOR/TOP600 | `cashflow_op`(cov 0.70)+`fnd17_fcf1a`(ac 23) | S 1.33 / F 0.89 / ladder 0.66 | ❌ |
| **ASI/MINVOL1M** | `cashflow_op`(ac 3047)+`fnd17_fcf1a`(ac 711)+`returns` | **S 2.09 / F 1.42 / ladder 2.06 PASS** | ✅ **`VkxZg7n0`** |

**关键结论**

1. **`operating_cash_flow` 是 USA 专属**（fundamental23 的该裸名只在美国可用）；EUR 的等价字段是
   `fnd23_ofc`，但**字段名不同 ≠ 族不同**——迁移时必须先用 `field_availability` 逐字段确认。
2. **GBR/DEU 是 fast-factor 区域，只有 pv1**，任何"基本面 + 事件"骨架都迁不过去；
   analyst83 在那里的 coverage 只有 0.32–0.33，事件腿本身变成噪声（单腿负 Sharpe）。
3. **EUR 的 OCF 族单腿能到 1.55–1.70，但 IS_LADDER 全线 0.44–0.68**——与 §4.4 的 EUR 经验一致：
   EUR 近年（2021–2023）对现金流/反转混合不友好，必须靠额外正交腿才能过 ladder（`RREAx3Na` 用了 4 腿）。
4. **ASI/MINVOL1M 是目前唯一同时满足 Sharpe / Fitness / ladder 的区域**：

```fastexpr
0.50*rank(cashflow_op/cap) + 0.50*rank(-ts_rank(returns, 252))
```
ASI/MINVOL1M/d1 / decay 6 / SUBINDUSTRY / trunc 0.08 / **maxTrade ON** → `VkxZg7n0`
S **2.09**、F **1.42**、TO 22.1%、Ret 10.24%、DD 5.83%；ladder **PASS 2.06/2.02**、
SUB_UNIVERSE 2.09/0.62；年度 2014–2023 **全正**（3.30/2.15/2.57/2.01/2.25/2.82/**0.13**/2.11/1.76/2.53）。
`0.45/0.55` 变体 `wpQ3MjXp`：S 2.08 / F 1.36 / ladder 2.04，略差。
**未提交**（`cashflow_op` alphaCount 3047、`returns` 110420，prod corr 风险 MID，须待显式授权）。
