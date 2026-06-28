"""Конструктор зависимости (ТЗ эффектов §4).

Запись = AddictionDefinition: источники, накопление, стадии, ломка, лечение,
спад. Хранение — EntityStore (data/addiction_constructor.json). Слой данных +
валидация + расчёт стадии; рантайм-применение — на вырост.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

ADDICTION_SCOPES = ("player", "item_group", "potion_group", "skill_group", "custom")
GAIN_ON = ("use", "consume", "equip", "win", "lose", "action", "tick", "battle_end", "custom")
VISIBILITY_MODES = ("hidden", "vague_text", "stage_only", "exact_value")

_store = EntityStore(
    env_var="ADDICTION_CONSTRUCTOR_PATH",
    default_rel="data/addiction_constructor.json",
    statuses=STATUSES,  # noqa: F405
    transitions=TRANSITIONS,  # noqa: F405
    initial_status=STATUS_DRAFT,  # noqa: F405
)


def store() -> EntityStore:
    return _store


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    return bool(value) and str(value).lower() not in ("false", "0", "")


def _check_stages(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    stages = data.get("stages")
    if not isinstance(stages, list) or not stages:
        return
    ranges: list[tuple[float, float]] = []
    for i, st in enumerate(stages, start=1):
        if not isinstance(st, dict):
            errors.append(f"Стадия #{i}: неверный формат.")
            continue
        lo, hi = _num(st.get("min_value")), _num(st.get("max_value"))
        if lo is None or hi is None:
            errors.append(f"Стадия #{i}: нужен диапазон min/max.")
            continue
        if lo > hi:
            errors.append(f"Стадия #{i}: min больше max.")
        ranges.append((lo, hi))
    ranges.sort()
    for a, b in zip(ranges, ranges[1:]):
        if b[0] <= a[1]:
            errors.append("Стадии зависимости пересекаются.")


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name_admin") or data.get("name") or "").strip():
        errors.append("Не заполнено название зависимости.")
    scope = str(data.get("addiction_scope") or "").strip()
    if scope and scope not in ADDICTION_SCOPES:
        warnings.append(f"Область зависимости «{scope}» не из списка.")
    visibility = str(data.get("visibility_mode") or "").strip()
    if visibility and visibility not in VISIBILITY_MODES:
        warnings.append(f"Видимость «{visibility}» не из списка.")

    lo = _num(data.get("addiction_value_min"))
    hi = _num(data.get("addiction_value_max"))
    # §8.3: зависимость должна иметь максимум значения.
    if hi is None:
        errors.append("Зависимость должна иметь максимум значения (addiction_value_max).")
    if lo is not None and hi is not None and lo >= hi:
        errors.append("Минимум зависимости должен быть меньше максимума.")
    default = _num(data.get("default_value"))
    if default is not None and lo is not None and hi is not None and not (lo <= default <= hi):
        errors.append("Стартовое значение вне диапазона.")

    for key in ("gain_per_use", "gain_per_trigger", "daily_gain_limit", "decay_per_day"):
        v = data.get(key)
        if v not in (None, "") and (_num(v) is None or _num(v) < 0):
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    if _truthy(data.get("withdrawal_enabled")) and _num(data.get("withdrawal_delay_seconds")) is None:
        warnings.append("Ломка включена, но не задана задержка (withdrawal_delay_seconds).")
    if _truthy(data.get("decay_enabled")) and (_num(data.get("decay_per_day")) or 0) <= 0:
        warnings.append("Спад включён, но decay_per_day не задан.")

    _check_stages(data, errors, warnings)

    for key in ("name_admin", "name_player", "description_admin", "player_text"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def stage_for_value(data: dict[str, Any], value: Any) -> dict[str, Any] | None:
    v = _num(value)
    if v is None:
        return None
    for st in data.get("stages") or []:
        if not isinstance(st, dict):
            continue
        lo, hi = _num(st.get("min_value")), _num(st.get("max_value"))
        if lo is not None and hi is not None and lo <= v <= hi:
            return st
    return None
