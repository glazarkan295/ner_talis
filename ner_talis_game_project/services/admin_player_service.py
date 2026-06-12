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
from services.inventory_service import add_inventory_item
from services.item_registry import build_inventory_item
from services.progression_service import experience_to_next_level
from services.registration_service import DEFAULT_CRAFTING_LEVELS, load_races

STAT_KEYS = ("strength", "dexterity", "endurance", "intelligence", "wisdom", "perception")
GAME_ID_PATTERN = re.compile(r"^NT-[A-Z0-9]{10}$", re.IGNORECASE)


def normalize_game_id(identifier: str) -> str:
    """Возвращает игровой ID в каноническом виде NT-XXXXXXXXXX."""
    return str(identifier or "").strip().strip("\'\"").upper()


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


def _fallback_hard_delete_player_by_game_id(storage: Any, game_id: str) -> bool:
    """Hard-delete through generic load/save for storages without a native method."""
    if not hasattr(storage, "load") or not hasattr(storage, "save"):
        return False

    data = storage.load()
    players = data.setdefault("players", {})
    normalized_game_id = normalize_game_id(game_id)
    real_key = normalized_game_id if normalized_game_id in players else None

    if real_key is None:
        for key, player in players.items():
            if not isinstance(player, dict):
                continue
            if normalize_game_id(player.get("game_id") or player.get("id") or "") == normalized_game_id:
                real_key = key
                break

    if real_key is None:
        return False

    player = players.pop(real_key, None) or {}
    target_ids = {str(real_key), normalized_game_id}
    if isinstance(player, dict):
        target_ids.add(str(player.get("game_id") or ""))
        target_ids.add(str(player.get("id") or ""))

    for index_name in ("platform_links", "names"):
        data[index_name] = {
            key: value
            for key, value in data.get(index_name, {}).items()
            if str(value) not in target_ids
        }

    data["link_codes"] = {
        key: value
        for key, value in data.get("link_codes", {}).items()
        if not isinstance(value, dict) or str(value.get("game_id") or "") not in target_ids
    }

    for sessions_key in ("site_sessions", "web_sessions"):
        data[sessions_key] = {
            token: session
            for token, session in data.get(sessions_key, {}).items()
            if not isinstance(session, dict) or str(session.get("game_id") or "") not in target_ids
        }

    storage.save(data)
    return True


def delete_player_profile(storage: Any, identifier: str) -> tuple[bool, str, dict[str, Any] | None]:
    """Безоговорочно удаляет профиль игрока по game_id NT-XXXXXXXXXX.

    Это не сброс и не мягкое удаление. Профиль удаляется вместе с
    Telegram/VK-привязками, занятым именем, web-сессиями и кодами привязки.
    Backup старого профиля не создаётся, чтобы игрок начал полностью с нуля.
    """
    game_id = normalize_game_id(identifier)
    if not is_valid_game_id(game_id):
        return (
            False,
            "Удаление выполняется только по игровому ID вида NT-XXXXXXXXXX. "
            "Пример: /admin_delete_player NT-1A2B3C4D5E CONFIRM_DELETE",
            None,
        )

    if not hasattr(storage, "get_player_by_game_id"):
        return False, "Хранилище не умеет искать игроков по game_id. Обнови проект до этой версии.", None

    player = storage.get_player_by_game_id(game_id)
    if player is None:
        return False, f"Игрок {game_id} не найден. Проверь игровой ID в профиле игрока.", None

    delete_method = getattr(storage, "hard_delete_player_by_game_id", None)
    if callable(delete_method):
        deleted = bool(delete_method(game_id))
    else:
        deleted = _fallback_hard_delete_player_by_game_id(storage, game_id)

    if not deleted:
        return False, f"Игрок {game_id} не найден или уже удалён.", player

    try:
        still_exists_by_game_id = storage.get_player_by_game_id(game_id)
    except Exception as exc:
        return False, f"Удаление выполнено с ошибкой проверки: {exc}", player

    if still_exists_by_game_id is not None:
        return (
            False,
            f"Ошибка: хранилище сообщило об удалении {game_id}, но профиль всё ещё находится по игровому ID. "
            "Обнови проект и перезапусти приложение на Timeweb.",
            player,
        )

    linked_accounts = player.get("linked_accounts") if isinstance(player, dict) else {}
    if isinstance(linked_accounts, dict) and hasattr(storage, "get_player_by_platform"):
        for platform, external_user_id in linked_accounts.items():
            if not external_user_id:
                continue
            try:
                linked_player = storage.get_player_by_platform(platform, external_user_id)
            except Exception as exc:
                return False, f"Удаление выполнено с ошибкой проверки привязки {platform}: {exc}", player
            if linked_player is not None:
                return (
                    False,
                    f"Ошибка: профиль {game_id} удалён не полностью — привязка {platform}:{external_user_id} всё ещё открывает персонажа. "
                    "Обнови проект и перезапусти приложение на Timeweb.",
                    player,
                )

    return (
        True,
        f"Профиль игрока {game_id} полностью удалён. "
        "Старые данные, привязки Telegram/VK, имя, web-сессии и коды привязки очищены. "
        "При следующей команде игрок будет отправлен на начало регистрации и начнёт с нуля.",
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
        "experience_to_next": 100,
        "total_experience": 0,
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

    explicit_source = item_data is not None and item_data.get("source") is not None
    if item_data:
        item = dict(item_data)
    else:
        # Simple admin commands should use the same item registry as loot, market
        # and camp crafting. Otherwise /admin_add_item dried_meat would create
        # a bare technical item named "dried_meat" without Russian name, icon,
        # stack size, sale price or use effect.
        item = build_inventory_item(item_id, amount, item_id=item_id)

    item.setdefault("instance_id", f"adm-{uuid.uuid4().hex}")
    item.setdefault("item_id", item_id)
    item.setdefault("id", item.get("item_id", item_id))
    item.setdefault("name", item.get("name_ru") or item.get("item_id", item_id))
    item["amount"] = amount
    item["quality"] = quality or item.get("quality") or "обычный"
    if not explicit_source:
        item["source"] = "admin"
    item.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    result = add_inventory_item(player, item, amount, default_source="admin")
    storage.update_player(player)

    if result.added <= 0:
        return False, "В инвентаре нет свободного места, предмет не добавлен.", player
    suffix = f" В доп. слот попало: {result.added_to_overflow}." if result.added_to_overflow else ""
    if result.discarded:
        suffix += f" Не поместилось: {result.discarded}."
    return True, f"Игроку {game_id} добавлен предмет {item['item_id']} x{result.added}.{suffix}", player


def _iter_players(storage: Any) -> list[dict[str, Any]]:
    """Возвращает список профилей для безопасных админ-поисков."""
    if not hasattr(storage, "load"):
        return []
    data = storage.load()
    players = data.get("players") or {}
    return [player for player in players.values() if isinstance(player, dict)]


def _player_platform_pairs(player: dict[str, Any]) -> list[str]:
    linked_accounts = player.get("linked_accounts") or {}
    if not isinstance(linked_accounts, dict):
        return []
    pairs: list[str] = []
    for platform, external_user_id in linked_accounts.items():
        if external_user_id:
            pairs.append(f"{platform}:{external_user_id}")
    return pairs


def format_player_admin_summary(player: dict[str, Any]) -> str:
    """Короткая карточка игрока для админ-чата без огромного JSON."""
    inventory = player.get("inventory") if isinstance(player.get("inventory"), list) else []
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    active_effects = player.get("active_effects") if isinstance(player.get("active_effects"), list) else []
    location = player.get("location_id") or player.get("current_zone") or player.get("current_city") or "не указано"
    linked = ", ".join(_player_platform_pairs(player)) or "нет"
    inventory_preview = []
    for item in inventory[:8]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("name_ru") or item.get("item_id") or item.get("id") or "предмет"
        amount = item.get("amount", 1)
        inventory_preview.append(f"{name}×{amount}")
    preview_text = "; ".join(inventory_preview) if inventory_preview else "пусто/не показано"
    if len(inventory) > 8:
        preview_text += f"; … ещё {len(inventory) - 8}"

    return (
        f"Игрок: {player.get('name') or 'без имени'}\n"
        f"game_id: {player.get('game_id') or player.get('id')}\n"
        f"public_id: {player.get('public_id') or 'нет'}\n"
        f"Привязки: {linked}\n"
        f"Уровень: {player.get('level', 1)}, опыт: {player.get('experience', 0)}/{player.get('experience_to_next', '?')}\n"
        f"Монеты: {player.get('money', 0)}, долг/штраф: {player.get('debt', 0)}\n"
        f"HP: {player.get('hp', player.get('current_hp', '?'))}/{player.get('max_hp', '?')}, "
        f"энергия: {player.get('energy', '?')}/{player.get('max_energy', '?')}\n"
        f"Локация: {location}\n"
        f"В бою: {'да' if player.get('in_battle') else 'нет'}, мёртв: {'да' if player.get('is_dead') else 'нет'}\n"
        f"Инвентарь: {len(inventory)} стеков. {preview_text}\n"
        f"Экипировка: {len([value for value in equipment.values() if value])} занятых слотов\n"
        f"Активные эффекты: {len(active_effects)}"
    )


def find_players(storage: Any, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Ищет игроков по game_id/public_id/имени/Telegram/VK id."""
    needle = str(query or "").strip()
    if not needle:
        return []
    needle_cf = needle.casefold()
    normalized_game_id = normalize_game_id(needle)

    # Сначала быстрый точный поиск по game_id, если хранилище умеет.
    if is_valid_game_id(normalized_game_id) and hasattr(storage, "get_player_by_game_id"):
        player = storage.get_player_by_game_id(normalized_game_id)
        if player:
            return [player]

    # Поиск по platform id в стандартных вариантах.
    if hasattr(storage, "get_player_by_platform"):
        for platform in ("telegram", "vk"):
            raw_id = needle
            if needle_cf.startswith("tg_") and platform == "telegram":
                raw_id = needle[3:]
            elif needle_cf.startswith("vk_") and platform == "vk":
                raw_id = needle[3:]
            try:
                player = storage.get_player_by_platform(platform, raw_id)
            except Exception:
                player = None
            if player:
                return [player]

    matches: list[dict[str, Any]] = []
    for player in _iter_players(storage):
        fields = [
            str(player.get("game_id") or player.get("id") or ""),
            str(player.get("public_id") or ""),
            str(player.get("name") or ""),
        ]
        fields.extend(_player_platform_pairs(player))
        if any(needle_cf in field.casefold() for field in fields):
            matches.append(player)
            if len(matches) >= max(1, int(limit)):
                break
    return matches



def _safe_admin_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _grant_exact_experience(player: dict[str, Any], amount: int) -> dict[str, Any]:
    """Начисляет опыт ровно 1 к 1 для админ-наград/крупиц опыта.

    Обычный grant_experience применяет расовые бонусы. Для админ-команды
    крупицы опыта должны считаться буквально: 1 крупица = 1 единица опыта.
    """
    gained = max(0, _safe_admin_int(amount, 0))
    player["experience"] = max(0, _safe_admin_int(player.get("experience"), 0)) + gained
    player["total_experience"] = max(0, _safe_admin_int(player.get("total_experience"), 0)) + gained

    level_ups = 0
    while True:
        level = max(1, _safe_admin_int(player.get("level"), 1))
        required = experience_to_next_level(level)
        if player["experience"] < required:
            player["experience_to_next"] = required
            break
        player["experience"] -= required
        player["level"] = level + 1
        player["free_stat_points"] = _safe_admin_int(player.get("free_stat_points"), 0) + 5
        player["free_skill_points"] = _safe_admin_int(player.get("free_skill_points"), 0) + 2
        level_ups += 1

    return {
        "gained": gained,
        "level_ups": level_ups,
        "level": max(1, _safe_admin_int(player.get("level"), 1)),
        "experience": _safe_admin_int(player.get("experience"), 0),
        "experience_to_next": _safe_admin_int(player.get("experience_to_next"), experience_to_next_level(max(1, _safe_admin_int(player.get("level"), 1)))),
    }


def add_experience_to_player(storage: Any, *, game_id: str, amount: int) -> tuple[bool, str, dict[str, Any] | None]:
    """Админское начисление крупиц опыта: 1 крупица = 1 единица опыта."""
    if amount <= 0:
        return False, "Количество крупиц опыта должно быть больше 0.", None
    if amount > 1_000_000_000:
        return False, "Слишком большое количество опыта для одной админ-команды.", None

    player = storage.get_player_by_game_id(normalize_game_id(game_id)) if hasattr(storage, "get_player_by_game_id") else None
    if player is None:
        return False, f"Игрок {game_id} не найден.", None

    old_level = max(1, _safe_admin_int(player.get("level"), 1))
    old_exp = _safe_admin_int(player.get("experience"), 0)
    backup_player(player, "before_admin_experience")
    progress = _grant_exact_experience(player, amount)
    player["admin_experience_changed_at"] = datetime.now(timezone.utc).isoformat()
    storage.update_player(player)

    level_part = f", уровень {old_level} -> {progress['level']}" if progress["level"] != old_level else ""
    ups_part = f", повышений уровня: {progress['level_ups']}" if progress["level_ups"] else ""
    return (
        True,
        f"Игроку {player.get('game_id')} начислены крупицы опыта: +{amount}. "
        f"Опыт: {old_exp} -> {progress['experience']}/{progress['experience_to_next']}"
        f"{level_part}{ups_part}.",
        player,
    )


def _add_free_points_to_player(
    storage: Any,
    *,
    game_id: str,
    amount: int,
    field_name: str,
    label: str,
    backup_reason: str,
) -> tuple[bool, str, dict[str, Any] | None]:
    if amount == 0:
        return False, f"Количество для изменения поля «{label}» должно быть не равно 0.", None
    if abs(amount) > 1_000_000:
        return False, "Слишком большое количество очков для одной админ-команды.", None

    player = storage.get_player_by_game_id(normalize_game_id(game_id)) if hasattr(storage, "get_player_by_game_id") else None
    if player is None:
        return False, f"Игрок {game_id} не найден.", None

    old_value = _safe_admin_int(player.get(field_name), 0)
    new_value = old_value + int(amount)
    if new_value < 0:
        return False, f"Нельзя списать {abs(amount)}: у игрока только {old_value} ({label}).", player

    backup_player(player, backup_reason)
    player[field_name] = new_value
    player["admin_points_changed_at"] = datetime.now(timezone.utc).isoformat()
    storage.update_player(player)
    sign = "+" if amount > 0 else ""
    return True, f"{label} игрока {player.get('game_id')} изменены: {old_value} -> {new_value} ({sign}{amount}).", player


def add_stat_points_to_player(storage: Any, *, game_id: str, amount: int) -> tuple[bool, str, dict[str, Any] | None]:
    """Админское изменение очков характеристик: 1 единица = 1 свободное очко характеристик."""
    return _add_free_points_to_player(
        storage,
        game_id=game_id,
        amount=amount,
        field_name="free_stat_points",
        label="Очки характеристик",
        backup_reason="before_admin_stat_points",
    )


def add_skill_points_to_player(storage: Any, *, game_id: str, amount: int) -> tuple[bool, str, dict[str, Any] | None]:
    """Админское изменение очков навыков: 1 единица = 1 свободное очко навыков."""
    return _add_free_points_to_player(
        storage,
        game_id=game_id,
        amount=amount,
        field_name="free_skill_points",
        label="Очки навыков",
        backup_reason="before_admin_skill_points",
    )

def add_money_to_player(storage: Any, *, game_id: str, amount: int) -> tuple[bool, str, dict[str, Any] | None]:
    """Админское изменение медных монет игрока с backup и защитой от минуса."""
    if amount == 0:
        return False, "Сумма должна быть не равна 0.", None
    if abs(amount) > 1_000_000_000_000:
        return False, "Слишком большая сумма для одной админ-команды.", None

    player = storage.get_player_by_game_id(normalize_game_id(game_id)) if hasattr(storage, "get_player_by_game_id") else None
    if player is None:
        return False, f"Игрок {game_id} не найден.", None

    old_money = int(player.get("money", 0) or 0)
    new_money = old_money + int(amount)
    if new_money < 0:
        return False, f"Нельзя списать {abs(amount)} медных: у игрока только {old_money}.", player

    backup_player(player, "before_admin_money")
    player["money"] = new_money
    player["admin_money_changed_at"] = datetime.now(timezone.utc).isoformat()
    storage.update_player(player)
    sign = "+" if amount > 0 else ""
    return True, f"Монеты игрока {player.get('game_id')} изменены: {old_money} -> {new_money} ({sign}{amount}).", player


def kick_player_profile_sessions(storage: Any, *, game_id: str, scope: str = "profile") -> tuple[bool, str, int]:
    """Удаляет активные web/site-сессии игрока для профиля."""
    normalized_game_id = normalize_game_id(game_id)
    if not is_valid_game_id(normalized_game_id):
        return False, "Укажи игровой ID вида NT-XXXXXXXXXX.", 0
    if not hasattr(storage, "get_player_by_game_id") or storage.get_player_by_game_id(normalized_game_id) is None:
        return False, f"Игрок {normalized_game_id} не найден.", 0

    # PostgreSQL save(data) не удаляет отсутствующие сессии, поэтому для него нужен нативный DELETE.
    engine = getattr(storage, "engine", None)
    if engine is not None:
        try:
            from sqlalchemy import text

            with engine.begin() as connection:
                result = connection.execute(
                    text("DELETE FROM web_sessions WHERE game_id = :game_id AND scope = :scope"),
                    {"game_id": normalized_game_id, "scope": scope},
                )
                deleted = int(result.rowcount or 0)
            return True, f"Web-сессии игрока {normalized_game_id} отключены. Удалено: {deleted}.", deleted
        except Exception as exc:
            return False, f"Не удалось отключить web-сессии в PostgreSQL: {exc}", 0

    if not hasattr(storage, "load") or not hasattr(storage, "save"):
        return False, "Хранилище не поддерживает массовое отключение сессий.", 0

    data = storage.load()
    deleted = 0
    for key in ("site_sessions", "web_sessions"):
        sessions = data.get(key) or {}
        if not isinstance(sessions, dict):
            continue
        for token, session in list(sessions.items()):
            if not isinstance(session, dict):
                continue
            if str(session.get("game_id") or "").upper() == normalized_game_id and str(session.get("scope") or scope) == scope:
                sessions.pop(token, None)
                deleted += 1
        data[key] = sessions
    storage.save(data)
    return True, f"Web-сессии игрока {normalized_game_id} отключены. Удалено: {deleted}.", deleted
