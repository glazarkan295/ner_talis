"""Конструктор уровней (чат-ТЗ «уровни/опыт/регистрация/расы»).

Запись = определение уровня: требуемый опыт, награды (очки характеристик/навыков),
заголовок, разблокировки. Слой данных + валидация; хранение — EntityStore
(data/level_constructor.json). Существующая формула опыта/уровня — в рантайме
(derived_stats_service); конструктор задаёт табличные параметры по уровням.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="LEVEL_CONSTRUCTOR_PATH",
    default_rel="data/level_constructor.json",
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

    level = _num(data.get("level"))
    if level is None or level < 1:
        errors.append("Уровень должен быть целым ≥ 1.")
    for key in ("exp_required", "stat_points", "skill_points"):
        if data.get(key) in (None, ""):
            continue
        val = _num(data.get(key))
        if val is None or val < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    title = str(data.get("title") or "").strip()
    if title and (_HTML_RE.search(title) or "<script" in title.lower()):
        errors.append("В поле «title» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
