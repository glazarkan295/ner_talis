"""Persistent runtime timer delivery for real-time location actions.

Timers are stored inside the player profile.  This module restores timers after
container restarts and also protects delivery with a storage-level claim so the
same timer is not completed twice when the app is scaled to several containers.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from typing import Any, Callable

from services.external_location_service import LocationResponse, complete_active_timer, timer_remaining_seconds

logger = logging.getLogger(__name__)

TimerSendCallback = Callable[[str, str, LocationResponse], None]
PROCESS_TIMER_OWNER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
DEFAULT_CLAIM_TTL_SECONDS = 300


def _target_key_for_platform(platform: str) -> str:
    return "chat_id" if platform == "telegram" else "peer_id"


def attach_timer_notification(
    storage: Any,
    game_id: str | None,
    timer_id: str | None,
    platform: str,
    target_id: str | int,
) -> None:
    """Persist where a timer completion notification must be sent."""

    if not game_id or not timer_id or not platform or target_id is None:
        return

    player = storage.get_player_by_game_id(str(game_id))
    if player is None:
        return

    active_timer = player.get("active_timer")
    if not isinstance(active_timer, dict) or active_timer.get("id") != timer_id:
        return

    notify = {
        "platform": platform,
        _target_key_for_platform(platform): str(target_id),
        "target_id": str(target_id),
        "saved_at": time.time(),
    }
    active_timer["notify"] = notify
    # A new notification target means any old failed/stale delivery lock is no
    # longer useful.
    active_timer.pop("delivery_claim", None)
    player["active_timer"] = active_timer
    storage.update_player(player)


def _extract_notify_target(timer: dict[str, Any], platform_filter: str | None = None) -> tuple[str, str] | None:
    notify = timer.get("notify")
    if not isinstance(notify, dict):
        return None

    platform = str(notify.get("platform") or "").strip()
    if not platform:
        return None
    if platform_filter and platform != platform_filter:
        return None

    target_id = notify.get(_target_key_for_platform(platform)) or notify.get("target_id")
    if target_id is None or str(target_id).strip() == "":
        return None
    return platform, str(target_id)


def _fallback_claim_player(
    storage: Any,
    game_id: str,
    timer_id: str,
    platform_filter: str | None,
) -> dict[str, Any] | None:
    """Best-effort claim for legacy storage classes without atomic support."""

    player = storage.get_player_by_game_id(str(game_id))
    if player is None:
        return None

    active_timer = player.get("active_timer")
    if not isinstance(active_timer, dict) or active_timer.get("id") != timer_id:
        return None
    if _extract_notify_target(active_timer, platform_filter=platform_filter) is None:
        return None
    if timer_remaining_seconds(active_timer) > 0:
        return None
    return player


def _claim_timer_for_delivery(
    storage: Any,
    game_id: str,
    timer_id: str,
    platform_filter: str | None,
) -> dict[str, Any] | None:
    claim_method = getattr(storage, "claim_active_timer_for_delivery", None)
    if callable(claim_method):
        return claim_method(
            str(game_id),
            str(timer_id),
            PROCESS_TIMER_OWNER,
            claim_ttl_seconds=DEFAULT_CLAIM_TTL_SECONDS,
            platform_filter=platform_filter,
        )
    return _fallback_claim_player(storage, game_id, timer_id, platform_filter)


def _deliver_timer_once(
    storage: Any,
    game_id: str,
    timer_id: str,
    send_callback: TimerSendCallback,
    platform_filter: str | None = None,
) -> bool:
    """Complete a persisted timer after atomically claiming it.

    Returns True only when this process actually completed and sent the timer.
    Another container may return False because it lost the claim race; that is a
    normal condition and should not be logged as an error.
    """

    player = _claim_timer_for_delivery(storage, str(game_id), str(timer_id), platform_filter)
    if player is None:
        return False

    active_timer = player.get("active_timer")
    if not isinstance(active_timer, dict) or active_timer.get("id") != timer_id:
        return False

    target = _extract_notify_target(active_timer, platform_filter=platform_filter)
    if target is None:
        return False

    platform, target_id = target
    response = complete_active_timer(storage, player, timer_id)
    send_callback(platform, target_id, response)
    return True


def schedule_timer_delivery(
    storage: Any,
    game_id: str | None,
    timer_id: str | None,
    seconds: int | float,
    send_callback: TimerSendCallback,
    *,
    platform_filter: str | None = None,
) -> threading.Timer | None:
    """Schedule a persisted timer completion in the current process."""

    if not game_id or not timer_id:
        return None

    delay = max(0.05, float(seconds or 0))

    def fire() -> None:
        try:
            _deliver_timer_once(
                storage=storage,
                game_id=str(game_id),
                timer_id=str(timer_id),
                send_callback=send_callback,
                platform_filter=platform_filter,
            )
        except Exception:
            logger.exception("Failed to deliver timer %s for player %s", timer_id, game_id)

    timer = threading.Timer(delay, fire)
    timer.daemon = True
    timer.start()
    return timer


def _iter_players_with_timers(storage: Any) -> list[dict[str, Any]]:
    try:
        data = storage.load()
    except Exception:
        logger.exception("Failed to load players for timer recovery")
        return []

    players = data.get("players") if isinstance(data, dict) else None
    if not isinstance(players, dict):
        return []

    result: list[dict[str, Any]] = []
    for player in players.values():
        if isinstance(player, dict) and isinstance(player.get("active_timer"), dict):
            result.append(player)
    return result


def recover_saved_timers(
    storage: Any,
    send_callback: TimerSendCallback,
    *,
    platform_filter: str | None = None,
    schedule_future: bool = True,
) -> int:
    """Recover active timers that have a saved notification target.

    Expired timers are claimed and delivered immediately.  Future timers are
    scheduled only when ``schedule_future`` is True.  Background workers use
    ``schedule_future=False`` to avoid creating duplicate in-memory timers.
    """

    recovered = 0
    for player in _iter_players_with_timers(storage):
        game_id = str(player.get("game_id") or player.get("id") or "")
        active_timer = player.get("active_timer")
        if not game_id or not isinstance(active_timer, dict):
            continue
        timer_id = str(active_timer.get("id") or "")
        if not timer_id or _extract_notify_target(active_timer, platform_filter=platform_filter) is None:
            continue

        remaining = timer_remaining_seconds(active_timer)
        if remaining <= 0:
            try:
                if _deliver_timer_once(storage, game_id, timer_id, send_callback, platform_filter=platform_filter):
                    recovered += 1
            except Exception:
                logger.exception("Failed to immediately recover timer %s for player %s", timer_id, game_id)
            continue

        if schedule_future and schedule_timer_delivery(
            storage=storage,
            game_id=game_id,
            timer_id=timer_id,
            seconds=remaining,
            send_callback=send_callback,
            platform_filter=platform_filter,
        ):
            recovered += 1

    return recovered


def start_persistent_timer_worker(
    storage: Any,
    send_callback: TimerSendCallback,
    *,
    platform_filter: str | None = None,
    interval_seconds: int | float = 30,
) -> threading.Event:
    """Start a lightweight DB-backed recovery loop.

    This loop is what makes timers resilient in multi-container mode. Every
    container may run the loop, but only the one that successfully claims a due
    timer sends the final notification.
    """

    stop_event = threading.Event()
    interval = max(5.0, float(interval_seconds or 30))

    def loop() -> None:
        while not stop_event.wait(interval):
            try:
                recover_saved_timers(
                    storage,
                    send_callback,
                    platform_filter=platform_filter,
                    schedule_future=False,
                )
            except Exception:
                logger.exception("Persistent timer worker failed for platform=%s", platform_filter)

    thread = threading.Thread(
        target=loop,
        name=f"NerTalisTimerWorker-{platform_filter or 'all'}",
        daemon=True,
    )
    thread.start()
    return stop_event
