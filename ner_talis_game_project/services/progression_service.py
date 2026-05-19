"""Character experience and level-up helpers."""

from __future__ import annotations

import math
from typing import Any

from services.race_bonus_service import experience_multiplier


def experience_to_next_level(level: int) -> int:
    level = max(1, int(level or 1))
    return max(100, level * 100)


def grant_experience(player: dict[str, Any], base_amount: int) -> dict[str, int]:
    """Grant experience, apply race bonus and process level-ups.

    ``player["experience"]`` is the current progress inside the current level.
    ``player["total_experience"]`` keeps the lifetime total for future rating
    and audit views.
    """

    base_amount = max(0, int(base_amount or 0))
    gained = max(0, int(math.ceil(base_amount * experience_multiplier(player))))
    if gained <= 0:
        player["experience_to_next"] = experience_to_next_level(int(player.get("level") or 1))
        return {"gained": 0, "levels_gained": 0}

    level = max(1, int(player.get("level") or 1))
    current = max(0, int(player.get("experience") or 0)) + gained
    player["total_experience"] = max(0, int(player.get("total_experience") or 0)) + gained

    levels_gained = 0
    while current >= experience_to_next_level(level):
        current -= experience_to_next_level(level)
        level += 1
        levels_gained += 1

    if levels_gained:
        player["level"] = level
        player["free_stat_points"] = max(0, int(player.get("free_stat_points") or 0)) + levels_gained * 5
        player["free_skill_points"] = max(0, int(player.get("free_skill_points") or 0)) + levels_gained

    player["experience"] = current
    player["experience_to_next"] = experience_to_next_level(level)
    return {"gained": gained, "levels_gained": levels_gained}
