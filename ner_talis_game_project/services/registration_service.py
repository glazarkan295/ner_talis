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
from project_paths import project_path, resolve_project_path

NAME_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё0-9 -]+$")
FORBIDDEN_NAMES = {
    "admin",
    "administrator",
    "moderator",
    "system",
    "support",
    "админ",
    "администратор",
    "модератор",
    "система",
    "поддержка",
}

DEFAULT_CRAFTING_LEVELS = {
    "smelting": {"level": 1, "experience": 0},
    "blacksmithing": {"level": 1, "experience": 0},
    "leatherworking": {"level": 1, "experience": 0},
    "jewelcrafting": {"level": 1, "experience": 0},
    "alchemy": {"level": 1, "experience": 0},
    "enchanting": {"level": 1, "experience": 0},
}


def load_races(path: str | Path | None = None) -> dict[str, Any]:
    races_path = project_path("data", "races.json") if path is None else resolve_project_path(path)
    with races_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


def validate_name(raw_name: str) -> tuple[bool, str]:
    name = normalize_name(raw_name)

    if len(name) < 3:
        return False, "Имя слишком короткое. Минимум 3 символа."

    if len(name) > 20:
        return False, "Имя слишком длинное. Максимум 20 символов."

    if not NAME_PATTERN.match(name):
        return False, "Имя может содержать только буквы, цифры, пробел и дефис."

    if name.casefold() in FORBIDDEN_NAMES:
        return False, "Это имя нельзя использовать."

    if name.startswith("-") or name.endswith("-"):
        return False, "Имя не может начинаться или заканчиваться дефисом."

    return True, name


def get_race_id_by_name(races: dict[str, Any], race_name: str) -> str | None:
    normalized = race_name.strip().casefold()
    for race_id, race_data in races.items():
        if race_data["name"].casefold() == normalized:
            return race_id
    return None


def format_race_card(race_id: str, races: dict[str, Any]) -> str:
    race = races[race_id]
    stats = race["stats"]
    bonuses = "\n".join(f"• {bonus}" for bonus in race["bonuses"])

    return (
        f"🧬 {race['name']}\n\n"
        f"{race['description']}\n\n"
        "Характеристики:\n"
        f"• Сила: {stats['strength']}\n"
        f"• Ловкость: {stats['dexterity']}\n"
        f"• Выносливость: {stats['endurance']}\n"
        f"• Интеллект: {stats['intelligence']}\n"
        f"• Мудрость: {stats['wisdom']}\n"
        f"• Восприятие: {stats['perception']}\n\n"
        "Бонусы расы:\n"
        f"{bonuses}"
    )


def build_profile_url(player: dict[str, Any]) -> str:
    base_url = os.getenv("SITE_PROFILE_BASE_URL", "https://example.com/profile")
    return f"{base_url.rstrip('/')}/{player['public_id']}"


def create_player(
    game_id: str,
    platform: str,
    external_user_id: str,
    name: str,
    race_id: str,
    races: dict[str, Any],
) -> dict[str, Any]:
    race = races[race_id]
    return {
        "id": game_id,
        "game_id": game_id,
        "public_id": str(uuid.uuid4()),
        "main_platform": platform,
        "linked_accounts": {
            platform: external_user_id,
        },
        "name": name,
        "race_id": race_id,
        "race_name": race["name"],
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
        "stats": race["stats"].copy(),
        "invested_stats": {
            "strength": 0,
            "dexterity": 0,
            "endurance": 0,
            "intelligence": 0,
            "wisdom": 0,
            "perception": 0,
        },
        "stat_bonuses": {
            "strength": 0,
            "dexterity": 0,
            "endurance": 0,
            "intelligence": 0,
            "wisdom": 0,
            "perception": 0,
        },
        "free_stat_points": 0,
        "free_skill_points": 0,
        "hp": None,
        "spirit": None,
        "mana": None,
        "branch": "Без ветви",
        "skill_branch": None,
        "branch_choice_hint_sent": False,
        "has_identification_amulet": True,
        "unlocked_skill_sources": [],
        "skill_equip_capacity": 2,
        "inventory": [],
        "storage": [],
        "equipment": get_starter_equipment(),
        "skills": get_starter_skills(),
        "starter_pack_applied": True,
        "active_effects": [],
        "active_sets": [],
        "known_recipes": [],
        "alchemy_level": 1,
        "alchemy_experience": 0,
        "unlocked_alchemy_recipes": [],
        "alchemy_known_failures": [],
        "owned_special_recipes": [],
        "crafting_levels": deepcopy(DEFAULT_CRAFTING_LEVELS),
        "housing": {
            "plot_type": None,
            "buildings": [],
        },
        "achievements": [],
        "rating": {"globalPlace": "—", "pvePlace": "—", "pvpPlace": "—", "craftPlace": "—"},
        "pve_kills": 0,
        "pvp_kills": 0,
        "soul_particles_absorbed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
