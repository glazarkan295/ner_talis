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
    "cooking", "repair", "disassembly", "upgrade", "purification", "camp", "service",
)
WORKSHOP_TYPE_LABELS = {
    "smeltery": "Плавильня", "forge": "Кузница", "leatherwork": "Кожевенная мастерская",
    "alchemy": "Алхимическая мастерская", "jewelry": "Ювелирная мастерская",
    "enchanting": "Чародейская мастерская", "home": "Домашняя мастерская",
    "temporary": "Временная мастерская", "event": "Событийная мастерская",
    "field": "Полевая мастерская", "npc": "NPC-мастерская",
    "cooking": "Кулинарная", "repair": "Ремонтная", "disassembly": "Разборочная",
    "upgrade": "Улучшательная", "purification": "Очищающая", "camp": "Лагерная", "service": "Служебная",
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


def published_for_action(action: str) -> dict[str, Any] | None:
    wanted = str(action or "").strip().casefold()
    for row in store().list(status=STATUS_PUBLISHED):  # noqa: F405
        data = row.get("data") or {}
        labels = {str(data.get("name") or ""), str(data.get("player_name") or ""), str(data.get("button_text") or "")}
        if wanted and wanted in {label.strip().casefold() for label in labels if label.strip()}:
            return {"id": row.get("id"), **data}
    return None


def player_has_access(player: dict[str, Any], workshop: dict[str, Any]) -> tuple[bool, str]:
    level = int(player.get("level") or 1)
    if level < int(workshop.get("min_level") or 0):
        return False, str(workshop.get("access_denied_text") or "Недостаточный уровень для мастерской.")
    inventory_ids = {str(row.get("item_id") or row.get("id") or "") for row in player.get("inventory") or [] if isinstance(row, dict)}
    required_item = str(workshop.get("required_item_id") or "")
    if required_item and required_item not in inventory_ids:
        return False, str(workshop.get("access_denied_text") or "Для мастерской требуется специальный предмет.")
    if workshop.get("requires_no_fine") and (player.get("active_fines") or player.get("fines")):
        return False, str(workshop.get("access_denied_text") or "Мастерская недоступна при активном штрафе.")
    for field, state_key in (("required_quest_id", "completed_quests"), ("required_achievement_id", "achievements"), ("required_npc_id", "known_npcs")):
        required = str(workshop.get(field) or "")
        state = player.get(state_key) or []
        if isinstance(state, dict):
            state = state.keys()
        if required and required not in {str(x) for x in state}:
            return False, str(workshop.get("access_denied_text") or "Условие доступа к мастерской не выполнено.")
    reputation_id = str(workshop.get("required_reputation_id") or "")
    if reputation_id and int((player.get("reputation") or {}).get(reputation_id, 0)) < int(workshop.get("min_reputation") or 0):
        return False, str(workshop.get("access_denied_text") or "Недостаточная репутация для мастерской.")
    locations = {str(x) for x in workshop.get("locations") or []}
    if workshop.get("location"):
        locations.add(str(workshop["location"]))
    current = str(player.get("current_location") or player.get("current_zone") or "")
    if locations and current not in locations:
        return False, str(workshop.get("access_denied_text") or "Мастерская недоступна в текущем месте.")
    return True, ""
