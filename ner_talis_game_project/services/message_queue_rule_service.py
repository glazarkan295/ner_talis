"""Конструктор правил очереди и приоритета сообщений (ТЗ 2.0, файл 18).

Запись = правило очереди: для типа/источника сообщения задаёт приоритет, канал,
режим отправки, группировку, повторную доставку и срок жизни. Это авторский слой
поверх рантайма bot_message_queue (который уже ранжирует и группирует сообщения);
здесь админ описывает правила приоритета без правки кода.

Приоритет — число (§5): 1 — боевые/критичные, 2 — достижения/награды, 3 —
рассылки/инфо, 0 — ждать следующего сообщения/действия игрока, пусто (None) —
отправка после внутреннего таймера независимо от очереди.

Хранение — EntityStore (data/message_queue_rules.json).
"""

from __future__ import annotations

import re
from typing import Any

from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403 - статусы конструктора

_HTML_RE = re.compile(r"<[^>]+>")

# Типы сообщений (§4).
MESSAGE_TYPES = (
    "combat", "combat_turn", "combat_result", "achievement", "reward", "quest",
    "event", "world_event", "arena_event", "penalty", "delivery", "transfer",
    "promo", "broadcast", "registration", "referral", "economy", "profile",
    "site", "npc", "system", "admin", "error",
)
# Источники (§7).
SOURCE_TYPES = (
    "battle", "skill", "item", "effect", "event", "quest", "achievement",
    "penalty", "promo", "broadcast", "delivery", "transfer", "economy",
    "registration", "referral", "profile", "site", "npc", "city", "fortress",
    "tavern", "casino", "world_event", "admin",
)
# Режимы отправки/таймеры (§9).
SEND_MODES = (
    "immediate", "after_timer", "after_player_action", "after_battle",
    "after_event", "at_time", "after_next_message", "batch",
)
SEND_MODE_LABELS = {
    "immediate": "Сразу", "after_timer": "После таймера",
    "after_player_action": "После действия игрока", "after_battle": "После боя",
    "after_event": "После события", "at_time": "В указанное время",
    "after_next_message": "После следующего сообщения игрока", "batch": "Пачкой",
}
PLATFORMS = ("telegram", "vk", "both")
# Специальные значения приоритета (§5).
PRIORITY_WAIT_NEXT = 0

_store = EntityStore(
    env_var="MESSAGE_QUEUE_RULES_PATH",
    default_rel="data/message_queue_rules.json",
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


def _has_html(value: Any) -> bool:
    s = str(value or "")
    return bool(_HTML_RE.search(s)) or "<script" in s.lower()


def validate(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") or {}
    errors: list[str] = []
    warnings: list[str] = []

    if not str(data.get("name") or "").strip():
        errors.append("Не заполнено название правила очереди.")

    mtype = str(data.get("message_type") or "").strip()
    if not mtype:
        errors.append("Не выбран тип сообщения.")
    elif mtype not in MESSAGE_TYPES:
        errors.append(f"Неизвестный тип сообщения: {mtype}.")

    source = str(data.get("source") or "").strip()
    if source and source not in SOURCE_TYPES:
        warnings.append(f"Источник «{source}» не из списка.")

    # Приоритет (§5/§15): число ≥ 0; пусто = после таймера (разрешено).
    if data.get("priority") not in (None, ""):
        prio = _num(data.get("priority"))
        if prio is None:
            errors.append("Приоритет — не число.")
        elif prio < 0:
            errors.append("Приоритет не может быть отрицательным (0 — спец-значение «ждать сообщения»).")

    send_mode = str(data.get("send_mode") or "").strip()
    if send_mode and send_mode not in SEND_MODES:
        warnings.append(f"Режим отправки «{send_mode}» не из списка.")
    if send_mode == "at_time" and data.get("send_at") in (None, ""):
        warnings.append("Режим «в указанное время», но время отправки не задано.")

    platform = str(data.get("platform") or "").strip()
    if platform and platform not in PLATFORMS:
        errors.append(f"Неизвестная платформа: {platform}.")

    # Таймеры (§9): неотрицательные.
    for key, label in (("timer_seconds", "таймер"), ("ttl_seconds", "срок жизни"),
                       ("max_in_group", "макс. сообщений в группе")):
        if data.get(key) not in (None, "") and (_num(data.get(key)) is None or _num(data.get(key)) < 0):
            errors.append(f"{label.capitalize()}: неотрицательное число.")

    # Повторная доставка (§12/§15): при включении нужен лимит попыток.
    if data.get("repeat_on_error"):
        retries = _num(data.get("max_retries"))
        if retries is None or retries <= 0:
            errors.append("Повторная доставка включена, но не задан лимит попыток (§15).")
        if data.get("retry_interval_seconds") not in (None, "") and (_num(data.get("retry_interval_seconds")) is None or _num(data.get("retry_interval_seconds")) < 0):
            errors.append("Интервал повторов — неотрицательное число.")

    # Предупреждения §15.
    prio_num = _num(data.get("priority"))
    if mtype == "broadcast" and prio_num is not None and prio_num <= 1:
        warnings.append("Массовая рассылка имеет слишком высокий приоритет (перебьёт бой).")
    if mtype in ("combat", "combat_turn", "combat_result") and data.get("priority") in (None, ""):
        warnings.append("Боевое сообщение без приоритета (обычно приоритет 1).")
    if mtype in ("reward", "achievement") and not data.get("group_enabled"):
        warnings.append("Сообщение награды/достижения не группируется (§15).")
    if not str(data.get("error_text") or "").strip() and data.get("repeat_on_error"):
        warnings.append("Нет текста ошибки доставки (§15).")

    # Тексты без HTML.
    for key in ("name", "description"):
        if _has_html(data.get(key)):
            errors.append(f"В поле «{key}» недопустим HTML.")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def preview(data: dict[str, Any]) -> dict[str, Any]:
    """Краткое описание правила очереди для админа."""
    data = data or {}
    prio = data.get("priority")
    prio_label = "после таймера" if prio in (None, "") else ("ждать сообщения" if _num(prio) == 0 else str(prio))
    return {
        "name": data.get("name") or "Правило очереди",
        "message_type": data.get("message_type"),
        "source": data.get("source"),
        "priority": prio_label,
        "send_mode": SEND_MODE_LABELS.get(str(data.get("send_mode") or ""), str(data.get("send_mode") or "—")),
        "platform": data.get("platform") or "both",
        "group_enabled": bool(data.get("group_enabled")),
        "repeat_on_error": bool(data.get("repeat_on_error")),
    }
