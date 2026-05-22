"""Helpers for claiming player events before giving rewards.

Linked Telegram/VK accounts can send the same button action nearly at the same
moment.  Event rewards must be granted only once, so storage backends claim the
current active_event atomically before the event resolver mutates inventory,
money or resources.
"""

from __future__ import annotations

import time
from typing import Any


def _event_identity(event: dict[str, Any]) -> str:
    return str(event.get("event_id") or event.get("id") or "")


def ensure_event_id(event: dict[str, Any], fallback: str | None = None) -> str:
    event_id = _event_identity(event)
    if not event_id:
        event_id = str(fallback or f"event_{int(time.time() * 1000)}")
        event["event_id"] = event_id
    return event_id


def can_claim_active_event(
    player: dict[str, Any],
    event_id: str | None = None,
    *,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else float(now)
    event = player.get("active_event")
    if not isinstance(event, dict):
        return False

    current_event_id = _event_identity(event)
    if event_id and current_event_id and str(event_id) != current_event_id:
        return False

    claim = event.get("resolution_claim")
    if isinstance(claim, dict):
        try:
            claimed_until = float(claim.get("claimed_until") or 0)
        except (TypeError, ValueError):
            claimed_until = 0.0
        if claimed_until > now:
            return False

    return True


def try_mark_active_event_claimed(
    player: dict[str, Any],
    event_id: str | None,
    owner: str,
    *,
    claim_ttl_seconds: int = 120,
    now: float | None = None,
) -> bool:
    """Mark player.active_event as being resolved.

    The caller must persist the changed player while holding the backend lock or
    transaction.  Returns False when the event was already claimed/resolved.
    """

    now = time.time() if now is None else float(now)
    if not can_claim_active_event(player, event_id, now=now):
        return False

    event = player.get("active_event")
    if not isinstance(event, dict):
        return False

    ensure_event_id(event, fallback=event_id)
    event["resolution_claim"] = {
        "owner": str(owner),
        "claimed_at": now,
        "claimed_until": now + max(15, int(claim_ttl_seconds or 120)),
    }
    player["active_event"] = event
    return True
