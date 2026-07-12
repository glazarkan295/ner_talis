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
START_FIELDS = ("start_hp", "start_mana", "start_spirit", "start_energy", "accuracy", "dodge", "crit_chance", "crit_damage", "physical_defense", "magic_defense", "armor", "physical_damage", "magic_damage")
BONUS_TYPES = ("stat_flat", "stat_percent", "resource_flat", "resource_percent", "damage_percent", "experience_percent", "effect", "formula", "event_chance", "resource_chance", "craft_chance", "trade_chance", "resistance", "regeneration", "access", "reputation")
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
    for key in START_FIELDS:
        if data.get(key) not in (None, "") and _num(data.get(key)) is None:
            errors.append(f"Стартовый параметр {key}: не число.")
    for index, row in enumerate(data.get("bonuses") or [], 1):
        if not isinstance(row, dict): continue
        if not str(row.get("id") or "").strip(): errors.append(f"Расовый бонус {index}: нет ID.")
        if not str(row.get("name") or "").strip(): errors.append(f"Расовый бонус {index}: нет названия.")
        kind = str(row.get("type") or "")
        if kind not in BONUS_TYPES: errors.append(f"Расовый бонус {index}: неизвестный тип «{kind}».")
        chance = _num(row.get("chance"))
        if chance is not None and not 0 <= chance <= 100: errors.append(f"Расовый бонус {index}: шанс должен быть 0–100.")
        if kind == "effect" and not str(row.get("effect_id") or "").strip(): errors.append(f"Расовый бонус {index}: нужен ID эффекта.")
        if kind == "formula" and not str(row.get("formula_id") or "").strip(): errors.append(f"Расовый бонус {index}: нужен ID формулы.")
    if data.get("change_allowed") and not str(data.get("change_warning_text") or "").strip():
        errors.append("Для смены расы нужен крупный текст предупреждения.")
    if data.get("change_allowed") and not data.get("change_requires_confirmation", True):
        errors.append("Смена расы обязана требовать подтверждения.")

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

    for key in ("race_name", "player_name", "system_name", "description", "full_description", "lore", "technical_description", "change_warning_text", "change_success_text", "change_denied_text"):
        value = str(data.get(key) or "")
        if value and (_HTML_RE.search(value) or "<script" in value.lower()):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def published_definition(race_id: str) -> dict[str, Any] | None:
    env = store().get(str(race_id or ""))
    return dict(env.get("data") or {}) if env and env.get("status") == STATUS_PUBLISHED else None  # noqa: F405


def registration_races() -> dict[str, dict[str, Any]]:
    out = {}
    for env in store().list(status=STATUS_PUBLISHED):  # noqa: F405
        data = env.get("data") or {}
        if data.get("registration_enabled", data.get("playable", True)) and not data.get("hidden") and not data.get("admin_only"):
            out[str(env.get("id"))] = data
    return out
