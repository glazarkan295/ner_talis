"""Административные операции над профилем игрока."""

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from game_data.starter_items import get_starter_equipment
from game_data.starter_skills import get_starter_skills
from project_paths import resolve_project_path
from services.registration_service import DEFAULT_CRAFTING_LEVELS, load_races

STAT_KEYS = ("strength", "dexterity", "endurance", "intelligence", "wisdom", "perception")
GAME_ID_PATTERN = re.compile(r"^NT-[A-Z0-9]{10}$", re.IGNORECASE)


def normalize_game_id(identifier: str) -> str:
    """Возвращает game_id в каноническом виде NT-XXXXXXXXXX."""
    return str(identifier or "").strip().strip("\"'").upper()


def is_valid_game_id(identifier: str) -> bool:
    return bool(GAME_ID_PATTERN.fullmatch(normalize_game_id(identifier)))


def _backup_dir() -> Path:
    return resolve_project_path(os.getenv("ADMIN_BACKUP_DIR", "data/admin_backups"))


def backup_player(player: dict[str, Any], reason: str) -> Path:
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    game_id = str(player.get("game_id") or player.get("id") or "unknown")
    safe_reason = "".join(ch for ch in reason if ch.isalnum() or ch in {"_", "-"})[:40] or "backup"
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{game_id}_{safe_reason}.json"
    path = backup_dir / filename
    with path.open("w", encoding="utf-8") as file:
        json.dump(player, file, ensure_ascii=False, indent=2, default=str)
    return path


def _base_stats_for_player(player: dict[str, Any]) -> dict[str, int]:
    race_id = player.get("race_id")
    if race_id:
        try:
            races = load_races()
            race = races.get(str(race_id))
            if race and isinstance(race.get("stats"), dict):
                return {key: int(race["stats"].get(key, 0)) for key in STAT_KEYS}
        except Exception:
            pass

    existing_stats = player.get("stats") or {}
    return {key: int(existing_stats.get(key, 0)) for key in STAT_KEYS}


def delete_player_profile(storage: Any, identifier: str) -> tuple[bool, str, dict[str, Any] | None]:
    """Hard-delete a player by game_id so linked users must register again.

    This is not a reset and not a soft-delete. The previous profile is removed
    from the storage together with platform links, name index, link codes and
    web sessions. No profile backup is created for this operation.
    """
    game_id = normalize_game_id(identifier)
    if not is_valid_game_id(game_id):
        return (
            False,
            "Удаление выполняется только по игровому ID вида NT-XXXXXXXXXX. "
            "Пример: /admin_delete_player NT-1A2B3C4D5E CONFIRM_DELETE",
            None,
        )

    player = storage.get_player_by_game_id(game_id) if hasattr(storage, "get_player_by_game_id") else None
    if player is None:
        return False, f"Игрок {game_id} не найден. Проверь игровой ID в профиле игрока.", None

    if not hasattr(storage, "delete_player"):
        return False, "Хранилище не поддерживает жёсткое удаление игроков. Обнови проект до последней версии.", player

    deleted = bool(storage.delete_player(game_id))
    if not deleted:
        return False, f"Игрок {game_id} не найден или уже удалён.", player

    return (
        True,
        f"Профиль игрока {game_id} полностью удалён. "
        "Старые данные, привязки Telegram/VK, имя, web-сессии и коды привязки очищены. "
        "При любой следующей команде игрок будет отправлен на начало регистрации и начнёт с нуля.",
        player,
    )


def reset_player_progress(storage: Any, game_id: str) -> tuple[bool, str, dict[str, Any] | None]:
    player = storage.get_player_by_game_id(game_id)
    if player is None:
        return False, f"Игрок {game_id} не найден.", None

    backup_player(player, "before_reset")

    identity = {
        "id": player.get("game_id") or player.get("id"),
        "game_id": player.get("game_id") or player.get("id"),
        "public_id": player.get("public_id"),
        "main_platform": player.get("main_platform"),
        "linked_accounts": deepcopy(player.get("linked_accounts", {})),
        "name": player.get("name"),
        "race_id": player.get("race_id"),
        "race_name": player.get("race_name"),
        "created_at": player.get("created_at"),
    }

    reset_player = {
        **identity,
        "level": 1,
        "experience": 0,
        "current_city": "seldar",
        "current_zone": "seldar_central_square",
        "location_id": "seldar_central_square",
        "money": 0,
        "debt": 0,
        "energy": 100,
        "max_energy": 100,
        "bonus_max_energy": 0,
        "in_battle": False,
        "is_dead": False,
        "stats": _base_stats_for_player(player),
        "invested_stats": {key: 0 for key in STAT_KEYS},
        "stat_bonuses": {key: 0 for key in STAT_KEYS},
        "free_stat_points": 0,
        "free_skill_points": 0,
        "inventory": [],
        "storage": [],
        "equipment": get_starter_equipment(),
        "skills": get_starter_skills(),
        "active_effects": [],
        "known_recipes": [],
        "alchemy_level": 1,
        "alchemy_experience": 0,
        "unlocked_alchemy_recipes": [],
        "alchemy_known_failures": [],
        "owned_special_recipes": [],
        "crafting_levels": deepcopy(DEFAULT_CRAFTING_LEVELS),
        "housing": {"plot_type": None, "buildings": []},
        "admin_reset_at": datetime.now(timezone.utc).isoformat(),
    }

    storage.update_player(reset_player)
    return True, f"Прогресс игрока {game_id} обнулён.", reset_player


def add_item_to_player(
    storage: Any,
    *,
    game_id: str,
    item_id: str,
    amount: int = 1,
    quality: str = "обычный",
    item_data: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any] | None]:
    if amount <= 0:
        return False, "Количество предметов должно быть больше 0.", None
    if amount > 1_000_000:
        return False, "Слишком большое количество предметов.", None

    player = storage.get_player_by_game_id(game_id)
    if player is None:
        return False, f"Игрок {game_id} не найден.", None

    backup_player(player, "before_add_item")

    item = dict(item_data or {})
    item.setdefault("instance_id", f"adm-{uuid.uuid4().hex}")
    item.setdefault("item_id", item_id)
    item.setdefault("name", item.get("item_id", item_id))
    item["amount"] = amount
    item.setdefault("quality", quality)
    item.setdefault("source", "admin")
    item.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    player.setdefault("inventory", []).append(item)
    storage.update_player(player)

    return True, f"Игроку {game_id} добавлен предмет {item['item_id']} x{amount}.", player
