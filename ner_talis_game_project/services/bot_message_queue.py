"""Исходящая очередь сообщений бота (ТЗ «Мгновенная доставка сообщений»).

Глобальная очередь немедленной доставки: система/админ кладёт сообщение, фоновый
диспетчер сразу берёт его и шлёт в Telegram/VK. В отличие от per-player
``pending_bot_messages`` (запасной путь — доставка при следующем действии),
здесь сообщение живёт со статусом, попытками, дедупликацией и приоритетом.

Реальная отправка инкапсулирована в «sender» (set_sender) — его регистрирует
процесс бота. Это делает диспетчер тестируемым без живых Telegram/VK API.

Хранилище — JSON-файл с блокировкой (env MESSAGE_QUEUE_PATH, по умолчанию
data/bot_message_queue.json). Для больших объёмов стоит перенести в БД.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

try:  # POSIX-блокировка (на Windows отсутствует)
    import fcntl
except Exception:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from project_paths import project_path, resolve_project_path

# --- Статусы (ТЗ §6) --------------------------------------------------------
STATUS_QUEUED = "queued"
STATUS_SENDING = "sending"
STATUS_SENT = "sent"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"
STATUS_RETRY_WAIT = "retry_wait"
STATUS_CANCELLED = "cancelled"
STATUS_BLOCKED = "blocked"
STATUS_EXPIRED = "expired"

STATUSES = (
    STATUS_QUEUED, STATUS_SENDING, STATUS_SENT, STATUS_DELIVERED, STATUS_FAILED,
    STATUS_RETRY_WAIT, STATUS_CANCELLED, STATUS_BLOCKED, STATUS_EXPIRED,
)
# Терминальные статусы — больше не отправляем.
_TERMINAL = {STATUS_SENT, STATUS_DELIVERED, STATUS_CANCELLED, STATUS_EXPIRED}

# --- Приоритеты (ТЗ §9) -----------------------------------------------------
PRIORITY_CRITICAL = "critical"
PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"
PRIORITY_LOW = "low"
PRIORITY_SCHEDULED = "scheduled"
PRIORITIES = (PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW, PRIORITY_SCHEDULED)
_PRIORITY_RANK = {PRIORITY_CRITICAL: 0, PRIORITY_HIGH: 1, PRIORITY_NORMAL: 2, PRIORITY_LOW: 3, PRIORITY_SCHEDULED: 4}

# Бэкофф повторов по числу попыток (ТЗ §10), в секундах.
_BACKOFF = [0, 30, 120, 600, 1800]
DEFAULT_MAX_ATTEMPTS = 5

# Результаты sender'а.
RESULT_SENT = "sent"
RESULT_BLOCKED = "blocked"
RESULT_FAILED_TEMPORARY = "failed_temporary"
RESULT_FAILED_PERMANENT = "failed_permanent"


class _NoSender(Exception):
    pass


_SENDER: Callable[[dict[str, Any]], tuple[str, str]] | None = None
_STORE_LOCK = threading.Lock()


def set_sender(sender: Callable[[dict[str, Any]], tuple[str, str]] | None) -> None:
    """Зарегистрировать реальный отправитель: (message)->(result, error)."""
    global _SENDER
    _SENDER = sender


def _default_sender(_message: dict[str, Any]) -> tuple[str, str]:
    # Бот ещё не подключил отправитель — сообщение ждёт (временная ошибка).
    return RESULT_FAILED_TEMPORARY, "Отправитель бота не подключён."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def queue_path() -> Path:
    override = os.getenv("MESSAGE_QUEUE_PATH")
    if override:
        return resolve_project_path(override)
    return project_path("data", "bot_message_queue.json")


def _load() -> dict[str, Any]:
    try:
        with queue_path().open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    path = queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    tmp.replace(path)


@contextmanager
def _file_lock() -> Iterator[None]:
    if fcntl is None:
        yield
        return
    path = queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _messages(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)]


def _find_by_delivery_key(data: dict[str, Any], delivery_key: str) -> dict[str, Any] | None:
    for msg in _messages(data):
        if msg.get("delivery_key") == delivery_key:
            return msg
    return None


def enqueue(
    *,
    game_id: str | None,
    platform: str,
    recipient: str,
    text: str,
    type: str = "direct",
    priority: str = PRIORITY_NORMAL,
    delivery_key: str | None = None,
    source: str = "",
    operation_id: str | None = None,
    buttons: Any = None,
    attachments: Any = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[dict[str, Any], bool]:
    """Поставить сообщение в очередь немедленной доставки.

    Возвращает (сообщение, created). При дубле по delivery_key возвращает
    существующее с created=False (ТЗ §11).
    """
    if priority not in _PRIORITY_RANK:
        priority = PRIORITY_NORMAL
    with _STORE_LOCK, _file_lock():
        data = _load()
        if delivery_key:
            existing = _find_by_delivery_key(data, delivery_key)
            if existing is not None:
                return existing, False
        message_id = uuid.uuid4().hex
        message = {
            "id": message_id,
            "delivery_key": delivery_key or "",
            "game_id": str(game_id or ""),
            "platform": str(platform or ""),
            "recipient": str(recipient or ""),
            "type": str(type or "direct"),
            "text": str(text or ""),
            "buttons": buttons,
            "attachments": attachments,
            "priority": priority,
            "status": STATUS_QUEUED,
            "attempts": 0,
            "max_attempts": int(max_attempts) if max_attempts else DEFAULT_MAX_ATTEMPTS,
            "created_at": _now_iso(),
            "first_attempt_at": None,
            "last_attempt_at": None,
            "delivered_at": None,
            "next_attempt_at": _now_iso(),
            "error": "",
            "source": str(source or ""),
            "operation_id": str(operation_id or ""),
        }
        data[message_id] = message
        _save(data)
        return dict(message), True


def get(message_id: str) -> dict[str, Any] | None:
    with _STORE_LOCK, _file_lock():
        msg = _load().get(str(message_id))
    return msg if isinstance(msg, dict) else None


def list_messages(*, status: str | None = None, game_id: str | None = None, errors_only: bool = False, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    with _STORE_LOCK, _file_lock():
        items = _messages(_load())
    if status:
        items = [m for m in items if m.get("status") == status]
    if game_id:
        items = [m for m in items if str(m.get("game_id")) == str(game_id)]
    if errors_only:
        items = [m for m in items if m.get("status") in (STATUS_FAILED, STATUS_BLOCKED, STATUS_RETRY_WAIT)]
    items.sort(key=lambda m: str(m.get("created_at") or ""), reverse=True)
    start = max(0, int(offset))
    return items[start:start + max(1, int(limit))]


def stats() -> dict[str, Any]:
    with _STORE_LOCK, _file_lock():
        data = _load()
        items = _messages(data)
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
    by_status = {s: 0 for s in STATUSES}
    for m in items:
        st = m.get("status")
        if st in by_status:
            by_status[st] += 1
    return {"total": len(items), "by_status": by_status, "dispatcher": meta}


def dispatcher_status() -> dict[str, Any]:
    with _STORE_LOCK, _file_lock():
        data = _load()
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        pending = sum(1 for m in _messages(data) if m.get("status") in (STATUS_QUEUED, STATUS_RETRY_WAIT))
    return {
        "running": _SENDER is not None,
        "last_run": meta.get("last_run"),
        "last_success": meta.get("last_success"),
        "last_error": meta.get("last_error"),
        "pending": pending,
    }


def _due(msg: dict[str, Any], now: datetime) -> bool:
    if msg.get("status") not in (STATUS_QUEUED, STATUS_RETRY_WAIT):
        return False
    nxt = msg.get("next_attempt_at")
    if not nxt:
        return True
    try:
        return datetime.fromisoformat(str(nxt).replace("Z", "+00:00")) <= now
    except (TypeError, ValueError):
        return True


def retry(message_id: str, *, force: bool = False) -> dict[str, Any] | None:
    """Поставить сообщение на повторную немедленную отправку (админ)."""
    with _STORE_LOCK, _file_lock():
        data = _load()
        msg = data.get(str(message_id))
        if not isinstance(msg, dict):
            return None
        if msg.get("status") in (STATUS_SENT, STATUS_DELIVERED) and not force:
            # Уже доставлено — повтор только принудительно (ТЗ §11).
            return dict(msg)
        msg["status"] = STATUS_QUEUED
        msg["next_attempt_at"] = _now_iso()
        msg["error"] = ""
        data[str(message_id)] = msg
        _save(data)
        return dict(msg)


def cancel(message_id: str) -> dict[str, Any] | None:
    with _STORE_LOCK, _file_lock():
        data = _load()
        msg = data.get(str(message_id))
        if not isinstance(msg, dict):
            return None
        if msg.get("status") in _TERMINAL:
            return dict(msg)
        msg["status"] = STATUS_CANCELLED
        msg["last_attempt_at"] = _now_iso()
        data[str(message_id)] = msg
        _save(data)
        return dict(msg)


def _apply_result(msg: dict[str, Any], result: str, error: str, now: datetime) -> None:
    msg["attempts"] = int(msg.get("attempts") or 0) + 1
    msg["last_attempt_at"] = now.isoformat()
    if not msg.get("first_attempt_at"):
        msg["first_attempt_at"] = now.isoformat()
    if result == RESULT_SENT:
        msg["status"] = STATUS_SENT
        msg["delivered_at"] = now.isoformat()
        msg["error"] = ""
    elif result == RESULT_BLOCKED:
        msg["status"] = STATUS_BLOCKED
        msg["error"] = error or "Получатель заблокировал бота."
    elif result == RESULT_FAILED_PERMANENT:
        msg["status"] = STATUS_FAILED
        msg["error"] = error or "Постоянная ошибка доставки."
    else:  # временная ошибка — повтор
        if int(msg["attempts"]) >= int(msg.get("max_attempts") or DEFAULT_MAX_ATTEMPTS):
            msg["status"] = STATUS_FAILED
            msg["error"] = error or "Исчерпаны попытки доставки."
        else:
            msg["status"] = STATUS_RETRY_WAIT
            delay = _BACKOFF[min(int(msg["attempts"]), len(_BACKOFF) - 1)]
            from datetime import timedelta
            msg["next_attempt_at"] = (now + timedelta(seconds=delay)).isoformat()
            msg["error"] = error or "Временная ошибка, повтор запланирован."


def dispatch_once(sender: Callable[[dict[str, Any]], tuple[str, str]] | None = None, *, now: datetime | None = None, limit: int = 25) -> dict[str, int]:
    """Один проход диспетчера: взять готовые к отправке и отправить."""
    now = now or _now()
    send = sender or _SENDER or _default_sender
    counts = {"sent": 0, "failed": 0, "blocked": 0, "retry": 0, "processed": 0}
    with _STORE_LOCK, _file_lock():
        data = _load()
        due = [m for m in _messages(data) if _due(m, now)]
        due.sort(key=lambda m: (_PRIORITY_RANK.get(m.get("priority"), 2), str(m.get("created_at") or "")))
        due = due[:max(1, int(limit))]
        for m in due:
            m["status"] = STATUS_SENDING
        _save(data)

    last_error = None
    last_success = None
    for msg in due:
        try:
            result, error = send(msg)
        except Exception as exc:  # noqa: BLE001
            result, error = RESULT_FAILED_TEMPORARY, str(exc)
        with _STORE_LOCK, _file_lock():
            data = _load()
            stored = data.get(msg["id"])
            if not isinstance(stored, dict):
                continue
            _apply_result(stored, result, error, now)
            data[msg["id"]] = stored
            _save(data)
        counts["processed"] += 1
        if stored["status"] == STATUS_SENT:
            counts["sent"] += 1
            last_success = now.isoformat()
        elif stored["status"] == STATUS_BLOCKED:
            counts["blocked"] += 1
            last_error = error
        elif stored["status"] == STATUS_FAILED:
            counts["failed"] += 1
            last_error = error
        else:
            counts["retry"] += 1
            last_error = error

    with _STORE_LOCK, _file_lock():
        data = _load()
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        meta["last_run"] = now.isoformat()
        if last_success:
            meta["last_success"] = last_success
        if last_error:
            meta["last_error"] = last_error
        data["_meta"] = meta
        _save(data)
    return counts
