<!-- 路由器：本文件只保留决策所需的常驻规则。细节在 references/，按需读一个文件即可。 -->

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

## 0. 路由表（先看这里）

| 你要做什么 | 去哪 |
|---|---|
| 查「这个族/字段试过没」 | `python scripts/redflag.py <关键词>`（账本 `references/ledger.md`） |
| 找社区模板 / 论坛方法 | `python scripts/kb.py search <关键词>` / `kb.py templates` |
| 扫新族、单腿排序、混腿 SOP | 本文件 §8.4 |
| 某条 IS 检查 FAIL 不懂含义 | `references/checks.md` |
| 写 API 调用 / 分页 / 轮询 | `references/api.md` |
| 套模板、要模板全文、一致性门槛代码 | `references/templates-core.md` |
| 提交前逐项自检 | 本文件 §9 |
| 历史实证与推理过程 | `references/empirical-log.md`（叙述；结论查 ledger） |

## 1. 快速决策树

```
开始
  └── Step 0: 运行 recommend_fields.py 获取低拥挤字段池
              python scripts/recommend_fields.py --region <r> --universe <u>
              └── 从输出中按经济学维度选择信号字段
  ├── 拉取所有 alpha 列表 ──→ 只看 ACTIVE；算 **日收益** 相关，>0.7 则修改或放弃
  ├── 设计新因子
  │    ├── **Step 0.5: 先查结论账本** ──→ python scripts/redflag.py <字段或 dataset>
  │    │                                命中 CLOSED/BLOCKED（退出码 1）→ 换族，别重烧
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

> **正文已迁至 [`references/templates-core.md`](references/templates-core.md)**（286 行，按需读）。
> 什么时候读：要套现成模板 / 想复用别人的结构 / 需要 4.1.1 数据集一致性门槛的判定代码 / 查社区模板检索方式。

子节目录：
  - 4.1 高胜率模板
  - 4.1.1 数据集一致性硬门槛（套模板前强制，先于一切构造）
  - 4.1.2 模板库（已标注 dataset）
  - 4.1.3 历史库命中率（2026-10-30 统计，alpha_db.json 127 条，顾问门槛口径）
  - 4.2 低拥挤字段优先策略
  - 4.2.1 字段拥挤度分层
  - 4.2.2 三道筛选闸门（`recommend_fields.py` 自动执行）
  - 4.2.3 11 个经济学维度
  - 4.2.4 强制在线模式
  - 4.2.5 仿真前静态检查
  - 4.2.6 快照有效期
  - 4.3 推荐默认设置
  - 4.4 少数股东损益族（`fnd6_miisa`）：可用性与已验证结构（2026-11-05）

## 5. 指标与检查

> **正文已迁至 [`references/checks.md`](references/checks.md)**（450 行，按需读）。
> 什么时候读：某条 IS 检查项报警，需要知道含义与阈值（如 LOW_2Y_SHARPE、IS_LADDER_SHARPE、LOW_ROBUST_UNIVERSE_SHARPE）。

子节目录：
  - 5.1 核心指标
  - Fitness 公式的两个实战推论（2026-10-30 实测校准，重要）
  - 5.1.1 提交阈值：顾问账号 vs 普通账号（易踩坑）
  - 5.1.2 Power Pool Alphas（低 Sharpe 通道，Sharpe ≥ 1.0 即可）
  - 5.1.3 PP 候选的构造准则：(A − B) / mean(A, B) 结构
  - 5.1.4 PP 提交机制实测：`POWER_POOL` tag 怎么打、缺什么会退回常规通道
  - 5.1.5 PP 的真正开关是「活跃 theme 的作用域」——本账户为 GLB/D1
  - 5.2 IS 检查清单（真实 check 名称，2026-09 顾问面板实测）
  - 5.2.1 IS Sharpe Ladder（D1）
  - 5.3 失败统计

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

> **正文已迁至 [`references/api.md`](references/api.md)**（573 行，按需读）。
> 什么时候读：要写 BRAIN API 调用：认证、字段分页、仿真轮询、批量提交、缓存、错误码。

子节目录：
  - 7.0 只保留一套实现：`scripts/wq_api.py`
  - 7.1 认证与权限
  - 7.2 获取已提交 Alpha 并计算相关性（双层护栏）
  - 7.3 仿真提交（settings 权威字段）
  - 7.4 多仿真（MULTI_SIMULATION）
  - 7.5 每日额度与限流
  - 7.6 记录集（recordsets）
  - 7.7 提交与二次确认
  - 7.7.1 相关性数值的两个位置（读错就会以为"平台不暴露"）
  - 7.7.2 提交配额：201 吞提交 vs 403 硬封锁
  - 7.8 重复仿真去重（省额度）
  - 7.9 拉取最新官方文档（保持同步）
  - 7.9.1 搜官方文档 / 找「社区工具」时能到哪、到不了哪（2026-10-31 实测）
  - 7.9.1.1 顾问论坛读取三步法（2026-10-31 打通，务必按此走）
  - 7.9.2 官方 `ace_lib.py` vs 社区 `machine_lib.py`（常被混为一谈）
  - 7.9.3 `cnhkmcp` 的客户端选择（2026-10 核实）
  - 7.10 字段可用性探测（区域 × 宇宙 × 拥挤度）
  - 7.10.1 一次扫清某宇宙的全部字段（换族找腿的第一步）
  - 7.11 常见 API 错误

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
- ⚠️ **这条斜率只对「拥挤源是价格族」的骨架成立（2026-11-06 反证）**：当拥挤源是 `fundamental23`
  （OCF/资产）或 `pv1` 252 日反转、且两者同时在场时，改任一腿的权重对 prod corr **几乎无效**
  （35%→30% 反而 +0.0025，→25% 只降 0.008，见 §12 2026-11-06）。此时唯一有效动作是**换掉拥挤族本身**，
  不是调权重。
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

#### 8.4.7 USA 基本面/估值族：prod corr 恒 ≈0.82，族内换腿无效（2026-11-07）

`free_cash_flow_to_enterprise_value`（model109，alphaCount 6）在 USA/TOP3000 上做了
一整套"换族混腿"，**三次判定书全部卡在 prod corr 0.8 量级，且与本地日收益相关完全脱节**：

| 结构（FCF 变化率 / 第二腿 / 反转） | S | 本地最高日相关 | PROD 实测 |
|---|---:|---:|---:|
| .40 水平 + .40 反转252 + .20 反转63 | 2.07 | **0.611** | **0.8751** |
| .40 变化率 + .40 毛利/总资产 + .20 反转 | 1.76 | **0.628** | **0.847** |
| .30 变化率 + .30 FCF/权益 + .20 FCF率 + .20 反转 | 1.86 | **0.657** | **0.8157** |

- **本地 proxy 低估 prod 0.15–0.26**：本地 0.61–0.66 对应 prod 0.82–0.88。凡属
  fundamental / model 估值族，提交前**默认 prod ≈ 0.82**，不要拿日收益相关当乐观依据。
- **换腿会换掉"本地最相关对象"却不换 prod 族**：反转 60% → 毛利/资产 40% → 全 FCF 族腿，
  每次 top-1 相关对象都变了（pwN5e7KX→9q7nYrZe→…），prod 仍锁在 0.81–0.88。
  ⇒ 基本面内部再正交也没用，必须引入**非基本面腿**（期权/新闻/情绪/价量结构）。
- **SELF 与 PROD 的分工**：SELF 由自建池决定（本账户 ROE 8 条、`est_eps/close` 2 条，
  故 ROE/毛利率/现金流变化腿会把 SELF 顶到 0.70–0.77）；PROD 由全站生产池决定。
  一轮内同族 ≥2 次 403 即停手，不再换权重。

#### 8.4.8 换区域：只有 GLB 成立，COUNTRY 中性化修好 EMEA；但反转腿是 prod 拥挤源（2026-11-07）

字段 `free_cash_flow_to_enterprise_value` 在 USA 之外仅 HKG/TOP800、KOR/TOP600、GLB/TOP3000、
GBR/TOP700、DEU/TOP500 可用（EUR/ASI/CHN/AMR/IND 不存在）。单腿 FULL 实测：HKG/GBR/DEU 全废
（|S| ≤ 0.87 且方向混乱）、KOR 混合最高 1.28/F 0.70、**只有 GLB 的 `CHG126 + REV252` 混合过线**。

**关键一刀：GLB 用 `COUNTRY` 中性化把 EMEA 从 0.70 拉到 1.38**（同骨架 SUBINDUSTRY 下
EMEA 0.70 / AMER 1.31 / APAC 1.56；COUNTRY 下 1.38 / 1.40 / 1.59，S 2.23 / F 1.07、ladder PASS）。
SECTOR（EMEA 0.63）与 INDUSTRY（0.67）均无效。⇒ 「GLB 三子区不可达」的旧结论只对 SUBINDUSTRY 成立，
**去国家 beta 是有效手段**；判断 GLB 候选必须先跑 COUNTRY。

`MINVOL10M` 比 `TOP3000` 更强、EMEA 余量更大（同骨架 S 2.31 / F 1.37 / EMEA 1.49）。

**但本轮两次 403 揭示了 prod 的真实拥挤源是反转腿，不是 FCF/EV**：

| alpha | universe | FCF / REV 权重 | S | F | TO | 本地SELF | PROD 实测 |
|---|---|---:|---:|---:|---:|---:|---:|
| `P0o861Xw` | TOP3000 | 60% / 40% | 2.09 | 1.09 | 24.2% | 0.56 | **0.7903** |
| `rKRVobb3` | MINVOL10M | 40% / 60% | 2.68 | 1.31 | 44.4% | 0.59 | **0.829** |

⇒ **反转权重 ↑ 20% → prod ↑ 0.039**。按此外推，要压到 0.70 需 FCF 权重接近 100%，
而纯 FCF 腿只有 1.2–1.6 Sharpe，不可行。GLB 的可提交候选（`O0AVoLa1` S 2.31/F 1.37/EMEA 1.49、
`Xg9ep9Q1` S 2.52/F 1.35）都属同一族，**不要再提交**。

GLB 无可用第三正交族（全部单腿 FULL，COUNTRY/d4）：分析师修正幅度 0.40/−0.28/0.04/0.10、
`sentiment22` 情绪净值 −0.18（TO 102%）、`fundamental44` fscore −0.43 / mscore −0.36 / accruals −0.44、
`model28` distance-to-default −0.26、机构净买入 0.32、机构持仓比 0.10。冷门 ≠ 有效再次成立。

规则：GLB 候选一律先试 COUNTRY；含 ≥40% `ts_rank(returns,252)` 的骨架默认 prod ≈ 0.79–0.83，不提交。

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
> `vector_neut(估值, 市值delta)` **0.8314**、GBR 大盘价格反转（ftse100 相对 + 52 周高 + MA50）**0.7621**、
> USA/TOP3000「`ts_rank(operating_cash_flow/assets_total_2,504)` + analyst83 会议出席 + 252 日反转」
> 三腿混合 **0.7588**（权重 35/30/35，d10；改成 30/35/30 与 40/35/25 均不改善）、
> ASI/MINVOL10M「`cashflow_op/cap` 40% + analyst4 EPS 修正 25% + 252 日反转 35%」（decay 4 / SECTOR）
> **0.7244**（最低实测；同骨架去掉分析师腿为 0.876）、
> GLB/TOP3000「FCF/EV 60% + 252 日反转 40%」（COUNTRY/d4）**0.7903**、
> GLB/MINVOL10M「FCF/EV 40% + 252 日反转 60%」**0.829**（反转权重越高 prod 越高）。
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

**运行前先查 `references/ledger.md`（结论账本）**：

```bash
python scripts/redflag.py <字段关键词>        # 这个字段试过没、结论如何
python scripts/redflag.py --region IND --open # 该区还有哪些族没关闭
```

账本按 region × dataset 一行一条，状态 `CLOSED`/`BLOCKED` 命中时退出码为 1。
散文留在 empirical-log，机器可查的结论只在 ledger——**两份不要混，改结论只改 ledger**。

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
| 2026-11-06 | 用户原式 `trade_when(vec_count(buyside_attendance_count)>0, rank(operating_cash_flow), -1)` 2014–2020 全亏、2020 后转正；改造为 3 腿 `QPvWNOqW`（S 1.88 / F 1.25 / TO 12.9%，十年全正）后提交被 **PROD_CORRELATION 0.7588** 拒 | **`rank(operating_cash_flow)` 是规模暴露不是现金流信号**：换成 `/assets_total_2` 或 `/cap` 后年度形态完全不变 ⇒ 是价值/质量 vs 成长的 regime，不是数据 bug；`trade_when(...,-1)` 把换手压到 1.2% 只是把几次陈旧 tilt 冻住。修复靠 `ts_rank(...,504)` + analyst83 事件强度 `vec_sum` + 252 日反转腿 |
| 2026-11-06 | 上述 3 腿的 prod corr 权重 sweep（35/30/35 → 30/35/30 → 40/35/25，另试 REV 45%） | **权重对 prod corr 无效**（0.7588/0.7613/0.7508/0.8601）；原因是 `fundamental23` 与 `pv1` 反转**同时在饱和**，改任一项都只是换哪个拥挤源主导；§8.4.3 的 −0.03/5% 只适用于「拥挤源是价格族」的骨架 |
| 2026-11-06 | 同一现金流×反转骨架换 region：GBR/DEU（快因子区）、EUR/TOP2500、KOR/TOP600、ASI/MINVOL1M 全测 | **`operating_cash_flow` 是 USA 专属裸名**，EUR 等价物是 `fnd23_ofc`（ac 17）；GBR/DEU 只有 pv1 + 事件数据 cov 0.32 ⇒ 事件腿变噪声（单腿 −0.47）；EUR 的 OCF 族 S 1.55–1.70 但 **ladder 0.44–0.68 FAIL**；**只有 ASI/MINVOL1M 成立：`0.50*rank(cashflow_op/cap)+0.50*rank(-ts_rank(returns,252))` → S 2.09 / F 1.42 / ladder 2.06 PASS，2014–2023 全正** |
| 2026-11-06 | ASI 上面的候选 `VkxZg7n0` 提交 403 = `LOW_ROBUST_UNIVERSE_*`（ratio 1.8/1.88、ret 0.0875/0.0922），非 prod corr | **ASI 的 robust 门槛 = 主 universe 指标的 90%**；MINVOL1M 上该比例结构性地锁在 0.86–0.87，权重/decay/中性化/trunc 全改不动（trunc 0.04 与 0.08 输出完全相同，疑被钳位）。**换 MINVOL10M 才过 robust**：`qMLObadv`（SECTOR/decay 5）S 1.81 / F 1.18 全检查 PASS，但提交 403 **PROD_CORRELATION 0.876** ⇒ ASI 同族也已饱和 |
| 2026-11-06 | 正交第三腿换族（USA: SBC/buzz/attendance；ASI: analyst4 EPS 修正） | **USA 三条正交腿单腿全废**（SBC −0.25 / buzz −0.35 / 出席变更 −0.30），混合后 −0.35–0.03，方向在 USA 不成立；**ASI 的 analyst4 极冷（alphaCount 1–3）、EPS 修正 126 天单腿 S 0.88，混入 25% 后把 prod corr 从 0.876 压到 0.7244**（S 1.86 / F 1.21 / JPN 1.01 / ladder 2.13 / robust 全 PASS），但仍差 0.024；**再加分析师权重会先打死 JPN 子区**（35% → 0.82、40% → 0.71），所以这条路的上限就是「接近但过不去」 |
| 2026-11-06 | 换更强的分析师腿：sales 修正 / 覆盖数变化 / 季度 EPS 修正 / 三期合成 | **sales 修正腿（单腿 0.68）混入 25% 后 `LLMENAL2` S 1.81 / JPN 1.20 / ladder 2.04 PASS，但 prod corr 0.7394，比 EPS 版更差**；其余三条腿（覆盖数、季度 EPS、三期合成）ladder 直接 FAIL。**sales 腿加到 30% 起 ladder 断崖掉线（1.56/1.49）** ⇒ 该骨架 prod corr 天花板 0.72–0.74，无法在保住 ladder/JPN 的前提下压到 0.70；**更冷的 alphaCount 不等于更低 prod corr**，analyst4 的 EPS/sales 修正属同一经济族，换字段不换族 |
| 2026-11-06 | ASI 第三族可用性：期权族 / 事件族 / fundamental17 FCF | **ASI 无任何 `option*` 数据集（158 个 dataset 全量枚举），期权族整族不可用**；**事件族字段是 event input，`ts_backfill`/`ts_*` 直接 400（`does not support event inputs`），必须先 `vec_avg` 聚合**；事件单腿上限 0.78（`event_stock_model.earnings_financial_event_score_2`，且 2Y FAIL），`news104` 0.31；`fnd17_fcfmtt/cap` 1.08 但 ladder 1.57 WARNING 且与 `cashflow_op` 同族 ⇒ **ASI 该骨架第三腿空间关闭，止于 robust 90% + prod corr 0.72–0.74 双天花板** |
