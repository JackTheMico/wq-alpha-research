---
name: wq-alpha-research
description: "Use for WorldQuant BRAIN alpha research: designing WQ Alpha expressions, selecting fields/operators, diagnosing simulation and IS check failures, tuning Sharpe/Fitness/Turnover, submitting alphas, and building low-correlation alpha portfolios. Covers the BRAIN HTTP API (auth, multi-simulation, rate limits, recordsets), consultant-tier submission thresholds, and the self-evolution loop. Also use for 中文 requests about WorldQuant、BRAIN、WQ Alpha、顾问权限、因子表达式、回测、提交、换手、Fitness、Sharpe。"
---

# WQ Alpha 研究 Skill

> 结构化 playbook：字段 → 表达式 → 回测 → 检查 → 提交 → 组合。融合 WorldQuant BRAIN 文档知识与 USA TOP3000 实证经验。

---

## ⚠️ 硬性声明：构造 alpha 前必须运行 recommend_fields.py

**任何 alpha 表达式的构造，第一步必须是运行 `recommend_fields.py` 获取低拥挤字段池。**

```bash
python scripts/recommend_fields.py --region <region> --universe <universe>
```

**原因**：直接使用常见高 alphaCount 字段（如 `operating_income/equity`、`est_eps`、`implied_volatility_*`）会导致 alpha 反复卡在 PROD_CORRELATION < 0.7 的闸门，浪费仿真额度。从低拥挤字段池中选择信号字段是从源头降低撞墙概率的唯一有效手段。

**规则**：
1. 信号字段必须从 `recommend_fields.py` 输出中选取
2. 每个信号字段必须能写出一句话经济学解释（`simulate_batch.py --field-rationale` 强制校验）
3. 仿真前 `simulate_batch.py` 会自动检查字段拥挤度，高 alphaCount 字段会被拒绝
4. 模板 A–G 中的示例字段仅演示语法，**直接使用会撞 PROD_CORRELATION**

详见 §4.2「低拥挤字段优先策略」。

---

## ⚠️ 硬性声明：提交需要显式授权，且每天最多 1 条

**未经用户在本轮对话中明确下达"提交"指令，禁止调用 `POST /alphas/{id}/submit`。**
"混出候选""跑仿真""看看能不能过线"都不构成提交授权；也**禁止用提交去探测 `PROD_CORRELATION`**（即便 403 不消耗配额）。

**每日提交配额（默认 1 条/天）**：

1. 每个自然日（`Asia/Shanghai`）**最多提交 1 条 alpha**。
2. **例外**：当**可提交候选池达到两位数（≥ 10 条）**时，解除 1 条/天限制。
   「可提交」口径 = 同时满足 `brain.gate_report(a, strict=True)` 为 True、`IS_LADDER_SHARPE` / `LOW_2Y_SHARPE` PASS、且与已 ACTIVE alpha 的日收益相关 < 0.7 的 `UNSUBMITTED` alpha。
3. **计数口径**：提交前先按 `dateSubmitted` 落在当天统计"今日已提交条数"，满额即停，不得跨日预支。
4. **交互要求**：每次提交前把候选清单（alpha_id / S / F / TO / 自相关）与"今日剩余额度"报给用户确认，提交后回报判定结果。

违反此条 = 越权操作，必须先回滚认知（说明已提交了什么）再继续。

---

## 1. 快速决策树

```
开始
  └── Step 0: 运行 recommend_fields.py 获取低拥挤字段池
              python scripts/recommend_fields.py --region <r> --universe <u>
              └── 从输出中按经济学维度选择信号字段
  ├── 拉取所有 alpha 列表 ──→ 只看 ACTIVE；算 **日收益** 相关，>0.7 则修改或放弃
  ├── 设计新因子
  │    ├── 字段已验证？ ──否──→ 查第 2 节（本地字段文件搜索 / 模拟 rank(field)）
  │    └── 是 ──→ 若套模板，先过 4.1.1 数据集一致性门槛
  │               （模板信号字段与用户字段同一 dataset，否则混信号 → 停止执行）
  │         ├── 基本面 ──→ group_rank + ts_rank, SUBINDUSTRY, decay=0
  │         ├── 分析师 ──→ group_rank + ts_rank, INDUSTRY/SUBINDUSTRY, decay=0–4
  │         ├── 技术 ────→ 高 decay(10–30) 或混合基本面降低换手
  │         └── 情绪 ────→ nanHandling=ON, 小窗口谨慎
  ├── 提交被拒 ──→ 看判定书
  │    ├── PROD_CORRELATION FAIL ──→ **换族混腿**（§8.4：扫全字段 → 单腿 FULL 排序
  │    │                               → 正交族权重 25%→35% sweep → 双筛 → 依次提交）
  │    │                              ⚠️ 改窗口/decay/同族字段名对 prod corr 无效
  │    ├── IS_LADDER_SHARPE FAIL ──→ 增大 decay（GBR 实测 d0/d3 FAIL、d5 PASS）
  │    └── SELF_CORRELATION FAIL ──→ 与已有 ACTIVE 的信号级重叠，换数据族
  └── 提交后 ──→ 验证 status == ACTIVE（要等 40–80 次 POST，§7.7.2 坑五）
```

**提交前必过 `preflight.py`（§9.1）——指标全绿不等于能提交。** 一次被拒的代价是
一次提交额度，而拒因（`IS_LADDER_SHARPE` 的 WARNING→FAIL、`PROD_CORRELATION` 只在提交时回算）
在仿真结果里看不出来。

**如果这条 alpha 的信号族已经在 §9.1 的"饱和族"名单里，别裸提交**——直接按 §8.4 混
≥35% 正交族再跑，能省掉 2–3 次提交配额。

---

## 2. 字段速查（本地数据集）

本 SKILL 已内置 USA TOP3000 delay=1 的完整字段列表（共 4367 个），无需每次从网页/ API 拉取：

- `references/fields_usa_top3000_delay1.json`：完整字段元数据数组
- `references/fields_index.json`：多区域快照索引
- `references/wq_usa_top3000_delay1_data_fields_summary.json`：分类统计与示例字段

> **首选方式**：直接运行 `recommend_fields.py` 获取按维度分组的低拥挤字段池，无需手动搜索。手动搜索仅用于补充验证。

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
data = json.loads((field_dir / "fields_usa_top3000_delay1.json").read_text(encoding="utf-8"))

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

> **默认按 alphaCount 升序排列**，优先查看低拥挤字段。

```python
category = "pv"  # 或 fundamental / analyst / news / option / model / socialmedia
fields = [f for f in data if f.get("category", {}).get("id") == category]
print(f"{category}: {len(fields)} fields")
# 按 alphaCount 升序（低拥挤优先）
for f in sorted(fields, key=lambda x: x.get("alphaCount", 0))[:10]:
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
| 提交确认 | 只看 201 | 反复 POST 至 403 判定书 / 201，再确认 `ACTIVE`（§7.7.2） |
| 提交闸门 | `gate_report` 放行 WARNING | `gate_report(strict=True)` + `scripts/preflight.py` 出 GO/NO-GO（§9） |
| 多仿真分批 | 跨 region 直接报错 | `run_many` 按 5 项不变项自动分组（§7.4） |
| 字段可用性 | 读顶层 `regions`（永远空） | `field_coverage()` / `field_regions()` / `fields_of_dataset()`（§7.10） |

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

1. 一批 2..10 个；**同批内 `type`/`instrumentType`/`region`/`delay`/`language` 必须一致**。
2. 报 `The simulation requires more resources than are available` 时，减小批内数量重试。
3. 每个子仿真都会计入当日额度——多仿真不省额度，只省你等的时间。

`brain.run_many(payloads, batch_size=8)` 已封装切片与串行，直接用即可。
**它会按上面那 5 项自动分组**：跨 region / 跨 delay 的 payload 混在一个 list 里也不会整批失败
（实测跨 region 混排会让整轮研究脚本在提交阶段 1 秒内死掉，白等一次），返回顺序与入参严格一致。
`universe` / `neutralization` / `decay` / `truncation` 同批可以不同 —— 所以一次多仿真就能扫完
"同区域 × 多宇宙 × 多 decay" 的参数网格。

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

> ⚠️ **提交前必须先过"显式授权 + 每日 1 条配额"**（见文首硬性声明）。
> 统一入口：`python scripts/submit_one.py <alpha_id> --do-submit [--pool-size N]`，
> 脚本内置当日配额校验（`dateSubmitted` 按 `Asia/Shanghai` 自然日计数），满额直接拒绝提交。
> **禁止**绕过该脚本直接 `POST /alphas/{id}/submit` 去探测相关性。

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
| 200 + `Retry-After` + 空 body | **还在算**（不是失败） | 按 `Retry-After` **反复 POST 同一端点**，实测约 38 次 / 90 秒出结果 |
| 201 | 请求被接受，**但不等于进了审核队列** | 核验 `dateSubmitted` 非 None 且 status 离开 `UNSUBMITTED` |
| 429 | 软限频 | 读 `Retry-After` 退避后重试 |
| 403 | **两类**：① 提交配额耗尽（硬封锁）；② **相关性/阶梯 FAIL 的判定书** | 先解析 body（见坑二），再决定是等配额还是换信号 |

**坑一：把"还在算"误判成"吞提交"（2026-11-03 修正）** — 提交计算期间 `POST /submit` 持续返回
`200 + Retry-After + 空 body + 无 Location`，此时 alpha 仍 `UNSUBMITTED`、`dateSubmitted=None`。
旧实现用固定间隔 `GET /alphas/{id}` 轮询 200 秒，超时后误报"201 吞提交"。
**正确做法是反复 POST same endpoint**；`GET /alphas/{id}/submit` 会一直返回同样的 200+Retry-After
（读不到结果），`POST /alphas/{id}/check` 是 405。`submit_verified(max_posts=100, max_wait=300)`
已按此重写，命中 403 立刻解析判定书。

**坑二：403 ≠ 一定是配额耗尽（2026-10-30 修正）** — 403 响应体形如 `{"is": {"checks": [...]}}`，是**提交时实时计算**的完整 IS checks。实测 `E560gqE1` 的 403 body 里：`PROD_CORRELATION FAIL value=0.8045 limit=0.7`、`SELF_CORRELATION PASS 0.6226`、`REGULAR_SUBMISSION PASS value=0 limit=4`——配额根本没用完，FAIL 的是生产池相关。

```python
from wq_api import submit_verdict
detail = submit_verdict(resp)   # "PROD_CORRELATION=0.8045(limit=0.7)" 或 ""（空=真配额耗尽）
```

FAIL 时这是**最可靠**的取值途径。`is.prodCorrelation` 在 ACTIVE alpha 上**多数时候**为 `0.0`（平台不回算，与 `POWER_POOL_CORRELATION` 同为僵尸字段），但**并非恒定**——2026-11-05 实测刚转 ACTIVE 的 `RREAx3Na` 上读到 `is.prodCorrelation = 0.6761`（PASS，limit 0.7）。所以：403 必须先解析 body，只有 body 里没有 FAIL 项时才是真的配额耗尽；ACTIVE 后可以顺手读一次 `is.prodCorrelation`，读到非 0 值就记下来当同族的经验基线，读到 0.0 就按"不可知"处理。

**坑三：`/alphas` 集合端点对部分账号返回 405** — 既不能 `GET` 枚举，也不能 `POST` 建 alpha；只能 `GET /alphas/{id}` 按 id 查。此时"提交前拉全部 alpha 算日收益相关"不可行，只能依赖信号成分重叠护栏 + BRAIN 自己的信号级相关性。`BrainSession.alphas()` 遇到 405 会抛错，请捕获后退化为按 id 查。

**坑四：PASS 时通常读不到 `PROD_CORRELATION`，但偶发可读（2026-11-04 / 2026-11-05 修正）** — 判定书只在
**FAIL** 时回传 `PROD_CORRELATION=0.7621(limit=0.7)`；PASS 转 `ACTIVE` 后 `is.prodCorrelation`
多数情况是 `0.0`，但 2026-11-05 的 `RREAx3Na` 上读到 **0.6761**。所以：
- **FAIL 数值**一定拿得到，可当进度条（0.7621 → 0.7510 → 0.7155）；
- **PASS 数值**属于"有时能读到"：读到就写进报告并作为同族基线，读到 `0.0` 就写"不可知"，别编数字；
- 别把 `0.0` 解释成"完全不相关"——它也可能只是平台没回算。

**坑五：成功提交的 POST 次数远多于失败（40–110+ 次）** — 2026-11-04 实测 `ZYQbbVnj`：
POST#1 起 201→200 交替、POST#11 后 `Retry-After` 变 `None`、一直到 POST#80 全部 `200`，
最后 `GET /alphas/{id}` 才显示 `status=ACTIVE, dateSubmitted=2026-11-04T03:47:19`。
2026-11-05 `RREAx3Na` 更长：`submit_one.py` 跑满 `max_posts=100`（182 秒）仍是
`200 + Retry-After=1.0`、`status=UNSUBMITTED`，接着**继续 POST 到第 10 次**（共约 110 次）才转 ACTIVE。
而 FAIL 的 alpha 通常在 1–3 次 POST 内就给 403。⇒ **`max_posts` 至少设 150**，
且循环内每 5–10 次 POST 顺手 `GET /alphas/{id}` 一次，见到 `ACTIVE`/`dateSubmitted` 立刻收工；
**跑满上限仍是 200 不代表失败**，重新发起一轮 POST 即可接着算（`submit_verified` 会从头计数）。

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

#### 7.9.1 搜官方文档 / 找「社区工具」时能到哪、到不了哪（2026-10-31 实测）

| 目标 | 可用通道 | 结论 |
|------|----------|------|
| 官方教程正文 | `GET /tutorial-pages/<id>` | ✅ 唯一可靠入口。教程目录用 `GET /tutorials?limit=60` 拿 `pages[].id`（别猜 id，猜的会 404） |
| 官方站内搜索 | `GET /search?query=` | ⚠️ 多实体返回：`reference` / `tutorialPage` / `video` / `recommendedReading` / `faq` / `event` / `message` / `competition`。**`message` 只索引官方 ANNOUNCEMENT，不含顾问论坛帖** |
| 顾问社区论坛（Zendesk） | `support.worldquantbrain.com` | ✅ **可读，见 7.9.1.1 的三步法**（当天早些时候误判为不可达，已修正） |
| 平台侧论坛 API | `/forum` `/forums` `/posts` `/threads` `/community` `/discussions` `/messages` | ❌ 全部 404。论坛**不在** `api.worldquantbrain.com` 上，只有一个 `/messages/<id>` 读**官方公告** |

#### 7.9.1.1 顾问论坛读取三步法（2026-10-31 打通，务必按此走）

论坛是独立 Zendesk（内部域 `worldquantbrain.zendesk.com`），Cloudflare + 登录双闸。三件事缺一不可：

```python
from curl_cffi import requests as creq            # 1) CF 必须用 TLS 指纹模拟，普通 requests/curl 一律 403
t = BrainSession().authenticate() ... cookie "t"   # 2) 平台 JWT（HS256，179 字符）
s = creq.Session(impersonate="chrome")             # 注意：impersonate 写 "chrome"（=最新版）才过；写 "chrome124" 反而 403
s.get("https://api.worldquantbrain.com/authentication/support",   # 3) 唯一的 SSO 换票端点
      params={"return_to": target_url}, cookies={"t": t})
```

- 第 3 步返回 302 → `worldquantbrain.zendesk.com/access/jwt?jwt=<另一个 JWT>` → `/access/return_to?challenge=…` → 目标页，全程自动，`s` 里落 `_zendesk_session` / `_zendesk_authenticated`。
- **权限**：这个 SSO 只给「当前登录账号本就能看」的内容，即顾问可见的中文专属论坛；非顾问账号预期拿不到。
- **别自己造 JWT**：直接拿平台 `t` 去打 `/access/jwt` 会报 `JWT signature invalid`（Zendesk 用另一把密钥签），必须走 `authentication/support` 让平台现签。
- **别用无头 chromium**：`--headless=new --dump-dom` 出来是空/白屏，CF 不放行；`agent-browser` 也卡在「请稍候…」。curl_cffi 才是正解。

拿到 session 后这几个端点全通（这才是论坛调研的主入口）：

| 端点 | 用途 |
|------|------|
| `GET /api/v2/community/posts/{id}.json` | 帖子正文（`details` 是 HTML，含 `<img src>` 图链）、`author_id`、票数、评论数 |
| `GET /api/v2/community/posts/{id}/comments.json` | 全部评论 |
| `GET /api/v2/help_center/community_posts/search.json?query=<词>` | **论坛全文搜索**（`count` 封顶 1000，返回按相关度；支持引号短语） |
| `GET /api/v2/help_center/articles/search.json?query=` | 官方文章搜索 |
| `GET /hc/zh-cn/profiles/{author_id}-{NAME}?filter_by=posts` | 用户主页：活动总数 / 发帖数 / 评论数 / 帖子列表（HTML，正则扒） |
| `GET /api/v2/users/{id}.json` | ❌ 403，用户资料要从 profile HTML 的 `<title>`（「XXX 的用户个人资料」）拿名字 |

⚠️ 两个坑：`/api/v2/community/posts.json` 的 `query` / `author_id` 参数**被忽略**，会返回全站最新 8858 条；要搜就用 `community_posts/search.json`。`/api/v2/search.json` 是 403（需 agent 权限）。

⇒ 结论：**论坛完全可读，别再退到公开镜像**。镜像（ima.qq.com AlphaNode、10100.com、公众号）只当交叉验证用。

#### 7.9.2 官方 `ace_lib.py` vs 社区 `machine_lib.py`（常被混为一谈）

| | 官方 ACE API Library | 社区 `machine_lib.py` |
|---|---|---|
| 出处 | Learn → `documentation-ace-api-library-gold`（lastModified 2026-09-18），附件在其内链的 support 文章 | 无官方出处；总与 `Alpha Machine.ipynb` 成对出现在各类 GitHub 挖矿仓库 |
| 文件 | `ace_lib.py` + `helpful_functions.py` + `how_to_use.ipynb` + `requirements.txt` | 单文件 `machine_lib.py` |
| 权限 | Gold 起可下（Expert/Master 另有版本页） | 无门槛，靠转载 |
| 分发 | support 站附件 | **不在 PyPI**（`/pypi/machine_lib/json` → 404） |
| 典型接口 | `login()`、`simulate_single_alpha()`、`get_datafields()`、`check_submission()` | `login()`、`simulate()`、`multi_simulate()`、`get_alphas()`、`check_submission()`、`set_alpha_properties()`、`ts_factory/group_factory/vector_factory` |
| 现状 | 官方维护 | 同步实现，无 `Retry-After` 感知；后继者是 PyPI `wqb`（`A better machine lib.`，`WQBSession(requests.Session)`，自称**兼容 machine_lib.py**，异步，官方 BRAINbot 推荐） |

**对本仓库的含义**：`scripts/wq_api.py` 已是这条技术路线上的第三代实现（`Retry-After` 轮询 + 多仿真 + 额度 + `SimulationCache` 去重 + 日期对齐相关性），**不需要引入 `machine_lib` 或 `wqb`**；但看别人的 `machine_lib` 脚本时，函数名与本仓库的对应关系是 `login()→BrainSession().authenticate()`、`simulate()→simulate_one()/run_many()`、`check_submission()→gate_report()`、`submit_alpha()→submit_verified()`。

#### 7.9.3 `cnhkmcp` 的客户端选择（2026-10 核实）

`cnhkmcp` 是**标准 stdio MCP server**（`command` + `args` + 包内 `user_config.json`），与 IDE 无绑定；2026 年 MCP 已是所有 AI IDE 的标配，所以「哪个 IDE 能用」的实质是「**哪个 IDE 的模型额度免费且够用**」。真正吃额度的是 `get_multisimulation_result` / `get_alpha_pnl` 返回的巨量 JSON。

| 客户端 | 形态 / 成本 | 免费档关键限制 |
|---|---|---|
| Google Antigravity（IDE / 2.0 / CLI） | macOS/Win/Linux，个人**免费公测**，内置 Gemini | 预览期额度，未公布收费方案 |
| Trae（TraeCode / TraeWork） | Win/macOS/Linux，免费档 | Auto 模式 only、5000 补全/月、约 500 积分/月 |
| VS Code + Cline | 扩展，Apache-2.0，免费 | BYOK 或 Ollama（可 $0） |
| VS Code / JetBrains + Kilo Code | 扩展 + CLI，免费开源（2026-04 重建于 OpenCode） | BYOK，零加价 |
| opencode | CLI/TUI，免费开源 | BYOK |
| Zed | 编辑器，开源免费 | AI 需 BYOK |
| Windsurf → **Devin Desktop**（Cognition 收购后改名） | Win/macOS/Linux | 免费档仅 light agent quota |
| Cursor Hobby | Win/macOS/Linux | 额度极小 |
| ~~Roo Code~~ | **2026-05-15 关停，仓库已归档**（推荐迁移到 Cline/Kilo） | — |

配置要点：`command` 用**装了 cnhkmcp 的那个 venv 的 python 绝对路径**，`args` 指向包内 `platform_functions.py`；包路径用 `python -c "import cnhkmcp,os;print(os.path.dirname(cnhkmcp.__file__))"` 查。远程 MCP 在多数客户端写 `url`，**Antigravity 例外，必须写 `serverUrl`**（写错不报错、只是加载不到工具）。前置依赖：Python ≥3.8、pandas、selenium、**本机 Chrome**（`search_forum_posts` 用）；wheel 约 79 MB。仓库 `github.com/cnhk/cnhkmcp` 已 404，只剩 PyPI 可装 —— 属于把平台账号密码交给第三方代码，自行评估。

### 7.10 字段可用性探测（区域 × 宇宙 × 拥挤度）

三个问题都有唯一可靠答案，别再靠猜：

```python
from wq_api import field_coverage, field_regions, field_availability, fields_of_dataset

# 1) 这个字段在哪些 region/universe/delay 能用？（元数据在 data[] 里，不在顶层）
field_coverage(brain, "star_val_sector_rank")

# 2) 平台到底有哪几个合法 region 代码？（没有 /regions 端点，只能这样反推）
field_regions(brain, ["returns", "mdl26_market_cap_u"])
# -> USA EUR ASI CHN KOR HKG GLB AMR IND GBR DEU ALL   （没有 "ARC"）

# 3) 某宇宙下的覆盖与拥挤度（alphaCount）
field_availability(brain, "star_val_sector_rank", region="EUR", universe="TOP2500", delay=1)

# 4) 某 dataset 下有哪些字段（**必须带 instrumentType=EQUITY**）
fields_of_dataset(brain, "model38", region="EUR", universe="TOP2500", delay=1)
```

三个已踩过的坑：

| 坑 | 症状 | 真相 |
|---|---|---|
| 读顶层 `regions` 属性 | 永远为空 ⇒ 误判"字段不可用" | 按 region 的条目在 `data[]` 数组里 |
| `GET /regions`、`GET /simulations/settings` | 404 | 平台没有区域枚举端点，只能用字段元数据反推 |
| `GET /data-fields?dataset.id=X` 漏 `instrumentType=EQUITY` | `400 Invalid query`（不是空数组） | 该参数是硬必填，漏了会误判成"数据集在本地域不可用" |
| `GET /data-fields&limit=200` | `400 Invalid query` | **`limit` 上限是 50**；必须用 `offset` 翻页（2026-11-04 实测） |
| 把响应当数组 | `TypeError` / 空 | 响应体是 `{"count": N, "results": [...]}`，翻页读 `results` |
| 用本地快照判断"字段不存在" | 误判，例如 EUR/TOP2500 快照 10,000 条里**完全没有 fundamental6** | 快照有 10,000 条上限且按某种顺序截断。**要确认某 dataset 在不在**，直接 `GET /data-fields?instrumentType=EQUITY&region=..&universe=..&delay=1&dataset.id=..&limit=50` 翻页查（2026-11-05 实测 EUR 的 fundamental6 有 279 条，只是没进快照） |

拥挤度（`alphaCount`）的用法见 §9.1——它是 `PROD_CORRELATION` 唯一可用的本地代理，
但**低 alphaCount 不等于有信号**（§10 第 21 条）。

#### 7.10.1 一次扫清某宇宙的全部字段（换族找腿的第一步）

不要逐个 `fields_of_dataset` 试探——直接拉整个宇宙的字段元数据成本地快照，
再在本地按 `dataset` / `category` / `type` / `coverage` / `alphaCount` 切。
**`scripts/field_snapshot.py` 已经封装好翻页**（`limit=50` + `instrumentType=EQUITY`，
落盘到 `references/fields_{region}_{universe}_delay{N}.json`）：

```python
from field_snapshot import load_snapshot, refresh_snapshot

fields = load_snapshot("GBR", "TOP700", 1, brain=brain)   # 有快照就读、没有就自动拉
# fields = refresh_snapshot(brain, "GBR", "TOP700", 1)   # 强制重拉（字段推进后）

from collections import Counter
print(len(fields), len({(f.get("dataset") or {}).get("id") for f in fields}))
```

按族分组 + 筛可混腿池：

```python
mat = [f for f in fields if f.get("type") == "MATRIX"]
usable = [
    f for f in mat
    if (f.get("coverage") or 0) >= 0.5
    and (f.get("alphaCount") or 9999) < 200
    and (f.get("dataset") or {}).get("id") != "analyst_revision_horizons"  # 排除当前族
]
for ds, n in Counter((f.get("dataset") or {}).get("id") for f in usable).most_common():
    print(f"{ds:30s} {n}")
```

GBR/TOP700/delay=1 实测：**10,000 字段 / 138 个 dataset / 6,094 个 MATRIX 字段**，
其中 `coverage ≥ 0.5 且 alphaCount < 200` 的 MATRIX 字段 **1,750 个**——可混的池子很大，
不要拿"没字段可换"当借口。

**筛候选腿的四个硬条件**（顺序照抄，能砍掉 90% 噪音）：

1. `type == "MATRIX"`（`VECTOR` 不能直接进 `rank()`/`ts_rank()`）
2. `coverage ≥ 0.5`（< 0.3 基本模拟不出来，0.3~0.5 是稀疏噪音）
3. `alphaCount < 500`（只在做拥挤度分级时用，**不是越冷越好**，§10 第 21 条）
4. `dataset.id` **不是你当前骨架的族**（同族换字段名不算换族，§10 第 16 条）

### 7.11 常见 API 错误

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

0. **先过配额**：默认每天只能提交 1 条；只有可提交候选池 ≥ 10 条时才允许同一天提交多条（见文首硬性声明与 §7.7）。
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

### 8.4 换族混腿：把 `PROD_CORRELATION` 从 0.76 打到 0.70 以下

> 2026-11-04，GBR/TOP700 价格反转骨架 `O0ANYnG1`，IS checks 全 PASS 但
> `PROD_CORRELATION 0.7621 / 0.7` 一次提交即 403，**1 次 POST 出结果、配额未消耗**。
> 该族（"GBR 大盘价格反转"）在全局生产池已拥挤，同族短周期反转参考值 **0.9673**。

#### 8.4.1 为什么只有"换族"有效

`PROD_CORRELATION` 是**按信号族（dataset × 经济逻辑）算的**，不是按你的数值相关性算的。
所以：

| 尝试过的动作 | 对 prod corr 的效果 |
|---|---|
| 换 `ts_rank` 窗口（22→126） | 0（只是 Sharpe 的杠杆） |
| 换 decay / neutralization / truncation | ≈ 0 |
| 同族换字段名（52 周高 → MA50 → 200 日均线） | ≈ 0（都是价格反转） |
| **加一条不同 dataset 的腿**（`pattern_scores`） | **唯一有效，且可量化** |

#### 8.4.2 五步 SOP

1. **扫全字段**（§7.10.1）：`type=MATRIX` + `coverage ≥ 0.5` + `alphaCount < 500` + 非同族。
2. **单腿 FULL 实测**（不是 QUICK，GBR 上 QUICK 系统性高 0.45，§5.1.4 ⑧）：
   跨族腿**不要求单腿强**，只要能"加进来不拖后腿"。本次 20 条跨族候选里
   只有 2 条单腿 S > 1.0（`pattern_scores` 的 `breakaway_gap_up_*`，S=1.11 / 1.05），
   其余多在 0.3–0.7，直接当独立 alpha 都是废的——但作为混腿素材完全够用。
3. **权重 sweep**：正交腿从 25% 起，按 5% 递增（25/30/35/40），价格腿按比例压缩。
4. **双筛**：`IS_LADDER_SHARPE` 的 value ≥ limit **且** gate（S>1.58 / F>1.0 / TO 1–70%）同时 PASS 才进提交池。
5. **按"预期 prod corr 最低"的顺序依次提交**，用 FAIL 数值当前进进度条。

#### 8.4.3 实测权重梯度（同一骨架，只动权重与正交腿窗口）

| Alpha | 表达式构成 | 价格族权重 | 正交腿 `ts_rank` 窗口 | FULL S | IS_LADDER | PROD_CORR |
|---|---|---:|---:|---:|---|---:|
| `O0ANYnG1` | 0.40 ftse + 0.30 52w + 0.30 MA50 | **100%** | — | 1.78 | PASS | **0.7621** |
| `kqNo1nE6` | 4 腿：0.30/0.225/0.225 + 0.25 ps2 | 75% | 126 | 1.78 | PASS 2.12/2.02 | **0.7510** |
| `omELnaov` | 0.40 ftse + 0.30 52w + 0.30 ps1 | 70% | 100 | 1.74 | PASS 1.81/1.75 | **0.7236** |
| `Xg9b7z7a` | 同上 | 70% | 60 | 1.82 | PASS 1.84/1.75 | **0.7232** |
| `JjeN5nrO` | 同上 | 70% | 126 | 1.73 | PASS 1.80/1.75 | **0.7184** |
| `mLomgpd5` | 同上 | 70% | 252 | 1.80 | PASS 2.09/2.02 | **0.7155** |
| `ZYQbbVnj` ✅ | 0.325 ftse + 0.325 52w + **0.35 ps1** | **65%** | 252 | 1.78 | PASS 2.07/2.02 | **PASS（<0.70）** |

读法：

- **权重→corr 是凸的（这是最反直觉的一条）**：100%→75% 只降 **0.0111**（几乎无效），
  75%→65% 却降 **0.0355**（真正起作用的正是这一段）。所以"混一点点"不是"不够"，
  而是**基本没用**；到 35% 正交重量才开始见效。
- 换算成斜率：有效区间内 **≈ −0.03 / 5 个百分点**（走廊值），别按线性外推。
- **正交腿的 `ts_rank` 窗口越长，prod corr 越低**（60/100/126/252 → 0.7232/0.7236/0.7184/0.7155），
  而 Sharpe 反而略升（1.73→1.80）。加长窗口 = 让这条腿更像"慢变量"，与价格反转的高频结构脱钩。
- **过线那一刻还压了最拥挤那条腿**：ftse 腿 0.40 → 0.325，同时 52 周腿 0.30 → 0.325。
  即在"总价格权重"之外，**单条最拥挤腿的权重也是一个旋钮**。

#### 8.4.4 双约束：65% 是唯一可行的一小段窗口

降价格权重既能降 corr，也会**直接打死 `IS_LADDER_SHARPE`**（顾问面板必查）：

| 价格族权重 | 65% | 60% | 55% | 50% |
|---|---:|---:|---:|---:|
| FULL S | 1.78 | 1.76 | 1.74 | 1.72 |
| IS_LADDER value / limit | **2.07 / 2.02 ✅** | 1.56 / 1.58 ❌ | 1.53 / 1.58 ❌ | 1.49 / 1.58 ❌ |

⇒ **`PROD_CORRELATION` 要 ≤ 0.70，`IS_LADDER_SHARPE` 要 ≥ 1.58，两者的可行交集只有 65%~70%**。
Sharpe 看起来只掉 0.06，但 ladder 是断崖式 FAIL——所以**不能靠继续压权重蒙过去**，
要么把正交腿本身做强（换更好的族/更好的算子），要么接受这一族暂时交不出去。

#### 8.4.5 反例：不是所有"非价格腿"都能混

同一骨架上换别的族，直接崩：

| 混入的族 | 结构 | FULL S | IS_LADDER | 判断 |
|---|---|---:|---|---|
| `pattern_scores`（ps1） | 0.325/0.325/0.35 | **1.78** | PASS | ✅ 唯一可用 |
| `model250`（ML 综合分）+ ps1 | 4 腿 0.25×4 | **0.72** | FAIL 0.08 | ❌ 灾难，ML 分与价格反转反向抵消 |
| 只留 1 条价格腿 + 2 条 pattern | 0.45/0.30/0.25 | 1.52 | FAIL 1.28 | ❌ 打散过头 |
| pattern 腿套 `group_rank` | 0.40/0.30/0.30 | 1.60 | FAIL 1.43 | ❌ 额外中性化吃掉信号 |
| 换 pattern 字段（`adaptive_similarity`） | 0.40/0.30/0.30 | 1.50 | FAIL 1.47 | ❌ 同族里也有强弱之分 |

⇒ 换族要**先用单腿 FULL 实测排座次**，再混；不要以为"只要不是价格的就行"。

#### 8.4.6 GBR/TOP700 可用族地图（138 个 dataset 里的关键几张）

| dataset | category | 可作混腿的字段 | 单腿 FULL S |
|---|---|---|---:|
| `analyst_revision_horizons` | model | `price_change_vs_ftse100_30d_*`、`pct_change_from_52week_high_long_term`、`pct_diff_*moving_average*` | 1.32–1.54 |
| **`pattern_scores`** | **pv** | `breakaway_gap_up_mean_simscore_lookback60`、`breakaway_gap_up_dynamic_simscore_lookback60` | **1.11 / 1.05** |
| `model250` | model | `mdl250_lmt_open_eq_score` | 0.46（混进去崩） |
| `model36` / `model53` | model | `credit_risk_leverage_score_d1`、`default_risk_*` | 0.3–0.7 |
| `model238` | model | `mdl238_region_owner_rank`、`mdl238_sector_rank` | 0.3–0.7 |
| `model109` | model | `debt_to_market_cap_ratio`、`float_turnover_ratio` | 0.3–0.7 |
| `shortinterest*` / `institutions*` / `insider_agg_matrix` | model | `mean_loan_rate`、`count_institutional_holders_security` 等 | 0.3–0.7 |
| `fundamental72` / `continuation_score` | fundamental / pv | 覆盖率不足，GBR 上多不可用 | — |

> 这张表只对 GBR/TOP700/delay=1 成立；换区域要重扫（§7.10.1）。

---

## 9. 提交硬闸门与 Checklist

### 9.0 先记住：指标全绿 ≠ 能提交

2026-11-03 实测（代价是 1 次提交额度）：一条 EUR alpha `Sharpe 1.80 / Fitness 1.26 / TO 16.02%`，
本地 `gate_report` 判定 True，提交仍被拒。原因是**三道本地看不见的闸门**：

| 闸门 | 仿真后看到的样子 | 提交时的真身 | 能否本地预判 |
|---|---|---|---|
| `IS_LADDER_SHARPE` | `WARNING 0.88 / 1.58` | **`FAIL 0.88 / 1.58`** | 能——按 value<limit 一律当 FAIL |
| `PROD_CORRELATION` | `PENDING`（无值） | `FAIL 0.8314 / 0.7` | 不能——只能用**拥挤度先验**估风险 |
| `REGULAR_SUBMISSION` | `PENDING` | PASS 0 / 4（消耗配额） | 不能——只能记账 |

⇒ **`gate_report` 返回 True 只是必要条件。** 顺序应该是：`preflight.py` 判 GO → 再花额度。

### 9.1 一条命令：`scripts/preflight.py`

```bash
# 判定若干候选（联网，会查拥挤度先验）
python scripts/preflight.py RREmY1Qe KPJG6Jwj

# 从研究结果批量判定
python scripts/preflight.py --from-json .workbuddy/eur_mine3.json

# 机器可读 / 跳过拥挤度查询
python scripts/preflight.py RREmY1Qe --json --skip-crowding
```

退出码 `0` = 至少一个 GO，`1` = 全部 NO-GO。判定口径：

| 项 | 口径 |
|---|---|
| Sharpe / Fitness / Turnover | 按账号权限取阈值（顾问 D1 为 1.58 / 1.0 / 1%–70%） |
| `IS_LADDER_SHARPE` / `LOW_2Y_SHARPE` | **WARNING 且 value < limit ⇒ 阻断**（不信 WARNING） |
| `LOW_SUB_UNIVERSE_SHARPE` / `CONCENTRATED_WEIGHT` / `OLD_SIMULATION` | FAIL/ERROR ⇒ 阻断 |
| `SELF_/PROD_/POWER_POOL_CORRELATION` | 恒 PENDING ⇒ 只作提示，绝不当作 0 |
| 拥挤度先验 | 信号字段 alphaCount ≥ 5000 ⇒ 阻断；1000–4999 ⇒ 提示；< 1000 ⇒ 提示"冷门≠有效" |

**拥挤度先验的标定**（同一字段 `star_val_sector_rank`，同一账户）：
`EUR/TOP2500 alphaCount=19,800` → `PROD_CORRELATION 0.8314` FAIL；
`AMR/TOP600 alphaCount=256` → 未触及相关性闸门。所以它是风险分级，不是概率预测。

> 已知其他族的 prod corr 实测值：EBITDA/EV **0.7785**、短周期反转 **0.9673**、
> `vector_neut(估值, 市值delta)` **0.8314**、GBR 大盘价格反转（ftse100 相对 + 52 周高 + MA50）**0.7621**。
> 这几族在全局池已饱和，别再投裸版本；要用就先按 §8.4 混进 ≥35% 的正交族重量。

### 9.2 Checklist

**Step 1 — 硬闸门（不过就别提交）**

- [ ] `python scripts/preflight.py <alpha_id>` 返回 **GO**
- [ ] `IS_LADDER_SHARPE` / `LOW_2Y_SHARPE` 的 value ≥ limit（**不看 result 标签，看数值**）
- [ ] 信号字段所在宇宙的 alphaCount < 5000（否则 prod corr 大概率 > 0.7）
- [ ] 信号族不在 §9.1 的"饱和族"名单里；**若在，先按 §8.4 混 ≥35% 正交族**，否则 403 是必然

**Step 2 — 构造与仿真**

- [ ] 已运行 `recommend_fields.py`，信号字段从低拥挤字段池中选取
- [ ] 每个信号字段已写出一句话经济学解释（`--field-rationale`）
- [ ] `simulate_batch.py` 静态检查通过（无高 alphaCount 字段、无 ACTIVE 池已用字段）
- [ ] 若套用模板：模板信号字段与用户给定字段**同一 dataset**（4.1.1 硬门槛）
- [ ] `checks` 里没有 `OLD_SIMULATION = FAIL`（否则先重模拟；实测存货重跑 9/9 全灭）
- [ ] `CONCENTRATED_WEIGHT` PASS（单股 < 10%），多空数量合理
- [ ] Drawdown < 15%

**Step 3 — 提交与确认**

- [ ] 已获取**所有** alpha（含 ACTIVE / UNSUBMITTED），而非只有本次模拟
- [ ] 新因子与已有 ACTIVE alpha **日收益**相关性 < 0.7（按日期交集对齐，不是累计 PnL）
- [ ] 提交用 `submit_verified()`（内部反复 POST，成功路径要 40–80 次，见 §7.7.2 坑五；`max_posts ≥ 60`）
- [ ] 提交后 **再次确认 `status == ACTIVE`**，201/200 都不代表上线
- [ ] 若被 `PROD_CORRELATION` 拦，**记下 FAIL 数值**当下一轮的进度条（0.7621→0.7510→0.7155 是实测梯度），换族混腿后再提

---

## 10. 核心经验（一句话版）

1. **先生成因子前先拉取所有 ACTIVE alpha 的 PnL**，避免高相关重复。
2. **相关性必须算日收益**，累计 PnL 相关会把所有因子看成同一个。
3. **201 响应 ≠ 提交成功**：提交后必须确认 `status == ACTIVE`。
4. **双腿混合 > 单腿**：`operating_income/equity`、`est_eps/close`、`free_cash_flow_reported_value/equity` 是最稳的**腿**，但单独用命中率只有 5.8%；两条正交腿相加的命中率 33.3%。单腿只作探索，不作交付形态。（2026-10-30 按 127 条历史库修正：原「基本面 > 混合 > 技术」的分类型排序误导，真正分层的维度是腿数，不是数据类型。）
5. **group_rank + ts_rank 是黄金组合**。
6. **SUBINDUSTRY 中性化通过率最高**。
7. **Decay 是控制换手的主杠杆**：基本面 0，技术 10–30。
8. **50/50 正交混合能降低换手，但未必能降低相关**。要分两种相关看：**`SELF_CORRELATION` 是同族内信号级相关，权重与窗口基本无效，只能换族**；**`PROD_CORRELATION` 是跨族池相关，正交族权重反而是有刻度的旋钮**（每 5% ≈ −0.03，§8.4.3）。
9. **字段先验证**，无效字段秒级报错。
10. **USA TOP3000 里真正的低相关很难做**；同一数据池的 "不同" 表达式往往高度相关。
11. **套模板先过数据集一致性门槛（4.1.1）**：模板信号字段与用户给定字段不同 dataset = 混信号，立即停止，不模拟不提交。
12. **阈值跟着账号走**：顾问账号 D1 要 Sharpe > 1.58（不是 1.25），并且多两道 `IS_LADDER_SHARPE` / `LOW_2Y_SHARPE`；低换手（TO<30%）能让 IS Ladder 的 PASS 阈值打 0.85 折。
13. **API 字段以 `OPTIONS /simulations` 为准**，文档正文可能是旧版（旧文档里的 `testPeriod`/`maxTrade` 已进 settings，而 `status` 在仿真进行中并不返回，只有 `progress`）。
14. **额度是最硬约束**：所有成功仿真都计数（含多仿真子任务、重跑同一 alpha），必须用 hash 缓存去重。
15. **Fitness 贴线时先换 neutralization，不要先动 decay**：`Fitness = Sharpe × √(Returns / max(TO, 0.125))`（已用 6 条真实仿真反算校准）。TO < 12.5% 时分母被地板锁死，降 TO 零收益；此时 SUBINDUSTRY→INDUSTRY 是性价比最高的一刀（实测 F 0.95→1.08）。decay 只在 TO 已 >12.5% 时才值得动。
16. **腿的独占性按「数据族」判，不按「字段名」判**：换期限（90/120/180/270）、换口径（call-put skew / mean_skew / pcr_oi）都逃不出同一族的 SELF_CORRELATION（实测与同族 alpha 相关仍 0.70–0.94）。要降相关就必须换到池内无人用的数据族。
17. **先清点存货，但别信存货的旧指标**：`scripts/template_hitrate.py --stock` 能免费列出历史库里「曾过门槛但仍 UNSUBMITTED」的 alpha（2026-10-30 实测 9 条），值得先扫一遍；但**这些指标只在仿真当时成立**。实测把这 9 条按原样重跑，平均 −0.42 Sharpe、**9/9 全灭**。所以存货的正确用法是：拿它的**表达式当新因子的候选骨架**，而不是当成能直接提交的资产；只要 `OLD_SIMULATION=FAIL`，重跑就是要花额度的，且大概率掉线（见 §12 2026-10-30 第二条）。
18. **`WARNING` 在提交时会被重新裁定为 `FAIL`**：`IS_LADDER_SHARPE` 仿真后是 WARNING 0.88/1.58，提交判定书里是 FAIL 0.88/1.58 —— 同一组 value/limit，两种裁定。所以**看数值，不看 result 标签**（§9.0）。
19. **降换手要"只钝化对冲腿，不动主信号"**：对市值 delta 中性腿套 `ts_mean(...,10)`（TO 26.3%→15.7%、Fitness 0.78→0.98），再收窄主信号窗口（`ts_arg_min` 120→60，Sharpe 1.51→1.85）。反过来，提高 decay 降 TO 会同步杀 Sharpe（d5→d10：TO 26%→15% 但 S 1.64→1.31）——说明信号衰减快，平滑信号本身就是伤害。
20. **`hump()` 会杀死 rank 化信号**：`hump(alpha, 0.01)` 把 TO 压到 0.8% 的同时把 Sharpe 从 1.64 打到 0.08。rank 后的数值量级太小，阈值吞掉了几乎全部调仓。压换手不要用它。
21. **冷门 ≠ 有效，拥挤 ≠ 无效**：同一字段在 AMR/TOP600（256 个 alpha）Sharpe 0.68、EUR/TOP800（239 个）0.59，而在**很拥挤**的 EUR/TOP2500（19,800 个）有 1.64。冷门字段要配大宇宙才活；相关性风险留给公式形态去化解，不能靠缩宇宙。
22. **多仿真按 5 项不变项分组**：`type/instrumentType/region/delay/language` 不同的 payload 不能同批，跨 region 混排会让整轮脚本在提交阶段 1 秒内死掉。`run_many` 已自动分桶，返回顺序仍与入参一致。
23. **有些算子在某些区域根本不存在**：`ts_decay_exp_window`、`group_median` 在 GLB 不可用（unknown/inaccessible operator）。社区模板照抄前先用 QUICK 模式验证算子栈，别用 FULL 额度试错。
24. **`PROD_CORRELATION` 是族级判定，不是数值相关性**：换窗口/换 decay/换同族字段名对它几乎没有影响；**唯一有效旋钮是「不同 dataset 的正交腿权重」**（完整 SOP 见 §8.4）。
25. **同族权重与 prod corr 的映射是凸的**：100%→75% 只降 0.0111，75%→65% 降 0.0355。⇒"混一点点"基本无效，**要到 ≈35% 的正交重量才开始见效**；只在线性区段可近似 −0.03 / 5 个百分点。完整梯度见 §8.4.3。
26. **降权重会同步打死 `IS_LADDER_SHARPE`，且是断崖式的**：65% 时 2.07/2.02 PASS，60% 时 1.56/1.58 FAIL，而 Sharpe 只从 1.78 掉到 1.76。⇒ prod corr 与 ladder 的可行交集很窄，别指望一路压权重压到过线（§8.4.4）。
27. **正交腿的 `ts_rank` 窗口越长，prod corr 越低、Sharpe 反而略升**：60/126/252 → 0.7232/0.7184/0.7155（S 1.82/1.73/1.80）。慢变量更能与高频价格结构脱钩——这是免费的一刀。
28. **跨族腿不要求单腿强**：20 条跨族候选里只有 2 条单腿 FULL S > 1.0，其余 0.3–0.7，但当混腿素材完全够用。**反过来，强腿不一定能混**：`model250` 的 ML 综合分（单腿 0.46）混进 4 腿骨架把 Sharpe 从 1.78 砸到 0.72。
29. **成功提交的 POST 次数是失败的 20–80 倍**：FAIL 通常 1–3 次 POST 就给 403；成功要 40–80 次 200 才转 `ACTIVE`。`max_posts ≥ 60`，且循环内每 5–10 次查一次 `GET /alphas/{id}`，见 `ACTIVE` 立刻收工（§7.7.2 坑五）。
30. **PASS 之后永远读不到 prod corr 的数值**：判定书只在 FAIL 时回传数字，ACTIVE 上 `is.prodCorrelation` 恒 0.0。报告里只能写"已过线"，不能写具体值（§7.7.2 坑四）。

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
- `SKILL.md`：最终人类可读 playbook；第 12 节只留决策级结论索引，完整实验记录在 `references/empirical-log.md`。

## 12. 实证记录（已迁至 references/empirical-log.md）

完整记录（含原始指标表与推理链）见 `references/empirical-log.md`。
这里只留**决策级结论**——做判断时看这一页就够，要追溯证据再翻文件。

| 日期 | 实验 | 一句话结论 |
|---|---|---|
| 2026-08-13 | cap 回归中性化模板挖掘（YPvlEl0l 提交 ACTIVE） | `bucket(cap)` 回归中性化可产出 ACTIVE；模板能复用，但字段要换族 |
| 2026-08-13 | bucket(cap) × 期权 breakeven × OI 模板挖掘（GrGmXvwx 提交 ACTIVE） | 期权 breakeven × OI 组合可提交；单腿期权数据命中率极低 |
| 2026-08-16 | mdl77_2gdna_actrtn12m × ROE × 资产负债率（VkGQxanA / QPGRvdV5 提交 ACTIVE） | 双基本面腿（ROE × 资产负债率）稳，但同族复用会撞 SELF_CORRELATION |
| 2026-10-29 | 按最新官方文档对齐 API 层（顾问权限） | `OPTIONS /simulations` 才是 settings 权威来源；文档正文会过期 |
| 2026-10-29 | 内置模板 A–F 首次全量实测（顾问账号 USA TOP3000 D1） | 模板本身不保证过线；数据集一致性优先于模板美观 |
| 2026-10-30 | 历史库反查：哪个模板最容易产出可提交 alpha（127 条样本统计，零仿真消耗） | **腿数**才是分层维度，不是数据类型；单腿命中率 5.8%、双腿 33% |
| 2026-10-30 | 存货重跑反证：9 条已过线存货全部掉线（消耗 9 次仿真） | `OLD_SIMULATION=FAIL` 的存货重跑 9/9 全灭（平均 −0.42 Sharpe），存货只能当骨架 |
| 2026-10-30 | 门槛核对：数值未提高，但发现 Power Pool 低门槛通道 | 数值门槛没变；发现 Power Pool 低门槛通道（Sharpe ≥ 1.0） |
| 2026-10-30 | IV skew × ROE（模板 G）优化：Fitness 解法与「换字段」的边界 | Fitness 贴线时先换 neutralization，别先动 decay |
| 2026-10-30 | 提交 E560gqE1 失败：PROD_CORRELATION 0.8045 硬否决，以及「403 响应体才是判定书」 | **403 响应体才是判定书**；本地护栏对 prod corr 无预测力 |
| 2026-10-30 | 换数据源两轮 20 次仿真：0/20，以及「冷门字段」假说的破产 | 20 次仿真 0 命中；「冷门字段 = 好机会」是伪命题 |
| 2026-10-31 | 豁免路径实跑：本账户已饱和，IS 与相关性互斥 | 本账户在已知数据族已饱和：IS 与相关性互斥，无法同时满足 |
| 2026-10-31 | Power Pool 形状的结构性洞察：(A−B)/mean(A,B) 是 ≤3 字段下的唯一高 Sharpe 结构 | `(A−B)/mean(A,B)` 是 ≤3 字段下唯一高 Sharpe 结构 |
| 2026-11-03 | 社区 ARC/GLB 模板复现：GLB 结构性不可达，EUR 打通后被 PROD_CORRELATION 否决（7 批 47 次仿真） | GLB 的 EMEA 门槛不可达（13 次最高 0.77）；EUR 靠"平滑对冲腿 + 收窄窗口"打通，但 ladder 0.88 与 prod corr 0.8314 双双 FAIL |
| 2026-11-04 | GBR/TOP700 价格反转族改造：`ts_rank` 窗口 22→126 是决定性杠杆，加 52 周高/均线相对腿（alphaCount 9–50）后 S 0.82→1.78 | 窗口长度比 decay 重要得多；**GBR 大盘是反 52 周高点**（该腿须反号）；QUICK 的 Sharpe 在 GBR 系统性高估 0.45，定稿必须 FULL |
| 2026-11-04 | `PROD_CORRELATION 0.7621` 被拒后换族混腿：三族 20 条单腿实测 + 权重 sweep，最终 65% 价格族 + 35% `pattern_scores` → **`ZYQbbVnj` ACTIVE**（S 1.78 / F 1.51 / ladder 2.07） | **prod corr 是族级判定，唯一旋钮是正交族权重（每 5% ≈ −0.03）**；65% 是 `PROD_CORRELATION ≤ 0.70` 与 `IS_LADDER ≥ 1.58` 的唯一交集；正交腿 `ts_rank` 窗口越长 corr 越低且 Sharpe 不降 |
| 2026-11-05 | `fnd6_miisa`（少数股东损益）跨数据集混腿：单腿最好 0.88，4 腿混合 `RREAx3Na` 提交 **ACTIVE**（S 2.24 / F 1.14 / TO 33%，prod corr **0.6761**） | **USA 无 `fnd6_miisa`，只能跑 EUR/ASI/CHN/GBR/DEU**；EUR 的 fundamental6 只剩 NCI 一支，分母必须借 fundamental23（`equity_to_equityholders`）；该混合对 decay 敏感（d10→d6 时 S 1.75→2.24、ladder FAIL→PASS），`ts_backfill(...,60)` 可白赚 0.07 Sharpe |
