# WQ 社区 ARC/GLB Alpha 模板合集（顾问社区贴）

> **来源**：WorldQuant BRAIN 社区帖子《10个超级高效好用的ARC/GLB模板，再不刷就没有了》
> **帖子 ID**：43499065604247
> **作者**：顾问社区用户
> **抓取/验证日期**：2026-10-31
> **原始链接**：https://support.worldquantbrain.com/hc/en-us/community/posts/43499065604247
> **语法验证**：全部 12 个模板（10 主贴 + 2 评论补）已用 QUICK 仿真验证通过（HTTP 201）

---

## 使用提示

- 表达式中的 `FIELD` / `FIELD_2` / `T1` / `T2` / `N` / `K` / `W` 为**占位符**，需替换为实际字段和参数
- `mdl26_market_cap_u` / `mdl26_market_cap_l` / `mdl110_*` / `star_*` / `oth176_*` 为**特定数据集字段**，使用前需确认账号有对应权限
- 所有模板已在 USA TOP3000 delay=1 上语法验证通过；**GLB 区域的字段可用性需另行验证**
- 评论区提示：`ts_decay_exp_window`、`jump_decay`、`clamp`、`group_median`、`group_vector_neut`、`ts_median`、`group_count` 等算子可能需要 Gold+ 权限

---

## 模板目录

| ID | 名称 | 复杂度 | 核心算子 | 语法 | 备注 |
|----|------|--------|----------|:----:|------|
| F1a | vector_neut/ts_arg_min 主模板 | ★★★ | vector_neut, ts_arg_min, ts_backfill, ts_decay_exp_window | ✅ | GLB 主流骨架 |
| F1b | ts_rank/ts_arg_max 变体 | ★★★ | 同上 + ts_rank | ✅ | mdl26_market_cap_l 需验证 |
| F1c | F1 简化版 | ★★ | 同 F1a 但无外层 group_neutralize | ✅ | 最小消融骨架，建议先跑 |
| F2 | clamp/jump_decay 截面 | ★★ | clamp, jump_decay, group_vector_neut | ✅ | 算子权限存疑 |
| F3 | 残差回归管道 | ★★★ | ts_regression, group_median, vector_neut | ✅ | group_median 权限存疑 |
| F4 | model110 多因子复合 | ★★ | ts_quantile, ts_rank, ts_arg_max | ✅ | 三连乘建议逐件消融 |
| F5 | STAR 盈余惊喜排序 | ★ | ts_quantile, rank | ✅ | rank(x)*rank(x) 冗余，建议删除一个 |
| F6 | 动量切换 | ★★ | if_else, group_count, is_nan | ✅ | 三元运算符 ? : 语法 OK |
| F7 | ts_median vector_neut | ★★ | ts_median, vector_neut | ✅ | ts_median 权限存疑 |
| F10 | 多步命名赋值 | ★★★ | vec_avg, normalize, ts_decay_exp_window | ✅ | normalize 算子需验证 |
| C1 | tm_16 + tema 双因子 | ★ | ts_zscore, rank | ✅ | 评论区分享，Sharpe 8.37 |
| C2 | 简化版 vector_neut | ★ | vector_neut, rank, ts_arg_min | ✅ | 无 decay_exp，通用 |

---

## 模板详情

### F1a — vector_neut/ts_arg_min 主模板（比较高效）

**说明**：低波动率状态门控（trade_when）+ 市值中性化的滚动极小值信号，GLB 语料中最主流的骨架结构。

```fastexpr
alpha = ts_decay_exp_window(
    vector_neut(
         rank( ts_arg_min( ts_backfill( FIELD, 60 ), 120 ) ),
         rank( ts_delta( ts_backfill( mdl26_market_cap_u, 2 ), 1 ) )
    ),
    5, factor = 0.7 );
group_neutralize(
    trade_when( rank( ts_std_dev( mdl26_market_cap_u, 60 ) ) > 0.3,
                alpha, -1 ),
    subindustry );
```

**参数替换建议**：
- `FIELD` → model26 / analyst15 / ai_funda_synth 字段
- `T1=60`、`T2=120`、`N=2`、`W=60` → 可按字段特性微调
- `factor=0.7` → 建议作为独立变量扫描（不同字段最优衰减差别大）

---

### F1b — ts_rank/ts_arg_max 变体

**说明**：用 ts_rank + ts_arg_max 替换 F1a 的 rank + ts_arg_min，同时市值字段换成 mdl26_market_cap_l，门控变量换成 returns。

```fastexpr
alpha = ts_decay_exp_window(
    vector_neut(
         ts_rank( ts_arg_max( ts_backfill( FIELD, 60 ), 120 ), 60 ),
         rank( ts_delta( ts_backfill( mdl26_market_cap_l, 2 ), 1 ) )
    ),
    5, factor = 0.9 );
group_neutralize( trade_when( rank( ts_std_dev( returns, 66 ) ) > 0.5, alpha, -1 ), industry );
```

---

### F1c — 同骨架，省略外层 group_neutralize

**说明**：最小消融骨架，建议**先用 F1c 验证信号方向**，方向成立后再上完整管道。

```fastexpr
ts_decay_exp_window(
    vector_neut(
        rank( ts_arg_min( ts_backfill( FIELD, 60 ), 120 ) ),
        rank( ts_delta( ts_backfill( FIELD, 2 ), 1 ) )
    ),
    5, factor = 0.6 );
```

---

### F2 — clamp/jump_decay 截面模板

**说明**：跳跃衰减算子 + clamp 限制极值，适合 pv1 动量/成交量字段或短周期 DL 预测信号。

```fastexpr
a = clamp( -jump_decay( FIELD, 120, sensitivity = 0.5, force = 0.1 ),
            lower = -0.5, upper = 0.5 );
group_vector_neut( rank( close ), rank( a ), subindustry );
```

**权限警告**：`jump_decay` / `clamp` / `group_vector_neut` 在部分账号算子清单中不存在。

---

### F3 — 残差回归管道

**说明**：截面中位数残差 → group_rank → 市值向量中性 → 低波动门控 → 行业中性。适合宽基本面数据集。

```fastexpr
df         = FIELD;
group_med  = group_median( df, subindustry );
resid      = ts_regression( df, group_med, 500, lag = 0, rettype = 0 );
resid_gpr  = group_rank( resid, subindustry );
alpha      = vector_neut( resid_gpr,
                  rank( ts_delta( ts_backfill( mdl26_market_cap_u, 2 ), 1 ) ) );
group_neutralize( trade_when( rank( ts_std_dev( returns, 270 ) ) > 0.3,
                  signed_power( alpha, 2 ), -1 ), industry );
```

**评论建议**：`group_median` 若无权限，可替换为 `group_neutralize(x, subindustry)`（近似效果）。

---

### F4 — model110 多因子复合信号

**说明**：三字段乘积（quantile × rank × arg_max^3）+ group_backfill 平滑。适合 model110 / analyst15 复合字段。

```fastexpr
a = ts_quantile( mdl110_score, 5120 )
      * ts_rank( mdl110_analyst_sentiment, 60 )
      * power( ts_arg_max( mdl110_quality, 1200 ), 3 );
group_backfill( a, 90, 90 );
```

**评论建议**：三连乘建议逐件消融——"拆掉就崩"才留，"乘上去 IS 变好"不算理由。

---

### F5 — STAR 盈余惊喜/估值排序器

**说明**：单字段 quantile × rank² + backfill。最简模板。

```fastexpr
a = ts_quantile( star_rev_surprise_prediction_fq1, 252 )
      * rank( star_rev_surprise_prediction_fq1 )
      * rank( star_rev_surprise_prediction_fq1 );
ts_backfill( a, 60 );
```

**评论警告（冗余）**：`rank(x) * rank(x)` 是对 rank 的单调变换，截面排序信息与 `rank(x)` 完全相同——除非下游的中性化/截断对分布形状敏感，否则纯属多余算子。建议删除一个 rank 乘法。

**修正版**：
```fastexpr
ts_quantile( star_rev_surprise_prediction_fq1, 252 )
  * rank( star_rev_surprise_prediction_fq1 );
```

---

### F6 — rank/ts_rank 动量切换

**说明**：动量 > 0.5 时用 1（做多），否则用反转信号。group_count 门控防止 NaN 过多。

```fastexpr
alpha = rank( ts_rank( FIELD, 242 ) );
a = if_else( alpha > 0.5, 1, rank( -ts_delta( close, 2 ) ) );
lastalpha = group_count( is_nan( a ), market ) > 40 ? a : nan;
ts_backfill( lastalpha, 2 );
```

**权限警告**：`group_count` 在部分账号算子清单中不存在。

---

### F7 — ts_median vector_neut（ATOM 风格）

**说明**：用两个不同窗口的 ts_median 做向量中性化（ATOM 风格）。

```fastexpr
group_neutralize(
    vector_neut( ts_median( FIELD, 60 ), ts_median( FIELD, 120 ) ),
    close, COUNTRY );
```

**权限警告**：`ts_median` 在部分账号算子清单中不存在。

---

### F10 — 多步命名赋值构建

**说明**：与 F1a 结构相同，但先 vec_avg + normalize 预处理，且 FIELD 与 pt 分开（两个独立字段）。

```fastexpr
df = vec_avg( FIELD );
normalize( df, useStd = false, limit = 0.0 );
pt = FIELD_2;
alpha = ts_decay_exp_window(
            vector_neut(
                rank( ts_arg_min( ts_backfill( df, 60 ), 122 ) ),
                rank( ts_delta( ts_backfill( pt, 2 ), 1 ) ) ),
            5, factor = 0.6 );
group_neutralize( trade_when( rank( ts_std_dev( pt, 120 ) ) > 0.3, alpha, -1 ), subindustry );
```

---

### C1 — 评论补充：双 ts_zscore 因子

**说明**：评论区用户分享，原始字段 `tm_16_r1_r5_r10_rh_d1_r10_q1` + `tcm_ta50_d1_tema` 实测 Sharpe 8.29 / Fitness 3.4。

```fastexpr
rank( ts_zscore( FIELD_A, 300 ) ) + rank( ts_zscore( FIELD_B, 300 ) )
```

**原帖补充的四信号合版**：
```fastexpr
ts_decay_linear(
    rank( ts_zscore( tm_16_r1_r5_r10_rh_d1_r10_q1, 270 ) )
  + rank( ts_zscore( tcm_ta50_d1_tema, 270 ) )
  + rank( ts_zscore( tm_15_field, 270 ) )
  + rank( ts_zscore( tm_14_field, 270 ) ),
    2 )
```

---

### C2 — 评论补充：简化版 vector_neut（无 decay_exp）

**说明**：去掉 ts_decay_exp_window，直接 vector_neut，适合没有该算子权限的账号。

```fastexpr
vector_neut(
    rank( FIELD ),
    rank( ts_delta( ts_backfill( mdl26_market_cap_u, 2 ), 1 ) )
)
```

---

## 模板 × 数据集搭配建议

| 模板 | 推荐数据集 | 理由 |
|------|-----------|------|
| F1a/F1b/F1c/F10 | model26, analyst15, ai_funda_synth | 覆盖度适中，适合滚动极值信号 |
| F3 | model38, fundamental17, risk87 | 宽基本面数据集，残差回归效果好 |
| F4/F5 | model110, analyst15, STAR 系列 | 复合/惊喜排序类字段 |
| F2 | pv1 (动量/成交量), dl_short_signals, short_cnn_pred | 跳跃衰减适合波动率/成交量类 |
| F1a/F1c (低采用数据集) | global_sl_pred, cyber_risk_ratings, news95 | 先用 F1c 最小骨架快速验证方向 |

---

## 成熟稳健数据集（久经验证）

| Dataset | 名称 | Alpha 数 | 用户数 | 覆盖率 |
|---------|------|---------:|-------:|:------:|
| pv1 | Price Volume Data for Equity | 38,948 | 4,639 | 1.00 |
| model38 | Growth Valuation Model | 8,699 | 1,771 | 0.82 |
| risk70 | Multi-Factor Model | 7,395 | 1,573 | 0.99 |
| model77 | Analysts' Factor Model | 6,921 | 1,041 | 0.78 |
| model26 | Analyst Revisions | 4,179 | 899 | 0.76 |
| analyst15 | Earnings forecasts | 2,575 | 885 | 0.94 |

> **警告**：这类数据集竞争激烈（valueScore≈1），适合练手和验证模板，但差异化空间有限。

---

## 全新上线数据集（2026-03 批次，先发机会）

### Short Interest 类目

| Dataset | 名称 | 字段数 | 覆盖率 | 简介 |
|---------|------|-------:|:------:|------|
| global_sl_pred | Global Securities Lending Prediction | 256 | 0.98 | 1-250 天多周期借贷需求/使用率 ML 预测 |
| dl_shortinterest_alpha | DL Short Interest Alpha | 342 | 0.80 | CNN 图像化分析借贷时序 |
| short_cnn_pred | DL Short Interest Prediction | 232 | 0.87 | CNN 图表模式识别 |
| dl_short_signals | DL Equity Short Signals | 297 | 0.79 | OHLC+IV 图表 CNN，挤压/拥挤空头信号 |
| lending_cnn_alpha | DL Securities Lending Alpha | 78 | 0.95 | 借贷指标图表 CNN |
| shortinterest25 | Execution Risk Dataset | 37 | 0.85 | 全球流动性/交易成本/市场冲击统计 |

### Model / AI / Risk 类目

| Dataset | 名称 | 字段数 | 简介 |
|---------|------|-------:|------|
| ai_funda_synth | AI Synthesized Fundamental | 443 | LLM/集成学习生成的逐日基本面 |
| ai_funda_llm | AI Enhanced Global Fundamentals | 263 | 跨区域迁移学习合成全球基本面 |
| dl_returns_pred | DL Returns Prediction | 1092 | 图表 CNN 融合多因子预测 |
| llm_feature_transfer | LLM Driven Feature Transfer | 502 | LLM 提取特征跨模型迁移 |
| crowding_scores | Multi-Vendor Crowded Position | 14 | 六家供应商聚合的多空拥挤度指标 |
| model266 | Earnings Predictions Data | 25 | 量化模型预测未来 8 个季度 EPS |
| cyber_risk_ratings | Global Cybersecurity Risk | 35 | 公司网络安全风险评分、数据泄露事件 |
| company_network | Global Company Relationship | 1 | 分析师标注的供应商/客户/竞争对手网络 |
| equity_alerts | Intraday Equity Alert Signals | 15 | 30 分钟粒度评级变化/成交量异常/新闻提及 |
| instrument_clusters | Instrument Clustering for Alpha | 81 | 基于收益相关性的 ML 股票聚类 |
| equity_pca_risk | Global Equity PCA Risk Factors | 21 | PCA 多资产风险模型 |
| specific_returns | Reproducible Asset Specific Returns | 1 | 可复现的因子调整后特质收益 |
| crowding_risk | Equity Crowding Risk Model | 23 | 拥挤度调整后特质收益 |
| institutions17 | Buyside Data Feed | 73 | 4 万+公司债借贷分析 |

> **评论警告**：2026-03 批次部分数据集账本只有 217 天 < 500 天，会被 duration 类闸门拦死。覆盖率好看不代表历史够长，先拉逐年统计确认数据从哪年开始。

---

## 2025 年新发布数据集（低使用率）

| 更新时间 | Dataset | 名称 | 字段数 | 类别 |
|----------|---------|------|-------:|------|
| 2025-11 | risk87 | Risk Factor Data | 264 | Risk |
| 2025-11 | news95 | Global News Event Sentiment | 33 | News |
| 2025-11 | news13 | Event Dataset | 21 | News |
| 2025-11 | institutions22 | Global Hedge Fund Ownership | 24 | Institutions |
| 2025-11 | fundamental90 | Governance, Accounting, Management | 68 | Fundamental |
| 2025-10 | analyst90 | Analyst Idea Dataset | 15 | Analyst |
| 2025-10 | pv130 | Identity Group Dataset | 370 | Price Volume |

---

## 小众但高价值数据集（按类别）

| 类别 | Dataset | 名称 | 简介 |
|------|---------|------|------|
| Sentiment | sentiment27 | Website Popularity Rankings | 抗操纵的全球网站流量排名 |
| Macro | macro49 | Index Rebalance Dataset | Russell/MSCI 指数再平衡 |
| Option | option2 | US Equity Option Volatility | 完整美股期权链数据 |
| Insiders | insider_agg_matrix | Smart Insider Transaction | 过滤后的内部人买卖矩阵化聚合 |
| Fundamental | predictive_funda | Predictive Company Financials | 重述后财务数据的前瞻预测模型 |
| Analyst | analyst91 | Global Exposure Dataset | ~2,700 家公司地理营收/成本敞口 |
| Analyst | analyst92 | Patent Innovation Signals | 专利 ML 创新信号 |

---

## 避坑：仅为映射表的数据集

以下数据集名称/类别标签具有误导性，但实际是 RIC↔Bloomberg BBID 身份映射表，**没有真实研究信号**：

other321, other10, news90, model218, shortinterest21, analyst11, analyst16, fundamental88, analyst95, model255

> **判断技巧**：凡描述文本出现 "comprehensive mapping between Reuters Instrument Codes (RICs) and Bloomberg Identifiers (BBIDs)" 字样，一律先核实字段 schema。

---

## 评论区重要经验汇总

### 权限相关
1. `ts_decay_exp_window`、`jump_decay`、`clamp`、`group_median`、`group_vector_neut`、`ts_median`、`group_count` 等算子很多账号（包括顾问）不在算子清单里——**不要只按名称替换，先跑裸字段探针**
2. MATRIX 型字段不能进 `group_rank` / `group_neutralize` 的分组参数位——同型毒批
3. 以下放进 multisim 会毒化整批：`winsorize(x, 4)`、`hump(...)`、`ts_decay_linear(x, 0)`、`bucket(range='...~...')`（波浪号会被拒）

### 模板骨架相关
4. **F1a/F1b 骨架在 GLB 已相当拥挤**——即使信号来自全新数据集，只要骨架同构，prod correlation 照样偏高
5. **建议先在 F1c 简化骨架上验证方向，再刻意换骨架**——ts_arg_min → ts_median、vector_neut → group_vector_neut，制造骨架多样性
6. **rank 开头的模板只适合信号在尾部/极端值的字段**——如果字段原值版有信号、rank 版塌掉，说明信号在幅度里，应该保留幅度写法 + truncation 控集中度

### 数据集体检
7. **零用户数据集 = 零验证**，先查：账本长度（逐年统计）、覆盖率、字段分布（是否高度稀疏）、更新频率
8. **字段覆盖率落差**：FIELD 与市值约束字段覆盖率差 > 10pp 时，优先加 ts_backfill 拉平
9. **映射表识别**：去 Data Explorer 看字段取值分布——若所有标的上恒定或几乎无方差，直接排除

### 模板使用方法论
10. **最小消融四组必跑**：原字段裸跑 → 只加 backfill → 只加中性化 → 完整模板，记录覆盖率/turnover/Sub-universe/PC
11. **trade_when 门控要跟着字段走**——换字段/换 universe 后，被放行的股票数量可能完全变了，空转的门控比没有门控更麻烦
12. **ts_decay_exp_window 的 factor 参数当成独立变量扫描**——不同字段的最优衰减差别很大
13. **F5 中 rank(x)×rank(x) 冗余**——同字段 rank 自乘不带来新截面信息
