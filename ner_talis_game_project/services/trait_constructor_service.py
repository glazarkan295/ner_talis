"""Конструктор черт мобов (ТЗ «черты/благословения/фазы» §1, §3–6).

Черта — пассивное свойство/реакция моба по рангу (особая/элитная/уникальная/
мировая). Библиотека из ~50 универсальных черт сидируется через
constructor_import.import_traits. Слой данных + валидация; хранение — генерик
EntityStore (data/trait_constructor.json). Аудит и права (trait.*) — в роутере.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore

STATUS_DRAFT = "draft"
STATUS_REVIEW = "review"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_DISABLED = "disabled"
STATUS_ARCHIVE = "archive"
STATUS_ERROR = "error"

STATUSES = (STATUS_DRAFT, STATUS_REVIEW, STATUS_READY, STATUS_PUBLISHED, STATUS_DISABLED, STATUS_ARCHIVE, STATUS_ERROR)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик", STATUS_REVIEW: "На проверке", STATUS_READY: "Готов к публикации",
    STATUS_PUBLISHED: "Опубликован", STATUS_DISABLED: "Отключён", STATUS_ARCHIVE: "Архив",
    STATUS_ERROR: "Ошибка проверки",
}
TRANSITIONS: dict[str, set[str]] = {
    STATUS_DRAFT: {STATUS_REVIEW, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_REVIEW: {STATUS_DRAFT, STATUS_READY, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_READY: {STATUS_DRAFT, STATUS_PUBLISHED, STATUS_ARCHIVE, STATUS_ERROR},
    STATUS_PUBLISHED: {STATUS_DISABLED, STATUS_ARCHIVE},
    STATUS_DISABLED: {STATUS_PUBLISHED, STATUS_DRAFT, STATUS_ARCHIVE},
    STATUS_ARCHIVE: {STATUS_DRAFT},
    STATUS_ERROR: {STATUS_DRAFT, STATUS_REVIEW, STATUS_ARCHIVE},
}

# --- Справочники (ТЗ §1.1, §1.3) --------------------------------------------
TRAIT_RANKS = ("special", "elite", "unique", "world")
TRAIT_RANK_LABELS = {"special": "Особая", "elite": "Элитная", "unique": "Уникальная", "world": "Мировая"}
TRIGGERS = (
    "passive", "battle_start", "on_attack", "on_receive_damage",
    "on_turn_start", "on_turn_end", "on_death", "phase_change",
)
TRIGGER_LABELS = {
    "passive": "Пассивно", "battle_start": "В начале боя", "on_attack": "При атаке",
    "on_receive_damage": "При получении урона", "on_turn_start": "В начале хода",
    "on_turn_end": "В конце хода", "on_death": "При смерти", "phase_change": "Смена фазы",
}
STACK_RULES = ("refresh", "strongest_only", "stack_limited", "unique_only")
MOB_CATEGORIES = (
    "beast", "spirit", "undead", "mutant", "anomaly", "construct", "insect",
    "plant", "humanoid", "demon", "elemental", "ancient_guard", "bandit",
    "water", "shadow", "cursed", "boss",
)

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="TRAIT_CONSTRUCTOR_PATH",
    default_rel="data/trait_constructor.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _str(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def _has_markup(value: str) -> bool:
    return "<script" in value.lower() or bool(_HTML_RE.search(value))


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка черты (ТЗ §1.3–§1.4)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str(data, "trait_name"):
        errors.append("Не заполнено название черты.")
    rank = _str(data, "trait_rank")
    if not rank:
        errors.append("Не выбран ранг черты.")
    elif rank not in TRAIT_RANKS:
        errors.append(f"Неизвестный ранг черты: {rank}.")
    trigger = _str(data, "trigger")
    if trigger and trigger not in TRIGGERS:
        errors.append(f"Неизвестный триггер: {trigger}.")
    stack_rule = _str(data, "stack_rule")
    if stack_rule and stack_rule not in STACK_RULES:
        errors.append(f"Неизвестное правило стака: {stack_rule}.")

    cats = data.get("applicable_mob_categories")
    if isinstance(cats, list):
        for c in cats:
            if str(c) not in MOB_CATEGORIES:
                warnings.append(f"Категория «{c}» не из стандартного списка.")
        # §1.2: черта должна подходить минимум 4 категориям.
        if 0 < len(cats) < 4:
            warnings.append("Черта подходит менее чем 4 категориям мобов (ТЗ §1.2 рекомендует 4–6).")
    elif cats not in (None, ""):
        errors.append("Список категорий мобов должен быть списком.")

    for key in ("trait_name", "player_text", "admin_description"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
