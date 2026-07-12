"""Конструктор зачарования предметов (ТЗ 13 §5.10).

Запись = правило зачарования: накладываемый эффект, материалы, шансы и риски,
ограничения по типу предмета. Хранение — EntityStore
(data/enchant_constructor.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="ENCHANT_CONSTRUCTOR_PATH",
    default_rel="data/enchant_constructor.json",
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
        errors.append("Не заполнено название зачарования.")
    if not data.get("clear_enchant") and not str(data.get("enchant_effect") or "").strip():
        warnings.append("Не указан эффект зачарования.")
    for key in ("success_chance", "break_risk", "extra_effect_chance"):
        if data.get(key) in (None, ""):
            continue
        num = _num(data.get(key))
        if num is None or num < 0 or num > 100:
            errors.append(f"Поле «{key}» должно быть 0–100.")
    for key in ("name", "description"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")
    from services.formula_runtime import validate_references
    errors.extend(validate_references(data, ("success_formula_id", "enchant_formula_id", "purify_formula_id", "break_risk_formula_id")))
    effect_id = str(data.get("enchant_effect") or "")
    if effect_id and not data.get("clear_enchant"):
        from services.effect_constructor_service import published_definition
        if not published_definition(effect_id):
            errors.append(f"Эффект зачарования «{effect_id}» не опубликован.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}
