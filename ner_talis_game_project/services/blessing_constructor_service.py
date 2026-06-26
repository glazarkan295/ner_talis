"""Конструктор благословений (ТЗ «черты/благословения/фазы» §8, §12.2).

Благословение — положительный временный эффект для игрока/моба/группы/зоны.
Библиотека из 19 благословений сидируется через
constructor_import.import_blessings. Слой данных + валидация; хранение —
EntityStore (data/blessing_constructor.json). Аудит/права (blessing.*) — в роутере.
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

# --- Справочники (ТЗ §8.1) --------------------------------------------------
SOURCE_TYPES = ("zone", "quest", "achievement", "event", "item", "admin", "mob_trait", "boss_phase")
SOURCE_TYPE_LABELS = {
    "zone": "Зона", "quest": "Задание", "achievement": "Достижение", "event": "Событие",
    "item": "Предмет", "admin": "Админ", "mob_trait": "Черта моба", "boss_phase": "Фаза босса",
}
ALLOWED_TARGETS = ("player", "mob", "party", "raid", "location", "city", "region")
TARGET_LABELS = {
    "player": "Игрок", "mob": "Моб", "party": "Группа", "raid": "Рейд",
    "location": "Локация", "city": "Город", "region": "Регион",
}
STACK_RULES = ("refresh", "strongest_only", "unique_only", "stack_limited")

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="BLESSING_CONSTRUCTOR_PATH",
    default_rel="data/blessing_constructor.json",
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


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not _str(data, "blessing_name"):
        errors.append("Не заполнено название благословения.")
    source = _str(data, "source_type")
    if source and source not in SOURCE_TYPES:
        errors.append(f"Неизвестный источник: {source}.")

    targets = data.get("allowed_targets")
    if isinstance(targets, list):
        for tgt in targets:
            if str(tgt) not in ALLOWED_TARGETS:
                errors.append(f"Неизвестная цель благословения: {tgt}.")
    elif targets not in (None, ""):
        errors.append("Список целей должен быть списком.")

    stack_rule = _str(data, "stack_rule")
    if stack_rule and stack_rule not in STACK_RULES:
        errors.append(f"Неизвестное правило стака: {stack_rule}.")

    bonus = data.get("bonus_values")
    if isinstance(bonus, dict):
        for key in ("flat_bonus", "percent_bonus", "duration_seconds"):
            val = _num(bonus.get(key))
            if val is not None and val < 0:
                errors.append(f"Бонус «{key}» не может быть отрицательным.")
    elif bonus not in (None, ""):
        errors.append("bonus_values должно быть объектом.")

    for key in ("blessing_name", "player_text"):
        value = _str(data, key)
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
