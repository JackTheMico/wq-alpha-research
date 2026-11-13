"""WorldQuant BRAIN API 客户端（对齐 2026-09 官方文档 + 平台前端实际端点）。

设计依据
--------
1. `GET /tutorial-pages/brain-api`（lastModified 2026-09-21）正文 + `OPTIONS /simulations` 实时 schema。
2. `GET /tutorial-pages/understanding-simulation-limits`：`X-Ratelimit-*` 响应头。
3. `GET /tutorial-pages/how-can-you-avoid-duplicate-simulations`：hash 去重缓存。
4. `GET /tutorial-pages/consultant-submission-tests`：顾问级提交阈值（Sharpe>1.58 D1 / >2.69 D0，Fitness>1 D1 / >1.5 D0）。

相对旧脚本的关键修正
--------------------
* 轮询用 `Retry-After` 响应头驱动（文档规定），不再固定 `sleep(8)`。
* 终态集合补全：WAITING / SIMULATING / COMPLETE / WARNING / CANCELLED / ERROR / TIMEOUT / FAIL。
  旧代码只认 COMPLETE / ERROR / FAILED，会把 `WARNING`（alpha 已生成）当成运行中、把 `TIMEOUT`/`FAIL`
  当成未知状态，从而死等或误判。
* 支持 MULTI_SIMULATION：POST 数组（2..10 个），父任务 `children` 给子仿真 id。
* 解析 `location` 字段，代码错误能定位到 property/line/start/end。
* 记录 `X-Ratelimit-Limit / Remaining / Reset`，接近每日额度时主动停。
* 列表用服务端 `status=` 过滤（旧代码拉全量 564 个 alpha 再本地筛）。

用法
----
    from wq_api import BrainSession

    brain = BrainSession()          # 读 WQ_BRAIN_USERNAME / WQ_BRAIN_PASSWORD 或 credential.txt
    brain.authenticate()

    payload = brain.build_payload("rank(close)", decay=4, neutralization="SUBINDUSTRY")
    res = brain.run(payload)
    print(res.alpha_id, brain.alpha(res.alpha_id)["is"]["sharpe"])
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import requests
from requests.auth import HTTPBasicAuth

import numpy as np

API_BASE = "https://api.worldquantbrain.com"

# 官文档 consultant-submission-tests：Thresholds for consultants
CONSULTANT_THRESHOLDS = {
    1: {"sharpe": 1.58, "fitness": 1.00, "turnover": (0.01, 0.70)},
    0: {"sharpe": 2.69, "fitness": 1.50, "turnover": (0.01, 0.70)},
}

# 旧的非顾问门槛，仅在账号无 CONSULTANT 权限时作为回退
STANDARD_THRESHOLDS = {
    1: {"sharpe": 1.25, "fitness": 1.00, "turnover": (0.01, 0.70)},
    0: {"sharpe": 1.25, "fitness": 1.00, "turnover": (0.01, 0.70)},
}

# 质量闸门：平台的 LOW_FITNESS limit=1.0 只是「允许提交」，不代表「值得提交」。
# 社区实操共识：低质量 alpha 交多了会把 Value Factor 打到 0.10，之后交再多也救不回来
# （「为了交而交」是新手最贵的错误）。因此本地在平台线之上再加一道质量线：
#   * Fitness ≥ 2.0 才交；2.5 以上才算好的 regular alpha；
#   * Margin ≥ 万分之十（10‱ = 0.001），否则收益盖不住手续费，交上去也是负贡献；
#   * Returns / Drawdown 只做提示（无公认硬阈值，但有 dd 明显大于 ret 时应人工复核）。
QUALITY_FITNESS_MIN = 2.0
QUALITY_FITNESS_GOOD = 2.5
QUALITY_MARGIN_MIN = 0.001  # 10‱
QUALITY_MARGIN_GOOD = 0.003  # 30‱

# 数据历史硬门槛：字段可回测天数 < 500 时，平台在提交那一刻返回
# `LOW_DURATION = <天数> / 500`。2026-11-13 实测 analyst15 的
# `ebg_sector_18mo_marketcap_percent` 只有 50 天：Sharpe 2.05 / Fitness 2.22 /
# Margin 65.5‱ 全绿，仍然无法提交。关键在于这一项**在 QUICK/FULL 的
# `is.checks` 里都不出现**，只有 `POST /alphas/{id}/submit` 才回算，
# 所以本地只能靠快照 `dateCreated` 的年龄提前估算（见 preflight 的年龄闸门）。
MIN_DURATION_DAYS = 500


def duration_blockers(checks: dict) -> list[str]:
    """LOW_DURATION：字段历史不足，提交必拒。纯函数，便于单测。"""
    check = checks.get("LOW_DURATION")
    if not check:
        return []
    if check.get("result") in ("FAIL", "ERROR"):
        return [
            f"LOW_DURATION = {check.get('result')} {check.get('value')}/{check.get('limit')}"
            f"（字段可回测天数 < {MIN_DURATION_DAYS}，无法提交）"
        ]
    return []


THEME_CHECK = "MATCHES_THEMES"


def theme_entries(checks: Sequence[dict]) -> list[dict]:
    """从 `MATCHES_THEMES` 里抽出 theme 定义（id / multiplier / name）。

    同名检查会出现多次（每个 theme 一条），所以入参必须是**原始列表**，
    不能先按 name 折叠成 dict——折叠会把 PENDING 与 WARNING 两条压成一条。
    实测（2026-11-13，alpha RReWar7g）：
        [{"result": "WARNING", "name": "MATCHES_THEMES",
          "themes": [{"id": "Jypwvg4", "multiplier": 2.0, "name": "EUR/D1 TOPCS1600 Theme"}]},
         {"result": "PENDING", "name": "MATCHES_THEMES",
          "themes": [{"id": "9B3qVP4", "multiplier": 1.0, "name": "GLB/D1 Power Pool Nov`26"}]}]
    """
    out: list[dict] = []
    for check in checks or []:
        if check.get("name") != THEME_CHECK:
            continue
        for theme in check.get("themes") or []:
            out.append({**theme, "result": check.get("result")})
    return out


def parse_theme_scope(name: str) -> dict:
    """从 theme 名解析作用域：`EUR/D1 TOPCS1600 Theme` → region/delay/universe。"""
    scope: dict[str, Any] = {"region": None, "delay": None, "universe": None}
    if not name:
        return scope
    m = re.match(r"([A-Z]{3})\s*/\s*D([01])(?:\s+(TOP[A-Z0-9]*))?", name)
    if m:
        scope["region"], scope["delay"] = m.group(1), int(m.group(2))
        scope["universe"] = m.group(3).upper() if m.group(3) else None
    return scope


def theme_blockers(checks: Sequence[dict]) -> list[str]:
    """主题未命中：有已生效主题（WARNING/FAIL）且没有任何 PASS。

    `WARNING` 语义是「主题已生效但该 alpha 不在范围内」——不影响提交，
    但拿不到 multiplier。社区/用户策略是优先挖主题内 alpha，所以本地按阻断处理。
    """
    entries = theme_entries(checks)
    matched = {t.get("id") for t in entries if t.get("result") == "PASS"}
    out: list[str] = []
    for t in entries:
        if t.get("result") not in ("WARNING", "FAIL"):
            continue
        if t.get("id") in matched:
            continue
        mult = t.get("multiplier")
        mult_txt = f"（x{mult:g}）" if isinstance(mult, (int, float)) else ""
        scope = parse_theme_scope(t.get("name") or "")
        scope_txt = ""
        if scope["region"]:
            scope_txt = f" 作用域 {scope['region']}/D{scope['delay']}"
            if scope["universe"]:
                scope_txt += f"/{scope['universe']}"
        out.append(
            f"主题未命中：{t.get('name')}{mult_txt}{scope_txt} —— "
            f"该 alpha 不在主题范围内，拿不到 multiplier（挖掘时应优先主题作用域）"
        )
    return out


def quality_blockers(is_: dict) -> list[str]:
    """质量闸门的阻断项（纯函数，便于单测）。质量优先于数量。"""
    out: list[str] = []
    fitness = is_.get("fitness")
    if fitness is not None and fitness < QUALITY_FITNESS_MIN:
        out.append(
            f"Fitness {fitness:.2f} < 质量线 {QUALITY_FITNESS_MIN:.1f}"
            f"（平台线只保证能提交；低质量提交会拉低 Value Factor）"
        )
    margin = is_.get("margin")
    if margin is not None and margin < QUALITY_MARGIN_MIN:
        out.append(
            f"Margin {margin:.5f} < 质量线 {QUALITY_MARGIN_MIN:.4f}（10‱），"
            f"收益盖不住手续费"
        )
    returns, drawdown = is_.get("returns"), is_.get("drawdown")
    if (
        isinstance(returns, (int, float))
        and isinstance(drawdown, (int, float))
        and abs(drawdown) > abs(returns)
    ):
        out.append(f"Drawdown {abs(drawdown):.2%} > Returns {abs(returns):.2%}，PnL 形态不可接受")
    return out


def quality_notes(is_: dict) -> list[str]:
    """质量闸门的提示项：不阻断，但提交前应看一眼。"""
    notes: list[str] = []
    fitness, margin = is_.get("fitness"), is_.get("margin")
    if fitness is not None and fitness >= QUALITY_FITNESS_GOOD:
        notes.append(f"Fitness {fitness:.2f} ≥ {QUALITY_FITNESS_GOOD:.1f}，属于好 alpha")
    if margin is None:
        notes.append("Margin 缺失，无法确认交易成本覆盖（建议补 FULL 仿真）")
    elif margin >= QUALITY_MARGIN_GOOD:
        notes.append(f"Margin {margin:.5f} ≥ 30‱，成本覆盖充裕")
    return notes

# GET /simulations/<id> 的终态；WARNING 也可能带 alpha
TERMINAL_STATUSES = {"COMPLETE", "WARNING", "ERROR", "TIMEOUT", "FAIL", "CANCELLED"}
ALPHA_STATUSES = {"COMPLETE", "WARNING"}

# 会阻断提交的 IS 检查（顾问面板实测出现的项）
BLOCKING_CHECKS = {
    "LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
    "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE",
    "LOW_2Y_SHARPE", "POWER_POOL_CORRELATION", "LOW_DURATION",
    "SELF_CORRELATION", "PROD_CORRELATION", "DATA_DIVERSITY",
    "REGULAR_SUBMISSION", "OLD_SIMULATION",
}

# 「仿真后 WARNING、提交时 FAIL」的检查 —— 本地必须按 FAIL 口径预判。
# 实测（2026-11-03，EUR，代价是一次提交额度）：
#   is.checks 里 `IS_LADDER_SHARPE = WARNING, value=0.88, limit=1.58`
#   提交 403 判定书里 `IS_LADDER_SHARPE = FAIL, value=0.88, limit=1.58`
# 同一组 value/limit，两种裁定。所以 **WARNING 不可采信**，只要 value < limit 就当阻断。
STRICT_BLOCKING_CHECKS = {"IS_LADDER_SHARPE", "LOW_2Y_SHARPE"}

# 提交前的实操下限：ladder 类检查要求 ≥ FAIL 阈值才算"值得占用一次提交额度"。
# 纯 PASS 口径（×0.85 折后约 1.35）留的余量太小，实测 0.88 这种量级基本不可能过。
GATE_LADDER_MIN_RATIO = 1.0

DEFAULT_SETTINGS: dict[str, Any] = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 0,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
}

# 多仿真内部必须一致的设置（文档：REGION, DELAY, LANGUAGE, INSTRUMENT TYPE）
MULTI_SIM_INVARIANT = ("type", "instrumentType", "region", "delay", "language")

# `settings` 允许出现的键。不在表内的键会被平台以 400 `Unexpected property` 拒绝，
# 且报错只提属性名、不提是哪一层，极难定位（实测把 `name=` 当关键字参数传进来，
# `name` 会漏进 settings 并触发 400）。这里前置拦截，改为本地可读错误。
VALID_SETTING_KEYS = frozenset(DEFAULT_SETTINGS) | {
    "maxTrade", "maxPosition", "testPeriod", "unitHandling",
    "pasteurization", "nanHandling", "instrumentType", "selectionHandling",
    "selectionLimit", "componentActivation", "lookback", "maxStockWeight",
    "minStockWeight", "capital", "holidayHandling", "tradeWhen",
    "simulationMode",
}


class BrainError(RuntimeError):
    """BRAIN API 调用失败。"""


class RateLimitReached(BrainError):
    """当日仿真额度耗尽。"""


@dataclass
class SimulationResult:
    simulation_id: str
    status: str
    alpha_id: Optional[str] = None
    message: str = ""
    location: dict = field(default_factory=dict)
    children: list[str] = field(default_factory=list)
    progress: Optional[float] = None
    payload: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ALPHA_STATUSES and bool(self.alpha_id)

    def __str__(self) -> str:
        return f"<{self.status} sim={self.simulation_id} alpha={self.alpha_id}>"


def load_credentials(
    username: Optional[str] = None,
    password: Optional[str] = None,
    credential_file: str = "credential.txt",
) -> tuple[str, str]:
    """环境变量优先，其次 credential.txt（JSON 数组，已被 .gitignore 忽略）。"""
    u = username or os.getenv("WQ_BRAIN_USERNAME")
    p = password or os.getenv("WQ_BRAIN_PASSWORD")
    if u and p:
        return u, p
    for path in (Path(credential_file), Path.home() / ".brain_credentials"):
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return str(data[0]), str(data[1])
    raise BrainError(
        "缺少凭据：请设置 WQ_BRAIN_USERNAME / WQ_BRAIN_PASSWORD，"
        "或提供凭据文件 ['<email>','<password>']"
    )


def build_payload(
    expression: str,
    *,
    settings: Optional[dict] = None,
    sim_type: str = "REGULAR",
    **overrides: Any,
) -> dict:
    """构造 POST /simulations 的请求体。overrides 覆盖 settings 中的同名键。

    对未知设置键做前置拦截。**不要往这里传 `name`** —— 平台 schema 里没有这个
    属性，它会漏进 settings 并被拒为 400 `Unexpected property: name`；变体的名字
    属于脚本层的元数据，不要进 payload。
    """
    merged = dict(DEFAULT_SETTINGS)
    if settings:
        merged.update(settings)
    merged.update(overrides)

    unknown = sorted(set(merged) - VALID_SETTING_KEYS)
    if unknown:
        hint = ""
        if "name" in unknown:
            hint = "（变体名字是脚本元数据，不能进 settings；请从 build_payload 参数里去掉 name=）"
        raise BrainError(
            f"payload.settings 含未知属性 {unknown}，平台会返回 400 Unexpected property{hint}。"
            f"合法键见 VALID_SETTING_KEYS。"
        )
    return {"type": sim_type, "settings": merged, "regular": expression}


# ---------------------------------------------------------------------------
# PnL / 相关性工具
# ---------------------------------------------------------------------------
def as_pairs(pnl: Any) -> list[tuple[str, float]]:
    """归一化为 [(date, value)]；兼容旧库的纯 float 列表（用序号当日期）。"""
    if not pnl:
        return []
    if isinstance(pnl, dict):
        pnl = list(pnl.items())
    if not isinstance(pnl, (list, tuple)):
        return []
    out: list[tuple[str, float]] = []
    for i, item in enumerate(pnl):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            try:
                out.append((str(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
        else:
            try:
                out.append((str(i), float(item)))
            except (TypeError, ValueError):
                continue
    return out


def to_returns(pnl: Any, min_points: int = 30) -> list[tuple[str, float]]:
    """累计曲线 -> 日收益（带日期）；已是日收益则原样返回。

    判据：水平波动 std(a) 远大于日变化 std(diff(a))（>5x）即视为累计曲线。
    """
    pairs = as_pairs(pnl)
    if len(pairs) < min_points:
        return []
    a = np.asarray([v for _, v in pairs], dtype=float)
    d = np.diff(a)
    if d.std() > 0 and a.std() > 5 * d.std():
        return [(pairs[i + 1][0], float(d[i])) for i in range(len(d))]
    return pairs


def aligned_corr(
    new_ret: list[tuple[str, float]],
    old_ret: list[tuple[str, float]],
    min_points: int = 30,
) -> Optional[float]:
    """按日期交集对齐后算日收益相关；样本不足或零方差返回 None。

    位置对齐会低估相关性，因此优先按日期取交集；旧库只有序号时退化为尾部对齐。
    """
    if len(new_ret) < min_points or len(old_ret) < min_points:
        return None
    new_map = {d: v for d, v in new_ret}
    if all(d.isdigit() for d, _ in new_ret) or all(d.isdigit() for d, _ in old_ret):
        n = min(len(new_ret), len(old_ret))
        y1 = [v for _, v in new_ret[-n:]]
        y2 = [v for _, v in old_ret[-n:]]
    else:
        common = [(d, new_map[d]) for d, _ in old_ret if d in new_map]
        if len(common) < min_points:
            return None
        y1 = [v for _, v in common]
        y2 = [v for d, v in old_ret if d in new_map]
    if not y1 or np.std(y1) == 0 or np.std(y2) == 0:
        return None
    return float(np.corrcoef(y1, y2)[0, 1])


class SimulationCache:
    """Hash 去重缓存，避免重复仿真白白消耗每日额度（官方推荐做法）。

    以 JSONL 存盘，不引入 pandas/pyarrow 依赖。
    """
    def __init__(self, path: str | Path = "simulation_cache.jsonl"):
        self.path = Path(path)
        self._index: dict[str, str] = {}
        self._load()

    @staticmethod
    def hash_payload(payload: dict) -> str:
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._index[row["alpha_hashed"]] = row["alpha_id"]

    def get(self, payload: dict) -> Optional[str]:
        return self._index.get(self.hash_payload(payload))

    def add(self, payload: dict, alpha_id: str) -> None:
        h = self.hash_payload(payload)
        if h in self._index:
            return
        self._index[h] = alpha_id
        row = {
            "alpha_hashed": h,
            "alpha_id": alpha_id,
            "date_created": datetime.now(timezone.utc).isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def __len__(self) -> int:
        return len(self._index)


class BrainSession:
    """带认证、限流与多仿真支持的 BRAIN 会话。"""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        *,
        credential_file: str | Path = "credential.txt",
        timeout: tuple[float, float] = (10, 120),
        max_retries: int = 3,
        poll_cap: float = 900.0,
    ) -> None:
        self.username, self.password = load_credentials(
            username, password, str(credential_file)
        )
        self.http = requests.Session()
        self.http.auth = HTTPBasicAuth(self.username, self.password)
        self.http.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self.poll_cap = poll_cap
        self.user_id: Optional[str] = None
        self.permissions: list[str] = []
        self.expiry: float = 0.0
        self.rate_limit: dict[str, Optional[str]] = {
            "limit": None,
            "remaining": None,
            "reset": None,
        }

    # ------------------------------------------------------------------ 认证
    def authenticate(self) -> dict:
        resp = self.http.post(f"{API_BASE}/authentication", timeout=self.timeout)
        if resp.status_code == 401 and "persona" in resp.headers.get("WWW-Authenticate", "").lower():
            raise BrainError(
                "该账号启用了生物识别登录，需在浏览器完成认证："
                + requests.compat.urljoin(resp.url, resp.headers.get("Location", ""))
            )
        if resp.status_code == 401:
            detail = ""
            try:
                detail = resp.json().get("detail", "")
            except ValueError:
                detail = resp.text[:200]
            raise BrainError(f"认证失败（401）：{detail}（多次失败可能要求 reCAPTCHA）")
        if resp.status_code != 201:
            raise BrainError(f"认证失败：{resp.status_code} {resp.text[:300]}")
        data = resp.json()
        self.user_id = data.get("user", {}).get("id")
        self.permissions = data.get("permissions", [])
        self.expiry = float(data.get("token", {}).get("expiry", 0))
        return data

    @property
    def is_consultant(self) -> bool:
        return "CONSULTANT" in self.permissions

    @property
    def supports_multi_simulation(self) -> bool:
        return "MULTI_SIMULATION" in self.permissions

    @property
    def supports_quick_mode(self) -> bool:
        return "QUICK_MODE" in self.permissions

    def thresholds(self, delay: int = 1) -> dict:
        table = CONSULTANT_THRESHOLDS if self.is_consultant else STANDARD_THRESHOLDS
        return table[1 if delay == 1 else 0]

    # ------------------------------------------------------------------ 请求层
    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(self.max_retries + 1):
            resp = self.http.request(method, url, **kwargs)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 30))
                if attempt == self.max_retries:
                    raise BrainError(f"429 限流，重试耗尽：{url}")
                time.sleep(wait)
                continue
            if resp.status_code == 401 and attempt == 0:
                self.authenticate().pop("token", None)
                continue
            self._capture_rate_limit(resp)
            return resp
        raise BrainError(f"请求失败：{url}")

    def _capture_rate_limit(self, resp: requests.Response) -> None:
        h = resp.headers
        if "X-Ratelimit-Limit" in h:
            self.rate_limit = {
                "limit": h.get("X-Ratelimit-Limit"),
                "remaining": h.get("X-Ratelimit-Remaining"),
                "reset": h.get("X-Ratelimit-Reset"),
            }

    @property
    def remaining_simulations(self) -> Optional[int]:
        rem = self.rate_limit.get("remaining")
        return int(float(rem)) if rem is not None else None

    def _raise_for(self, resp: requests.Response, what: str) -> None:
        if resp.status_code in (200, 201, 204):
            return
        body = resp.text[:600]
        try:
            parsed = resp.json()
            if isinstance(parsed, dict) and any(
                isinstance(v, list) for v in parsed.values()
            ):
                body = json.dumps(parsed, ensure_ascii=False)[:600]
        except ValueError:
            pass
        raise BrainError(f"{what} 失败：{resp.status_code} {body}")

    # ------------------------------------------------------------------ 仿真
    def simulate(self, payload: dict) -> str:
        """提交单个仿真，返回 simulation id。"""
        resp = self.request("POST", "/simulations", json=payload)
        self._raise_for(resp, "提交仿真")
        return self._sim_id_from(resp)

    def simulate_multi(self, payloads: Sequence[dict]) -> str:
        """提交多仿真（2..10 个），返回父 simulation id。

        文档要求：同一批内 type / instrumentType / region / delay / language 必须一致。
        """
        payloads = list(payloads)
        if not 2 <= len(payloads) <= 10:
            raise BrainError(f"多仿真需要 2..10 个 payload，当前 {len(payloads)} 个")
        if not self.supports_multi_simulation:
            raise BrainError("账号缺少 MULTI_SIMULATION 权限")
        base = payloads[0]
        for p in payloads[1:]:
            for key in MULTI_SIM_INVARIANT:
                if key == "type":
                    a, b = base.get("type"), p.get("type")
                else:
                    a = base["settings"].get(key)
                    b = p["settings"].get(key)
                if a != b:
                    raise BrainError(f"多仿真 {key} 不一致：{a} != {b}")
        resp = self.request("POST", "/simulations", json=payloads)
        self._raise_for(resp, "提交多仿真")
        return self._sim_id_from(resp)

    @staticmethod
    def _sim_id_from(resp: requests.Response) -> str:
        loc = resp.headers.get("Location")
        if not loc:
            raise BrainError("响应缺少 Location 头，无法获取 simulation id")
        return loc.rstrip("/").split("/")[-1]

    def wait(self, sim_id: str, *, verbose: bool = False) -> SimulationResult:
        """按 `Retry-After` 头轮询直到终态（文档规定的正确等待方式）。"""
        waited = 0.0
        last: SimulationResult = SimulationResult(sim_id, "UNKNOWN")
        last_progress: Optional[float] = None
        while waited <= self.poll_cap:
            resp = self.request("GET", f"/simulations/{sim_id}")
            self._raise_for(resp, f"查询仿真 {sim_id}")
            data = resp.json() if resp.content else {}
            # 实测：仿真进行中的 GET 只返回 progress、不带 status 字段，
            # 因此以 progress / alpha 的存在性兜底推导状态。
            status = data.get("status")
            if not status:
                if data.get("alpha"):
                    status = "COMPLETE"
                elif data.get("children"):
                    status = "COMPLETE"
                elif data.get("progress") is not None:
                    status = "SIMULATING"
                else:
                    status = "WAITING"
            last = SimulationResult(
                simulation_id=sim_id,
                status=status,
                alpha_id=data.get("alpha"),
                message=data.get("message", "") or "",
                location=data.get("location") or {},
                children=list(data.get("children") or []),
                progress=data.get("progress"),
                payload=data,
            )
            # Retry-After 缺省或为 0 即表示已到终态
            retry_after = resp.headers.get("Retry-After")
            done = not retry_after or float(retry_after) == 0
            if verbose and not done:
                print(
                    f"  [{sim_id}] {status} progress={last.progress} "
                    f"wait={retry_after}s limit_left={self.remaining_simulations}"
                )
            if done and (status in TERMINAL_STATUSES or status in ALPHA_STATUSES):
                return last
            sleep_for = float(retry_after) if retry_after else 5.0
            time.sleep(max(sleep_for, 1.0))
            waited += max(sleep_for, 1.0)
        last.message = last.message or f"轮询超过 {self.poll_cap}s 未达终态"
        return last

    def run(self, payload: dict, *, verbose: bool = False) -> SimulationResult:
        sim_id = self.simulate(payload)
        result = self.wait(sim_id, verbose=verbose)
        result.payload = payload
        return result

    @staticmethod
    def multi_sim_group_key(payload: dict) -> tuple:
        """多仿真分组键：只有 `MULTI_SIM_INVARIANT` 内的 5 项决定能否同批。"""
        settings = payload.get("settings") or {}
        return tuple(
            payload.get("type") if key == "type" else settings.get(key)
            for key in MULTI_SIM_INVARIANT
        )

    def run_many(
        self, payloads: Sequence[dict], *, batch_size: int = 8, verbose: bool = False
    ) -> list[SimulationResult]:
        """把 payloads 按多仿真不变项分组，组内切成 ≤batch_size 批次依次执行。

        **自动分组**：`region / delay / instrumentType / language / type` 不同的 payload
        不能进同一批（平台报 `多仿真 region 不一致: AMR != EUR`）。这里按这 5 项分桶，
        跨区域 / 跨 delay 的 payload 混在一个 list 里也不会整批失败——实测这个报错
        会让一整轮研究脚本在提交阶段 1 秒内死掉，白等一次。
        返回顺序与入参顺序严格一致（内部记录下标回填）。

        顾问最多 8 个并发多仿真；这里保守串行，避免触发资源错误
        （"The simulation requires more resources than are available"）。
        """
        payloads = list(payloads)
        if not payloads:
            return []

        groups: dict[tuple, list[int]] = {}
        for idx, payload in enumerate(payloads):
            groups.setdefault(self.multi_sim_group_key(payload), []).append(idx)

        if len(groups) > 1 and verbose:
            desc = ", ".join(
                f"({'/'.join(str(x) for x in key)})×{len(idxs)}" for key, idxs in groups.items()
            )
            print(f"payload 跨 {len(groups)} 个多仿真组，自动分组串行：{desc}")

        ordered: list[Optional[SimulationResult]] = [None] * len(payloads)
        for key, idxs in groups.items():
            subset = [payloads[i] for i in idxs]
            if verbose and len(groups) > 1:
                print(f"-- 组 {'/'.join(str(x) for x in key)}：{len(subset)} 个")
            for pos, res in enumerate(
                self._run_batch(subset, batch_size=batch_size, verbose=verbose)
            ):
                if pos < len(idxs):
                    ordered[idxs[pos]] = res
        return [r for r in ordered if r is not None]

    def _run_batch(
        self, payloads: Sequence[dict], *, batch_size: int = 8, verbose: bool = False
    ) -> list[SimulationResult]:
        """执行同一多仿真不变项下的 payload（已由 `run_many` 分好组）。"""
        payloads = list(payloads)
        results: list[SimulationResult] = []
        if not payloads:
            return results
        if len(payloads) == 1 or not self.supports_multi_simulation:
            for i, p in enumerate(payloads):
                if verbose:
                    print(f"[{i + 1}/{len(payloads)}] 单仿真")
                results.append(self.run(p, verbose=verbose))
                time.sleep(2)
            return results

        batch_size = max(2, min(batch_size, 10))
        for start in range(0, len(payloads), batch_size):
            chunk = payloads[start : start + batch_size]
            if len(chunk) == 1:
                results.append(self.run(chunk[0], verbose=verbose))
                continue
            if verbose:
                print(f"多仿真批次 [{start + 1}..{start + len(chunk)}] / {len(payloads)}")
            parent_id = self.simulate_multi(chunk)
            parent = self.wait(parent_id, verbose=verbose)
            if parent.status not in ALPHA_STATUSES and not parent.children:
                results.append(parent)
                continue
            # children 顺序与提交顺序一致，回填原始 payload 以便写去重缓存
            for idx, child_id in enumerate(parent.children):
                child = self.wait(child_id, verbose=verbose)
                if idx < len(chunk):
                    child.payload = chunk[idx]
                results.append(child)
                if len(chunk) == 1 and not child.alpha_id:
                    child.message = child.message or parent.message
            time.sleep(2)
        return results

    def run_cached(
        self,
        payloads: Sequence[dict],
        cache: SimulationCache,
        *,
        batch_size: int = 8,
        verbose: bool = False,
    ) -> list[SimulationResult]:
        """先查 hash 缓存，只对真正新的 payload 跑仿真。"""
        fresh, results = [], []
        for p in payloads:
            hit = cache.get(p)
            if hit:
                results.append(SimulationResult("cached", "COMPLETE", alpha_id=hit, payload=p))
                if verbose:
                    print(f"  命中缓存 -> {hit}")
            else:
                fresh.append(p)
        for res in self.run_many(fresh, batch_size=batch_size, verbose=verbose):
            if res.alpha_id:
                cache.add(res.payload, res.alpha_id)
            results.append(res)
        return results

    # ------------------------------------------------------------------ Alpha
    def alpha(self, alpha_id: str) -> dict:
        resp = self.request("GET", f"/alphas/{alpha_id}")
        self._raise_for(resp, f"读取 alpha {alpha_id}")
        return resp.json()

    def alphas(
        self,
        *,
        status: Optional[str] = None,
        page_size: int = 100,
        max_items: Optional[int] = None,
    ) -> list[dict]:
        """分页拉取 alpha；`status` 走服务端过滤（ACTIVE / UNSUBMITTED / DECOMMISSIONED）。"""
        params: dict[str, Any] = {"limit": page_size, "offset": 0}
        if status:
            params["status"] = status
        out: list[dict] = []
        while True:
            resp = self.request("GET", "/users/self/alphas", params=params)
            self._raise_for(resp, "拉取 alpha 列表")
            data = resp.json()
            batch = data.get("results") or data.get("alphas") or []
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page_size:
                break
            if max_items and len(out) >= max_items:
                return out[:max_items]
            params["offset"] += page_size
        return out

    def recordset(self, alpha_id: str, name: str = "pnl", *, max_wait: float = 120) -> dict:
        """取记录集；文档规定未就绪时返回 `Retry-After`。"""
        waited = 0.0
        while waited <= max_wait:
            resp = self.request("GET", f"/alphas/{alpha_id}/recordsets/{name}")
            retry_after = resp.headers.get("Retry-After")
            if retry_after and float(retry_after) > 0:
                time.sleep(float(retry_after))
                waited += float(retry_after)
                continue
            self._raise_for(resp, f"读取记录集 {alpha_id}/{name}")
            return resp.json() if resp.content else {}
        raise BrainError(f"记录集 {alpha_id}/{name} 在 {max_wait}s 内未就绪")

    def pnl_series(self, alpha_id: str) -> list[tuple[str, float]]:
        """返回 [(date, value), ...]，自动解析 schema/records 压缩格式。"""
        data = self.recordset(alpha_id, "pnl")
        props = (data.get("schema") or {}).get("properties") or []
        if isinstance(props, dict):
            names = {v.get("name", k).lower(): v.get("index", i) for i, (k, v) in enumerate(props.items())}
            date_idx = names.get("date", 0)
            val_idx = next(
                (names[k] for k in ("pnl", "cum_pnl", "returns", "ret") if k in names), 1
            )
        else:
            date_idx = next(
                (i for i, p in enumerate(props) if str(p.get("name", "")).lower() == "date"), 0
            )
            val_idx = next(
                (
                    i
                    for i, p in enumerate(props)
                    if str(p.get("name", "")).lower() in ("pnl", "cum_pnl", "returns", "ret")
                ),
                1,
            )
        out: list[tuple[str, float]] = []
        for row in sorted(data.get("records") or [], key=lambda r: r[date_idx] if isinstance(r, list) else ""):
            rec = row[0] if isinstance(row, list) and len(row) == 1 and isinstance(row[0], list) else row
            try:
                out.append((str(rec[date_idx]), float(rec[val_idx])))
            except (IndexError, TypeError, ValueError):
                continue
        return out

    def submit(self, alpha_id: str) -> requests.Response:
        return self.request("POST", f"/alphas/{alpha_id}/submit")

    @staticmethod
    def checks(alpha: dict) -> dict[str, dict]:
        """把 is.checks 列表转成 {name: check}。"""
        checks = (alpha.get("is") or {}).get("checks") or []
        return {c.get("name"): c for c in checks if c.get("name")}

    @staticmethod
    def self_correlation(alpha: dict) -> Optional[float]:
        """自相关数值——**两个位置都要读**。

        实测（2026-10）：
          * 未提交/待审核 alpha：`is.checks[].name == "SELF_CORRELATION"`，`result` 可能 PENDING；
          * 已提交/ACTIVE alpha：checks 里**没有**该项，数值在 `is.selfCorrelation`（float）。
        只认其中一处就会得出"平台不暴露相关性"的错误结论。
        """
        is_ = alpha.get("is") or {}
        val = is_.get("selfCorrelation")
        if val is None:
            check = {c.get("name"): c for c in is_.get("checks") or []}.get("SELF_CORRELATION") or {}
            val = check.get("value")
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def prod_correlation(alpha: dict) -> Optional[float]:
        """生产池相关（顾问独有），同样兼读 `is.prodCorrelation` 与 checks。"""
        is_ = alpha.get("is") or {}
        val = is_.get("prodCorrelation")
        if val is None:
            check = {c.get("name"): c for c in is_.get("checks") or []}.get("PROD_CORRELATION") or {}
            val = check.get("value")
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def pending_checks(alpha: dict) -> list[str]:
        """尚未回算的检查名。

        `SELF_CORRELATION` / `PROD_CORRELATION` / `POWER_POOL_CORRELATION` 在仿真后
        恒为 `PENDING`，平台只在**提交那一刻**才回算；因此拿 `None` 当作"无相关性"
        是错误解读，只能当作"未知"。这个函数把"未知"显式暴露出来。
        """
        checks = (alpha.get("is") or {}).get("checks") or []
        return [c.get("name") for c in checks if c.get("result") == "PENDING"]

    def active_themes(self, *, limit: int = 200) -> list[dict]:
        """当前生效主题及其作用域（region/delay/universe）与 multiplier。

        `/themes`、`/users/self/themes` 仍然 404（2026-11-13 复核），
        `MATCHES_THEMES` 是唯一窗口：每个 alpha 的 checks 都带 themes 定义。
        按 theme id 去重，result 取最积极的一个（PASS > WARNING > PENDING）。
        """
        rank = {"PASS": 3, "WARNING": 2, "FAIL": 2, "PENDING": 1}
        themes: dict[str, dict] = {}
        for status in ("UNSUBMITTED", "ACTIVE"):
            try:
                rows = self.alphas(status=status, page_size=100, max_items=limit)
            except BrainError:
                continue
            for alpha in rows:
                for theme in theme_entries((alpha.get("is") or {}).get("checks") or []):
                    tid = theme.get("id")
                    if not tid:
                        continue
                    scope = parse_theme_scope(theme.get("name") or "")
                    prev = themes.get(tid)
                    if prev is None or rank.get(theme["result"], 0) > rank.get(prev["result"], 0):
                        themes[tid] = {
                            "id": tid,
                            "name": theme.get("name"),
                            "multiplier": theme.get("multiplier"),
                            "result": theme.get("result"),
                            **scope,
                        }
        order = {"PASS": 0, "WARNING": 1, "PENDING": 2, "FAIL": 1}
        return sorted(themes.values(), key=lambda t: (order.get(t["result"], 3),
                                                      t.get("region") or "", t.get("name") or ""))

    def gate_report(
        self,
        alpha: dict,
        *,
        delay: Optional[int] = None,
        strict: bool = True,
        quality: bool = True,
        theme: bool = True,
    ) -> tuple[bool, list[str]]:
        """按顾问级阈值给出可读的提交判定（本地前置检查）。

        `strict=True`（默认）比 `ok` 更保守：`STRICT_BLOCKING_CHECKS` 里的检查即使
        在仿真后显示 `WARNING`，只要 `value < limit` 就判为阻断——因为提交时平台会
        把同样数值重新裁定为 `FAIL`（实测 IS_LADDER_SHARPE 0.88/1.58）。传
        `strict=False` 可退回旧口径（只看 FAIL/ERROR），仅用于复盘对照。

        `quality=True`（默认）在平台线之上再加一道**质量闸门**：Fitness < 2.0 或
        Margin < 10‱ 直接阻断（见 `QUALITY_FITNESS_MIN` / `QUALITY_MARGIN_MIN`）。
        低质量提交会拉低 Value Factor，宁可少交。传 `quality=False` 只看平台线。

        注意：返回 True 仍只是**必要条件**。`PROD_CORRELATION` 无法本地预测
        （见 §5.2），所以 True 不等于"一定能过"。
        """
        is_ = alpha.get("is") or {}
        delay = delay if delay is not None else int((alpha.get("settings") or {}).get("delay", 1))
        th = self.thresholds(delay)
        blockers: list[str] = []
        notes: list[str] = []

        sharpe, fitness = is_.get("sharpe"), is_.get("fitness")
        turnover = is_.get("turnover")
        if sharpe is not None and sharpe < th["sharpe"]:
            blockers.append(f"Sharpe {sharpe:.2f} < 门槛 {th['sharpe']:.2f}（D{delay} 顾问级）")
        if fitness is not None and fitness < th["fitness"]:
            blockers.append(f"Fitness {fitness:.2f} < 门槛 {th['fitness']:.2f}（D{delay} 顾问级）")
        if turnover is not None:
            lo, hi = th["turnover"]
            if not lo <= turnover <= hi:
                blockers.append(f"Turnover {turnover:.2%} 不在 [{lo:.0%}, {hi:.0%}]")

        if quality:
            blockers.extend(quality_blockers(is_))
            notes.extend(quality_notes(is_))

        # 主题：优先挖主题内 alpha，主题外拿不到 multiplier（用户明确要求）
        if theme:
            theme_msgs = theme_blockers(is_.get("checks") or [])
            blockers.extend(theme_msgs)
            if not theme_msgs:
                for t in theme_entries(is_.get("checks") or []):
                    if t.get("result") == "PASS":
                        notes.append(
                            f"命中主题 {t.get('name')}（x{t.get('multiplier')}），multiplier 生效"
                        )

        checks = self.checks(alpha)
        for name, check in checks.items():
            if name not in BLOCKING_CHECKS:
                continue
            result = check.get("result")
            value, limit = check.get("value"), check.get("limit")
            suffix = f"（value={value}, limit={limit}）" if value is not None else ""
            if result in ("FAIL", "ERROR"):
                blockers.append(f"{name} = {result}{suffix}")
            elif strict and name in STRICT_BLOCKING_CHECKS and result == "WARNING":
                try:
                    below = float(value) < float(limit) * GATE_LADDER_MIN_RATIO
                except (TypeError, ValueError):
                    below = True  # 拿不到数值时按最坏情况处理
                if below:
                    blockers.append(
                        f"{name} = WARNING{value}/{limit}，提交时会被裁定为 FAIL（实测行为）"
                    )

        # 相关性：ACTIVE alpha 的数值不在 checks 里，单独取
        for label, val in (
            ("SELF_CORRELATION", self.self_correlation(alpha)),
            ("PROD_CORRELATION", self.prod_correlation(alpha)),
        ):
            if val is None:
                if label in checks:
                    notes.append(f"{label} 仍未回算（PENDING），只能在提交时得到真实数值")
                continue
            if val >= 0.7:
                blockers.append(f"{label} = {val:.4f} ≥ 0.7（除非新 Sharpe ≥ 冲突因子 × 1.1）")
            elif val >= 0.5:
                notes.append(f"{label} = {val:.4f} 已接近 0.7，按历史实测偏低估 0.1 左右")

        return (not blockers), blockers + notes


def submit_verified(
    brain: BrainSession,
    alpha_id: str,
    *,
    max_posts: int = 100,
    max_wait: float = 300.0,
    verbose: bool = False,
    status_check_every: int = 5,
) -> str:
    """提交并拿到最终判定（返回值是可直接落盘的判定串）。

    **正确姿势是「反复 POST」，不是「GET 轮询 alpha」**（2026-11-03 实测，代价是差点误判）：

      * 提交计算期间，`POST /alphas/{id}/submit` 返回 **200 + `Retry-After` + 空 body + 无 Location**；
        此时 alpha 仍 `UNSUBMITTED`、`dateSubmitted` 仍 `None` —— 这是"还在算"，不是失败。
      * 必须按 `Retry-After` **反复 POST 同一端点**，实测约 **38 次 / 90 秒**才落地：
        `403`（判定书，body 含完整 checks）或 `201`（受理）。
      * `GET /alphas/{id}/submit` 会一直返回同样的 200+Retry-After，读不到结果；
        `POST /alphas/{id}/check` 是 405。
      * 因此本函数不再用 `interval=10` 的 GET 轮询（旧实现 200 秒超时会把正常计算
        误判成"201 吞提交"）。

    **PASS 与 FAIL 的 POST 次数极不对称**（2026-11-04 实测 `ZYQbbVnj`）：
      * FAIL：1–3 次 POST 内就给 403 判定书；
      * PASS：要 40–80 次 200 才转 `ACTIVE`（POST#11 之后 `Retry-After` 变 None，仍全是 200）。
    所以循环内每 `status_check_every` 次顺手 `GET /alphas/{id}`，见到 `ACTIVE` 立刻收工，
    不必陪平台把 POST 次数烧满。

    返回形态：
      `"ACTIVE"` / `"submit_blocked(NAME=value(limit=...); ...)"` /
      `"submit_403_quota_exhausted"` / `"submit_429_retry_after=..."` /
      `"still_UNSUBMITTED(posts=N, waited=..s)"`
    """
    started = time.time()
    deadline = started + max_wait
    posts = 0
    resp = brain.submit(alpha_id)

    while True:
        posts += 1
        code = resp.status_code

        if code == 403:
            detail = submit_verdict(resp)
            if verbose:
                print(f"  POST#{posts} 403 判定书: {detail or '(无 FAIL 项=配额耗尽)'}")
            return f"submit_blocked({detail})" if detail else "submit_403_quota_exhausted"
        if code == 429:
            return f"submit_429_retry_after={resp.headers.get('Retry-After')}"
        if code not in (200, 201):
            return f"submit_failed({code}): {resp.text[:160]}"

        retry_after = resp.headers.get("Retry-After")
        wait = float(retry_after) if retry_after else 1.5  # 没 Retry-After 也不直接 break — 再 POST
        if verbose:
            print(f"  POST#{posts} {code} Retry-After={retry_after} 仍待判定")

        # 成功路径中途收工：成功提交要累积几十次 POST，别等循环跑满
        # （失败路径 1–3 次就 403 了，走不到这里）
        if status_check_every > 0 and posts % status_check_every == 0:
            try:
                cur = brain.alpha(alpha_id)
            except Exception:  # 状态查询失败不该打断提交流程
                cur = {}
            if cur.get("status") == "ACTIVE" or cur.get("dateSubmitted"):
                if verbose:
                    print(f"  收工: status={cur.get('status')} "
                          f"dateSubmitted={cur.get('dateSubmitted')} posts={posts}")
                return "ACTIVE"

        # 只有拿到 403 判定书或转 ACTIVE 才算结束。
        # 201 只表示"请求入队了"，BRAIN 还没开始算；必须继续 POST 直到 403 或 ACTIVE。
        if posts >= max_posts or time.time() >= deadline:
            break
        time.sleep(max(wait, 1.0))
        resp = brain.submit(alpha_id)

    alpha = brain.alpha(alpha_id)
    status = alpha.get("status")
    waited = time.time() - started
    if verbose:
        print(f"  收尾: status={status} dateSubmitted={alpha.get('dateSubmitted')} posts={posts} {waited:.0f}s")
    if status == "ACTIVE" or alpha.get("dateSubmitted"):
        return "ACTIVE"

    # 兜底：还没拿到判定书就再来几次 POST（每次都可能把判定推出来）
    for _ in range(3):
        retry = brain.submit(alpha_id)
        if retry.status_code == 403:
            detail = submit_verdict(retry)
            if detail:
                return f"submit_blocked({detail})"
            return "submit_403_quota_exhausted"
        if retry.status_code == 201:
            if brain.alpha(alpha_id).get("status") == "ACTIVE":
                return "ACTIVE"
        time.sleep(2.0)

    return f"still_{brain.alpha(alpha_id).get('status')}(posts={posts}, waited={waited:.0f}s)"


def submit_verdict_checks(resp: "requests.Response") -> dict[str, Any]:
    """把提交判定书（403 的 body）解析成结构化字典。

    返回 `{"fails": [{name, value, limit, result}...], "checks": [...]}`；
    body 不是 JSON 时返回空结构。**`fails` 为空且 HTTP 403 ⇒ 真的是配额耗尽**，
    两者不能用同一句话概括（历史上曾把相关性 FAIL 误报成配额问题）。
    """
    try:
        body = resp.json()
    except ValueError:
        return {"fails": [], "checks": []}
    checks = ((body or {}).get("is") or {}).get("checks") or []
    fails = [c for c in checks if c.get("result") in ("FAIL", "ERROR")]
    return {"fails": fails, "checks": checks}


def submit_verdict(resp: "requests.Response") -> str:
    """从 submit 的 403 响应体解析真实判定。

    403 的 body 形如 `{"is": {"checks": [...]}}`，里面是**提交时实时计算**的
    IS checks（含 SELF_CORRELATION / PROD_CORRELATION 的真实数值）。返回
    `NAME=value(limit=...)` 拼接串；无 FAIL 则返回空串（那才是真的配额耗尽）。
    """
    return "; ".join(
        f"{c.get('name')}={c.get('value')}(limit={c.get('limit')})"
        for c in submit_verdict_checks(resp)["fails"]
    )

# ---------------------------------------------------------------------------
# 字段可用性 / 区域覆盖（"这个字段能不能在某区域用" 的唯一可靠来源）
# ---------------------------------------------------------------------------
def data_field(brain: BrainSession, field_id: str) -> dict:
    """取单个字段的完整元数据；不存在返回空 dict。"""
    resp = brain.request("GET", f"/data-fields/{field_id}")
    if resp.status_code != 200:
        return {}
    return resp.json() or {}


def field_coverage(brain: BrainSession, field_id: str) -> list[dict]:
    """字段在各 `region / universe / delay` 下的可用性条目。

    **元数据结构是个坑**：按 region 的可用性在 `data[]` 数组里，顶层**没有**
    `regions` 属性。早期代码读顶层 `regions` 会得到空值，从而误判"字段不可用"
    （实测 returns 字段就因此被判成不可用，实际上 GLB/TOP3000/delay=1 覆盖 1.0）。
    """
    return list(data_field(brain, field_id).get("data") or [])


def field_regions(brain: BrainSession, field_ids: Iterable[str]) -> set[str]:
    """收集一批字段出现过的合法 region 代码。

    `/regions`、`/simulations/settings` 都是 404，平台没有公开的区域枚举端点，
    只能这样反推。实测全集：USA EUR ASI CHN KOR HKG GLB AMR IND GBR DEU ALL
    —— **没有 "ARC"**（社区文章里常写的 "ARC/GLB" 中 ARC 不是合法代码）。
    """
    out: set[str] = set()
    for fid in field_ids:
        for entry in field_coverage(brain, fid):
            if entry.get("region"):
                out.add(entry["region"])
    return out


def field_availability(
    brain: BrainSession,
    field_id: str,
    *,
    region: str,
    universe: Optional[str] = None,
    delay: Optional[int] = None,
) -> list[dict]:
    """按 region / universe / delay 过滤后的可用性条目（含 coverage 与 alphaCount）。

    `alphaCount` 是拥挤度信号，但**低 alphaCount 不等于有信号**：实测
    `star_val_sector_rank` 在 AMR/TOP600 仅 256 个 alpha、EUR/TOP800 仅 239 个，
    Sharpe 却只有 0.68 / 0.59；真正可用的是很拥挤的 EUR/TOP2500。
    """
    out = []
    for entry in field_coverage(brain, field_id):
        if entry.get("region") != region:
            continue
        if universe is not None and entry.get("universe") != universe:
            continue
        if delay is not None and entry.get("delay") != delay:
            continue
        out.append(entry)
    return out


def fields_of_dataset(
    brain: BrainSession,
    dataset_id: str,
    *,
    region: str = "USA",
    universe: str = "TOP3000",
    delay: int = 1,
    limit: int = 50,
    max_pages: int = 20,
) -> list[dict]:
    """列出某 dataset 在指定 region/universe/delay 下的字段。

    **必须带 `instrumentType=EQUITY`**：实测用 `dataset.id` 过滤时漏掉这个参数，
    服务端一律返回 400 `Invalid query`（不是空数组，是硬报错），极易误判成
    "该数据集在本地域不可用"。
    """
    out: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        params = {
            "dataset.id": dataset_id,
            "region": region,
            "universe": universe,
            "delay": delay,
            "instrumentType": "EQUITY",
            "limit": limit,
            "offset": offset,
        }
        resp = brain.request("GET", "/data-fields", params=params)
        brain._raise_for(resp, f"列出 dataset {dataset_id} 的字段")
        body = resp.json() or {}
        page = list(body.get("results") or [])
        out.extend(page)
        count = body.get("count")
        offset += len(page)
        if not page or (count is not None and offset >= int(count)):
            break
    return out


def simulate_one(
    brain: BrainSession,
    expression: str,
    *,
    name: Optional[str] = None,
    base_settings: Optional[dict] = None,
    **settings_overrides: Any,
) -> dict:
    """跑单个变体并返回摘要字典（含 is 指标、checks、本地门槛判定）。

    统一的返回结构，便于各研究脚本直接打印或落盘：
        {"name", "alpha_id", "status", "message", "location",
         "is", "checks", "gate_ok", "gate_msgs", "payload"}
    """
    payload = build_payload(expression, settings=base_settings, **settings_overrides)
    res = brain.run(payload)
    row: dict[str, Any] = {
        "name": name or expression.strip().splitlines()[0][:48],
        "alpha_id": res.alpha_id,
        "status": res.status,
        "message": res.message,
        "location": res.location,
        "payload": payload,
    }
    if not res.alpha_id:
        return row
    alpha = brain.alpha(res.alpha_id)
    row["is"] = alpha.get("is") or {}
    row["checks"] = {k: v.get("result") for k, v in brain.checks(alpha).items()}
    ok, msgs = brain.gate_report(alpha)
    row["gate_ok"], row["gate_msgs"] = ok, msgs
    return row


def print_row(row: dict) -> None:
    """统一打印一行摘要。"""
    if not row.get("alpha_id"):
        print(f"[{row.get('name')}] 失败: {row.get('status')} {row.get('message', '')[:200]}")
        return
    is_ = row.get("is") or {}
    flag = "✅" if row.get("gate_ok") else "❌"
    print(
        f"{flag} [{row['name']}] {row['alpha_id']} "
        f"Sharpe={is_.get('sharpe', 0):.3f} Fitness={is_.get('fitness', 0):.3f} "
        f"TO={is_.get('turnover', 0) * 100:.1f}% Ret={is_.get('returns', 0) * 100:.1f}% "
        f"DD={is_.get('drawdown', 0) * 100:.1f}%"
    )
    for msg in row.get("gate_msgs", []):
        print(f"     · {msg}")


__all__ = [
    "API_BASE",
    "BrainError",
    "BrainSession",
    "RateLimitReached",
    "SimulationCache",
    "SimulationResult",
    "CONSULTANT_THRESHOLDS",
    "DEFAULT_SETTINGS",
    "GATE_LADDER_MIN_RATIO",
    "MIN_DURATION_DAYS",
    "QUALITY_FITNESS_GOOD",
    "QUALITY_FITNESS_MIN",
    "QUALITY_MARGIN_GOOD",
    "QUALITY_MARGIN_MIN",
    "STRICT_BLOCKING_CHECKS",
    "VALID_SETTING_KEYS",
    "aligned_corr",
    "as_pairs",
    "build_payload",
    "data_field",
    "field_availability",
    "field_coverage",
    "field_regions",
    "fields_of_dataset",
    "load_credentials",
    "parse_theme_scope",
    "print_row",
    "simulate_one",
    "submit_verdict",
    "submit_verdict_checks",
    "submit_verified",
    "theme_blockers",
    "theme_entries",
    "to_returns",
]
