"""Helpers for claiming persisted real-time timers safely.

When the app runs in more than one container, each process can recover and fire
its own in-memory ``threading.Timer`` for the same player timer.  The helpers in
this module mark a timer as claimed before completion so only one process sends
its final notification.
"""

from __future__ import annotations

import time
from typing import Any


def timer_notify_platform(timer: dict[str, Any]) -> str | None:
    notify = timer.get("notify")
    if not isinstance(notify, dict):
        return None
    platform = str(notify.get("platform") or "").strip()
    return platform or None


def can_claim_timer(
    player: dict[str, Any],
    timer_id: str,
    *,
    platform_filter: str | None = None,
    now: float | None = None,
) -> bool:
    """Return True when ``player.active_timer`` can be claimed for delivery."""

    now = time.time() if now is None else float(now)
    timer = player.get("active_timer")
    if not isinstance(timer, dict):
        return False
    if str(timer.get("id") or "") != str(timer_id):
        return False
    if platform_filter and timer_notify_platform(timer) != platform_filter:
        return False

    try:
        ends_at = float(timer.get("ends_at") or 0)
    except (TypeError, ValueError):
        ends_at = 0.0
    if ends_at > now:
        return False

    claim = timer.get("delivery_claim")
    if isinstance(claim, dict):
        try:
            claimed_until = float(claim.get("claimed_until") or 0)
        except (TypeError, ValueError):
            claimed_until = 0.0
        if claimed_until > now:
            return False

    return True


def try_mark_timer_claimed(
    player: dict[str, Any],
    timer_id: str,
    owner: str,
    *,
    claim_ttl_seconds: int = 300,
    platform_filter: str | None = None,
    now: float | None = None,
) -> bool:
    """Mark an expired active timer as claimed in-place.

    The caller must persist the changed player atomically while holding the
    storage-specific lock/transaction.  Returns False if another process already
    owns a non-expired claim, if the timer is not current, or if it is not yet due.
    """

    now = time.time() if now is None else float(now)
    if not can_claim_timer(player, timer_id, platform_filter=platform_filter, now=now):
        return False

    timer = player.get("active_timer")
    if not isinstance(timer, dict):
        return False

    timer["delivery_claim"] = {
        "owner": str(owner),
        "claimed_at": now,
        "claimed_until": now + max(30, int(claim_ttl_seconds or 300)),
    }
    player["active_timer"] = timer
    return True
