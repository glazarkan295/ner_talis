"""Active-skill paths runtime for Ner-Talis.

This module integrates the 0-10000 path skill catalog.  Players choose a main
branch/path at the Order Stone, may later choose a secondary path, unlock one of
three skills at each available path threshold, and spend free skill points on
skill modifiers.  The two neutral starter skills remain intact and are still
available to every character.
"""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from project_paths import project_path

ACTIVE_SKILL_BRANCH_INTEGRATION_ENABLED = True
STARTER_SKILL_IDS = {"basic_attack", "magic_spark"}
STARTER_SKILL_NAMES = {"Обычный удар", "Магический сгусток"}
ACTIVE_BRANCH_TEXT = (
    "Система путей активных и пассивных навыков включена. "
    "На 10 уровне игрок выбирает ветку Духа или Маны у Распорядительного камня."
)
DISABLED_BRANCH_TEXT = ACTIVE_BRANCH_TEXT  # Compatibility for old imports.

SPIRIT_BRANCH = "Дух"
MANA_BRANCH = "Мана"
BRANCH_ALIASES = {
    "spirit": SPIRIT_BRANCH,
    "дух": SPIRIT_BRANCH,
    "ветвь духа": SPIRIT_BRANCH,
    "Ветвь Духа": SPIRIT_BRANCH,
    "Выбрать Ветвь Духа": SPIRIT_BRANCH,
    "mana": MANA_BRANCH,
    "мана": MANA_BRANCH,
    "ветвь маны": MANA_BRANCH,
    "Ветвь Маны": MANA_BRANCH,
    "Выбрать Ветвь Маны": MANA_BRANCH,
}

SPIRIT_PATHS = ["Меч", "Кинжал", "Топор", "Молот", "Лук", "Щит", "Арбалет"]
MANA_PATHS = ["Огонь", "Вода", "Земля", "Воздух", "Поддержка", "Смерть", "Жизнь"]
PATHS_BY_BRANCH = {SPIRIT_BRANCH: SPIRIT_PATHS, MANA_BRANCH: MANA_PATHS}
PATH_ALIASES = {
    "sword": "Меч", "меч": "Меч", "Меч": "Меч",
    "dagger": "Кинжал", "кинжал": "Кинжал", "Кинжал": "Кинжал",
    "axe": "Топор", "топор": "Топор", "Топор": "Топор",
    "hammer": "Молот", "молот": "Молот", "Молот": "Молот",
    "bow": "Лук", "лук": "Лук", "Лук": "Лук",
    "shield": "Щит", "щит": "Щит", "Щит": "Щит",
    "crossbow": "Арбалет", "арбалет": "Арбалет", "Арбалет": "Арбалет",
    "fire": "Огонь", "огонь": "Огонь", "Огонь": "Огонь",
    "water": "Вода", "вода": "Вода", "Вода": "Вода",
    "earth": "Земля", "земля": "Земля", "Земля": "Земля",
    "air": "Воздух", "воздух": "Воздух", "Воздух": "Воздух",
    "support": "Поддержка", "поддержка": "Поддержка", "Поддержка": "Поддержка",
    "death": "Смерть", "смерть": "Смерть", "Смерть": "Смерть",
    "life": "Жизнь", "жизнь": "Жизнь", "Жизнь": "Жизнь",
}
PATH_TO_WEAPON = {
    "Меч": ["sword"],
    "Кинжал": ["dagger"],
    "Топор": ["axe"],
    "Молот": ["hammer"],
    "Лук": ["bow"],
    "Щит": ["shield"],
    "Арбалет": ["crossbow"],
    "Огонь": ["staff", "magic_book"],
    "Вода": ["staff", "magic_book"],
    "Земля": ["staff", "magic_book"],
    "Воздух": ["staff", "magic_book"],
    "Поддержка": ["staff", "magic_book"],
    "Смерть": ["staff", "magic_book"],
    "Жизнь": ["staff", "magic_book"],
}
PATH_EN = {
    "Меч": "sword", "Кинжал": "dagger", "Топор": "axe", "Молот": "hammer",
    "Лук": "bow", "Щит": "shield", "Арбалет": "crossbow",
    "Огонь": "fire", "Вода": "water", "Земля": "earth", "Воздух": "air",
    "Поддержка": "support", "Смерть": "death", "Жизнь": "life",
}

THRESHOLDS = [25, 50, 100, 200, 500, 800, 1000, 1500, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
SECONDARY_PATH_RATIO = 0.6
MODIFIER_SOFTENING = 30

RUS_TO_BACK_ATTRIBUTE = {
    "Сила": "strength",
    "Выносливость": "endurance",
    "Ловкость": "dexterity",
    "Восприятие": "perception",
    "Интеллект": "intelligence",
    "Мудрость": "wisdom",
    "str": "strength",
    "end": "endurance",
    "agi": "dexterity",
    "dex": "dexterity",
    "per": "perception",
    "int": "intelligence",
    "wis": "wisdom",
}

PROFILE_ATTRIBUTE_KEYS = {
    "str": "strength",
    "end": "endurance",
    "agi": "dexterity",
    "dex": "dexterity",
    "per": "perception",
    "int": "intelligence",
    "wis": "wisdom",
    "strength": "strength",
    "endurance": "endurance",
    "dexterity": "dexterity",
    "perception": "perception",
    "intelligence": "intelligence",
    "wisdom": "wisdom",
}

ATTRIBUTE_RE = re.compile(r"(Сила|Выносливость|Ловкость|Восприятие|Интеллект|Мудрость)\s*[×x*]\s*(\d+(?:[.,]\d+)?)\s*%", re.I)
INT_RE = re.compile(r"(\d+)")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _canon_branch(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"Без ветви", "Ветви отключены"}:
        return None
    return BRANCH_ALIASES.get(text, BRANCH_ALIASES.get(text.casefold(), text if text in PATHS_BY_BRANCH else None))


def _canon_path(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("Путь: "):
        text = text.split(":", 1)[1].strip()
    return PATH_ALIASES.get(text, PATH_ALIASES.get(text.casefold(), text if text in PATH_ALIASES.values() else None))


@lru_cache(maxsize=1)
def load_active_skill_registry() -> dict[str, Any]:
    path = project_path("data", "active_skills_registry.json")
    if not path.exists():
        return {"skills": [], "counts": {}}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return {"skills": data, "counts": {}}
    if isinstance(data, dict) and isinstance(data.get("skills"), list):
        return data
    return {"skills": [], "counts": {}}


@lru_cache(maxsize=1)
def load_active_skill_counts() -> dict[str, Any]:
    path = project_path("data", "active_skills_counts.json")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return data.get("skill_counts") if isinstance(data.get("skill_counts"), dict) else data
    return {}


@lru_cache(maxsize=1)
def load_branch_choice_messages() -> dict[str, Any]:
    path = project_path("data", "branch_choice_messages.json")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def all_catalog_skills() -> tuple[dict[str, Any], ...]:
    skills = load_active_skill_registry().get("skills")
    return tuple(skill for skill in skills if isinstance(skill, dict)) if isinstance(skills, list) else tuple()


@lru_cache(maxsize=1)
def _catalog_by_id() -> dict[str, dict[str, Any]]:
    return {str(skill.get("id")): skill for skill in all_catalog_skills() if skill.get("id")}


def catalog_skill_by_id(skill_id: str) -> dict[str, Any] | None:
    skill = _catalog_by_id().get(str(skill_id or ""))
    return deepcopy(skill) if skill else None


def skills_for_group(choice_group: str) -> list[dict[str, Any]]:
    group = str(choice_group or "")
    skills = [deepcopy(skill) for skill in all_catalog_skills() if str(skill.get("choice_group") or "") == group]
    return sorted(skills, key=lambda item: _safe_int(item.get("choice_index"), 0))


def _parse_attribute_profile(formula: Any) -> dict[str, float]:
    text = str(formula or "")
    profile: dict[str, float] = {}
    for attr, percent in ATTRIBUTE_RE.findall(text):
        key = RUS_TO_BACK_ATTRIBUTE.get(attr, attr)
        profile[key] = profile.get(key, 0.0) + float(str(percent).replace(",", ".")) / 100.0
    return profile


def _parse_first_int(value: Any, default: int = 0) -> int:
    if isinstance(value, (int, float)):
        return max(0, int(value))
    match = INT_RE.search(str(value or ""))
    return max(0, int(match.group(1))) if match else default


def _resource_type(skill: dict[str, Any]) -> str:
    raw = str(skill.get("resource_type") or skill.get("resource") or "").casefold()
    if "дух" in raw or raw == "spirit":
        return "spirit"
    if "мана" in raw or raw == "mana":
        return "mana"
    return "none"


def _damage_type(skill: dict[str, Any]) -> str:
    raw = str(skill.get("damage_type") or skill.get("resource_type") or "").casefold()
    if skill.get("is_passive") or "пассив" in raw:
        return "none"
    if "маг" in raw or "мана" in raw or str(skill.get("branch")) == MANA_BRANCH:
        return "magic"
    if "смеш" in raw or "оба" in raw:
        return "mixed"
    return "physical"


def _normalise_weapon_token(value: Any) -> str:
    raw = str(value or "").strip().casefold()
    aliases = {
        "меч": "sword",
        "sword": "sword",
        "кинжал": "dagger",
        "dagger": "dagger",
        "топор": "axe",
        "axe": "axe",
        "молот": "hammer",
        "hammer": "hammer",
        "булава": "hammer",
        "лук": "bow",
        "bow": "bow",
        "щит": "shield",
        "shield": "shield",
        "арбалет": "crossbow",
        "crossbow": "crossbow",
        "посох": "staff",
        "staff": "staff",
        "магическая книга": "magic_book",
        "magic_book": "magic_book",
        "any": "any",
        "любой": "any",
    }
    return aliases.get(raw, raw)


def _weapon_requirements_for_skill(skill: dict[str, Any]) -> list[str]:
    existing = skill.get("weapon_requirements")
    if isinstance(existing, str) and existing.strip():
        return [_normalise_weapon_token(existing)]
    if isinstance(existing, list) and existing:
        tokens = [_normalise_weapon_token(item) for item in existing if str(item or "").strip()]
        return sorted({token for token in tokens if token}) or ["any"]
    path = _canon_path(skill.get("path"))
    requirements = skill.get("usage_requirements") or []
    if isinstance(requirements, str):
        requirements = [requirements]
    text = " ".join([str(skill.get("required_equipment") or "")] + [str(item) for item in requirements]).casefold()
    tokens: set[str] = set(PATH_TO_WEAPON.get(path or "", []))
    if "меч" in text:
        tokens.add("sword")
    if "кинжал" in text:
        tokens.add("dagger")
    if "топор" in text:
        tokens.add("axe")
    if "молот" in text:
        tokens.add("hammer")
    if "лук" in text:
        tokens.add("bow")
    if "щит" in text:
        tokens.add("shield")
    if "арбал" in text:
        tokens.add("crossbow")
    if "посох" in text:
        tokens.add("staff")
    if "книг" in text:
        tokens.add("magic_book")
    return sorted(tokens) or ["any"]


def _ammo_requirements(skill: dict[str, Any], weapons: list[str]) -> dict[str, Any]:
    requirements_by_weapon: dict[str, dict[str, Any]] = {}
    if "bow" in weapons:
        requirements_by_weapon["bow"] = {
            "ammo_item_id": "arrow_for_bow",
            "ammo_name": "Стрела",
            "ammo_short_name": "стрела",
            "consume_per_use": 1,
            "quiver_slot": "arrow_quiver",
            "quiver_requirement": {"quiver_slot": "arrow_quiver", "missing_quiver_message": "Нужен колчан для стрел."},
            "missing_loaded_ammo_message": "В колчане нет стрел.",
        }
    if "crossbow" in weapons:
        requirements_by_weapon["crossbow"] = {
            "ammo_item_id": "bolt_for_crossbow",
            "ammo_name": "Болт",
            "ammo_short_name": "болт",
            "consume_per_use": 1,
            "quiver_slot": "bolt_quiver",
            "quiver_requirement": {"quiver_slot": "bolt_quiver", "missing_quiver_message": "Нужен колчан для болтов."},
            "missing_loaded_ammo_message": "В колчане нет болтов.",
        }
    return {"enabled": True, "requirements_by_weapon": requirements_by_weapon} if requirements_by_weapon else {}


def _modifier_id(name: str, index: int) -> str:
    safe = re.sub(r"[^a-zа-яё0-9]+", "_", str(name).casefold(), flags=re.I).strip("_")
    return safe or f"mod_{index + 1}"


def _catalog_modifier_dicts(skill: dict[str, Any]) -> list[dict[str, Any]]:
    raw_modifiers = skill.get("modifiers") or []
    if isinstance(raw_modifiers, str):
        raw_modifiers = [raw_modifiers]
    modifiers: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_modifiers if isinstance(raw_modifiers, list) else []):
        if isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("label") or f"Модификатор {index + 1}")
            effect = str(raw.get("effect") or raw.get("description") or "Усиливает навык.")
            level = _safe_int(raw.get("level") if "level" in raw else raw.get("points"), 0)
        else:
            name = str(raw or f"Модификатор {index + 1}")
            effect = f"Усиливает параметр: {name}."
            level = 0
        modifiers.append({
            "id": _modifier_id(name, index),
            "name": name,
            "label": name,
            "type": name,
            "effect": effect,
            "description": effect,
            "level": level,
            "displayFormat": "+0,00%",
            "modifier_formula": skill.get("modifier_formula") or f"Бонус % = floor(30 × ln(1 + Очки / {MODIFIER_SOFTENING}))",
        })
    return modifiers


def runtime_skill_from_catalog(skill: dict[str, Any]) -> dict[str, Any]:
    source = deepcopy(skill)
    branch = _canon_branch(source.get("branch")) or str(source.get("branch") or "")
    path = _canon_path(source.get("path")) or str(source.get("path") or "")
    is_passive = bool(source.get("is_passive")) or str(source.get("skill_type") or "").casefold().startswith("пасс")
    resource = "none" if is_passive else _resource_type(source)
    cost = 0 if is_passive else _parse_first_int(source.get("resource_cost", source.get("resource_cost_text")), 0)
    cooldown = 0 if is_passive else _parse_first_int(source.get("cooldown_turns", source.get("cooldown_turns_text")), 0)
    weapons = _weapon_requirements_for_skill(source)
    modifiers = _catalog_modifier_dicts(source)
    description = str(source.get("effect") or source.get("description") or "Навык пути.")
    skill_type = "passive" if is_passive else "active"
    return {
        "id": source.get("id"),
        "name": source.get("name"),
        "level": skill_level({"modifiers": modifiers}) if modifiers else 1,
        "skill_type": skill_type,
        "type": "Пассивный" if is_passive else "Активный",
        "category": source.get("skill_type") or ("Пассивные навыки" if is_passive else "Активные навыки"),
        "branch": branch,
        "path": path,
        "choice_group": source.get("choice_group"),
        "choice_index": _safe_int(source.get("choice_index"), 0),
        "unlock_path_level": _safe_int(source.get("unlock_path_level"), 0),
        "resource": resource,
        "resource_type": resource,
        "spirit_cost": cost if resource == "spirit" else 0,
        "mana_cost": cost if resource == "mana" else 0,
        "base_resource_cost": cost,
        "resource_text": "Расход: нет" if is_passive else str(source.get("resource_cost_text") or f"{cost} {'духа' if resource == 'spirit' else 'маны'}"),
        "cooldown_turns": cooldown,
        "cooldown_text": "Откат: нет" if is_passive else str(source.get("cooldown_turns_text") or f"{cooldown} ход."),
        "target_mode": "passive" if is_passive else "single_enemy",
        "target": "пассивно" if is_passive else "single_enemy",
        "damage_type": _damage_type(source),
        "base_damage_formula": source.get("base_formula"),
        "attribute_profile": _parse_attribute_profile(source.get("base_formula")),
        "role_coefficient": 0.0,
        "upgradeable": bool(modifiers),
        "has_modifiers": bool(modifiers),
        "modifiers": modifiers,
        "description": description,
        "effect": description,
        "bot_text": f"Вы применяете навык: «{source.get('name')}».",
        "weapon_requirements": weapons,
        "required_equipment": source.get("required_equipment"),
        "usage_requirements": source.get("usage_requirements") or [],
        "ammo_requirements": deepcopy(source.get("ammo_requirements"))
        if isinstance(source.get("ammo_requirements"), dict) and source.get("ammo_requirements")
        else _ammo_requirements(source, weapons),
        "equippable": not is_passive,
        "show_in_profile": True,
        "show_as_battle_button": not is_passive,
        "always_active": is_passive,
        "profile_slot": "Пассивные навыки" if is_passive else "Активные навыки",
        "not_unlocked_by_player_level": True,
    }


def skill_level(skill: dict[str, Any]) -> int:
    modifiers = skill.get("modifiers")
    if isinstance(modifiers, list) and modifiers:
        total = 1
        for modifier in modifiers:
            if isinstance(modifier, dict):
                total += _safe_int(modifier.get("level") if "level" in modifier else modifier.get("points"), 0)
        return max(1, total)
    return max(1, _safe_int(skill.get("level"), 1))


def find_player_skill(player: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    skills = player.get("skills") if isinstance(player.get("skills"), dict) else {}
    target = str(skill_id or "")
    for section in ("active", "equipped", "passive"):
        values = skills.get(section, []) if isinstance(skills.get(section), list) else []
        for skill in values:
            if not isinstance(skill, dict):
                continue
            if target in {str(skill.get("id") or ""), str(skill.get("name") or "")}:
                return skill
    return None


def get_player_skill_level(player: dict[str, Any], skill_id: str) -> int:
    skill = find_player_skill(player, skill_id)
    return skill_level(skill) if skill else 0


def get_modifier_level(player: dict[str, Any], skill_id: str, modifier_name: str) -> int:
    skill = find_player_skill(player, skill_id)
    if not skill:
        return 0
    target = str(modifier_name or "")
    for modifier in skill.get("modifiers", []) if isinstance(skill.get("modifiers"), list) else []:
        if not isinstance(modifier, dict):
            continue
        if target in {str(modifier.get("id") or ""), str(modifier.get("name") or ""), str(modifier.get("label") or "")}:
            return _safe_int(modifier.get("level") if "level" in modifier else modifier.get("points"), 0)
    return 0


def player_branch(player: dict[str, Any]) -> str | None:
    return _canon_branch(player.get("skill_branch") or player.get("active_skill_branch") or player.get("branch"))


def _is_legacy_concentration_skill(skill: dict[str, Any]) -> bool:
    if not isinstance(skill, dict):
        return False
    catalog_ids = {str(raw.get("id") or "") for raw in all_catalog_skills() if isinstance(raw, dict)}
    skill_id = str(skill.get("id") or "")
    if skill_id in STARTER_SKILL_IDS or skill_id in catalog_ids:
        return False
    legacy_keys = (
        "concentration_cost",
        "concentrationCost",
        "bonus_max_concentration",
        "bonus_concentration_regen",
    )
    if any(key in skill for key in legacy_keys):
        return True
    text = " ".join(str(skill.get(key) or "") for key in ("resource_text", "cost", "description", "effect", "name")).casefold()
    return "concentration" in text or "концентрац" in text


def ensure_active_skill_fields(player: dict[str, Any]) -> bool:
    changed = False
    branch = player_branch(player)
    if branch:
        if player.get("skill_branch") != branch:
            player["skill_branch"] = branch
            changed = True
        if player.get("branch") != f"Ветвь {branch}":
            player["branch"] = f"Ветвь {branch}"
            changed = True
    else:
        if player.get("skill_branch") not in {None, ""}:
            player["skill_branch"] = None
            changed = True
        if player.get("branch") not in {None, "Без ветви"}:
            player["branch"] = "Без ветви"
            changed = True
    if "has_identification_amulet" not in player:
        player["has_identification_amulet"] = True
        changed = True
    skills = player.setdefault("skills", {})
    if not isinstance(skills, dict):
        player["skills"] = skills = {"active": [], "passive": [], "equipped": []}
        changed = True
    for section in ("active", "passive", "equipped"):
        if not isinstance(skills.get(section), list):
            skills[section] = []
            changed = True
    if not isinstance(player.get("chosen_skill_groups"), list):
        player["chosen_skill_groups"] = list(player.get("chosen_skill_groups") or []) if player.get("chosen_skill_groups") else []
        changed = True
    if "unlocked_skill_sources" not in player or not isinstance(player.get("unlocked_skill_sources"), list):
        player["unlocked_skill_sources"] = []
        changed = True
    for section in ("active", "equipped", "passive"):
        values = skills.get(section) if isinstance(skills.get(section), list) else []
        filtered = [skill for skill in values if not _is_legacy_concentration_skill(skill)]
        if len(filtered) != len(values):
            skills[section] = filtered
            changed = True
    return changed


def normalize_starter_only_skills(player: dict[str, Any]) -> bool:
    """Compatibility name: now keeps the full integrated skill system."""
    return ensure_active_skill_fields(player)


def has_identification_amulet(player: dict[str, Any]) -> bool:
    if player.get("has_identification_amulet") is True:
        return True
    return bool(player.get("starter_pack_applied") or player.get("created_at"))


def player_has_skill(player: dict[str, Any], skill_id: str) -> bool:
    return find_player_skill(player, skill_id) is not None


def add_skill_to_player(player: dict[str, Any], skill: dict[str, Any]) -> bool:
    ensure_active_skill_fields(player)
    skill_id = str(skill.get("id") or "")
    if not skill_id or player_has_skill(player, skill_id):
        return False
    runtime = runtime_skill_from_catalog(skill) if "unlock_path_level" in skill and "attribute_profile" not in skill else deepcopy(skill)
    target = "passive" if str(runtime.get("skill_type") or "").casefold() in {"passive", "пассивный"} or runtime.get("always_active") else "active"
    player["skills"].setdefault(target, []).append(runtime)
    return True


def branch_starter_skills(branch: str) -> list[dict[str, Any]]:
    branch = _canon_branch(branch) or str(branch)
    return [deepcopy(skill) for skill in all_catalog_skills() if _canon_branch(skill.get("branch")) == branch and _safe_int(skill.get("unlock_path_level"), 0) == 0]


def starter_skill_for_path(branch: str, path: str) -> dict[str, Any] | None:
    branch = _canon_branch(branch)
    path = _canon_path(path)
    for skill in all_catalog_skills():
        if _canon_branch(skill.get("branch")) == branch and _canon_path(skill.get("path")) == path and _safe_int(skill.get("unlock_path_level"), 0) == 0:
            return deepcopy(skill)
    return None


def selected_main_path(player: dict[str, Any]) -> str | None:
    return _canon_path(player.get("main_skill_path") or player.get("active_skill_main_path"))


def selected_secondary_path(player: dict[str, Any]) -> str | None:
    return _canon_path(player.get("secondary_skill_path") or player.get("active_skill_secondary_path"))


def selected_paths(player: dict[str, Any]) -> list[tuple[str, str]]:
    paths = []
    main = selected_main_path(player)
    secondary = selected_secondary_path(player)
    if main:
        paths.append(("main", main))
    if secondary:
        paths.append(("secondary", secondary))
    return paths


def path_level(player: dict[str, Any], path: str) -> int:
    target = _canon_path(path)
    if not target:
        return 0
    total = 0
    skills = player.get("skills") if isinstance(player.get("skills"), dict) else {}
    seen: set[str] = set()
    for section in ("active", "equipped", "passive"):
        for skill in skills.get(section, []) if isinstance(skills.get(section), list) else []:
            if not isinstance(skill, dict):
                continue
            key = str(skill.get("id") or skill.get("name") or id(skill))
            if key in seen:
                continue
            if _canon_path(skill.get("path")) == target:
                total += skill_level(skill)
                seen.add(key)
    return total


def main_path_level(player: dict[str, Any]) -> int:
    main = selected_main_path(player)
    return path_level(player, main) if main else 0


def secondary_path_limit(player: dict[str, Any]) -> int:
    return math.floor(main_path_level(player) * SECONDARY_PATH_RATIO)


def is_secondary_skill(player: dict[str, Any], skill: dict[str, Any]) -> bool:
    secondary = selected_secondary_path(player)
    return bool(secondary and _canon_path(skill.get("path")) == secondary)


def can_spend_skill_points_on(player: dict[str, Any], skill: dict[str, Any], amount: int) -> tuple[bool, str]:
    if not is_secondary_skill(player, skill):
        return True, ""
    projected = path_level(player, str(skill.get("path") or "")) + max(0, amount)
    limit = secondary_path_limit(player)
    if projected > limit:
        return False, f"Уровень дополнительного пути не может превышать 60% основного пути. Лимит сейчас: {limit}."
    return True, ""


def choose_active_skill_branch(player: dict[str, Any], branch: str) -> dict[str, Any]:
    ensure_active_skill_fields(player)
    branch = _canon_branch(branch)
    if not branch:
        raise ValueError("unknown active skill branch")
    if _safe_int(player.get("level"), 1) < 10:
        raise ValueError("branch choice is available from level 10")
    current = player_branch(player)
    if current and current != branch:
        raise ValueError("active skill branch is already chosen")
    player["skill_branch"] = branch
    player["active_skill_branch"] = branch
    player["branch"] = f"Ветвь {branch}"
    player["branch_choice_hint_sent"] = True
    return player


def choose_main_path(player: dict[str, Any], path: str) -> dict[str, Any]:
    ensure_active_skill_fields(player)
    branch = player_branch(player)
    path = _canon_path(path)
    if not branch or not path or path not in PATHS_BY_BRANCH.get(branch, []):
        raise ValueError("path is not available for selected branch")
    if selected_main_path(player):
        raise ValueError("main path is already chosen")
    player["main_skill_path"] = path
    player["active_skill_main_path"] = path
    starter = starter_skill_for_path(branch, path)
    if starter:
        add_skill_to_player(player, starter)
    return player


def choose_secondary_path(player: dict[str, Any], path: str) -> dict[str, Any]:
    ensure_active_skill_fields(player)
    branch = player_branch(player)
    path = _canon_path(path)
    if _safe_int(player.get("level"), 1) < 100:
        raise ValueError("secondary path is available from level 100")
    if not branch or not path or path not in PATHS_BY_BRANCH.get(branch, []):
        raise ValueError("path is not available for selected branch")
    if path == selected_main_path(player):
        raise ValueError("secondary path cannot duplicate main path")
    if selected_secondary_path(player):
        raise ValueError("secondary path is already chosen")
    player["secondary_skill_path"] = path
    player["active_skill_secondary_path"] = path
    starter = starter_skill_for_path(branch, path)
    if starter:
        add_skill_to_player(player, starter)
    return player


def chosen_groups(player: dict[str, Any]) -> set[str]:
    raw = player.get("chosen_skill_groups")
    return {str(item) for item in raw if item} if isinstance(raw, list) else set()


def choice_groups_by_threshold(player: dict[str, Any]) -> list[dict[str, Any]]:
    ensure_active_skill_fields(player)
    branch = player_branch(player)
    if not branch:
        return []
    groups = chosen_groups(player)
    available: list[dict[str, Any]] = []
    for role, path in selected_paths(player):
        current_level = path_level(player, path)
        if role == "secondary":
            current_level = min(current_level, secondary_path_limit(player))
        for threshold in THRESHOLDS:
            if threshold > current_level:
                continue
            group = f"{path}_{threshold}"
            if group in groups:
                continue
            options = [skill for skill in skills_for_group(group) if _canon_branch(skill.get("branch")) == branch and _canon_path(skill.get("path")) == path]
            if options:
                available.append({"role": role, "path": path, "threshold": threshold, "choice_group": group, "options": options})
    return sorted(available, key=lambda item: (0 if item["role"] == "main" else 1, int(item["threshold"]), str(item["path"])))


def current_available_choice(player: dict[str, Any]) -> dict[str, Any] | None:
    choices = choice_groups_by_threshold(player)
    if not choices:
        player.pop("pending_skill_choice", None)
        player.pop("pending_skill_preview_id", None)
        return None
    choice = choices[0]
    player["pending_skill_choice"] = {
        "choice_group": choice["choice_group"],
        "path": choice["path"],
        "threshold": choice["threshold"],
        "options": [str(skill.get("id")) for skill in choice["options"]],
    }
    return choice


def preview_skill_choice(player: dict[str, Any], choice_index: int | str) -> dict[str, Any] | None:
    choice = current_available_choice(player)
    if not choice:
        return None
    try:
        index = int(choice_index) - 1
    except (TypeError, ValueError):
        return None
    options = choice["options"]
    if index < 0 or index >= len(options):
        return None
    skill = options[index]
    player["pending_skill_preview_id"] = str(skill.get("id") or "")
    return deepcopy(skill)


def confirm_pending_skill_choice(player: dict[str, Any]) -> dict[str, Any] | None:
    ensure_active_skill_fields(player)
    preview_id = str(player.get("pending_skill_preview_id") or "")
    choice = current_available_choice(player)
    if not preview_id or not choice:
        return None
    options = {str(skill.get("id") or ""): skill for skill in choice["options"]}
    selected = options.get(preview_id)
    if not selected:
        return None
    add_skill_to_player(player, selected)
    groups = player.setdefault("chosen_skill_groups", [])
    group = str(choice["choice_group"])
    if group not in groups:
        groups.append(group)
    player.pop("pending_skill_choice", None)
    player.pop("pending_skill_preview_id", None)
    return runtime_skill_from_catalog(selected)


def next_threshold_for_path(player: dict[str, Any], path: str) -> int | None:
    level = path_level(player, path)
    for threshold in THRESHOLDS:
        if threshold > level:
            return threshold
    return None


def can_choose_active_skill_branch_here(player: dict[str, Any]) -> bool:
    return _safe_int(player.get("level"), 1) >= 10 and player_branch(player) is None


def refresh_unlocked_active_skills(player: dict[str, Any]) -> int:
    ensure_active_skill_fields(player)
    # Choices are intentionally granted only by explicit Order Stone selection.
    return 0


def branch_hint_text() -> str:
    messages = load_branch_choice_messages()
    text = ((messages.get("level_10_notification") or {}).get("text") if isinstance(messages.get("level_10_notification"), dict) else None)
    return str(text or "Вы достигли порога развития. Зайдите в ратушу Селдара к Распорядительному камню.")


def maybe_mark_branch_hint(player: dict[str, Any]) -> str | None:
    ensure_active_skill_fields(player)
    level = _safe_int(player.get("level"), 1)
    if level >= 10 and not player_branch(player) and not player.get("branch_choice_hint_sent"):
        player["branch_choice_hint_sent"] = True
        return branch_hint_text()
    if level >= 100 and player_branch(player) and selected_main_path(player) and not selected_secondary_path(player) and not player.get("secondary_path_hint_sent"):
        player["secondary_path_hint_sent"] = True
        messages = load_branch_choice_messages()
        return str(((messages.get("level_100_notification") or {}).get("text")) or "Вы достигли нового порога развития. Распорядительный камень может открыть дополнительный путь.")
    if choice_groups_by_threshold(player) and not player.get("path_threshold_hint_sent"):
        player["path_threshold_hint_sent"] = True
        messages = load_branch_choice_messages()
        return str(((messages.get("path_threshold_notification") or {}).get("text")) or "Распорядительный камень в ратуше может открыть новый навык.")
    return None


WEAPON_SLOT_ORDER = ("weapon1", "weapon2", "shield")


def weapon_token_for_item(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    explicit = str(item.get("weapon_type") or item.get("weaponToken") or item.get("weapon_token") or "").strip().casefold()
    if explicit in {"sword", "dagger", "staff", "axe", "hammer", "bow", "shield", "crossbow", "magic_book"}:
        return explicit
    text = " ".join(str(item.get(key) or "") for key in ("type", "subtype", "name", "slot", "slotKey", "targetSlotKey", "category")).casefold()
    if "арбал" in text or "crossbow" in text:
        return "crossbow"
    if "лук" in text or "bow" in text:
        return "bow"
    if "посох" in text or "staff" in text:
        return "staff"
    if "магическ" in text and "книг" in text or "magic_book" in text:
        return "magic_book"
    if "кинжал" in text or "dagger" in text:
        return "dagger"
    if "топор" in text or "axe" in text:
        return "axe"
    if "молот" in text or "hammer" in text or "булав" in text or "mace" in text:
        return "hammer"
    if "щит" in text or "shield" in text:
        return "shield"
    if "меч" in text or "sword" in text:
        return "sword"
    return None


def current_weapon_tokens(player: dict[str, Any]) -> set[str]:
    tokens = {"any"}
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    for slot in WEAPON_SLOT_ORDER:
        token = weapon_token_for_item(equipment.get(slot))
        if token:
            tokens.add(token)
    return tokens


def equipped_weapon_token_for_skill(player: dict[str, Any], skill: dict[str, Any]) -> str | None:
    allowed_raw = skill.get("weapon_requirements") or ["any"]
    if isinstance(allowed_raw, str):
        allowed_raw = [allowed_raw]
    allowed = {str(item) for item in allowed_raw if item}
    if not allowed or "any" in allowed:
        return None
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    for slot in WEAPON_SLOT_ORDER:
        token = weapon_token_for_item(equipment.get(slot))
        if token and token in allowed:
            return token
    return None


def current_equipment_tokens(player: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    for item in equipment.values():
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get(key) or "") for key in ("type", "subtype", "name", "slot", "slotKey", "category")).casefold()
        if "тяж" in text or "heavy" in text:
            tokens.add("heavy_armor")
        if "сред" in text or "medium" in text:
            tokens.add("medium_armor")
        if "лёг" in text or "легк" in text or "light" in text:
            tokens.add("light_armor")
        if "ткан" in text or "robe" in text or "cloth" in text:
            tokens.add("cloth_armor")
        if "щит" in text or "shield" in text:
            tokens.add("shield")
    return tokens


def invested_attribute_value(player: dict[str, Any], attribute: str) -> int:
    key = RUS_TO_BACK_ATTRIBUTE.get(str(attribute or ""), str(attribute or ""))
    invested = player.get("invested_stats") if isinstance(player.get("invested_stats"), dict) else {}
    return _safe_int(invested.get(key), 0)


def check_skill_requirement(player: dict[str, Any], requirement: dict[str, Any]) -> bool:
    if not isinstance(requirement, dict):
        return False
    kind = requirement.get("kind")
    branch = player_branch(player)
    if kind in {"player_registered", "starter_action"}:
        return True
    if kind == "branch_choice":
        return branch == requirement.get("branch")
    if kind == "branch_choice_required":
        return branch in set(requirement.get("allowed_branches") or [])
    if kind == "required_skill_level":
        return get_player_skill_level(player, str(requirement.get("skill_id") or "")) >= _safe_int(requirement.get("skill_level"), 0)
    if kind == "any_required_skill_level":
        return any(get_player_skill_level(player, str(option.get("skill_id") or "")) >= _safe_int(option.get("skill_level"), 0) for option in requirement.get("options", []) if isinstance(option, dict))
    if kind == "required_modifier_level":
        return get_modifier_level(player, str(requirement.get("skill_id") or ""), str(requirement.get("modifier_name") or "")) >= _safe_int(requirement.get("modifier_level"), 0)
    if kind == "invested_attribute":
        return invested_attribute_value(player, str(requirement.get("attribute") or "")) >= _safe_int(requirement.get("threshold"), 0)
    if kind == "weapon_type":
        allowed_raw = requirement.get("allowed") or []
        if isinstance(allowed_raw, str):
            allowed_raw = [allowed_raw]
        allowed = {str(item) for item in allowed_raw}
        if not allowed:
            return True
        tokens = current_weapon_tokens(player)
        return bool(tokens & allowed) or "any" in allowed
    if kind == "equipment_type":
        allowed_raw = requirement.get("allowed") or []
        if isinstance(allowed_raw, str):
            allowed_raw = [allowed_raw]
        allowed = {str(item) for item in allowed_raw}
        return bool(current_equipment_tokens(player) & allowed)
    if kind == "weapon_or_equipment_type":
        allowed_weapons = requirement.get("allowed_weapons") or []
        allowed_equipment = requirement.get("allowed_equipment") or []
        if isinstance(allowed_weapons, str):
            allowed_weapons = [allowed_weapons]
        if isinstance(allowed_equipment, str):
            allowed_equipment = [allowed_equipment]
        return bool((current_weapon_tokens(player) & {str(item) for item in allowed_weapons}) or (current_equipment_tokens(player) & {str(item) for item in allowed_equipment}))
    if kind == "learning_source":
        sources = set(player.get("unlocked_skill_sources") or [])
        return str(requirement.get("source") or "") in sources or "ANY" in sources
    return False


def can_unlock_catalog_skill(player: dict[str, Any], skill: dict[str, Any]) -> bool:
    branch = player_branch(player)
    path = _canon_path(skill.get("path"))
    if not branch or _canon_branch(skill.get("branch")) != branch or path not in {selected_main_path(player), selected_secondary_path(player)}:
        return False
    threshold = _safe_int(skill.get("unlock_path_level"), 0)
    return threshold <= path_level(player, path or "")


def is_skill_weapon_compatible(player: dict[str, Any], skill: dict[str, Any]) -> bool:
    if str(skill.get("skill_type") or "").casefold() in {"passive", "пассивный"}:
        return True
    allowed_raw = skill.get("weapon_requirements") or ["any"]
    if isinstance(allowed_raw, str):
        allowed_raw = [allowed_raw]
    allowed = {str(item) for item in allowed_raw}
    if not allowed or "any" in allowed:
        return True
    return bool(current_weapon_tokens(player) & allowed)


def skill_weapon_requirement_text(skill: dict[str, Any]) -> str:
    allowed_raw = skill.get("weapon_requirements") or ["any"]
    if isinstance(allowed_raw, str):
        allowed_raw = [allowed_raw]
    labels = {
        "any": "любое оружие",
        "sword": "меч",
        "dagger": "кинжал",
        "staff": "посох",
        "magic_book": "магическая книга",
        "axe": "топор",
        "hammer": "молот",
        "bow": "лук",
        "shield": "щит",
        "crossbow": "арбалет",
    }
    return ", ".join(labels.get(str(item), str(item)) for item in allowed_raw)


def _ammo_requirements_for_weapon(skill: dict[str, Any], weapon_token: str | None) -> dict[str, Any] | None:
    ammo = skill.get("ammo_requirements") if isinstance(skill.get("ammo_requirements"), dict) else {}
    if not ammo or ammo.get("enabled") is False or not weapon_token:
        return None
    by_weapon = ammo.get("requirements_by_weapon") if isinstance(ammo.get("requirements_by_weapon"), dict) else {}
    requirement = by_weapon.get(weapon_token)
    return requirement if isinstance(requirement, dict) else None


def skill_ammo_requirement_for_current_weapon(player: dict[str, Any], skill: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    weapon_token = equipped_weapon_token_for_skill(player, skill)
    return weapon_token, _ammo_requirements_for_weapon(skill, weapon_token)


def _quiver_kind(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    item_id = str(item.get("id") or item.get("item_id") or "")
    raw = " ".join(str(item.get(key) or "") for key in ("quiver_type", "subtype", "type", "slot", "slotKey", "targetSlotKey", "name")).casefold()
    if item_id == "arrow_quiver_empty" or "arrow_quiver" in raw or "стрел" in raw:
        return "arrow_quiver"
    if item_id == "bolt_quiver_empty" or "bolt_quiver" in raw or "болт" in raw:
        return "bolt_quiver"
    return "quiver" if "quiver" in raw or "колчан" in raw else ""


def _equipped_quiver(player: dict[str, Any], slot: str) -> dict[str, Any] | None:
    equipment = player.get("equipment") if isinstance(player.get("equipment"), dict) else {}
    weapon2 = equipment.get("weapon2")
    if isinstance(weapon2, dict) and _quiver_kind(weapon2) == slot:
        return weapon2
    item = equipment.get(slot)
    if isinstance(item, dict):
        return item
    equipped_quivers = player.get("equipped_quivers") if isinstance(player.get("equipped_quivers"), dict) else {}
    item = equipped_quivers.get(slot)
    return item if isinstance(item, dict) else None


def validate_skill_ammo(player: dict[str, Any], skill: dict[str, Any]) -> tuple[bool, str]:
    _weapon, requirement = skill_ammo_requirement_for_current_weapon(player, skill)
    if not requirement:
        return True, ""
    quiver_requirement = requirement.get("quiver_requirement") if isinstance(requirement.get("quiver_requirement"), dict) else {}
    quiver_slot = str(quiver_requirement.get("quiver_slot") or requirement.get("quiver_slot") or "")
    quiver = _equipped_quiver(player, quiver_slot)
    if not isinstance(quiver, dict):
        return False, str(requirement.get("missing_quiver_message") or quiver_requirement.get("missing_quiver_message") or "Нужен подходящий колчан.")
    required_ammo_id = str(requirement.get("ammo_item_id") or "")
    if required_ammo_id and str(quiver.get("ammo_item_id") or required_ammo_id) != required_ammo_id:
        return False, str(requirement.get("missing_loaded_ammo_message") or "В колчане нет нужных боеприпасов.")
    need = max(1, _safe_int(requirement.get("consume_per_use"), 1))
    if _safe_int(quiver.get("ammo_count"), 0) < need:
        return False, str(requirement.get("missing_loaded_ammo_message") or requirement.get("missing_message") or "В колчане нет нужного количества боеприпасов.")
    return True, ""


def consume_skill_ammo(player: dict[str, Any], skill: dict[str, Any]) -> tuple[bool, str]:
    _weapon, requirement = skill_ammo_requirement_for_current_weapon(player, skill)
    if not requirement:
        return True, ""
    ok, message = validate_skill_ammo(player, skill)
    if not ok:
        return False, message
    quiver_requirement = requirement.get("quiver_requirement") if isinstance(requirement.get("quiver_requirement"), dict) else {}
    quiver_slot = str(quiver_requirement.get("quiver_slot") or requirement.get("quiver_slot") or "")
    quiver = _equipped_quiver(player, quiver_slot)
    need = max(1, _safe_int(requirement.get("consume_per_use"), 1))
    quiver["ammo_count"] = max(0, _safe_int(quiver.get("ammo_count"), 0) - need)
    ammo_name = str(requirement.get("ammo_short_name") or requirement.get("ammo_name") or "боеприпас")
    return True, f"Из колчана израсходовано: {ammo_name} ×{need}."


def skill_profile_power(stats: dict[str, Any], profile: dict[str, Any]) -> float:
    total = 0.0
    for raw_key, weight in profile.items():
        key = PROFILE_ATTRIBUTE_KEYS.get(str(raw_key), str(raw_key))
        try:
            total += float(stats.get(key) or 0) * float(weight)
        except (TypeError, ValueError):
            continue
    return total


def modifier_bonus_percent(points: int) -> float:
    points = max(0, _safe_int(points, 0))
    if points <= 0:
        return 0.0
    return 30.0 * math.log(1 + points / MODIFIER_SOFTENING)


def skill_modifier_bonus_percent(skill: dict[str, Any], keywords: tuple[str, ...] = ()) -> float:
    total = 0.0
    for modifier in skill.get("modifiers", []) if isinstance(skill.get("modifiers"), list) else []:
        if not isinstance(modifier, dict):
            continue
        text = f"{modifier.get('name') or ''} {modifier.get('label') or ''} {modifier.get('type') or ''} {modifier.get('effect') or ''}".casefold()
        if keywords and not any(keyword in text for keyword in keywords):
            continue
        total += modifier_bonus_percent(_safe_int(modifier.get("level") if "level" in modifier else modifier.get("points"), 0))
    return total


def skill_modifier_multiplier(skill: dict[str, Any]) -> float:
    bonus = skill_modifier_bonus_percent(skill, ("сила", "урон", "эффект", "исцел", "основн"))
    return max(0.1, 1.0 + bonus / 100.0)


def _passive_active_for_skill(player: dict[str, Any], passive: dict[str, Any], active_skill: dict[str, Any] | None = None) -> bool:
    if not isinstance(passive, dict):
        return False
    if str(passive.get("skill_type") or "").casefold() not in {"passive", "пассивный"} and not passive.get("always_active"):
        return False
    path = _canon_path(passive.get("path"))
    if active_skill is not None and path and _canon_path(active_skill.get("path")) != path:
        return False
    return is_skill_weapon_compatible(player, passive)


def player_passive_bonus_percent(player: dict[str, Any], active_skill: dict[str, Any] | None, keywords: tuple[str, ...]) -> float:
    skills = player.get("skills") if isinstance(player.get("skills"), dict) else {}
    total = 0.0
    for passive in skills.get("passive", []) if isinstance(skills.get("passive"), list) else []:
        if not _passive_active_for_skill(player, passive, active_skill):
            continue
        text = f"{passive.get('name') or ''} {passive.get('effect') or ''} {passive.get('description') or ''}".casefold()
        if any(keyword in text for keyword in keywords):
            total += skill_modifier_bonus_percent(passive)
        else:
            total += skill_modifier_bonus_percent(passive, keywords)
    return total


def passive_skill_multiplier(player: dict[str, Any], skill: dict[str, Any], kind: str = "damage") -> float:
    keywords = {
        "damage": ("урон", "эффектив", "сила", "усиливает"),
        "accuracy": ("точност",),
        "resource": ("эконом", "расход", "ресурс"),
    }.get(kind, (kind,))
    bonus = player_passive_bonus_percent(player, skill, keywords)
    return max(0.1, 1.0 + bonus / 100.0)


def passive_stat_modifiers(player: dict[str, Any]) -> dict[str, int]:
    skills = player.get("skills") if isinstance(player.get("skills"), dict) else {}
    totals = {
        "bonus_accuracy": 0,
        "bonus_dodge": 0,
        "bonus_physical_defense": 0,
        "bonus_magic_defense": 0,
        "bonus_crit_chance": 0,
        "bonus_damage": 0,
        "bonus_spirit": 0,
        "bonus_mana": 0,
        "bonus_hp": 0,
    }
    for passive in skills.get("passive", []) if isinstance(skills.get("passive"), list) else []:
        if not _passive_active_for_skill(player, passive, None):
            continue
        text = f"{passive.get('name') or ''} {passive.get('effect') or ''} {passive.get('description') or ''} {' '.join(str(m.get('name') or '') for m in passive.get('modifiers', []) if isinstance(m, dict))}".casefold()
        bonus = math.ceil(skill_modifier_bonus_percent(passive))
        if bonus <= 0:
            continue
        if "точност" in text:
            totals["bonus_accuracy"] += bonus
        if "уклон" in text:
            totals["bonus_dodge"] += bonus
        if "физическ" in text or "защит" in text or "блок" in text:
            totals["bonus_physical_defense"] += bonus
        if "магическ" in text or "мана" in text:
            totals["bonus_magic_defense"] += bonus // 2
        if "крит" in text:
            totals["bonus_crit_chance"] += max(1, bonus // 2)
        if "урон" in text or "эффектив" in text or "сила" in text:
            totals["bonus_damage"] += bonus
        if "дух" in text or "ресурс" in text:
            totals["bonus_spirit"] += bonus
        if "мана" in text or "ресурс" in text:
            totals["bonus_mana"] += bonus
        if "жив" in text or "здоров" in text or "hp" in text:
            totals["bonus_hp"] += bonus
    return {key: value for key, value in totals.items() if value}


def resource_cost_with_modifiers(skill: dict[str, Any], player: dict[str, Any] | None = None) -> tuple[int, int]:
    base_cost = _safe_int(skill.get("base_resource_cost") or skill.get("spirit_cost") or skill.get("mana_cost"), 0)
    reduction = skill_modifier_bonus_percent(skill, ("ресурс", "расход", "эконом")) / 100.0
    if player is not None:
        reduction += max(0.0, passive_skill_multiplier(player, skill, "resource") - 1.0)
    cost = max(0, math.ceil(base_cost * max(0.2, 1 - reduction)))
    resource = str(skill.get("resource") or "")
    if resource == "spirit" or _safe_int(skill.get("spirit_cost"), 0) > 0:
        return cost, 0
    if resource == "mana" or _safe_int(skill.get("mana_cost"), 0) > 0:
        return 0, cost
    return 0, 0
