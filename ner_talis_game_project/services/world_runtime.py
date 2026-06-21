"""Runtime-чтение опубликованного контента «Конструктора мира» (ТЗ §17).

Единая точка, через которую ИГРА читает data-driven контент из реестра —
только статус ``published``. Бот по нажатию кнопки определяет локацию, берёт её
сцену (описание + кнопки + переходы + события), а при бое — моба и его дроп.

Слой только читает реестр (world_content_registry); он НЕ переписывает игровые
циклы. Подключение к конкретным хендлерам (city/боя) — отдельный аккуратный шаг.
"""

from __future__ import annotations

import random
from typing import Any

from services import world_content_registry as registry

_PUBLISHED = registry.STATUS_PUBLISHED


def _published(kind: str) -> list[dict[str, Any]]:
    return registry.list_content(kind, status=_PUBLISHED)


def _data(envelope: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(envelope, dict):
        return None
    data = dict(envelope.get("data") or {})
    data["id"] = envelope.get("id")
    return data


def get_published(kind: str, content_id: str) -> dict[str, Any] | None:
    envelope = registry.get_content(kind, content_id)
    if envelope is None or envelope.get("status") != _PUBLISHED:
        return None
    return _data(envelope)


def location(loc_id: str) -> dict[str, Any] | None:
    return get_published(registry.KIND_LOCATION, loc_id)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def location_buttons(loc_id: str, *, platform: str | None = None) -> list[dict[str, Any]]:
    """Опубликованные кнопки локации, отсортированные по order, с фильтром по
    платформе (telegram/vk) по флагам показа."""
    loc_id = str(loc_id)
    result = []
    for env in _published(registry.KIND_BUTTON):
        data = env.get("data") or {}
        if str(data.get("owner_location") or "") != loc_id:
            continue
        if platform == "telegram" and not data.get("show_telegram"):
            continue
        if platform == "vk" and not data.get("show_vk"):
            continue
        result.append(_data(env))
    result.sort(key=lambda b: _num(b.get("order"), 0))
    return result


def location_transitions(loc_id: str) -> list[dict[str, Any]]:
    loc_id = str(loc_id)
    return [_data(e) for e in _published(registry.KIND_TRANSITION)
            if str((e.get("data") or {}).get("from_location") or "") == loc_id]


def location_events(loc_id: str) -> list[dict[str, Any]]:
    loc_id = str(loc_id)
    return [_data(e) for e in _published(registry.KIND_EVENT)
            if str((e.get("data") or {}).get("location") or "") == loc_id]


def location_npcs(loc_id: str) -> list[dict[str, Any]]:
    loc_id = str(loc_id)
    return [_data(e) for e in _published(registry.KIND_NPC)
            if str((e.get("data") or {}).get("location") or "") == loc_id]


def _spawns_in(mob_data: dict[str, Any], loc_id: str) -> bool:
    raw = mob_data.get("locations")
    ids = [str(x).strip() for x in raw] if isinstance(raw, list) else [p.strip() for p in str(raw or "").split(",")]
    return loc_id in [i for i in ids if i]


def mobs_in_location(loc_id: str) -> list[dict[str, Any]]:
    loc_id = str(loc_id)
    return [_data(e) for e in _published(registry.KIND_MOB) if _spawns_in(e.get("data") or {}, loc_id)]


def mob(mob_id: str) -> dict[str, Any] | None:
    return get_published(registry.KIND_MOB, mob_id)


def location_scene(loc_id: str, *, platform: str | None = None) -> dict[str, Any] | None:
    """Готовая «сцена» локации для бота: заголовок, текст, кнопки и связи."""
    data = location(loc_id)
    if data is None:
        return None
    return {
        "id": loc_id,
        "title": data.get("name"),
        "text": data.get("description") or data.get("short_description") or "",
        "buttons": [b.get("text") for b in location_buttons(loc_id, platform=platform)],
        "transitions": location_transitions(loc_id),
        "events": location_events(loc_id),
        "npcs": location_npcs(loc_id),
    }


def roll_drop(mob_or_id: Any, *, rng: random.Random | None = None, enhanced: bool = False, event: bool = False) -> list[dict[str, Any]]:
    """Прокрутить таблицу дропа моба. Возвращает список {item_id, amount}.

    Чистая функция (rng инъектируется для тестов). Учитывает флаги строки
    «только усиленный» / «только событие».
    """
    rng = rng or random.Random()
    data = mob(mob_or_id) if isinstance(mob_or_id, str) else (mob_or_id or {})
    rows = (data or {}).get("drop")
    if not isinstance(rows, list):
        return []
    drops: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("only_enhanced") and not enhanced:
            continue
        if row.get("only_event") and not event:
            continue
        item_id = str(row.get("item_id") or "").strip()
        chance = _num(row.get("chance"), 0)
        if not item_id or chance <= 0:
            continue
        if rng.uniform(0, 100) <= chance:
            cmin = int(_num(row.get("min_count"), 1) or 1)
            cmax = int(_num(row.get("max_count"), cmin) or cmin)
            if cmax < cmin:
                cmax = cmin
            drops.append({"item_id": item_id, "amount": rng.randint(cmin, cmax)})
    return drops
