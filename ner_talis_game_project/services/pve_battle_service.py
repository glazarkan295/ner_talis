"""Runnable PVE battle service for Telegram/VK exploration events.

The module integrates the uploaded PVE battle data structures into the existing
project. It keeps the first implementation intentionally compact: random PVE
encounters in external locations become real turn-based battles, but the API is
stable enough to later replace damage/AI/skill formulas with the full combat
system.
"""

from __future__ import annotations

import logging
import math
import random
import uuid
from dataclasses import asdict
from typing import Any

logger = logging.getLogger(__name__)

from services.derived_stats_service import calculate_player_derived_stats, calculate_player_skill_raw_damage, ensure_player_resources, safe_int, soft_level
from services.item_registry import build_inventory_item, get_item_definition_by_id, get_item_definition_by_name
from services.inventory_service import add_inventory_item as add_inventory_stack, apply_generated_item_level_and_price, inventory_add_result_notice, recalculate_inventory_overflow
from services.progression_service import apply_death_experience_penalty, grant_experience
from services.active_skill_service import (
    consume_skill_ammo,
    resource_cost_with_modifiers,
    is_skill_weapon_compatible,
    skill_weapon_requirement_text,
    validate_skill_ammo,
    normalize_starter_only_skills,
)
from services.pve_battle_models import (
    BattleState,
    DamageSplit,
    DamageType,
    EnemyBattleState,
    EnemyRank,
    PlayerBattleState,
    calculate_final_damage,
    calculate_hit_chance,
)
from services.race_bonus_service import (
    combat_hp_regen_percent,
    hp_multiplier,
    incoming_physical_damage_multiplier,
    outgoing_damage_multiplier,
    stat_multiplier,
)

BATTLE_ATTACK = "Обычная атака"
BATTLE_MAGIC_SPARK = "Магический сгусток"
BATTLE_DEFEND = "Защита"
BATTLE_POUCH = "Подсумок"
BATTLE_ESCAPE = "Сбежать"
BATTLE_WAIT = "Ждать"
BATTLE_POUCH_PAGE_SIZE = 8
BATTLE_POUCH_NEXT = "Подсумок далее"
BATTLE_POUCH_PREV = "Подсумок назад"
BATTLE_POUCH_ITEM_PREFIX = "Предмет "
BATTLE_THROW_TARGET_PROMPT = "Выберите цель для расходника"
OLD_IRON_SWORD_IDS = {"old_iron_sword"}
TARGETED_POUCH_EFFECTS = {"throw_damage"}


# В интерфейсе боя показываются только подсумок, побег и экипированные активные навыки.
# Обычная атака и защита оставлены как внутренние fallback-действия для старых сохранений.
BATTLE_ACTIONS = frozenset({
    BATTLE_POUCH,
    BATTLE_POUCH_NEXT,
    BATTLE_POUCH_PREV,
    BATTLE_ESCAPE,
    BATTLE_WAIT,
    "Отступить",
})


def base_battle_buttons(player: dict[str, Any] | None = None) -> list[list[str]]:
    if isinstance(player, dict) and player.get("inventory_overflow_no_escape"):
        return [[BATTLE_POUCH, BATTLE_WAIT], ["Побег недоступен"]]
    return [[BATTLE_POUCH, BATTLE_ESCAPE], [BATTLE_WAIT]]

RANK_MULTIPLIERS = {
    EnemyRank.NORMAL: {"hp": 1.0, "damage": 1.0, "accuracy": 1.0, "dodge": 1.0, "defense": 1.0, "xp": 1.0},
    EnemyRank.EMPOWERED: {"hp": 1.5, "damage": 1.42, "accuracy": 1.22, "dodge": 1.1, "defense": 1.28, "xp": 1.7},
    EnemyRank.ELITE: {"hp": 2.3, "damage": 1.85, "accuracy": 1.35, "dodge": 1.2, "defense": 1.6, "xp": 3.2},
}

ENEMY_RANK_LABELS = {
    "normal": "обычный",
    "empowered": "усиленный",
    "elite": "элитный",
    "mini_boss": "мини-босс",
    "boss": "босс",
    "raid_boss": "рейдовый босс",
}

DAMAGE_TYPE_LABELS = {
    "physical": "физический",
    "magic": "магический",
    "mixed": "смешанный",
}

HILLY_MEADOWS_MOBS = {
    "overgrown_gopher": {
        "name": "Суслик-переросток",
        "biological_type": "beast",
        "role": "small_pack_attacker",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (2, 4), EnemyRank.EMPOWERED: (2, 3), EnemyRank.ELITE: (1, 1)},
        "skills": ["Укус", "Рывок из норы"],
        "features": ["Стайный инстинкт"],
        "text": "Земля впереди начинает шевелиться. Из нор выбираются крупные суслики с непропорционально большими зубами.",
        "loot": [
            ("Простая шкура", 60, 1, 1),
            ("Маленький кусок сырого мяса", 45, 1, 1),
            ("Простой клык", 20, 1, 1),
            ("Простой коготь", 10, 1, 1),
        ],
    },
    "wild_jackal": {
        "name": "Дикий шакал",
        "biological_type": "beast",
        "role": "fast_attacker",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 2), EnemyRank.EMPOWERED: (1, 2), EnemyRank.ELITE: (1, 1)},
        "skills": ["Укус", "Рывок"],
        "features": ["Прыжок хищника"],
        "text": "Из-за холма доносится низкое рычание. Из травы выходят дикие шакалы, отрезая путь назад.",
        "loot": [
            ("Простая шкура", 65, 1, 1),
            ("Сырое мясо", 55, 1, 2),
            ("Простой клык", 25, 1, 1),
            ("Сухожилия", 20, 1, 1),
        ],
    },
    "rabid_rabbit": {
        "name": "Бешеный кролик",
        "biological_type": "beast",
        "role": "single_fast_attacker",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 1), EnemyRank.EMPOWERED: (1, 1), EnemyRank.ELITE: (1, 1)},
        "skills": ["Резкий прыжок", "Укус"],
        "features": ["Прыжок хищника"],
        "text": "Из высокой травы выскакивает кролик. Мутные глаза и пена у пасти быстро меняют первое впечатление.",
        "loot": [
            ("Простая шкура", 55, 1, 1),
            ("Сырое мясо", 45, 1, 1),
            ("Простой клык", 18, 1, 1),
        ],
    },
    "hill_bull": {
        "name": "Бык",
        "biological_type": "beast",
        "role": "heavy_defender",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 1), EnemyRank.EMPOWERED: (1, 1), EnemyRank.ELITE: (1, 1)},
        "skills": ["Удар рогами", "Тяжёлый рывок"],
        "features": ["Толстая шкура"],
        "text": "На соседнем склоне пасётся огромный бык. Зверь резко поднимает голову и начинает рыть землю копытом.",
        "loot": [
            ("Простая шкура", 80, 1, 1),
            ("Сырое мясо", 85, 2, 3),
            ("Бычий рог", 30, 1, 1),
            ("Сухожилия", 35, 1, 1),
        ],
        "hp_base": 85,
        "hp_per_level": 16,
        "armor_factor": 2.6,
        "dodge_per_level": 0.75,
        "damage_bonus_per_level": 1.8,
    },
}


HILLY_MEADOWS_MOB_WEIGHTS = {
    EnemyRank.NORMAL: [("overgrown_gopher", 40), ("rabid_rabbit", 35), ("wild_jackal", 25)],
    "empowered_early": [("overgrown_gopher", 40), ("rabid_rabbit", 35), ("wild_jackal", 25)],
    EnemyRank.EMPOWERED: [("wild_jackal", 35), ("overgrown_gopher", 30), ("rabid_rabbit", 25), ("hill_bull", 10)],
    EnemyRank.ELITE: [("hill_bull", 100)],
}

ORDINARY_FOREST_MOBS = {
    "forest_wolf": {
        "name": "Волк",
        "biological_type": "beast",
        "role": "attacker",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (2, 5), EnemyRank.EMPOWERED: (2, 4), EnemyRank.ELITE: (1, 1)},
        "skills": ["Укус", "Рывок", "Стайный натиск"],
        "features": ["Окружение"],
        "text": "Из-за деревьев доносится протяжный вой. Через несколько мгновений из тени выходят волки. Они медленно расходятся в стороны, пытаясь окружить вас.",
        "loot": [("Сырое мясо", 60, 1, 2), ("Простая шкура", 65, 1, 1), ("Простой клык", 25, 1, 1), ("Сухожилия", 20, 1, 1)],
        "hp_base": 34,
        "hp_per_level": 9,
        "armor_factor": 1.1,
        "dodge_per_level": 1.9,
    },
    "angry_deer": {
        "name": "Разъярённый олень",
        "biological_type": "beast",
        "role": "attacker",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 1), EnemyRank.EMPOWERED: (1, 1), EnemyRank.ELITE: (1, 1)},
        "skills": ["Удар рогами", "Резкий рывок"],
        "features": ["Защита территории"],
        "text": "На небольшой прогалине вы замечаете оленя. Он резко опускает голову, выставляет рога и начинает бить копытом землю.",
        "loot": [("Сырое мясо", 70, 1, 2), ("Простая шкура", 60, 1, 1), ("Оленьи рога", 30, 1, 1), ("Сухожилия", 25, 1, 1)],
        "hp_base": 42,
        "hp_per_level": 10,
        "armor_factor": 1.0,
        "dodge_per_level": 2.0,
    },
    "forest_boar": {
        "name": "Кабан",
        "biological_type": "beast",
        "role": "defender",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 3), EnemyRank.EMPOWERED: (1, 2), EnemyRank.ELITE: (1, 1)},
        "skills": ["Рывок", "Удар клыками"],
        "features": ["Толстая шкура"],
        "text": "Из кустов раздаётся тяжёлое сопение. На тропу выходит кабан; судя по шуму, вы оказались слишком близко к месту кормёжки.",
        "loot": [("Сырое мясо", 75, 1, 3), ("Простая шкура", 65, 1, 1), ("Простой клык", 30, 1, 1), ("Кусок жира", 25, 1, 1)],
        "hp_base": 55,
        "hp_per_level": 12,
        "armor_factor": 1.8,
        "dodge_per_level": 1.0,
    },
    "forest_bear": {
        "name": "Медведь",
        "biological_type": "beast",
        "role": "defender",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 1), EnemyRank.EMPOWERED: (1, 1), EnemyRank.ELITE: (1, 1)},
        "skills": ["Удар лапой", "Рёв", "Тяжёлый рывок"],
        "features": ["Толстая шкура"],
        "text": "Впереди трескаются ветки. Из-за стволов выходит огромный медведь, поднимается на задние лапы и тяжело рычит.",
        "loot": [("Сырое мясо", 85, 1, 3), ("Простая шкура", 75, 1, 1), ("Простой коготь", 35, 1, 1), ("Простой клык", 30, 1, 1), ("Кусок жира", 25, 1, 1)],
        "hp_base": 115,
        "hp_per_level": 20,
        "armor_factor": 2.8,
        "dodge_per_level": 0.7,
        "damage_bonus_per_level": 2.0,
    },
}


ORDINARY_FOREST_MOB_WEIGHTS = {
    EnemyRank.NORMAL: [("forest_wolf", 34), ("angry_deer", 33), ("forest_boar", 33)],
    "empowered_early": [("forest_wolf", 34), ("angry_deer", 33), ("forest_boar", 33)],
    EnemyRank.EMPOWERED: [("forest_wolf", 25), ("angry_deer", 25), ("forest_boar", 25), ("forest_bear", 25)],
    EnemyRank.ELITE: [("forest_bear", 100)],
}

BATTLE_MOB_CATALOGS = {
    "hilly_meadows": HILLY_MEADOWS_MOBS,
    "ordinary_forest": ORDINARY_FOREST_MOBS,
}

BATTLE_LOOT_ITEM_IDS = {
    "hilly_meadows": {
        "Простая шкура": "simple_hide",
        "Сухожилия": "simple_tendon",
        "Маленький кусок сырого мяса": "meat_piece",
        "Простой клык": "simple_fang",
        "Простой коготь": "simple_claw",
        "Простой клык": "simple_fang",
        "Сырое мясо": "raw_meat",
        "Простой клык": "simple_fang",
        "Бычий рог": "bull_horn",
    },
    "ordinary_forest": {
        "Простая шкура": "simple_hide",
        "Сухожилия": "simple_tendon",
        "Сырое мясо": "raw_meat",
        "Простой клык": "simple_fang",
        "Простой коготь": "simple_claw",
        "Оленьи рога": "deer_antlers",
        "Кусок жира": "fat_piece",
    },
}


def battle_loot_item_id(location_id: str | None, item_name: str) -> str | None:
    return BATTLE_LOOT_ITEM_IDS.get(normalize_battle_location(location_id), {}).get(item_name)


def player_display_name(player: dict[str, Any] | None) -> str:
    if not isinstance(player, dict):
        return "Игрок"
    for key in ("name", "nickname", "display_name", "username", "player_name"):
        value = str(player.get(key) or "").strip()
        if value:
            return value
    return "Игрок"


def battle_player_name(battle: dict[str, Any]) -> str:
    value = str(battle.get("player_name") or "").strip()
    return value or "Игрок"


def format_last_turn_log(battle: dict[str, Any]) -> str:
    entries = [str(entry).strip() for entry in (battle.get("last_turn_log") or battle.get("battle_log", [])[-4:])]
    entries = [entry for entry in entries if entry]
    if not entries:
        return "—"

    player_name = battle_player_name(battle)
    enemy_names = {str(enemy.get("name") or "").strip() for enemy in battle.get("enemies", []) if isinstance(enemy, dict)}
    enemy_names.discard("")
    player_lines: list[str] = []
    enemy_lines: list[str] = []
    other_lines: list[str] = []

    for entry in entries:
        if entry.startswith(player_name) or entry.startswith("🎒") or entry.startswith("🦎"):
            player_lines.append(entry)
        elif any(entry.startswith(name) for name in enemy_names):
            enemy_lines.append(entry)
        else:
            other_lines.append(entry)

    sections: list[str] = []
    if player_lines:
        sections.append(f"🧍 {player_name}:")
        sections.extend(f"• {line}" for line in player_lines)
    if enemy_lines:
        sections.append("👹 Противники:")
        sections.extend(f"• {line}" for line in enemy_lines)
    if other_lines:
        sections.append("📌 Прочее:")
        sections.extend(f"• {line}" for line in other_lines)
    return "\n".join(sections)


def battle_buttons(player: dict[str, Any] | None = None) -> list[list[str]]:
    normalize_starter_only_skills(player) if isinstance(player, dict) else None
    recalculate_inventory_overflow(player) if isinstance(player, dict) else None
    rows = [row[:] for row in base_battle_buttons(player)]
    skills = ((player or {}).get("skills") or {}).get("equipped", []) if isinstance((player or {}).get("skills"), dict) else []
    skill_names = [str(skill.get("name") or skill.get("id")) for skill in skills if isinstance(skill, dict)]
    for index in range(0, len(skill_names), 2):
        rows.append(skill_names[index:index + 2])
    return rows


def is_enemy_alive(enemy: dict[str, Any]) -> bool:
    return safe_int(enemy.get("current_hp"), 0) > 0


def target_buttons(battle: dict[str, Any], player: dict[str, Any] | None = None) -> list[list[str]]:
    """Return target buttons with stable numbers from the battle text.

    Dead enemies stay in the enemy list and keep their text number, so target
    buttons must use original enemy indexes instead of re-numbering alive enemies.
    Example: if enemy 1 is defeated, the next target button is still «Цель: 2».
    """
    target_labels = [
        f"Цель: {index}"
        for index, enemy in enumerate(battle.get("enemies", []), start=1)
        if isinstance(enemy, dict) and is_enemy_alive(enemy)
    ]
    rows = [target_labels] if target_labels else []
    rows.extend(battle_buttons(player))
    return rows


def decrement_cooldowns_at_turn_start(player_state: dict[str, Any]) -> None:
    cooldowns = player_state.setdefault("cooldowns", {})
    if not isinstance(cooldowns, dict):
        player_state["cooldowns"] = cooldowns = {}
    for key in list(cooldowns.keys()):
        cooldowns[key] = max(0, safe_int(cooldowns.get(key), 0) - 1)
        if cooldowns[key] <= 0:
            cooldowns.pop(key, None)


def decrement_cooldowns_once_at_player_turn(battle: dict[str, Any], player_state: dict[str, Any]) -> None:
    """Decrease cooldowns once at the beginning of each player turn."""

    round_number = safe_int(battle.get("round_number"), 1)
    tick_key = "_cooldown_tick_round"
    if safe_int(player_state.get(tick_key), 0) == round_number:
        return
    decrement_cooldowns_at_turn_start(player_state)
    player_state[tick_key] = round_number


def make_player_battle_state(player: dict[str, Any]) -> PlayerBattleState:
    stats = ensure_player_resources(player)
    return PlayerBattleState(
        current_hp=safe_int(player.get("hp"), stats["max_hp"]),
        max_hp=stats["max_hp"],
        current_spirit=safe_int(player.get("spirit"), stats["max_spirit"]),
        max_spirit=stats["max_spirit"],
        current_mana=safe_int(player.get("mana"), stats["max_mana"]),
        max_mana=stats["max_mana"],
        armor=stats["armor"],
        magic_armor=stats["magic_armor"],
        physical_defense=stats["physical_defense"],
        magic_defense=stats["magic_defense"],
        accuracy=stats["accuracy"],
        dodge=stats["dodge"],
        crit_chance=safe_int(stats.get("crit_chance_percent"), 0),
        crit_damage=max(100, safe_int(stats.get("crit_damage_percent"), 100)),
    )




def active_battle_stimulant_bonuses(player: dict[str, Any]) -> tuple[int, int]:
    """Return active inventory-used battle stimulant bonuses.

    The item is consumed from inventory, not the pouch. Active effects are pruned
    by ensure_player_resources before a battle state is created, so the remaining
    effects can be read directly here.
    """

    damage_bonus = 0
    resource_bonus = 0
    effects = player.get("active_effects", [])
    if not isinstance(effects, list):
        return 0, 0
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        if str(effect.get("id") or "") != "effect_battle_stimulant" and str(effect.get("source") or "") != "battle_stimulant":
            continue
        damage_bonus = max(damage_bonus, safe_int(effect.get("combat_damage_bonus_percent"), 0))
        resource_bonus = max(resource_bonus, safe_int(effect.get("resource_max_bonus_percent"), 0))
    return damage_bonus, resource_bonus


def apply_inventory_battle_stimulant_to_battle(player: dict[str, Any], battle: dict[str, Any]) -> None:
    damage_bonus, resource_bonus = active_battle_stimulant_bonuses(player)
    if damage_bonus <= 0 and resource_bonus <= 0:
        return
    player_state = battle.setdefault("player_state", {})
    if damage_bonus > 0:
        player_state["battle_stimulant_active"] = True
        player_state["combat_damage_bonus_percent"] = max(safe_int(player_state.get("combat_damage_bonus_percent"), 0), damage_bonus)
    if resource_bonus > 0 and not player_state.get("_inventory_battle_stimulant_applied"):
        for current_key, max_key in (("current_spirit", "max_spirit"), ("current_mana", "max_mana")):
            base_max = max(1, safe_int(player_state.get(max_key), 1))
            bonus = math.floor(base_max * resource_bonus / 100)
            player_state[max_key] = safe_int(player_state.get(max_key), 0) + bonus
            player_state[current_key] = safe_int(player_state.get(current_key), 0) + bonus
        player_state["_inventory_battle_stimulant_applied"] = True

def normalize_battle_location(location_id: str | None) -> str:
    value = str(location_id or "hilly_meadows")
    if value.endswith("_battle"):
        value = value.removesuffix("_battle")
    if value.endswith("_search"):
        value = value.removesuffix("_search")
    if value.endswith("_camp"):
        value = value.removesuffix("_camp")
    return value if value in BATTLE_MOB_CATALOGS else "hilly_meadows"


def mob_catalog(location_id: str | None) -> dict[str, dict[str, Any]]:
    return BATTLE_MOB_CATALOGS.get(normalize_battle_location(location_id), HILLY_MEADOWS_MOBS)


def battle_return_location(battle: dict[str, Any] | None) -> str:
    if not isinstance(battle, dict):
        return "hilly_meadows"
    return normalize_battle_location(battle.get("return_location") or battle.get("origin_location_id") or battle.get("location_id"))


def move_player_to_battle_return_location(player: dict[str, Any], battle: dict[str, Any]) -> str:
    location_id = battle_return_location(battle)
    player["current_location"] = location_id
    player["current_zone"] = location_id
    player["location_id"] = location_id
    return location_id


def death_camp_buttons() -> list[list[str]]:
    return [["Профиль"], ["Готовка", "Еда"], ["Свернуть лагерь"]]


def move_player_to_death_camp(player: dict[str, Any], battle: dict[str, Any]) -> str:
    """Move the defeated player to the current location camp by default."""

    location_id = battle_return_location(battle)
    player["current_location"] = location_id
    player["current_zone"] = f"{location_id}_camp"
    player["location_id"] = f"{location_id}_camp"
    player["active_timer"] = None
    return location_id


def choose_battle_rank(rng: random.Random, player_level: int = 1, location_id: str = "hilly_meadows") -> EnemyRank:
    location_id = normalize_battle_location(location_id)
    roll = rng.uniform(0, 100)
    if location_id == "ordinary_forest":
        if player_level <= 3:
            if roll <= 76:
                return EnemyRank.NORMAL
            if roll <= 96:
                return EnemyRank.EMPOWERED
            return EnemyRank.ELITE
        if roll <= 66:
            return EnemyRank.NORMAL
        if roll <= 93:
            return EnemyRank.EMPOWERED
        return EnemyRank.ELITE
    if player_level <= 3:
        if roll <= 92:
            return EnemyRank.NORMAL
        return EnemyRank.EMPOWERED
    if roll <= 70:
        return EnemyRank.NORMAL
    if roll <= 94:
        return EnemyRank.EMPOWERED
    return EnemyRank.ELITE


def enemy_level_for_rank(player_level: int, rank: EnemyRank, rng: random.Random, *, cap: int = 50, min_level: int = 1) -> int:
    floor_level = max(1, min_level)
    if player_level <= 3:
        if rank == EnemyRank.NORMAL:
            level = player_level + rng.randint(-1, 0)
        elif rank == EnemyRank.EMPOWERED:
            level = player_level + rng.randint(1, 2)
        else:
            level = player_level + rng.randint(3, 4)
    elif rank == EnemyRank.NORMAL:
        level = player_level + rng.randint(-1, 1)
    elif rank == EnemyRank.EMPOWERED:
        level = player_level + rng.randint(3, 5)
    else:
        level = player_level + rng.randint(7, 9)
    return max(floor_level, min(cap, level))




def weighted_mob_choice(entries: list[tuple[str, int]], rng: random.Random) -> str:
    if not entries:
        return "overgrown_gopher"
    total = sum(max(0, safe_int(weight, 0)) for _key, weight in entries)
    if total <= 0:
        return entries[0][0]
    roll = rng.uniform(0, total)
    current = 0.0
    for key, weight in entries:
        current += max(0, safe_int(weight, 0))
        if roll <= current:
            return key
    return entries[-1][0]

def choose_mob_key(rank: EnemyRank, rng: random.Random, player_level: int = 1, location_id: str = "hilly_meadows") -> str:
    location_id = normalize_battle_location(location_id)
    if location_id == "ordinary_forest":
        if rank == EnemyRank.EMPOWERED and player_level <= 3:
            return weighted_mob_choice(ORDINARY_FOREST_MOB_WEIGHTS["empowered_early"], rng)
        return weighted_mob_choice(ORDINARY_FOREST_MOB_WEIGHTS.get(rank, ORDINARY_FOREST_MOB_WEIGHTS[EnemyRank.NORMAL]), rng)
    if rank == EnemyRank.EMPOWERED and player_level <= 3:
        return weighted_mob_choice(HILLY_MEADOWS_MOB_WEIGHTS["empowered_early"], rng)
    return weighted_mob_choice(HILLY_MEADOWS_MOB_WEIGHTS.get(rank, HILLY_MEADOWS_MOB_WEIGHTS[EnemyRank.NORMAL]), rng)


def build_enemy(mob_key: str, rank: EnemyRank, level: int, index: int, location_id: str = "hilly_meadows") -> EnemyBattleState:
    catalog = mob_catalog(location_id)
    if mob_key not in catalog:
        catalog = HILLY_MEADOWS_MOBS
    template = catalog[mob_key]
    mult = RANK_MULTIPLIERS[rank]
    base_hp = int(template.get("hp_base", 28)) + level * int(template.get("hp_per_level", 8))
    if mob_key == "rabid_rabbit":
        base_hp = 20 + level * 6
    early_hp_multiplier = 1.0
    if level <= 3 and rank == EnemyRank.NORMAL:
        early_hp_multiplier = 0.62 if normalize_battle_location(location_id) == "hilly_meadows" else 0.85
    elif level <= 3 and rank == EnemyRank.EMPOWERED:
        early_hp_multiplier = 0.78 if normalize_battle_location(location_id) == "hilly_meadows" else 0.92
    max_hp = max(1, math.ceil(base_hp * mult["hp"] * early_hp_multiplier))
    armor_factor = float(template.get("armor_factor", 1.0 if mob_key != "hill_bull" else 2.2))
    armor = math.ceil(level * armor_factor * mult["defense"])
    physical_defense = math.ceil(armor * 1.5 + level * 1.4 * mult["defense"])
    # Магическая защита раньше была почти нулевой (level*0.8) — магия игнорировала
    # мобов. Приводим к сопоставимой с физической базе (чуть ниже по коэффициенту).
    magic_defense = math.ceil(armor * 1.5 + level * 0.8 * mult["defense"])
    accuracy = math.ceil((18 + level * 2.1) * mult["accuracy"])
    dodge_per_level = float(template.get("dodge_per_level", 1.7 if mob_key != "hill_bull" else 0.8))
    dodge_base = 14 + level * dodge_per_level
    dodge = math.ceil(dodge_base * mult["dodge"])
    enemy = EnemyBattleState(
        mob_id=f"{mob_key}_{index}_{uuid.uuid4().hex[:6]}",
        name=template["name"],
        rank=rank,
        biological_type=template["biological_type"],
        role=template["role"],
        level=level,
        damage_type=template["damage_type"],
        damage_split=template["damage_split"],
        current_hp=max_hp,
        max_hp=max_hp,
        armor=armor,
        magic_armor=0,
        physical_defense=physical_defense,
        magic_defense=magic_defense,
        accuracy=accuracy,
        dodge=dodge,
        skills=list(template["skills"]),
        features=list(template["features"]),
    )
    enemy.validate_damage_type()
    return enemy


def create_location_battle(player: dict[str, Any], rng: random.Random | None = None, location_id: str | None = None) -> tuple[dict[str, Any], str]:
    normalize_starter_only_skills(player)
    rng = rng or random.Random()
    location_id = normalize_battle_location(location_id or player.get("current_location") or player.get("location_id") or "hilly_meadows")
    player_level = max(1, safe_int(player.get("level"), 1))
    rank = choose_battle_rank(rng, player_level, location_id)
    mob_key = choose_mob_key(rank, rng, player_level, location_id)
    catalog = mob_catalog(location_id)
    template = catalog[mob_key]
    min_count, max_count = template["group"][rank]
    if player_level <= 3:
        min_count = 1
        max_count = 1 if rank != EnemyRank.NORMAL else min(2, max_count)
    count = 1 if rank == EnemyRank.ELITE else rng.randint(min_count, max_count)
    cap = 60 if location_id == "ordinary_forest" else 50
    min_level = 10 if location_id == "ordinary_forest" else 1
    enemies = [
        build_enemy(mob_key, rank, enemy_level_for_rank(player_level, rank, rng, cap=cap, min_level=min_level), index + 1, location_id)
        for index in range(count)
    ]
    battle = BattleState(
        battle_id=f"pve_{uuid.uuid4().hex[:12]}",
        player_id=str(player.get("game_id") or player.get("id") or "player"),
        location_id=location_id,
        battle_type="random_event",
        round_number=1,
        player_state=make_player_battle_state(player),
        enemies=enemies,
        can_escape=True,
        battle_log=[template["text"]],
    )
    battle_dict = serialize_battle(battle)
    apply_inventory_battle_stimulant_to_battle(player, battle_dict)
    battle_dict["origin_location_id"] = location_id
    battle_dict["return_location"] = location_id
    battle_dict["player_name"] = player_display_name(player)
    player["active_battle"] = battle_dict
    player["active_event"] = None
    player["in_battle"] = True
    player["current_location"] = location_id
    player["current_zone"] = f"{location_id}_battle"
    player["location_id"] = f"{location_id}_battle"
    sync_player_from_battle(player, battle_dict)
    return battle_dict, format_battle_started_text(battle_dict)


def create_hilly_meadows_battle(player: dict[str, Any], rng: random.Random | None = None) -> tuple[dict[str, Any], str]:
    return create_location_battle(player, rng, "hilly_meadows")


def serialize_enemy(enemy: EnemyBattleState) -> dict[str, Any]:
    data = asdict(enemy)
    data["rank"] = enemy.rank.value
    data["damage_type"] = enemy.damage_type.value
    return data


def serialize_player_state(state: PlayerBattleState) -> dict[str, Any]:
    return asdict(state)


def serialize_battle(battle: BattleState) -> dict[str, Any]:
    return {
        "battle_id": battle.battle_id,
        "player_id": battle.player_id,
        "location_id": battle.location_id,
        "battle_type": battle.battle_type,
        "round_number": battle.round_number,
        "player_state": serialize_player_state(battle.player_state),
        "enemies": [serialize_enemy(enemy) for enemy in battle.enemies],
        "can_escape": battle.can_escape,
        "battle_log": list(battle.battle_log),
    }


def alive_enemies(battle: dict[str, Any]) -> list[dict[str, Any]]:
    return [enemy for enemy in battle.get("enemies", []) if isinstance(enemy, dict) and is_enemy_alive(enemy)]


def enemy_by_stable_number(battle: dict[str, Any], target_number: int) -> dict[str, Any] | None:
    enemies = battle.get("enemies", [])
    index = target_number - 1
    if not isinstance(enemies, list) or index < 0 or index >= len(enemies):
        return None
    enemy = enemies[index]
    if not isinstance(enemy, dict) or not is_enemy_alive(enemy):
        return None
    return enemy


def enemy_rank(enemy: dict[str, Any]) -> EnemyRank:
    try:
        return EnemyRank(enemy.get("rank") or EnemyRank.NORMAL.value)
    except ValueError:
        return EnemyRank.NORMAL


def enemy_damage_type(enemy: dict[str, Any]) -> DamageType:
    try:
        return DamageType(enemy.get("damage_type") or DamageType.PHYSICAL.value)
    except ValueError:
        return DamageType.PHYSICAL


def enemy_damage_split(enemy: dict[str, Any]) -> DamageSplit:
    split = enemy.get("damage_split") or {}
    return DamageSplit(physical=safe_int(split.get("physical"), 100), magic=safe_int(split.get("magic"), 0))


def enemy_raw_damage(enemy: dict[str, Any]) -> int:
    rank = enemy_rank(enemy)
    mult = RANK_MULTIPLIERS.get(rank, RANK_MULTIPLIERS[EnemyRank.NORMAL])
    level = max(1, safe_int(enemy.get("level"), 1))
    base = 4 + level * 2.25
    name = str(enemy.get("name") or "")
    if name == "Кабан":
        base += level * 0.7

    bonus_by_name = {
        "Бык": 1.8,
        "Медведь": 2.0,
    }
    base += level * bonus_by_name.get(name, 0)
    return max(1, math.ceil(base * mult["damage"]))


def equipped_items(player: dict[str, Any]) -> list[dict[str, Any]]:
    equipment = player.get("equipment") if isinstance(player, dict) else {}
    if not isinstance(equipment, dict):
        return []
    return [item for item in equipment.values() if isinstance(item, dict)]


def has_old_iron_sword_equipped(player: dict[str, Any]) -> bool:
    for item in equipped_items(player):
        identity = item_identity(item)
        name = item_name_value(item).casefold()
        if identity in OLD_IRON_SWORD_IDS or "старый железный меч" in name:
            return True
    return False


def old_iron_sword_scaling(player_level: int) -> dict[str, float]:
    root = math.sqrt(max(1, player_level))
    return {
        "bonus_damage": math.floor(3 + 0.35 * root),
        "poison_chance_percent": min(12.0, 3.0 + 0.08 * root),
        "mob_xp_penalty_percent": min(12.0, 2.0 + 0.07 * root),
        "mob_money_penalty_percent": min(12.0, 2.0 + 0.07 * root),
    }


def old_iron_sword_bonus_damage(player: dict[str, Any]) -> int:
    if not has_old_iron_sword_equipped(player):
        return 0
    return int(old_iron_sword_scaling(max(1, safe_int(player.get("level"), 1)))["bonus_damage"])


def old_iron_sword_penalty_percent(player: dict[str, Any], key: str) -> float:
    if not has_old_iron_sword_equipped(player):
        return 0.0
    return float(old_iron_sword_scaling(max(1, safe_int(player.get("level"), 1))).get(key, 0.0))


def money_copper(player: dict[str, Any]) -> int:
    return max(0, safe_int(player.get("money_copper", player.get("money", 0)), 0))


def set_money_copper(player: dict[str, Any], amount: int) -> None:
    amount = max(0, safe_int(amount, 0))
    player["money_copper"] = amount
    player["money"] = amount


def spend_copper_for_poverty(player: dict[str, Any], rng: random.Random) -> tuple[int, int]:
    roll = int(rng.randint(1, 1000))
    current = money_copper(player)
    spent = min(roll, current)
    set_money_copper(player, current - spent)
    return roll, spent


def apply_battle_damage_bonuses(player: dict[str, Any], battle: dict[str, Any], raw_damage: int, damage_type: DamageType, *, is_skill: bool = False) -> int:
    result = max(1, safe_int(raw_damage, 1))
    if damage_type in {DamageType.PHYSICAL, DamageType.MIXED}:
        result += old_iron_sword_bonus_damage(player)
    player_state = battle.get("player_state") if isinstance(battle.get("player_state"), dict) else {}
    bonus_percent = safe_int(player_state.get("combat_damage_bonus_percent"), 0) if is_skill else 0
    if bonus_percent:
        result = max(1, math.ceil(result * (1 + bonus_percent / 100)))
    return result


def maybe_apply_old_sword_on_hit(player: dict[str, Any], battle: dict[str, Any], target: dict[str, Any], rng: random.Random, log: list[str]) -> int:
    if not has_old_iron_sword_equipped(player):
        return 0
    roll, spent = spend_copper_for_poverty(player, rng)
    if spent > 0:
        target["current_hp"] = max(0, safe_int(target.get("current_hp"), 0) - spent)
        log.append(f"💰 Эффект «Бедность»: брошено {roll} медных, списано {spent}; {target.get('name')} получает {spent} чистого урона.")
    else:
        log.append(f"💰 Эффект «Бедность»: медных монет нет, чистый урон равен 0.")
    scaling = old_iron_sword_scaling(max(1, safe_int(player.get("level"), 1)))
    chance = float(scaling["poison_chance_percent"])
    if rng.uniform(0, 100) <= chance and safe_int(target.get("current_hp"), 0) > 0:
        statuses = target.setdefault("statuses", [])
        if not isinstance(statuses, list):
            statuses = []
            target["statuses"] = statuses
        poison_damage = max(1, math.floor(1 + 0.10 * math.sqrt(max(1, safe_int(player.get("level"), 1)))))
        existing = next((entry for entry in statuses if isinstance(entry, dict) and entry.get("id") == "old_iron_sword_poison"), None)
        payload = {"id": "old_iron_sword_poison", "name": "Отравление старым мечом", "turns": 2, "damage": poison_damage}
        if existing is not None:
            existing.update(payload)
        else:
            statuses.append(payload)
        log.append(f"☠️ Старый железный меч накладывает отравление: {poison_damage} урона/ход на 2 хода.")
    return spent


def player_attack_raw_damage(player: dict[str, Any], action: str) -> tuple[int, DamageType, str]:
    stats = calculate_player_derived_stats(player)
    level = stats["level"]
    if action == BATTLE_MAGIC_SPARK:
        raw = math.ceil(4 + level * 1.1 + stats["intelligence"] * 0.8)
        raw = math.ceil(raw * outgoing_damage_multiplier(player, DamageType.MAGIC.value))
        return max(1, raw), DamageType.MAGIC, "магическим сгустком"
    raw = math.ceil(5 + level * 1.2 + stats["strength"] * 0.8)
    raw = math.ceil(raw * outgoing_damage_multiplier(player, DamageType.PHYSICAL.value))
    return max(1, raw), DamageType.PHYSICAL, "обычной атакой"


def get_equipped_skill(player: dict[str, Any], action: str) -> dict[str, Any] | None:
    normalize_starter_only_skills(player)
    skills = player.get("skills") if isinstance(player.get("skills"), dict) else {}
    for skill in skills.get("equipped", []):
        if not isinstance(skill, dict):
            continue
        if str(skill.get("name") or skill.get("id") or "") == action or str(skill.get("id") or "") == action:
            return skill
    return None


def skill_costs(skill: dict[str, Any], player: dict[str, Any] | None = None) -> tuple[int, int]:
    try:
        spirit, mana = resource_cost_with_modifiers(skill, player)
        if spirit or mana:
            return max(0, spirit), max(0, mana)
    except Exception:
        logger.exception("Failed to calculate battle skill costs for skill=%r", skill.get("id") or skill.get("name"))
    spirit = safe_int(skill.get("spirit_cost") if "spirit_cost" in skill else skill.get("spiritCost"), 0)
    mana = safe_int(skill.get("mana_cost") if "mana_cost" in skill else skill.get("manaCost"), 0)
    return max(0, spirit), max(0, mana)


def skill_damage_type(skill: dict[str, Any]) -> DamageType:
    raw = str(skill.get("damage_type") or skill.get("damageType") or "physical").casefold()
    if "маг" in raw or raw in {"magic", "magical"}:
        return DamageType.MAGIC
    if "mixed" in raw or "смеш" in raw:
        return DamageType.MIXED
    return DamageType.PHYSICAL


def player_skill_raw_damage(player: dict[str, Any], skill: dict[str, Any]) -> tuple[int, DamageType, str]:
    result = calculate_player_skill_raw_damage(player, skill)
    damage_type = DamageType(result.get("damage_type") or skill_damage_type(skill).value)
    damage = result.get("damage")
    if not isinstance(damage, int):
        # Fallback for unknown formula text: keep the historical basic attack scale.
        stats = calculate_player_derived_stats(player)
        damage = math.ceil(5 + stats["level"] * 1.2 + stats["strength"] * 0.8)
    return max(1, safe_int(damage, 1)), damage_type, str(result.get("name") or skill.get("name") or "навыком")


def item_identity(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("item_id") or item.get("id") or "").strip()


def item_name_value(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("name") or item.get("name_ru") or item_identity(item) or "Предмет")


def combat_effect_data(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("combat_effect", "battle_effect", "use_effect"):
        value = item.get(key)
        if isinstance(value, dict):
            return value
    return {}


def combat_effect_type(item: dict[str, Any]) -> str:
    effect = combat_effect_data(item)
    raw = str(
        effect.get("type")
        or effect.get("battle_action")
        or effect.get("combat_action")
        or item.get("combat_action")
        or item.get("pouch_action")
        or ""
    ).strip().casefold()
    item_id = item_identity(item)
    aliases = {
        "old_throwing_knife": "throw_damage",
        "decent_throwing_knife": "throw_damage",
        "good_throwing_knife": "throw_damage",
        "homemade_smoke_bomb": "escape_bonus",
        "minor_regeneration_potion": "battle_regeneration",
        "small_regeneration_potion": "battle_regeneration",
        "common_cleansing_potion": "cleanse_debuffs",
        "ordinary_cleansing_potion": "cleanse_debuffs",
        "battle_stimulant": "battle_stimulant",
    }
    return aliases.get(item_id, raw)


def is_food_item(item: dict[str, Any]) -> bool:
    category = str(item.get("category") or item.get("type") or item.get("subtype") or "").casefold()
    item_class = str(item.get("item_class") or "").casefold()
    tags = {str(tag).casefold() for tag in item.get("integration_tags", []) if isinstance(tag, str)}
    effect = item.get("use_effect") if isinstance(item.get("use_effect"), dict) else {}
    return bool(
        "еда" in category
        or "напит" in category
        or "food" in category
        or "drink" in category
        or item_class == "camp_food"
        or "food" in tags
        or "energy_restore" in tags
        or item.get("energy_restore")
        or item.get("restore_energy")
        or effect.get("energy_restore")
        or effect.get("restore_energy")
    )


def combat_restore_amount(item: dict[str, Any]) -> int:
    effect = item.get("use_effect") if isinstance(item.get("use_effect"), dict) else {}
    amount = 0
    for label in ("restore_hp", "hp_restore", "restore_spirit", "spirit_restore", "restore_mana", "mana_restore"):
        amount = max(amount, safe_int(item.get(label), 0), safe_int(effect.get(label), 0))
    return amount


def is_combat_pouch_item(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict) or is_food_item(item):
        return False
    # Боевой стимулятор принимается из инвентаря заранее и не должен появляться в подсумке.
    if item_identity(item) == "battle_stimulant" or bool(item.get("pouch_excluded")):
        return False
    category = str(item.get("category") or item.get("type") or item.get("subtype") or "").casefold()
    tags = {str(tag).casefold() for tag in item.get("integration_tags", []) if isinstance(tag, str)}
    allowed_categories = {"алхимия", "расходник", "расходники", "consumable", "consumables", "метательное", "зелья", "зелье"}
    return bool(
        category in allowed_categories
        or "combat_pouch" in tags
        or "battle_consumable" in tags
        or combat_effect_type(item)
        or combat_restore_amount(item) > 0
    )


def pouch_item_needs_target(item: dict[str, Any]) -> bool:
    return combat_effect_type(item) in TARGETED_POUCH_EFFECTS



def pouch_items(player: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry["item"] for entry in pouch_items_with_refs(player)]


def pouch_items_with_refs(player: dict[str, Any]) -> list[dict[str, Any]]:
    """Return combat pouch items with stable inventory-index references.

    The battle UI uses numbered buttons instead of item names. This avoids using
    the wrong item when two consumables share a display name but differ by id,
    quality, effect, or future metadata.
    """

    result: list[dict[str, Any]] = []
    inventory = player.get("inventory", [])
    if not isinstance(inventory, list):
        return result
    for index, item in enumerate(inventory):
        if not isinstance(item, dict):
            continue
        if is_combat_pouch_item(item):
            result.append({"ref": str(index), "item": item})
    return result


def format_pouch(player: dict[str, Any], battle: dict[str, Any] | None = None, page: int = 0) -> tuple[str, list[list[str]]]:
    entries = pouch_items_with_refs(player)
    if not entries:
        if isinstance(battle, dict):
            battle.pop("pouch_context", None)
        return "🎒 Подсумок пуст. В инвентаре нет зелий или расходников для боя.", battle_buttons(player)

    page_count = max(1, math.ceil(len(entries) / BATTLE_POUCH_PAGE_SIZE))
    page = max(0, min(page, page_count - 1))
    start_index = page * BATTLE_POUCH_PAGE_SIZE
    visible = entries[start_index:start_index + BATTLE_POUCH_PAGE_SIZE]

    lines = [
        "🎒 Подсумок",
        "",
        f"Страница {page + 1}/{page_count}. Расходники — дополнительное действие: они не завершают ход.",
        "После расходников можно снова открыть подсумок или выполнить основное действие: навык, ждать или сбежать.",
    ]
    buttons: list[list[str]] = []
    context_items: dict[str, str] = {}
    current_row: list[str] = []
    for local_index, entry in enumerate(visible, start=1):
        item = entry["item"]
        name = str(item.get("name") or "Предмет")
        amount = safe_int(item.get("amount"), 1)
        target_note = " — выберите цель" if pouch_item_needs_target(item) else ""
        lines.append(f"{local_index}. {name} ×{amount}{target_note}")
        context_items[str(local_index)] = str(entry["ref"])
        current_row.append(f"{BATTLE_POUCH_ITEM_PREFIX}{local_index}")
        if len(current_row) == 2:
            buttons.append(current_row)
            current_row = []
    if current_row:
        buttons.append(current_row)

    nav_row: list[str] = []
    if page > 0:
        nav_row.append(BATTLE_POUCH_PREV)
    if page + 1 < page_count:
        nav_row.append(BATTLE_POUCH_NEXT)
    if nav_row:
        buttons.append(nav_row)

    if isinstance(battle, dict):
        battle["pouch_context"] = {
            "page": page,
            "items": context_items,
            "round_number": safe_int(battle.get("round_number"), 1),
        }
    buttons.extend(battle_buttons(player))
    return "\n".join(lines), buttons


def remove_inventory_item_by_ref(player: dict[str, Any], ref: str, amount: int = 1) -> dict[str, Any] | None:
    inventory = player.setdefault("inventory", [])
    try:
        index = int(str(ref))
    except (TypeError, ValueError):
        return None
    if not isinstance(inventory, list) or index < 0 or index >= len(inventory):
        return None
    item = inventory[index]
    if not isinstance(item, dict):
        return None
    current = safe_int(item.get("amount"), 1)
    used = dict(item)
    if current > amount:
        item["amount"] = current - amount
    else:
        inventory.pop(index)
    return used


def remove_inventory_item_by_name(player: dict[str, Any], name: str, amount: int = 1) -> dict[str, Any] | None:
    inventory = player.setdefault("inventory", [])
    for index, item in enumerate(list(inventory)):
        if not isinstance(item, dict) or str(item.get("name") or "") != name:
            continue
        current = safe_int(item.get("amount"), 1)
        used = dict(item)
        if current > amount:
            item["amount"] = current - amount
        else:
            inventory.pop(index)
        return used
    return None


def use_pouch_item_by_ref(player: dict[str, Any], battle: dict[str, Any], ref: str, *, target_number: int | None = None, rng: random.Random | None = None) -> tuple[str, bool]:
    inventory = player.get("inventory", [])
    try:
        index = int(str(ref))
    except (TypeError, ValueError):
        return "🎒 Такой предмет уже недоступен. Откройте подсумок заново.", False
    if not isinstance(inventory, list) or index < 0 or index >= len(inventory):
        return "🎒 Такой предмет уже недоступен. Откройте подсумок заново.", False
    source_item = inventory[index]
    if not isinstance(source_item, dict):
        return "🎒 Такой предмет уже недоступен. Откройте подсумок заново.", False
    return use_pouch_item(player, battle, source_item, ref=str(index), target_number=target_number, rng=rng)


def use_pouch_item(player: dict[str, Any], battle: dict[str, Any], item_name_or_item: str | dict[str, Any], *, ref: str | None = None, target_number: int | None = None, rng: random.Random | None = None) -> tuple[str, bool]:
    rng = rng or random.Random()
    if isinstance(item_name_or_item, dict):
        source_item = item_name_or_item
        item_name = item_name_value(source_item)
    else:
        item_name = str(item_name_or_item)
        source_item = next((item for item in player.get("inventory", []) if isinstance(item, dict) and str(item.get("name") or "") == item_name), None)
    if source_item is None:
        return "🎒 Такого предмета нет в подсумке.", False
    if not is_combat_pouch_item(source_item):
        return "🎒 Этот предмет нельзя использовать в бою.", False

    effect_type = combat_effect_type(source_item)
    if pouch_item_needs_target(source_item) and target_number is None:
        return "🎯 Для этого предмета нужно выбрать цель.", False

    player_state = battle.setdefault("player_state", {})
    consumed = False
    message = ""

    if effect_type == "throw_damage":
        target = enemy_by_stable_number(battle, target_number or 1)
        if target is None:
            return "🎯 Эта цель уже побеждена или недоступна. Выберите живого противника.", False
        damage = throwable_damage(player, source_item)
        target["current_hp"] = max(0, safe_int(target.get("current_hp"), 0) - damage)
        message = f"🎒 {player_display_name(player)} бросает {item_name}: {target.get('name')} получает {damage} урона."
        consumed = True

    elif effect_type == "escape_bonus":
        effect = combat_effect_data(source_item)
        bonus = safe_int(effect.get("escape_bonus_percent"), 20)
        turns = safe_int(effect.get("duration_turns"), 2)
        player_state["escape_bonus_chance_percent"] = max(safe_int(player_state.get("escape_bonus_chance_percent"), 0), bonus)
        player_state["escape_bonus_turns"] = max(safe_int(player_state.get("escape_bonus_turns"), 0), turns)
        message = f"🎒 {player_display_name(player)} использует {item_name}: шанс сбежать повышен на +{bonus}% на {turns} хода."
        consumed = True

    elif effect_type == "battle_regeneration":
        effect = combat_effect_data(source_item)
        max_hp = max(1, safe_int(player_state.get("max_hp"), safe_int(player.get("max_hp"), 1)))
        flat = safe_int(effect.get("regen_flat"), 30)
        percent = float(effect.get("regen_max_hp_percent", 2) or 0)
        amount = max(1, flat + math.floor(max_hp * percent / 100))
        turns = safe_int(effect.get("duration_turns"), 2)
        source_id = item_identity(source_item) or item_name
        regens = player_state.setdefault("battle_regeneration_effects", [])
        if not isinstance(regens, list):
            regens = []
            player_state["battle_regeneration_effects"] = regens
        existing = next((entry for entry in regens if isinstance(entry, dict) and entry.get("source_id") == source_id), None)
        payload = {"source_id": source_id, "name": item_name, "amount": amount, "turns": turns}
        if existing is not None:
            existing.update(payload)
        else:
            regens.append(payload)
        message = f"🎒 {player_display_name(player)} использует {item_name}: регенерация {amount} HP/ход на {turns} хода."
        consumed = True

    elif effect_type == "cleanse_debuffs":
        debuffs = player_state.setdefault("debuffs", [])
        if not isinstance(debuffs, list):
            debuffs = []
            player_state["debuffs"] = debuffs
        removed: list[Any] = []
        if debuffs:
            removed.append(debuffs.pop(0))
        if debuffs and rng.random() < 0.10:
            removed.append(debuffs.pop(0))
        if not removed:
            return f"🎒 {item_name} не использовано: на игроке нет боевых дебафов.", False
        message = f"🎒 {player_display_name(player)} использует {item_name}: снято дебафов — {len(removed)}."
        consumed = True

    elif effect_type == "battle_stimulant":
        effect = combat_effect_data(source_item)
        damage_bonus = safe_int(effect.get("damage_bonus_percent"), 30)
        resource_bonus = safe_int(effect.get("resource_max_bonus_percent"), 20)
        player_state["battle_stimulant_active"] = True
        player_state["combat_damage_bonus_percent"] = max(safe_int(player_state.get("combat_damage_bonus_percent"), 0), damage_bonus)
        for current_key, max_key in (("current_spirit", "max_spirit"), ("current_mana", "max_mana")):
            original_key = f"_{max_key}_before_battle_stimulant"
            if original_key not in player_state:
                player_state[original_key] = safe_int(player_state.get(max_key), 0)
                bonus = math.floor(max(1, safe_int(player_state.get(max_key), 1)) * resource_bonus / 100)
                player_state[max_key] = safe_int(player_state.get(max_key), 0) + bonus
                player_state[current_key] = safe_int(player_state.get(current_key), 0) + bonus
        message = f"🎒 {player_display_name(player)} использует {item_name}: урон навыков +{damage_bonus}%, максимум духа и маны +{resource_bonus}%."
        consumed = True

    else:
        restored_parts: list[str] = []
        effect = source_item.get("use_effect") if isinstance(source_item.get("use_effect"), dict) else {}
        for current_key, max_key, labels in (("current_hp", "max_hp", ("restore_hp", "hp_restore")), ("current_spirit", "max_spirit", ("restore_spirit", "spirit_restore")), ("current_mana", "max_mana", ("restore_mana", "mana_restore"))):
            restore = 0
            for label in labels:
                restore = max(restore, safe_int(source_item.get(label), 0))
                restore = max(restore, safe_int(effect.get(label), 0))
            if restore <= 0:
                continue
            before = safe_int(player_state.get(current_key), safe_int(player.get(current_key.removeprefix("current_")), 0))
            maximum = safe_int(player_state.get(max_key), safe_int(player.get(max_key.removeprefix("current_")), 0))
            after = min(maximum, before + restore)
            player_state[current_key] = after
            actual = after - before
            if actual > 0:
                restored_parts.append(f"+{actual} {current_key.removeprefix('current_')}")
        if not restored_parts:
            return "🎒 Предмет не дал боевого эффекта.", False
        message = f"🎒 {player_display_name(player)} использует {item_name}: " + ", ".join(restored_parts) + "."
        consumed = True

    if consumed:
        if ref is not None:
            remove_inventory_item_by_ref(player, ref, 1)
        else:
            remove_inventory_item_by_name(player, item_name, 1)
        sync_player_from_battle(player, battle)
    return message, consumed


def throwable_damage(player: dict[str, Any], item: dict[str, Any]) -> int:
    effect = combat_effect_data(item)
    level = max(1, safe_int(player.get("level"), 1))
    base = safe_int(effect.get("base_from_player_level"), level)
    percent = float(effect.get("bonus_player_level_percent", 0) or 0)
    return max(1, math.floor(base + level * percent / 100))



def sync_player_from_battle(player: dict[str, Any], battle: dict[str, Any]) -> None:
    player_state = battle.get("player_state") or {}
    for battle_key, player_key in (("current_hp", "hp"), ("max_hp", "max_hp"), ("current_spirit", "spirit"), ("max_spirit", "max_spirit"), ("current_mana", "mana"), ("max_mana", "max_mana")):
        if battle_key in player_state:
            player[player_key] = safe_int(player_state.get(battle_key), safe_int(player.get(player_key), 0))


def format_enemy_line(enemy: dict[str, Any], index: int | None = None) -> str:
    hp = max(0, safe_int(enemy.get("current_hp"), 0))
    max_hp = max(1, safe_int(enemy.get("max_hp"), 1))
    rank = ENEMY_RANK_LABELS.get(str(enemy.get("rank") or "normal"), str(enemy.get("rank") or "обычный"))
    damage_type = DAMAGE_TYPE_LABELS.get(str(enemy.get("damage_type") or "physical"), str(enemy.get("damage_type") or "физический"))
    prefix = f"{index}. " if index is not None else "• "
    return (
        f"{prefix}{enemy.get('name')} ур. {enemy.get('level')} — ❤️ {hp}/{max_hp}\n"
        f"   Тип: {rank} · Урон: {damage_type}\n"
        f"   🎯 {safe_int(enemy.get('accuracy'), 0)} · 🌀 {safe_int(enemy.get('dodge'), 0)} · "
        f"🛡 {safe_int(enemy.get('physical_defense'), 0)} · ✨ {safe_int(enemy.get('magic_defense'), 0)}"
    )



def battle_location_label(location_id: str | None) -> str:
    labels = {
        "hilly_meadows": "Холмистые луга",
        "ordinary_forest": "Обыкновенный лес",
    }
    normalized = normalize_battle_location(location_id)
    return labels.get(normalized, normalized or "неизвестная локация")

def format_battle_started_text(battle: dict[str, Any]) -> str:
    intro = battle.get("battle_log", ["Начался бой."])[0]
    enemy_lines = "\n".join(format_enemy_line(enemy, index + 1) for index, enemy in enumerate(battle.get("enemies", [])))
    player_state = battle.get("player_state") or {}
    player_name = battle_player_name(battle)
    location_label = battle_location_label(str(battle.get("location_id") or battle.get("return_location") or "hilly_meadows"))
    return (
        f"⚔️ Бой начался!\n📍 Локация: {location_label}\n{intro}\n\n"
        f"Ход: {battle.get('round_number', 1)}.\n\n"
        f"🧍 {player_name}:\n"
        f"❤️ {player_state.get('current_hp')}/{player_state.get('max_hp')} · "
        f"🔥 {player_state.get('current_spirit')}/{player_state.get('max_spirit')} · "
        f"✨ {player_state.get('current_mana')}/{player_state.get('max_mana')}\n"
        f"🎯 {player_state.get('accuracy')} · 🌀 {player_state.get('dodge')} · "
        f"🛡 {player_state.get('physical_defense')} · ✨ {player_state.get('magic_defense')}\n\n"
        f"👹 Противники:\n{enemy_lines}"
    )


def format_battle_status(battle: dict[str, Any]) -> str:
    enemy_lines = "\n".join(format_enemy_line(enemy, index + 1) for index, enemy in enumerate(battle.get("enemies", []))) or "• врагов не осталось"
    player_state = battle.get("player_state") or {}
    player_name = battle_player_name(battle)
    last_log = format_last_turn_log(battle)
    return (
        f"⚔️ PVE-бой. Ход: {battle.get('round_number', 1)}.\n\n"
        f"🧍 {player_name}:\n"
        f"❤️ {player_state.get('current_hp')}/{player_state.get('max_hp')} · "
        f"🔥 {player_state.get('current_spirit')}/{player_state.get('max_spirit')} · "
        f"✨ {player_state.get('current_mana')}/{player_state.get('max_mana')}\n"
        f"🎯 Точность: {player_state.get('accuracy')} · 🌀 Уклонение: {player_state.get('dodge')}\n"
        f"🛡 Физ. защита: {player_state.get('physical_defense')} · ✨ Маг. защита: {player_state.get('magic_defense')}\n\n"
        f"👹 Противники:\n{enemy_lines}\n\n"
        f"📜 Действия прошлого хода:\n{last_log}"
    )


def loot_parameters_for_rank(rank: EnemyRank, chance: int | float, min_amount: int, max_amount: int) -> tuple[int, int, int]:
    chance_value = max(0, int(math.ceil(float(chance))))
    min_value = max(1, safe_int(min_amount, 1))
    max_value = max(min_value, safe_int(max_amount, min_value))
    if rank == EnemyRank.EMPOWERED:
        # Усиленные мобы в стартовых локациях должны давать добычу немного чаще.
        # Сейчас PVE-каталоги с добычей подключены для стартовых локаций
        # Холмистые луга и Обыкновенный лес; повышение касается только шанса,
        # не количества предметов.
        chance_value = min(100, int(math.ceil(chance_value * 1.1)))
    elif rank == EnemyRank.ELITE:
        chance_value = min(100, int(math.ceil(chance_value * 1.5)))
        min_value = max(1, int(math.ceil(min_value * 1.5)))
        max_value = max(min_value, int(math.ceil(max_value * 1.7)))
    return chance_value, min_value, max_value


def grant_battle_rewards(player: dict[str, Any], battle: dict[str, Any], rng: random.Random) -> str:
    enemies = battle.get("enemies", [])
    player_level = max(1, safe_int(player.get("level"), 1))
    reward_location_id = battle_return_location(battle)
    catalog = mob_catalog(reward_location_id)
    xp_total = 0
    loot_lines: list[str] = []
    for enemy in enemies:
        rank = enemy_rank(enemy)
        level = max(1, safe_int(enemy.get("level"), 1))
        rank_xp = RANK_MULTIPLIERS.get(rank, RANK_MULTIPLIERS[EnemyRank.NORMAL])["xp"]
        base_xp = math.ceil((20 + level * 12) * rank_xp)
        difference = level - player_level
        if difference >= 0:
            diff_mult = min(2.5, 1 + difference * 0.04)
        else:
            diff_mult = max(0.1, 1 + difference * 0.08)
        xp_total += math.ceil(base_xp * diff_mult)
        template_key = next((key for key, value in catalog.items() if value["name"] == enemy.get("name")), "")
        for item_name, chance, min_amount, max_amount in catalog.get(template_key, {}).get("loot", []):
            loot_chance, loot_min, loot_max = loot_parameters_for_rank(rank, chance, min_amount, max_amount)
            if rng.uniform(0, 100) <= loot_chance:
                amount = rng.randint(loot_min, loot_max)
                item_id = battle_loot_item_id(reward_location_id, item_name)
                add_result = add_inventory_item(player, item_name, amount, item_id=item_id)
                if add_result.added > 0:
                    note = inventory_add_result_notice(add_result, item_name)
                    loot_lines.append(f"{item_name} ×{add_result.added}{note}")
                elif add_result.discarded > 0:
                    loot_lines.append(f"{item_name}: не поместилось ×{add_result.discarded}")
    group_count = max(1, len(enemies))
    xp_total = math.ceil(xp_total * max(0.55, 1 - ((group_count - 1) * 0.05)))
    # Global balance change: experience received from killing mobs is reduced by 20%.
    xp_total = max(1, math.floor(xp_total * 0.8)) if xp_total > 0 else 0
    # After reaching level 10, mob experience is reduced by an additional 30%.
    if player_level >= 10 and xp_total > 0:
        xp_total = max(1, math.floor(xp_total * 0.7))
    old_sword_xp_penalty = old_iron_sword_penalty_percent(player, "mob_xp_penalty_percent")
    if old_sword_xp_penalty and xp_total > 0:
        xp_total = max(1, math.floor(xp_total * (1 - old_sword_xp_penalty / 100)))
    progress = grant_experience(player, xp_total)
    player["pve_kills"] = safe_int(player.get("pve_kills"), 0) + len(enemies)
    rewards = [f"Опыт: +{progress['gained']}"]
    if old_sword_xp_penalty:
        rewards.append(f"Старый железный меч: опыт с мобов -{old_sword_xp_penalty:.2f}%")
    if progress["level_ups"]:
        rewards.append(
            f"Уровень повышен: {progress['level']} "
            f"(+{progress['level_ups'] * 5} очк. характеристик, +{progress['level_ups'] * 2} очк. навыков)"
        )
    if progress.get("branch_hint"):
        rewards.append(str(progress["branch_hint"]))
    if loot_lines:
        rewards.append("Добыча: " + ", ".join(loot_lines))
    else:
        rewards.append("Добыча: ничего")
    return "\n".join(rewards)


def add_inventory_item(player: dict[str, Any], item_name: str, amount: int, *, item_id: str | None = None):
    if amount <= 0:
        return add_inventory_stack(player, item_name, 0)
    definition = get_item_definition_by_id(item_id or "") if item_id else None
    definition = definition or get_item_definition_by_name(item_name)
    inventory_item = build_inventory_item(item_name, amount, item_id=item_id)
    apply_generated_item_level_and_price(player, inventory_item, "found")
    if not inventory_item.get("level"):
        inventory_item["category"] = "Добыча"
    inventory_item["source"] = "Добыча с мобов"
    if definition:
        inventory_item.setdefault("type", definition.get("type"))
    return add_inventory_stack(
        player,
        inventory_item,
        amount,
        default_source="Добыча с мобов",
        default_category="Добыча",
    )





def skill_uses_without_target(skill: dict[str, Any]) -> bool:
    """Return True for skills that explicitly do not require manual enemy target selection."""
    mode = str(
        skill.get("target_mode")
        or skill.get("targetMode")
        or skill.get("target")
        or skill.get("target_type")
        or skill.get("targetType")
        or "enemy"
    ).casefold()
    return mode in {"self", "ally", "all", "aoe", "area", "random", "no_target", "без цели", "все", "себя"}


def apply_enemy_status_effects(battle: dict[str, Any], log: list[str]) -> None:
    for enemy in alive_enemies(battle):
        statuses = enemy.get("statuses")
        if not isinstance(statuses, list):
            continue
        kept: list[dict[str, Any]] = []
        for status in statuses:
            if not isinstance(status, dict):
                continue
            if status.get("id") == "old_iron_sword_poison":
                damage = max(1, safe_int(status.get("damage"), 1))
                enemy["current_hp"] = max(0, safe_int(enemy.get("current_hp"), 0) - damage)
                log.append(f"☠️ {enemy.get('name')} получает {damage} урона от отравления.")
                status["turns"] = safe_int(status.get("turns"), 1) - 1
                if status["turns"] > 0 and safe_int(enemy.get("current_hp"), 0) > 0:
                    kept.append(status)
            else:
                kept.append(status)
        enemy["statuses"] = kept


def apply_player_regeneration_effects(player: dict[str, Any], battle: dict[str, Any], log: list[str]) -> None:
    player_state = battle.setdefault("player_state", {})
    regens = player_state.get("battle_regeneration_effects")
    if not isinstance(regens, list) or safe_int(player_state.get("current_hp"), 0) <= 0:
        return
    max_hp = max(1, safe_int(player_state.get("max_hp"), 1))
    kept: list[dict[str, Any]] = []
    for regen in regens:
        if not isinstance(regen, dict):
            continue
        amount = max(1, safe_int(regen.get("amount"), 1))
        before = safe_int(player_state.get("current_hp"), 0)
        player_state["current_hp"] = min(max_hp, before + amount)
        actual = player_state["current_hp"] - before
        if actual > 0:
            log.append(f"🧪 {regen.get('name') or 'Регенерация'} восстанавливает {actual} HP.")
        regen["turns"] = safe_int(regen.get("turns"), 1) - 1
        if regen["turns"] > 0:
            kept.append(regen)
    player_state["battle_regeneration_effects"] = kept


def tick_player_battle_effects(player: dict[str, Any], battle: dict[str, Any], log: list[str]) -> None:
    player_state = battle.setdefault("player_state", {})
    if safe_int(player_state.get("escape_bonus_turns"), 0) > 0:
        player_state["escape_bonus_turns"] = safe_int(player_state.get("escape_bonus_turns"), 0) - 1
        if player_state["escape_bonus_turns"] <= 0:
            player_state.pop("escape_bonus_turns", None)
            player_state.pop("escape_bonus_chance_percent", None)
            log.append("💨 Дым рассеивается: бонус к побегу закончился.")


def apply_enemy_phase(player: dict[str, Any], battle: dict[str, Any], rng: random.Random, log: list[str], *, defending: bool = False) -> bool:
    player_state = battle.setdefault("player_state", {})
    apply_enemy_status_effects(battle, log)
    if safe_int(player_state.get("invulnerable_turns"), 0) > 0:
        # One-turn invulnerability (e.g. Last Chance artifact resurrection).
        player_state["invulnerable_turns"] = safe_int(player_state.get("invulnerable_turns"), 0) - 1
        log.append("✨ Неуязвимость: весь урон этого хода заблокирован.")
        battle["round_number"] = safe_int(battle.get("round_number"), 1) + 1
        battle["last_turn_log"] = log[:]
        battle.setdefault("battle_log", []).extend(log)
        sync_player_from_battle(player, battle)
        return False
    for enemy in alive_enemies(battle):
        hit_chance = calculate_hit_chance(safe_int(enemy.get("accuracy"), 1), safe_int(player_state.get("dodge"), 1))
        if rng.random() > hit_chance:
            log.append(f"{enemy.get('name')} промахивается.")
            continue
        raw = enemy_raw_damage(enemy)
        if defending:
            raw = math.ceil(raw * 0.65)
        damage_type = enemy_damage_type(enemy)
        final_damage = calculate_final_damage(
            raw_damage=raw,
            damage_type=damage_type,
            target_physical_defense=safe_int(player_state.get("physical_defense"), 0),
            target_magic_defense=safe_int(player_state.get("magic_defense"), 0),
            target_soft_level=soft_level(safe_int(player.get("level"), 1)),
            damage_split=enemy_damage_split(enemy),
        )
        if damage_type == DamageType.PHYSICAL:
            final_damage = max(0, math.ceil(final_damage * incoming_physical_damage_multiplier(player)))
        player_state["current_hp"] = max(0, safe_int(player_state.get("current_hp"), 0) - final_damage)
        log.append(f"{enemy.get('name')} атакует и наносит {final_damage} урона.")

    regen_percent = combat_hp_regen_percent(player)
    if regen_percent and safe_int(player_state.get("current_hp"), 0) > 0:
        max_hp = max(1, safe_int(player_state.get("max_hp"), 1))
        before = safe_int(player_state.get("current_hp"), 0)
        restored = max(1, math.floor(max_hp * regen_percent / 100))
        player_state["current_hp"] = min(max_hp, before + restored)
        actual = player_state["current_hp"] - before
        if actual:
            log.append(f"🦎 Регенерация расы восстанавливает {actual} HP.")

    apply_player_regeneration_effects(player, battle, log)
    tick_player_battle_effects(player, battle, log)

    battle["round_number"] = safe_int(battle.get("round_number"), 1) + 1
    battle["last_turn_log"] = log[:]
    battle.setdefault("battle_log", []).extend(log)
    sync_player_from_battle(player, battle)
    return safe_int(player_state.get("current_hp"), 0) <= 0


LAST_CHANCE_ARTIFACT_ID = "one_time_artifact_last_chance"


def _try_last_chance_resurrection(player: dict[str, Any], battle: dict[str, Any], log: list[str]) -> bool:
    """Revive the player once if the Last Chance artifact is equipped.

    Restores HP/mana/spirit to full, grants 1 turn of invulnerability and
    destroys the artifact. Returns True if the resurrection happened.
    """
    equipment = player.get("equipment")
    if not isinstance(equipment, dict):
        return False
    slot_key = None
    for key, equipped in equipment.items():
        if isinstance(equipped, dict) and str(equipped.get("item_id") or equipped.get("id") or "") == LAST_CHANCE_ARTIFACT_ID:
            slot_key = key
            break
    if slot_key is None:
        return False

    player_state = battle.setdefault("player_state", {})
    max_hp = max(1, safe_int(player_state.get("max_hp"), safe_int(player.get("max_hp"), 100)))
    max_mana = max(0, safe_int(player_state.get("max_mana"), safe_int(player.get("max_mana"), 0)))
    max_spirit = max(0, safe_int(player_state.get("max_spirit"), safe_int(player.get("max_spirit"), 0)))
    player_state["current_hp"] = max_hp
    player_state["current_mana"] = max_mana
    player_state["current_spirit"] = max_spirit
    player_state["invulnerable_turns"] = 1
    player["hp"] = max_hp
    player["mana"] = max_mana
    player["spirit"] = max_spirit
    equipment.pop(slot_key, None)  # artifact is destroyed
    sync_player_from_battle(player, battle)
    log.append(
        "🔮 Одноразовый Артефакт Последнего Шанса срабатывает: воскрешение со 100% HP, маны и духа "
        "и неуязвимость на 1 ход. Артефакт рассыпается в прах."
    )
    return True


def finish_player_defeat(player: dict[str, Any], battle: dict[str, Any], log: list[str]) -> tuple[str, list[list[str]]]:
    if _try_last_chance_resurrection(player, battle, log):
        return "\n".join(log), battle_buttons(player)
    player["in_battle"] = False
    player["active_battle"] = None
    player["active_event"] = None
    death_location_id = move_player_to_death_camp(player, battle)
    player["hp"] = max(1, math.ceil(safe_int(player.get("max_hp"), 100) * 0.2))
    penalty = apply_death_experience_penalty(player, 10)
    player_name = battle_player_name(battle)
    penalty_text = "Штраф смерти: опыт не потерян."
    if penalty["lost"] > 0:
        penalty_text = f"Штраф смерти: -{penalty['lost']} опыта (-10%)."
    return (
        "\n".join(log)
        + f"\n\n❌ {player_name} проигрывает бой и отступает в лагерь локации. HP частично восстановлено.\n{penalty_text}"
    ), death_camp_buttons()


def handle_battle_action(player: dict[str, Any], action: str, rng: random.Random | None = None) -> tuple[str, list[list[str]]]:
    rng = rng or random.Random()
    battle = player.get("active_battle")
    if not player.get("in_battle") or not isinstance(battle, dict):
        player["in_battle"] = False
        player["active_battle"] = None
        return "Активного боя нет.", []

    battle.setdefault("player_name", player_display_name(player))
    player_name = battle_player_name(battle)

    recalculate_inventory_overflow(player)
    if action == "Побег недоступен":
        return "🎒 Вы перегружены: при 4+ занятых доп. слотах нельзя сбежать от противника.", battle_buttons(player)

    player_state = battle.setdefault("player_state", {})
    enemies = alive_enemies(battle)
    if not enemies:
        player["in_battle"] = False
        player["active_battle"] = None
        player["active_event"] = None
        move_player_to_battle_return_location(player, battle)
        rewards = grant_battle_rewards(player, battle, rng)
        return f"Победа!\n\n{rewards}", []

    # If a player selected a skill and then presses any other battle button,
    # cancel the stale target prompt. This prevents a later «Цель: N» click from
    # firing an old skill after opening the pouch, waiting, or choosing another
    # action.
    if battle.get("pending_skill") and not action.startswith("Цель: "):
        battle.pop("pending_skill", None)

    if action in {BATTLE_ESCAPE, "Отступить"}:
        if player.get("inventory_overflow_no_escape"):
            return "🎒 Вы перегружены: при 4+ занятых доп. слотах нельзя сбежать от противника.", battle_buttons(player)
        decrement_cooldowns_once_at_player_turn(battle, player_state)
        escape_chance = min(0.95, 0.4 + safe_int(player_state.get("escape_bonus_chance_percent"), 0) / 100)
        if rng.random() < escape_chance:
            player["in_battle"] = False
            player["active_battle"] = None
            player["active_event"] = None
            move_player_to_battle_return_location(player, battle)
            return f"🏃 {player_name} находит просвет между противниками и сбегает. Бой завершён без награды.", []
        log = [f"🏃 {player_name} пытается сбежать, но противники отрезают путь. Ход пропущен."]
        defeated = apply_enemy_phase(player, battle, rng, log)
        if defeated:
            return finish_player_defeat(player, battle, log)
        player["active_battle"] = battle
        return format_battle_status(battle), battle_buttons(player)

    if action == BATTLE_POUCH:
        text, buttons = format_pouch(player, battle, 0)
        player["active_battle"] = battle
        return text, buttons

    if action in {BATTLE_POUCH_NEXT, BATTLE_POUCH_PREV}:
        context = battle.get("pouch_context") if isinstance(battle.get("pouch_context"), dict) else {}
        page = safe_int(context.get("page"), 0) + (1 if action == BATTLE_POUCH_NEXT else -1)
        text, buttons = format_pouch(player, battle, page)
        player["active_battle"] = battle
        return text, buttons

    if action.startswith(BATTLE_POUCH_ITEM_PREFIX):
        context = battle.get("pouch_context") if isinstance(battle.get("pouch_context"), dict) else {}
        context_items = context.get("items") if isinstance(context.get("items"), dict) else {}
        local_number = action.removeprefix(BATTLE_POUCH_ITEM_PREFIX).strip().split()[0]
        ref = context_items.get(local_number)
        if ref is None:
            return "🎒 Этот пункт подсумка уже устарел. Откройте подсумок заново.", battle_buttons(player)
        try:
            source_index = int(str(ref))
            source_item = player.get("inventory", [])[source_index]
        except Exception:
            source_item = None
        if isinstance(source_item, dict) and pouch_item_needs_target(source_item):
            battle["pending_pouch_item"] = {"ref": str(ref), "name": item_name_value(source_item)}
            player["active_battle"] = battle
            return f"🎯 Выберите противника для предмета «{item_name_value(source_item)}».", target_buttons(battle, player)
        item_text, consumed = use_pouch_item_by_ref(player, battle, ref, rng=rng)
        log = [item_text]
        if consumed:
            log.append("Дополнительное действие выполнено: ход не завершён. Выберите основное действие.")
        battle["last_turn_log"] = log
        battle.setdefault("battle_log", []).extend(log)
        sync_player_from_battle(player, battle)
        if not alive_enemies(battle):
            player["in_battle"] = False
            player["active_battle"] = None
            player["active_event"] = None
            move_player_to_battle_return_location(player, battle)
            rewards = grant_battle_rewards(player, battle, rng)
            return f"{chr(10).join(log)}\n\n✅ Победа!\n\n{rewards}", []
        player["active_battle"] = battle
        return format_battle_status(battle), battle_buttons(player)

    if action.startswith("Использовать: "):
        item_name = action.removeprefix("Использовать: ").strip()
        item_text, consumed = use_pouch_item(player, battle, item_name, rng=rng)
        log = [item_text]
        if consumed:
            log.append("Дополнительное действие выполнено: ход не завершён. Выберите основное действие.")
        battle["last_turn_log"] = log
        battle.setdefault("battle_log", []).extend(log)
        sync_player_from_battle(player, battle)
        player["active_battle"] = battle
        return format_battle_status(battle), battle_buttons(player)

    pending_pouch = battle.get("pending_pouch_item") if isinstance(battle.get("pending_pouch_item"), dict) else None
    if action.startswith("Цель: ") and pending_pouch:
        raw_target = action.removeprefix("Цель: ").strip().split()[0]
        try:
            target_number = max(1, int(raw_target))
        except ValueError:
            target_number = 1
        ref = str(pending_pouch.get("ref") or "")
        item_text, consumed = use_pouch_item_by_ref(player, battle, ref, target_number=target_number, rng=rng)
        battle.pop("pending_pouch_item", None)
        log = [item_text]
        if consumed:
            log.append("Дополнительное действие выполнено: ход не завершён. Выберите основное действие.")
        battle["last_turn_log"] = log
        battle.setdefault("battle_log", []).extend(log)
        sync_player_from_battle(player, battle)
        if not alive_enemies(battle):
            player["in_battle"] = False
            player["active_battle"] = None
            player["active_event"] = None
            move_player_to_battle_return_location(player, battle)
            rewards = grant_battle_rewards(player, battle, rng)
            return f"{chr(10).join(log)}\n\n✅ Победа!\n\n{rewards}", []
        player["active_battle"] = battle
        return format_battle_status(battle), battle_buttons(player)

    pending_skill = battle.get("pending_skill") if isinstance(battle.get("pending_skill"), dict) else None
    target_number: int | None = None
    if action.startswith("Цель: ") and pending_skill:
        raw_target = action.removeprefix("Цель: ").strip().split()[0]
        try:
            target_number = max(1, int(raw_target))
        except ValueError:
            target_number = 1
        action = str(pending_skill.get("name") or pending_skill.get("id") or action)
        battle.pop("pending_skill", None)

    equipped_skill = get_equipped_skill(player, action)
    if equipped_skill is None and action in {BATTLE_DEFEND, BATTLE_ATTACK, BATTLE_MAGIC_SPARK, BATTLE_WAIT}:
        decrement_cooldowns_once_at_player_turn(battle, player_state)
    if equipped_skill is not None and not is_skill_weapon_compatible(player, equipped_skill):
        return f"⚔️ Навык «{equipped_skill.get('name')}» нельзя применить с текущим оружием. Нужно: {skill_weapon_requirement_text(equipped_skill)}.", battle_buttons(player)
    if equipped_skill is not None and target_number is None and not skill_uses_without_target(equipped_skill):
        cooldown_key = str(equipped_skill.get("id") or equipped_skill.get("name"))
        cooldowns = player_state.setdefault("cooldowns", {})
        if safe_int(cooldowns.get(cooldown_key), 0) > 0:
            return f"⏳ Навык «{equipped_skill.get('name')}» ещё на откате: {cooldowns[cooldown_key]} ход.", battle_buttons(player)
        decrement_cooldowns_once_at_player_turn(battle, player_state)
        ammo_ok, ammo_message = validate_skill_ammo(player, equipped_skill)
        if not ammo_ok:
            return f"🏹 {ammo_message}", battle_buttons(player)
        battle["pending_skill"] = equipped_skill
        player["active_battle"] = battle
        return f"🎯 Выберите противника для навыка «{equipped_skill.get('name')}».", target_buttons(battle, player)

    if equipped_skill is None and action not in {BATTLE_DEFEND, BATTLE_ATTACK, BATTLE_MAGIC_SPARK, BATTLE_WAIT}:
        return "⚔️ Выберите действие боя кнопкой: подсумок, сбежать, ждать или экипированный навык.", battle_buttons(player)

    if equipped_skill is not None:
        cooldown_key = str(equipped_skill.get("id") or equipped_skill.get("name"))
        cooldowns = player_state.setdefault("cooldowns", {})
        if safe_int(cooldowns.get(cooldown_key), 0) > 0:
            return f"⏳ Навык «{equipped_skill.get('name')}» ещё на откате: {cooldowns[cooldown_key]} ход.", battle_buttons(player)
        decrement_cooldowns_once_at_player_turn(battle, player_state)
        ammo_ok, ammo_message = validate_skill_ammo(player, equipped_skill)
        if not ammo_ok:
            return f"🏹 {ammo_message}", battle_buttons(player)

    log: list[str] = []
    defending = action == BATTLE_DEFEND
    waiting = action == BATTLE_WAIT
    if defending:
        log.append(f"{player_name} занимает защитную стойку. Входящий урон в этом ходе снижен.")
    elif waiting:
        log.append(f"{player_name} выжидает и восстанавливает темп боя.")
    else:
        if target_number is not None:
            target = enemy_by_stable_number(battle, target_number)
            if target is None:
                player["active_battle"] = battle
                return "🎯 Эта цель уже побеждена или недоступна. Выберите живого противника.", target_buttons(battle, player)
        else:
            target = enemies[0]
        if equipped_skill is not None:
            spirit_cost, mana_cost = skill_costs(equipped_skill, player)
            cooldown_key = str(equipped_skill.get("id") or equipped_skill.get("name"))
            cooldowns = player_state.setdefault("cooldowns", {})
            if safe_int(cooldowns.get(cooldown_key), 0) > 0:
                return f"⏳ Навык «{equipped_skill.get('name')}» ещё на откате: {cooldowns[cooldown_key]} ход.", battle_buttons(player)
            if spirit_cost > safe_int(player_state.get("current_spirit"), 0):
                return f"🔥 Не хватает духа для навыка «{equipped_skill.get('name')}». Нужно: {spirit_cost}.", battle_buttons(player)
            if mana_cost > safe_int(player_state.get("current_mana"), 0):
                return f"✨ Не хватает маны для навыка «{equipped_skill.get('name')}». Нужно: {mana_cost}.", battle_buttons(player)
            ammo_ok, ammo_message = consume_skill_ammo(player, equipped_skill)
            if not ammo_ok:
                return f"🏹 {ammo_message}", battle_buttons(player)
            if ammo_message:
                log.append(f"🏹 {ammo_message}")
            player_state["current_spirit"] = max(0, safe_int(player_state.get("current_spirit"), 0) - spirit_cost)
            player_state["current_mana"] = max(0, safe_int(player_state.get("current_mana"), 0) - mana_cost)
            cooldown = safe_int(equipped_skill.get("cooldown_turns") if "cooldown_turns" in equipped_skill else equipped_skill.get("cooldown"), 0)
            if cooldown > 0:
                cooldowns[cooldown_key] = cooldown
            raw_damage, damage_type, action_text = player_skill_raw_damage(player, equipped_skill)
            action_text = f"навыком «{action_text}»"
        else:
            raw_damage, damage_type, action_text = player_attack_raw_damage(player, action)
        raw_damage = apply_battle_damage_bonuses(player, battle, raw_damage, damage_type, is_skill=equipped_skill is not None)
        hit_chance = calculate_hit_chance(safe_int(player_state.get("accuracy"), 1), safe_int(target.get("dodge"), 1))
        if rng.random() <= hit_chance:
            final_damage = calculate_final_damage(
                raw_damage=raw_damage,
                damage_type=damage_type,
                target_physical_defense=safe_int(target.get("physical_defense"), 0),
                target_magic_defense=safe_int(target.get("magic_defense"), 0),
                target_soft_level=soft_level(safe_int(target.get("level"), 1)),
            )
            # Критический удар: шанс и множитель берутся из боевых статов игрока
            # (производные crit_chance_percent / crit_damage_percent).
            crit_chance = safe_int(player_state.get("crit_chance"), 0)
            crit_damage = max(100, safe_int(player_state.get("crit_damage"), 100))
            is_crit = crit_chance > 0 and rng.random() * 100 < crit_chance
            if is_crit:
                final_damage = max(1, math.ceil(final_damage * crit_damage / 100))
            target["current_hp"] = max(0, safe_int(target.get("current_hp"), 0) - final_damage)
            crit_suffix = " 💥 Критический удар!" if is_crit else ""
            log.append(f"{player_name} бьёт {action_text}: {target.get('name')} получает {final_damage} урона.{crit_suffix}")
            if damage_type in {DamageType.PHYSICAL, DamageType.MIXED}:
                maybe_apply_old_sword_on_hit(player, battle, target, rng, log)
        else:
            log.append(f"{player_name} промахивается: {target.get('name')} успевает уйти с линии атаки.")

    if not alive_enemies(battle):
        battle.setdefault("battle_log", []).extend(log)
        sync_player_from_battle(player, battle)
        player["in_battle"] = False
        player["active_battle"] = None
        player["active_event"] = None
        move_player_to_battle_return_location(player, battle)
        rewards = grant_battle_rewards(player, battle, rng)
        return f"{chr(10).join(log)}\n\n✅ Победа!\n\n{rewards}", []

    defeated = apply_enemy_phase(player, battle, rng, log, defending=defending)
    if defeated:
        return finish_player_defeat(player, battle, log)

    player["active_battle"] = battle
    return format_battle_status(battle), battle_buttons(player)
