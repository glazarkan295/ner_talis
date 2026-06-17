"""Админская рассылка «Общее сообщение».

Админ выбирает аудиторию (пол / диапазон уровней / все / конкретные игроки) и
текст. Сообщение кладётся в ``pending_bot_messages`` каждого получателя и
доставляется ботом в том виде, как отправлено, при ближайшем взаимодействии
игрока с ботом (тот же канал, что у курьера и время-эффектов).
"""

from __future__ import annotations

from typing import Any

from services.courier_service import find_player_by_query
from services.derived_stats_service import safe_int

# Ключ аудитории → человекочитаемая подпись (для аудита/ответа API).
AUDIENCE_LABELS = {
    "all": "Все игроки",
    "male": "Игроки мужского пола",
    "female": "Игроки женского пола",
    "lvl_1_50": "Игроки 1–50 уровня",
    "lvl_50_plus": "Игроки 50 уровня и выше",
    "lvl_50_100": "Игроки 50–100 уровня",
    "lvl_500_plus": "Игроки 500 уровня и выше",
    "lvl_100_500": "Игроки 100–500 уровня",
    "lvl_500_1000": "Игроки 500–1000 уровня",
    "lvl_1000_plus": "Игроки 1000 уровня и выше",
    "specific": "Определённые игроки",
}


class BroadcastError(Exception):
    """Ошибка рассылки с человекочитаемым сообщением."""


def _matches_audience(player: dict[str, Any], audience: str) -> bool:
    gender = str(player.get("gender") or "")
    level = safe_int(player.get("level"), 1)
    if audience == "all":
        return True
    if audience == "male":
        return gender == "male"
    if audience == "female":
        return gender == "female"
    if audience == "lvl_1_50":
        return 1 <= level <= 50
    if audience == "lvl_50_plus":
        return level >= 50
    if audience == "lvl_50_100":
        return 50 <= level <= 100
    if audience == "lvl_500_plus":
        return level >= 500
    if audience == "lvl_100_500":
        return 100 <= level <= 500
    if audience == "lvl_500_1000":
        return 500 <= level <= 1000
    if audience == "lvl_1000_plus":
        return level >= 1000
    return False


def _all_players(storage: Any) -> dict[str, dict[str, Any]]:
    try:
        data = storage.load()
    except Exception:
        return {}
    players = data.get("players") if isinstance(data, dict) else None
    if not isinstance(players, dict):
        return {}
    return {str(gid): pl for gid, pl in players.items() if isinstance(pl, dict)}


def select_recipient_ids(
    storage: Any, audience: str, specific_players: list[str] | None = None
) -> list[str]:
    """Возвращает список game_id получателей для выбранной аудитории."""
    audience = str(audience or "").strip()
    if audience not in AUDIENCE_LABELS:
        raise BroadcastError("Неизвестная аудитория рассылки.")

    if audience == "specific":
        ids: list[str] = []
        for raw in specific_players or []:
            query = str(raw or "").strip()
            if not query:
                continue
            player = find_player_by_query(storage, query)
            if player is None:
                raise BroadcastError(f"Игрок не найден: {query}.")
            game_id = str(player.get("game_id") or player.get("id") or "")
            if game_id and game_id not in ids:
                ids.append(game_id)
        return ids

    return [
        game_id
        for game_id, player in _all_players(storage).items()
        if _matches_audience(player, audience)
    ]


def broadcast_message(
    storage: Any,
    audience: str,
    message: str,
    specific_players: list[str] | None = None,
) -> dict[str, Any]:
    """Ставит сообщение в очередь доставки всем получателям аудитории.

    Возвращает {"audience", "audienceLabel", "recipients", "delivered"}.
    """
    text = str(message or "").strip()
    if not text:
        raise BroadcastError("Сообщение не может быть пустым.")

    recipient_ids = select_recipient_ids(storage, audience, specific_players)
    if not recipient_ids:
        raise BroadcastError("Не найдено игроков-получателей для выбранной аудитории.")

    get_player = getattr(storage, "get_player_by_game_id", None)
    update_player = getattr(storage, "update_player", None)
    if not callable(update_player):
        raise BroadcastError("Хранилище не поддерживает доставку сообщений.")

    delivered = 0
    for game_id in recipient_ids:
        player = get_player(game_id) if callable(get_player) else None
        if not isinstance(player, dict):
            continue
        pending = player.setdefault("pending_bot_messages", [])
        if not isinstance(pending, list):
            pending = []
            player["pending_bot_messages"] = pending
        pending.append(text)
        try:
            update_player(player)
            delivered += 1
        except Exception:
            continue

    return {
        "audience": audience,
        "audienceLabel": AUDIENCE_LABELS.get(audience, audience),
        "recipients": len(recipient_ids),
        "delivered": delivered,
    }
