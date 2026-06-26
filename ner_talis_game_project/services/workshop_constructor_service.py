"""Конструктор мастерских (ТЗ 13 §5.5).

Запись = мастерская: место создания предметов (плавильня/кузница/домашняя/…),
её доступность, бонусы/штрафы, стоимость и связанные профессии/рецепты.
Хранение — EntityStore (data/workshop_constructor.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Типы мастерских (§5.5).
WORKSHOP_TYPES = (
    "smeltery", "forge", "leatherwork", "alchemy", "jewelry", "enchanting",
    "home", "temporary", "event", "field", "npc",
)
WORKSHOP_TYPE_LABELS = {
    "smeltery": "Плавильня", "forge": "Кузница", "leatherwork": "Кожевенная мастерская",
    "alchemy": "Алхимическая мастерская", "jewelry": "Ювелирная мастерская",
    "enchanting": "Чародейская мастерская", "home": "Домашняя мастерская",
    "temporary": "Временная мастерская", "event": "Событийная мастерская",
    "field": "Полевая мастерская", "npc": "NPC-мастерская",
}

_store = EntityStore(
    env_var="WORKSHOP_CONSTRUCTOR_PATH",
    default_rel="data/workshop_constructor.json",
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
        errors.append("Не заполнено название мастерской.")
    wtype = str(data.get("type") or "").strip()
    if not wtype:
        errors.append("Не выбран тип мастерской.")
    elif wtype not in WORKSHOP_TYPES:
        errors.append(f"Неизвестный тип мастерской: {wtype}.")

    for key in ("use_cost", "work_time"):
        if data.get(key) in (None, ""):
            continue
        val = _num(data.get(key))
        if val is None or val < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    for key in ("name", "description"):
        value = str(data.get(key) or "").strip()
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")
    image = str(data.get("image") or "").strip()
    if image and (image.startswith("http://") or image.startswith("https://")):
        errors.append("Изображение должно быть локальным путём (/assets/…), не URL.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
