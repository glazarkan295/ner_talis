"""Конструктор улучшения предметов (ТЗ 13 §5.10).

Запись = правило улучшения предмета: тип улучшения, материалы, шансы успеха/
поломки, ограничения по типу предмета. Хранение — EntityStore
(data/upgrade_constructor.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

UPGRADE_TYPES = (
    "raise_level", "raise_quality", "add_effect", "replace_effect",
    "strengthen_effect", "remove_effect", "enchant", "clear_enchant",
)
UPGRADE_TYPE_LABELS = {
    "raise_level": "Повышение уровня", "raise_quality": "Повышение качества",
    "add_effect": "Добавить эффект", "replace_effect": "Заменить эффект",
    "strengthen_effect": "Усилить эффект", "remove_effect": "Снять эффект",
    "enchant": "Зачарование", "clear_enchant": "Очистить зачарование",
}

_store = EntityStore(
    env_var="UPGRADE_CONSTRUCTOR_PATH",
    default_rel="data/upgrade_constructor.json",
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


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название правила улучшения.")
    utype = str(data.get("upgrade_type") or "").strip()
    if utype and utype not in UPGRADE_TYPES:
        errors.append(f"Неизвестный тип улучшения: {utype}.")
    for key in ("success_chance", "break_risk", "material_loss_risk", "extra_effect_chance"):
        if data.get(key) in (None, ""):
            continue
        num = _num(data.get(key))
        if num is None or num < 0 or num > 100:
            errors.append(f"Поле «{key}» должно быть 0–100.")
    for key in ("name", "description"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}
