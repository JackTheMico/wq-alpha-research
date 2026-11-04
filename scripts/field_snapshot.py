"""多区域字段快照基础设施。

管理按区域/宇宙/延迟组织的字段元数据快照，支持按需懒加载、有效期检查、手动刷新。
快照命名规范：fields_{region}_{universe}_delay{N}.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = REPO / "references"
MAX_AGE_DAYS = 30

# 分页拉取字段的 API
DATA_FIELDS_URL = "https://api.worldquantbrain.com/data-fields"


def get_index_path() -> Path:
    """索引文件路径。按当前 SNAPSHOT_DIR 动态解析，便于测试隔离（不要在导入时固化）。"""
    return SNAPSHOT_DIR / "fields_index.json"


def get_snapshot_path(region: str, universe: str, delay: int) -> Path:
    """按命名规范返回快照文件路径（region/universe 统一小写）。"""
    region = region.lower()
    universe = universe.lower()
    return SNAPSHOT_DIR / f"fields_{region}_{universe}_delay{delay}.json"


def snapshot_exists(region: str, universe: str, delay: int) -> bool:
    """快照文件是否已存在。"""
    return get_snapshot_path(region, universe, delay).exists()


def check_snapshot_age(path: Path, *, max_days: int = MAX_AGE_DAYS) -> tuple[bool, float]:
    """检查快照是否过期。返回 (是否过期, 已用天数)。"""
    mtime = path.stat().st_mtime
    age_days = (time.time() - mtime) / 86400
    return age_days > max_days, age_days


def _load_index() -> dict:
    index_path = get_index_path()
    if index_path.exists():
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"snapshots": []}


def _save_index(index: dict) -> None:
    get_index_path().write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _update_index(region: str, universe: str, delay: int, field_count: int) -> None:
    """登记/刷新索引条目。

    条目内容未变就不落盘 —— 否则每次 `load_snapshot()` 都会改写 `updated_at`，
    让 `references/fields_index.json` 在每次跑测试后都变成"已修改"，仓库永远是脏的。
    """
    key = f"{region.lower()}_{universe.lower()}_delay{delay}"
    path_name = f"fields_{region.lower()}_{universe.lower()}_delay{delay}.json"
    index = _load_index()
    existing = next((s for s in index["snapshots"] if s.get("key") == key), None)
    if existing and existing.get("field_count") == field_count and existing.get("path") == path_name:
        return

    snapshots = [s for s in index["snapshots"] if s.get("key") != key]
    snapshots.append({
        "key": key,
        "region": region.lower(),
        "universe": universe.lower(),
        "delay": delay,
        "path": path_name,
        "field_count": field_count,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    index["snapshots"] = snapshots
    _save_index(index)


def _fetch_fields_from_api(brain, region: str, universe: str, delay: int) -> list[dict]:
    """分页拉取指定区域的全量字段元数据。"""
    fields: list[dict] = []
    offset = 0
    page_size = 50
    total: Optional[int] = None
    while True:
        resp = brain.request(
            "GET",
            "/data-fields",
            params={
                "region": region.upper(),
                "universe": universe.upper(),
                "delay": delay,
                "instrumentType": "EQUITY",   # 硬必填，漏掉会 400 Invalid query（SKILL §7.10）
                "limit": page_size,
                "offset": offset,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            # 平台对越界 offset 返回 400 "Invalid offset"，翻到尾页时视为正常结束
            if total is not None and offset >= total:
                break
            raise RuntimeError(f"拉取字段失败：{resp.status_code} {resp.text[:200]}")
        data = resp.json()
        if total is None:
            total = data.get("count")
        batch = data.get("results") or data.get("data") or []
        if not batch:
            break
        fields.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        # count 上限为 10000，到尾后越界请求会 400，提前收工
        if total is not None and offset >= total:
            break
    return fields


def load_snapshot(
    region: str,
    universe: str,
    delay: int,
    *,
    brain=None,
    auto_fetch: bool = True,
) -> list[dict]:
    """加载字段快照。若不存在且 brain 提供则自动拉取。"""
    path = get_snapshot_path(region, universe, delay)
    if path.exists():
        fields = json.loads(path.read_text(encoding="utf-8"))
        _update_index(region, universe, delay, len(fields))
        return fields

    if auto_fetch and brain is not None:
        fields = _fetch_fields_from_api(brain, region, universe, delay)
        path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
        _update_index(region, universe, delay, len(fields))
        return fields

    if not path.exists():
        raise FileNotFoundError(
            f"快照不存在：{path}。请提供 brain 参数自动拉取，或先运行 --refresh。"
        )
    fields = json.loads(path.read_text(encoding="utf-8"))
    _update_index(region, universe, delay, len(fields))
    return fields


def refresh_snapshot(brain, region: str, universe: str, delay: int) -> list[dict]:
    """强制从 API 重新拉取并覆盖本地快照。"""
    fields = _fetch_fields_from_api(brain, region, universe, delay)
    path = get_snapshot_path(region, universe, delay)
    path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    _update_index(region, universe, delay, len(fields))
    return fields
