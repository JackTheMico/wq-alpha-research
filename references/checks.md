# 指标与检查（SKILL.md §5 迁出）

> 由 `SKILL.md` §5 迁出，**节号保持不变**，文中「第 N 节」等交叉引用仍指向原编号。
> 回主页：[`SKILL.md`](../SKILL.md)。结论与状态查 [`ledger.md`](ledger.md)。

## 5. 指标与检查

### 5.1 核心指标

| 指标 | 公式/含义 | 目标 |
|------|-----------|------|
| Sharpe | 日 IR × √252 | 见 5.1.1 阈值表 |
| Fitness | Sharpe × √(abs(Returns) / max(TO, 0.125)) | 见 5.1.1 阈值表 |
| Returns | 年化收益 / $10M | ≥ 7% |
| Turnover | 日交易额 / Book Size | 1%–70% |
| Drawdown | 峰值到谷值最大回撤 | < 15% |
| Margin | PnL / 总交易额 | 越高越好 |

#### Fitness 公式的两个实战推论（2026-10-30 实测校准，重要）

`Fitness = Sharpe × √(|Returns| / max(TO, 0.125))`，用 6 个真实仿真逐条反算验证吻合（误差 <0.005）。由此得到两条会直接改变优化方向的结论：

1. **TO 低于 12.5% 时，再降 TO 对 Fitness 毫无贡献**——分母被 0.125 地板锁死。此时 `Fitness = 2.828 × Sharpe × √Returns`，只受 Sharpe 和 Returns 支配。低换手因子的「降 TO 提 Fitness」直觉在这个区间是错的。
2. **开 TO 上限换取 Returns 通常是亏的**：把 decay 从 15 降到 0，TO 8.0%→19.7%、Sharpe 1.59→1.77，但 Fitness 反而 0.95→0.89（分母从地板 0.125 变成真实 TO 0.197，涨了 58%，而 Returns 只涨 12%）。**只有 Returns 的涨幅超过 TO 的涨幅（即 margin 提升）时，提 TO 才划算。**

推论：Fitness 贴线时先动 **neutralization**（见 §6）和 **信号质量**，decay 只在 TO 已经 >12.5% 时才是有效杠杆。

### 5.1.1 提交阈值：顾问账号 vs 普通账号（易踩坑）

**顾问账号（CONSULTANT 权限）的提交门槛明显更高，与普通账号不同。** 判定以 `GET /alphas/{id}` 的 `is.checks[].limit` 为**权威值**，不要凭记忆写死。

| 指标 | 顾问 D1 | 顾问 D0 | 普通账号（参考） |
|------|---------|---------|------------------|
| Sharpe | **> 1.58** | **> 2.69** | > 1.25 |
| Fitness | **> 1.0** | **> 1.5** | > 1.0 |
| Turnover | 1%–70% | 1%–70% | 1%–70% |
| Max weight | 单股 < 10%（OS 阶段 USA < 8%） | 同左 | 单股 < 10% |

区域特例：

| 区域 | 追加门槛 |
|------|----------|
| CHN | D1: Sharpe ≥ 2.08, Returns ≥ 8%, Fitness ≥ 1.0；D0: Sharpe ≥ 3.5, Returns ≥ 12%, Fitness ≥ 1.5；且 Robust universe 需保留 ≥ 40% 的收益与 Sharpe |
| ASI | Robust Universe 需保留 ≥ 90% 收益与 Sharpe；MaxTrade 必须 ON |
| ASI/JPN/HKG/TWN/KOR | Investability Sharpe：`maxtrade=ON`，或 `investability Sharpe > 原 Sharpe × 0.7` |
| SuperAlpha | 门槛同 alpha，但 turnover 改为 **2% ≤ TO < 40%** |

#### 5.1.1.1 质量闸门：平台线 ≠ 值得交（Fitness ≥ 2.0 / Margin ≥ 10‱）

平台 `LOW_FITNESS` 的 limit 只有 1.0，但**「能提交」不代表「该提交」**。质量差的因子交多了会把 Value Factor 打到 0.10 量级，之后交再多也救不回来——「为了交而交」是新手最贵的错误。因此本地在平台线之上再卡一道质量线（`wq_api.QUALITY_*`，`gate_report` / `preflight` 默认开启）：

| 指标 | 质量线 | 说明 |
|------|--------|------|
| **Fitness** | **≥ 2.0**（2.5+ 才算好的 regular alpha） | 主排序指标；低于 2.0 直接阻断，不再看 Sharpe |
| **Margin** | **≥ 10‱（0.001）**，30‱+ 更佳 | 低于 10‱ 收益盖不住手续费，交上去是负贡献 |
| Returns / Drawdown | DD ≤ Returns | 回撤大于收益的 PnL 形态直接阻断 |
| PnL 平滑度 / 逐年稳定性 | 人工复核 | 逐年 Sharpe/Fitness 不应有明显断层（记录集 `yearly-stats` 可查） |

- 只重点看 **Fitness、Margin、Returns、Drawdown**，其余指标不必纠结。
- `preflight.py` 的渲染会打印 `质量线: Fitness ≥ 2.0  Margin ≥ 10‱`，NO-GO 时先看是不是这一项。
- 复盘对照或确有必要时，可传 `quality=False`（分别对应 `gate_report(..., quality=False)` / `preflight.evaluate(..., quality=False)`）。

#### 5.1.2 Power Pool Alphas（低 Sharpe 通道，Sharpe ≥ 1.0 即可）

来源：`GET /tutorial-pages/alpha-submission`（lastModified 2026-09-18）「Power Pool Alphas」章节。**这是顾问账号上 Sharpe 门槛最低的一条路径**，四类条件必须同时满足：

| 条件 | 阈值 |
|------|------|
| Sharpe | **≥ 1.0**（远低于顾问常规的 1.58） |
| 算子总数 | **≤ 8**（含重复算子；`ts_backfill` / `group_backfill` **不计入**） |
| 唯一数据字段 | **≤ 3**（不含分组字段） |
| Power Pool Correlation | **< 0.5**（比 SELF/PROD 的 0.7 更严） |

分组字段（不计入字段数）：`country` `industry` `subindustry` `currency` `market` `sector` `exchange` `split` `adjfactor`。

**实战含义**：简单表达式（`rank(ts_mean(...))`、`group_rank(ts_rank(x,N),subindustry)` 这类 2–3 字段结构）天然满足算子/字段约束，只要把 Sharpe 做到 1.0+ 且对 Power Pool 相关 < 0.5 就能进池。**当常规通道卡在 1.58 时，值得专门构造 ≤3 字段的极简版本走这条路。**

**官方文档中另外三条容易漏读的规则（`GET /tutorial-pages/alpha-submission` 原文，2026-10-31 复核）**：

1. **相关性不是硬否决，是可补偿的**：原文 "If the Power Pool correlation is > 0.5, the Alpha must have a Sharpe at least 10% higher than the most correlated Alpha to be considered eligible for submission." —— 即 PP 相关 0.5 只是默认线，只要 Sharpe 比**最相关那个 alpha 高出 10%** 仍可提交。构造候选时若 PP 相关落在 0.5–0.7，不要直接放弃，先算这条。
2. **tag 不可逆**：原文 "Once you tag an Alpha as power pool, it stays in the self-correlation pool even if you untag it later." —— 给 alpha 打 PP tag 是单向门，打错就永久污染 self-correlation 池。**只对确定要投 PP 的候选打 tag，绝不在试验品上打。**
3. **theme 决定 eligibility**：原文 "Eligible region, delay, universe and other conditions (risk neutralization, datasets, turnover ranges, etc) are defined by the active Power Pool theme (e.g. GLB/D1, All regions/D0, EUR/D1 Fast Factors)." —— 字段数/算子数只是必要项，region/delay/universe/中性化还必须命中**当前活跃 theme**，否则 checks 里 `MATCHES_THEMES` 会 WARNING。

#### 5.1.3 PP 候选的构造准则：(A − B) / mean(A, B) 结构

这是 ≤3 字段约束下**唯一能稳定把 Sharpe 推到 1.0 以上**的形状，来自对 IV skew（单腿 Sharpe 1.55–1.60）的解剖：

```
(A − B) / mean(A, B)          # 3 字段、4 算子，天然合规
```

- `A` / `B` 是**同源的反向分量对**（call vs put、up vs down、high vs low），分子做差分取方向，分母取两者均值做归一化。
- 分母与分子同源是这个结构的关键：`implied_volatility_mean_180` 的官方描述就是 "The average of IvCall180 and IvPut180"。同源归一化让指标天然有界、噪声自消，于是 turnover 低、回撤小、排序稳定。
- **反例**：单比率 `a/b`、单字段 `rank(x)`、异源分母 `x/close` —— 这类形状在 USA TOP3000 上实测 Sharpe 普遍落在 0.6–0.9（§5.1.2 首批 9 条非 model51 候选：0.09–0.92），够不到 PP 的 1.0。
- **推论**：优化 PP 候选时，先问「我的 3 个字段构不构成一个正向分量对 + 一个同源归一化分母」。若不构成，换窗口/换期限是无效劳动（§12 已用 7 次仿真证伪：同族换期限相关仍 0.70–0.94，Sharpe 也不会质变）。
- **换族而非换参数**：IV 族的这个形状已被本池 `58p0232N`（`rank(ts_mean(同一 skew,5))`，S=1.55）占位，再做任何 IV skew 变体都撞 PP 相关。正确动作是保住形状、换数据族。

**已验证的行为**：`POWER_POOL_CORRELATION` 在 alpha 的 `is.checks[]` 里**对合格候选出现**，但实测在 ACTIVE alpha 上**恒为 `PENDING`**（`is.powerPoolCorrelation` 也为 `None`）——平台在当前阶段并未回算该值。因此**不能**用它做提交前判据，只能按上面 4 条硬约束自行预筛。

> **⚠️ 实测修正（2026-10-31，首批 10 候选全量仿真 + 提交实测）**
> 1. **`build_payload(sim_type="POWER_POOL")` 直接 400**：`{"type":["Object with name=POWER_POOL does not exist."]}`。
>    仿真 `type` 只能是 `"REGULAR"`，**Power Pool 不是合法的 `type` 值**，不能靠设 type 进 PP 通道。
> 2. **~~平台不会自动路由到 PP，触发方式未查清~~ → 已查清：靠 alpha 的 `POWER_POOL` tag**
>    （2026-10-31 补测，见下方 §5.1.4）。**不带 tag 提交时 checks 里根本没有
>    `POWER_POOL_CORRELATION` 这一项**，`LOW_SHARPE` 直接按 1.58 判 FAIL；**带 tag 后
>    checks 会挂上 `POWER_POOL_CORRELATION` + `POWER_POOL_DESCRIPTION_FORMAT` 两个 PP 专属项**，
>    但实测 `LOW_SHARPE` 的 limit **仍是 1.58**——因为 description 未填，PP 资格不成立，平台退回常规通道。
> 3. **`model51` 字段（如 `unsystematic_risk_last_360_days`）双杀**：实测提交出现
>    `CONCENTRATED_WEIGHT` FAIL（None/None）+ `LOW_COVERAGE` FAIL（value=17, limit=5），
>    **常规与 PP 两条通道都过不去**。PP 候选避开 model51。
> 4. **单腿「未饱和」基本面/分析师在 USA TOP3000 上打不到 1.0**：首批 9 条非 model51 候选
>    Sharpe 仅 0.09–0.92（F4 `anl4_ebitda_value/debt` 最高 0.92，仍 <1.0）；唯一 ≥1.0 的是
>    model51（1.44，但被第 3 点双杀）。能稳定 ≥1.0 的单腿几乎都是**已饱和族**
>    （`operating_income/equity`≈1.23、IV skew 1.5+），但那些又撞 SELF/PP 相关。
>    ⇒ 想用 ≤3 字段达到 PP 的 Sharpe≥1.0，**更靠谱的是 ≤3 字段的双腿正交混合**（见 §10 双腿 33% 命中率），
>    而非单腿未饱和信号——单腿未饱和信号普遍卡在 0.6–0.9。

#### 5.1.4 PP 提交机制实测：`POWER_POOL` tag 怎么打、缺什么会退回常规通道

2026-10-31 在真实账户上做的对照实验（零仿真消耗，只涉及元数据与提交尝试）。

**① tag 怎么打**：alpha 对象顶层有 `tags: []` 数组字段，`PATCH /alphas/{id}`（`Allow: GET, PUT, PATCH, HEAD, OPTIONS`）可写。

```python
brain.request("PATCH", f"/alphas/{aid}", json={"tags": ["POWER_POOL"]})
```

`PATCH` 的字段白名单实测（2026-10-31）：`tags` / `name` / `color` / `category` 接受 200；
`description` / `notes` / `idea` / `rationale` 全部返回 400 `{"description":["Unexpected property."]}`。

**② tag 取值**：本账户 664 个 alpha 的 tag 分布实测为
`{'POWER_POOL': 2, '9B3qVP4': 1, 'Power Pool Alpha': 2, '基本与技术混合': 3}`。
`POWER_POOL`（全大写下划线）是系统枚举值，`9B3qVP4` 是 theme id，两者可并存；
`Power Pool Alpha` 与 `基本与技术混合` 形态上都是用户自定义标签，**不要用它当 PP 触发标记**。

**③ 带 tag / 不带 tag 的提交差异**（同一账户、同为 FULL 模式的对照）：

| | 无 tag（`vR1zPEXG`，S=-1.45） | 带 `POWER_POOL` tag（`YP1k0EJo`，S=1.44） |
|---|---|---|
| submit 响应 | 403 | 403（首次曾返回 201 但未落地） |
| checks 数量 | 18 | 18 |
| `POWER_POOL_CORRELATION` | **不存在** | **PENDING** |
| `POWER_POOL_DESCRIPTION_FORMAT` | **不存在** | **WARNING** |
| `LOW_SHARPE` limit | 1.58 | **1.58（未降到 1.0）** |

**结论（2026-10-31 下午修订）**：tag + description 都只是**必要条件**，两者齐备仍不足以切到 PP 通道——
见下面 ④′ 的对照实验。真正决定 PP 资格的是**活跃 theme 的作用域**（region/delay），见 §5.1.5。

**④ ~~description 的入口：API 无接口，只能走网页端~~ → 已推翻（2026-10-31 下午实测）**

**description 可以用 PATCH 写，只是不在顶层**：它嵌在 `regular` 对象之下。

```python
brain.request("PATCH", f"/alphas/{aid}", json={"regular": {"description": "Idea: ... Rationale for data: ... Rationale for operators: ..."}})
# -> 200，且重读 alpha 后 regular.description 长度持久化（实测 1544 / 1694 字符均成功）
```

- 顶层 `{"description": ...}` 确实报 400 `Unexpected property`（旧结论只对了一半）；
- 写入后 `POWER_POOL_DESCRIPTION_LENGTH` / `POWER_POOL_DESCRIPTION_FORMAT` 两个 WARNING 消失；
- **但 `LOW_SHARPE` 的 limit 依旧是 1.58**，`POWER_POOL_CORRELATION` 依旧 `PENDING`。

**④′ tag + description 齐备后的对照实验（决定性，两个区域各一次）**

| 区域 | alpha | tags | description | `LOW_SHARPE` limit | 403 body |
|---|---|---|---|---|---|
| USA | `unsystematic_risk_last_360_days` 候选 | `POWER_POOL` | 434 字符 | **1.58（未降）** | 另被 model51 的 `LOW_COVERAGE`/`CONCENTRATED_WEIGHT` 双杀 |
| GLB | `leAz1nP7`（EBITDA/EV，S=1.17） | `POWER_POOL` | 1694 字符 | **1.58（未降）** | `PROD_CORRELATION=0.7785` 等常规项 |
| GLB | `bl6PgQNN`（反转，S=1.88） | `POWER_POOL` | 1544 字符 | **1.58（未降）** | `PROD_CORRELATION=0.9673` 等常规项 |

⇒ **tags + description 不是 PP 提交的触发器。** 平台仍按 REGULAR 门槛（Sharpe 1.58 / Fitness 1.0 / ProdCorr 0.7）判定。

**⑤ QUICK 模式无法提交**：`POST /alphas/{id}/submit` 对 `settings.simulationMode == "QUICK"` 的 alpha
直接返回 400 `{"detail":"Cannot submit QUICK mode alphas"}`。而 QUICK 仿真的 `is.checks` 只有 7 项
（缺 SELF/PROD/POWER_POOL 相关项），**不能用 QUICK 结果预判能否提交**——必须 FULL 重跑。

**⑥ tag 不可逆**：官方原文 "Once you tag an Alpha as power pool, it stays in the self-correlation pool
even if you untag it later." —— 打 tag 是单向门。**只在确定投 PP 的候选上打，绝不在试验品上打。**

**⑦ PP 通道只放宽 Sharpe，不放宽其余三项——这是最容易漏的杀手**

2026-10-31 实测（`3qo6Rp9X` → FULL 重跑得 `ZYQlv7Yd`）：Sharpe **1.6 已过常规 1.58 线**，
但提交仍 403，且 `SELF_CORRELATION` 停在 PENDING（说明根本没走到相关性计算那一步）。
拦路的是三项与 PP 无关的检查：

| check | value | limit | 判定 |
|---|---|---|---|
| LOW_SHARPE | 1.6 | 1.58 | **PASS** |
| LOW_FITNESS | 0.65 | 1.0 | FAIL |
| CONCENTRATED_WEIGHT | 0.1538 | 0.1 | FAIL |
| LOW_SUB_UNIVERSE_SHARPE | 0.23 | 0.69 | FAIL |

⇒ **PP 的 Sharpe ≥1.0 只是放宽了 `LOW_SHARPE` 一项**，`LOW_FITNESS` 仍按 1.0、
`CONCENTRATED_WEIGHT` 仍按 0.1、`LOW_SUB_UNIVERSE_SHARPE` 仍按
`0.75·√(size_ratio)·Sharpe` 判。官方 PP 条件里写的 "must pass turnover tests / sub-universe test /
robust-universe test" 就是这个意思。**判断 PP 可行性时不能只算 Sharpe 和字段数。**

**根因诊断（已由 ⑩ 的实测验伪，见下）**：初判把三项 FAIL 都归因于 `decay=0` 导致的高换手
（TO 36.56%），并主张「decay 0→10 是第一修复动作」。**该因果链对 `CONCENTRATED_WEIGHT` 是错的、
对其余两项也只是部分成立**——decay=10 的实测结果见 ⑩。真正的结论是：这条 alpha 的失败是
**边际过薄（margin 3.27bp）+ 小票失效**的结构性问题，调 decay 无法修复。

**⑧ QUICK 与 FULL 的指标关系（同表达式实测）**：`3qo6Rp9X`(QUICK) 与 `ZYQlv7Yd`(FULL)
的 IS 指标**逐项完全相同**（S=1.6 / F=0.65 / TO=36.56% / Ret=5.97% / DD=6.83%），差别只在 checks——
QUICK 只有 7 项、缺 SELF/PROD/POWER_POOL_CORRELATION 等 8 项。
⇒ **QUICK 可以用来快速预筛 Sharpe 与 Fitness，但不能用来判断可否提交**；定稿候选仍需 FULL 复核。

> ⚠️ **「QUICK 指标 = FULL 指标」只在个别样本成立（2026-11-04 反证，GBR/TOP700 13 组对照）**：
> 同表达式只改 `simulationMode`，FULL 的 Sharpe 比 QUICK 系统性低 **0.43–0.51**
> （例：`rank(-ts_rank(短+中+长,126))` d5：QUICK 1.94 → FULL 1.43）。
> 逐年拆开看，差异集中在 2014/2020/2023 这些高波动年 ⇒ QUICK 的抽样在这些年份偏乐观。
> **判据**：QUICK 只能看方向和相对排序（Δ≈−0.45 可当经验偏移量）；**任何要交付 / 要提交的候选必须 FULL 重跑**，
> 不要把 QUICK 的 Sharpe 直接当达标结论。

**⑨ 工具**：`scripts/pp_precheck.py`（零仿真消耗）对 alpha_id 或裸表达式做 PP 资格体检：

```bash
python scripts/pp_precheck.py <alpha_id> [alpha_id ...]      # 查线上 alpha
python scripts/pp_precheck.py --expr "rank((a-b)/((a+b)/2))" # 只算字段/算子/形状
```

它用本地 4367 字段快照做标识符归类（在字段表里→字段，否则→算子），因此能准确区分
`subindustry` 这类分组字段（不计入）与真正的数据字段；算术运算符单独计数，`ts_backfill` /
`group_backfill` 按官方规则豁免。同时报告 `simulationMode`（QUICK 直接标 FAIL）、
`POWER_POOL` tag 有无、`POWER_POOL_DESCRIPTION_FORMAT` 状态，以及是否构成 `(A−B)/mean` 形状。

**⑩ decay 调参实测验伪：内部已含平滑时，加大 decay 会吃掉信号（2026-10-31）**

对 `3qo6Rp9X`/`ZYQlv7Yd` 做单变量对照，**唯一改动是 `decay: 0 → 10`**（其余 settings 逐项沿用：
USA / TOP3000 / delay 1 / SUBINDUSTRY / truncation 0.08 / FULL）。变体 id `WjOXrGRx`，消耗 1 次仿真。

| 指标 | decay=0 (`ZYQlv7Yd`) | decay=10 (`WjOXrGRx`) | 变化 |
|---|---:|---:|---|
| Sharpe | **1.60** | **1.31** | −18% ❌ |
| Fitness | 0.65 | 0.68 | +5% |
| Turnover | 36.56% | **18.93%** | −48% ✅ |
| Returns | 5.97% | 5.16% | −14% |
| Margin | 3.27 bp | 5.45 bp | +67% |
| **LOW_2Y_SHARPE** | **1.86 PASS** | **1.50 FAIL** | 由过变挂 ❌ |
| **LOW_SUB_UNIVERSE_SHARPE** | 0.23 / 0.69 FAIL | 0.15 / 0.57 FAIL | 更差 ❌ |
| **CONCENTRATED_WEIGHT** | 0.153846 FAIL | **0.153846 FAIL** | **六位小数完全不变** |
| LOW_SHARPE | 1.60 PASS | 1.31 FAIL | 由过变挂 ❌ |

三条可复用结论：

1. **换手确实腰斩，但这是以牺牲信号为代价的**。该表达式内部已有 `ts_decay_linear(...,5)`，
   再叠加 `decay=10` 等于二次平滑，把 5 日快信号的主要 alpha 抹平——Sharpe −18%、
   近期（2Y）Sharpe 从 1.86 掉到 1.50。**「decay 是快信号的万能修复」不成立**：
   只有当表达式本身**不含**时间平滑算子时，decay 才是纯降噪手段；已含
   `ts_decay_linear` / `ts_mean` / `ts_rank` 时，decay 与内部窗口会叠加，须把两者当同一个
   平滑预算来分配，而不是各调各的。
2. **`CONCENTRATED_WEIGHT = 0.153846` 与 decay 无关**——两次运行逐位相同（0.153846 = 2/13）。
   该值来自表达式自身的截面权重分布（IV 有效票数在某些交易日塌缩），**不是换手造成的**。
   初判的「换手快→权重来不及分散」被证伪。修复只能从字段覆盖度、`truncation`、`neutralization`
   下手，调 decay 无效。
3. **Fitness 几乎不动（0.65→0.68）是必然的**：Fitness ≈ Sharpe×√(|ret|/max(TO,0.125))，
   decay=10 让 ret/TO 比值从 0.163 升到 0.273（好转），但 Sharpe 同时掉了 18%，
   两者互相抵消。**要让 Fitness 从 0.65 到 1.0，在 Sharpe≈1.6 时需要 ret/TO ≈ 0.39，
   即边际要翻 2.4 倍——这不可能靠调参达成，必须换更强的信号源。**

⇒ **判据**：`margin` 低于 ~5bp 的候选，不要指望靠 decay / truncation / neutralization 调参
过 Fitness 1.0 线，直接放弃或换信号。该 alpha 的 margin 在最优 decay 下也只到 5.45bp，
属于「信号真实但太薄」，不是参数没调好。

#### 5.1.5 PP 的真正开关是「活跃 theme 的作用域」——本账户为 GLB/D1

**一、`MATCHES_THEMES` 是判读 theme 状态的唯一窗口**（API 无 themes 接口：`/themes`、
`/themes/{id}`、`/competitions/{id}` 全 404，`/competitions` 只返回 7 个已结束赛事）。

alpha 的 `is.checks[]` 里每个 theme 单独一条 `MATCHES_THEMES`，`result` 语义为：

| result | 含义 |
|---|---|
| **PASS** | 主题**已生效**且该 alpha 命中（会带 `multiplier`） |
| **WARNING** | 主题**已生效**但未命中（例如换手不在 15–30% 区间） |
| **PENDING** | **主题尚未评估/尚未生效**，命中与否未知 |

本账户看到的三条：
`AyomWlD` GLB/D1 turnover 15...30%（multiplier 2.5）、`JypwKv4` GLB/D1/FUNDAMENTAL Pyramid（1.4）、
`9B3qVP4` **GLB/D1 Power Pool Nov\`26（1.0）**。

**二、关键判据：PP 主题即使已打 tag + 已写 description 仍恒定 `PENDING`**
（USA 与 GLB 各有样本验证）。结合 403 仍按 1.58 判定，推断 **PP 主题在 2026-10-31 尚未生效**
（名称含 `Nov\`26`，很可能 11 月 1 日开池）。⇒ **别再在「如何触发 PP」上做实验，先看 theme 是否 PASS。**

**三、PP 候选必须跑在主题指定的 region/delay 上 —— 本主题是 GLB/D1**
USA/D1 的 alpha 永远进不了这个池（它的 turnover/pyramid 主题只会显示 WARNING）。这是过去
10 条 USA 候选全部白跑的根因。

**四、GLB 区域的数据可用性与 USA 完全不同（踩坑重点）**
- `analyst4` 在 GLB **不存在** ⇒ **所有 `anl4_*` 字段在 GLB 报 `unknown variable`**。
- `fundamental6` 在 GLB 只有 197 字段，裸名 `operating_income` / `debt` / `equity` 全部不可用。
- **GLB 实测可用字段**：
  `pv1`：`returns` `close` `open` `high` `low` `vwap` `volume` `adv20` `cap` `sharesout`（cov 1.0）；
  `fundamental17`：`fnd17_ebitda2ev`(0.78) `fnd17_fcf1a`(0.78) `fnd17_atotd2cap`(0.75) `fnd17_ev_cur`(0.79)；
  `fundamental23`：`fnd23_roe`(0.96) `fnd23_net_debt`(0.89) `fnd23_capex`(0.94) `fnd23_ofc`(0.96)；
  `analyst14`：`anl14_*`（cov 0.5）；`analyst69`：`anl69_*`（多为 VECTOR）。
- 正确查法：`GET /data-fields?region=GLB&delay=1&universe=TOP3000&dataset.id=fnd23&limit=20&order=-alphaCount`。
  **`search=` 是模糊匹配，会返回仅含子串的无关字段，不能用来证明某字段存在。**

**五、GLB 额外硬门槛：三个子地理 Sharpe 各自 ≥ 1**
检查项 `LOW_GLB_AMER_SHARPE` / `LOW_GLB_APAC_SHARPE` / `LOW_GLB_EMEA_SHARPE`，limit 均为 1。
**EMEA 是共同瓶颈**，15 个 GLB 候选实测无一达到 1：

| 信号族 | 表达式 | 总体 Sh | AMER | APAC | EMEA |
|---|---|---|---|---|---|
| 反转 d=0 | `group_rank(-ts_rank(returns,126),subindustry)` | 1.42 | 0.52 | 1.05 | **0.73** |
| 反转 d=4 | 同上 +decay4 | 1.99 | 0.95 | 1.83 | 0.52 |
| 反转 d=10 | 同上 +decay10 | 1.88 | 1.00 | 1.97 | 0.25 |
| 反转 d=20 | 同上 +decay20 | 1.67 | 1.04 | 1.70 | 0.14 |
| EBITDA/EV | `group_rank(ts_rank(fnd17_ebitda2ev,126),subindustry)` | 1.17 | 0.67 | 1.07 | -0.27 |
| ROE | `group_rank(ts_rank(fnd23_roe,126),subindustry)` | 0.47 | 0.90 | 0.30 | -0.53 |
| FCF/资产 | `group_rank(ts_rank(fnd17_fcf1a,126),subindustry)` | 0.31 | 0.06 | 0.49 | -0.18 |

- **`decay` 对 EMEA 单调有害**（0.73→0.52→0.25→0.14），同时轻微抬高 AMER。
  用 decay 救换手会把 EMEA 打死 —— 这是 GLB 上最坑的权衡。
- **GLB 的 12M 动量是反的**：`group_rank(ts_rank(returns,252))` Sharpe **-1.45**（APAC -1.07、EMEA -0.77），
  GLB 大市值池里做的是反转。

**六、`PROD_CORRELATION` 只在提交时可见，且已排除两条最自然的路**
`is.checks[]` 恒 `PENDING`，真实值只出现在 403 body（即使 Sharpe 已达标也会一并列出，可白嫖诊断）：
**EBITDA/EV = 0.7785**、**短周期反转 = 0.9673**。PP 要求 <0.5，两者都不可用。
⇒ 这两类教科书因子在 BRAIN 全局池已高度拥挤，不能再当 PP 主力腿。

> 代码里用 `BrainSession.thresholds(delay)` 取阈值，它按账号权限自动在
> `CONSULTANT_THRESHOLDS` / `STANDARD_THRESHOLDS` 之间切换。

**七、GLB 走不通时的正解：迁移到单区域 EUR（2026-11 实测打通）**

GLB 的三子区硬门槛无法用参数调优绕开（EMEA 结构性 ≤0.77）。**单区域没有子区门槛**，
把同一信号迁到 EUR 即可通过。实测 47 次 FULL 仿真后得出 4 条可复用规律：

1. **冠军公式**（EUR/TOP2500/delay1/decay5/SUBINDUSTRY/trunc0.08，S=1.85 F=1.27 TO=17.3%，GATE_OK=True）：
   ```
   group_neutralize(vector_neut(
       rank(ts_arg_min(ts_backfill(star_val_sector_rank,60),60)),
       rank(ts_mean(ts_delta(ts_backfill(mdl26_market_cap_u,2),1),10))
   ), subindustry)
   ```
   `star_val_sector_rank` 属 `model38`（行业内估值排名 1-100）。GLB 上该式 S=1.85/F=0.99，
   迁 EUR 后同样成立；**但迁 AMR(S 0.68)/ASI(JPN 0.47) 均失败 → 该信号是 EUR 专属**。
2. **`vector_neut` 的市值 delta 腿既是 alpha 来源也是换手源头**：删掉它 S 1.85→0.90 直接失效；
   保留但加 `ts_mean(...,10)` 平滑 → TO 26.25%→15.7%、F 0.78→0.98。**只钝化对冲腿、不拖慢主信号**，
   这是唯一能同时保住 Sharpe 和降 TO 的手段。
3. **`ts_arg_min` 窗口 120→60 是决定性一击**：S 1.51→1.85、F 0.98→1.27。邻域 a45/a75 因子宇宙
   检查(0.91/0.95、0.85/0.86)失败，说明 a60 是真实最优点而非参数巧合。
4. **两条看似合理但实测无效的降 TO 手段**（勿再试）：
   - **`hump(alpha, 0.01)` 会彻底杀死 rank 化信号**（S 1.64→0.08，TO 压到 0.77%）——
     rank 归一化后数值太小，hump 门槛吞掉几乎全部调仓。hump 只适用于未归一化的原始信号。
   - **提高 decay 降 TO 会同步杀 Sharpe**（d5→d10：TO 26.3%→15.2% 但 S 1.64→1.31），
     与 GLB 上"decay 伤 EMEA"是同一现象的两种表现：该信号衰减快。
   - 缩小宇宙同样无效：EUR/TOP2500 S=1.64，TOP1200→0.66，TOP800→0.59。

**八、区域代码集合与"冷门 ≠ 有效"**

- **`/regions` 端点不存在（404）**，`/simulations/settings` 也 404。取合法区域只能从字段元数据
  `GET /data-fields/{id}` 的 `data[]` 条目里收集 `region` 字段，实测全集仅：
  `USA EUR ASI CHN KOR HKG GLB AMR IND GBR DEU ALL`。**没有 "ARC"** —— 社区文章标题里的
  "ARC/GLB" 中 ARC 不是合法 region（最接近的是 AMR），照抄会 400。
- **冷门度必须用 alphaCount 实测，"低 alphaCount" 不等于有信号**：
  `star_val_sector_rank` 在 AMR/TOP600 仅 256 个 alpha、EUR/TOP800 仅 239 个（极冷门），
  但实测 Sharpe 只有 0.68 / 0.59；真正可用的是 EUR/TOP2500（该字段已有 19,800 个 alpha，**很拥挤**）。
  ⇒ 冷门字段要配大宇宙才活；拥挤度风险留给 `PROD_CORRELATION` 用公式形态去区分，不能靠缩宇宙解决。

**九、多仿真的"可变参数"边界（省额度的关键）**

`MULTI_SIM_INVARIANT` 只有 5 项：`type / instrumentType / region / delay / language`。
**`universe` / `neutralization` / `decay` / `truncation` 在同一批内可以不同** —— 所以一次多仿真
就能扫完"同区域 × 多宇宙 × 多 decay"的参数网格；但**跨 region 不能同批**（报
`多仿真 region 不一致: AMR != EUR`），必须按 region 分组后再各自 `run_many`。

**十、本地 `gate_report` 通过 ≠ 能提交（2026-11 实测，代价是一次提交额度）**

同一个 check 在仿真后的 `is.checks` 里可能是 `WARNING`，但**提交时会被重新裁定为 `FAIL`**。
实测 `JjeGme5m`（EUR，S=1.80 F=1.26 TO=16.0%）：

| 检查项 | 本地 `is.checks` | 提交 403 判定书 |
|---|---|---|
| `IS_LADDER_SHARPE` | WARNING 0.88 / 1.58 | **FAIL 0.88 / 1.58** |
| `PROD_CORRELATION` | PENDING | **FAIL 0.8314 / 0.7** |
| `SELF_CORRELATION` | PENDING | PASS（无值） |
| `REGULAR_SUBMISSION` | PENDING | PASS 0 / 4 |

⇒ **`gate_report` 返回 True 只是必要条件，不是充分条件。** 提交前必须自己按最严口径预判：
`IS_LADDER_SHARPE` 低于 limit 一律当作 FAIL（别信 WARNING），`PROD_CORRELATION` 只要信号族
是拥挤的估值类（如 STAR 估值排名，EUR 已有 19,800 个 alpha 在用）就默认会 >0.7。
再补两条实测参考值：**EUR 式 vector_neut(估值, 市值delta) 的 prod corr = 0.8314**；
EBITDA/EV = 0.7785；短周期反转 = 0.9673。这三族在全局池都已饱和。

> **代码已按这条教训改过（2026-11-03）**：`gate_report(strict=True)` 现为默认，
> `STRICT_BLOCKING_CHECKS`（`IS_LADDER_SHARPE`/`LOW_2Y_SHARPE`）在 `WARNING` 且
> `value < limit` 时直接判阻断；`preflight.py` 在其之上再加拥挤度先验，一条命令出 GO/NO-GO。
> 要复盘旧口径请显式传 `strict=False`。

**十一、提交被拒后如何拿到判定书（别用长轮询）**

`POST /alphas/{id}/submit` 在提交计算期间返回 **`200` + `Retry-After: 1.0` + 空 body + 无 Location**，
此时 alpha 仍是 `UNSUBMITTED`、`dateSubmitted` 仍是 `None`。正确做法是**按 Retry-After 反复 POST 同一个
submit 端点**，直到拿到 `403`（判定书，body 里是完整 checks）或 `201`（接受）。
实测约 **38 次 / 90 秒**才落地判定结果 —— 任何基于 `GET /alphas/{id}` 的固定间隔长轮询
（旧签名 `submit_verified(polls=20, interval=10)`，200 秒**不够**）都会误判成"201 吞提交"。
注意 `GET /alphas/{id}/submit` 会一直返回同样的 200+Retry-After，读不到结果；
`POST /alphas/{id}/check` 是 405。

> **代码已重写（2026-11-03，2026-11-04 补中途状态检查）**：
> `submit_verified(brain, alpha_id, max_posts=100, max_wait=300, status_check_every=5)`
> 是「反复 POST + 按 Retry-After 退避」，命中 403 立刻解析判定书，不再 GET 轮询；
> 同时每 5 次 POST 查一次 alpha 状态，成功转 `ACTIVE` 就提前收工（见 §7.7.2 坑五）。
> 判定书解析用 `submit_verdict_checks()`，可区分「相关性 FAIL」与「真的配额耗尽」。

### 5.2 IS 检查清单（真实 check 名称，2026-09 顾问面板实测）

| 检查项 | 阈值 | 失败原因 | 修复方法 |
|--------|------|----------|----------|
| LOW_SHARPE | 见 5.1.1 | 信号弱 | 换字段/窗口/加 group_rank |
| LOW_FITNESS | 见 5.1.1 | 换手过高 | 增大 decay、混合稳定信号 |
| LOW_TURNOVER | ≥ 1% | 信号太稳定 | 缩短窗口、换更活跃字段 |
| HIGH_TURNOVER | ≤ 70% | 换手爆炸 | 增大 decay、trade_when、混合 |
| CONCENTRATED_WEIGHT | 单股 < 10% 且分散 | 权重集中 | 用 rank()、降低 truncation、ts_backfill |
| LOW_SUB_UNIVERSE_SHARPE | TOPXXX：`subU_Sharpe ≥ 0.75·√(size_ratio)·Sharpe` | 小票依赖 | 用基本面、SUBINDUSTRY、避免市值倾斜 |
| **IS_LADDER_SHARPE** | 分年阶梯（D1 FAIL 1.59；见 5.2.1） | 近年 Sharpe 衰减 | 提高近年表现；TO<30% 时 PASS 阈值×0.85。⚠️ 仿真后可能只标 `WARNING`，**提交时按 FAIL 判**，看数值不看标签（§9.0） |
| **LOW_2Y_SHARPE** | 近 2 年 Sharpe ≥ 1.58（D1） | 近年失效 | 同上 |
| **SELF_CORRELATION** | 0.7（信号级） | 与已提交 alpha 太像 | 换信号簇/换数据源；不要只调参数 |
| **PROD_CORRELATION** | 0.7（对 PROD 池） | 与生产池太像 | 顾问独有，**本地护栏完全无法预测**（见下） |
| **POWER_POOL_CORRELATION** | 0.5 | Power Pool 通道内相关性 | 见 §5.1.2；⚠️ 实测在 ACTIVE 上恒 `PENDING`，平台不回算，只能按复杂度约束自行预筛 |
| DATA_DIVERSITY | 信息性/受限 | 数据源单一 | 引入新 dataset |
| OLD_SIMULATION | — | 仿真过旧 | **重新模拟**后再提交。⚠️ 它同时是**掉线预警**：2026-10-30 实测 9 条 OLD_SIMULATION=FAIL 的存货全部重跑，Sharpe 平均 −0.42、9/9 全灭。看到它就别指望原指标，重跑前先按「大概率要重做」来规划 |
| CLUSTER_TEST | Sharpe ≥ 1.58（KOR/JPS/TWN/HKG/IND/GBR/DEU ≥ 1） | 仅分类，不阻断 | 无影响（`ERROR` 也不阻断） |
| MATCHES_PYRAMID / MATCHES_THEMES | multiplier | 仅加分项 | 无影响 |
| OSMOSIS_ALLOCATION | — | 仅 WARNING | 无影响 |

**PROD_CORRELATION 的不可预测性（2026-10-30 实测，重要）**

本地护栏只能拿自己的 ACTIVE 池当日收益算相关，它近似的是 `SELF_CORRELATION`，**对 `PROD_CORRELATION` 毫无预测力**：

- 护栏预测 `E560gqE1` 最大相关 **0.509**（对 `YPvlEl0l`），实际 `SELF_CORRELATION = 0.6226`（PASS）、`PROD_CORRELATION = 0.8045`（**FAIL**）。护栏低估约 0.11，且完全没覆盖生产池。
- `is.prodCorrelation` 在 22 条 ACTIVE 上**全部为 0.0**，平台不回算；`POWER_POOL_CORRELATION` 同样恒 `PENDING`。所以「按信号族统计 prod 拥挤度」这条路做不出来，别再试。

推论：
1. **护栏只能用来排除，不能用来放行**。护栏 ≥ 0.45 就当高危（0.509 → 实际 0.6226），别因为「护栏说 0.51 没问题」就放心提交。
2. **真正的判定只有提交那一刻才产生**，且只能从 403 响应体读（见 §7.7.2 坑二）。所以每条候选的边际成本不只是仿真额度，还有一次提交尝试。
3. 指标全 PASS ≠ 能提交。`E560gqE1`（S=2.10 / F=1.43 / 全 IS check PASS，本地 gate PASS）照样被 `PROD_CORRELATION` 一票否决。

#### 5.2.1 IS Sharpe Ladder（D1）

先看全历史 Sharpe 是否 ≥ FAIL 阈值；再从最近 2 年起逐年扩容比较：

| 年数 | D1 FAIL | D1 PASS | D0 FAIL | D0 PASS |
|------|---------|---------|---------|---------|
| 全历史 | 1.59 | — | 2.69 | — |
| 2–5 年 | 1.59 | 2.38 | 2.69 | 3.96 |
| 6 年 | 1.59 | 2.22 | 2.69 | 3.64 |
| 7 年 | 1.59 | 2.06 | 2.69 | 3.33 |
| 8 年 | 1.59 | 1.90 | 2.69 | 3.17 |
| 9 年 | 1.59 | 1.74 | 2.69 | 2.85 |
| 10 年 | 1.59 | 1.59 | 2.69 | 2.69 |

> **TO < 30% 时 PASS 阈值 × 0.85**（FAIL 阈值不打折）——这是低换手因子的隐性红利。

### 5.3 失败统计

| 失败原因 | 占比 | 结论 |
|----------|------|------|
| LOW_SHARPE | 90.7% | 信号质量是最大瓶颈 |
| LOW_FITNESS | 66.2% | 通常是 HIGH_TURNOVER 的软性版本 |
| LOW_SUB_UNIVERSE_SHARPE | 51.0% | 避免小票/流动性倾斜 |

**按数据类型通过率**：基本面 40% > 混合 12.7% > 纯技术 5.3% > 其他 0%

---
