"""Runtime недельных лимитов / истощения / ротации локаций (ТЗ §16–§42, §62).

Это «живой мир» расширенного конструктора локаций: на одной неделе локация
богата травами, на другой — переполнена волками, на третьей истощена игроками.
Модуль ведёт НЕДЕЛЬНОЕ СОСТОЯНИЕ запасов (сколько осталось) и считает по нему
эффективные шансы выпадения ресурсов/мобов/добычи/событий.

Дизайн (как у world_runtime):
* определения (total_stock, base/min chance, тип лимита) приходят из
  опубликованного контента реестра (kind location_weekly_limit);
* ОСТАТКИ недели — отдельное runtime-состояние в JSON-файле с блокировкой
  (env LOCATION_RUNTIME_STATE_PATH), ключ: <week>/<location>/<limit_id>;
* ядро (effective_chance / redistribution / empty-event порог) — чистые
  функции (детерминированные, rng инъектируется), их и тестируем.

Слой только читает реестр и ведёт состояние запасов. Подключение к живому поиску
(external_location_service) — отдельный аккуратный шаг (как у world_runtime).
"""

from __future__ import annotations

import json
import os
import random
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:  # POSIX-блокировка (на Windows отсутствует)
    import fcntl
except Exception:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from project_paths import project_path, resolve_project_path
from services import world_content_registry as registry

_PUBLISHED = registry.STATUS_PUBLISHED


# --- Неделя -----------------------------------------------------------------
def current_week_key(now: datetime | None = None) -> str:
    """ISO-неделя как ключ периода, напр. «2026-W25»."""
    moment = now or datetime.now(timezone.utc)
    iso = moment.isocalendar()
    return f"{iso[0]}-W{int(iso[1]):02d}"


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "да"}
    return bool(value)


# --- Состояние остатков недели (файл с блокировкой) ------------------------
_STATE_LOCK = threading.Lock()


def state_path() -> Path:
    override = os.getenv("LOCATION_RUNTIME_STATE_PATH")
    if override:
        return resolve_project_path(override)
    return project_path("data", "location_weekly_state.json")


def _load_state() -> dict[str, Any]:
    path = state_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(data: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    tmp.replace(path)


@contextmanager
def _state_file_lock() -> Iterator[None]:
    if fcntl is None:
        yield
        return
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


# --- Определения лимитов (из опубликованного реестра) ----------------------
def published_limits(location_id: str) -> list[dict[str, Any]]:
    """Опубликованные недельные лимиты локации (envelope'ы)."""
    location_id = str(location_id)
    result = []
    for env in registry.list_content(registry.KIND_LOCATION_WEEKLY_LIMIT, status=_PUBLISHED):
        data = env.get("data") or {}
        if str(data.get("location") or "") == location_id:
            result.append(env)
    return result


def limit_total(limit: dict[str, Any]) -> int | None:
    """Общий недельный запас (None → лимита нет, бесконечно)."""
    data = limit.get("data") or limit
    raw = data.get("total_stock")
    if raw in (None, ""):
        return None
    return max(0, _int(raw))


# --- Остатки / расход -------------------------------------------------------
def remaining(location_id: str, limit: dict[str, Any], *, week: str | None = None) -> int | None:
    """Остаток запаса лимита на текущую неделю (None → без лимита)."""
    total = limit_total(limit)
    if total is None:
        return None
    week = week or current_week_key()
    limit_id = str((limit.get("id") if isinstance(limit, dict) else None) or (limit.get("data") or {}).get("id") or "")
    with _STATE_LOCK, _state_file_lock():
        state = _load_state()
        stored = (((state.get(week) or {}).get(location_id) or {}).get(limit_id))
    if stored is None:
        return total
    return max(0, min(total, _int(stored)))


def consume(location_id: str, limit: dict[str, Any], amount: int, *, week: str | None = None) -> tuple[int, int | None]:
    """Списать ``amount`` из недельного запаса. Возвращает (списано, остаток).

    Нельзя списать больше, чем осталось (ТЗ §22/§23): если запрошено больше
    остатка — списывается только остаток, событие выдаёт урезанное количество.
    Без лимита (total=None) — списывается запрошенное, остаток None.
    """
    amount = max(0, _int(amount))
    total = limit_total(limit)
    if total is None:
        return amount, None
    week = week or current_week_key()
    limit_id = str(limit.get("id") or (limit.get("data") or {}).get("id") or "")
    with _STATE_LOCK, _state_file_lock():
        state = _load_state()
        week_bucket = state.setdefault(week, {})
        loc_bucket = week_bucket.setdefault(location_id, {})
        current = loc_bucket.get(limit_id)
        current = total if current is None else max(0, min(total, _int(current)))
        taken = min(amount, current)
        loc_bucket[limit_id] = current - taken
        _save_state(state)
    return taken, current - taken


def force_set_remaining(location_id: str, limit_id: str, value: int, *, week: str | None = None) -> int:
    """Ручное вмешательство админа (§40): задать остаток. Возвращает остаток."""
    value = max(0, _int(value))
    week = week or current_week_key()
    with _STATE_LOCK, _state_file_lock():
        state = _load_state()
        state.setdefault(week, {}).setdefault(location_id, {})[str(limit_id)] = value
        _save_state(state)
    return value


# --- Истощение и эффективный шанс ------------------------------------------
def is_depleted(limit: dict[str, Any], left: int | None, total: int | None) -> bool:
    """Истощён ли лимит для целей минимального шанса (ТЗ §26.1)."""
    if total is None or left is None:
        return False
    data = limit.get("data") or limit
    trigger = str(data.get("depletion_trigger") or data.get("trigger") or "zero")
    if trigger == "below_10pct":
        return left <= total * 0.10
    if trigger == "below_count":
        threshold = _int(data.get("depletion_count"), 0)
        return left <= threshold
    if trigger == "manual":
        return _truthy(data.get("manual_depleted"))
    return left <= 0


def effective_chance(limit: dict[str, Any], left: int | None, total: int | None) -> float:
    """Текущий шанс с учётом истощения (ТЗ §25–§26).

    Норма — базовый шанс. При истощении и включённом «минимальном шансе» падает
    до min_chance; если минимальный шанс не включён — до 0.
    """
    data = limit.get("data") or limit
    base = _num(data.get("base_chance"), 0.0) or 0.0
    if not is_depleted(limit, left, total):
        return base
    if _truthy(data.get("use_min_chance", True)):
        return _num(data.get("min_chance"), 0.0) or 0.0
    return 0.0


# --- Перераспределение шансов событий (ТЗ §27–§30) -------------------------
def resource_chances(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Шансы ресурсов: истощённый падает до min, остальные НЕ растут (ТЗ §27)."""
    out = []
    for row in rows:
        out.append({
            "id": row.get("id"),
            "chance": effective_chance(row, row.get("remaining"), row.get("total")),
        })
    return out


def redistribute_event_chances(rows: list[dict[str, Any]], *, redistribute: bool = False, mode: str = "by_weight") -> list[dict[str, Any]]:
    """Шансы событий: освободившийся шанс истощённых может перетекать к живым
    (ТЗ §28–§30). ``rows``: [{id, base_chance, weight, group, depleted}].

    Если redistribute=False — поведение как у ресурсов (истощённое → min/0,
    остальные без изменений). Если True — освобождённая разница раздаётся живым
    событиям по режиму: even / by_weight / same_group / same_category / normal_only.
    """
    enriched = []
    freed = 0.0
    for row in rows:
        base = _num(row.get("base_chance"), 0.0) or 0.0
        if row.get("depleted"):
            eff = (_num(row.get("min_chance"), 0.0) or 0.0) if _truthy(row.get("use_min_chance", True)) else 0.0
            freed += max(0.0, base - eff)
            enriched.append({**row, "chance": eff, "alive": False})
        else:
            enriched.append({**row, "chance": base, "alive": True})

    if not redistribute or freed <= 0 or mode == "none":
        return [{"id": r.get("id"), "chance": r["chance"]} for r in enriched]

    # Кандидаты на добавку — только «живые» события (есть лимит/не истощены).
    alive = [r for r in enriched if r["alive"]]
    if mode in ("same_group", "same_category"):
        key = "group" if mode == "same_group" else "category"
        # Группируем освобождённый шанс по группе истощённых и раздаём внутри неё.
        for r in enriched:
            r.setdefault("_bonus", 0.0)
        by_group_freed: dict[Any, float] = {}
        for row in rows:
            if row.get("depleted"):
                base = _num(row.get("base_chance"), 0.0) or 0.0
                eff = (_num(row.get("min_chance"), 0.0) or 0.0) if _truthy(row.get("use_min_chance", True)) else 0.0
                by_group_freed[row.get(key)] = by_group_freed.get(row.get(key), 0.0) + max(0.0, base - eff)
        for grp, pool in by_group_freed.items():
            members = [r for r in alive if r.get(key) == grp]
            if not members or pool <= 0:
                continue
            share = pool / len(members)
            for r in members:
                r["_bonus"] += share
        return [{"id": r.get("id"), "chance": r["chance"] + r.get("_bonus", 0.0)} for r in enriched]

    if mode == "even":
        if alive:
            share = freed / len(alive)
            for r in alive:
                r["chance"] += share
    else:  # by_weight (по весам), normal_only трактуем как by_weight среди живых
        total_weight = sum(max(0.0, _num(r.get("weight"), 1.0) or 1.0) for r in alive)
        if total_weight > 0:
            for r in alive:
                w = max(0.0, _num(r.get("weight"), 1.0) or 1.0)
                r["chance"] += freed * (w / total_weight)
    return [{"id": r.get("id"), "chance": r["chance"]} for r in enriched]


def should_show_empty_event(rows: list[dict[str, Any]], *, min_percent: float = 50.0) -> bool:
    """Событие пустой локации: истощено больше заданного % событий (ТЗ §31–§32)."""
    if not rows:
        return False
    depleted = sum(1 for r in rows if r.get("depleted"))
    return (depleted / len(rows)) * 100.0 >= float(min_percent)


# --- Выбор события (взвешенный) --------------------------------------------
def weighted_choice(options: list[dict[str, Any]], rng: random.Random | None = None) -> dict[str, Any] | None:
    """Выбрать один вариант по полю ``chance`` (вес). rng инъектируется."""
    pool = [o for o in options if (_num(o.get("chance"), 0.0) or 0.0) > 0]
    if not pool:
        return None
    rng = rng or random.Random()
    total = sum(_num(o.get("chance"), 0.0) or 0.0 for o in pool)
    point = rng.uniform(0, total)
    upto = 0.0
    for option in pool:
        upto += _num(option.get("chance"), 0.0) or 0.0
        if point <= upto:
            return option
    return pool[-1]
