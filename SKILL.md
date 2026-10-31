---
name: wq-alpha-research
description: "Use for WorldQuant BRAIN alpha research: designing WQ Alpha expressions, selecting fields/operators, diagnosing simulation and IS check failures, tuning Sharpe/Fitness/Turnover, submitting alphas, and building low-correlation alpha portfolios. Covers the BRAIN HTTP API (auth, multi-simulation, rate limits, recordsets), consultant-tier submission thresholds, and the self-evolution loop. Also use for 中文 requests about WorldQuant、BRAIN、WQ Alpha、顾问权限、因子表达式、回测、提交、换手、Fitness、Sharpe。"
---

# WQ Alpha 研究 Skill

> 结构化 playbook：字段 → 表达式 → 回测 → 检查 → 提交 → 组合。融合 WorldQuant BRAIN 文档知识与 USA TOP3000 实证经验。

---

## 1. 快速决策树

```
开始
  ├── 拉取所有 alpha 列表 ──→ 只看 ACTIVE；算 **日收益** 相关，>0.7 则修改或放弃
  ├── 设计新因子
  │    ├── 字段已验证？ ──否──→ 查第 2 节（本地字段文件搜索 / 模拟 rank(field)）
  │    └── 是 ──→ 若套模板，先过 4.1.1 数据集一致性门槛
  │               （模板信号字段与用户字段同一 dataset，否则混信号 → 停止执行）
  │         ├── 基本面 ──→ group_rank + ts_rank, SUBINDUSTRY, decay=0
  │         ├── 分析师 ──→ group_rank + ts_rank, INDUSTRY/SUBINDUSTRY, decay=0–4
  │         ├── 技术 ────→ 高 decay(10–30) 或混合基本面降低换手
  │         └── 情绪 ────→ nanHandling=ON, 小窗口谨慎
  └── 提交后 ──→ 验证 status == ACTIVE，否则检查 SELF_CORRELATION
```

---

## 2. 字段速查（本地数据集）

本 SKILL 已内置 USA TOP3000 delay=1 的完整字段列表（共 4367 个），无需每次从网页/ API 拉取：

- `references/wq_usa_top3000_delay1_data_fields.json`：完整字段元数据数组
- `references/wq_usa_top3000_delay1_data_fields.csv`：CSV 版，方便 Excel/ pandas 查看
- `references/wq_usa_top3000_delay1_data_fields_summary.json`：分类统计与示例字段

字段分布：

| 类别 | 数量 | 说明 |
|------|------|------|
| fundamental | 1652 | 财务报表、附注科目 |
| analyst | 1324 | 分析师预期、一致预期 |
| news | 996 | 新闻、财报事件 |
| pv | 195 | 价量、ADV、VWAP 等 |
| option | 138 | 期权隐含波动、Put/Call 等 |
| model | 40 | 模型因子 |
| socialmedia | 22 | 社交媒体情绪 |
| univ1 | 6 | Universe 相关 |

### 2.1 本地搜索字段

```python
import json
from pathlib import Path

# 假设在 skill 目录下运行；如在其他位置，改为实际路径
skill_dir = Path(".")
field_dir = skill_dir / "references"
data = json.loads((field_dir / "wq_usa_top3000_delay1_data_fields.json").read_text(encoding="utf-8"))

keyword = "operating_income"
matches = [
    f for f in data
    if keyword.lower() in f["id"].lower()
    or (f.get("description") and keyword.lower() in f["description"].lower())
]

for f in matches[:10]:
    print(f"{f['id']} | {f.get('category',{}).get('name')} | {f.get('dataset',{}).get('name')} | coverage={f.get('coverage')} | alphaCount={f.get('alphaCount')}")
```

### 2.2 按类别筛选

```python
category = "pv"  # 或 fundamental / analyst / news / option / model / socialmedia
fields = [f for f in data if f.get("category", {}).get("id") == category]
print(f"{category}: {len(fields)} fields")
for f in sorted(fields, key=lambda x: x.get("alphaCount", 0), reverse=True)[:10]:
    print(f"  {f['id']} | alphaCount={f.get('alphaCount')} | coverage={f.get('coverage')}")
```

### 2.3 字段验证

拿到候选字段后，**先用简单表达式模拟验证**字段是否真的可用：

```python
payload = {
    "type": "REGULAR",
    "settings": {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 0, "neutralization": "MARKET",
        "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY",
        "nanHandling": "ON", "language": "FASTEXPR", "visualization": False,
    },
    "regular": "rank(my_candidate_field)",
}
resp = session.post("https://api.worldquantbrain.com/simulations", json=payload)
# 201 表示字段可用；非 201 通常表示字段不存在或参数不匹配
```

### 2.4 何时需要重新拉取

本地字段集已覆盖 USA TOP3000 delay=1。以下情况才需要重新从 BRAIN 拉取：

- 换 Region（如 CHN、EUR）
- 换 Universe（如 TOP500、TOP1000）
- 换 Delay（如 0）
- BRAIN 平台字段列表明显更新（可对比 `dateCreated` 与本地）

---

## 3. 运算符速查表

| 类型 | 算子 | 作用 |
|------|------|------|
| 截面 | `rank(x)`, `zscore(x)`, `normalize(x)`, `scale(x)`, `winsorize(x, std=4)` | 每天对所有股票标准化 |
| 时序 | `ts_mean`, `ts_std_dev`, `ts_delta`, `ts_rank`, `ts_corr`, `ts_decay_linear`, `ts_backfill`, `ts_zscore` | 单只股票历史窗口计算 |
| 分组 | `group_rank(x, group)`, `group_neutralize(x, group)`, `group_zscore(x, group)`, `group_backfill(x, group, N)` | 组内中性化 |
| 条件 | `if_else(cond, a, b)`, `trade_when(x, cond, delay)` | 条件暴露 |
| 向量 | `vec_avg(a, b, c)`, `vec_sum(a, b, c)` | 多字段逐元素平均/求和 |

**黄金组合**：`group_rank(ts_rank(signal, N), subindustry)`

---

## 4. 因子模板库

### 4.1 高胜率模板

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
FIELDS_JSON = Path("/path/to/wq-alpha-research/references/wq_usa_top3000_delay1_data_fields.json")

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

```fastexpr
-- 模板 A：ROE 趋势（主信号 fundamental6：operating_income, equity）
-- ⚠️ 旧注「通过率最高」指的是「最不容易报错、最容易跑出结果」，**不是**「能过顾问门槛」。
--    2026-10-29 USA TOP3000 D1 实测：Sharpe 1.23 / Fitness 0.58，未过 1.58 / 1.0。
group_rank(ts_rank(operating_income / equity, 126), subindustry)

-- 模板 B：EPS 收益率修正（主信号 analyst4：est_eps；close 为 pv1 价格基准）
group_rank(ts_rank(est_eps / close, 126), industry)

-- 模板 C：FCF 收益率（主信号 analyst4：free_cash_flow_reported_value；equity 为规模基准）
group_rank(ts_rank(free_cash_flow_reported_value / equity, 126), industry)

-- 模板 D：多因子混合（高 Fitness）【跨数据集：fundamental6 + analyst4】
-- ⚠️ 混合模板：不得用于套用用户给定的单一字段（必触发 4.1.1 混信号门槛）
0.5 * group_rank(ts_rank(operating_income / equity, 126), subindustry)
+ 0.5 * group_rank(ts_rank(est_eps / close, 126), industry)

-- 模板 E：低相关技术+基本面混合【跨数据集：pv1 + fundamental6】
-- ⚠️ 混合模板：同上，不得用于套用用户字段
0.5 * rank(-(close / open - 1)) + 0.5 * rank(ts_rank(operating_income / equity, 126))

-- 模板 F：资产周转 × 利润率（主信号 fundamental6：operating_income, sales, assets）
rank(ts_rank(operating_income / sales * sales / assets, 126))

-- 模板 G：期权 IV skew × 基本面质量【跨数据集：option + fundamental6/analyst4】★历史命中率最高
-- ⚠️ 混合模板：不得用于套用用户给定的单一字段（必触发 4.1.1 混信号门槛）
-- 腿1（期权）：rank(ts_mean((implied_volatility_call_180 - implied_volatility_put_180)/implied_volatility_mean_180, 5))
-- 腿2（质量）：group_rank(ts_rank(operating_income/equity, 126), subindustry)
-- 质量腿可换：free_cash_flow_reported_value/equity、cashflow_op/equity、enterprise_value/cashflow、enterprise_value/ebitda
0.5 * rank(ts_mean((implied_volatility_call_180 - implied_volatility_put_180) / implied_volatility_mean_180, 5))
+ 0.5 * group_rank(ts_rank(operating_income / equity, 126), subindustry)
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

### 4.2 推荐默认设置

| 因子类型 | Decay | Neutralization | Truncation | nanHandling | 预期 TO |
|----------|-------|----------------|------------|-------------|---------|
| 基本面质量 | 0 | SUBINDUSTRY | 0.08 | ON | 2–8% |
| 分析师预期 | 0–4 | INDUSTRY/SUBINDUSTRY | 0.08 | ON | 9–16% |
| 技术反转 | 10–30 | INDUSTRY | 0.08 | OFF | 15–35% |
| 混合因子 | 4–20 | INDUSTRY/SUBINDUSTRY | 0.08 | ON | 10–20% |
| 情绪 | 4–10 | INDUSTRY | 0.05–0.08 | ON | 8–30% |

---

## 5. 指标与检查

### 5.1 核心指标

| 指标 | 公式/含义 | 目标 |
|------|-----------|------|
| Sharpe | 日 IR × √252 | 见 5.1.1 阈值表 |
| Fitness | Sharpe × √(|Returns| / max(TO, 0.125)) | 见 5.1.1 阈值表 |
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

**已验证的行为**：`POWER_POOL_CORRELATION` 在 alpha 的 `is.checks[]` 里**对合格候选出现**，但实测在 ACTIVE alpha 上**恒为 `PENDING`**（`is.powerPoolCorrelation` 也为 `None`）——平台在当前阶段并未回算该值。因此**不能**用它做提交前判据，只能按上面 4 条硬约束自行预筛。

> **⚠️ 实测修正（2026-10-31，首批 10 候选全量仿真 + 提交实测）**
> 1. **`build_payload(sim_type="POWER_POOL")` 直接 400**：`{"type":["Object with name=POWER_POOL does not exist."]}`。
>    仿真 `type` 只能是 `"REGULAR"`，**Power Pool 不是合法的 `type` 值**，不能靠设 type 进 PP 通道。
> 2. **提交 REGULAR alpha（Sharpe 落在 [1.0,1.58)）会被 REGULAR 门槛挡下**：403 body 里
>    `LOW_SHARPE` 的 limit 仍是 **1.58**（不是 PP 的 1.0），且 `POWER_POOL_CORRELATION` 保持
>    **PENDING（永不被计算）**。即平台**不会自动把 1.0–1.58 的 alpha 路由到 PP**，必须显式触发
>    PP 提交上下文（疑似走 theme/competition 或带 `description` 的特定提交；403 里出现
>    `POWER_POOL_DESCRIPTION_LENGTH`/`POWER_POOL_DESCRIPTION_FORMAT` 两个 PP 专属 WARNING，
>    暗示 PP 提交需要填描述）。**PP 的准确提交触发方式尚未完全查清，需进一步验证。**
> 3. **`model51` 字段（如 `unsystematic_risk_last_360_days`）双杀**：实测提交出现
>    `CONCENTRATED_WEIGHT` FAIL（None/None）+ `LOW_COVERAGE` FAIL（value=17, limit=5），
>    **常规与 PP 两条通道都过不去**。PP 候选避开 model51。
> 4. **单腿「未饱和」基本面/分析师在 USA TOP3000 上打不到 1.0**：首批 9 条非 model51 候选
>    Sharpe 仅 0.09–0.92（F4 `anl4_ebitda_value/debt` 最高 0.92，仍 <1.0）；唯一 ≥1.0 的是
>    model51（1.44，但被第 3 点双杀）。能稳定 ≥1.0 的单腿几乎都是**已饱和族**
>    （`operating_income/equity`≈1.23、IV skew 1.5+），但那些又撞 SELF/PP 相关。
>    ⇒ 想用 ≤3 字段达到 PP 的 Sharpe≥1.0，**更靠谱的是 ≤3 字段的双腿正交混合**（见 §10 双腿 33% 命中率），
>    而非单腿未饱和信号——单腿未饱和信号普遍卡在 0.6–0.9。

> 代码里用 `BrainSession.thresholds(delay)` 取阈值，它按账号权限自动在
> `CONSULTANT_THRESHOLDS` / `STANDARD_THRESHOLDS` 之间切换。

### 5.2 IS 检查清单（真实 check 名称，2026-09 顾问面板实测）

| 检查项 | 阈值 | 失败原因 | 修复方法 |
|--------|------|----------|----------|
| LOW_SHARPE | 见 5.1.1 | 信号弱 | 换字段/窗口/加 group_rank |
| LOW_FITNESS | 见 5.1.1 | 换手过高 | 增大 decay、混合稳定信号 |
| LOW_TURNOVER | ≥ 1% | 信号太稳定 | 缩短窗口、换更活跃字段 |
| HIGH_TURNOVER | ≤ 70% | 换手爆炸 | 增大 decay、trade_when、混合 |
| CONCENTRATED_WEIGHT | 单股 < 10% 且分散 | 权重集中 | 用 rank()、降低 truncation、ts_backfill |
| LOW_SUB_UNIVERSE_SHARPE | TOPXXX：`subU_Sharpe ≥ 0.75·√(size_ratio)·Sharpe` | 小票依赖 | 用基本面、SUBINDUSTRY、避免市值倾斜 |
| **IS_LADDER_SHARPE** | 分年阶梯（D1 FAIL 1.59；见 5.2.1） | 近年 Sharpe 衰减 | 提高近年表现；TO<30% 时 PASS 阈值×0.85 |
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

## 6. 问题诊断与修复

| 症状 | 可能原因 | 修复 |
|------|----------|------|
| **Fitness < 1.0 且 TO < 12.5%** | 分母被 0.125 地板锁死，降 TO 无效；缺的是 Returns | **第一顺位：把 neutralization 从 SUBINDUSTRY 换成 INDUSTRY**（2026-10-30 同一表达式实测 F 0.95→1.08、Returns 4.47%→5.32%、TO 只从 8.0% 动到 7.4%）。第二顺位提 Sharpe。❌ 不要靠降 decay 提 TO（见 §5.1 推论 2） |
| Sharpe < 1.25 | 信号弱 | 拉长窗口、group_rank、换字段 |
| TO > 50% | 信号变化太快 | decay 10–30、trade_when、混合 |
| DD > 15% | 波动大/杠杆高 | 增大 decay、降 truncation、混合低波信号 |
| CONCENTRATED_WEIGHT FAIL | 稀疏/极值 | rank()、truncation 0.05、ts_backfill |
| Sub-Universe FAIL | 小票依赖 | 避免 `rank(-assets)`，用 group_rank、加流动性过滤 |
| 新闻/事件类信号 TO > 60%（如 Bull Trap：`news_pct_1min` 斜率 × `news_max_up_ret`） | 事件驱动字段日间跳变 + 短窗斜率相乘、无平滑（2026-08 实测：TO=65%、Fitness 0.93 FAIL） | **0.3 新闻 + 0.7 基本面**：`0.3*新闻信号 + 0.7*group_rank(ts_rank(operating_income/equity,126),subindustry)` → TO 65%→26%、Sharpe 1.57→1.73、DD 15.4%→5.9%；新闻部分再包 `ts_decay_linear(信号,5)` → TO 15.3%、Fitness 1.24（INDUSTRY 中性化）。**不要**拉长回归窗口（5→20 伤 Sharpe 至 1.41）或设置层 decay=15（Sharpe 打穿至 1.18）；新闻信号配 SUBINDUSTRY 反而 Fitness FAIL（0.98） |
| simulation_error | 字段不存在/算子参数错误 | 先 rank(field) 验证字段，检查算子参数个数 |
| trade_when 零交易 | 条件过严 | 放宽条件或用 if_else |

---

## 7. BRAIN API 自动化

> 本节已按 **2026-09-21** 版官方文档（`/learn/documentation/consultant-information/brain-api`）与顾问账号实测行为重写。
> 可执行实现集中在 `scripts/wq_api.py`，下列代码即其用法的精简说明；**优先直接 import，不要在各脚本里重抄一遍**。

### 7.0 只保留一套实现：`scripts/wq_api.py`

| 能力 | 旧做法（已废弃） | 现状 |
|------|------------------|------|
| 轮询等待 | 固定 `sleep(8)` + 最多 90 次 | 按响应头 `Retry-After` 驱动 |
| 终态判断 | 只认 `COMPLETE` / `ERROR` / `FAILED` | `WAITING`/`SIMULATING`/`COMPLETE`/`WARNING`/`CANCELLED`/`ERROR`/`TIMEOUT`/`FAIL`；`WARNING` 也带 alpha |
| 批量仿真 | 逐个 POST 串行 | 数组 POST（2..10 个）+ 父任务 `children` |
| 额度控制 | 无 | 解析 `X-Ratelimit-Limit/Remaining/Reset` |
| 重复仿真 | 无 | `SimulationCache`（payload sha256 去重，JSONL 落盘） |
| 拉 alpha 列表 | 拉全量 500+ 再本地筛 | 服务端 `?status=ACTIVE` 过滤 |
| PnL 对齐 | 要求两条序列等长 | 按**日期交集**对齐后算相关 |
| 提交确认 | 只看 201 | 轮询至 `ACTIVE`，并单独判 `SELF_CORRELATION`/`PROD_CORRELATION` |

```python
import sys; sys.path.insert(0, "scripts")
from wq_api import BrainSession, SimulationCache, build_payload, print_row, simulate_one, submit_verified

brain = BrainSession()          # WQ_BRAIN_USERNAME/PASSWORD 或 credential.txt
brain.authenticate()
print(brain.user_id, brain.permissions, brain.thresholds(1))
```

### 7.1 认证与权限

`POST /authentication`（Basic Auth）→ 201，返回 JWT（cookie `t`，默认 4 小时）与 `permissions`。**先读 permissions 再决定能做什么**：

| 权限 | 含义 |
|------|------|
| `CONSULTANT` | 顾问：更高提交门槛 + PROD_CORRELATION + BRAIN Labs + 欧元/亚洲市场 |
| `MULTI_SIMULATION` | 可一次 POST 数组跑 2..10 个仿真 |
| `QUICK_MODE` | 可用 `simulationMode: "QUICK"` 快速粗略回测 |
| `REGION_AGNOSTIC` / `PROD_ALPHAS` / `VISUALIZATION` / `BRAIN_LABS` | 区域无限制 / 生产池 / 可视化 / Labs |

要点：

- `GET /authentication` 可查当前状态：未登录 `204`，已登录 `200` 带 `user.id`/`token.expiry`。
- `POST` 可带 `{"expiry": <1..14400>}` 指定有效期；反复失败会要求 `recaptcha`（400/401 带 `recaptcha` 字段）。
- 启用生物识别的账号会返回 `401` + `WWW-Authenticate: persona` + `Location`，需在浏览器完成认证后再 POST 该 `Location`。
- `DELETE /authentication` 注销并作废 JWT。
- 建议会话级复用 cookie；`BrainSession` 在 401 时会自动重认证一次。

### 7.2 获取已提交 Alpha 并计算相关性（双层护栏）

**目的**：在新因子提交前，避免与已上线因子撞 SELF_CORRELATION。两层护栏：

- **护栏 1（日收益相关，proxy）**：按日期交集对齐算日收益相关，< 0.7 才算安全。**但这是 proxy，会低估信号级相关**（见下方实战教训）。
- **护栏 2（信号成分重叠，关键）**：提取候选的核心 `group_rank(...)` 信号，与已上线 alpha 的表达式做子串匹配。若候选信号是某已上线 alpha 的子串，则两者**信号级相关 ≈ 0.9**，WQ 的 SELF_CORRELATION 必 FAIL。护栏 2 只比表达式、不拉 PnL，便宜且能提前拦截近复制品。

```python
import re
import numpy as np

# ---------- 数据拉取 ----------
def fetch_pnl(session, alpha_id, retries=4):
    """获取 Alpha PnL 序列，返回 [(date, value), ...]。空结果重试 ≥3 次。"""
    for _ in range(retries):
        r = session.get(f"{API_BASE}/alphas/{alpha_id}/recordsets/pnl")
        if r.status_code == 200 and r.text.strip():
            data = r.json()
            props = data.get("schema", {}).get("properties", [])
            if isinstance(props, list):
                date_idx = next((i for i, p in enumerate(props) if p.get("name","").lower()=="date"), 0)
                pnl_idx = next((i for i, p in enumerate(props) if p.get("name","").lower() in ("pnl","cum_pnl","returns","ret")), 1)
            else:
                date_idx = next((v["index"] for k,v in props.items() if k.lower()=="date"), 0)
                pnl_idx = next((v["index"] for k,v in props.items() if k.lower() in ("pnl","cum_pnl","returns","ret")), 1)
            recs = sorted(data.get("records", []), key=lambda r: r[date_idx])
            out = []
            for row in recs:
                rec = row[0] if isinstance(row, list) and len(row)==1 and isinstance(row[0], list) else row
                try:
                    out.append((rec[date_idx], float(rec[pnl_idx])))
                except Exception:
                    continue
            if out:
                return out
        time.sleep(8)
    return []

def to_returns(pnl):
    """累计曲线→日收益；日收益序列原样返回。**保留 (date, value) 以便按日期对齐**。
    判据：水平波动 std(a) 远大于日变化 std(diff(a))（>5×）即累计曲线；旧 mean/std 启发式对慢牛会误判。"""
    if len(pnl) < 30:
        return []
    a = np.asarray([v for _, v in pnl], dtype=float)
    d = np.diff(a)
    if d.std() > 0 and a.std() > 5 * d.std():
        return [(pnl[i+1][0], float(d[i])) for i in range(len(d))]   # 累计曲线→日收益（带日期）
    return [(dt, float(v)) for dt, v in pnl]                         # 已是日收益序列（带日期）

def aligned_corr(new_ret, old_ret):
    """按日期交集对齐后算日收益相关（位置对齐会低估相关）。"""
    if len(new_ret) < 30 or len(old_ret) < 30:
        return None
    nd = {dt: v for dt, v in new_ret} if isinstance(new_ret[0], tuple) else None
    # 若传入的是 (date,val) 列表，先转成对齐序列
    if nd is not None:
        common = [dt for dt, _ in old_ret if dt in nd]
        if len(common) < 30:
            return None
        y1 = [nd[dt] for dt, _ in old_ret if dt in nd]
        y2 = [v for dt, v in old_ret if dt in nd]
        return float(np.corrcoef(y1, y2)[0, 1])
    n = min(len(new_ret), len(old_ret))
    return float(np.corrcoef(new_ret[-n:], old_ret[-n:])[0, 1])

# ---------- 护栏 2：信号成分重叠（关键）----------
def _balanced_close(s, open_idx):
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(": depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1

def main_signal(expr):
    """提取核心排名信号（最外层 group_rank(...) / rank(...)）。"""
    e = (expr or "").replace("\n", " ")
    idx = e.find("group_rank(")
    if idx >= 0:
        k = e.find("(", idx); j = _balanced_close(e, k)
        if j > 0:
            return e[idx:j+1]
    for fn in ("rank(", "ts_rank(", "ts_zscore(", "zscore("):
        idx = e.find(fn)
        if idx >= 0:
            k = e.find("(", idx); j = _balanced_close(e, k)
            if j > 0:
                return e[idx:j+1]
    return e.strip()

def norm(e): return re.sub(r"\s+", "", (e or "")).lower()

def signal_overlap(cand_expr, active_exprs):
    """候选核心信号是否⊂某已上线 alpha 表达式（或反之）。命中→信号级相关≈0.9，必撞 SELF_CORRELATION。
    active_exprs: {alpha_id: expression}。"""
    cm = norm(main_signal(cand_expr))
    hits = []
    for oid, oexpr in active_exprs.items():
        on = norm(oexpr)
        if cm and cm in on:
            hits.append(oid)
        else:
            om = norm(main_signal(oexpr))
            if om and om in norm(cand_expr):
                hits.append(oid)
    return hits

# ---------- 使用示例 ----------
def get_active_alphas(session, user_id="self", limit=100):
    """获取所有 alpha（含 ACTIVE / UNSUBMITTED），分页。"""
    all_alphas, offset = [], 0
    while True:
        data = session.get(f"{API_BASE}/users/{user_id}/alphas", params={"limit": limit, "offset": offset}).json()
        batch = data.get("results", data.get("alphas", []))
        if not batch:
            break
        all_alphas.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return all_alphas

active = [a for a in get_active_alphas(session) if a.get("status") == "ACTIVE"]

# 护栏 2：先比表达式（便宜，不用拉 PnL）
active_exprs = {a["id"]: (a.get("regular") or {}).get("code", "") or a.get("expression", "") for a in active}
overlap = signal_overlap(new_expr, active_exprs)   # new_expr = 候选表达式字符串
if overlap:
    print(f"⚠️ 信号成分重叠（SELF_CORRELATION 将 FAIL）: {overlap} — 建议放弃或换信号簇")

# 护栏 1：日收益相关（proxy，按日期对齐）
new_pnl = fetch_pnl(session, new_alpha_id)
new_ret = to_returns(new_pnl)
for alpha in active:
    old = fetch_pnl(session, alpha["id"])
    old_ret = to_returns(old)
    c = aligned_corr(new_ret, old_ret)
    if c is not None:
        flag = "❌" if abs(c) >= 0.7 else ("⚠️" if abs(c) >= 0.5 else "✅")
        print(f"{flag} 与 {alpha['id']} 日收益相关: {c:+.3f}")
```

**判断规则**：

| 信号成分重叠 | 日收益相关 | 动作 |
|------|------|------|
| 命中 | — | ❌ 直接放弃（信号级相关≈0.9，必 FAIL） |
| 未命中 | abs < 0.5 | ✅ 可提交 |
| 未命中 | 0.5 ≤ abs < 0.7 | ⚠️ 谨慎，需新 Sharpe ≥ 冲突因子 × 1.1 |
| 未命中 | abs ≥ 0.7 | ❌ 放弃或重构（除非新 Sharpe ≥ 旧 × 1.1） |

> ⚠️ **不要用累计 PnL 算相关**（累计曲线自带趋势，会把所有因子看成同一个，相关普遍 > 0.90）。
> ⚠️ **日收益相关只是 proxy**：WQ 的 SELF_CORRELATION 用信号级相关，近复制品（共享同一核心 `group_rank(...)` 信号）的日收益相关可能只有 0.4–0.5，但信号级相关 0.9+ 仍会 FAIL。**护栏 2 比护栏 1 更可靠**，提交前必跑。

**实战教训（2026-08-30）**：纯信号版 `F3 = group_rank(ts_rank(raw, 60), subindustry)`（S=1.81）与已上线 `M3 = 0.6*sg + 0.4*OI`（sg 同信号，S=2.56）日收益相关仅 0.465（看似安全），但信号成分重叠 → 提交后 SELF_CORRELATION **FAIL 0.9313**（>0.7 且 Sharpe 未高 10%），被拒。加护栏 2 后复跑即拦下 `候选信号⊂已上线 gJjLJvlm`。

### 7.3 仿真提交（settings 权威字段）

`POST /simulations` → `201` + `Location: /simulations/<id>`。字段以 `OPTIONS /simulations` 的实时 schema 为准（**这是最可靠的字段清单，优先于任何文档快照**）。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | choice | ✓ | `REGULAR` / `REGION_AGNOSTIC` |
| `settings.instrumentType` | choice | ✓ | 目前仅 `EQUITY` |
| `settings.region` | choice | ✓ | `USA` `GLB` `EUR` `ASI` `CHN` `KOR` `HKG` `AMR` `IND` `DEU` `GBR` `ALL` |
| `settings.universe` | choice | ✓ | `TOP3000` `TOP1000` `TOP500` `TOPSP500` `TOPDIV3000` `MINVOL1M` `MINVOL10M` `ILLIQUID_MINVOL1M` 等 |
| `settings.delay` | choice | ✓ | `0` / `1` |
| `settings.decay` | int | ✓ | `0..512` |
| `settings.neutralization` | choice | ✓ | `NONE` `MARKET` `SECTOR` `INDUSTRY` `SUBINDUSTRY` `COUNTRY` + 风险类 `SLOW` `FAST` `SLOW_AND_FAST` `CROWDING` `REVERSION_AND_MOMENTUM` `STATISTICAL` |
| `settings.truncation` | float | ✓ | `0..1`（常用 0.05–0.08） |
| `settings.pasteurization` | choice | ✓ | `ON` / `OFF` |
| `settings.unitHandling` | choice | ✓ | `VERIFY` |
| `settings.nanHandling` | choice | ✓ | `ON` / `OFF`（默认 OFF） |
| `settings.language` | choice | ✓ | `FASTEXPR` / `PYTHON` |
| `settings.visualization` | bool | ✓ | 一般 `False`（开则更慢） |
| `settings.lookback` | int | | `0..1024` |
| `settings.maxTrade` | choice | | `ON`/`OFF`；ASI/JPN/HKG/KOR/TW 必须 `ON` |
| `settings.maxPosition` | choice | | `ON`/`OFF`；USA/ASI/EUR 建议 `ON` 提升容量真实性 |
| `settings.testPeriod` | string | | `P0Y0M0D` … `P6Y0M0D`，把 IS 尾部划为测试段 |
| `settings.simulationMode` | choice | | `FULL`（默认）/ `QUICK` |

```python
from wq_api import build_payload, simulate_one
row = simulate_one(brain, "group_rank(ts_rank(operating_income/equity,126),subindustry)",
                   neutralization="SUBINDUSTRY", decay=0)
print_row(row)          # Sharpe / Fitness / TO / Ret / DD + 本地门槛判定
```

`simulate_one` 内部走 `brain.run()`：提交 → 按 `Retry-After` 轮询 → 取 `alpha` 字段 → 拉指标与 checks。

### 7.4 多仿真（MULTI_SIMULATION）

顾问可同时跑 **最多 8 个多仿真**，每个含 **最多 10 个 alpha**（批内串行）。API 直接 POST 数组：

```python
resp = brain.request("POST", "/simulations", json=[payload_a, payload_b])
parent_id = resp.headers["Location"].rstrip("/").split("/")[-1]
parent = brain.wait(parent_id)          # 父任务完成后 children 才有子仿真 id
for child_id in parent.children:
    print(brain.wait(child_id))
```

约束（违反即 400 或资源错误）：

1. 一批 2..10 个；**同批内 `type`/`instrumentType`/`region`/`delay`/`language` 必须一致**（`BrainSession.simulate_multi` 会前置校验）。
2. 报 `The simulation requires more resources than are available` 时，减小批内数量重试。
3. 每个子仿真都会计入当日额度——多仿真不省额度，只省你等的时间。

`brain.run_many(payloads, batch_size=8)` 已封装切片与串行，直接用即可。

### 7.5 每日额度与限流

`POST /simulations` 的响应头给出额度：

```
X-Ratelimit-Limit: 5000        # 当日总上限
X-Ratelimit-Remaining: 4998    # 当日剩余
X-Ratelimit-Reset: 3393        # 距离重置的秒数
```

实测（顾问账号，2026-10）：`limit=5000`。注意：

- **所有成功仿真都计数**，包括多仿真里的子仿真、以及"重新模拟已存在的 alpha"。
- 同一表达在不同日期重跑也计数，但 alpha 只出现在首次模拟那天 → 别用 Alphas 页面的 Today 计数估算额度。
- 额度耗尽后要等到次日（EST 时区）重置。脚本里用 `brain.remaining_simulations` 做前置守卫。
- `429` 读 `Retry-After` 退避；`BrainSession.request` 已内置 3 次重试。

### 7.6 记录集（recordsets）

```
GET /alphas/<id>/recordsets            # 列出可用记录集
GET /alphas/<id>/recordsets/<name>     # 取具体记录集
```

可用名称：`pnl` `daily-pnl` `sharpe` `turnover` `yearly-stats` `coverage` `coverage-by-industry` `coverage-by-sector` `average-size-by-*` `pnl-by-*` `sharpe-by-*` `average-value-by-*`。

返回是压缩表：`schema.properties[].name/type` + `records` 二维数组，**列顺序要与 properties 对齐**。`type` 影响显示格式：`amount`（千/百万/十亿）、`percent`、`permyriad`（万分比）、`date`、`datetime`。

**未就绪时返回 `Retry-After`**，必须等（旧代码只看 200 会拿到空 body）。直接用 `brain.pnl_series(alpha_id)` → `[(date, value)]`。

### 7.7 提交与二次确认

```python
outcome = submit_verified(brain, alpha_id)
# "ACTIVE" | "SELF_CORRELATION_FAIL(value=...)" | "PROD_CORRELATION_FAIL(...)" | "still_UNSUBMITTED"
```

- `POST /alphas/<id>/submit` 返回 **201 只表示请求被接受**，不是上线。
- 必须轮询到 `status == "ACTIVE"`；`UNSUBMITTED` 通常意味着相关性检查没过或仍在审核。
- `OLD_SIMULATION = FAIL` 时，说明该 alpha 的仿真太旧，**需重新模拟**再提交，而不是重试 submit。

#### 7.7.1 相关性数值的两个位置（读错就会以为"平台不暴露"）

`SELF_CORRELATION` 在 alpha 生命周期里**换了位置**，只认一处必然读空：

| alpha 状态 | 数值位置 | 说明 |
|------------|----------|------|
| 刚模拟 / `UNSUBMITTED` | `is.checks[]` 中 `name == "SELF_CORRELATION"`，`result` 常为 `PENDING` | 未提交，相关性尚未计算 |
| 已提交 / `ACTIVE` | `is.selfCorrelation`（float），**checks 里没有该项** | 例如 `0.8166` |
| 生产池相关（顾问） | `is.prodCorrelation`（float） | 未提交时为 `0.0` |

```python
brain.self_correlation(alpha)   # 两个位置都读，返回 float 或 None
brain.prod_correlation(alpha)
```

> 旧笔记曾断言"`is.checks` 里永远找不到 SELF_CORRELATION"——那只是 ACTIVE alpha 的表现；`UNSUBMITTED` alpha 的 checks 里确实有这一项（`PENDING`）。**两处都要读**才是完整结论。

另注：`is.selfCorrelation > 0.7` 的 alpha 仍可能是 ACTIVE（豁免条件：新 Sharpe ≥ 冲突因子 × 1.1），所以它只用于判断"是否需要换信号簇"，不能当提交的硬否决。

#### 7.7.2 提交配额：201 吞提交 vs 403 硬封锁

`POST /alphas/{id}/submit` 的返回码要分三种，**只看 2xx 不够**：

| 返回 | 含义 | 处置 |
|------|------|------|
| 200 / 201 | 请求被接受，**但不等于进了审核队列** | 继续核验 `dateSubmitted` 非 None 且 status 离开 `UNSUBMITTED` |
| 429 | 软限频 | 读 `Retry-After` 退避后重试 |
| 403 | **两类**：① 提交配额耗尽（硬封锁）；② **相关性 FAIL 的判定书** | 先解析 body（见坑二），再决定是等配额还是换信号 |

**坑一：201 吞提交（静默丢弃）** — 返回 201，但 `dateSubmitted` 恒为 `None`、status 卡 `UNSUBMITTED`、`SELF_CORRELATION` 一直 `PENDING`。这表示提交被丢弃、alpha 从未进队列。**正确处置：再 POST 一次**——第二次通常返回 403，其响应体就是带真实数值的最终判定（见坑二）。`submit_verified` 已内置这一步，返回 `submit_blocked(...)`。

**坑二：403 ≠ 一定是配额耗尽（2026-10-30 修正）** — 403 响应体形如 `{"is": {"checks": [...]}}`，是**提交时实时计算**的完整 IS checks。实测 `E560gqE1` 的 403 body 里：`PROD_CORRELATION FAIL value=0.8045 limit=0.7`、`SELF_CORRELATION PASS 0.6226`、`REGULAR_SUBMISSION PASS value=0 limit=4`——配额根本没用完，FAIL 的是生产池相关。

```python
from wq_api import submit_verdict
detail = submit_verdict(resp)   # "PROD_CORRELATION=0.8045(limit=0.7)" 或 ""（空=真配额耗尽）
```

这是**唯一**能拿到相关性真实数值的途径：`is.prodCorrelation` 在 ACTIVE alpha 上恒为 `0.0`（平台不回算，与 `POWER_POOL_CORRELATION` 同为僵尸字段），轮询一万年也读不到。因此 403 必须先解析 body，只有 body 里没有 FAIL 项时才是真的配额耗尽。

**坑三：`/alphas` 集合端点对部分账号返回 405** — 既不能 `GET` 枚举，也不能 `POST` 建 alpha；只能 `GET /alphas/{id}` 按 id 查。此时"提交前拉全部 alpha 算日收益相关"不可行，只能依赖信号成分重叠护栏 + BRAIN 自己的信号级相关性。`BrainSession.alphas()` 遇到 405 会抛错，请捕获后退化为按 id 查。

### 7.8 重复仿真去重（省额度）

官方推荐：对 payload 做 sha256，本地缓存 `hash → alpha_id`，命中就复用，不再提交。

```python
from wq_api import SimulationCache
cache = SimulationCache("simulation_cache.jsonl")
results = brain.run_cached(payloads, cache, batch_size=8)
```

用 LLM/模板批量生成表达式时，这一步能省掉大量重复额度——**同一表达式换个权重往往是"新" payload，但同一份配置重复跑毫无意义**。

### 7.9 拉取最新官方文档（保持同步）

平台文档站是 SPA，匿名抓不到内容，但内容接口可用（需登录态 cookie）：

```python
GET https://api.worldquantbrain.com/tutorials?limit=50          # 目录：11 个教程 / 80+ 页
GET https://api.worldquantbrain.com/tutorial-pages/<page_id>    # 正文（blocks 数组）
```

常用 `page_id`：

| page_id | 内容 |
|---------|------|
| `brain-api` | BRAIN HTTP API 全量端点与错误码 |
| `understanding-simulation-limits` | 每日额度与 `X-Ratelimit-*` |
| `multi-alpha-simulation` | 多仿真与 Test Period |
| `consultant-submission-tests` | **顾问级提交阈值**、IS Ladder、Cluster |
| `consultant-features` | OS 测试项、MaxTrade/MaxPosition、Prod Correlation |
| `how-can-you-avoid-duplicate-simulations` | hash 去重缓存 |
| `alpha-submission` | 提交测试细则 |

正文是 block 数组（`HEADING`/`TEXT`/`TABLE`/`EQUATION`/`IMAGE`），按 `type` 渲染即可。**每次大改代码前先拉 `brain-api` 的 `lastModified` 比对**。

### 7.10 常见 API 错误

| 现象 | 原因与处理 |
|------|------------|
| `400 "Invalid data field"` | 字段名错，或把 vector/matrix 字段用于不支持的算子 |
| `400 "Got invalid input at index 0, must be an event data"` | 向量算子传了常数 |
| `400` 且 body 为 `{"settings": {"region": ["This field is required."]}}` | 必填项缺失，按字段路径逐个补 |
| `400 "Expected ISO 8601 datetime with timezone"` | 列表过滤的时间参数要带时区 |
| `404` on `/users/self/alphas` | 路径错；正确是 `GET /users/self/alphas`（或 `/users/<id>/alphas`） |
| 仿真 `ERROR` 带 `location` | `{property, line, start, end}` 直接定位表达式语法错误 |
| 仿真长期无 `status` 字段 | 进行中的 GET 只返回 `progress`，别把它当异常 |

---

## 8. 组合构建规则

### 8.1  diversified 组合示例

| 簇 | 代表表达式 |
|----|------------|
| 盈利能力 | `group_rank(ts_rank(operating_income/equity, 126), subindustry)` |
| 分析师 | `group_rank(ts_rank(est_eps/close, 252), subindustry)` |
| FCF | `group_rank(ts_rank(free_cash_flow_reported_value/equity, 126), industry)` |
| 低相关混合 | `0.5*rank(-(close/open-1)) + 0.5*rank(ts_rank(operating_income/equity, 126))` |
| 质量组合 | `0.5*group_rank(ts_rank(oi/equity,126),subindustry) + 0.5*group_rank(ts_rank(est_eps/close,126),industry)` |

### 8.2 提交优先级

1. 高 Fitness（≥ 1.5）且低 TO（< 15%）
2. 来自不同信号簇
3. 若 SELF_CORRELATION 冲突，保留高 Fitness 版本

### 8.3 相关性的真相

对 ACTIVE alpha 的日收益做相关分析，发现：

- **同一信号簇内相关性极高**：
  - 两个 open-close 反转 + OI/Equity 混合（权重不同）日收益相关 **0.84**
  - 两个分析师 EPS 相关 **0.74**
  - 两个杠杆/质量因子（`-equity/assets` vs `liabilities/assets`）相关 **0.84**
- **跨簇也不一定能分散**：基于 `scl12_buzz` 的情绪 alpha 与基于 `est_eps/close` 的分析师 alpha 相关仍达 **0.59–0.67**。
- **累计 PnL 相关性严重失真**： alpha 的累计 PnL 两两相关普遍 **> 0.90**，容易让人误以为所有因子都一样。

**结论**：

- 换窗口、换权重、换 neutralization **不能创造真正的低相关**。
- 真正的低相关来自 **完全不同的数据来源或经济逻辑**（如：宏观事件、期权流、跨境、另类数据）。
- 在常规 USA TOP3000 基本面/价量/分析师池子里，"低相关" 往往是 **0.3–0.6 的日收益相关**，不要追求 0。
- ⚠️ **WQ 的 SELF_CORRELATION 检查用信号级相关（≈0.9+），不是日收益相关**。两个 alpha 若共享同一核心 `group_rank(...)` 信号（如 `0.6*sg + 0.4*OI` 与纯 `sg`），日收益相关可能只有 0.4–0.5，但信号级相关 0.93，提交必 FAIL（"above cutoff of 0.7 and Sharpe not better by 10%"）。**提交前必跑信号成分重叠护栏**（见 7.2/7.5），日收益相关只是 proxy。

---

## 9. 提交前 Checklist

- [ ] 已获取 **所有** alpha 列表（含 ACTIVE / UNSUBMITTED），不只是本次模拟
- [ ] 新因子与已有 ACTIVE alpha **日收益** 相关性 < 0.7（或新 Sharpe ≥ 旧 Sharpe × 1.1）
- [ ] 相关性基于 **日收益** 计算、**按日期交集对齐**，不是累计 PnL
- [ ] 字段已验证
- [ ] 若套用模板：模板信号字段与用户给定字段**同一 dataset**（4.1.1 硬门槛），不一致 = 混信号，已停止执行
- [ ] 模拟无报错；`checks` 里没有 `OLD_SIMULATION = FAIL`（否则先重模拟）
- [ ] Sharpe ≥ **1.58**（顾问 D1）/ ≥ **2.69**（顾问 D0），普通账号 ≥ 1.25
- [ ] Fitness ≥ **1.0**（顾问 D1）/ ≥ **1.5**（顾问 D0）
- [ ] Turnover 1%–70%（SuperAlpha 2%–40%）
- [ ] Drawdown < 15%
- [ ] `LOW_SHARPE` / `LOW_FITNESS` / `LOW_SUB_UNIVERSE_SHARPE` / `IS_LADDER_SHARPE` / `LOW_2Y_SHARPE` 全 PASS
- [ ] `CONCENTRATED_WEIGHT` PASS（单股 < 10%）
- [ ] 多空数量合理
- [ ] 提交后 **再次确认 status == ACTIVE**，201 不代表上线
- [ ] 检查 `SELF_CORRELATION` 与 `PROD_CORRELATION`（顾问）均未 FAIL

---

## 10. 核心经验（一句话版）

1. **先生成因子前先拉取所有 ACTIVE alpha 的 PnL**，避免高相关重复。
2. **相关性必须算日收益**，累计 PnL 相关会把所有因子看成同一个。
3. **201 响应 ≠ 提交成功**：提交后必须确认 `status == ACTIVE`。
4. **双腿混合 > 单腿**：`operating_income/equity`、`est_eps/close`、`free_cash_flow_reported_value/equity` 是最稳的**腿**，但单独用命中率只有 5.8%；两条正交腿相加的命中率 33.3%。单腿只作探索，不作交付形态。（2026-10-30 按 127 条历史库修正：原「基本面 > 混合 > 技术」的分类型排序误导，真正分层的维度是腿数，不是数据类型。）
5. **group_rank + ts_rank 是黄金组合**。
6. **SUBINDUSTRY 中性化通过率最高**。
7. **Decay 是控制换手的主杠杆**：基本面 0，技术 10–30。
8. **50/50 正交混合能降低换手，但未必能降低相关**；相关靠信号来源，不靠权重。
9. **字段先验证**，无效字段秒级报错。
10. **USA TOP3000 里真正的低相关很难做**；同一数据池的 "不同" 表达式往往高度相关。
11. **套模板先过数据集一致性门槛（4.1.1）**：模板信号字段与用户给定字段不同 dataset = 混信号，立即停止，不模拟不提交。
12. **阈值跟着账号走**：顾问账号 D1 要 Sharpe > 1.58（不是 1.25），并且多两道 `IS_LADDER_SHARPE` / `LOW_2Y_SHARPE`；低换手（TO<30%）能让 IS Ladder 的 PASS 阈值打 0.85 折。
13. **API 字段以 `OPTIONS /simulations` 为准**，文档正文可能是旧版（旧文档里的 `testPeriod`/`maxTrade` 已进 settings，而 `status` 在仿真进行中并不返回，只有 `progress`）。
14. **额度是最硬约束**：所有成功仿真都计数（含多仿真子任务、重跑同一 alpha），必须用 hash 缓存去重。
15. **Fitness 贴线时先换 neutralization，不要先动 decay**：`Fitness = Sharpe × √(Returns / max(TO, 0.125))`（已用 6 条真实仿真反算校准）。TO < 12.5% 时分母被地板锁死，降 TO 零收益；此时 SUBINDUSTRY→INDUSTRY 是性价比最高的一刀（实测 F 0.95→1.08）。decay 只在 TO 已 >12.5% 时才值得动。
16. **腿的独占性按「数据族」判，不按「字段名」判**：换期限（90/120/180/270）、换口径（call-put skew / mean_skew / pcr_oi）都逃不出同一族的 SELF_CORRELATION（实测与同族 alpha 相关仍 0.70–0.94）。要降相关就必须换到池内无人用的数据族。
17. **先清点存货，但别信存货的旧指标**：`scripts/template_hitrate.py --stock` 能免费列出历史库里「曾过门槛但仍 UNSUBMITTED」的 alpha（2026-10-30 实测 9 条），值得先扫一遍；但**这些指标只在仿真当时成立**。实测把这 9 条按原样重跑，平均 −0.42 Sharpe、**9/9 全灭**。所以存货的正确用法是：拿它的**表达式当新因子的候选骨架**，而不是当成能直接提交的资产；只要 `OLD_SIMULATION=FAIL`，重跑就是要花额度的，且大概率掉线（见 §12 2026-10-30 第二条）。

---

## 11. 自进化机制

每次与 BRAIN 交互（提交、查询、分析）后，AI 应把新发现写回本 SKILL，使其随实战经验持续进化。

### 11.1 触发条件

以下任一情况发生后，运行一次 `scripts/evolve_skill.py`：

- 提交了一个或多个新 alpha
- 批量回测了一批 alpha
- 查询了 alpha 状态并发现变化（如 UNSUBMITTED → ACTIVE，或被拒绝）
- 发现了新的字段可用性/失效模式

### 11.2 运行方式

**前提**：设置 `WQ_BRAIN_USERNAME` / `WQ_BRAIN_PASSWORD`，或在 skill 目录下放置未跟踪的 `credential.txt`，内容为 BRAIN 账号密码 JSON 数组：

```json
["your_username", "your_password"]
```

```bash
# 1. 预览：生成建议追加的 markdown 片段，不修改任何文件
python scripts/evolve_skill.py

# 2. 提交：追加到 SKILL.md 并更新 alpha_db.json
python scripts/evolve_skill.py --apply

# 首次全量快照时限制 PnL 抓取数量（默认 60，避免 500+ 次串行请求）
python scripts/evolve_skill.py --max-pnl-fetch 30
```

> 注意：**不带 `--apply` 的预览模式不会修改 `alpha_db.json` 和 `SKILL.md`**，你可以先审查再提交。脚本仅依赖 `requests` 和 `numpy`，**不需要 `wq-bus` 项目代码**。数据文件已随 SKILL 分发。
> `alpha_db.json` 现以 `[[date, value], ...]` 存 PnL；旧的纯 float 列表仍可读取（退化为按位置对齐）。

脚本会：

1. 拉取 `/users/self/alphas`（分页）获取全部 alpha。
2. 与本地 `alpha_db.json` 对比，找出 **新增** 或 **状态/指标变化** 的 alpha。
3. 对新 alpha 抓取 `recordsets/pnl`，计算与已有 ACTIVE alpha 的 **日收益相关性**。
4. 自动生成经验条目（指标评价 + 相关评价 + 表达式摘要）。
5. 第一次运行输出**批量快照**；后续运行输出**增量条目**。
6. `--apply` 模式下把条目追加到 `## 12. 实证记录（自动更新）`，并保存本地 `alpha_db.json`。

### 11.3 AI 应如何整理经验

脚本输出后，AI 需要**人工判断**哪些条目值得永久写入 SKILL：

- **保留**：高 Fitness 低换手的成功案例、新的低相关信号簇、意外的失败模式。
- **精简**：大量重复的同一信号簇条目应合并为一句话规律。
- **更新模板/阈值**：如果多次发现某个字段/模板失效，应回到第 4、5、6 节更新。

### 11.4 数据结构

- `alpha_db.json`：本地 alpha 快照库，包含状态、指标、表达式、PnL。该文件会包含个人研究记录，默认被 `.gitignore` 忽略，不应提交到公开仓库。
- `SKILL.md`：最终人类可读 playbook，第 12 节只保留脱敏后的通用经验。

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
