"""Конструктор разборки предметов (ТЗ 13 §5.11).

Запись = правило разборки: какой предмет разбирается и что из него можно
получить, шансы/количество, требования. Хранение — EntityStore
(data/disassemble_constructor.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="DISASSEMBLE_CONSTRUCTOR_PATH",
    default_rel="data/disassemble_constructor.json",
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
        errors.append("Не заполнено название правила разборки.")
    if not str(data.get("source_item_id") or "").strip():
        errors.append("Не указан разбираемый предмет (source_item_id).")
    outputs = data.get("outputs")
    if outputs in (None, "", []):
        warnings.append("Не указано, что можно получить при разборке.")
    elif not isinstance(outputs, list):
        errors.append("Список результатов должен быть списком.")
    for key in ("output_chance",):
        if data.get(key) in (None, ""):
            continue
        num = _num(data.get(key))
        if num is None or num < 0 or num > 100:
            errors.append(f"Поле «{key}» должно быть 0–100.")
    for key in ("name", "success_text", "fail_text"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}
