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

from services.item_registry import enrich_inventory_item
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
    ("wisdom", "wisdom", "Мудрость", "Поддержка, лечение, регенерация маны и устойчивые магические формы."),
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

ITEM_VALUE_TRANSLATIONS = {
    "weapon": "Оружие",
    "armor": "Броня",
    "jewelry": "Бижутерия",
    "accessory": "Аксессуар",
    "consumable": "Расходник",
    "potion": "Зелье",
    "food": "Еда",
    "drink": "Напиток",
    "resource": "Ресурс",
    "staff": "Посох",
    "sword": "Меч",
    "axe": "Топор",
    "dagger": "Кинжал",
    "bow": "Лук",
    "crossbow": "Арбалет",
    "mace": "Булава",
    "hammer": "Молот",
    "shield": "Щит",
    "cloth_armor": "Тканевая броня",
    "light_armor": "Лёгкая броня",
    "medium_armor": "Средняя броня",
    "heavy_armor": "Тяжёлая броня",
    "light_boots": "Лёгкие сапоги",
    "cloth_headwear": "Тканевый головной убор",
    "ring": "Кольцо",
    "necklace": "Ожерелье",
    "bracelet": "Браслет",
    "helmet": "Шлем",
    "chest": "Нагрудник",
    "pants": "Штаны",
    "boots": "Ботинки",
    "gloves": "Перчатки",
    "belt": "Пояс",
    "special": "Особый предмет",
    "physical": "Физический",
    "magic": "Магический",
    "physical_blunt": "Дробящий физический",
    "melee": "Ближний бой",
    "ranged": "Дальний бой",
    "normal": "Обычная",
}

ENGLISH_ITEM_NAME_TRANSLATIONS = {
    "wooden staff": "Деревянный посох",
    "tunic": "Туника",
    "canvas pants": "Холщевые штаны",
    "old boots": "Старые сапоги",
    "bandana": "Бандана",
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


class SkillEquipRequest(BaseModel):
    skill_id: str


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


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def effective_stat(player: dict[str, Any], stat_key: str, bonus_modifiers: dict[str, int] | None = None) -> int:
    base = safe_int((player.get("stats") or {}).get(stat_key), 0)
    invested = safe_int((player.get("invested_stats") or {}).get(stat_key), 0)
    bonus = safe_int((player.get("stat_bonuses") or {}).get(stat_key), 0)
    if bonus_modifiers:
        bonus += equipment_stat_bonus(bonus_modifiers, stat_key)
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
    else:
        match = re.match(r"([+-]?\s*\d+(?:[.,]\d+)?)\s*(?:к\s+)?(.+)$", text, flags=re.IGNORECASE)
        if not match:
            return None
        value, label = match.groups()
    modifier_key = normalize_modifier_key(label)
    if not modifier_key:
        return None
    match = re.search(r"([+-]?)\s*(\d+(?:[.,]\d+)?)", value)
    if not match:
        return None
    sign = -1 if match.group(1) == "-" else 1
    amount = int(float(match.group(2).replace(",", ".")))
    return modifier_key, sign * amount


def normalize_modifier_key(key: Any) -> str | None:
    raw_key = str(key or "").strip()
    if not raw_key:
        return None
    folded = raw_key.casefold()
    if folded in ITEM_STAT_LABEL_TO_MODIFIER:
        return ITEM_STAT_LABEL_TO_MODIFIER[folded]
    snake_key = folded.replace("-", "_").replace(" ", "_").replace(".", "")
    normalized = MODIFIER_KEY_ALIASES.get(snake_key, snake_key)
    if normalized in KNOWN_MODIFIER_KEYS:
        return normalized
    return None


def modifier_amount(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        if contains_formula_text(value):
            return 0
        match = re.search(r"([+-]?)\s*(\d+(?:[.,]\d+)?)", value)
        if match:
            sign = -1 if match.group(1) == "-" else 1
            return sign * int(float(match.group(2).replace(",", ".")))
    return safe_int(value, 0)


def add_modifier(totals: dict[str, int], key: Any, value: Any) -> None:
    normalized_key = normalize_modifier_key(key)
    if not normalized_key:
        return
    totals[normalized_key] = safe_int(totals.get(normalized_key), 0) + modifier_amount(value)


def collect_modifiers_from_value(value: Any, totals: dict[str, int]) -> None:
    if isinstance(value, dict):
        explicit_fields = ("stat_modifiers", "modifiers", "bonus_modifiers", "effect_modifiers", "bonuses")
        has_explicit_modifiers = any(isinstance(value.get(field), (dict, list)) for field in explicit_fields)

        for field in explicit_fields:
            nested = value.get(field)
            if isinstance(nested, (dict, list)):
                collect_modifiers_from_value(nested, totals)

        text_fields = ("properties", "enchantments", "effects") if has_explicit_modifiers else ("stats", "properties", "enchantments", "effects")
        for field in text_fields:
            nested = value.get(field)
            if isinstance(nested, (dict, list)):
                collect_modifiers_from_value(nested, totals)

        skipped_fields = set(explicit_fields) | {"stats", "properties", "enchantments", "effects"}
        for key, nested_value in value.items():
            if key in skipped_fields:
                continue
            if isinstance(nested_value, (int, float, str)):
                add_modifier(totals, key, nested_value)
        return

    if isinstance(value, list):
        for nested in value:
            collect_modifiers_from_value(nested, totals)
        return

    parsed = parse_item_stat_modifier(value)
    if parsed is not None:
        key, amount = parsed
        add_modifier(totals, key, amount)


def equipment_modifier_totals(player: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    equipment = player.get("equipment") or {}
    if not isinstance(equipment, dict):
        return totals
    for raw_item in equipment.values():
        if isinstance(raw_item, dict):
            collect_modifiers_from_value(raw_item, totals)
    return totals


def external_effect_modifier_totals(player: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for field in EXTERNAL_EFFECT_FIELDS:
        collect_modifiers_from_value(player.get(field), totals)
    return totals


def merge_modifier_totals(*sources: dict[str, int]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for source in sources:
        for key, value in (source or {}).items():
            add_modifier(totals, key, value)
    return totals


def equipment_bonus(bonus_modifiers: dict[str, int] | None, key: str) -> int:
    return safe_int((bonus_modifiers or {}).get(key), 0)


def consumable_effect_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    effect_payload = item.get("use_effect") or item.get("active_effect") or item.get("consumable_effect")
    if effect_payload is None and any(field in item for field in ("stat_modifiers", "modifiers", "bonus_modifiers", "effect_modifiers", "bonuses")):
        effect_payload = item
    if effect_payload is None:
        return None
    totals: dict[str, int] = {}
    collect_modifiers_from_value(effect_payload, totals)
    if not totals:
        return None
    return {
        "id": f"effect_{item.get('id') or item.get('item_id') or item.get('name')}",
        "name": item.get("effect_name") or item.get("name") or "Временный эффект",
        "source": "consumable",
        "stat_modifiers": totals,
        "description": item.get("effect_description") or item.get("description") or "Эффект от использованного предмета.",
    }


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


def translate_item_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    translated = ITEM_VALUE_TRANSLATIONS.get(stripped.casefold())
    return translated or stripped


def translate_item_name(value: Any) -> str:
    if not isinstance(value, str):
        return "Безымянный предмет"
    stripped = value.strip()
    return ENGLISH_ITEM_NAME_TRANSLATIONS.get(stripped.casefold(), stripped or "Безымянный предмет")


HIDDEN_FORMULA_KEYS = {"formula", "base_damage_formula", "damage_formula", "scaling_formula"}
FORMULA_TEXT_MARKERS = ("player_level", "ceil(", "floor(", "log2(", "ln(", "уровень ×", "уровня ×", "уровень персонажа ×")
CONCENTRATION_TEXT_MARKERS = ("концентрац", "concentration")
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
    "критический урон": "bonus_crit_damage",
    "реген hp": "bonus_hp_regen_percent",
    "регенерация hp": "bonus_hp_regen_percent",
    "реген здоровья": "bonus_hp_regen_percent",
    "реген духа": "bonus_spirit_regen_percent",
    "регенерация духа": "bonus_spirit_regen_percent",
    "реген маны": "bonus_mana_regen_percent",
    "регенерация маны": "bonus_mana_regen_percent",
    "энергия": "bonus_max_energy",
    "макс. энергия": "bonus_max_energy",
    "максимальная энергия": "bonus_max_energy",
    "экономия энергии": "bonus_energy_saving_percent",
    "восстановление энергии": "bonus_energy_restore_percent",
    "урон": "bonus_damage",
    "физический урон": "bonus_physical_damage",
    "магический урон": "bonus_magic_damage",
    "сила": "bonus_strength",
    "выносливость": "bonus_endurance",
    "ловкость": "bonus_agility",
    "восприятие": "bonus_perception",
    "интеллект": "bonus_intelligence",
    "мудрость": "bonus_wisdom",
}
MODIFIER_KEY_ALIASES = {
    "hp": "bonus_hp",
    "spirit": "bonus_spirit",
    "mana": "bonus_mana",
    "strength": "bonus_strength",
    "endurance": "bonus_endurance",
    "agility": "bonus_agility",
    "dexterity": "bonus_agility",
    "perception": "bonus_perception",
    "intelligence": "bonus_intelligence",
    "wisdom": "bonus_wisdom",
    "crit_damage_percent": "bonus_crit_damage",
    "bonus_crit_damage_percent": "bonus_crit_damage",
    "critical_damage": "bonus_crit_damage",
    "critical_damage_percent": "bonus_crit_damage",
    "hp_regen_percent": "bonus_hp_regen_percent",
    "spirit_regen_percent": "bonus_spirit_regen_percent",
    "mana_regen_percent": "bonus_mana_regen_percent",
    "max_energy": "bonus_max_energy",
    "energy_saving_percent": "bonus_energy_saving_percent",
    "energy_restore_bonus_percent": "bonus_energy_restore_percent",
    "energy_restore_percent": "bonus_energy_restore_percent",
    "physical_damage": "bonus_physical_damage",
    "magic_damage": "bonus_magic_damage",
    "damage": "bonus_damage",
}
KNOWN_MODIFIER_KEYS = {
    "armor",
    "magic_armor",
    "bonus_hp",
    "bonus_spirit",
    "bonus_mana",
    "bonus_physical_defense",
    "bonus_magic_defense",
    "bonus_accuracy",
    "bonus_dodge",
    "bonus_crit_chance",
    "bonus_crit_damage",
    "bonus_strength",
    "bonus_endurance",
    "bonus_agility",
    "bonus_perception",
    "bonus_intelligence",
    "bonus_wisdom",
    "bonus_hp_regen_percent",
    "bonus_spirit_regen_percent",
    "bonus_mana_regen_percent",
    "bonus_max_energy",
    "bonus_energy_saving_percent",
    "bonus_energy_restore_percent",
    "bonus_damage",
    "bonus_physical_damage",
    "bonus_magic_damage",
}
EXTERNAL_EFFECT_FIELDS = (
    "active_effects",
    "effects",
    "temporary_effects",
    "location_effects",
    "active_location_effects",
    "environment_effects",
    "active_buffs",
    "buffs",
    "potions",
    "consumed_potions",
    "active_consumables",
    "active_food_effects",
    "active_sets",
)


def contains_formula_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return any(marker in lowered for marker in FORMULA_TEXT_MARKERS)


def contains_concentration_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return any(marker in lowered for marker in CONCENTRATION_TEXT_MARKERS)


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
    item = enrich_inventory_item(item)
    normalized = strip_hidden_formulas(deepcopy(item))
    if not isinstance(normalized, dict):
        normalized = {}
    normalized.setdefault("id", normalized.get("item_id") or normalized.get("name") or "item")
    normalized["name"] = translate_item_name(normalized.get("name"))
    normalized["category"] = translate_item_value(normalized.get("category") or default_category)
    raw_subtype = normalized.get("subtype")
    raw_type = normalized.get("type") or normalized.get("slotKey") or normalized.get("slot") or "Предмет"
    translated_subtype = translate_item_value(raw_subtype) if raw_subtype else None
    translated_type = translate_item_value(raw_type)
    normalized["type"] = translated_subtype if translated_subtype and translated_type in {"Оружие", "Броня", "Предмет"} else translated_type
    if raw_subtype:
        normalized["subtype"] = translated_subtype
    normalized["quality"] = normalize_quality(normalized.get("quality"))
    normalized.setdefault("level", 1)
    normalized.setdefault("description", "Описание предмета пока не добавлено.")
    normalized.setdefault("stats", [])
    normalized.setdefault("enchantments", [])
    normalized.setdefault("compare", [])
    normalized.setdefault("amount", 1)
    return normalized


def format_skill_damage(skill: dict[str, Any], player_level: int, bonus_modifiers: dict[str, int] | None = None) -> Any:
    if not isinstance(skill, dict):
        return None
    formula = str(skill.get("base_damage_formula") or "")
    generic_bonus = equipment_bonus(bonus_modifiers, "bonus_damage")
    if skill.get("id") == "basic_attack" or "5 + player_level * 1.2" in formula:
        return max(1, ceil(5 + player_level * 1.2 + generic_bonus + equipment_bonus(bonus_modifiers, "bonus_physical_damage")))
    if skill.get("id") == "magic_spark" or "4 + player_level * 1.1" in formula:
        return max(1, ceil(4 + player_level * 1.1 + generic_bonus + equipment_bonus(bonus_modifiers, "bonus_magic_damage")))
    damage = skill.get("damage")
    if contains_formula_text(damage):
        return None
    if isinstance(damage, (int, float)):
        return max(1, ceil(float(damage) + generic_bonus))
    return damage


def skill_resource_text(skill: dict[str, Any]) -> str:
    mana = safe_float(skill.get("mana_cost") if "mana_cost" in skill else skill.get("manaCost"), 0)
    spirit = safe_float(skill.get("spirit_cost") if "spirit_cost" in skill else skill.get("spiritCost"), 0)
    parts: list[str] = []
    if mana > 0:
        parts.append(f"Мана: {mana:g}")
    if spirit > 0:
        parts.append(f"Дух: {spirit:g}")
    if parts:
        return "Расход: " + " · ".join(parts)
    return "Расход: не требует маны и духа"


def skill_cooldown_text(skill: dict[str, Any]) -> str:
    turns = safe_int(skill.get("cooldown_turns") if "cooldown_turns" in skill else skill.get("cooldown"), 0)
    return f"Откат: {turns} ходов"


def normalize_skill(skill: dict[str, Any], player_level: int, bonus_modifiers: dict[str, int] | None = None, source_section: str = "active") -> dict[str, Any]:
    normalized = strip_hidden_formulas(deepcopy(skill))
    if not isinstance(normalized, dict):
        normalized = {}
    for hidden_key in ("concentration_cost", "concentrationCost", "bonus_max_concentration", "bonus_concentration_regen"):
        normalized.pop(hidden_key, None)
    damage = format_skill_damage(skill, player_level, bonus_modifiers)
    if damage is not None:
        normalized["damage"] = damage
    else:
        normalized.pop("damage", None)
    raw_resource_text = skill.get("resource_text") or skill.get("cost")
    if isinstance(raw_resource_text, str) and not contains_concentration_text(raw_resource_text) and not contains_formula_text(raw_resource_text):
        normalized["resourceText"] = raw_resource_text
    else:
        normalized["resourceText"] = skill_resource_text(skill)
    normalized["cooldownText"] = skill.get("cooldown_text") or skill_cooldown_text(skill)
    normalized["cooldown"] = safe_int(skill.get("cooldown_turns") if "cooldown_turns" in skill else skill.get("cooldown"), 0)
    skill_type = str(skill.get("skill_type") or skill.get("type") or source_section or "active").lower()
    normalized.setdefault("skill_type", skill_type)
    normalized["equippable"] = bool(skill.get("equippable", skill_type not in {"passive", "пассивный"}))
    return normalized


def frontend_profile(player: dict[str, Any]) -> dict[str, Any]:
    level = safe_int(player.get("level"), 1) or 1
    s_level = soft_level(level)
    equipment_modifiers = equipment_modifier_totals(player)
    external_modifiers = external_effect_modifier_totals(player)
    bonus_modifiers = merge_modifier_totals(equipment_modifiers, external_modifiers)
    eff = {front_key: effective_stat(player, back_key, bonus_modifiers) for front_key, back_key, *_ in ATTRIBUTE_META}
    armor = safe_int(player.get("armor"), 0) + equipment_bonus(bonus_modifiers, "armor")
    magic_armor = safe_int(player.get("magic_armor"), safe_int(player.get("armor"), 0)) + equipment_bonus(bonus_modifiers, "magic_armor")

    hp_max = ceil(100 + eff["endurance"] * 4.0 + eff["strength"] * 0.8 + s_level * 4 + safe_int(player.get("bonus_hp"), 0) + equipment_bonus(bonus_modifiers, "bonus_hp"))
    spirit_max = ceil(20 + eff["endurance"] * 1.2 + eff["strength"] * 1.0 + eff["agility"] * 0.7 + s_level * 1.2 + safe_int(player.get("bonus_spirit"), 0) + equipment_bonus(bonus_modifiers, "bonus_spirit"))
    mana_max = ceil(20 + eff["intelligence"] * 1.6 + eff["wisdom"] * 1.3 + s_level * 1.2 + safe_int(player.get("bonus_mana"), 0) + equipment_bonus(bonus_modifiers, "bonus_mana"))
    physical_defense = ceil(armor * 1.5 + eff["endurance"] * 0.9 + eff["strength"] * 0.6 + eff["agility"] * 0.2 + safe_int(player.get("bonus_physical_defense"), 0) + equipment_bonus(bonus_modifiers, "bonus_physical_defense"))
    magic_defense = ceil(magic_armor * 1.5 + eff["wisdom"] * 0.9 + eff["intelligence"] * 0.6 + eff["endurance"] * 0.2 + safe_int(player.get("bonus_magic_defense"), 0) + equipment_bonus(bonus_modifiers, "bonus_magic_defense"))
    accuracy = ceil(eff["perception"] * 1.8 + eff["agility"] * 1.1 + s_level * 0.7 + safe_int(player.get("bonus_accuracy"), 0) + equipment_bonus(bonus_modifiers, "bonus_accuracy"))
    dodge = ceil(eff["agility"] * 1.8 + eff["perception"] * 0.9 + eff["wisdom"] * 0.3 + s_level * 0.5 + safe_int(player.get("bonus_dodge"), 0) + equipment_bonus(bonus_modifiers, "bonus_dodge"))
    crit_stat = ceil(eff["perception"] * 1.5 + eff["agility"] * 0.8 + eff["wisdom"] * 0.2 + s_level * 0.2 + safe_int(player.get("bonus_crit_chance"), 0) + equipment_bonus(bonus_modifiers, "bonus_crit_chance"))
    crit_chance = min(0.49, crit_stat / (crit_stat + 5000))
    crit_damage = max(100, 100 + safe_int(player.get("bonus_crit_damage"), 0) + equipment_bonus(bonus_modifiers, "bonus_crit_damage"))
    max_energy = max(1, safe_int(player.get("max_energy"), 100) + equipment_bonus(bonus_modifiers, "bonus_max_energy"))
    current_energy = max(0, min(max_energy, safe_int(player.get("energy"), max_energy)))

    attributes = []
    for front_key, back_key, label, description in ATTRIBUTE_META:
        base = safe_int((player.get("stats") or {}).get(back_key), 0)
        invested = safe_int((player.get("invested_stats") or {}).get(back_key), 0)
        bonus = safe_int((player.get("stat_bonuses") or {}).get(back_key), 0) + equipment_stat_bonus(bonus_modifiers, back_key)
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
    equipped_skills = [normalize_skill(skill, level, bonus_modifiers, "equipped") for skill in skills.get("equipped", []) if isinstance(skill, dict)]
    equipped_skill_keys = {str(skill.get("id") or skill.get("name") or "") for skill in equipped_skills}
    active_skills = [
        normalize_skill(skill, level, bonus_modifiers, "active")
        for skill in skills.get("active", [])
        if isinstance(skill, dict) and str(skill.get("id") or skill.get("name") or "") not in equipped_skill_keys
    ]
    passive_skills = [
        normalize_skill(skill, level, bonus_modifiers, "passive")
        for skill in skills.get("passive", [])
        if isinstance(skill, dict) and str(skill.get("id") or skill.get("name") or "") not in equipped_skill_keys
    ]

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
            "inventoryCapacity": safe_int(player.get("inventory_capacity") or player.get("max_inventory_slots") or player.get("inventory_slots"), 20),
            "inventoryUsedSlots": len(inventory),
            "inventoryFreeSlots": max(0, safe_int(player.get("inventory_capacity") or player.get("max_inventory_slots") or player.get("inventory_slots"), 20) - len(inventory)),
            "skillEquipCapacity": safe_int(player.get("skill_equip_capacity") or player.get("max_equipped_skills"), 2),
            "skillEquipUsed": len(equipped_skills),
            "skillEquipFree": max(0, safe_int(player.get("skill_equip_capacity") or player.get("max_equipped_skills"), 2) - len(equipped_skills)),
        },
        "attributes": attributes,
        "parameters": [
            {"label": "HP", "value": f"{safe_int(player.get('hp'), hp_max)} / {hp_max}"},
            {"label": "Дух", "value": f"{safe_int(player.get('spirit'), spirit_max)} / {spirit_max}"},
            {"label": "Мана", "value": f"{safe_int(player.get('mana'), mana_max)} / {mana_max}"},
            {"label": "Энергия", "value": f"{current_energy} / {max_energy}"},
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
        "skills": {"active": active_skills, "equipped": equipped_skills, "passive": passive_skills},
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


def skill_matches(skill: dict[str, Any], skill_id: str) -> bool:
    target = str(skill_id or "").strip()
    return bool(target) and target in {str(skill.get("id") or ""), str(skill.get("name") or "")}


def find_player_skill_with_section(player: dict[str, Any], skill_id: str, sections: tuple[str, ...] = ("active", "equipped", "passive")) -> tuple[str, int, dict[str, Any]] | None:
    skills = player.get("skills")
    if not isinstance(skills, dict):
        return None
    for section in sections:
        section_skills = skills.get(section, [])
        if not isinstance(section_skills, list):
            continue
        for index, skill in enumerate(section_skills):
            if isinstance(skill, dict) and skill_matches(skill, skill_id):
                return section, index, skill
    return None


def find_player_skill(player: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    found = find_player_skill_with_section(player, skill_id)
    return found[2] if found else None


def equip_player_skill(player: dict[str, Any], skill_id: str) -> None:
    skills = player.setdefault("skills", {})
    equipped = skills.setdefault("equipped", [])
    if not isinstance(equipped, list):
        equipped = []
        skills["equipped"] = equipped
    if any(isinstance(skill, dict) and skill_matches(skill, skill_id) for skill in equipped):
        return
    capacity = safe_int(player.get("skill_equip_capacity") or player.get("max_equipped_skills"), 2)
    if len(equipped) >= capacity:
        raise HTTPException(status_code=400, detail="Нет свободных слотов экипированных навыков.")
    found = find_player_skill_with_section(player, skill_id, ("active", "passive"))
    if found is None:
        raise HTTPException(status_code=404, detail="Навык не найден.")
    source_section, index, skill = found
    skill_type = str(skill.get("skill_type") or skill.get("type") or source_section).lower()
    if skill.get("equippable") is False or skill_type in {"passive", "пассивный"}:
        raise HTTPException(status_code=400, detail="Этот навык нельзя экипировать для использования.")
    source_list = skills.get(source_section)
    if isinstance(source_list, list):
        source_list.pop(index)
    skill["source_section"] = source_section
    equipped.append(skill)


def unequip_player_skill(player: dict[str, Any], skill_id: str) -> None:
    skills = player.setdefault("skills", {})
    found = find_player_skill_with_section(player, skill_id, ("equipped",))
    if found is None:
        raise HTTPException(status_code=404, detail="Экипированный навык не найден.")
    _section, index, skill = found
    equipped = skills.get("equipped", [])
    if isinstance(equipped, list):
        equipped.pop(index)
    target_section = skill.pop("source_section", None) or ("passive" if str(skill.get("skill_type") or "").lower() in {"passive", "пассивный"} else "active")
    skills.setdefault(target_section, []).append(skill)


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

    @router.post("/{identifier}/skills/equip")
    def equip_skill(identifier: str, request: SkillEquipRequest) -> dict[str, Any]:
        storage = get_storage()
        player = resolve_profile_write(storage, identifier)
        equip_player_skill(player, request.skill_id)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile(player)}

    @router.post("/{identifier}/skills/unequip")
    def unequip_skill(identifier: str, request: SkillEquipRequest) -> dict[str, Any]:
        storage = get_storage()
        player = resolve_profile_write(storage, identifier)
        unequip_player_skill(player, request.skill_id)
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
        if item.get("category") in {"Алхимия", "Еда", "Напитки"}:
            effect = consumable_effect_from_item(item)
            if effect is not None:
                player.setdefault("active_effects", []).append(effect)
        amount = safe_int(item.get("amount"), 1)
        if amount > 1:
            item["amount"] = amount - 1
        else:
            inventory.pop(item_index)
        save_player(storage, player)
        return {"ok": True, "profile": frontend_profile(player)}

    return router
