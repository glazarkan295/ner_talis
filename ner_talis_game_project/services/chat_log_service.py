"""Small per-player chat log helpers used by admin panel diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

MAX_CHAT_LOG = 1000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_player_chat_log(player: dict[str, Any], *, direction: str, text: str, platform: str | None = None) -> None:
    log = player.get("chat_log")
    if not isinstance(log, list):
        log = []
        player["chat_log"] = log
    log.append({
        "created_at": _utc_now(),
        "direction": str(direction or "message"),
        "platform": str(platform or ""),
        "text": str(text or ""),
    })
    if len(log) > MAX_CHAT_LOG:
        del log[:-MAX_CHAT_LOG]


def normalize_bot_messages(items: Any) -> list[str]:
    """Привести записи outbox (строки или {"text": ...}) к списку строк."""
    if not isinstance(items, list):
        return []
    messages: list[str] = []
    for entry in items:
        if isinstance(entry, dict):
            text = str(entry.get("text") or "").strip()
        else:
            text = str(entry or "").strip()
        if text:
            messages.append(text)
    return messages


def pop_pending_bot_messages(player: dict[str, Any]) -> list[str]:
    pending = player.get("pending_bot_messages")
    if not isinstance(pending, list) or not pending:
        return []
    messages = normalize_bot_messages(pending)
    player["pending_bot_messages"] = []
    return messages


class DurableOutboxDelivery:
    """Гарантия доставки durable-outbox: помечай отправленные, в finally верни
    недоставленные обратно в очередь.

    Хендлеры выгребают outbox через dequeue (атомарно удаляя записи) и затем
    шлют их боту. Если бот-API упал/лимит/краш в середине — выгруженные
    сообщения уже не в хранилище и пропали бы навсегда. Этот драйвер (без I/O —
    подходит и для sync VK, и для async Telegram) возвращает несработавшие
    записи обратно, чтобы они доставились при следующем действии игрока."""

    def __init__(self, storage: Any, game_id: str, messages: list[str]) -> None:
        self._storage = storage
        self._game_id = str(game_id or "")
        self.remaining: list[str] = list(messages or [])

    def mark_sent(self) -> None:
        """Вызывать ПОСЛЕ успешной отправки очередного durable-сообщения."""
        if self.remaining:
            self.remaining.pop(0)

    def requeue_unsent(self) -> None:
        """Вызывать в finally: вернуть недоставленные durable-сообщения в outbox."""
        if self.remaining and self._game_id and hasattr(self._storage, "enqueue_bot_messages"):
            try:
                self._storage.enqueue_bot_messages(self._game_id, list(self.remaining))
            except Exception:
                pass
        self.remaining = []
