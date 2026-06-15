"""Lazy catch-up for wall-clock background effects.

Игра не держит постоянный планировщик. Время-зависимые фоновые эффекты
(почасовой «Ожог от амулета» и суточный счётчик дней с Древним Проклятьем)
догоняются «лениво» — при каждом действии игрока, исходя из прошедшего
времени. Сообщения складываются в pending_bot_messages и доставляются ботом.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from services.small_plateau_service import (
    AMULET_BURN_ID,
    ANCIENT_CURSE_ID,
    SEVERE_AMULET_BURN_ID,
    has_effect,
    register_ancient_curse_active_day,
    tick_amulet_burn_hourly,
)

HOUR_SECONDS = 3600
MAX_CATCHUP_HOURS = 24            # не наказываем более чем за сутки простоя за раз
ACTIVE_GAP_CAP_SECONDS = 600      # промежуток до 10 минут засчитывается как активность
CURSE_ACTIVE_DAY_MINUTES = 30     # день засчитывается при активности >= 30 минут


def _now_ts(now_ts: float | int | None = None) -> int:
    return int(time.time() if now_ts is None else now_ts)


def _utc_day(now_ts: int) -> str:
    return datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _advance_amulet_burn(player: dict[str, Any], now: int, messages: list[str]) -> None:
    active = has_effect(player, SEVERE_AMULET_BURN_ID) or has_effect(player, AMULET_BURN_ID)
    if not active:
        player.pop("amulet_burn_last_tick_ts", None)
        return
    last = player.get("amulet_burn_last_tick_ts")
    if not isinstance(last, (int, float)):
        player["amulet_burn_last_tick_ts"] = now
        return
    hours = int((now - int(last)) // HOUR_SECONDS)
    if hours <= 0:
        return
    hours = min(hours, MAX_CATCHUP_HOURS)
    for _ in range(hours):
        result = tick_amulet_burn_hourly(player)
        if not result:
            break
        text = str(result.get("text") or "").strip()
        if text:
            messages.append(text)
    player["amulet_burn_last_tick_ts"] = int(last) + hours * HOUR_SECONDS


def _advance_curse_days(player: dict[str, Any], now: int, messages: list[str]) -> None:
    tracker = player.get("curse_day_tracker")
    if not isinstance(tracker, dict):
        player["curse_day_tracker"] = {"date": _utc_day(now), "active_seconds": 0, "last_action_ts": now}
        return
    today = _utc_day(now)
    last_action = int(tracker.get("last_action_ts") or now)
    if str(tracker.get("date")) == today:
        gap = now - last_action
        if 0 < gap <= ACTIVE_GAP_CAP_SECONDS:
            tracker["active_seconds"] = int(tracker.get("active_seconds") or 0) + gap
        tracker["last_action_ts"] = now
        return
    # Сутки сменились — финализируем прошедший день.
    prev_minutes = int(tracker.get("active_seconds") or 0) // 60
    result = register_ancient_curse_active_day(player, prev_minutes)
    if result and result.get("text"):
        messages.append(str(result["text"]))
    tracker["date"] = today
    tracker["active_seconds"] = 0
    tracker["last_action_ts"] = now


def advance_player_time(player: dict[str, Any], now_ts: float | int | None = None) -> list[str]:
    """Догоняет фоновые время-зависимые эффекты; возвращает сообщения игроку."""
    now = _now_ts(now_ts)
    messages: list[str] = []
    _advance_amulet_burn(player, now, messages)
    _advance_curse_days(player, now, messages)
    if messages:
        pending = player.setdefault("pending_bot_messages", [])
        if isinstance(pending, list):
            pending.extend(messages)
    return messages
