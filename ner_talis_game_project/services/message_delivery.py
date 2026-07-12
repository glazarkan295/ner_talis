"""Мост мгновенной доставки: маршрутизация сообщений игроку + живой отправитель.

Правило одного пути (без дублей):
* если диспетчер включён (ENV BOT_MESSAGE_DISPATCHER_ENABLED) и у игрока есть
  адрес доставки → кладём в исходящую очередь (bot_message_queue) — мгновенная
  доставка фоновым диспетчером;
* иначе → старый per-player outbox (pending_bot_messages), доставка при
  следующем действии игрока (запасной путь).

Живой отправитель регистрируется процессом бота по платформам
(register_platform_sender) и используется диспетчером. По умолчанию (флаг выкл.)
поведение системы не меняется.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from services import bot_message_queue as mq

logger = logging.getLogger(__name__)


def dispatcher_enabled() -> bool:
    return str(os.getenv("BOT_MESSAGE_DISPATCHER_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}


def resolve_recipient(player: dict[str, Any] | None) -> tuple[str, str]:
    """Платформа + адрес доставки из профиля игрока (ТЗ §12–13)."""
    if not isinstance(player, dict):
        return "", ""
    linked = player.get("linked_accounts") if isinstance(player.get("linked_accounts"), dict) else {}
    platform = str(player.get("main_platform") or "").strip()
    if platform and linked.get(platform):
        return platform, str(linked.get(platform))
    for plat in ("telegram", "vk"):
        if linked.get(plat):
            return plat, str(linked.get(plat))
    return "", ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def notify_player(
    storage: Any,
    game_id: str,
    text: str,
    *,
    type: str = "system",
    priority: str = mq.PRIORITY_NORMAL,
    delivery_key: str | None = None,
    source: str = "",
    operation_id: str | None = None,
    fallback_message: dict[str, Any] | None = None,
    text_key: str | None = None,
    text_variables: dict[str, Any] | None = None,
    buttons: Any = None,
    attachments: Any = None,
    source_id: str = "",
) -> str:
    """Отправить сообщение игроку правильным путём.

    ``text_key`` включает опубликованный текст конструктора с платформенным
    вариантом и подстановкой переменных; ``text`` остаётся безопасным fallback.
    Возвращает 'queued'/'pending'/'skipped'.
    """
    game_id = str(game_id or "")
    player = None
    platform = ""
    recipient = ""
    if game_id and hasattr(storage, "get_player_by_game_id"):
        try:
            player = storage.get_player_by_game_id(game_id)
        except Exception:
            player = None
        platform, recipient = resolve_recipient(player) if player else ("", "")
    if text_key:
        try:
            from services.text_runtime import get_text
            text = get_text(text_key, platform=platform or "both", variables=text_variables, default=text)
        except Exception:
            logger.exception("Failed to render constructor text %s", text_key)
    if fallback_message is not None:
        fallback_message = {**fallback_message, "text": text, "text_key": text_key or fallback_message.get("text_key", "")}
    if dispatcher_enabled() and game_id:
        if recipient:
            mq.bind_pending_recipient(game_id,platform,recipient)
        if recipient or game_id:
            try:
                from services.message_queue_rule_service import resolve_rule
                rule = resolve_rule(type, source=source, platform=platform)
            except Exception:
                rule = {}
            template=str(rule.get("message_template") or "")
            if template:
                values={"message":text,"game_id":game_id,"player_name":str((player or {}).get("name") or ""),"source_name":source,"amount":"","item_name":"","error":"","date":datetime.now().strftime("%d.%m.%Y"),"time":datetime.now().strftime("%H:%M")}
                for key,value in values.items():template=template.replace("{{"+key+"}}",str(value)).replace("{{ "+key+" }}",str(value))
                text=template
            raw_priority = rule.get("priority")
            send_mode=str(rule.get("send_mode") or "immediate")
            if raw_priority == 0 or send_mode in ("after_next_message","after_player_action") or rule.get("hide_until_condition"):initial=mq.STATUS_WAIT_ACTION
            elif send_mode=="after_battle":initial=mq.STATUS_WAIT_BATTLE
            elif send_mode=="after_event":initial=mq.STATUS_WAIT_EVENT
            elif send_mode in ("after_timer","at_time") or (rule and raw_priority in (None,"")):initial=mq.STATUS_WAIT_TIMER
            else:initial=mq.STATUS_QUEUED
            if not recipient:initial=mq.STATUS_NOTIFICATION_PENDING
            if True:
                if raw_priority not in (None, ""):
                    try:
                        numeric = int(raw_priority)
                        priority = mq.PRIORITY_HIGH if numeric <= 1 else (mq.PRIORITY_NORMAL if numeric == 2 else mq.PRIORITY_LOW)
                    except (TypeError, ValueError):
                        pass
                delay = int(rule.get("timer_seconds") or 1) if initial==mq.STATUS_WAIT_TIMER else 0
                attempts = int(rule.get("max_retries") or 0) + 1 if rule.get("repeat_on_error") else mq.DEFAULT_MAX_ATTEMPTS
                mq.enqueue(
                    game_id=game_id, platform=platform, recipient=recipient, text=text,
                    type=type, priority=priority, delivery_key=delivery_key,
                    source=source, operation_id=operation_id, max_attempts=attempts,
                    delay_seconds=delay, ttl_seconds=int(rule.get("ttl_seconds") or 0),
                    initial_status=initial,buttons=buttons if buttons is not None else rule.get("buttons"),attachments=attachments or rule.get("image_path"),
                    group_key=f"{game_id}:{type}:{source}" if rule.get("group_enabled") else "",
                    group_header=str(rule.get("group_header") or ""),group_footer=str(rule.get("group_footer") or ""),
                    max_in_group=int(rule.get("max_in_group") or 0),source_id=source_id,
                    send_at=str(rule.get("send_at") or "") if send_mode=="at_time" else "",
                    retry_interval_seconds=int(rule.get("retry_interval_seconds") or 0),delete_after_ttl=bool(rule.get("delete_after_ttl")),
                )
                return "pending" if initial in (mq.STATUS_NOTIFICATION_PENDING,mq.STATUS_WAIT_ACTION) else "queued"
    # Запасной путь — per-player outbox (доставка при следующем действии).
    enqueue = getattr(storage, "enqueue_bot_messages", None)
    if callable(enqueue):
        msg = fallback_message or {"type": type, "text": text, "created_at": _now_iso(), "source": source, "text_key": text_key or ""}
        if 'rule' in locals() and rule:
            msg = {**msg, "queue_rule_id": rule.get("id"), "send_mode": rule.get("send_mode"), "priority": rule.get("priority")}
        enqueue(game_id, [msg])
        return "pending"
    return "skipped"


# --- Живой отправитель (регистрируется процессом бота) -----------------------
_platform_senders: dict[str, Callable[[str, str], None]] = {}
_lock = threading.Lock()
_dispatcher_started = False

# Маркеры «постоянной» ошибки доставки → статус blocked (не повторять бесконечно).
_BLOCKED_MARKERS = (
    "blocked", "bot was blocked", "forbidden", "can't write", "cant write",
    "cannot send messages", "chat not found", "user not found", "peer not found",
    "allowed_from_group", "not allowed", "privacy", "deactivated",
)


def classify_error(exc: Exception) -> tuple[str, str]:
    text = str(exc).lower()
    if any(marker in text for marker in _BLOCKED_MARKERS):
        return mq.RESULT_BLOCKED, str(exc)
    return mq.RESULT_FAILED_TEMPORARY, str(exc)


def _combined_sender(message: dict[str, Any]) -> tuple[str, str]:
    platform = str(message.get("platform") or "")
    recipient = str(message.get("recipient") or "")
    text = message.get("text") or ""
    if not recipient:
        return mq.RESULT_FAILED_PERMANENT, "Нет получателя."
    fn = _platform_senders.get(platform)
    if fn is None:
        return mq.RESULT_FAILED_TEMPORARY, f"Нет отправителя для платформы {platform}."
    try:
        fn(recipient, text)
    except Exception as exc:  # noqa: BLE001
        return classify_error(exc)
    return mq.RESULT_SENT, ""


def register_platform_sender(platform: str, send_fn: Callable[[str, str], None]) -> None:
    """Подключить реальный отправитель платформы (telegram/vk)."""
    with _lock:
        _platform_senders[str(platform)] = send_fn
    mq.set_sender(_combined_sender)
    logger.info("Registered bot message sender for platform %s", platform)


def registered_platforms() -> list[str]:
    """Платформы, для которых в ЭТОМ процессе есть отправитель."""
    with _lock:
        return [p for p in _platform_senders.keys()]


def start_message_dispatcher(interval_seconds: int = 5) -> bool:
    """Запустить фоновый цикл диспетчера один раз (демон-поток)."""
    global _dispatcher_started
    with _lock:
        if _dispatcher_started:
            return False
        _dispatcher_started = True

    def _loop() -> None:
        while True:
            try:
                # Клеймим только сообщения платформ, для которых в этом процессе
                # есть отправитель — иначе процесс одной платформы жёг бы попытки
                # чужим сообщениям (Codex P2).
                mq.dispatch_once(platforms=registered_platforms())
            except Exception:  # noqa: BLE001
                logger.exception("Bot message dispatch tick failed")
            time.sleep(max(1, int(interval_seconds)))

    thread = threading.Thread(target=_loop, name="bot-message-dispatcher", daemon=True)
    thread.start()
    logger.info("Bot message dispatcher loop started (interval=%ss)", interval_seconds)
    return True
