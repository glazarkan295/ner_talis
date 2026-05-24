"""Level and experience progression helpers."""

from __future__ import annotations

import math
from typing import Any

from services.race_bonus_service import experience_multiplier


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def experience_to_next_level(level: int) -> int:
    return max(100, safe_int(level, 1) * 100)


def grant_experience(player: dict[str, Any], base_amount: int) -> dict[str, Any]:
    """Grant experience, process level-ups and return a compact result."""

    base_amount = max(0, safe_int(base_amount, 0))
    gained = int(math.ceil(base_amount * experience_multiplier(player)))
    player["experience"] = max(0, safe_int(player.get("experience"), 0)) + gained
    player["total_experience"] = max(0, safe_int(player.get("total_experience"), 0)) + gained

    level_ups = 0
    while True:
        level = max(1, safe_int(player.get("level"), 1))
        required = experience_to_next_level(level)
        if player["experience"] < required:
            player["experience_to_next"] = required
            break
        player["experience"] -= required
        player["level"] = level + 1
        player["free_stat_points"] = safe_int(player.get("free_stat_points"), 0) + 5
        player["free_skill_points"] = safe_int(player.get("free_skill_points"), 0) + 2
        level_ups += 1

    branch_hint = None
    return {
        "gained": gained,
        "level_ups": level_ups,
        "level": max(1, safe_int(player.get("level"), 1)),
        "experience": safe_int(player.get("experience"), 0),
        "experience_to_next": safe_int(player.get("experience_to_next"), experience_to_next_level(max(1, safe_int(player.get("level"), 1)))),
        "branch_hint": branch_hint,
    }


def apply_death_experience_penalty(player: dict[str, Any], percent: int = 10) -> dict[str, int]:
    """Remove a percentage of the level's required experience after death.

    Default death penalty is 10% of the maximum experience available on the
    player's current level, not 10% of the currently filled progress bar. The
    penalty never lowers the player's level and never drops current experience
    below zero. ``total_experience`` stays as lifetime earned experience and is
    not reduced.
    """

    percent = max(0, safe_int(percent, 0))
    current = max(0, safe_int(player.get("experience"), 0))
    level = max(1, safe_int(player.get("level"), 1))
    required = experience_to_next_level(level)
    lost = 0 if current <= 0 or percent <= 0 else max(1, math.ceil(required * percent / 100))
    lost = min(current, lost)
    player["experience"] = max(0, current - lost)
    player["experience_to_next"] = required
    player["last_death_experience_penalty"] = lost
    return {
        "lost": lost,
        "percent": percent,
        "base_experience": required,
        "experience": safe_int(player.get("experience"), 0),
        "experience_to_next": safe_int(player.get("experience_to_next"), required),
    }
