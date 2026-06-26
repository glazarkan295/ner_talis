"""Конструктор опыта (чат-ТЗ «уровни/опыт/регистрация/расы»).

Запись = источник опыта: тип источника (бой/задание/событие/ремесло/поиск/…),
базовый опыт, масштабирование по уровню. Слой данных + валидация; хранение —
EntityStore (data/exp_constructor.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

SOURCE_TYPES = ("mob_kill", "quest", "event", "craft", "search", "achievement", "boss", "admin")
SOURCE_TYPE_LABELS = {
    "mob_kill": "Убийство моба", "quest": "Задание", "event": "Событие", "craft": "Ремесло",
    "search": "Поиск", "achievement": "Достижение", "boss": "Босс", "admin": "Админ",
}

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="EXP_CONSTRUCTOR_PATH",
    default_rel="data/exp_constructor.json",
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
        errors.append("Не заполнено название источника опыта.")
    source = str(data.get("source_type") or "").strip()
    if source and source not in SOURCE_TYPES:
        errors.append(f"Неизвестный тип источника: {source}.")
    for key in ("base_exp", "level_scaling_percent"):
        if data.get(key) in (None, ""):
            continue
        val = _num(data.get(key))
        if val is None or val < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    name = str(data.get("name") or "")
    if name and (_HTML_RE.search(name) or "<script" in name.lower()):
        errors.append("В поле «name» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
