"""Lazy catch-up for wall-clock background effects.

Игра не держит постоянный планировщик. Время-зависимые фоновые эффекты
(почасовой «Ожог от амулета» и суточный счётчик дней с Древним Проклятьем)
догоняются «лениво» — при каждом действии игрока, исходя из прошедшего
времени. Сообщения складываются в pending_bot_messages и доставляются ботом.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

from services.small_plateau_service import (
    AMULET_BURN_ID,
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


def _advance_amulet_burn(player: dict[str, Any], now: int, messages: list[str]) -> bool:
    active = has_effect(player, SEVERE_AMULET_BURN_ID) or has_effect(player, AMULET_BURN_ID)
    if not active:
        return bool(player.pop("amulet_burn_last_tick_ts", None) is not None)
    last = player.get("amulet_burn_last_tick_ts")
    if not isinstance(last, (int, float)):
        player["amulet_burn_last_tick_ts"] = now
        return True
    hours = int((now - int(last)) // HOUR_SECONDS)
    if hours <= 0:
        return False
    hours = min(hours, MAX_CATCHUP_HOURS)
    for _ in range(hours):
        result = tick_amulet_burn_hourly(player)
        if not result:
            break
        text = str(result.get("text") or "").strip()
        if text:
            messages.append(text)
    player["amulet_burn_last_tick_ts"] = int(last) + hours * HOUR_SECONDS
    return True


def _advance_curse_days(player: dict[str, Any], now: int, messages: list[str], count_activity: bool = True) -> bool:
    tracker = player.get("curse_day_tracker")
    if not isinstance(tracker, dict):
        player["curse_day_tracker"] = {"date": _utc_day(now), "active_seconds": 0, "last_action_ts": now}
        return True
    today = _utc_day(now)
    last_action = int(tracker.get("last_action_ts") or now)
    if str(tracker.get("date")) == today:
        # Активность копится только из действий игрока — фоновый тик планировщика
        # (count_activity=False) не должен накручивать «активные минуты».
        if not count_activity:
            return False
        changed = False
        gap = now - last_action
        if 0 < gap <= ACTIVE_GAP_CAP_SECONDS:
            tracker["active_seconds"] = int(tracker.get("active_seconds") or 0) + gap
            changed = True
        tracker["last_action_ts"] = now
        return changed
    # Сутки сменились — финализируем прошедший день (даже в фоне, по уже
    # накопленной игроком активности).
    prev_minutes = int(tracker.get("active_seconds") or 0) // 60
    result = register_ancient_curse_active_day(player, prev_minutes)
    if result and result.get("text"):
        messages.append(str(result["text"]))
    tracker["date"] = today
    tracker["active_seconds"] = 0
    tracker["last_action_ts"] = now
    return True


def _advance(player: dict[str, Any], now: int, count_activity: bool) -> tuple[list[str], bool]:
    messages: list[str] = []
    burn_changed = _advance_amulet_burn(player, now, messages)
    curse_changed = _advance_curse_days(player, now, messages, count_activity=count_activity)
    return messages, bool(burn_changed or curse_changed or messages)


def _queue_messages(player: dict[str, Any], messages: list[str]) -> None:
    if not messages:
        return
    pending = player.setdefault("pending_bot_messages", [])
    if isinstance(pending, list):
        pending.extend(messages)


def advance_player_time(player: dict[str, Any], now_ts: float | int | None = None) -> list[str]:
    """Догоняет фоновые время-зависимые эффекты для одного игрока (путь действия).

    Возвращает сообщения и кладёт их в pending_bot_messages для доставки ботом.
    """
    messages, _changed = _advance(player, _now_ts(now_ts), count_activity=True)
    _queue_messages(player, messages)
    return messages


def advance_all_players_time(storage: Any, now_ts: float | int | None = None) -> int:
    """Тик планировщика: догоняет время-зависимые эффекты для ВСЕХ игроков.

    Вызывается фоновым воркером, поэтому активность игрока не накручивается
    (count_activity=False) — фоновый тик не должен засчитываться как «игровая
    активность» для суточного счётчика проклятья. Почасовой ожог амулета и
    смена суток обрабатываются. Изменённые игроки сохраняются; сообщения
    уходят через pending_bot_messages при следующем взаимодействии.
    """
    try:
        data = storage.load()
    except Exception:
        return 0
    players = data.get("players") if isinstance(data, dict) else None
    if not isinstance(players, dict):
        return 0
    now = _now_ts(now_ts)
    updated = 0
    for player in list(players.values()):
        if not isinstance(player, dict):
            continue
        try:
            messages, changed = _advance(player, now, count_activity=False)
        except Exception:
            continue
        if not changed and not messages:
            continue
        _queue_messages(player, messages)
        try:
            storage.update_player(player)
            updated += 1
        except Exception:
            continue
    return updated


def start_persistent_player_effect_worker(
    storage: Any,
    *,
    interval_seconds: int | float = 60,
) -> threading.Event:
    """Постоянный фоновый планировщик время-зависимых эффектов.

    Каждые ``interval_seconds`` догоняет почасовой «Ожог от амулета» и суточный
    счётчик дней с проклятьем для ВСЕХ игроков, даже офлайн. Лёгкий daemon-поток
    (как и таймерный воркер). При нескольких контейнерах каждый прогоняет цикл;
    повторное применение безопасно — урон/счётчик считаются по прошедшим часам/
    суткам относительно сохранённых меток, а не по числу тиков.
    """
    stop_event = threading.Event()
    interval = max(15.0, float(interval_seconds or 60))

    def loop() -> None:
        while not stop_event.wait(interval):
            try:
                advance_all_players_time(storage)
            except Exception:
                logger.exception("Persistent player-effect worker failed")

    thread = threading.Thread(
        target=loop,
        name="NerTalisPlayerEffectWorker",
        daemon=True,
    )
    thread.start()
    return stop_event
