"""Unified derived stat and modifier calculations for profile, bots and PVE.

The project used to have separate formula copies in the profile API and the PVE
service. Keeping the calculations here prevents profile values and combat values
from drifting apart when equipment, textual item modifiers or temporary effects
are added.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from services.race_bonus_service import hp_multiplier, outgoing_damage_multiplier, stat_multiplier
from services.active_skill_service import skill_level, skill_modifier_multiplier, skill_profile_power, passive_skill_multiplier, passive_stat_modifiers

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
    "bonus_inventory_slots",
    "bonus_stun_resist_chance",
    "bonus_blind_resist_chance",
    "bonus_bleed_resist_chance",
    "bonus_poison_resist_chance",
    "bonus_npc_buy_discount_percent",
    "bonus_npc_sell_bonus_percent",
}

EXTERNAL_EFFECT_FIELDS = (
    "active_effects",
    "active_curses",
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


def safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ceil(value: float) -> int:
    return int(math.ceil(value))


def soft_level(level: int) -> int:
    return int(math.floor(10 * math.log2(max(1, level) + 1)))


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


def collect_modifiers_from_value(value: Any, totals: dict[str, int]) -> None:
    if isinstance(value, dict):
        explicit_fields = ("stat_modifiers", "modifiers", "bonus_modifiers", "effect_modifiers", "bonuses")
        has_explicit_modifiers = any(isinstance(value.get(field), (dict, list)) for field in explicit_fields)

        for field in explicit_fields:
            nested = value.get(field)
            if isinstance(nested, (dict, list)):
                collect_modifiers_from_value(nested, totals)

        # Предмет/навык может хранить только ссылки на опубликованные эффекты.
        for link in value.get("effect_links") or []:
            effect_id = str((link or {}).get("effect_id") or "") if isinstance(link, dict) else str(link or "")
            if not effect_id:
                continue
            trigger = str((link or {}).get("trigger") or "passive") if isinstance(link, dict) else "passive"
            if trigger not in ("passive", "on_equip"):
                continue
            try:
                from services.effect_formula_runtime import resolve
                definition = resolve(effect_id)
            except Exception:
                definition = None
            if definition:
                etype = str(definition.get("effect_type") or "")
                if etype == "stat_modifier":
                    add_modifier(totals, definition.get("stat"), definition.get("value", definition.get("value_flat", definition.get("value_percent", 0))))
                collect_modifiers_from_value(definition, totals)

        text_fields = ("properties", "enchantments", "effects") if has_explicit_modifiers else ("stats", "properties", "enchantments", "effects")
        for field in text_fields:
            nested = value.get(field)
            if isinstance(nested, (dict, list)):
                collect_modifiers_from_value(nested, totals)

        skipped_fields = set(explicit_fields) | {"stats", "properties", "enchantments", "effects", "effect_links"}
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


def parse_effect_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_effect_active(effect: Any, now: datetime | None = None) -> bool:
    if not isinstance(effect, dict):
        return True
    expires_at = parse_effect_datetime(effect.get("expires_at"))
    if expires_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    return expires_at > now


def prune_expired_effects(player: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    changed = False
    for field in EXTERNAL_EFFECT_FIELDS:
        value = player.get(field)
        if not isinstance(value, list):
            continue
        filtered = [effect for effect in value if is_effect_active(effect, now)]
        if len(filtered) != len(value):
            player[field] = filtered
            changed = True
    return changed


def collect_active_external_modifiers(value: Any, totals: dict[str, int], now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if isinstance(value, list):
        for item in value:
            collect_active_external_modifiers(item, totals, now)
        return
    if isinstance(value, dict):
        if not is_effect_active(value, now):
            return
        effect_id = str(value.get("effect_id") or value.get("id") or "").strip()
        if effect_id and not value.get("constructor_live"):
            try:
                from services.effect_formula_runtime import resolve
                definition = resolve(effect_id)
            except Exception:
                definition = None
            if definition:
                merged = {**definition, **value, "constructor_live": True}
                etype = str(merged.get("effect_type") or "")
                if etype == "stat_modifier":
                    stat = str(merged.get("stat") or "")
                    amount = merged.get("value", merged.get("value_flat", merged.get("value_percent", 0)))
                    add_modifier(totals, stat, amount)
                elif etype == "max_resource_modifier":
                    resource = str(merged.get("resource") or "")
                    add_modifier(totals, f"bonus_{resource}", merged.get("value", merged.get("value_flat", 0)))
                collect_modifiers_from_value(merged, totals)
                return
    collect_modifiers_from_value(value, totals)


def external_effect_modifier_totals(player: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = {}
    now = datetime.now(timezone.utc)
    for field in EXTERNAL_EFFECT_FIELDS:
        collect_active_external_modifiers(player.get(field), totals, now)
    return totals


def active_resource_max_percent(player: dict[str, Any], now: datetime | None = None) -> dict[str, int]:
    """Sum percentage modifiers to max HP/spirit/mana from active consumable effects.

    Consumables (mana/spirit/life crystals) add an active effect that carries a
    ``resource_max_percent`` payload like ``{"max_mana": 20, "max_hp": -5}``.
    Expired effects are ignored.
    """
    now = now or datetime.now(timezone.utc)
    totals: dict[str, int] = {}
    for field in EXTERNAL_EFFECT_FIELDS:
        value = player.get(field)
        if not isinstance(value, list):
            continue
        for effect in value:
            if not isinstance(effect, dict) or not is_effect_active(effect, now):
                continue
            percents = effect.get("resource_max_percent")
            if isinstance(percents, dict):
                for key, raw in percents.items():
                    totals[str(key)] = totals.get(str(key), 0) + safe_int(raw, 0)
    return totals


def merge_modifier_totals(*sources: dict[str, int]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for source in sources:
        for key, value in (source or {}).items():
            add_modifier(totals, key, value)
    return totals


def equipment_bonus(bonus_modifiers: dict[str, int] | None, key: str) -> int:
    return safe_int((bonus_modifiers or {}).get(key), 0)


def equipment_stat_bonus(equipment_modifiers: dict[str, int], stat_key: str) -> int:
    bonus_key = STAT_EQUIPMENT_BONUS_KEYS.get(stat_key, f"bonus_{stat_key}")
    fallback_key = f"bonus_{stat_key}"
    total = safe_int(equipment_modifiers.get(bonus_key), 0)
    if fallback_key != bonus_key:
        total += safe_int(equipment_modifiers.get(fallback_key), 0)
    return total


def all_bonus_modifiers(player: dict[str, Any]) -> dict[str, int]:
    return merge_modifier_totals(equipment_modifier_totals(player), external_effect_modifier_totals(player), passive_stat_modifiers(player))


def effective_stat(player: dict[str, Any], stat_key: str, bonus_modifiers: dict[str, int] | None = None) -> int:
    base = safe_int((player.get("stats") or {}).get(stat_key), 0)
    invested = safe_int((player.get("invested_stats") or {}).get(stat_key), 0)
    bonus = safe_int((player.get("stat_bonuses") or {}).get(stat_key), 0)
    if bonus_modifiers:
        bonus += equipment_stat_bonus(bonus_modifiers, stat_key)
    invested_total = (base + invested) * stat_multiplier(player, stat_key)
    return int(math.floor(1000 * math.log(1 + invested_total / 1000) + bonus))


def calculate_energy_stats(player: dict[str, Any], bonus_modifiers: dict[str, int] | None = None) -> dict[str, int]:
    bonus_modifiers = bonus_modifiers if bonus_modifiers is not None else all_bonus_modifiers(player)
    base_max_energy = safe_int(
        player.get("base_max_energy", player.get("max_energy_base", player.get("max_energy", 100))),
        100,
    )
    base_max_energy = max(1, base_max_energy)
    bonus_max_energy = safe_int(player.get("bonus_max_energy"), 0) + equipment_bonus(bonus_modifiers, "bonus_max_energy")
    max_energy = max(1, base_max_energy + bonus_max_energy)
    current = safe_int(player.get("current_energy", player.get("energy", max_energy)), max_energy)
    current = max(0, min(max_energy, current))
    return {
        "base_max_energy": base_max_energy,
        "max_energy": max_energy,
        "current_energy": current,
        "bonus_max_energy": bonus_max_energy,
    }


def calculate_player_derived_stats(player: dict[str, Any]) -> dict[str, int]:
    prune_expired_effects(player)
    level = max(1, safe_int(player.get("level"), 1))
    s_level = soft_level(level)
    bonus_modifiers = all_bonus_modifiers(player)

    strength = effective_stat(player, "strength", bonus_modifiers)
    endurance = effective_stat(player, "endurance", bonus_modifiers)
    dexterity = effective_stat(player, "dexterity", bonus_modifiers)
    perception = effective_stat(player, "perception", bonus_modifiers)
    intelligence = effective_stat(player, "intelligence", bonus_modifiers)
    wisdom = effective_stat(player, "wisdom", bonus_modifiers)

    armor = max(0, safe_int(player.get("armor"), 0) + equipment_bonus(bonus_modifiers, "armor"))
    base_magic_armor = safe_int(player.get("magic_armor"), 0)
    magic_armor = max(0, base_magic_armor + equipment_bonus(bonus_modifiers, "magic_armor"))

    bonus_hp = safe_int(player.get("bonus_hp"), 0) + equipment_bonus(bonus_modifiers, "bonus_hp")
    bonus_spirit = safe_int(player.get("bonus_spirit"), 0) + equipment_bonus(bonus_modifiers, "bonus_spirit")
    bonus_mana = safe_int(player.get("bonus_mana"), 0) + equipment_bonus(bonus_modifiers, "bonus_mana")
    bonus_accuracy = safe_int(player.get("bonus_accuracy"), 0) + equipment_bonus(bonus_modifiers, "bonus_accuracy")
    bonus_dodge = safe_int(player.get("bonus_dodge"), 0) + equipment_bonus(bonus_modifiers, "bonus_dodge")
    bonus_physical_defense = safe_int(player.get("bonus_physical_defense"), 0) + equipment_bonus(bonus_modifiers, "bonus_physical_defense")
    bonus_magic_defense = safe_int(player.get("bonus_magic_defense"), 0) + equipment_bonus(bonus_modifiers, "bonus_magic_defense")
    bonus_crit_chance = safe_int(player.get("bonus_crit_chance"), 0) + equipment_bonus(bonus_modifiers, "bonus_crit_chance")
    bonus_crit_damage = safe_int(player.get("bonus_crit_damage"), 0) + equipment_bonus(bonus_modifiers, "bonus_crit_damage")

    max_hp = ceil((100 + endurance * 4.0 + strength * 0.8 + s_level * 4 + bonus_hp) * hp_multiplier(player))
    max_spirit = ceil(20 + endurance * 1.2 + strength * 1.0 + dexterity * 0.7 + s_level * 1.2 + bonus_spirit)
    max_mana = ceil(20 + intelligence * 1.6 + wisdom * 1.3 + s_level * 1.2 + bonus_mana)
    # Временные %-баффы к максимуму ресурсов от расходников (кристаллы маны/духа/жизни).
    resource_percent = active_resource_max_percent(player)
    if resource_percent:
        max_hp = max(1, ceil(max_hp * (1 + safe_int(resource_percent.get("max_hp"), 0) / 100)))
        max_spirit = max(0, ceil(max_spirit * (1 + safe_int(resource_percent.get("max_spirit"), 0) / 100)))
        max_mana = max(0, ceil(max_mana * (1 + safe_int(resource_percent.get("max_mana"), 0) / 100)))
    physical_defense = ceil(armor * 1.5 + endurance * 0.9 + strength * 0.6 + dexterity * 0.2 + bonus_physical_defense)
    # Магическая защита теперь строится от общей брони, эффективной мудрости,
    # интеллекта, выносливости и прямого бонуса магической защиты.
    # Отдельная ``magic_armor`` остаётся отображаемым/бонусным параметром, но не
    # подменяет формулу защиты в бою и профиле.
    magic_defense = ceil(armor * 1.5 + wisdom * 0.9 + intelligence * 0.6 + endurance * 0.2 + bonus_magic_defense)
    accuracy = ceil(perception * 1.8 + dexterity * 1.1 + s_level * 0.7 + bonus_accuracy)
    dodge = ceil(dexterity * 1.8 + perception * 0.9 + wisdom * 0.3 + s_level * 0.5 + bonus_dodge)
    crit_stat = ceil(perception * 1.5 + dexterity * 0.8 + wisdom * 0.2 + s_level * 0.2 + bonus_crit_chance)
    crit_chance_percent = ceil(min(0.49, crit_stat / (crit_stat + 5000)) * 100)
    crit_damage_percent = max(100, ceil(100 + bonus_crit_damage))

    energy = calculate_energy_stats(player, bonus_modifiers)

    result = {
        "level": level,
        "soft_level": s_level,
        "max_hp": max(1, max_hp),
        "max_spirit": max(0, max_spirit),
        "max_mana": max(0, max_mana),
        "armor": armor,
        "magic_armor": max(0, magic_armor),
        "physical_defense": max(0, physical_defense),
        "magic_defense": max(0, magic_defense),
        "accuracy": max(1, accuracy),
        "dodge": max(1, dodge),
        "crit_chance_percent": max(0, crit_chance_percent),
        "crit_damage_percent": crit_damage_percent,
        "max_energy": energy["max_energy"],
        "current_energy": energy["current_energy"],
        "base_max_energy": energy["base_max_energy"],
        "bonus_max_energy": energy["bonus_max_energy"],
        "strength": strength,
        "endurance": endurance,
        "dexterity": dexterity,
        "perception": perception,
        "intelligence": intelligence,
        "wisdom": wisdom,
        "bonus_modifiers": bonus_modifiers,
    }
    # Откат боевого стимулятора и «Зависимость» применяются как процентные
    # модификаторы поверх итоговых статов (активный бафф считается в бою).
    from services.battle_stimulant_service import apply_percent_modifiers_to_stats
    apply_percent_modifiers_to_stats(player, result)
    return result


def skill_damage_type_key(skill: dict[str, Any]) -> str:
    raw = str(skill.get("damage_type") or skill.get("damageType") or "physical").casefold()
    if "маг" in raw or raw in {"magic", "magical"}:
        return "magic"
    if "mixed" in raw or "смеш" in raw:
        return "mixed"
    return "physical"


def calculate_player_skill_raw_damage(player: dict[str, Any], skill: dict[str, Any]) -> dict[str, Any]:
    """Calculate the same pre-defense skill damage for profile preview and PVE.

    The returned damage is the raw value before target defense, hit and critical
    checks. This is exactly what PVE uses before applying the target mitigation.
    """

    if not isinstance(skill, dict):
        return {"damage": None, "damage_type": "physical", "name": "навыком"}

    stats = calculate_player_derived_stats(player)
    level = stats["level"]
    damage_type = skill_damage_type_key(skill)
    formula = str(skill.get("base_damage_formula") or skill.get("damage_formula") or "")
    skill_id = str(skill.get("id") or "")
    skill_name = str(skill.get("name") or "навыком")
    damage_value = skill.get("damage")

    formula_damage = None
    if skill.get("damage_formula_id"):
        from services.formula_runtime import evaluate, numeric_context
        formula_damage = evaluate(skill.get("damage_formula_id"), numeric_context({
            "base_amount": damage_value if isinstance(damage_value, (int, float)) else 1,
            "player_level": level, "item_level": skill_level(skill),
            "strength": stats.get("strength", 0), "agility": stats.get("agility", 0),
            "intelligence": stats.get("intelligence", 0), "wisdom": stats.get("wisdom", 0),
        }, player=player), default=None)
        if formula_damage is not None:
            damage_value = float(formula_damage)

    attribute_profile = skill.get("attribute_profile") if isinstance(skill.get("attribute_profile"), dict) else {}
    if formula_damage is not None:
        base_damage = float(formula_damage)
    elif attribute_profile:
        profile_power = skill_profile_power(stats, attribute_profile)
        role_coefficient = float(skill.get("role_coefficient") or 0.5)
        base_damage = profile_power + soft_level(level) * role_coefficient
        base_damage *= 1 + math.log(skill_level(skill) + 1) * 0.12
        base_damage *= skill_modifier_multiplier(skill)
        base_damage *= passive_skill_multiplier(player, skill, "damage")
    elif skill_id in {"magic_spark", "neutral_magic_clot"} or "magic_spark" in formula or "магический сгусток" in skill_name.casefold():
        base_damage = 4 + level * 1.1 + stats["intelligence"] * 0.8
    elif skill_id in {"basic_attack", "neutral_basic_strike"} or "basic_attack" in formula or "обычный удар" in skill_name.casefold():
        base_damage = 5 + level * 1.2 + stats["strength"] * 0.8
    elif isinstance(damage_value, (int, float)):
        base_damage = float(damage_value)
    elif contains_formula_text(damage_value) or contains_formula_text(formula):
        return {"damage": None, "damage_type": damage_type, "name": skill_name}
    else:
        parsed = modifier_amount(damage_value)
        base_damage = float(parsed) if parsed > 0 else 1.0

    if skill.get("level_power_formula_id"):
        from services.formula_runtime import evaluate, numeric_context
        base_damage = float(evaluate(skill.get("level_power_formula_id"), numeric_context({
            "base_amount": base_damage, "player_level": level,
            "item_level": skill_level(skill), "multiplier": skill_modifier_multiplier(skill),
        }, player=player), default=base_damage))

    bonus_modifiers = stats.get("bonus_modifiers") or {}
    bonus_damage = equipment_bonus(bonus_modifiers, "bonus_damage")
    if damage_type == "magic":
        bonus_damage += equipment_bonus(bonus_modifiers, "bonus_magic_damage")
    elif damage_type == "physical":
        bonus_damage += equipment_bonus(bonus_modifiers, "bonus_physical_damage")
    elif damage_type == "mixed":
        bonus_damage += max(
            equipment_bonus(bonus_modifiers, "bonus_physical_damage"),
            equipment_bonus(bonus_modifiers, "bonus_magic_damage"),
        )

    raw_damage = ceil(base_damage + bonus_damage)
    raw_damage = ceil(raw_damage * outgoing_damage_multiplier(player, damage_type))
    # «Зависимость» от боевого стимулятора слегка меняет базовый урон навыков
    # (активный +30% применяется боевым движком отдельно, не здесь).
    from services.battle_stimulant_service import skill_damage_multiplier
    raw_damage = ceil(raw_damage * skill_damage_multiplier(player))
    return {"damage": max(1, raw_damage), "damage_type": damage_type, "name": skill_name}


def ensure_player_resources(player: dict[str, Any]) -> dict[str, int]:
    prune_expired_effects(player)
    stats = calculate_player_derived_stats(player)
    for current_key, max_key in (("hp", "max_hp"), ("spirit", "max_spirit"), ("mana", "max_mana")):
        max_value = stats[max_key]
        player[max_key] = max_value
        if player.get(current_key) is None:
            player[current_key] = max_value
        player[current_key] = max(0, min(max_value, safe_int(player.get(current_key), max_value)))

    # Keep energy current fields in sync with the effective cap, but never write
    # temporary equipment/effect bonuses into player["max_energy"]. This prevents
    # max_energy from growing every time food is used while bonus_max_energy is active.
    player["energy"] = stats["current_energy"]
    player["current_energy"] = stats["current_energy"]
    return stats
