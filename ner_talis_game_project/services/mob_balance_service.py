"""Тестовый бой и баланс-проверка моба (ТЗ «Конструктор мобов» §28–§30).

Лёгкий Monte-Carlo симулятор дуэли «моб против тестового игрока» поверх чистых
боевых формул (pve_battle_models): он НЕ запускает реальный игровой бой и ничего
не меняет в профиле — это админ-инструмент оценки баланса до публикации.

Симуляция упрощена (обмен базовыми атаками с учётом точности/уклонения/защиты/
крита); цель — относительные метрики (шанс победы, средняя длительность, средний
урон) и предупреждения баланса, а не точная копия боевого ядра.
"""

from __future__ import annotations

import random
from typing import Any

from services.pve_battle_models import apply_defense, calculate_hit_chance

TURN_CAP = 60  # защита от бесконечной дуэли


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def default_player_stats(level: int = 1) -> dict[str, float]:
    """Грубый эталонный игрок уровня ``level`` (можно переопределить в запросе)."""
    level = max(1, int(level))
    return {
        "level": level,
        "hp": 80 + level * 20,
        "damage": 10 + level * 4,
        "accuracy": 20 + level * 3,
        "evasion": 10 + level * 2,
        "phys_defense": 5 + level * 3,
        "mag_defense": 5 + level * 2,
        "crit_chance": 5,
        "crit_damage": 50,
    }


def _attack(attacker: dict[str, float], defender: dict[str, float], rng: random.Random) -> int:
    """Один удар: попадание → урон с учётом защиты и крита. 0 — промах."""
    hit_chance = calculate_hit_chance(int(_num(attacker.get("accuracy"), 1) or 1), int(_num(defender.get("evasion"), 1)))
    if rng.random() > hit_chance:
        return 0
    raw = max(1, int(_num(attacker.get("damage"), 1)))
    soft_level = int(_num(defender.get("level"), 1))
    damage = apply_defense(raw, int(_num(defender.get("phys_defense"), 0)), soft_level)
    crit_chance = _num(attacker.get("crit_chance"), 0)
    if crit_chance > 0 and rng.uniform(0, 100) <= crit_chance:
        damage = max(1, int(damage * (1 + _num(attacker.get("crit_damage"), 50) / 100.0)))
    return max(1, damage)


def mob_combat_stats(mob_data: dict[str, Any]) -> dict[str, float]:
    """Боевой профиль моба из карточки конструктора (физ. ветка)."""
    phys = _num(mob_data.get("phys_damage"))
    mag = _num(mob_data.get("mag_damage"))
    return {
        "level": _num(mob_data.get("max_level"), _num(mob_data.get("min_level"), 1)) or 1,
        "hp": max(1, _num(mob_data.get("hp"), 1)),
        "damage": max(1, phys + mag),
        "accuracy": _num(mob_data.get("accuracy"), 1) or 1,
        "evasion": _num(mob_data.get("evasion"), 0),
        "phys_defense": _num(mob_data.get("phys_defense"), 0),
        "mag_defense": _num(mob_data.get("mag_defense"), 0),
        "crit_chance": _num(mob_data.get("crit_chance"), 0),
        "crit_damage": _num(mob_data.get("crit_damage"), 50),
    }


def simulate_battle(mob_data: dict[str, Any], player_stats: dict[str, Any] | None = None, *, count: int = 200, rng: random.Random | None = None) -> dict[str, Any]:
    """Прогнать ``count`` дуэлей и вернуть агрегированные метрики (ТЗ §28)."""
    rng = rng or random.Random()
    count = max(1, min(5000, int(count)))
    mob = mob_combat_stats(mob_data)
    player = {**default_player_stats(int(_num((player_stats or {}).get("level"), 1)))}
    player.update({k: _num(v) for k, v in (player_stats or {}).items() if v not in (None, "")})

    wins = 0
    deaths = 0
    total_turns = 0
    total_mob_damage = 0.0
    total_player_damage = 0.0
    one_shot_seen = False

    for _ in range(count):
        php = player["hp"]
        mhp = mob["hp"]
        turns = 0
        while turns < TURN_CAP:
            turns += 1
            dealt = _attack(player, mob, rng)
            mhp -= dealt
            total_player_damage += dealt
            if mhp <= 0:
                wins += 1
                break
            taken = _attack(mob, player, rng)
            php -= taken
            total_mob_damage += taken
            if taken >= player["hp"]:
                one_shot_seen = True
            if php <= 0:
                deaths += 1
                break
        total_turns += turns

    win_rate = wins / count
    avg_turns = total_turns / count
    return {
        "simulations": count,
        "winRate": round(win_rate, 3),
        "deathRate": round(deaths / count, 3),
        "avgTurns": round(avg_turns, 2),
        "avgMobDamagePerTurn": round(total_mob_damage / max(1, total_turns), 2),
        "avgPlayerDamagePerTurn": round(total_player_damage / max(1, total_turns), 2),
        "avgExp": round(_num(mob_data.get("experience")) * win_rate, 1),
        "avgCoins": round(_num(mob_data.get("coins")) * win_rate, 1),
        "player": player,
        "mob": mob,
        "warnings": balance_warnings(mob_data, win_rate, avg_turns, one_shot_seen),
    }


def balance_warnings(mob_data: dict[str, Any], win_rate: float, avg_turns: float, one_shot: bool) -> list[str]:
    """Предупреждения баланса по результатам теста (ТЗ §30)."""
    warnings: list[str] = []
    if win_rate < 0.2:
        warnings.append("Моб слишком сильный: эталонный игрок почти не побеждает.")
    if win_rate > 0.98:
        if _num(mob_data.get("experience")) > 0 or _num(mob_data.get("coins")) > 0:
            warnings.append("Моб слишком слабый для своей награды.")
        else:
            warnings.append("Моб почти не представляет угрозы.")
    if avg_turns > 30:
        warnings.append("Бой слишком долгий — проверьте HP и урон.")
    if one_shot:
        warnings.append("Моб способен убить эталонного игрока за один ход.")
    return warnings
