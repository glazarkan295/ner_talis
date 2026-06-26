"""Конструктор ремесленных профессий (ТЗ 13 §5.3).

Запись = профессия: уровни, формулы опыта, награды/бонусы за уровень,
открываемые рецепты, мастерские. Хранение — EntityStore
(data/profession_constructor.json). Рантайм опыта профессий — отдельно;
здесь табличные параметры и связи.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Профессии проекта (§5.3) — справочник типов.
PROFESSION_TYPES = (
    "alchemy", "smithing", "smelting", "leatherworking", "jewelry",
    "enchanting", "artifacts", "materials", "cooking", "fishing",
)
PROFESSION_TYPE_LABELS = {
    "alchemy": "Алхимия", "smithing": "Кузнечное дело", "smelting": "Плавильное дело",
    "leatherworking": "Кожевенное дело", "jewelry": "Ювелирное дело",
    "enchanting": "Зачарование", "artifacts": "Создание артефактов",
    "materials": "Создание материалов", "cooking": "Кулинария", "fishing": "Рыболовное ремесло",
}

_store = EntityStore(
    env_var="PROFESSION_CONSTRUCTOR_PATH",
    default_rel="data/profession_constructor.json",
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
        errors.append("Не заполнено название профессии.")
    ptype = str(data.get("profession_type") or "").strip()
    if ptype and ptype not in PROFESSION_TYPES:
        warnings.append(f"Тип профессии «{ptype}» не из стандартного списка.")

    max_level = _num(data.get("max_level"))
    start_level = _num(data.get("start_level"))
    if data.get("max_level") not in (None, "") and (max_level is None or max_level < 1):
        errors.append("Максимальный уровень должен быть ≥ 1.")
    if data.get("start_level") not in (None, "") and (start_level is None or start_level < 0):
        errors.append("Стартовый уровень не может быть отрицательным.")
    if max_level is not None and start_level is not None and start_level > max_level:
        errors.append("Стартовый уровень больше максимального.")

    for key in ("name", "description"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
