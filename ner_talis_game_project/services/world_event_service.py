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

# Типы повтора события (ТЗ §4.2): не только раз в год.
REPEAT_TYPES = ("none", "weekly", "monthly", "yearly")

# Типы наград мирового события (ТЗ §4.3).
REWARD_TYPES = (
    "experience", "coins", "item", "resource", "effect", "achievement",
    "special_loot", "temp_buff", "temp_debuff", "event_shop", "special_location",
)
# Источники особой добычи события (ТЗ §4.4).
SPECIAL_LOOT_SOURCES = (
    "all_mobs", "selected_mobs", "all_events", "selected_events", "locations",
    "search", "battle", "chest", "quest",
)

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

    # Повтор события (ТЗ §4.1/§4.2).
    if data.get("repeat_enabled"):
        rtype = str(data.get("repeat_type") or "").strip()
        if rtype and rtype not in REPEAT_TYPES:
            errors.append(f"Неизвестный тип повтора: {rtype}.")
        if rtype == "weekly":
            wd = _num(data.get("repeat_weekday"))
            if wd is None or wd < 0 or wd > 6:
                errors.append("День недели повтора должен быть 0–6 (Пн–Вс).")
        if rtype == "monthly":
            dom = _num(data.get("repeat_day_of_month"))
            if dom is None or dom < 1 or dom > 31:
                errors.append("День месяца повтора должен быть 1–31.")
        if rtype == "yearly":
            mon = _num(data.get("repeat_month"))
            if mon is not None and (mon < 1 or mon > 12):
                errors.append("Месяц повтора должен быть 1–12.")
        for key in ("repeat_start_hour", "repeat_end_hour"):
            val = _num(data.get(key))
            if val is not None and (val < 0 or val > 23):
                errors.append(f"Час в «{key}» должен быть 0–23.")

    # Награды события (ТЗ §4.3).
    rewards = data.get("rewards")
    if isinstance(rewards, list):
        for i, row in enumerate(rewards, 1):
            if not isinstance(row, dict):
                errors.append(f"Награда {i}: неверный формат.")
                continue
            rtype = str(row.get("type") or "").strip()
            if rtype and rtype not in REWARD_TYPES:
                errors.append(f"Награда {i}: неизвестный тип «{rtype}».")
            amt = _num(row.get("amount"))
            if amt is not None and amt < 0:
                errors.append(f"Награда {i}: количество не может быть отрицательным.")

    # Особая добыча события (ТЗ §4.4).
    special_loot = data.get("special_loot")
    if isinstance(special_loot, list):
        for i, row in enumerate(special_loot, 1):
            if not isinstance(row, dict):
                errors.append(f"Особая добыча {i}: неверный формат.")
                continue
            source = str(row.get("source") or "").strip()
            if source and source not in SPECIAL_LOOT_SOURCES:
                errors.append(f"Особая добыча {i}: неизвестный источник «{source}».")
            chance = _num(row.get("chance"))
            if chance is not None and (chance < 0 or chance > 100):
                errors.append(f"Особая добыча {i}: шанс должен быть 0–100.")
            mn = _num(row.get("min_count"))
            mx = _num(row.get("max_count"))
            if mn is not None and mx is not None and mn > mx:
                errors.append(f"Особая добыча {i}: мин. количество больше макс.")

    if not str(data.get("start_message") or "").strip():
        warnings.append("Нет сообщения о начале события.")
    if not str(data.get("end_message") or "").strip():
        warnings.append("Нет сообщения о завершении события.")

    for key in ("name", "short_description", "description"):
        value = str(data.get(key) or "").strip()
        if value and _has_markup(value):
            errors.append(f"В поле «{key}» недопустимая разметка/HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
