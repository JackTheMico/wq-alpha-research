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

# GET /simulations/<id> 的终态；WARNING 也可能带 alpha
TERMINAL_STATUSES = {"COMPLETE", "WARNING", "ERROR", "TIMEOUT", "FAIL", "CANCELLED"}
ALPHA_STATUSES = {"COMPLETE", "WARNING"}

# 会阻断提交的 IS 检查（顾问面板实测出现的项）
BLOCKING_CHECKS = {
    "LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
    "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE", "IS_LADDER_SHARPE",
    "LOW_2Y_SHARPE", "POWER_POOL_CORRELATION",
    "SELF_CORRELATION", "PROD_CORRELATION", "DATA_DIVERSITY",
    "REGULAR_SUBMISSION", "OLD_SIMULATION",
}

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
    """构造 POST /simulations 的请求体。overrides 覆盖 settings 中的同名键。"""
    merged = dict(DEFAULT_SETTINGS)
    if settings:
        merged.update(settings)
    merged.update(overrides)
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

    def run_many(
        self, payloads: Sequence[dict], *, batch_size: int = 8, verbose: bool = False
    ) -> list[SimulationResult]:
        """把 payloads 切成 ≤batch_size 的多仿真批次依次执行。

        顾问最多 8 个并发多仿真；这里保守串行，避免触发资源错误
        （"The simulation requires more resources than are available"）。
        """
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

    def gate_report(self, alpha: dict, *, delay: Optional[int] = None) -> tuple[bool, list[str]]:
        """按顾问级阈值给出可读的提交判定（本地前置检查）。"""
        is_ = alpha.get("is") or {}
        delay = delay if delay is not None else int((alpha.get("settings") or {}).get("delay", 1))
        th = self.thresholds(delay)
        msgs: list[str] = []
        ok = True

        sharpe, fitness = is_.get("sharpe"), is_.get("fitness")
        turnover = is_.get("turnover")
        if sharpe is not None and sharpe < th["sharpe"]:
            ok = False
            msgs.append(f"Sharpe {sharpe:.2f} < 门槛 {th['sharpe']:.2f}（D{delay} 顾问级）")
        if fitness is not None and fitness < th["fitness"]:
            ok = False
            msgs.append(f"Fitness {fitness:.2f} < 门槛 {th['fitness']:.2f}（D{delay} 顾问级）")
        if turnover is not None:
            lo, hi = th["turnover"]
            if not lo <= turnover <= hi:
                ok = False
                msgs.append(f"Turnover {turnover:.2%} 不在 [{lo:.0%}, {hi:.0%}]")

        for name, check in self.checks(alpha).items():
            if name not in BLOCKING_CHECKS:
                continue
            result = check.get("result")
            if result in ("FAIL", "ERROR"):
                ok = False
                detail = check.get("value")
                limit = check.get("limit")
                suffix = f"（value={detail}, limit={limit}）" if detail is not None else ""
                msgs.append(f"{name} = {result}{suffix}")

        # 相关性：ACTIVE alpha 的数值不在 checks 里，单独取
        for label, val in (
            ("SELF_CORRELATION", self.self_correlation(alpha)),
            ("PROD_CORRELATION", self.prod_correlation(alpha)),
        ):
            if val is not None and val >= 0.7:
                ok = False
                msgs.append(f"{label} = {val:.4f} ≥ 0.7（除非新 Sharpe ≥ 冲突因子 × 1.1）")
        return ok, msgs


def submit_verified(
    brain: BrainSession, alpha_id: str, *, polls: int = 20, interval: float = 10.0
) -> str:
    """提交并二次确认是否真正上线。

    文档与实测一致：`POST /alphas/{id}/submit` 返回 201 只表示请求被接受，
    必须轮询 `status == ACTIVE`。

    另外两种静默失败要单独识别：
      * **201 吞提交**：返回 201 但 `dateSubmitted` 始终为 None、status 卡 `UNSUBMITTED`
        —— 提交被丢弃，SELF_CORRELATION 也就永远不会开始算。
      * **403 硬封锁**：账户提交配额耗尽，无 `Retry-After`，立刻重试无效。
    """
    resp = brain.submit(alpha_id)
    if resp.status_code == 403:
        return "submit_403_quota_exhausted"
    if resp.status_code == 429:
        return f"submit_429_retry_after={resp.headers.get('Retry-After')}"
    if resp.status_code not in (200, 201):
        return f"submit_failed({resp.status_code}): {resp.text[:160]}"

    for i in range(polls):
        time.sleep(interval)
        alpha = brain.alpha(alpha_id)
        status = alpha.get("status")
        if status == "ACTIVE":
            return "ACTIVE"
        self_corr = BrainSession.self_correlation(alpha)
        if self_corr is not None and self_corr >= 0.7:
            return f"SELF_CORRELATION_{self_corr:.4f}"
        prod_corr = BrainSession.prod_correlation(alpha)
        if prod_corr is not None and prod_corr >= 0.7:
            return f"PROD_CORRELATION_{prod_corr:.4f}"
        # 201 吞提交判别：2 分钟仍无 dateSubmitted 且停在 UNSUBMITTED
        if i >= 12 and not alpha.get("dateSubmitted") and status == "UNSUBMITTED":
            return "submit_swallowed(201 but dateSubmitted=None)"
    return f"still_{brain.alpha(alpha_id).get('status')}"

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
    "aligned_corr",
    "as_pairs",
    "build_payload",
    "load_credentials",
    "print_row",
    "simulate_one",
    "submit_verified",
    "to_returns",
]
