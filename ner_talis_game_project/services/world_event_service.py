"""Мировые события V2 (ТЗ «Мировые события»). Слой данных + валидация.

Хранение через генерик EntityStore (data/world_events.json). Аудит и права — в
роутере (admin_community_api). Этапы/глобальный прогресс/событийные магазины/
рассылки/рейтинги — на вырост (поля хранятся в data как есть, runtime позже).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.admin_entity_store import EntityStore

# --- Статусы жизненного цикла события ---------------------------------------
STATUS_DRAFT = "draft"
STATUS_SCHEDULED = "scheduled"
STATUS_ACTIVE = "active"
STATUS_FINISHED = "finished"
STATUS_DISABLED = "disabled"
STATUS_ARCHIVE = "archive"

STATUSES = (
    STATUS_DRAFT, STATUS_SCHEDULED, STATUS_ACTIVE,
    STATUS_FINISHED, STATUS_DISABLED, STATUS_ARCHIVE,
)
STATUS_LABELS = {
    STATUS_DRAFT: "Черновик",
    STATUS_SCHEDULED: "Запланировано",
    STATUS_ACTIVE: "Активно",
    STATUS_FINISHED: "Завершено",
    STATUS_DISABLED: "Отключено",
    STATUS_ARCHIVE: "Архив",
}
TRANSITIONS: dict[str, set[str]] = {
    # Старт можно дать сразу из черновика (быстрый запуск админом), не только
    # после планирования.
    STATUS_DRAFT: {STATUS_SCHEDULED, STATUS_ACTIVE, STATUS_ARCHIVE},
    STATUS_SCHEDULED: {STATUS_ACTIVE, STATUS_DISABLED, STATUS_DRAFT, STATUS_ARCHIVE},
    STATUS_ACTIVE: {STATUS_FINISHED, STATUS_DISABLED, STATUS_ARCHIVE},
    STATUS_FINISHED: {STATUS_ARCHIVE},
    STATUS_DISABLED: {STATUS_SCHEDULED, STATUS_ACTIVE, STATUS_ARCHIVE},
    STATUS_ARCHIVE: set(),
}

EVENT_TYPES = (
    "festive", "seasonal", "permanent", "threat", "world_boss", "global_raid",
    "mob_invasion", "fair", "city", "guild", "story", "economic",
    "boosted_drop", "boosted_exp", "new_location",
)
# Лимиты временных множителей мира (ТЗ §15) — превышение блокирует публикацию.
MAX_WORLD_MULTIPLIER = 5.0

_store = EntityStore(
    env_var="WORLD_EVENTS_PATH",
    default_rel="data/world_events.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or ("<" in value and ">" in value)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка события перед запуском (ТЗ §19, применимая часть)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название события.")
    ev_type = str(data.get("type") or "").strip()
    if ev_type and ev_type not in EVENT_TYPES:
        errors.append(f"Неизвестный тип события: {ev_type}.")

    start = _parse_date(data.get("start_date"))
    end = _parse_date(data.get("end_date"))
    if data.get("start_date") and start is None:
        errors.append("Некорректная дата начала.")
    if data.get("end_date") and end is None:
        errors.append("Некорректная дата окончания.")
    if start and end and end <= start:
        errors.append("Дата окончания должна быть позже даты начала.")
    if not data.get("start_date"):
        warnings.append("Не указана дата начала.")

    # Временные множители мира не должны превышать лимит.
    for key in ("exp_multiplier", "drop_multiplier", "coin_multiplier"):
        value = _num(data.get(key))
        if value is None:
            continue
        if value < 0:
            errors.append(f"Множитель «{key}» не может быть отрицательным.")
        elif value > MAX_WORLD_MULTIPLIER:
            errors.append(f"Множитель «{key}» превышает лимит ({MAX_WORLD_MULTIPLIER}).")

    if not str(data.get("start_message") or "").strip():
        warnings.append("Нет сообщения о начале события.")
    if not str(data.get("end_message") or "").strip():
        warnings.append("Нет сообщения о завершении события.")

    for key in ("name", "short_description", "description"):
        value = str(data.get(key) or "").strip()
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
