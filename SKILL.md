---
name: wq-alpha-research
description: "Use for WorldQuant BRAIN alpha research: designing WQ Alpha expressions, selecting fields/operators, diagnosing simulation and IS check failures, tuning Sharpe/Fitness/Turnover, submitting alphas, and building low-correlation alpha portfolios. Also use for 中文 requests about WorldQuant、BRAIN、WQ Alpha、因子表达式、回测、提交、换手、Fitness、Sharpe."
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
  │    └── 是
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

```fastexpr
-- 模板 A：ROE 趋势（通过率最高）
group_rank(ts_rank(operating_income / equity, 126), subindustry)

-- 模板 B：EPS 收益率修正
group_rank(ts_rank(est_eps / close, 126), industry)

-- 模板 C：FCF 收益率
group_rank(ts_rank(free_cash_flow_reported_value / equity, 126), industry)

-- 模板 D：多因子混合（高 Fitness）
0.5 * group_rank(ts_rank(operating_income / equity, 126), subindustry)
+ 0.5 * group_rank(ts_rank(est_eps / close, 126), industry)

-- 模板 E：低相关技术+基本面混合
0.5 * rank(-(close / open - 1)) + 0.5 * rank(ts_rank(operating_income / equity, 126))

-- 模板 F：资产周转 × 利润率
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
| Sharpe | 日 IR × √252 | ≥ 1.5（最低 1.25） |
| Fitness | Sharpe × √(|Returns| / max(TO, 0.125)) | ≥ 1.1（最低 1.0） |
| Returns | 年化收益 / $10M | ≥ 7% |
| Turnover | 日交易额 / Book Size | 1%–20% |
| Drawdown | 峰值到谷值最大回撤 | < 15% |
| Margin | PnL / 总交易额 | 越高越好 |

### 5.2 IS 检查清单

| 检查项 | 阈值 | 失败原因 | 修复方法 |
|--------|------|----------|----------|
| LOW_SHARPE | ≥ 1.25 | 信号弱 | 换字段/窗口/加 group_rank |
| LOW_FITNESS | ≥ 1.0 | 换手过高 | 增大 decay、混合稳定信号 |
| LOW_TURNOVER | ≥ 1% | 信号太稳定 | 缩短窗口、换更活跃字段 |
| HIGH_TURNOVER | ≤ 70% | 换手爆炸 | 增大 decay、trade_when、混合 |
| CONCENTRATED_WEIGHT | 单股 < 10% 且分散 | 权重集中 | 用 rank()、降低 truncation、ts_backfill |
| LOW_SUB_UNIVERSE_SHARPE | TOP1000 也有效 | 小票依赖 | 用基本面、SUBINDUSTRY、避免市值倾斜 |
| SELF_CORRELATION | **信号级** 相关系数 < 0.7，且新 Sharpe ≥ 冲突因子 × 1.1 | 与已上线因子太像（同信号簇） | 换信号簇/换数据来源；**不要只调参数或换窗口**。注意：此检查用信号级相关（≈0.9+），日收益相关只是 proxy 会低估，详见 7.2/7.5 |
| MATCHES_COMPETITION | 信息性 | — | 无影响 |

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

### 7.1 认证（请填写账号）

**使用前必须准备凭据**。推荐使用环境变量；也可以在本地放置未跟踪的 `credential.txt`（已被 `.gitignore` 忽略），内容为 JSON 数组：

```json
["your_username", "your_password"]
```

⚠️ **提醒**：不要把真实账号密码写入仓库。优先使用 `WQ_BRAIN_USERNAME` / `WQ_BRAIN_PASSWORD` 环境变量。

```python
import json
import requests
from requests.auth import HTTPBasicAuth

API_BASE = "https://api.worldquantbrain.com"

# 1. 读取 credential.txt
import os

username = os.getenv("WQ_BRAIN_USERNAME")
password = os.getenv("WQ_BRAIN_PASSWORD")
if not (username and password):
    with open("credential.txt") as f:
        username, password = json.load(f)

# 2. 创建会话并认证
session = requests.Session()
session.auth = HTTPBasicAuth(username, password)
session.headers.update({
    "Content-Type": "application/json",
    "Accept": "application/json",
})

resp = session.post(f"{API_BASE}/authentication")
assert resp.status_code == 201, f"认证失败: {resp.status_code} {resp.text}"
print("认证成功")
```

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

### 7.3 回测

```python
payload = {
    "type": "REGULAR",
    "settings": {
        "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
        "delay": 1, "decay": 0, "neutralization": "SUBINDUSTRY",
        "truncation": 0.08, "pasteurization": "ON", "unitHandling": "VERIFY",
        "nanHandling": "ON", "language": "FASTEXPR", "visualization": False,
    },
    "regular": "group_rank(ts_rank(operating_income/equity, 126), subindustry)",
}
resp = session.post("https://api.worldquantbrain.com/simulations", json=payload)
sim_id = resp.headers["Location"].rstrip("/").split("/")[-1]

while True:
    data = session.get(f"https://api.worldquantbrain.com/simulations/{sim_id}").json()
    if data.get("status") == "COMPLETE":
        alpha_id = data["alpha"]
        break
    time.sleep(8)

alpha = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}").json()
```

### 7.4 提交与监控

```python
# 提交
sub = session.post(f"https://api.worldquantbrain.com/alphas/{alpha_id}/submit")
print(sub.status_code)  # 201 成功

# 监控 SELF_CORRELATION（提交后检查才从 PENDING 跑出结果；value 字段常缺，须从 message 回退解析）
import re

def self_corr(session, alpha_id):
    a = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}").json()
    sc = next((c for c in a.get("is", {}).get("checks", []) if c["name"] == "SELF_CORRELATION"), {})
    result, value, msg = sc.get("result"), sc.get("value"), ""
    for fld in ("message", "description", "detail"):
        if sc.get(fld):
            msg = str(sc[fld]); break
    if value is None and msg:
        m = re.search(r"([0-9]+\.[0-9]+)", msg)
        if m:
            value = float(m.group(1))
    return result, value, msg

for _ in range(60):   # 最多 ~10 分钟；必须等到离开 PENDING，否则只看得到 None
    result, value, msg = self_corr(session, alpha_id)
    print(f"t+{_*10}s SELF_CORR={result} value={value} {msg}")
    if result in ("PASS", "FAIL"):
        break
    time.sleep(10)
# result=FAIL 时 value 即信号级相关系数（如 0.9313），msg 含 'above cutoff of 0.7' 与 Sharpe 比较结论
```

### 7.5 自动提交模板

```python
import numpy as np

def simulate_and_submit(expression, settings, existing=None, cand_expr=None):
    """
    existing: {alpha_id: {"pnl": [(date,val)...], "expr": "...", "sharpe": x}}，已上线因子元数据。
    cand_expr: 候选表达式字符串（信号成分重叠护栏用；缺省回退用 expression）。
    返回: {"alpha_id": ..., "decision": "submitted|skip|high_corr|signal_overlap|verify_failed", ...}
    """
    payload = {"type": "REGULAR", "settings": settings, "regular": expression}
    resp = session.post("https://api.worldquantbrain.com/simulations", json=payload)
    if resp.status_code != 201:
        return {"error": "simulate_failed"}
    sim_id = resp.headers["Location"].rstrip("/").split("/")[-1]
    while True:
        data = session.get(f"https://api.worldquantbrain.com/simulations/{sim_id}").json()
        if data.get("status") == "COMPLETE":
            alpha_id = data["alpha"]
            break
        if data.get("status") in ("ERROR", "FAILED"):
            return {"error": "simulation_error"}
        time.sleep(8)
    alpha = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}").json()
    is_ = alpha.get("is", {})

    # 1. 基础指标过滤
    if is_.get("fitness", 0) < 1.1 or is_.get("sharpe", 0) < 1.3 or is_.get("turnover", 1) > 0.20:
        return {"alpha_id": alpha_id, "decision": "skip", "reason": "metrics", "metrics": is_}

    # 2. 护栏 2：信号成分重叠（关键，只比表达式、不拉 PnL）
    cexpr = cand_expr or expression
    if existing:
        active_exprs = {oid: m.get("expr", "") for oid, m in existing.items()}
        ov = signal_overlap(cexpr, active_exprs)
        if ov:
            return {"alpha_id": alpha_id, "decision": "signal_overlap",
                    "overlap_with": ov, "reason": "信号级相关≈0.9，SELF_CORRELATION 将 FAIL"}

    # 3. 护栏 1：日收益相关（proxy，按日期对齐；豁免：新 Sharpe ≥ 冲突因子 × 1.1）
    if existing:
        new_ret = to_returns(fetch_pnl(session, alpha_id))
        for old_id, m in existing.items():
            old_ret = to_returns(m.get("pnl", []))
            c = aligned_corr(new_ret, old_ret)
            if c is not None and abs(c) >= 0.7:
                old_sharpe = m.get("sharpe")
                if old_sharpe is None or is_.get("sharpe", 0) < old_sharpe * 1.1:
                    return {"alpha_id": alpha_id, "decision": "high_corr",
                            "corr_with": old_id, "corr": c}

    # 4. 提交（201 只表示请求被接受，≠ 已上线）
    sub = session.post(f"https://api.worldquantbrain.com/alphas/{alpha_id}/submit")
    if sub.status_code not in (200, 201):
        return {"alpha_id": alpha_id, "decision": "submit_failed", "status": sub.status_code}

    # 5. 验证是否真正上线（BRAIN 可能因 SELF_CORRELATION 保持 UNSUBMITTED；提交被限频也会停在 UNSUBMITTED）
    for _ in range(20):
        time.sleep(10)
        alpha = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}").json()
        if alpha.get("status") == "ACTIVE":
            return {"alpha_id": alpha_id, "decision": "submitted", "status": "ACTIVE"}
        result, value, msg = self_corr(session, alpha_id)
        if result == "FAIL":
            return {"alpha_id": alpha_id, "decision": "self_correlation_fail",
                    "self_corr": value, "msg": msg, "status": alpha.get("status")}
    st = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}").json().get("status")
    return {"alpha_id": alpha_id, "decision": "verify_failed", "status": st}
```

### 7.6 限流

- 模拟/提交间 sleep 2–5 秒。
- 遇 429 读取 `Retry-After`，指数退避。
- 批量建议单线程或 ≤ 2 并发。

### 7.7 提交后验证（201 ≠ 已上线）

`POST /alphas/{id}/submit` 返回 201 只表示请求被接受，**不代表 alpha 已变为 ACTIVE**。实战中常见：

- alpha 状态仍为 `UNSUBMITTED`（SELF_CORRELATION 未通过或审核中）。
- 同一信号换参数生成的新 alpha被系统判定为重复，无法真正提交。

**必须二次确认**：

```python
alpha = session.get(f"{API_BASE}/alphas/{alpha_id}").json()
print(alpha.get("status"))  # ACTIVE 才算真正提交成功

# 如果 status == UNSUBMITTED，查看 checks 中 SELF_CORRELATION 结果
for c in alpha.get("is", {}).get("checks", []):
    print(c["name"], c.get("result"), c.get("value"))
```

**获取全部 alpha 并统计 ACTIVE 数量**：

```python
def get_all_alphas(session, limit=100):
    all_alphas = []
    offset = 0
    while True:
        data = session.get(f"{API_BASE}/users/self/alphas", params={"limit": limit, "offset": offset}).json()
        batch = data.get("results", data.get("alphas", []))
        if not batch:
            break
        all_alphas.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return all_alphas

all_alphas = get_all_alphas(session)
active = [a for a in all_alphas if a.get("status") == "ACTIVE"]
print(f"total={len(all_alphas)}, ACTIVE={len(active)}")
```

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
- [ ] 相关性基于 **日收益** 计算，不是累计 PnL
- [ ] 字段已验证
- [ ] 模拟无报错
- [ ] Sharpe ≥ 1.3（理想 ≥ 1.5）
- [ ] Fitness ≥ 1.1
- [ ] Turnover 1%–20%（可放宽至 ≤ 35%）
- [ ] Drawdown < 15%
- [ ] 所有 IS 检查 PASS
- [ ] 多空数量合理
- [ ] 提交后 **再次确认 status == ACTIVE**，201 不代表上线

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
pyenv exec python scripts/evolve_skill.py

# 2. 提交：追加到 SKILL.md 并更新 alpha_db.json
pyenv exec python scripts/evolve_skill.py --apply
```

> 注意：**不带 `--apply` 的预览模式不会修改 `alpha_db.json` 和 `SKILL.md`**，你可以先审查再提交。脚本仅依赖 `requests` 和 `numpy`，**不需要 `wq-bus` 项目代码**。数据文件已随 SKILL 分发。

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





