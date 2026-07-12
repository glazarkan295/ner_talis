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
    "block_quests", "block_npc", "block_delivery", "block_trade", "block_craft", "block_transitions", "block_event", "force_fortress", "raise_guard_check", "raise_raid_chance",
    "debuff", "debtor_mark",
)
# --- ТЗ 2.0 (файл 10 ч.1): стадии, оплата и снятие --------------------------
# Стадии штрафа (§9): первый/второй/третий/бессрочный/особая/админская.
FINE_STAGES = ("first", "second", "third", "permanent", "special", "admin")
FINE_STAGE_LABELS = {
    "first": "Первый штраф", "second": "Второй штраф", "third": "Третий штраф",
    "permanent": "Бессрочный штраф", "special": "Особая стадия", "admin": "Админская стадия",
}
# Места оплаты (§14).
PAYMENT_PLACES = ("npc", "city", "fortress", "profile", "button", "admin")
PAYMENT_PLACE_LABELS = {
    "npc": "У NPC", "city": "В городе", "fortress": "В крепости",
    "profile": "Через профиль", "button": "Через кнопку", "admin": "Через админку",
}
# Способы снятия (§14).
REMOVAL_METHODS = (
    "auto_after_payment", "after_term", "via_npc", "via_quest", "via_event",
    "admin", "delete_admin", "mass_old",
)
REMOVAL_METHOD_LABELS = {
    "auto_after_payment": "Автоматически после оплаты", "after_term": "После срока",
    "via_npc": "Через NPC", "via_quest": "Через квест", "via_event": "Через событие",
    "admin": "Через админ-панель", "delete_admin": "Удаление админом",
    "mass_old": "Массовое снятие старых",
}

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
    formula_id = str(data.get("amount_formula_id") or "").strip()
    if formula_id:
        from services import formula_constructor_service as formulas
        formula = formulas.store().get(formula_id)
        if not formula:
            errors.append(f"Формула суммы {formula_id} не найдена.")
        elif formula.get("status") != formulas.STATUS_PUBLISHED:
            errors.append(f"Формула суммы {formula_id} не опубликована.")

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

    # Стадии штрафа (ТЗ 2.0 §9-§10).
    for i, st in enumerate(data.get("stages") or [], start=1):
        if not isinstance(st, dict):
            continue
        skey = str(st.get("stage") or "").strip()
        if skey and skey not in FINE_STAGES:
            warnings.append(f"Стадия #{i}: «{skey}» не из списка.")
        for fkey, flabel in (("duration_days", "срок (дней)"),
                             ("base_amount", "базовая сумма"),
                             ("per_day_increase", "увеличение за день")):
            if st.get(fkey) not in (None, "") and (_num(st.get(fkey)) is None or _num(st.get(fkey)) < 0):
                errors.append(f"Стадия #{i}: {flabel} — неотрицательное число.")
        if st.get("percent_increase") not in (None, ""):
            pct = _num(st.get("percent_increase"))
            if pct is None or pct < 0 or pct > 1000:
                errors.append(f"Стадия #{i}: процент увеличения должен быть 0–1000.")
        # Перенос в крепость требует указания крепости (§19).
        if st.get("force_fortress") and not str(st.get("fortress_id") or data.get("fortress_id") or "").strip():
            warnings.append(f"Стадия #{i}: перенос в крепость включён, но крепость не указана.")
        if st.get("block_city") and not str(st.get("city_id") or data.get("city_id") or "").strip():
            warnings.append(f"Стадия #{i}: блокирует город, но город не указан.")

    # Оплата и снятие (ТЗ 2.0 §14).
    for place in (data.get("payment_places") or []):
        if str(place or "").strip() and str(place).strip() not in PAYMENT_PLACES:
            warnings.append(f"Место оплаты «{place}» не из списка.")
    if "npc" in (data.get("payment_places") or []) and not str(data.get("payment_npc_id") or "").strip():
        warnings.append("Оплата у NPC включена, но NPC оплаты не указан (§19).")
    if data.get("payment_commission") not in (None, "") and (_num(data.get("payment_commission")) is None or _num(data.get("payment_commission")) < 0):
        errors.append("Комиссия оплаты — неотрицательное число.")
    if data.get("payment_formula_id"):
        from services import formula_constructor_service as formulas
        formula=formulas.store().get(str(data["payment_formula_id"]));
        if not formula or formula.get("status")!=formulas.STATUS_PUBLISHED:errors.append("Формула оплаты не найдена или не опубликована.")
    for method in (data.get("removal_methods") or []):
        if str(method or "").strip() and str(method).strip() not in REMOVAL_METHODS:
            warnings.append(f"Способ снятия «{method}» не из списка.")
    # Бессрочный без способа снятия — предупреждение (§19), если явно не разрешено.
    if data.get("can_become_permanent") and not (data.get("removal_methods") or []) and not data.get("permanent_no_removal_allowed"):
        warnings.append("Штраф может стать бессрочным, но не задан способ снятия (§19).")

    # Безопасность текстов (§16): без HTML/скриптов. messages — словарь текстов.
    text_fields = [str(data.get(k) or "") for k in ("name", "short_description", "description")]
    messages = data.get("messages")
    if isinstance(messages, dict):
        text_fields.extend(str(v or "") for v in messages.values())
    for value in text_fields:
        if value and _has_markup(value):
            errors.append("В текстах штрафа недопустима разметка/HTML.")
            break

    # Вывод уведомления игроку (дополнение к ТЗ): изображение/формат/блоки.
    issue_message = data.get("issue_message")
    if issue_message:
        from services.message_output_service import validate_message_output
        result = validate_message_output(issue_message)
        errors.extend(f"Уведомление о штрафе — {e}" for e in result["errors"])
        warnings.extend(f"Уведомление о штрафе — {w}" for w in result["warnings"])

    return {"ok": not errors, "errors": errors, "warnings": warnings}
