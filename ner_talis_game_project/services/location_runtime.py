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


# --- Недельная ротация активного набора (ТЗ §35–§38) -----------------------
def _week_seed(location_id: str, week: str) -> int:
    """Детерминированное зерно недели — выбор стабилен в течение недели."""
    return abs(hash((str(location_id), str(week)))) % (2**31)


def _weighted_sample(pool: list[dict[str, Any]], count: int, rng: random.Random) -> list[Any]:
    """Выбор без повторов по весам (поле weight, по умолч. 1)."""
    remaining = list(pool)
    chosen: list[Any] = []
    while remaining and len(chosen) < count:
        weights = [max(0.0, _num(o.get("weight"), 1.0) or 1.0) for o in remaining]
        total = sum(weights)
        if total <= 0:
            chosen.extend(o.get("id") for o in remaining[:count - len(chosen)])
            break
        point = rng.uniform(0, total)
        upto = 0.0
        for index, weight in enumerate(weights):
            upto += weight
            if point <= upto:
                chosen.append(remaining.pop(index).get("id"))
                break
    return chosen


def select_active(pool: list[dict[str, Any]], count: int, *, mode: str = "random", week_index: int = 0, rng: random.Random | None = None) -> list[Any]:
    """Выбрать активный набор недели из пула кандидатов (ТЗ §37).

    ``pool``: [{id, weight?, forced?}]. Режимы: random / weighted_random /
    fixed_calendar (окно по номеру недели) / manual (только forced=True).
    seasonal/by_world_event/by_holiday/by_economy в чистом слое сводятся к
    weighted_random — внешний контекст подключается выше.
    """
    count = max(0, int(count))
    ids = [o.get("id") for o in pool]
    if count <= 0 or not pool:
        return []
    if mode == "manual":
        return [o.get("id") for o in pool if _truthy(o.get("forced"))][:count]
    if mode == "fixed_calendar":
        n = len(ids)
        start = int(week_index) % n
        return [ids[(start + i) % n] for i in range(min(count, n))]
    rng = rng or random.Random()
    if mode == "random":
        return rng.sample(ids, min(count, len(ids)))
    # weighted_random и все контекстные режимы (fallback).
    return _weighted_sample(pool, count, rng)


def rolled_rotation(location_id: str, rotation: dict[str, Any], *, week: str | None = None) -> dict[str, list[Any]]:
    """Активный набор недели для локации (стабилен в течение недели, ТЗ §39).

    Раскатанный выбор кэшируется в состоянии (ключ week/location/__rotation__),
    чтобы в течение недели набор не «прыгал» между запросами.
    """
    week = week or current_week_key()
    data = rotation.get("data") or rotation
    rot_id = str(rotation.get("id") or data.get("id") or "rotation")
    cache_key = f"__rotation__:{rot_id}"
    with _STATE_LOCK, _state_file_lock():
        state = _load_state()
        cached = (((state.get(week) or {}).get(location_id) or {}).get(cache_key))
        if isinstance(cached, dict):
            return {k: list(v) for k, v in cached.items()}
        mode = str(data.get("selection_mode") or "random")
        try:
            week_index = int(str(week).split("-W")[-1])
        except (ValueError, IndexError):
            week_index = 0
        rng = random.Random(_week_seed(location_id, week))
        result = {
            "resources": select_active(data.get("resource_pool") or [], _int(data.get("active_resources"), 0), mode=mode, week_index=week_index, rng=rng),
            "mobs": select_active(data.get("mob_pool") or [], _int(data.get("active_mobs"), 0), mode=mode, week_index=week_index, rng=rng),
            "events": select_active(data.get("event_pool") or [], _int(data.get("active_events"), 0), mode=mode, week_index=week_index, rng=rng),
        }
        state.setdefault(week, {}).setdefault(location_id, {})[cache_key] = result
        _save_state(state)
    return result


# --- Подключение к живой игре (флаг + overlay пустой локации) ---------------
def live_enabled() -> bool:
    """Включён ли живой слой конструктора локаций/мира.

    Источники (15-CODEX §5): env ``WORLD_CONSTRUCTOR_LIVE`` (аварийный override)
    ИЛИ feature flag ``use_v2_locations`` из админ-панели. По умолчанию ВЫКЛ —
    игра работает строго по старой логике. Так переключатель V2 в админке реально
    влияет на runtime, а env остаётся быстрым аварийным выключателем.
    """
    if _truthy(os.getenv("WORLD_CONSTRUCTOR_LIVE")):
        return True
    try:
        from services import feature_flags_service as ff

        return ff.is_enabled("use_v2_locations")
    except Exception:
        return False


def published_empty_events(location_id: str) -> list[dict[str, Any]]:
    """Опубликованные «события пустой локации» для локации (ТЗ §31)."""
    location_id = str(location_id)
    out = []
    for env in registry.list_content(registry.KIND_LOCATION_EMPTY_EVENT, status=_PUBLISHED):
        if str((env.get("data") or {}).get("location") or "") == location_id:
            out.append(env)
    return out


def location_limit_depletion(location_id: str, *, week: str | None = None) -> list[dict[str, Any]]:
    """[{id, depleted}] по опубликованным недельным лимитам локации."""
    week = week or current_week_key()
    rows = []
    for limit in published_limits(location_id):
        total = limit_total(limit)
        left = remaining(location_id, limit, week=week)
        rows.append({"id": limit.get("id"), "depleted": is_depleted(limit, left, total)})
    return rows


def pick_empty_text(empty_event: dict[str, Any], rng: random.Random | None = None) -> str:
    """Текст события пустой локации (несколько вариантов §33)."""
    data = empty_event.get("data") or empty_event
    texts = data.get("texts")
    if isinstance(texts, list):
        options = [str(t) for t in texts if str(t).strip()]
        if options:
            return (rng or random.Random()).choice(options)
    return str(data.get("player_text") or "Вы ничего не нашли — кажется, за эту неделю здесь уже всё забрали.")


def roll_empty_overlay(location_id: str, *, rng: random.Random | None = None, week: str | None = None) -> str | None:
    """Решение overlay'я «пустой локации» для поиска (ТЗ §31–§34).

    Возвращает текст, если: живой слой включён, у локации есть опубликованное
    событие пустой локации и недельные лимиты, истощено больше порога событий и
    сработал шанс события. Иначе None — поиск идёт по обычной логике.
    """
    if not live_enabled():
        return None
    empties = published_empty_events(location_id)
    if not empties:
        return None
    rows = location_limit_depletion(location_id, week=week)
    if not rows:
        return None
    empty = empties[0]
    data = empty.get("data") or {}
    min_pct = _num(data.get("min_percent_depleted"), 50.0) or 50.0
    if not should_show_empty_event(rows, min_percent=min_pct):
        return None
    rng = rng or random.Random()
    chance = _num(data.get("chance"), 100.0)
    if chance is not None and rng.uniform(0, 100) > chance:
        return None
    return pick_empty_text(empty, rng)


def consume_for_item(location_id: str, item_id: str, amount: int, *, week: str | None = None) -> int | None:
    """Списать выданный предмет из подходящего недельного лимита (ТЗ §23/§24).

    Ищет опубликованный лимит локации с linked_object==item_id (ресурс/предмет/
    трофей/дроп) и списывает из него. None — подходящего лимита нет.
    """
    item_id = str(item_id or "").strip()
    if not item_id or not live_enabled():
        return None
    item_types = {"resource", "item", "trophy", "mob_drop", "event_item", "guild_resource"}
    for limit in published_limits(location_id):
        data = limit.get("data") or {}
        if str(data.get("limit_type") or "") in item_types and str(data.get("linked_object") or "") == item_id:
            taken, _left = consume(location_id, limit, amount, week=week)
            return taken
    return None


def published_mob_spawns(location_id: str) -> list[dict[str, Any]]:
    """Опубликованные записи появления мобов на локации (ТЗ §15)."""
    location_id = str(location_id)
    out = []
    for env in registry.list_content(registry.KIND_LOCATION_MOB_SPAWN, status=_PUBLISHED):
        if str((env.get("data") or {}).get("location") or "") == location_id:
            out.append(env)
    return out


def _mob_limit(location_id: str, mob_id: str) -> dict[str, Any] | None:
    """Опубликованный недельный лимит-моб для (локация, mob_id)."""
    mob_types = {"mob", "mob_group", "rare_mob", "boss"}
    for limit in published_limits(location_id):
        data = limit.get("data") or {}
        if str(data.get("limit_type") or "") in mob_types and str(data.get("linked_object") or "") == str(mob_id):
            return limit
    return None


def mob_weekly_remaining(location_id: str, mob_id: str, *, week: str | None = None) -> int | None:
    """Остаток недельного запаса моба (None → лимита нет, не ограничено §18)."""
    limit = _mob_limit(location_id, mob_id)
    if limit is None:
        return None
    return remaining(location_id, limit, week=week)


def pick_mob_spawn(location_id: str, player_level: int, *, rng: random.Random | None = None, week: str | None = None) -> dict[str, Any] | None:
    """Выбрать запись появления моба для боя (ТЗ §15/§17/§22).

    Учитывает уровень игрока (диапазон спауна), исключает истощённые по
    недельному запасу мобы и выбирает по шансу встречи. None — нет подходящего
    спауна (бой строится по старой логике).
    """
    rng = rng or random.Random()
    candidates: list[dict[str, Any]] = []
    for env in published_mob_spawns(location_id):
        data = env.get("data") or {}
        mob_id = str(data.get("mob_id") or "")
        if not mob_id:
            continue
        lvl_min = data.get("player_level_min")
        lvl_max = data.get("player_level_max")
        if lvl_min not in (None, "") and player_level < _num(lvl_min, 1):
            continue
        if lvl_max not in (None, "") and player_level > _num(lvl_max, 9999):
            continue
        left = mob_weekly_remaining(location_id, mob_id, week=week)
        if left is not None and left <= 0:
            continue  # популяция выбита за неделю
        chance = _num(data.get("spawn_chance"), 0) or 0
        try:
            from services.world_event_runtime import multiplier
            chance *= multiplier("mob_chance_multiplier", context={"location_id": location_id, "mob_id": mob_id, "object_id": mob_id, "level": player_level})
            mob_env=registry.get_content(registry.KIND_MOB,mob_id);mob_data=(mob_env or {}).get("data") or {};rank=str(mob_data.get("mob_rank") or data.get("mob_rank") or "")
            if rank in {"elite","rare","dangerous","mini_boss","boss","world_boss"}:chance *= multiplier("elite_mob_chance_multiplier",context={"location_id":location_id,"mob_id":mob_id,"object_id":mob_id,"level":player_level})
        except Exception:
            pass
        if chance <= 0:
            continue
        candidates.append({"id": env.get("id"), "mob_id": mob_id, "data": data, "chance": chance, "remaining": left})
    return weighted_choice(candidates, rng)


def consume_for_mob(location_id: str, mob_id: str, amount: int, *, week: str | None = None) -> int | None:
    """Списать побеждённых мобов из недельного запаса локации (ТЗ §18/§22)."""
    mob_id = str(mob_id or "").strip()
    if not mob_id or not live_enabled():
        return None
    mob_types = {"mob", "mob_group", "rare_mob", "boss"}
    for limit in published_limits(location_id):
        data = limit.get("data") or {}
        if str(data.get("limit_type") or "") in mob_types and str(data.get("linked_object") or "") == mob_id:
            taken, _left = consume(location_id, limit, amount, week=week)
            return taken
    return None


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
