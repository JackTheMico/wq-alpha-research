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
-- 模板 A：ROE 趋势（通过率最高；主信号 fundamental6：operating_income, equity）
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
```

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
| **PROD_CORRELATION** | 0.7（对 PROD 池） | 与生产池太像 | 同上；顾问独有 |
| DATA_DIVERSITY | 信息性/受限 | 数据源单一 | 引入新 dataset |
| OLD_SIMULATION | — | 仿真过旧 | **重新模拟**后再提交 |
| CLUSTER_TEST | Sharpe ≥ 1.58（KOR/JPS/TWN/HKG/IND/GBR/DEU ≥ 1） | 仅分类，不阻断 | 无影响（`ERROR` 也不阻断） |
| MATCHES_PYRAMID / MATCHES_THEMES | multiplier | 仅加分项 | 无影响 |
| OSMOSIS_ALLOCATION | — | 仅 WARNING | 无影响 |

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
| Fitness < 1.0 | 换手 > 30% | 增大 decay、混合基本面、ts_decay_linear |
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
| 403 | **提交配额耗尽（硬封锁）** | 无 `Retry-After`，立刻重试无效，等配额窗口重置 |

**坑一：201 吞提交（静默丢弃）** — 返回 201，但 `dateSubmitted` 恒为 `None`、status 卡 `UNSUBMITTED`、`SELF_CORRELATION` 一直 `PENDING`。这表示提交被丢弃、alpha 从未进队列，此时**相关性检查永远不会开始算**，不能据此判断因子重复。`submit_verified` 会在 2 分钟无 `dateSubmitted` 时返回 `submit_swallowed(...)`。

**坑二：403 硬封锁** — 配额耗尽后 submit 稳定 403，响应体是 IS 检查列表、无 `Retry-After`。BRAIN 未暴露剩余提交配额端点（`/limits` 等均 404），只能靠时间窗等待。`submit_verified` 直接返回 `submit_403_quota_exhausted`。

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
4. **基本面 > 混合 > 技术**：`operating_income/equity`、`est_eps/close`、`free_cash_flow_reported_value/equity` 是最稳起点。
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
