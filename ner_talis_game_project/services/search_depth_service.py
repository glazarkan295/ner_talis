"""Глубина поиска (ТЗ 09 §19): счётчик непрерывных команд «Поиск» по локации.

Глубина хранится на игроке с привязкой к локации:
    player["search_depth"] = {"location": <id>, "depth": <int>}

Ключевая идея — счётчик помечен локацией. Поиск на ТОЙ ЖЕ локации наращивает
глубину; первый поиск на ДРУГОЙ локации автоматически сбрасывает её к 1. Лагерь/
профиль/подлокация/событие на текущей локации не меняют current_location и не
сбрасывают счётчик (§19.3), а переход на другую локацию/город/крепость сбрасывает
(§19.4). Чистый слой данных без I/O — тестируется напрямую.
"""

from __future__ import annotations

from typing import Any

_KEY = "search_depth"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def current_depth(player: dict[str, Any] | None, location_id: str) -> int:
    """Текущая глубина для локации (0, если счётчик от другой локации/пуст)."""
    state = (player or {}).get(_KEY)
    if not isinstance(state, dict):
        return 0
    if str(state.get("location") or "") != str(location_id or ""):
        return 0
    return max(0, _safe_int(state.get("depth"), 0))


def record_search(player: dict[str, Any], location_id: str, *, max_depth: int = 0) -> int:
    """Зафиксировать команду «Поиск» на локации: +1 к глубине (или 1, если локация
    сменилась). max_depth>0 ограничивает потолок. Возвращает новую глубину."""
    location_id = str(location_id or "")
    state = player.get(_KEY)
    if isinstance(state, dict) and str(state.get("location") or "") == location_id:
        depth = max(0, _safe_int(state.get("depth"), 0)) + 1
    else:
        depth = 1
    if max_depth and max_depth > 0:
        depth = min(depth, int(max_depth))
    player[_KEY] = {"location": location_id, "depth": depth}
    return depth


def reset_depth(player: dict[str, Any]) -> None:
    """Сбросить счётчик глубины (явный выход из локационной ветки, §19.4)."""
    if isinstance(player, dict):
        player[_KEY] = {"location": "", "depth": 0}


def threshold_for(thresholds: Any, depth: int) -> dict[str, Any] | None:
    """Найти порог глубины (§19.6), в диапазон которого попадает depth.

    thresholds — список dict с min_depth/max_depth (max_depth<=0 = без верхней
    границы). Возвращает первый подходящий порог или None."""
    if not isinstance(thresholds, list):
        return None
    depth = _safe_int(depth, 0)
    for row in thresholds:
        if not isinstance(row, dict):
            continue
        lo = _safe_int(row.get("min_depth"), 0)
        hi = _safe_int(row.get("max_depth"), 0)
        if depth >= lo and (hi <= 0 or depth <= hi):
            return row
    return None
