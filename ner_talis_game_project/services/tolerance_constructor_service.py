"""Конструктор привыкания (ТЗ эффектов §5).

Запись = ToleranceDefinition: снижение эффективности источника при частом
повторном использовании, стадии, спад. Хранение — EntityStore
(data/tolerance_constructor.json). Слой данных + валидация + расчёт
эффективности; рантайм-применение — на вырост.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

TOLERANCE_SCOPES = (
    "exact_item", "item_group", "effect_type", "potion_type", "skill_type",
    "action_type", "custom",
)

_store = EntityStore(
    env_var="TOLERANCE_CONSTRUCTOR_PATH",
    default_rel="data/tolerance_constructor.json",
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

    if not str(data.get("name_admin") or data.get("name") or "").strip():
        errors.append("Не заполнено название привыкания.")
    scope = str(data.get("tolerance_scope") or "").strip()
    if scope and scope not in TOLERANCE_SCOPES:
        warnings.append(f"Область привыкания «{scope}» не из списка.")

    lo = _num(data.get("value_min"))
    hi = _num(data.get("value_max"))
    if lo is not None and hi is not None and lo >= hi:
        errors.append("Минимум привыкания должен быть меньше максимума.")

    # §8.3: привыкание должно иметь минимум эффективности.
    min_eff = _num(data.get("min_effectiveness_percent"))
    if min_eff is None:
        errors.append("Привыкание должно иметь минимум эффективности (min_effectiveness_percent).")
    elif min_eff < 0 or min_eff > 100:
        errors.append("Минимум эффективности должен быть 0–100%.")

    for key in ("gain_per_use", "gain_per_repeated_use", "decay_per_hour",
                "effectiveness_loss_per_value", "max_penalty_percent"):
        v = data.get(key)
        if v not in (None, "") and (_num(v) is None or _num(v) < 0):
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    if _truthy(data.get("decay_enabled")) and (_num(data.get("decay_per_hour")) or 0) <= 0:
        warnings.append("Спад включён, но decay_per_hour не задан.")

    # Стадии: непересекающиеся.
    stages = data.get("stages")
    if isinstance(stages, list) and stages:
        ranges: list[tuple[float, float]] = []
        for i, st in enumerate(stages, start=1):
            if not isinstance(st, dict):
                errors.append(f"Стадия #{i}: неверный формат.")
                continue
            a, b = _num(st.get("min_value")), _num(st.get("max_value"))
            if a is None or b is None:
                errors.append(f"Стадия #{i}: нужен диапазон min/max.")
                continue
            ranges.append((a, b))
        ranges.sort()
        for x, y in zip(ranges, ranges[1:]):
            if y[0] <= x[1]:
                errors.append("Стадии привыкания пересекаются.")

    for key in ("name_admin", "name_player", "description_admin", "player_text"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def effectiveness(data: dict[str, Any], value: Any) -> float:
    """Эффективность источника при текущем привыкании, % (ТЗ §5.5)."""
    v = _num(value) or 0
    loss = _num(data.get("effectiveness_loss_per_value"))
    loss = 1.0 if loss is None else loss
    min_eff = _num(data.get("min_effectiveness_percent"))
    min_eff = 0.0 if min_eff is None else min_eff
    return max(min_eff, 100.0 - v * loss)
