"""Исходящая очередь сообщений бота (ТЗ «Мгновенная доставка сообщений»).

Глобальная очередь немедленной доставки: система/админ кладёт сообщение, фоновый
диспетчер сразу берёт его и шлёт в Telegram/VK. В отличие от per-player
``pending_bot_messages`` (запасной путь — доставка при следующем действии),
здесь сообщение живёт со статусом, попытками, дедупликацией и приоритетом.

Хранилище — за абстракцией backend:
* по умолчанию JSON-файл с блокировкой (env MESSAGE_QUEUE_PATH) — dev/json;
* при ``configure_queue(storage)`` с поддержкой outgoing_* (SQLite/Postgres) —
  таблица row-per-message с индексами для масштаба.

Реальная отправка инкапсулирована в «sender» (set_sender) — его регистрирует
процесс бота, что делает диспетчер тестируемым без живых Telegram/VK API.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
STATUS_WAIT_TIMER = "waiting_timer"
STATUS_WAIT_BATTLE = "waiting_battle"
STATUS_WAIT_EVENT = "waiting_event"
STATUS_WAIT_ACTION = "waiting_action"
STATUS_NOTIFICATION_PENDING = "notification_pending"
STATUS_DELETED = "deleted"

STATUSES = (
    STATUS_QUEUED, STATUS_SENDING, STATUS_SENT, STATUS_DELIVERED, STATUS_FAILED,
    STATUS_RETRY_WAIT, STATUS_CANCELLED, STATUS_BLOCKED, STATUS_EXPIRED,
    STATUS_WAIT_TIMER, STATUS_WAIT_BATTLE, STATUS_WAIT_EVENT, STATUS_WAIT_ACTION,
    STATUS_NOTIFICATION_PENDING, STATUS_DELETED,
)
_TERMINAL = {STATUS_SENT, STATUS_DELIVERED, STATUS_CANCELLED, STATUS_EXPIRED, STATUS_DELETED}

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# --- Backend: JSON-файл (по умолчанию) --------------------------------------
def queue_path() -> Path:
    override = os.getenv("MESSAGE_QUEUE_PATH")
    if override:
        return resolve_project_path(override)
    return project_path("data", "bot_message_queue.json")


class _JsonFileBackend:
    """Хранилище очереди в JSON-файле с блокировкой (dev/json деплои)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            with queue_path().open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        path = queue_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        tmp.replace(path)

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
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

    @staticmethod
    def _items(data: dict[str, Any]) -> list[dict[str, Any]]:
        return [v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)]

    def add_or_get(self, message: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        delivery_key = str(message.get("delivery_key") or "")
        with self._lock, self._file_lock():
            data = self._load()
            if delivery_key:
                for existing in self._items(data):
                    if existing.get("delivery_key") == delivery_key:
                        return existing, False
            data[message["id"]] = message
            self._save(data)
            return dict(message), True

    def get(self, message_id: str) -> dict[str, Any] | None:
        with self._lock, self._file_lock():
            msg = self._load().get(str(message_id))
        return msg if isinstance(msg, dict) else None

    def update(self, message_id: str, message: dict[str, Any]) -> None:
        with self._lock, self._file_lock():
            data = self._load()
            data[str(message_id)] = message
            self._save(data)

    def list(self, *, status=None, game_id=None, errors_only=False, limit=200, offset=0) -> list[dict[str, Any]]:
        with self._lock, self._file_lock():
            items = self._items(self._load())
        if status:
            items = [m for m in items if m.get("status") == status]
        if game_id:
            items = [m for m in items if str(m.get("game_id")) == str(game_id)]
        if errors_only:
            items = [m for m in items if m.get("status") in (STATUS_FAILED, STATUS_BLOCKED, STATUS_RETRY_WAIT)]
        items.sort(key=lambda m: str(m.get("created_at") or ""), reverse=True)
        start = max(0, int(offset))
        return items[start:start + max(1, int(limit))]

    def claim_due(self, *, now_iso: str, limit: int = 25, platforms: list[str] | None = None) -> list[dict[str, Any]]:
        now = _parse_dt(now_iso) or _now()
        # platforms=None → без фильтра; пустой список → не клеймить ничего (нет
        # зарегистрированных отправителей).
        plats = None if platforms is None else {str(p) for p in platforms if p}
        if plats is not None and not plats:
            return []
        with self._lock, self._file_lock():
            data = self._load()
            due = []
            for m in self._items(data):
                if m.get("status") not in (STATUS_QUEUED, STATUS_RETRY_WAIT):
                    continue
                if plats is not None and str(m.get("platform") or "") not in plats:
                    continue
                nxt = _parse_dt(m.get("next_attempt_at"))
                if nxt is None or nxt <= now:
                    due.append(m)
            due.sort(key=lambda m: (_PRIORITY_RANK.get(m.get("priority"), 2), str(m.get("created_at") or "")))
            due = due[:max(1, int(limit))]
            for m in due:
                m["status"] = STATUS_SENDING
                data[m["id"]] = m
            if due:
                self._save(data)
            return [dict(m) for m in due]

    def counts(self) -> dict[str, int]:
        with self._lock, self._file_lock():
            items = self._items(self._load())
        result: dict[str, int] = {}
        for m in items:
            st = str(m.get("status") or "")
            result[st] = result.get(st, 0) + 1
        return result

    def get_meta(self) -> dict[str, Any]:
        with self._lock, self._file_lock():
            meta = self._load().get("_meta")
        return meta if isinstance(meta, dict) else {}

    def set_meta(self, meta: dict[str, Any]) -> None:
        with self._lock, self._file_lock():
            data = self._load()
            data["_meta"] = meta
            self._save(data)


class _StorageBackend:
    """Хранилище очереди в БД (SQLite/Postgres) через методы storage.outgoing_*."""

    def __init__(self, storage: Any) -> None:
        self._s = storage

    def add_or_get(self, message: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        stored = self._s.enqueue_outgoing_message(message)
        created = str(stored.get("id")) == str(message.get("id"))
        return stored, created

    def get(self, message_id: str) -> dict[str, Any] | None:
        return self._s.get_outgoing_message(message_id)

    def update(self, message_id: str, message: dict[str, Any]) -> None:
        self._s.update_outgoing_message(message_id, message)

    def list(self, **kwargs) -> list[dict[str, Any]]:
        return self._s.list_outgoing_messages(**kwargs)

    def claim_due(self, *, now_iso: str, limit: int = 25, platforms: list[str] | None = None) -> list[dict[str, Any]]:
        try:
            return self._s.claim_due_outgoing_messages(now_iso=now_iso, limit=limit, platforms=platforms)
        except TypeError:
            # Старое хранилище без параметра platforms — без фильтра.
            return self._s.claim_due_outgoing_messages(now_iso=now_iso, limit=limit)

    def counts(self) -> dict[str, int]:
        return self._s.outgoing_message_status_counts()

    def get_meta(self) -> dict[str, Any]:
        return self._s.get_outgoing_dispatcher_meta()

    def set_meta(self, meta: dict[str, Any]) -> None:
        self._s.set_outgoing_dispatcher_meta(meta)


_REQUIRED_STORAGE_METHODS = (
    "enqueue_outgoing_message", "get_outgoing_message", "update_outgoing_message",
    "list_outgoing_messages", "claim_due_outgoing_messages",
    "outgoing_message_status_counts", "get_outgoing_dispatcher_meta",
    "set_outgoing_dispatcher_meta",
)

_backend: Any = _JsonFileBackend()


def configure_queue(storage: Any) -> bool:
    """Использовать БД-хранилище очереди, если storage его поддерживает.

    Возвращает True, если переключились на БД; иначе остаётся JSON-файл.
    """
    global _backend
    if storage is not None and all(callable(getattr(storage, m, None)) for m in _REQUIRED_STORAGE_METHODS):
        _backend = _StorageBackend(storage)
        return True
    return False


def use_json_file_backend() -> None:
    """Сброс на JSON-файловый backend (для тестов/локали)."""
    global _backend
    _backend = _JsonFileBackend()


# --- Sender (регистрируется процессом бота) ---------------------------------
_SENDER: Callable[[dict[str, Any]], tuple[str, str]] | None = None


def set_sender(sender: Callable[[dict[str, Any]], tuple[str, str]] | None) -> None:
    global _SENDER
    _SENDER = sender


def _default_sender(_message: dict[str, Any]) -> tuple[str, str]:
    return RESULT_FAILED_TEMPORARY, "Отправитель бота не подключён."


# --- Публичный API ----------------------------------------------------------
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
    delay_seconds: int = 0,
    ttl_seconds: int = 0,
    initial_status: str = STATUS_QUEUED,
    group_key: str = "",
    group_header: str = "",
    group_footer: str = "",
    max_in_group: int = 0,
    source_id: str = "",
    send_at: str = "",
    retry_interval_seconds: int = 0,
    delete_after_ttl: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Поставить сообщение в очередь немедленной доставки (дедуп по delivery_key)."""
    if priority not in _PRIORITY_RANK:
        priority = PRIORITY_NORMAL
    message = {
        "id": uuid.uuid4().hex,
        "delivery_key": delivery_key or "",
        "game_id": str(game_id or ""),
        "platform": str(platform or ""),
        "recipient": str(recipient or ""),
        "type": str(type or "direct"),
        "text": str(text or ""),
        "buttons": buttons,
        "attachments": attachments,
        "priority": priority,
        "status": initial_status if initial_status in STATUSES else STATUS_QUEUED,
        "attempts": 0,
        "max_attempts": int(max_attempts) if max_attempts else DEFAULT_MAX_ATTEMPTS,
        "created_at": _now_iso(),
        "first_attempt_at": None,
        "last_attempt_at": None,
        "delivered_at": None,
        "next_attempt_at": str(send_at or "") or (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(delay_seconds or 0)))).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(ttl_seconds or 0)))).isoformat() if ttl_seconds else None,
        "error": "",
        "source": str(source or ""),
        "source_id": str(source_id or ""),
        "operation_id": str(operation_id or ""),
        "group_key": str(group_key or ""),
        "group_header": str(group_header or ""),
        "group_footer": str(group_footer or ""),
        "max_in_group": max(0, int(max_in_group or 0)),
        "retry_interval_seconds":max(0,int(retry_interval_seconds or 0)),
        "delete_after_ttl":bool(delete_after_ttl),
    }
    return _backend.add_or_get(message)


def get(message_id: str) -> dict[str, Any] | None:
    return _backend.get(message_id)


def list_messages(*, status: str | None = None, game_id: str | None = None, errors_only: bool = False, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    return _backend.list(status=status, game_id=game_id, errors_only=errors_only, limit=limit, offset=offset)


def stats() -> dict[str, Any]:
    counts = _backend.counts()
    by_status = {s: int(counts.get(s, 0)) for s in STATUSES}
    return {"total": sum(counts.values()), "by_status": by_status, "dispatcher": _backend.get_meta()}


def dispatcher_status() -> dict[str, Any]:
    counts = _backend.counts()
    meta = _backend.get_meta()
    return {
        "running": _SENDER is not None,
        "last_run": meta.get("last_run"),
        "last_success": meta.get("last_success"),
        "last_error": meta.get("last_error"),
        "pending": int(counts.get(STATUS_QUEUED, 0)) + int(counts.get(STATUS_RETRY_WAIT, 0)),
    }


def retry(message_id: str, *, force: bool = False) -> dict[str, Any] | None:
    msg = _backend.get(message_id)
    if msg is None:
        return None
    if msg.get("status") in (STATUS_SENT, STATUS_DELIVERED) and not force:
        return dict(msg)
    msg["status"] = STATUS_QUEUED
    msg["next_attempt_at"] = _now_iso()
    msg["error"] = ""
    _backend.update(message_id, msg)
    return dict(msg)


def cancel(message_id: str) -> dict[str, Any] | None:
    msg = _backend.get(message_id)
    if msg is None:
        return None
    if msg.get("status") in _TERMINAL:
        return dict(msg)
    msg["status"] = STATUS_CANCELLED
    msg["last_attempt_at"] = _now_iso()
    _backend.update(message_id, msg)
    return dict(msg)

def delete(message_id: str) -> dict[str, Any] | None:
    """Soft-delete keeps the audit trail while hiding the payload from delivery."""
    msg=_backend.get(message_id)
    if msg is None:return None
    msg.update({"status":STATUS_DELETED,"text":"","buttons":None,"attachments":None,"last_attempt_at":_now_iso()})
    _backend.update(message_id,msg);return dict(msg)

def use_button(message_id:str,button_id:str,*,now:datetime|None=None)->dict[str,Any]:
    """Resolve a queued-message button with TTL and one-time protection."""
    msg=_backend.get(message_id)
    if not msg:return {"ok":False,"error":"Сообщение не найдено."}
    row=next((b for b in msg.get("buttons") or [] if isinstance(b,dict) and str(b.get("button_id") or "")==str(button_id)),None)
    if not row:return {"ok":False,"error":"Кнопка не найдена."}
    current=now or _now();created=_parse_dt(msg.get("created_at")) or current;ttl=int(row.get("ttl_seconds") or 0)
    if msg.get("status") in {STATUS_EXPIRED,STATUS_DELETED,STATUS_CANCELLED} or ttl and created+timedelta(seconds=ttl)<=current:return {"ok":False,"error":str(row.get("error_text") or "Срок действия кнопки истёк.")}
    used=msg.setdefault("used_buttons",[])
    if row.get("one_time") and str(button_id) in used:return {"ok":False,"error":str(row.get("error_text") or "Кнопка уже использована.")}
    if row.get("one_time"):used.append(str(button_id));_backend.update(message_id,msg)
    return {"ok":True,"action":row.get("action"),"target":row.get("target"),"condition":row.get("show_condition")}

def release_waiting(game_id:str,trigger:str)->int:
    """Release messages waiting for a player action, battle or event completion."""
    wanted={"action":{STATUS_WAIT_ACTION},"message":{STATUS_WAIT_ACTION},"battle":{STATUS_WAIT_BATTLE},"event":{STATUS_WAIT_EVENT}}.get(str(trigger),set())
    changed=0
    for msg in _backend.list(game_id=str(game_id),limit=10000,offset=0):
        if msg.get("status") in wanted:
            msg["status"]=STATUS_QUEUED;msg["next_attempt_at"]=_now_iso();_backend.update(msg["id"],msg);changed+=1
    return changed

def bind_pending_recipient(game_id:str,platform:str,recipient:str)->int:
    """Make platform-less notifications deliverable once an account is linked."""
    changed=0
    for msg in _backend.list(game_id=str(game_id),limit=10000,offset=0):
        if msg.get("status")==STATUS_NOTIFICATION_PENDING:
            msg.update({"platform":str(platform),"recipient":str(recipient),"status":STATUS_QUEUED,"next_attempt_at":_now_iso()});_backend.update(msg["id"],msg);changed+=1
    return changed

def _activate_due_timers(now:datetime)->None:
    for msg in _backend.list(limit=10000,offset=0):
        if msg.get("status")==STATUS_WAIT_TIMER and ((_parse_dt(msg.get("next_attempt_at")) or now)<=now):
            msg["status"]=STATUS_QUEUED;_backend.update(msg["id"],msg)


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
            delay = int(msg.get("retry_interval_seconds") or 0) or _BACKOFF[min(int(msg["attempts"]), len(_BACKOFF) - 1)]
            msg["next_attempt_at"] = (now + timedelta(seconds=delay)).isoformat()
            msg["error"] = error or "Временная ошибка, повтор запланирован."


def dispatch_once(sender: Callable[[dict[str, Any]], tuple[str, str]] | None = None, *, now: datetime | None = None, limit: int = 25, platforms: list[str] | None = None) -> dict[str, int]:
    """Один проход диспетчера: взять готовые к отправке и отправить.

    platforms (если задан) ограничивает claim только этими платформами — чтобы
    процесс с отправителем одной платформы не «забирал» чужие сообщения и не
    жёг им попытки доставки (Codex P2)."""
    now = now or _now()
    _activate_due_timers(now)
    send = sender or _SENDER or _default_sender
    counts = {"sent": 0, "failed": 0, "blocked": 0, "retry": 0, "processed": 0}
    due = _backend.claim_due(now_iso=now.isoformat(), limit=limit, platforms=platforms)

    last_error = None
    last_success = None
    handled:set[str]=set()
    for msg in due:
        if msg["id"] in handled:continue
        group=[msg];group_key=str(msg.get("group_key") or "")
        if group_key:
            cap=max(1,int(msg.get("max_in_group") or len(due)))
            group=[row for row in due if row["id"] not in handled and row.get("group_key")==group_key and row.get("platform")==msg.get("platform") and row.get("recipient")==msg.get("recipient")][:cap]
        active=[]
        for row in group:
            handled.add(row["id"]);expires=_parse_dt(row.get("expires_at"))
            if expires is not None and expires<=now:
                stored=_backend.get(row["id"])
                if isinstance(stored,dict):stored.update({"status":STATUS_DELETED if stored.get("delete_after_ttl") else STATUS_EXPIRED,"error":"Срок жизни сообщения истёк до отправки.","last_attempt_at":now.isoformat()});_backend.update(row["id"],stored)
                counts["processed"]+=1;counts["failed"]+=1
            else:active.append(row)
        if not active:continue
        payload=dict(active[0])
        if len(active)>1:
            texts=[str(row.get("text") or "") for row in active]
            payload["text"]="\n".join([str(payload.get("group_header") or ""),*texts,str(payload.get("group_footer") or "")]).strip()
            payload["grouped_message_ids"]=[row["id"] for row in active]
        try:result,error=send(payload)
        except Exception as exc:result,error=RESULT_FAILED_TEMPORARY,str(exc)
        for row in active:
            stored=_backend.get(row["id"])
            if not isinstance(stored,dict):continue
            if len(active)>1:stored["grouped_with"]=[other["id"] for other in active if other["id"]!=row["id"]]
            _apply_result(stored,result,error,now);_backend.update(row["id"],stored);counts["processed"]+=1
            if stored["status"]==STATUS_SENT:counts["sent"]+=1;last_success=now.isoformat()
            elif stored["status"]==STATUS_BLOCKED:counts["blocked"]+=1;last_error=error
            elif stored["status"]==STATUS_FAILED:counts["failed"]+=1;last_error=error
            else:counts["retry"]+=1;last_error=error

    meta = dict(_backend.get_meta())
    meta["last_run"] = now.isoformat()
    if last_success:
        meta["last_success"] = last_success
    if last_error:
        meta["last_error"] = last_error
    _backend.set_meta(meta)
    return counts
