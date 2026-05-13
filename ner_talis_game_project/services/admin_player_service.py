"""Административные операции над профилем игрока."""

from __future__ import annotations

import json
import os
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


def _resolve_player_by_identifier(storage: Any, identifier: str) -> dict[str, Any] | None:
    raw = str(identifier or "").strip()
    if not raw:
        return None

    normalized = raw.strip().strip("\"'")

    if hasattr(storage, "get_player_by_game_id"):
        player = storage.get_player_by_game_id(normalized)
        if player is not None:
            return player

    lowered = normalized.casefold()
    platform: str | None = None
    external_id: str | None = None
    if lowered.startswith("tg_"):
        platform, external_id = "telegram", normalized[3:]
    elif lowered.startswith("vk_"):
        platform, external_id = "vk", normalized[3:]
    elif ":" in normalized:
        left, right = normalized.split(":", 1)
        if left.casefold() in {"telegram", "tg"}:
            platform, external_id = "telegram", right
        elif left.casefold() == "vk":
            platform, external_id = "vk", right

    if platform and external_id and hasattr(storage, "get_player_by_platform"):
        player = storage.get_player_by_platform(platform, external_id)
        if player is not None:
            return player

    if hasattr(storage, "get_player_by_public_id"):
        try:
            player = storage.get_player_by_public_id(normalized)
        except Exception:
            player = None
        if player is not None:
            return player

    # Fallback for all storages: scan loaded players. This also supports raw
    # numeric platform IDs when the value uniquely matches telegram_id/vk_id.
    matches: list[dict[str, Any]] = []
    if hasattr(storage, "load"):
        data = storage.load()
        for player in (data.get("players") or {}).values():
            if not isinstance(player, dict):
                continue
            values = {
                str(player.get("game_id") or ""),
                str(player.get("id") or ""),
                str(player.get("public_id") or ""),
                str(player.get("telegram_id") or ""),
                str(player.get("vk_id") or ""),
            }
            for platform_name, platform_id in (player.get("linked_accounts") or {}).items():
                if platform_id:
                    values.add(str(platform_id))
                    values.add(f"{platform_name}:{platform_id}")
                    if platform_name == "telegram":
                        values.add(f"tg_{platform_id}")
                    if platform_name == "vk":
                        values.add(f"vk_{platform_id}")
            if normalized in values:
                matches.append(player)

    if len(matches) == 1:
        return matches[0]
    return None


def delete_player_profile(storage: Any, identifier: str) -> tuple[bool, str, dict[str, Any] | None]:
    """Delete a player profile so linked users return to registration on /start."""
    player = _resolve_player_by_identifier(storage, identifier)
    if player is None:
        return False, f"Игрок {identifier} не найден. Используй настоящий game_id вида NT-..., public_id, tg_123456, vk_123456, telegram:123456 или vk:123456.", None

    game_id = str(player.get("game_id") or player.get("id"))
    backup_player(player, "before_delete")

    if hasattr(storage, "delete_player"):
        deleted = bool(storage.delete_player(game_id))
    else:
        data = storage.load()
        deleted = game_id in data.get("players", {})
        if deleted:
            data["players"].pop(game_id, None)
            data["platform_links"] = {
                key: value
                for key, value in data.get("platform_links", {}).items()
                if value != game_id
            }
            data["names"] = {
                key: value
                for key, value in data.get("names", {}).items()
                if value != game_id
            }
            data["link_codes"] = {
                key: value
                for key, value in data.get("link_codes", {}).items()
                if not isinstance(value, dict) or value.get("game_id") != game_id
            }
            for sessions_key in ("site_sessions", "web_sessions"):
                if sessions_key in data:
                    data[sessions_key] = {
                        token: session
                        for token, session in data.get(sessions_key, {}).items()
                        if not isinstance(session, dict) or session.get("game_id") != game_id
                    }
            storage.save(data)

    if not deleted:
        return False, f"Игрок {game_id} не найден или уже удалён.", player
    return True, f"Профиль игрока {game_id} удалён. При следующем /start игрок снова попадёт на регистрацию.", player


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
