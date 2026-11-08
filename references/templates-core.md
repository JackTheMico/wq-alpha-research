# 因子模板库（SKILL.md §4 迁出）

> 由 `SKILL.md` §4 迁出，**节号保持不变**，文中「第 N 节」等交叉引用仍指向原编号。
> 回主页：[`SKILL.md`](../SKILL.md)。结论与状态查 [`ledger.md`](ledger.md)。

## 4. 因子模板库

### 4.1 高胜率模板

> **社区模板一律不贴进 SKILL.md。** 它们体积是 O(N) 增长的，用检索：
> `python scripts/kb.py search "regression_neut"` / `kb.py templates --dataset fundamental6` /
> `kb.py pull "alpha template" -n 10`（论坛抓取入库）。验证过或否都记回 `references/ledger.md`。

#### 4.1.1 数据集一致性硬门槛（套模板前强制，先于一切构造）

**规则**：用户给定字段后，所选模板的**主信号字段**必须与用户字段属于**同一 dataset**（以本地字段快照或 `GET /data-fields/{id}` 为准）。不一致 → 判定**混信号** → **立即停止执行**（不模拟、不提交），向用户报告冲突字段清单，等待用户换字段或换模板。**不允许**以"权重调低""只当过滤项"等理由放行。

判定要点：

1. **主信号字段 vs 基准字段**：门槛只约束主信号字段（承载 alpha 逻辑的字段）。仅作分母/分组/市值分桶的基准字段（如 `close`、`equity`、`cap`）不单独触发混信号；但只要模板主信号字段与用户字段不同源，就是混信号，停止。
2. **本地快照查不到的字段**（如 mdl77 系列）：先用 `GET /data-fields/{id}` 精确查询 dataset 再判定（search 端点对短词会返回 400，见第 12 节 2026-08-16）；API 也查不到 → 字段本身无效，停止。
3. **模板 D/E 是跨数据集混合模板**，与任何用户给定的单一字段都无法满足同源要求，**禁止**用于套用用户字段；仅当用户明确要求构造混合因子时才可参考其结构。

模板字段 dataset 实测对照（2026-09-01，本地快照）：

| 字段 | dataset | 常见角色 |
|------|---------|----------|
| operating_income / sales / assets / cashflow_op | fundamental6 | 信号 |
| equity | fundamental6 | 信号 / 规模基准 |
| est_eps / free_cash_flow_reported_value | analyst4 | 信号 |
| close / open / cap | pv1 | 价格 / 市值基准 |

校验代码（套模板前必跑）：

```python
import json
from pathlib import Path

API_BASE = "https://api.worldquantbrain.com"
# 按实际部署位置调整；skill 目录内为相对 references/ 路径
FIELDS_JSON = Path("/path/to/wq-alpha-research/references/fields_usa_top3000_delay1.json")

def load_field_datasets():
    data = json.loads(FIELDS_JSON.read_text(encoding="utf-8"))
    return {f["id"]: (f.get("dataset") or {}).get("id") for f in data}

def dataset_of(fid, known, session=None):
    d = known.get(fid)
    if d is None and session is not None:   # 本地快照没有 → API 精确查询
        r = session.get(f"{API_BASE}/data-fields/{fid}")
        if r.status_code == 200:
            d = (r.json().get("dataset") or {}).get("id")
    return d

def check_dataset_gate(user_field, template_signal_fields, session=None):
    """模板主信号字段与用户字段必须同一 dataset。
    返回 (ok, msgs)。ok=False → 混信号，必须停止执行（不模拟、不提交）。"""
    known = load_field_datasets()
    ud = dataset_of(user_field, known, session)
    if ud is None:
        return False, [f"用户字段 {user_field} 的 dataset 未知（本地快照与 API 均无），先按 2.3 验证字段"]
    msgs, bad = [f"用户字段 {user_field} → dataset={ud}"], []
    for f in template_signal_fields:
        d = dataset_of(f, known, session)
        if d != ud:
            bad.append(f"{f}({d})")
    if bad:
        return False, msgs + [f"混信号：模板信号字段 {', '.join(bad)} 与用户字段不同源 → 停止执行"]
    return True, msgs + [f"模板信号字段与用户字段同属 {ud} → 可继续"]

# 用法示例：用户给了 mdl77 字段（Analysts' Factor Model），想套模板 A（fundamental6）→ 拦截
ok, msgs = check_dataset_gate("mdl77_2gdna_actrtn12m", ["operating_income", "equity"])
print("\n".join(msgs))
if not ok:
    raise SystemExit("⚠️ 混信号：不模拟、不提交，请换同 dataset 模板或换字段")
```

判定表：

| 校验结果 | 动作 |
|----------|------|
| 信号字段与用户字段同 dataset | ✅ 继续套模板、进入回测 |
| 任一信号字段 dataset 不同 | ❌ 混信号：停止执行，报告冲突字段，等用户决策 |
| 用户字段 dataset 未知（快照 + API 均无） | ❌ 停止：先验证字段（2.3 / API 精确查询） |

#### 4.1.2 模板库（已标注 dataset）

> ⚠️ **模板中的信号字段均为低拥挤字段示例，未经 Sharpe 验证，仅演示填充方式。**
> 请运行 `recommend_fields.py` 获取最新低拥挤字段池，按同维度替换。

```fastexpr
-- 模板 A：盈利能力趋势（主信号：comprehensive_income_net_tax, deferred_tax_liabilities_total_4）
-- ⚠️ 示例字段 alphaCount 极低，仅演示结构。请从 recommend_fields.py 选择同维度字段。
group_rank(ts_rank(comprehensive_income_net_tax / deferred_tax_liabilities_total_4, 126), subindustry)

-- 模板 B：收益率修正（主信号：option_exercise_avg_price_period；close 为价格基准）
group_rank(ts_rank(option_exercise_avg_price_period / close, 126), industry)

-- 模板 C：偿债能力（主信号：debt_repayments_total_2；equity 为规模基准）
group_rank(ts_rank(debt_repayments_total_2 / equity, 126), industry)

-- 模板 D：多因子混合（高 Fitness）【跨数据集】
-- ⚠️ 混合模板：不得用于套用用户给定的单一字段（必触发 4.1.1 混信号门槛）
0.5 * group_rank(ts_rank(comprehensive_income_net_tax / deferred_tax_liabilities_total_4, 126), subindustry)
+ 0.5 * group_rank(ts_rank(option_exercise_avg_price_period / close, 126), industry)

-- 模板 E：低相关技术+基本面混合【跨数据集】
-- ⚠️ 混合模板：同上，不得用于套用用户字段
0.5 * rank(-(close / open - 1)) + 0.5 * rank(ts_rank(comprehensive_income_net_tax / deferred_tax_liabilities_total_4, 126))

-- 模板 F：资产周转 × 利润率（主信号：comprehensive_income_net_tax, sales, assets）
rank(ts_rank(comprehensive_income_net_tax / sales * sales / assets, 126))

-- 模板 G：事件 × 盈利能力【跨数据集】
-- 腿1（事件）：rank(ts_mean(news_dividend_yield, 5))
-- 腿2（盈利）：group_rank(ts_rank(comprehensive_income_net_tax / deferred_tax_liabilities_total_4, 126), subindustry)
0.5 * rank(ts_mean(news_dividend_yield, 5))
+ 0.5 * group_rank(ts_rank(comprehensive_income_net_tax / deferred_tax_liabilities_total_4, 126), subindustry)
-- decay=10~15, neutralization=SUBINDUSTRY, truncation=0.08
```

**实测基线（2026-10-29，顾问账号 USA TOP3000 D1，各跑 1 次真实仿真）**

| 模板 | alpha_id | Sharpe | Fitness | TO | 过顾问门槛 1.58 / 1.0 |
|---|---|---:|---:|---:|:---:|
| A · ROE 趋势 | npvblvPq | 1.23 | 0.58 | 6.1% | ✗ |
| B · EPS 收益率 | qMLZpJ6K | **1.57** | 1.10 | 11.2% | ✗（差 0.01） |
| C · FCF 收益率 | JjeLJEaW | 1.08 | 0.59 | 4.3% | ✗ |
| D · 多因子混合 | d5WwrmP2 | 1.64 | 1.02 | 6.6% | ✓ |
| E · 反转 + 质量 | omEe0Gdl | **1.81** | **1.24** | 11.3% | ✓ |
| F · 周转 × 利润率 | Xg9EA3Y0 | 1.08 | 0.50 | 6.9% | ✗ |

两条可直接用的推论：① **双腿正交混合（D/E）的达标率显著高于单腿（A/B/C/F 全灭）**，在顾问门槛下混合应作为默认姿势而非进阶技巧；② **接近门槛时（B 差 0.01）先做参数邻域搜索，比新造模板的期望收益高得多**——新造模板首跑达标率 2/6，而 B 只需 decay / neutralization / window 微调。

#### 4.1.3 历史库命中率（2026-10-30 统计，alpha_db.json 127 条，顾问门槛口径）

「过门槛」= Sharpe ≥ 1.58 且 Fitness ≥ 1.0 且 1% ≤ TO ≤ 70%（不含相关性检查）。

| 信号簇 | 尝试 | 过门槛 | 过门槛率 | 已 ACTIVE |
|--------|-----:|------:|-------:|----------:|
| **期权 IV（skew / pcr_oi）** | 16 | 10 | **62.5%** | 5 |
| 分析师 EPS | 11 | 5 | 45.5% | 3 |
| OI 质量（OI/equity、OI/liabilities） | 19 | 8 | 42.1% | 7 |
| 现金流 / EV | 15 | 4 | 26.7% | 5 |
| 其他（一次性探索） | 81 | 2 | 2.5% | 1 |

结构维度：**双腿混合 24 次尝试 / 8 个 ACTIVE（33.3%） vs 单腿 103 次 / 6 个 ACTIVE（5.8%）**，双腿的命中率是单腿的 5.7 倍——与 A–F 首跑「双腿全过、单腿全灭」互相印证。

> 复算命令：`python scripts/template_hitrate.py`（`--stock` 看过线存货，`--dup` 查重复仿真）。纯本地统计，**不联网、不消耗仿真额度**，可随时重跑。

> ⚠️ **时效警告（2026-10-30 反证）**：上表的「过门槛率」是**各 alpha 首次仿真时点**的口径，样本集中在 2025-03～2026-08。它回答的是「哪个骨架当初容易做出达标信号」，**不等于「现在拿去跑还能达标」**。
> 实测反证：把这批里 9 条已过线的存货全部重跑，Sharpe 平均 **−0.42**，9/9 全部掉线（唯一贴线的 `2rpzeGab` 从 2.37/1.88 掉到 1.63/1.00，卡在 `LOW_SUB_UNIVERSE_SHARPE` 0.70 vs 0.71）。**命中率表用于选骨架方向，不要用于估算当下的成功率。**

**结论：内置模板里 E 首跑分数最高（1.81/1.24），但按历史过线率排序，模板 G（期权 IV skew × 基本面质量）才是产出可提交 alpha 概率最高的骨架**——它的 16 次尝试里 10 次直接过线，且三个 50/50 变体（+OI/equity、+FCF/equity）全部过线。

**模板 G 的已占用情况（提交前必查，否则撞 SELF_CORRELATION）**：
- 腿1（IV skew 180d）已在库内出现 12 次，ACTIVE 5 个（ZYE31mzx、XgoQMAq1、58p0232N、E5GO9zOG、bldLbe6R）。
- 质量腿 `operating_income/equity` 与 `free_cash_flow_reported_value/equity` 已被占用；再跑同骨架必须**换质量腿**（`cashflow_op/equity`、`enterprise_value/ebitda`、`operating_income/liabilities`）或**换期权腿口径**（`implied_volatility_mean_skew_90`、`pcr_oi_270`、270/360 期限）。
- `2rpzeGab` 与 `ZYE31mzx` 是**同一表达式**（仅 decay 10 vs 15）→ 重复仿真，勿再跑；用 `SimulationCache` 去重可避免此类浪费。

> ⚠️ **换期权腿的期限/口径都不足以逃出这个簇（2026-10-30 实测 20 次仿真反证）**：把 IV 腿分别换成 90 / 120 / 270 天期限的 call-put skew、`implied_volatility_mean_skew_270/360`、`pcr_oi_270`，与池内纯 IV 腿 alpha `58p0232N` 的日收益相关仍在 **0.70–0.81**，与 `ZYE31mzx` 0.61–0.67，与 `XgoQMAq1` 0.55–0.94。原因是 SELF_CORRELATION 看的是**信号族**，不是字段串——同一个经济含义（期权 skew）换期限只是换个采样窗口。
> **结论：模板 G 在当前池里已经饱和，继续在 IV 簇里换字段是无效工作量。要留在「双腿混合」骨架上，第二腿必须换到池外数据族**（pv1 价量反转 / news / socialmedia / model）。实测 pv1 反转腿 `rank(-(close/open-1))` 在 22 个 ACTIVE 中无人使用，配 `cashflow_op/equity` 后与池内最大相关仅 0.509。

### 4.2 低拥挤字段优先策略

**核心目标**：从源头降低 PROD_CORRELATION 撞墙概率。

#### 4.2.1 字段拥挤度分层

| 层级 | alphaCount | 用法 |
|------|-----------|------|
| 🟢 首选 | 0–100 | 优先填入模板信号槽位 |
| 🟡 回退 | 100–500 | 首选不足时使用 |
| 🔴 饱和 | > 500 | 仅作分母/分组基准，不作主信号 |

#### 4.2.2 三道筛选闸门（`recommend_fields.py` 自动执行）

1. **拥挤度**：`alphaCount ≤ 500`
2. **数据可靠性**：`coverage ≥ 0.7` 且 `type == MATRIX`
3. **经济学可解释性**：AI 必须为每个信号字段写出一句话经济学解释

**粗筛排除**：
- 衍生信号字段：id/description 含 `rank`/`percentile`/`score`/`signal`/`factor`/`zscore`/`normalized`/`standardized`/`decay`/`neutralized`/`adjusted`
- 饱和数据集：`fundamental6`、`analyst4`、`pv1`

**极冷门标记**：`userCount < 100` 且 `alphaCount < 5` 的字段标记为「极高不确定性」，不作首选。

#### 4.2.3 11 个经济学维度

`recommend_fields.py` 按以下维度分组输出，便于按模板槽位语义选字段：

| 维度 | 语义 |
|------|------|
| profitability | 盈利能力 |
| growth | 成长性 |
| valuation | 估值 |
| leverage | 杠杆/偿债 |
| cashflow | 现金流 |
| efficiency | 运营效率 |
| analyst | 分析师预期 |
| volatility | 波动率 |
| sentiment | 情绪/舆情 |
| momentum | 价量动量/反转 |
| event | 特殊事件 |

#### 4.2.4 强制在线模式

`recommend_fields.py` 必须拉取当前区域的 ACTIVE alpha 列表，剔除已用字段。无凭据时报错退出，不降级到离线模式。

#### 4.2.5 仿真前静态检查

`simulate_batch.py` 仿真前自动检查：
- 信号字段 alphaCount > 500 → 拒绝（`--allow-crowded` 豁免）
- 信号字段在 ACTIVE 池中 → 拒绝
- 缺少 `--field-rationale` 或解释 < 10 字 → 拒绝
- 字段不在快照中 → 拒绝（`--allow-unknown-field` 豁免）

#### 4.2.6 快照有效期

字段快照超过 30 天未更新时输出警告。运行 `--refresh` 手动更新。支持多区域按需懒加载。

### 4.3 推荐默认设置

| 因子类型 | Decay | Neutralization | Truncation | nanHandling | 预期 TO |
|----------|-------|----------------|------------|-------------|---------|
| 基本面质量 | 0 | SUBINDUSTRY | 0.08 | ON | 2–8% |
| 分析师预期 | 0–4 | INDUSTRY/SUBINDUSTRY | 0.08 | ON | 9–16% |
| 技术反转 | 10–30 | INDUSTRY | 0.08 | OFF | 15–35% |
| 混合因子 | 4–20 | INDUSTRY/SUBINDUSTRY | 0.08 | ON | 10–20% |
| 情绪 | 4–10 | INDUSTRY | 0.05–0.08 | ON | 8–30% |

### 4.4 少数股东损益族（`fnd6_miisa`）：可用性与已验证结构（2026-11-05）

**可用性（关键：USA 没有这个字段）**

| Region / Universe | coverage | alphaCount |
|---|---:|---:|
| USA / TOP3000 | **不存在** | — |
| EUR / TOP2500 | 0.50 | **8** |
| EUR / TOP400–1200 | 0.50 | 7–176 |
| ASI / MINVOL1M | 0.50 | 148 |
| CHN / TOP2000U | 0.50 | 2 |
| GBR / TOP700 | 0.31 | 少 |
| DEU / TOP500 | 0.44 | 少 |

EUR 的 `fundamental6` 只有约 279 个字段，**且只有 NCI 这一支**——裸名 `fnd6_at` / `fnd6_sale` /
`fnd6_ib` 在 EUR 全部不可用。所以分母必须来自别的 dataset（这正是跨数据集搭配的入口）：

| 字段 | dataset | EUR/TOP2500 cov | 作用 |
|---|---|---:|---|
| `fnd6_miisa` | fundamental6 | 0.50 | 少数股东损益（利润表） |
| `fnd6_ibmiisa` | fundamental6 | 0.50 | 扣少数股东损益前的合并利润 |
| `fnd6_mibt` | fundamental6 | 0.50 | 少数股东权益（资产负债表） |
| `equity_to_equityholders` | fundamental23 | 0.89 | 归属母公司股东权益 |
| `assets_total_2` | fundamental23 | 0.84 | 总资产 |
| `dividends_noncontrolling_interest` | fundamental23 | 0.76 | 支付给少数股东的股息 |
| `current_minority_interest` | fundamental23 | 0.81 | 当期少数股东权益 |

**单腿实测（EUR/TOP2500/d1，decay 0，SUBINDUSTRY，rank 而非 ts_rank）**

| 信号 | Sharpe | TO | 说明 |
|---|---:|---:|---|
| `(ibmiisa−miisa)/equity_to_equityholders`（母公司 ROE） | **0.88** | 2.4% | 本族最强单腿 |
| `(ibmiisa−miisa)/assets_total_2`（母公司 ROA） | 0.82 | 2.1% | 与 ROE 近等价 |
| `miisa/equity_to_equityholders` | 0.71 | 2.0% | 少数股东资本占用（取负号同效） |
| `miisa/ibmiisa`（少数股东分走的利润占比） | 0.67 | 1.9% | 负向盈余质量 |
| `mibt/(mibt+equity_to_equityholders)` | 0.11 | — | 结构复杂度，基本无效 |
| 同一信号套 `group_rank(ts_rank(...))` | **0.25 / −0.29** | — | **ts_rank 会把该族信号打散，别套** |

**已验证可提交结构（4 腿，NCI 族合计 47%）**

```fastexpr
0.27*rank(ts_backfill((fnd6_ibmiisa - fnd6_miisa)/(abs(equity_to_equityholders)+0.01),60))
+ 0.38*group_rank(-ts_rank(returns,252),subindustry)
+ 0.15*group_rank(ts_rank(fnd17_ebitda2ev_a,126),subindustry)
+ 0.20*group_rank(ts_rank(dividends_noncontrolling_interest/(abs(fnd6_mibt)+0.01),252),subindustry)
```

EUR/TOP2500/d1，**decay 6**，SUBINDUSTRY，trunc 0.08 → `RREAx3Na` **ACTIVE**：
S 2.24 / F 1.14 / TO 33.0% / Ret 8.48% / DD 4.89%，IS_LADDER PASS 2.39/2.21、
LOW_SUB_UNIVERSE PASS 1.19/1.16、`is.prodCorrelation = 0.6761`（PASS，贴近 0.7）。

三条复用结论：
1. **miisa 单腿只到 0.88，不能单独交付**；它的价值是正交搭配（配上 252 日反转后混合 Sharpe
   1.57→1.85→2.24）。反转腿 0.28→0.38 是同时抬 Sharpe 和修 `LOW_SUB_UNIVERSE` 的关键一刀。
2. **该混合对 decay 敏感**：d10 → S 1.75 / d6 → S 2.24，且 ladder 由 FAIL 转 PASS。
   与"已含 `ts_rank` 时加大 decay 会二次平滑"一致，别照搬基本面默认 decay=0。
3. **`ts_backfill(...,60)` 是免费提升**：S 1.81→1.88、F 1.17→1.24，因为 miisa 覆盖率只有 0.5。

---
