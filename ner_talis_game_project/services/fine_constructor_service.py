"""Конструктор штрафов V2 (ТЗ «Конструктор штрафов») — авторская часть.

Здесь админ задаёт ТИПЫ штрафов (шаблоны): сумма/сроки/проценты/ограничения/
сообщения. Это слой данных + валидация; рантайм активных штрафов на игроке —
в services/fine_service.py (создание/оплата/снятие/починка). Хранение — генерик
EntityStore (data/fine_constructor.json). Аудит и права — в роутере
(admin_fines_api) через admin_operation.
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore

# --- Статусы (как у остальных конструкторов) --------------------------------
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

# --- Справочники (ТЗ §5–§13) ------------------------------------------------
FINE_TYPES = (  # §5
    "city", "raid", "chat_rules", "mechanic_abuse", "criminal", "obligation",
    "overdue", "assault", "illegal_trade", "forbidden_service", "manual",
    "system", "story",
)
FINE_SOURCES = (  # §6
    "black_market_raid", "informer_raid", "casino_raid", "guard_decision",
    "manager_decision", "admin_decision", "auto_moderation", "player_moderator",
    "player_report", "chat_violation", "trade_violation", "location_event",
    "story_event", "quest_fail", "contract_violation", "system_check",
)
ISSUER_ROLES = (  # §7
    "system", "admin", "senior_admin", "moderator", "player_moderator",
    "guard", "manager", "npc", "event", "location_script",
)
CURRENCIES = ("copper", "silver", "gold", "magic_gold", "ancient")  # §10
RESTRICTIONS = (  # §13
    "block_city", "block_starting", "block_market", "block_black_market",
    "block_casino", "block_transfer", "block_chat", "block_raids",
    "block_quests", "force_fortress", "raise_guard_check", "raise_raid_chance",
    "debuff", "debtor_mark",
)

_HTML_RE = re.compile(r"<[^>]+>")

_store = EntityStore(
    env_var="FINE_CONSTRUCTOR_PATH",
    default_rel="data/fine_constructor.json",
    statuses=STATUSES,
    transitions=TRANSITIONS,
    initial_status=STATUS_DRAFT,
)


def store() -> EntityStore:
    return _store


def _has_markup(value: str) -> bool:
    low = value.lower()
    return "<script" in low or bool(_HTML_RE.search(value))


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Проверка типа штрафа перед публикацией (ТЗ §16)."""
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название штрафа.")

    ftype = str(data.get("type") or "").strip()
    if ftype and ftype not in FINE_TYPES:
        errors.append(f"Неизвестный тип штрафа: {ftype}.")
    source = str(data.get("source") or "").strip()
    if source and source not in FINE_SOURCES:
        errors.append(f"Неизвестный источник: {source}.")
    currency = str(data.get("currency") or "copper").strip()
    if currency and currency not in CURRENCIES:
        errors.append(f"Неизвестная валюта: {currency}.")

    # Суммы (§10).
    base = _num(data.get("base_amount"))
    if base is None:
        errors.append("Базовая сумма — не число.")
    elif base < 0:
        errors.append("Базовая сумма не может быть отрицательной.")
    amin = _num(data.get("min_amount"))
    amax = _num(data.get("max_amount"))
    if amin is not None and amin < 0:
        errors.append("Минимальная сумма не может быть отрицательной.")
    if amin is not None and amax is not None and amin > amax:
        errors.append("Минимальная сумма больше максимальной.")

    # Сроки (§11) — неотрицательные дни.
    for key in ("first_deadline_days", "second_deadline_days", "interest_start_day", "restriction_start_day"):
        value = data.get(key)
        if value in (None, ""):
            continue
        num = _num(value)
        if num is None:
            errors.append(f"Поле «{key}» — не число.")
        elif num < 0:
            errors.append(f"Поле «{key}» не может быть отрицательным.")

    # Проценты (§12) — 0..100.
    if data.get("interest_enabled"):
        pct = _num(data.get("interest_percent_per_day"))
        if pct is None:
            errors.append("Процент в день — не число.")
        elif pct < 0 or pct > 100:
            errors.append("Процент в день должен быть 0–100.")

    # Ограничения (§13).
    restrictions = data.get("restrictions")
    if restrictions not in (None, ""):
        if not isinstance(restrictions, list):
            errors.append("Ограничения должны быть списком.")
        else:
            for r in restrictions:
                code = r.get("code") if isinstance(r, dict) else r
                if str(code) not in RESTRICTIONS:
                    errors.append(f"Неизвестное ограничение: {code}.")

    issuer_roles = data.get("issuer_roles")
    if isinstance(issuer_roles, list):
        for role in issuer_roles:
            if str(role) not in ISSUER_ROLES:
                errors.append(f"Неизвестная роль выдающего: {role}.")

    # Безопасность текстов (§16): без HTML/скриптов. messages — словарь текстов.
    text_fields = [str(data.get(k) or "") for k in ("name", "short_description", "description")]
    messages = data.get("messages")
    if isinstance(messages, dict):
        text_fields.extend(str(v or "") for v in messages.values())
    for value in text_fields:
        if value and _has_markup(value):
            errors.append("В текстах штрафа недопустима разметка/HTML.")
            break

    return {"ok": not errors, "errors": errors, "warnings": warnings}
