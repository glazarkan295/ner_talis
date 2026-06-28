"""Конструктор рас (чат-ТЗ «уровни/опыт/регистрация/расы»).

Запись = определение расы: название, описание/лор, бонусы характеристик,
стартовые параметры, модель, играбельность. Слой данных + валидация; хранение —
EntityStore (data/race_constructor.json). Существующие расы (data/races.json)
сидируются через constructor_import.import_races.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

STATS = ("strength", "wisdom", "endurance", "agility", "perception", "intelligence")
STAT_LABELS = {
    "strength": "Сила", "wisdom": "Мудрость", "endurance": "Выносливость",
    "agility": "Ловкость", "perception": "Восприятие", "intelligence": "Интеллект",
}

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="RACE_CONSTRUCTOR_PATH",
    default_rel="data/race_constructor.json",
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

    if not str(data.get("race_name") or "").strip():
        errors.append("Не заполнено название расы.")

    bonuses = data.get("stat_bonuses")
    if isinstance(bonuses, dict):
        for key in bonuses:
            if str(key) not in STATS:
                warnings.append(f"Бонус для неизвестной характеристики «{key}».")
    elif bonuses not in (None, ""):
        errors.append("stat_bonuses должно быть объектом.")

    image = str(data.get("model_image") or "").strip()
    if image and re.match(r"^(?:[a-z][a-z0-9+.-]*:)?//", image, re.IGNORECASE):
        errors.append("Изображение модели должно быть локальным ассетом (/assets/…), не внешней ссылкой.")

    for key in ("race_name", "description", "lore"):
        value = str(data.get(key) or "")
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
