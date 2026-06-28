"""Конструктор регистрации (чат-ТЗ «уровни/опыт/регистрация/расы»).

Запись = шаг/опция регистрации: тип шага (согласие/имя/раса/пол/стартовый дар),
подпись, обязательность, порядок, текст. Слой данных + валидация; хранение —
EntityStore (data/registration_constructor.json). Рантайм регистрации —
handlers/registration.py + registration_service.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

STEP_TYPES = ("consent", "name", "race", "gender", "starting_gift", "tutorial", "custom")
STEP_TYPE_LABELS = {
    "consent": "Согласие", "name": "Имя", "race": "Раса", "gender": "Пол",
    "starting_gift": "Стартовый дар", "tutorial": "Обучение", "custom": "Своё",
}

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="REGISTRATION_CONSTRUCTOR_PATH",
    default_rel="data/registration_constructor.json",
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

    if not str(data.get("label") or "").strip():
        errors.append("Не заполнена подпись шага.")
    step = str(data.get("step_type") or "").strip()
    if step and step not in STEP_TYPES:
        errors.append(f"Неизвестный тип шага: {step}.")
    order = _num(data.get("order"))
    if data.get("order") not in (None, "") and (order is None or order < 0):
        errors.append("Порядок не может быть отрицательным.")

    for key in ("label", "text"):
        value = str(data.get(key) or "")
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
