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


def pop_pending_bot_messages(player: dict[str, Any]) -> list[str]:
    pending = player.get("pending_bot_messages")
    if not isinstance(pending, list) or not pending:
        return []
    messages: list[str] = []
    for entry in pending:
        if isinstance(entry, dict):
            text = str(entry.get("text") or "").strip()
        else:
            text = str(entry or "").strip()
        if text:
            messages.append(text)
    player["pending_bot_messages"] = []
    return messages
