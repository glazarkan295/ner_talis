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


CONSENT_BUTTON = "Я прочитал и согласен"


def _doc_link(env_name: str) -> str:
    value = str(os.getenv(env_name, "") or "").strip()
    return value or "ссылка будет добавлена позже"


def registration_text(platform: str, key: str, fallback: str, **values: Any) -> str:
    try:
        from services.registration_constructor_service import scenario_text
        text = scenario_text(platform, key, fallback)
    except Exception:
        text = fallback
    try: return text.format(**values)
    except (KeyError, ValueError): return text


def registration_access(platform: str) -> tuple[bool, str]:
    try:
        from services.registration_constructor_service import active_scenario
        data = active_scenario(platform)
    except Exception:
        data = None
    if data and not data.get("registration_enabled", True):
        return False, str(data.get("closed_text") or "Регистрация временно закрыта.")
    return True, ""


def consent_message(platform: str = "telegram") -> str:
    """Сообщение-согласие перед регистрацией (со ссылками на документы)."""
    fallback = (
        "Перед началом игры, пожалуйста, ознакомьтесь с:\n\n"
        "📜 Политика конфиденциальности\n"
        f"{_doc_link('LINK_PRIVACY_POLICY')}\n\n"
        "🔒 Пользовательское соглашение\n"
        f"{_doc_link('LINK_TERMS_OF_SERVICE')}\n\n"
        "И подтвердите, если согласны с ними."
    )
    return registration_text(platform, "welcome_text", fallback)


def load_races(path: str | Path | None = None, platform: str | None = None) -> dict[str, Any]:
    races_path = project_path("data", "races.json") if path is None else resolve_project_path(path)
    with races_path.open("r", encoding="utf-8") as file:
        legacy = json.load(file)
    if path is not None:
        return legacy
    try:
        from services.race_constructor_service import registration_races
        published = registration_races()
    except Exception:
        published = {}
    if not published:
        return legacy
    out: dict[str, Any] = {}
    for rid, data in published.items():
        old = legacy.get(rid) or {}
        stats = dict(old.get("stats") or {})
        authored = data.get("starting_stats") or {}
        for key, value in authored.items():
            stats["dexterity" if key == "agility" else key] = value
        visible = [str(row.get("description") or row.get("name") or row.get("id")) for row in data.get("bonuses") or [] if isinstance(row, dict) and row.get("show_player", True)]
        out[rid] = {**old, **data, "name": data.get("player_name") or data.get("race_name") or old.get("name") or rid,
                    "description": data.get("description") or old.get("description") or "", "stats": stats,
                    "bonuses": visible or old.get("bonuses") or []}
    if platform:
        try:
            from services.registration_constructor_service import active_scenario
            allowed = {str(x) for x in (active_scenario(platform) or {}).get("available_races") or []}
            if allowed: out = {rid: row for rid, row in out.items() if rid in allowed}
        except Exception: pass
    return out


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


def validate_name(raw_name: str, platform: str = "telegram") -> tuple[bool, str]:
    name = normalize_name(raw_name)
    try:
        from services.registration_constructor_service import active_scenario
        scenario = active_scenario(platform) or {}
    except Exception: scenario = {}
    minimum=max(1,int(float(scenario.get("name_min_length") or 3)));maximum=max(minimum,int(float(scenario.get("name_max_length") or 20)))
    if len(name) < minimum:return False,registration_text(platform,"name_error_text",f"Имя слишком короткое. Минимум {minimum} символа.")
    if len(name) > maximum:return False,registration_text(platform,"name_error_text",f"Имя слишком длинное. Максимум {maximum} символов.")

    if not NAME_PATTERN.match(name):
        return False, "Имя может содержать только буквы, цифры, пробел и дефис."

    forbidden=FORBIDDEN_NAMES|{str(x).casefold() for x in scenario.get("forbidden_names") or []}
    if name.casefold() in forbidden:
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
    gender_id: str | None = None,
    gender_label: str | None = None,
) -> dict[str, Any]:
    race = races[race_id]
    try:
        from services.level_constructor_service import active_rule
        progression=active_rule()
    except Exception:progression={}
    start_level=max(1,int(progression.get("start_level") or 1));start_exp=max(0,int(progression.get("start_experience") or 0))
    try:
        from services.progression_service import experience_to_next_level
        start_next=experience_to_next_level(start_level)
    except Exception:start_next=start_level*100
    player = {
        "id": game_id,
        "game_id": game_id,
        "public_id": str(uuid.uuid4()),
        "main_platform": platform,
        "linked_accounts": {
            platform: external_user_id,
        },
        "name": name,
        "gender": gender_id or "not_selected",
        "gender_label": gender_label or "Не выбран",
        "race_id": race_id,
        "race_name": race["name"],
        "level": start_level,
        "experience": start_exp,
        "experience_to_next": start_next,
        "total_experience": start_exp,
        "current_city": "seldar",
        "current_zone": "seldar_central_square",
        "location_id": "seldar_central_square",
        "money": 0,
        "debt": 0,
        "energy": int(race.get("start_energy") or 100),
        "max_energy": int(race.get("start_energy") or 100),
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
        "hp": race.get("start_hp"),
        "max_hp": race.get("start_hp"),
        "spirit": race.get("start_spirit"),
        "max_spirit": race.get("start_spirit"),
        "mana": race.get("start_mana"),
        "max_mana": race.get("start_mana"),
        "branch": "Без ветви",
        "skill_branch": None,
        "main_skill_path": None,
        "secondary_skill_path": None,
        "chosen_skill_groups": [],
        "branch_choice_hint_sent": False,
        "secondary_path_hint_sent": False,
        "path_threshold_hint_sent": False,
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
    for key in ("accuracy", "dodge", "crit_chance", "crit_damage", "physical_defense", "magic_defense", "armor", "physical_damage", "magic_damage"):
        if race.get(key) not in (None, ""):
            player[key] = int(float(race[key]))
    try:
        from services.registration_constructor_service import apply_starting_setup
        apply_starting_setup(player, platform)
    except Exception:
        pass
    try:
        from services.race_bonus_service import sync_passive_effects
        sync_passive_effects(player)
    except Exception:
        pass
    return player
