"""Runtime helpers for race bonuses used by combat, profile, crafting and exploration."""

from __future__ import annotations

import math
import random
from typing import Any


UNDEAD_RESISTED_EFFECTS = {"poison", "bleed", "stun", "curse", "яд", "кровотечение", "оглушение", "проклятие"}
METAL_CRAFT_TYPES = {"weapon", "armor", "equipment", "blacksmithing", "оружие", "броня", "снаряжение", "кузнечное дело"}


def race_id(player: dict[str, Any]) -> str:
    return str(player.get("race_id") or "").casefold()


def stat_multiplier(player: dict[str, Any], stat_key: str) -> float:
    race = race_id(player)
    if race == "human":
        return 1.01
    if race == "dwarf" and stat_key == "endurance":
        return 1.03
    return 1.0


def hp_multiplier(player: dict[str, Any]) -> float:
    return 1.04 if race_id(player) == "undead" else 1.0


def experience_multiplier(player: dict[str, Any]) -> float:
    return 1.02 if race_id(player) == "human" else 1.0


def npc_purchase_refund_amount(player: dict[str, Any], spent_copper: int, rng: random.Random | None = None) -> int:
    """Human racial bonus: 5% chance to refund 3% of an NPC purchase."""

    if race_id(player) != "human" or spent_copper <= 0:
        return 0
    rng = rng or random.Random()
    if rng.uniform(0, 100) > 5:
        return 0
    return max(1, int(math.ceil(spent_copper * 0.03)))


def outgoing_damage_multiplier(player: dict[str, Any], damage_type: str) -> float:
    if race_id(player) == "elf" and str(damage_type).casefold() == "magic":
        return 1.03
    return 1.0


def alchemy_quality_chance_bonus_percent(player: dict[str, Any]) -> int:
    return 4 if race_id(player) == "elf" else 0


def extra_alchemy_ingredient_chance_percent(player: dict[str, Any]) -> int:
    return 3 if race_id(player) == "elf" else 0


def crafting_quality_chance_bonus_percent(player: dict[str, Any], craft_type: str) -> int:
    craft = str(craft_type or "").casefold()
    if race_id(player) == "dwarf" and craft in METAL_CRAFT_TYPES:
        return 4
    return 0


def metal_material_cost_multiplier(player: dict[str, Any], craft_type: str) -> float:
    craft = str(craft_type or "").casefold()
    if race_id(player) == "dwarf" and craft in METAL_CRAFT_TYPES:
        return 0.97
    return 1.0


def effect_resistance_bonus_percent(player: dict[str, Any], effect_type: str) -> int:
    effect = str(effect_type or "").casefold()
    if race_id(player) == "undead" and effect in UNDEAD_RESISTED_EFFECTS:
        return 5
    return 0


def incoming_periodic_damage_multiplier(player: dict[str, Any]) -> float:
    return 0.97 if race_id(player) == "undead" else 1.0


def incoming_physical_damage_multiplier(player: dict[str, Any]) -> float:
    return 0.98 if race_id(player) == "lizardfolk" else 1.0


def combat_hp_regen_percent(player: dict[str, Any]) -> float:
    return 0.5 if race_id(player) == "lizardfolk" else 0.0


def search_event_weights(player: dict[str, Any], base_weights: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Return race-adjusted exploration weights while keeping integer weights."""

    race = race_id(player)
    weights = {key: int(value) for key, value in base_weights}

    if race == "elf":
        weights["alchemy_ingredient"] = weights.get("alchemy_ingredient", 0) + 3
        weights["trap"] = max(1, weights.get("trap", 0) - 1)
        weights["battle"] = max(1, weights.get("battle", 0) - 2)

    if race == "lizardfolk":
        for key in ("alchemy_ingredient", "stone_or_ore", "berries"):
            if key in weights:
                weights[key] += 1
        weights["trap"] = max(1, weights.get("trap", 0) - 1)
        weights["battle"] = max(1, weights.get("battle", 0) - 3)

    return [(key, max(1, weights[key])) for key, _value in base_weights]
