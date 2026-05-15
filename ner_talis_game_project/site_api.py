"""Profile API for the React website.

The React profile from ``web/`` talks to these endpoints. The module uses the
same storage factory as Telegram/VK, so it works with PostgreSQL, SQLite and
JSON without a separate data file.
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.web_profile import PROFILE_SCOPE

FRONT_TO_BACK_STAT = {
    "strength": "strength",
    "endurance": "endurance",
    "agility": "dexterity",
    "dexterity": "dexterity",
    "perception": "perception",
    "intelligence": "intelligence",
    "wisdom": "wisdom",
}

ATTRIBUTE_META = [
    ("strength", "strength", "Сила", "Физический урон, пробой, блоки, силовые стойки."),
    ("endurance", "endurance", "Выносливость", "HP, физическая защита, дух, устойчивость."),
    ("agility", "dexterity", "Ловкость", "Уклонение, парирование, быстрые атаки."),
    ("perception", "perception", "Восприятие", "Точность, крит, обнаружение угроз."),
    ("intelligence", "intelligence", "Интеллект", "Магические навыки, мана, сложные формы."),
    ("wisdom", "wisdom", "Мудрость", "Концентрация, поддержка, лечение, регенерация маны."),
]

EQUIPMENT_SLOTS = [
    {"key": "helmet", "label": "Шлем", "icon": "⛑", "positionClass": "slot-helmet"},
    {"key": "necklace", "label": "Ожерелье", "icon": "◆", "positionClass": "slot-necklace"},
    {"key": "chest", "label": "Нагрудник", "icon": "▣", "positionClass": "slot-chest"},
    {"key": "belt", "label": "Пояс", "icon": "▰", "positionClass": "slot-belt"},
    {"key": "pants", "label": "Штаны", "icon": "▥", "positionClass": "slot-pants"},
    {"key": "boots", "label": "Ботинки", "icon": "▱", "positionClass": "slot-boots"},
    {"key": "gloves", "label": "Перчатки", "icon": "✋", "positionClass": "slot-gloves"},
    {"key": "ring1", "label": "Кольцо 1", "icon": "○", "positionClass": "slot-ring1"},
    {"key": "ring2", "label": "Кольцо 2", "icon": "○", "positionClass": "slot-ring2"},
    {"key": "weapon1", "label": "Оружие 1", "icon": "⚔", "positionClass": "slot-weapon1"},
    {"key": "weapon2", "label": "Оружие 2", "icon": "🛡", "positionClass": "slot-weapon2"},
    {"key": "special", "label": "Особый слот", "icon": "✦", "positionClass": "slot-special"},
]

CRAFT_LABELS = {
    "smelting": "Плавильное дело",
    "blacksmithing": "Кузнечное дело",
    "leatherworking": "Кожевничество",
    "jewelcrafting": "Ювелирное дело",
    "alchemy": "Алхимия",
    "enchanting": "Зачарование",
}

RACE_MODEL_KEYS = {
    "human": "human",
    "elf": "elf",
    "dwarf": "dwarf",
    "undead": "undead",
    "lizardfolk": "lizardfolk",
}


class SpendAttributeRequest(BaseModel):
    attribute_key: str
    amount: int = Field(gt=0)


class SpendSkillRequest(BaseModel):
    skill_id: str
    modifier_id: str | None = None
    amount: int = Field(gt=0)


class EquipItemRequest(BaseModel):
    item_id: str


class UnequipItemRequest(BaseModel):
    slot_key: str


class UseItemRequest(BaseModel):
    item_id: str


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def ceil(value: float) -> int:
    return int(math.ceil(value))


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def effective_stat(player: dict[str, Any], stat_key: str, equipment_modifiers: dict[str, int] | None = None) -> int:
    base = safe_int((player.get("stats") or {}).get(stat_key), 0)
    invested = safe_int((player.get("invested_stats") or {}).get(stat_key), 0)
    bonus = safe_int((player.get("stat_bonuses") or {}).get(stat_key), 0)
    if equipment_modifiers:
        bonus += equipment_stat_bonus(equipment_modifiers, stat_key)
    invested_total = base + invested
    return int(math.floor(1000 * math.log(1 + invested_total / 1000) + bonus))


def equipment_stat_bonus(equipment_modifiers: dict[str, int], stat_key: str) -> int:
    bonus_key = STAT_EQUIPMENT_BONUS_KEYS.get(stat_key, f"bonus_{stat_key}")
    fallback_key = f"bonus_{stat_key}"
    total = safe_int(equipment_modifiers.get(bonus_key), 0)
    if fallback_key != bonus_key:
        total += safe_int(equipment_modifiers.get(fallback_key), 0)
    return total


def parse_item_stat_modifier(line: Any) -> tuple[str, int] | None:
    if not isinstance(line, str):
        return None
    text = line.strip()
    if not text or contains_formula_text(text):
        return None
    if ":" in text:
        label, value = text.split(":", 1)
    elif " к " in text:
        value, label = text.split(" к ", 1)
    else:
        return None
    label_key = label.strip().casefold()
    modifier_key = ITEM_STAT_LABEL_TO_MODIFIER.get(label_key)
    if not modifier_key:
        return None
    match = re.search(r"([+-]?)\s*(\d+)", value)
    if not match:
        return None
    sign = -1 if match.group(1) == "-" else 1
    return modifier_key, sign * safe_int(match.group(2), 0)


def equipment_modifier_totals(player: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    equipment = player.get("equipment") or {}
    if not isinstance(equipment, dict):
        return totals
    for raw_item in equipment.values():
        if not isinstance(raw_item, dict):
            continue
        stat_modifiers = raw_item.get("stat_modifiers")
        if isinstance(stat_modifiers, dict):
            for key, value in stat_modifiers.items():
                totals[str(key)] = safe_int(totals.get(str(key)), 0) + safe_int(value, 0)
        for field in ("stats", "properties", "enchantments"):
            lines = raw_item.get(field)
            if not isinstance(lines, list):
                continue
            for line in lines:
                parsed = parse_item_stat_modifier(line)
                if parsed is None:
                    continue
                key, amount = parsed
                totals[key] = safe_int(totals.get(key), 0) + amount
    return totals


def equipment_bonus(equipment_modifiers: dict[str, int], key: str) -> int:
    return safe_int(equipment_modifiers.get(key), 0)


def soft_level(level: int) -> int:
    return int(math.floor(10 * math.log2(max(1, level) + 1)))


def format_money(copper: int) -> str:
    copper = max(0, int(copper or 0))
    values = [(500_000_000_000, "древн."), (1_000_000_000, "маг. зол."), (1_000_000, "зол."), (1_000, "сер.")]
    parts: list[str] = []
    for cost, label in values:
        amount, copper = divmod(copper, cost)
        if amount:
            parts.append(f"{amount} {label}")
    if copper or not parts:
        parts.append(f"{copper} мед.")
    return " ".join(parts)


def format_date(raw_value: str | None) -> str:
    if not raw_value:
        return "—"
    try:
        value = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        return value.strftime("%d.%m.%Y")
    except ValueError:
        return str(raw_value)


def normalize_quality(value: str | None) -> str:
    return (value or "обычный").strip().lower()


HIDDEN_FORMULA_KEYS = {"formula", "base_damage_formula", "damage_formula", "scaling_formula"}
FORMULA_TEXT_MARKERS = ("player_level", "ceil(", "floor(", "уровень ×", "уровня ×", "уровень персонажа ×")
STAT_EQUIPMENT_BONUS_KEYS = {
    "strength": "bonus_strength",
    "endurance": "bonus_endurance",
    "dexterity": "bonus_agility",
    "perception": "bonus_perception",
    "intelligence": "bonus_intelligence",
    "wisdom": "bonus_wisdom",
}
ITEM_STAT_LABEL_TO_MODIFIER = {
    "броня": "armor",
    "магическая броня": "magic_armor",
    "маг. броня": "magic_armor",
    "магическая защита": "bonus_magic_defense",
    "физическая защита": "bonus_physical_defense",
    "hp": "bonus_hp",
    "здоровье": "bonus_hp",
    "дух": "bonus_spirit",
    "мана": "bonus_mana",
    "точность": "bonus_accuracy",
    "уклонение": "bonus_dodge",
    "шанс крита": "bonus_crit_chance",
    "урон крита": "bonus_crit_damage",
    "сила": "bonus_strength",
    "выносливость": "bonus_endurance",
    "ловкость": "bonus_agility",
    "восприятие": "bonus_perception",
    "интеллект": "bonus_intelligence",
    "мудрость": "bonus_wisdom",
}


def contains_formula_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return any(marker in lowered for marker in FORMULA_TEXT_MARKERS)


def strip_hidden_formulas(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, nested_value in value.items():
            key_text = str(key).casefold()
            if key_text in HIDDEN_FORMULA_KEYS or "formula" in key_text:
                continue
            cleaned_value = strip_hidden_formulas(nested_value)
            if cleaned_value is None:
                continue
            cleaned[key] = cleaned_value
        return cleaned
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := strip_hidden_formulas(item)) is not None]
    if contains_formula_text(value):
        return None
    return value


def normalize_item(item: dict[str, Any], default_category: str = "Прочее") -> dict[str, Any]:
    normalized = strip_hidden_formulas(deepcopy(item))
    if not isinstance(normalized, dict):
        normalized = {}
    normalized.setdefault("id", normalized.get("item_id") or normalized.get("name") or "item")
    normalized.setdefault("name", "Безымянный предмет")
    normalized.setdefault("category", default_category)
    normalized.setdefault("type", normalized.get("slotKey") or normalized.get("slot") or "Предмет")
    normalized["quality"] = normalize_quality(normalized.get("quality"))
    normalized.setdefault("level", 1)
    normalized.setdefault("description", "Описание предмета пока не добавлено.")
    normalized.setdefault("stats", [])
    normalized.setdefault("enchantments", [])
    normalized.setdefault("compare", [])
    normalized.setdefault("amount", 1)
    return normalized


def format_skill_damage(skill: dict[str, Any], player_level: int) -> Any:
    if not isinstance(skill, dict):
        return None
    formula = str(skill.get("base_damage_formula") or "")
    if skill.get("id") == "basic_attack" or "5 + player_level * 1.2" in formula:
        return ceil(5 + player_level * 1.2)
    if skill.get("id") == "magic_spark" or "4 + player_level * 1.1" in formula:
        return ceil(4 + player_level * 1.1)
    damage = skill.get("damage")
    if contains_formula_text(damage):
        return None
    return damage


def normalize_skill(skill: dict[str, Any], player_level: int) -> dict[str, Any]:
    normalized = strip_hidden_formulas(deepcopy(skill))
    if not isinstance(normalized, dict):
        normalized = {}
    damage = format_skill_damage(skill, player_level)
    if damage is not None:
        normalized["damage"] = damage
    else:
        normalized.pop("damage", None)
    return normalized


def frontend_profile(player: dict[str, Any]) -> dict[str, Any]:
    level = safe_int(player.get("level"), 1) or 1
    s_level = soft_level(level)
    equipment_modifiers = equipment_modifier_totals(player)
    eff = {front_key: effective_stat(player, back_key, equipment_modifiers) for front_key, back_key, *_ in ATTRIBUTE_META}
    armor = safe_int(player.get("armor"), 0) + equipment_bonus(equipment_modifiers, "armor")
    magic_armor = safe_int(player.get("magic_armor"), safe_int(player.get("armor"), 0)) + equipment_bonus(equipment_modifiers, "magic_armor")

    hp_max = ceil(100 + eff["endurance"] * 4.0 + eff["strength"] * 0.8 + s_level * 4 + safe_int(player.get("bonus_hp"), 0) + equipment_bonus(equipment_modifiers, "bonus_hp"))
    spirit_max = ceil(20 + eff["endurance"] * 1.2 + eff["strength"] * 1.0 + eff["agility"] * 0.7 + s_level * 1.2 + safe_int(player.get("bonus_spirit"), 0) + equipment_bonus(equipment_modifiers, "bonus_spirit"))
    mana_max = ceil(20 + eff["intelligence"] * 1.6 + eff["wisdom"] * 1.3 + s_level * 1.2 + safe_int(player.get("bonus_mana"), 0) + equipment_bonus(equipment_modifiers, "bonus_mana"))
    concentration_max = ceil(1 + (20 * eff["wisdom"] / (eff["wisdom"] + 4000)) + (12 * eff["intelligence"] / (eff["intelligence"] + 5000)) + (6 * eff["endurance"] / (eff["endurance"] + 6000)) + float(player.get("bonus_max_concentration") or 0) + equipment_bonus(equipment_modifiers, "bonus_max_concentration"))

    physical_defense = ceil(armor * 1.5 + eff["endurance"] * 0.9 + eff["strength"] * 0.6 + eff["agility"] * 0.2 + safe_int(player.get("bonus_physical_defense"), 0) + equipment_bonus(equipment_modifiers, "bonus_physical_defense"))
    magic_defense = ceil(magic_armor * 1.5 + eff["wisdom"] * 0.9 + eff["intelligence"] * 0.6 + eff["endurance"] * 0.2 + safe_int(player.get("bonus_magic_defense"), 0) + equipment_bonus(equipment_modifiers, "bonus_magic_defense"))
    accuracy = ceil(eff["perception"] * 1.8 + eff["agility"] * 1.1 + s_level * 0.7 + safe_int(player.get("bonus_accuracy"), 0) + equipment_bonus(equipment_modifiers, "bonus_accuracy"))
    dodge = ceil(eff["agility"] * 1.8 + eff["perception"] * 0.9 + eff["wisdom"] * 0.3 + s_level * 0.5 + safe_int(player.get("bonus_dodge"), 0) + equipment_bonus(equipment_modifiers, "bonus_dodge"))
    crit_stat = ceil(eff["perception"] * 1.5 + eff["agility"] * 0.8 + eff["wisdom"] * 0.2 + s_level * 0.2 + safe_int(player.get("bonus_crit_chance"), 0) + equipment_bonus(equipment_modifiers, "bonus_crit_chance"))
    crit_chance = min(0.49, crit_stat / (crit_stat + 5000))
    crit_damage = max(100, 100 + safe_int(player.get("bonus_crit_damage"), 0) + equipment_bonus(equipment_modifiers, "bonus_crit_damage"))

    attributes = []
    for front_key, back_key, label, description in ATTRIBUTE_META:
        base = safe_int((player.get("stats") or {}).get(back_key), 0)
        invested = safe_int((player.get("invested_stats") or {}).get(back_key), 0)
        bonus = safe_int((player.get("stat_bonuses") or {}).get(back_key), 0) + equipment_stat_bonus(equipment_modifiers, back_key)
        attributes.append({"key": front_key, "label": label, "value": base + invested + bonus, "description": description})

    equipment = {}
    for slot_key, raw_item in (player.get("equipment") or {}).items():
        if not isinstance(raw_item, dict):
            continue
        item = normalize_item(raw_item, raw_item.get("category", "Снаряжение"))
        item["slotKey"] = slot_key
        item["actions"] = ["Снять"]
        equipment[slot_key] = item

    inventory = []
    for raw_item in player.get("inventory", []):
        if not isinstance(raw_item, dict):
            continue
        item = normalize_item(raw_item)
        if item.get("category") in {"Снаряжение", "Оружие", "Бижутерия", "Особое"} and (item.get("targetSlotKey") or item.get("slot")):
            item["actions"] = ["Надеть"]
        elif item.get("category") in {"Алхимия", "Еда", "Напитки"}:
            item["actions"] = ["Использовать"]
        else:
            item.setdefault("actions", [])
        inventory.append(item)

    skills = player.get("skills", {}) if isinstance(player.get("skills"), dict) else {}
    active_skills = [normalize_skill(skill, level) for skill in skills.get("active", []) if isinstance(skill, dict)]
    passive_skills = [normalize_skill(skill, level) for skill in skills.get("passive", []) if isinstance(skill, dict)]

    crafting_levels = []
    for key, value in (player.get("crafting_levels") or {}).items():
        if isinstance(value, dict):
            crafting_levels.append({"name": CRAFT_LABELS.get(key, key), "level": safe_int(value.get("level"), 1), "exp": f"{safe_int(value.get('experience'), 0)} опыта"})

    race_key = RACE_MODEL_KEYS.get(str(player.get("race_id", "human")), str(player.get("race_id", "human")))

    return {
        "assets": {
            "background": "/assets/profile/backgrounds/1.png",
            "raceModels": {
                "human": "/assets/profile/models/human.png",
                "elf": "/assets/profile/models/elf.png",
                "dwarf": "/assets/profile/models/dwarf.png",
                "undead": "/assets/profile/models/undead.png",
                "lizardfolk": "/assets/profile/models/lizardfolk.png",
            },
        },
        "player": {
            "userGlobalId": player.get("game_id") or player.get("id"),
            "publicId": player.get("public_id"),
            "nickname": player.get("name", "Безымянный"),
            "raceKey": race_key,
            "raceName": player.get("race_name", "Человек"),
            "branch": player.get("branch", "Ветвь не выбрана"),
            "level": level,
            "experienceCurrent": safe_int(player.get("experience"), 0),
            "experienceToNext": safe_int(player.get("experience_to_next"), max(100, level * 100)),
            "freeAttributePoints": safe_int(player.get("free_stat_points"), 0),
            "freeSkillPoints": safe_int(player.get("free_skill_points"), 0),
            "balanceText": format_money(safe_int(player.get("money"), 0)),
            "registrationDate": format_date(player.get("created_at")),
        },
        "attributes": attributes,
        "parameters": [
            {"label": "HP", "value": f"{safe_int(player.get('hp'), hp_max)} / {hp_max}"},
            {"label": "Дух", "value": f"{safe_int(player.get('spirit'), spirit_max)} / {spirit_max}"},
            {"label": "Мана", "value": f"{safe_int(player.get('mana'), mana_max)} / {mana_max}"},
            {"label": "Энергия", "value": f"{safe_int(player.get('energy'), 100)} / {safe_int(player.get('max_energy'), 100)}"},
            {"label": "Концентрация", "value": f"{safe_int(player.get('concentration'), concentration_max)} / {concentration_max}"},
            {"label": "Физическая защита", "value": physical_defense},
            {"label": "Магическая защита", "value": magic_defense},
            {"label": "Точность", "value": accuracy},
            {"label": "Уклонение", "value": dodge},
            {"label": "Шанс крита", "value": f"{ceil(crit_chance * 100)}%"},
            {"label": "Урон крита", "value": f"{crit_damage}%"},
        ],
        "effects": player.get("active_effects", []),
        "activeSets": player.get("active_sets", []),
        "equipmentSlots": EQUIPMENT_SLOTS,
        "equipment": equipment,
        "inventory": inventory,
        "skills": {"active": active_skills, "passive": passive_skills},
        "information": {
            "achievements": player.get("achievements", []),
            "rating": player.get("rating", {"globalPlace": "—", "pvePlace": "—", "pvpPlace": "—", "craftPlace": "—"}),
            "activity": {"pveKills": safe_int(player.get("pve_kills"), 0), "pvpKills": safe_int(player.get("pvp_kills"), 0), "soulParticlesAbsorbed": safe_int(player.get("soul_particles_absorbed"), 0), "craftingLevels": crafting_levels},
        },
    }


def get_player_by_public_id(storage: Any, public_id: str) -> dict[str, Any] | None:
    if hasattr(storage, "get_player_by_public_id"):
        player = storage.get_player_by_public_id(public_id)
        if player is not None:
            return player
    for player in (storage.load().get("players") or {}).values():
        if isinstance(player, dict) and str(player.get("public_id")) == str(public_id):
            return player
    return None


def get_session_and_player_by_token(storage: Any, token: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if hasattr(storage, "get_player_by_web_token"):
        return storage.get_player_by_web_token(token, scope=PROFILE_SCOPE)
    data = storage.load()
    sessions = data.get("web_sessions") or data.get("site_sessions") or {}
    session = sessions.get(token)
    if not session or session.get("scope") != PROFILE_SCOPE:
        return None, None
    expires_at = parse_datetime(session.get("expires_at"))
    if expires_at and expires_at <= datetime.now(timezone.utc):
        return None, None
    player = (data.get("players") or {}).get(session.get("game_id"))
    return player, session if player else None


def resolve_profile_read(storage: Any, identifier: str) -> tuple[dict[str, Any], bool]:
    player, session = get_session_and_player_by_token(storage, identifier)
    if player is not None and session is not None:
        return player, True
    player = get_player_by_public_id(storage, identifier)
    if player is not None:
        return player, False
    raise HTTPException(status_code=404, detail="Профиль игрока не найден или ссылка истекла.")


def resolve_profile_write(storage: Any, identifier: str) -> dict[str, Any]:
    player, session = get_session_and_player_by_token(storage, identifier)
    if player is None or session is None:
        raise HTTPException(status_code=401, detail="Действие доступно только по временной ссылке из бота.")
    return player


def save_player(storage: Any, player: dict[str, Any]) -> None:
    if hasattr(storage, "update_player"):
        storage.update_player(player)
        return
    data = storage.load()
    game_id = player.get("game_id") or player.get("id")
    if not game_id:
        raise HTTPException(status_code=500, detail="Нельзя сохранить игрока без game_id.")
    data.setdefault("players", {})[game_id] = player
    storage.save(data)


def find_player_skill(player: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    target = str(skill_id or "").strip()
    if not target:
        return None
    skills = player.get("skills")
    if not isinstance(skills, dict):
        return None
    for section in ("active", "passive"):
        for skill in skills.get(section, []):
            if not isinstance(skill, dict):
                continue
            if target in {str(skill.get("id") or ""), str(skill.get("name") or "")}:
                return skill
    return None


def spend_points_on_skill(skill: dict[str, Any], modifier_id: str | None, amount: int) -> None:
    if not skill.get("upgradeable"):
        raise HTTPException(status_code=400, detail="Этот навык нельзя улучшить.")

    skill["level"] = safe_int(skill.get("level"), 0) + amount
    modifiers = skill.get("modifiers")
    target_modifier = str(modifier_id or "main").strip()
    if not isinstance(modifiers, list) or not modifiers:
        if target_modifier in {"", "main"}:
            return
        raise HTTPException(status_code=400, detail="Модификатор навыка не найден.")

    for modifier in modifiers:
        if not isinstance(modifier, dict):
            continue
        modifier_keys = {
            str(modifier.get("id") or ""),
            str(modifier.get("name") or ""),
            str(modifier.get("label") or ""),
        }
        if target_modifier in modifier_keys:
            level_key = "level" if "level" in modifier or "points" not in modifier else "points"
            modifier[level_key] = safe_int(modifier.get(level_key), 0) + amount
            return

    raise HTTPException(status_code=400, detail="Модификатор навыка не найден.")


def create_profile_api_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/profile", tags=["profile"])

    @router.get("/{identifier}")
    def get_profile(identifier: str) -> dict[str, Any]:
        player, _is_private = resolve_profile_read(get_storage(), identifier)
        return frontend_profile(player)

    @router.post("/{identifier}/attributes/spend")
    def spend_attribute(identifier: str, request: SpendAttributeRequest) -> dict[str, Any]:
        storage = get_storage()
        player = resolve_profile_write(storage, identifier)
        stat_key = FRONT_TO_BACK_STAT.get(request.attribute_key)
        if not stat_key:
            raise HTTPException(status_code=400, detail="Неизвестная характеристика.")
        free_points = safe_int(player.get("free_stat_points"), 0)
        if request.amount > free_points:
            raise HTTPException(status_code=400, detail="Недостаточно свободных очков характеристик.")
        player.setdefault("invested_stats", {})[stat_key] = safe_int(player.setdefault("invested_stats", {}).get(stat_key), 0) + request.amount
        player["free_stat_points"] = free_points - request.amount
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile(player)}

    @router.post("/{identifier}/skills/spend")
    def spend_skill(identifier: str, request: SpendSkillRequest) -> dict[str, Any]:
        storage = get_storage()
        player = resolve_profile_write(storage, identifier)
        free_points = safe_int(player.get("free_skill_points"), 0)
        if request.amount > free_points:
            raise HTTPException(status_code=400, detail="Недостаточно свободных очков навыков.")
        skill = find_player_skill(player, request.skill_id)
        if skill is None:
            raise HTTPException(status_code=404, detail="Навык не найден.")
        spend_points_on_skill(skill, request.modifier_id, request.amount)
        player["free_skill_points"] = free_points - request.amount
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile(player)}

    @router.post("/{identifier}/equipment/equip")
    def equip_inventory_item(identifier: str, request: EquipItemRequest) -> dict[str, Any]:
        storage = get_storage()
        player = resolve_profile_write(storage, identifier)
        inventory = player.setdefault("inventory", [])
        equipment = player.setdefault("equipment", {})
        item_index = next((index for index, item in enumerate(inventory) if isinstance(item, dict) and str(item.get("id") or item.get("item_id")) == request.item_id), None)
        if item_index is None:
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        item = inventory.pop(item_index)
        slot_key = item.get("targetSlotKey") or item.get("slotKey") or item.get("slot")
        if not slot_key:
            inventory.insert(item_index, item)
            raise HTTPException(status_code=400, detail="У предмета не указан слот экипировки.")
        previous_item = equipment.get(slot_key)
        if isinstance(previous_item, dict):
            previous_item["targetSlotKey"] = slot_key
            previous_item.pop("slotKey", None)
            inventory.append(previous_item)
        item["slotKey"] = slot_key
        item.pop("targetSlotKey", None)
        equipment[slot_key] = item
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile(player)}

    @router.post("/{identifier}/equipment/unequip")
    def unequip_inventory_item(identifier: str, request: UnequipItemRequest) -> dict[str, Any]:
        storage = get_storage()
        player = resolve_profile_write(storage, identifier)
        equipment = player.setdefault("equipment", {})
        item = equipment.pop(request.slot_key, None)
        if not isinstance(item, dict):
            raise HTTPException(status_code=404, detail="В этом слоте нет предмета.")
        item["targetSlotKey"] = request.slot_key
        item.pop("slotKey", None)
        player.setdefault("inventory", []).append(item)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile(player)}

    @router.post("/{identifier}/inventory/use")
    def use_inventory_item(identifier: str, request: UseItemRequest) -> dict[str, Any]:
        storage = get_storage()
        player = resolve_profile_write(storage, identifier)
        inventory = player.setdefault("inventory", [])
        item_index = next((index for index, item in enumerate(inventory) if isinstance(item, dict) and str(item.get("id") or item.get("item_id")) == request.item_id), None)
        if item_index is None:
            raise HTTPException(status_code=404, detail="Предмет в инвентаре не найден.")
        item = inventory[item_index]
        amount = safe_int(item.get("amount"), 1)
        if amount > 1:
            item["amount"] = amount - 1
        else:
            inventory.pop(item_index)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile(player)}

    return router
