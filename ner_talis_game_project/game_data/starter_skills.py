"""Starter non-upgradeable skills for every new Ner-Talis character."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

STARTER_SKILLS: dict[str, list[dict[str, Any]]] = {
    "active": [
        {
            "id": "basic_attack",
            "name": "Обычный удар",
            "level": 0,
            "skill_type": "active",
            "category": "Физическая атака ближнего боя",
            "resource_branch": "neutral",
            "upgradeable": False,
            "has_modifiers": False,
            "cooldown_turns": 0,
            "target": "1 противник",
            "spirit_cost": 0,
            "mana_cost": 0,
            "damage_type": "physical",
            "base_damage_formula": "ceil(5 + player_level * 1.2)",
            "damage": "5 + уровень персонажа × 1.2",
            "uses_hit_check": True,
            "can_crit": True,
            "crit_type": "physical",
            "defense_type": "physical_defense",
            "description": "Урон зависит от уровня персонажа.",
        },
        {
            "id": "magic_spark",
            "name": "Магический сгусток",
            "level": 0,
            "skill_type": "active",
            "category": "Магическая атака",
            "resource_branch": "neutral",
            "upgradeable": False,
            "has_modifiers": False,
            "cooldown_turns": 0,
            "target": "1 противник",
            "spirit_cost": 0,
            "mana_cost": 2,
            "damage_type": "magic",
            "base_damage_formula": "ceil(4 + player_level * 1.1)",
            "damage": "5 + уровень персонажа × 1.4",
            "uses_hit_check": True,
            "can_crit": True,
            "crit_type": "magic",
            "defense_type": "magic_defense",
            "description": "Урон зависит от уровня персонажа.",
        },
    ],
    "passive": [],
}


def get_starter_skills() -> dict[str, list[dict[str, Any]]]:
    return deepcopy(STARTER_SKILLS)
