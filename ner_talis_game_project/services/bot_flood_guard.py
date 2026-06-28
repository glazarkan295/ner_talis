"""Защита входящих сообщений ботов (ТЗ 08 §7): антифлуд, дедупликация, лимит длины.

Чистый процесс-локальный слой без I/O — поэтому годится и для async Telegram, и
для sync VK, и легко тестируется (можно передавать ``now``).

* clamp_incoming_text — обрезать слишком длинный входящий текст ДО логирования и
  игровой логики;
* is_duplicate_event — отсечь повтор события по update_id/message_id/event_id
  (окно ~10 минут), чтобы повтор не запускал игровую логику дважды;
* allow_message — пер-пользовательский лимит частоты + глобальный лимит (мягкий
  отказ при превышении);
* guard_incoming — единая проверка (дубликат → reason=duplicate, флуд →
  reason=flood, иначе allowed).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

# Лимиты (ТЗ 08 §7.2): ~5–8 сообщений за 10 с на пользователя + глобальный.
PER_USER_LIMIT = 7
PER_USER_WINDOW = 10.0
GLOBAL_LIMIT = 300
GLOBAL_WINDOW = 10.0
DEDUP_TTL = 600.0  # помним события 10 минут
MAX_INCOMING_TEXT = 1000  # символов

_lock = threading.Lock()
_user_hits: dict[str, deque[float]] = {}
_global_hits: deque[float] = deque()
_seen_events: dict[str, float] = {}


def _now() -> float:
    return time.monotonic()


def clamp_incoming_text(text: Any, limit: int = MAX_INCOMING_TEXT) -> str:
    """Обрезать входящий текст до лимита (огромные сообщения не идут в лог/логику)."""
    s = str(text or "")
    return s if len(s) <= max(1, int(limit)) else s[: max(1, int(limit))]


def _trim(q: deque[float], cutoff: float) -> None:
    while q and q[0] < cutoff:
        q.popleft()


def _purge_seen(now: float) -> None:
    if len(_seen_events) > 4096:  # не даём словарю расти бесконечно
        for key in [k for k, exp in _seen_events.items() if exp <= now]:
            _seen_events.pop(key, None)


def is_duplicate_event(platform: str, event_id: Any, *, scope: Any = None, now: float | None = None) -> bool:
    """True, если событие с таким id уже встречалось в окне DEDUP_TTL.

    scope — peer/user (15-CODEX §2): id события у некоторых платформ уникален
    только внутри диалога (VK conversation_message_id), поэтому ключ должен
    включать peer, иначе событие одного пользователя «съест» событие другого с
    тем же id. Без scope — старое поведение (глобально по платформе)."""
    eid = str(event_id or "").strip()
    if not eid:
        return False
    scope_s = str(scope or "").strip()
    key = f"{platform}:{scope_s}:{eid}" if scope_s else f"{platform}:{eid}"
    now = _now() if now is None else now
    with _lock:
        _purge_seen(now)
        exp = _seen_events.get(key)
        if exp is not None and exp > now:
            return True
        _seen_events[key] = now + DEDUP_TTL
        return False


def allow_message(platform: str, user_id: Any, *, now: float | None = None) -> bool:
    """False при превышении пер-пользовательского или глобального лимита частоты."""
    now = _now() if now is None else now
    ukey = f"{platform}:{user_id}"
    with _lock:
        uq = _user_hits.setdefault(ukey, deque())
        _trim(uq, now - PER_USER_WINDOW)
        if len(uq) >= PER_USER_LIMIT:
            return False
        _trim(_global_hits, now - GLOBAL_WINDOW)
        if len(_global_hits) >= GLOBAL_LIMIT:
            return False
        uq.append(now)
        _global_hits.append(now)
        return True


def guard_incoming(platform: str, user_id: Any, event_id: Any = "", *, now: float | None = None) -> dict[str, Any]:
    """Единая проверка входящего: дубликат → тихо отклонить; флуд → мягкий отказ.

    Дедуп скоупится по user_id/peer (15-CODEX §2): разные пользователи с
    одинаковым id события (VK) не конфликтуют."""
    if is_duplicate_event(platform, event_id, scope=user_id, now=now):
        return {"allowed": False, "reason": "duplicate"}
    if not allow_message(platform, user_id, now=now):
        return {"allowed": False, "reason": "flood"}
    # 16-TZ §3: при общем backend (Redis) дополнительно применяем кросс-процессный
    # пер-пользовательский лимит, чтобы флуд нельзя было размазать по воркерам.
    # Без Redis (dev) ветка не входит — поведение прежнее, процесс-локальное.
    try:
        from services import shared_rate_limit

        if shared_rate_limit.shared_active():
            if not shared_rate_limit.allow(f"bot:{platform}:{user_id}", PER_USER_LIMIT, PER_USER_WINDOW):
                return {"allowed": False, "reason": "flood"}
    except Exception:
        pass
    return {"allowed": True, "reason": None}


def reset() -> None:
    """Сброс состояния (для тестов)."""
    with _lock:
        _user_hits.clear()
        _global_hits.clear()
        _seen_events.clear()
