"""Конструктор репутации (item-reputation §3, эффекты §3, import §5.17).

Запись = определение репутации: открытая/скрытая/частичная, область действия,
диапазон значений, стадии, правила изменения, эффекты, скрытые метки и угасание.
Хранение — EntityStore (data/reputation_constructor.json). Чистый слой данных +
валидация + предпросмотр последствий; рантайм-применение — на вырост.

UX-правило: игроку не показывать формулы и (для скрытой репутации) точное
значение — только стадию/текст.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

VISIBILITY = ("visible", "hidden", "partial")
VISIBILITY_LABELS = {"visible": "Открытая", "hidden": "Скрытая", "partial": "Частично скрытая"}
SCOPE_TYPES = (
    "city", "district", "faction", "npc", "guild", "crime_group", "guards",
    "traders", "crafters", "location", "region", "race", "world_event",
    "hidden_group", "global", "other",
)
DISPLAY_MODES = ("number", "stage", "scale", "text")
CHANGE_TRIGGERS = (
    "quest_complete", "quest_fail", "trade", "crime", "fine_paid", "fine_unpaid",
    "event_choice", "item_use", "mob_kill", "pvp_kill", "help_npc", "raid",
    "achievement", "admin",
)
DECAY_DIRECTIONS = ("toward_zero", "toward_default", "down_only", "up_only")

_store = EntityStore(
    env_var="REPUTATION_CONSTRUCTOR_PATH",
    default_rel="data/reputation_constructor.json",
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


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name_ru") or data.get("name") or "").strip():
        errors.append("Не заполнено название репутации.")
    visibility = str(data.get("visibility") or "visible").strip()
    if visibility not in VISIBILITY:
        errors.append(f"Неизвестная видимость: {visibility}.")
    scope = str(data.get("scope_type") or "").strip()
    if scope and scope not in SCOPE_TYPES:
        warnings.append(f"Область действия «{scope}» не из стандартного списка.")
    display_mode = str(data.get("display_mode") or "").strip()
    if display_mode and display_mode not in DISPLAY_MODES:
        warnings.append(f"Режим отображения «{display_mode}» не из списка.")

    lo = _num(data.get("min_value"))
    hi = _num(data.get("max_value"))
    default = _num(data.get("default_value"))
    if lo is not None and hi is not None and lo >= hi:
        errors.append("Минимальное значение должно быть меньше максимального.")
    if default is not None and lo is not None and hi is not None and not (lo <= default <= hi):
        errors.append("Стартовое значение вне диапазона min/max.")

    # §6.2: согласованность видимости.
    if visibility == "visible" and not _truthy(data.get("show_to_player", True)):
        warnings.append("Открытая репутация скрыта от игрока — проверьте видимость.")
    if visibility == "hidden" and _truthy(data.get("show_exact_value")):
        warnings.append("Скрытая репутация показывает точное значение игроку (ТЗ §6.2).")

    # Стадии: непересекающиеся диапазоны, без пробелов.
    stages = data.get("stages")
    if isinstance(stages, list) and stages:
        ranges: list[tuple[float, float]] = []
        for i, st in enumerate(stages, start=1):
            if not isinstance(st, dict):
                errors.append(f"Стадия #{i}: неверный формат.")
                continue
            smin, smax = _num(st.get("min_value")), _num(st.get("max_value"))
            if smin is None or smax is None:
                errors.append(f"Стадия #{i}: нужен диапазон min/max.")
                continue
            if smin > smax:
                errors.append(f"Стадия #{i}: min больше max.")
            ranges.append((smin, smax))
        ranges.sort()
        for a, b in zip(ranges, ranges[1:]):
            if b[0] <= a[1]:
                errors.append("Стадии репутации пересекаются.")
            elif b[0] > a[1] + 1:
                warnings.append("Между стадиями репутации есть пустой диапазон.")

    # Правила изменения.
    for i, rule in enumerate(data.get("change_rules") or [], start=1):
        if isinstance(rule, dict):
            trig = str(rule.get("trigger") or "").strip()
            if trig and trig not in CHANGE_TRIGGERS:
                warnings.append(f"Правило #{i}: триггер «{trig}» не из списка.")
            if rule.get("change_value") not in (None, "") and _num(rule.get("change_value")) is None:
                errors.append(f"Правило #{i}: изменение должно быть числом.")

    # Метки (item-reputation §3.8): нужен диапазон.
    for i, mark in enumerate(data.get("marks") or [], start=1):
        if isinstance(mark, dict):
            if _num(mark.get("required_min_value")) is None or _num(mark.get("required_max_value")) is None:
                warnings.append(f"Метка #{i}: не задан диапазон значений репутации.")

    # Угасание.
    if _truthy(data.get("decay_enabled")):
        direction = str(data.get("decay_direction") or "").strip()
        if direction and direction not in DECAY_DIRECTIONS:
            errors.append(f"Неизвестное направление угасания: {direction}.")
        interval = _num(data.get("decay_interval_seconds"))
        if interval is None or interval <= 0:
            errors.append("Угасание включено, но не задан интервал (decay_interval_seconds).")

    for key in ("name_ru", "name", "short_name", "description_player", "description_admin"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def stage_for_value(data: dict[str, Any], value: Any) -> dict[str, Any] | None:
    """Найти стадию репутации, в диапазон которой попадает значение."""
    v = _num(value)
    if v is None:
        return None
    for st in data.get("stages") or []:
        if not isinstance(st, dict):
            continue
        smin, smax = _num(st.get("min_value")), _num(st.get("max_value"))
        if smin is not None and smax is not None and smin <= v <= smax:
            return st
    return None


def active_marks(data: dict[str, Any], value: Any) -> list[dict[str, Any]]:
    """Метки, активные при текущем значении репутации (item-reputation §3.8)."""
    v = _num(value)
    out: list[dict[str, Any]] = []
    if v is None:
        return out
    for mark in data.get("marks") or []:
        if not isinstance(mark, dict):
            continue
        lo, hi = _num(mark.get("required_min_value")), _num(mark.get("required_max_value"))
        if lo is not None and hi is not None and lo <= v <= hi:
            out.append(mark)
    return out


def preview(data: dict[str, Any], value: Any, delta: Any = 0) -> dict[str, Any]:
    """Предпросмотр последствий (item-reputation §3.12): текущая/следующая стадия,
    активные метки до и после изменения на delta."""
    lo = _num(data.get("min_value"))
    hi = _num(data.get("max_value"))
    cur = _num(value)
    if cur is None:
        cur = _num(data.get("default_value")) or 0
    d = _num(delta) or 0
    nxt = cur + d
    if lo is not None:
        nxt = max(lo, nxt)
    if hi is not None:
        nxt = min(hi, nxt)
    cur_stage = stage_for_value(data, cur)
    nxt_stage = stage_for_value(data, nxt)
    return {
        "current_value": cur,
        "next_value": nxt,
        "current_stage": cur_stage,
        "next_stage": nxt_stage,
        "stage_changed": (cur_stage or {}).get("stage_id") != (nxt_stage or {}).get("stage_id"),
        "current_marks": [m.get("name_ru") or m.get("mark_id") for m in active_marks(data, cur)],
        "next_marks": [m.get("name_ru") or m.get("mark_id") for m in active_marks(data, nxt)],
    }
