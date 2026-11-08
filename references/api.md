# BRAIN API 自动化（SKILL.md §7 迁出）

> 由 `SKILL.md` §7 迁出，**节号保持不变**，文中「第 N 节」等交叉引用仍指向原编号。
> 回主页：[`SKILL.md`](../SKILL.md)。结论与状态查 [`ledger.md`](ledger.md)。

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
