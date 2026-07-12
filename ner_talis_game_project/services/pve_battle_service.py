"""Runnable PVE battle service for Telegram/VK exploration events.

The module integrates the uploaded PVE battle data structures into the existing
project. It keeps the first implementation intentionally compact: random PVE
encounters in external locations become real turn-based battles, but the API is
stable enough to later replace damage/AI/skill formulas with the full combat
system.
"""

from __future__ import annotations

import logging
import json
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
    battle = (player or {}).get("active_battle") if isinstance(player, dict) else None
    profile = (battle or {}).get("combat_profile") if isinstance(battle, dict) else None
    if isinstance(profile, dict) and profile.get("allow_ally_commands") and (battle.get("allies") or []):
        labels = {
            "attack": "Атаковать", "protect": "Защищать", "heal": "Лечить",
            "use_skill": "Использовать навык", "wait": "Ждать",
            "change_target": "Сменить цель", "retreat": "Отступить",
        }
        commands = [f"Приказ: {labels.get(str(cmd), cmd)}" for cmd in (profile.get("available_commands") or [])]
        for index in range(0, len(commands), 2):
            rows.append(commands[index:index + 2])
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
    """Move the defeated player to a published configured camp or legacy camp."""

    location_id = battle_return_location(battle)
    try:
        from services.camp_runtime import death_camp

        live_camp = death_camp(location_id)
    except Exception:
        live_camp = None
    player["current_location"] = location_id
    player["current_zone"] = f"{location_id}_camp"
    player["location_id"] = f"{location_id}_camp"
    if live_camp:
        player["current_camp_id"] = live_camp.get("id")
        player["last_opened_camp_id"] = live_camp.get("id")
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


def build_constructor_enemy(mob_data: dict[str, Any], level: int, index: int) -> EnemyBattleState:
    """Собрать боевого врага из карточки моба конструктора (ТЗ §7).

    HP/защиты/точность/уклонение/крит берутся прямо из карточки; урон движок
    считает через enemy_raw_damage, поэтому суммарный урон прокидываем явным
    полем base_damage (в serialize ниже) — иначе он считался бы по уровню.
    """
    def _n(key, default=0):
        try:
            return float(mob_data.get(key))
        except (TypeError, ValueError):
            return default

    hp = max(1, int(_n("hp", 1)))
    phys = _n("phys_damage", 0)
    mag = _n("mag_damage", 0)
    if phys > 0 and mag > 0:
        damage_type = DamageType.MIXED
        total = phys + mag
        split = DamageSplit(physical=max(0, round(phys / total * 100)), magic=max(0, 100 - round(phys / total * 100)))
    elif mag > 0:
        damage_type = DamageType.MAGIC
        split = DamageSplit(physical=0, magic=100)
    else:
        damage_type = DamageType.PHYSICAL
        split = DamageSplit(physical=100, magic=0)

    enemy = EnemyBattleState(
        mob_id=f"c_{index}_{uuid.uuid4().hex[:6]}",
        name=str(mob_data.get("name") or "Существо"),
        rank=EnemyRank.NORMAL,
        biological_type=str(mob_data.get("type") or "monster"),
        role="attacker",
        level=max(1, int(level)),
        damage_type=damage_type,
        current_hp=hp,
        max_hp=hp,
        armor=0,
        magic_armor=0,
        physical_defense=max(0, int(_n("phys_defense", 0))),
        magic_defense=max(0, int(_n("mag_defense", 0))),
        accuracy=max(1, int(_n("accuracy", 1) or 1)),
        dodge=max(0, int(_n("evasion", 0))),
        crit_chance=max(0, int(_n("crit_chance", 0))),
        crit_damage=max(0, int(_n("crit_damage", 100) or 100)),
        damage_split=split,
        skills=[],
        features=[],
    )
    enemy.validate_damage_type()
    return enemy


def hydrate_constructor_enemy(enemy:dict[str,Any],mob_id:str,mob_data:dict[str,Any])->dict[str,Any]:
    """Attach every published mob sub-card needed by the live battle runtime."""
    from services import world_content_registry as world
    enemy.update({"source_mob_id":str(mob_id),"constructor_rank":mob_data.get("mob_rank"),"constructor_drop_rows":[dict(row) for row in mob_data.get("drop") or [] if isinstance(row,dict)],"mana":safe_int(mob_data.get("mana"),0),"spirit":safe_int(mob_data.get("spirit"),0),"energy":safe_int(mob_data.get("energy"),0),"armor":safe_int(mob_data.get("armor"),0),"initiative":safe_int(mob_data.get("initiative"),0),"base_damage":max(1,safe_int(mob_data.get("phys_damage"),0)+safe_int(mob_data.get("mag_damage"),0)),"exp_formula_id":mob_data.get("exp_formula_id"),"authored_experience":safe_int(mob_data.get("experience"),0),"authored_coins":safe_int(mob_data.get("coins"),0),"coins_min":safe_int(mob_data.get("coins_min"),0),"coins_max":safe_int(mob_data.get("coins_max"),0),"rank_reward_multiplier":float(mob_data.get("rank_reward_multiplier") or 1),"experience_reduction_after_10":float(mob_data.get("experience_reduction_after_10") or 30),"first_win_reward":mob_data.get("first_win_reward"),"repeat_win_reward":mob_data.get("repeat_win_reward"),"actions_per_turn":max(1,safe_int(mob_data.get("actions_per_turn"),1)),"escape_forbidden":bool(mob_data.get("escape_forbidden")),"player_escape_chance":safe_int(mob_data.get("player_escape_chance"),100),"attributes":{key:safe_int(mob_data.get(key),0) for key in ("strength","agility","endurance","intelligence","wisdom","perception")}})
    mapping=((world.KIND_MOB_SKILL,"constructor_mob_skills"),(world.KIND_MOB_PASSIVE,"constructor_passives"),(world.KIND_MOB_RESISTANCE,"constructor_resistances"),(world.KIND_MOB_EFFECT,"constructor_effects"),(world.KIND_MOB_PHASE,"constructor_phases"))
    for kind,key in mapping:
        rows=[]
        for env in world.list_content(kind,status=world.STATUS_PUBLISHED):
            data=env.get("data") or {}
            if str(data.get("mob_id") or "")==str(mob_id):rows.append({"id":env.get("id"),**data})
        if kind==world.KIND_MOB_PHASE:rows.sort(key=lambda row:(safe_int(row.get("phase_number"),0),-safe_int(row.get("hp_percent"),100)))
        enemy[key]=rows
    return enemy


def apply_constructor_phase(enemy:dict[str,Any],battle:dict[str,Any],log:list[str])->None:
    hp=max(0,safe_int(enemy.get("current_hp"),0));maximum=max(1,safe_int(enemy.get("max_hp"),1));percent=hp*100/maximum
    applied=enemy.setdefault("applied_constructor_phases",[])
    for phase in enemy.get("constructor_phases") or []:
        phase_id=str(phase.get("id") or phase.get("phase_number") or "")
        threshold=float(phase.get("hp_percent") or 100)
        if phase_id in applied or percent>threshold:continue
        applied.append(phase_id);log.append(str(phase.get("transition_message") or phase.get("player_text") or f"{enemy.get('name')} переходит в новую фазу."))
        changes=phase.get("stat_changes") or {}
        if isinstance(changes,str):
            try:changes=json.loads(changes)
            except Exception:changes={}
        if isinstance(changes,dict):
            for key,value in changes.items():
                if key in {"base_damage","physical_defense","magic_defense","accuracy","dodge","actions_per_turn"}:enemy[key]=safe_int(enemy.get(key),0)+safe_int(value,0)
        if phase.get("forbid_escape"):battle["can_escape"]=False;enemy["escape_forbidden"]=True
        enemy.setdefault("added_phase_skill_ids",[]).extend(str(value) for value in phase.get("add_skill_ids") or [])
        enemy.setdefault("removed_phase_skill_ids",[]).extend(str(value) for value in phase.get("remove_skill_ids") or [])
        for effect_id in phase.get("add_effect_ids") or []:enemy.setdefault("phase_effect_ids",[]).append(str(effect_id))


def constructor_damage_multiplier(enemy:dict[str,Any],damage_type:Any,player:dict[str,Any])->float:
    dtype=str(getattr(damage_type,"value",damage_type) or "").lower();wanted={"physical"} if "physical" in dtype else {"magical","magic"} if "magic" in dtype else set()
    if "mixed" in dtype:wanted={"physical","magical","magic"}
    multiplier=1.0
    equipped=player.get("equipped_items") or player.get("equipment") or [];equipped=equipped.values() if isinstance(equipped,dict) else equipped
    weapons={str(row.get("weapon_type") or "") for row in equipped if isinstance(row,dict)}
    inventory_ids={str(row.get("item_id") or row.get("id") or "") for row in player.get("inventory") or [] if isinstance(row,dict)}
    for row in enemy.get("constructor_resistances") or []:
        rtype=str(row.get("resist_type") or "").lower();weapon=str(row.get("weapon_type") or "")
        if rtype not in wanted and not (weapon and weapon in weapons):continue
        value=max(0,min(100,float(row.get("value") or 0)));weakening=str(row.get("weakening_item_id") or "")
        if weakening and weakening in inventory_ids:continue
        multiplier*=1+value/100 if row.get("is_weakness") else max(0,1-value/100)
    return max(0,multiplier)


def create_constructor_battle(player: dict[str, Any], rng: random.Random, location_id: str) -> tuple[dict[str, Any], str] | None:
    """Бой из опубликованных спаунов конструктора (ТЗ §15/§22). None — нет
    подходящего спауна (вызывающий откатывается на легаси-бой)."""
    try:
        from services import location_runtime as lr
        from services import world_runtime as wr
    except Exception:
        return None
    if not lr.live_enabled():
        return None
    player_level = max(1, safe_int(player.get("level"), 1))
    spawn = lr.pick_mob_spawn(location_id, player_level, rng=rng)
    if not spawn:
        return None
    mob_id = str(spawn.get("mob_id") or "")
    mob_data = wr.get_published(wr.registry.KIND_MOB, mob_id)
    if not mob_data:
        return None
    spawn_data = spawn.get("data") or {}

    def _i(key, default):
        try:
            return int(float(spawn_data.get(key)))
        except (TypeError, ValueError):
            return default

    count_min = max(1, _i("min_in_battle", 1))
    count_max = max(count_min, _i("max_in_battle", count_min))
    count = rng.randint(count_min, count_max)
    # Недельный запас (§22): нельзя вывести в бой больше, чем осталось.
    remaining = spawn.get("remaining")
    if remaining is not None:
        if remaining <= 0:
            return None
        count = max(1, min(count, int(remaining)))

    lvl_min = _i("mob_level_min", 0) or int(float(mob_data.get("min_level") or player_level))
    lvl_max = _i("mob_level_max", 0) or int(float(mob_data.get("max_level") or lvl_min or player_level))
    lvl_max = max(lvl_min, lvl_max)

    enemies = []
    for index in range(count):
        level = rng.randint(lvl_min, lvl_max) if lvl_max >= lvl_min and lvl_min > 0 else max(1, player_level)
        enemies.append(build_constructor_enemy(mob_data, level, index + 1))

    intro = str(mob_data.get("description") or f"На вас выходит {mob_data.get('name') or 'существо'}.")
    battle = BattleState(
        battle_id=f"pve_{uuid.uuid4().hex[:12]}",
        player_id=str(player.get("game_id") or player.get("id") or "player"),
        location_id=location_id,
        battle_type="random_event",
        round_number=1,
        player_state=make_player_battle_state(player),
        enemies=enemies,
        can_escape=True,
        battle_log=[intro],
    )
    battle_dict = serialize_battle(battle)
    try:
        from services.combat_constructor_service import resolve_profile
        battle_dict["combat_profile"] = resolve_profile("mob", object_id=mob_id, group_battle=len(enemies) > 1)
    except Exception:
        battle_dict["combat_profile"] = {"scope": "pve", "timer_enabled": False}
    from services.combat_group_runtime import attach_participants
    attach_participants(battle_dict, player)
    # Тегируем врагов конструкторными данными: source_mob_id (для списания запаса
    # при победе §22) и base_damage (чтобы движок использовал урон из карточки).
    base_damage = max(1, int(float(mob_data.get("phys_damage") or 0) + float(mob_data.get("mag_damage") or 0)))
    for enemy_dict in battle_dict.get("enemies", []):
        hydrate_constructor_enemy(enemy_dict,mob_id,mob_data)
        from services.formula_runtime import evaluate
        enemy_dict["base_damage"] = max(1, safe_int(evaluate(mob_data.get("damage_formula_id"), {
            "mob_level": enemy_dict.get("level", player_level), "player_level": player_level,
            "level_diff": safe_int(enemy_dict.get("level"), player_level) - player_level,
            "base_amount": base_damage,
        }, default=base_damage), base_damage))
        enemy_dict["exp_formula_id"] = mob_data.get("exp_formula_id")
    apply_inventory_battle_stimulant_to_battle(player, battle_dict)
    battle_dict["origin_location_id"] = location_id
    battle_dict["return_location"] = location_id
    battle_dict["player_name"] = player_display_name(player)
    player["active_battle"] = battle_dict
    from services.item_effect_trigger_runtime import trigger_equipped
    trigger_equipped(player, "on_battle_start", context={"location_id": location_id}, rng=rng)
    player["active_event"] = None
    player["in_battle"] = True
    player["current_location"] = location_id
    player["current_zone"] = f"{location_id}_battle"
    player["location_id"] = f"{location_id}_battle"
    sync_player_from_battle(player, battle_dict)
    return battle_dict, format_battle_started_text(battle_dict)


def create_battle_for_constructor_mob(player: dict[str, Any], mob_id: str, *, rng: random.Random | None = None, location_id: str | None = None) -> tuple[dict[str, Any], str]:
    """Start a battle against an explicit published mob (craft/event consequence)."""
    from services import world_runtime as wr
    rng = rng or random.Random()
    mob_data = wr.get_published(wr.registry.KIND_MOB, str(mob_id))
    if not mob_data or not wr.campaign_content_allowed(player, wr.registry.KIND_MOB, str(mob_id)):
        raise ValueError("Моб последствия не опубликован или не найден.")
    location_id = str(location_id or player.get("current_location") or player.get("location_id") or "craft_event")
    player_level = max(1, safe_int(player.get("level"), 1))
    low = max(1, safe_int(mob_data.get("min_level"), player_level))
    high = max(low, safe_int(mob_data.get("max_level"), low))
    enemy = build_constructor_enemy(mob_data, rng.randint(low, high), 1)
    battle = BattleState(
        battle_id=f"pve_{uuid.uuid4().hex[:12]}", player_id=str(player.get("game_id") or player.get("id") or "player"),
        location_id=location_id, battle_type="craft_failure", round_number=1,
        player_state=make_player_battle_state(player), enemies=[enemy], can_escape=True,
        battle_log=[str(mob_data.get("description") or f"Из-за провала появляется {mob_data.get('name') or 'существо'}.")],
    )
    battle_dict = serialize_battle(battle)
    try:
        from services.combat_constructor_service import resolve_profile
        battle_dict["combat_profile"] = resolve_profile("mob", object_id=str(mob_id), group_battle=False)
    except Exception:
        battle_dict["combat_profile"] = {"scope": "pve", "timer_enabled": False}
    from services.combat_group_runtime import attach_participants
    attach_participants(battle_dict, player)
    battle_dict["origin_location_id"] = location_id
    battle_dict["return_location"] = location_id
    battle_dict["player_name"] = player_display_name(player)
    for row in battle_dict.get("enemies", []):
        hydrate_constructor_enemy(row,str(mob_id),mob_data)
    player["active_battle"] = battle_dict
    player["active_event"] = None
    player["in_battle"] = True
    player["current_zone"] = f"{location_id}_battle"
    player["location_id"] = f"{location_id}_battle"
    sync_player_from_battle(player, battle_dict)
    return battle_dict, format_battle_started_text(battle_dict)


def create_location_battle(player: dict[str, Any], rng: random.Random | None = None, location_id: str | None = None) -> tuple[dict[str, Any], str]:
    normalize_starter_only_skills(player)
    rng = rng or random.Random()
    location_id = normalize_battle_location(location_id or player.get("current_location") or player.get("location_id") or "hilly_meadows")
    # Если включён живой слой и у локации есть конструкторные спауны — строим бой
    # из них (иначе ниже обычная легаси-логика).
    try:
        constructor_battle = create_constructor_battle(player, rng, location_id)
    except Exception:
        constructor_battle = None
    if constructor_battle is not None:
        return constructor_battle
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
    try:
        from services.combat_constructor_service import resolve_profile
        battle_dict["combat_profile"] = resolve_profile("pve", object_id=location_id, group_battle=len(enemies) > 1)
    except Exception:
        battle_dict["combat_profile"] = {"scope": "pve", "timer_enabled": False}
    from services.combat_group_runtime import attach_participants
    attach_participants(battle_dict, player)
    apply_inventory_battle_stimulant_to_battle(player, battle_dict)
    battle_dict["origin_location_id"] = location_id
    battle_dict["return_location"] = location_id
    battle_dict["player_name"] = player_display_name(player)
    player["active_battle"] = battle_dict
    from services.item_effect_trigger_runtime import trigger_equipped
    trigger_equipped(player, "on_battle_start", context={"location_id": location_id}, rng=rng)
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
    # Конструкторные враги несут явный урон из карточки моба (base_damage):
    # его и используем (с ранговым множителем), не считая по уровню/имени.
    explicit = enemy.get("base_damage")
    if explicit not in (None, ""):
        return max(1, math.ceil(safe_int(explicit, 1) * mult["damage"]))
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
    from services.item_effect_trigger_runtime import trigger_equipped
    trigger_equipped(player, "on_attack")
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
    from services.item_effect_trigger_runtime import trigger_equipped
    trigger_equipped(player, "on_attack", context={"skill_level": safe_int(skill.get("level"), 1)})
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
    configured_actions = item.get("profile_actions")
    if isinstance(configured_actions, list) and "pouch_store" in configured_actions and not item.get("in_pouch"):
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
        damage=max(0,math.ceil(damage*constructor_damage_multiplier(target,DamageType.PHYSICAL,player)))
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
    allies = [f"• {row.get('name')}: ❤️ {row.get('current_hp')}/{row.get('max_hp')}" for row in (battle.get("allies") or []) if isinstance(row, dict)]
    ally_block = ("\n\n🤝 Союзники:\n" + "\n".join(allies)) if allies else ""
    return (
        f"⚔️ Бой начался!\n📍 Локация: {location_label}\n{intro}\n\n"
        f"Ход: {battle.get('round_number', 1)}.\n\n"
        f"🧍 {player_name}:\n"
        f"❤️ {player_state.get('current_hp')}/{player_state.get('max_hp')} · "
        f"🔥 {player_state.get('current_spirit')}/{player_state.get('max_spirit')} · "
        f"✨ {player_state.get('current_mana')}/{player_state.get('max_mana')}\n"
        f"🎯 {player_state.get('accuracy')} · 🌀 {player_state.get('dodge')} · "
        f"🛡 {player_state.get('physical_defense')} · ✨ {player_state.get('magic_defense')}\n\n"
        f"👹 Противники:\n{enemy_lines}{ally_block}"
    )


def format_battle_status(battle: dict[str, Any]) -> str:
    enemy_lines = "\n".join(format_enemy_line(enemy, index + 1) for index, enemy in enumerate(battle.get("enemies", []))) or "• врагов не осталось"
    player_state = battle.get("player_state") or {}
    player_name = battle_player_name(battle)
    last_log = format_last_turn_log(battle)
    allies = [f"• {row.get('name')}: ❤️ {row.get('current_hp')}/{row.get('max_hp')}" for row in (battle.get("allies") or []) if isinstance(row, dict) and safe_int(row.get("current_hp"), 0) > 0]
    ally_block = ("🤝 Союзники:\n" + "\n".join(allies) + "\n\n") if allies else ""
    profile = battle.get("combat_profile") if isinstance(battle.get("combat_profile"), dict) else {}
    layout = str(profile.get("message_layout") or "").strip()
    if layout:
        blocks = {str(row.get("block")): row for row in profile.get("message_blocks") or [] if isinstance(row, dict)}
        values = {"round": battle.get("round_number", 1), "player": player_name, "hp": player_state.get("current_hp"), "max_hp": player_state.get("max_hp"), "mana": player_state.get("current_mana"), "spirit": player_state.get("current_spirit"), "enemies": enemy_lines, "allies": ally_block.strip(), "log": last_log}
        for key, row in blocks.items():
            if row.get("enabled") is False: values[key] = ""
            elif row.get("template"): values[key] = str(row["template"]).format_map(values)
        try: return layout.format_map(values)
        except (KeyError, ValueError): pass
    return (
        f"⚔️ PVE-бой. Ход: {battle.get('round_number', 1)}.\n\n"
        f"🧍 {player_name}:\n"
        f"❤️ {player_state.get('current_hp')}/{player_state.get('max_hp')} · "
        f"🔥 {player_state.get('current_spirit')}/{player_state.get('max_spirit')} · "
        f"✨ {player_state.get('current_mana')}/{player_state.get('max_mana')}\n"
        f"🎯 Точность: {player_state.get('accuracy')} · 🌀 Уклонение: {player_state.get('dodge')}\n"
        f"🛡 Физ. защита: {player_state.get('physical_defense')} · ✨ Маг. защита: {player_state.get('magic_defense')}\n\n"
        f"{ally_block}👹 Противники:\n{enemy_lines}\n\n"
        f"📜 Действия прошлого хода:\n{last_log}"
    )


def _profile_text(battle: dict[str, Any], key: str, default: str, **values: Any) -> str:
    profile = battle.get("combat_profile") if isinstance(battle.get("combat_profile"), dict) else {}
    rows = profile.get("texts") or []
    authored = next((row.get("text") for row in rows if isinstance(row, dict) and row.get("key") == key), None)
    template = str(authored or profile.get(key) or default)
    try:
        return template.format_map({k: v for k, v in values.items()})
    except (KeyError, ValueError):
        return template


def _escape_condition(rule: dict[str, Any], enemy: dict[str, Any], battle: dict[str, Any], player: dict[str, Any]) -> bool:
    kind = str(rule.get("condition_type") or "scenario")
    value = rule.get("value")
    current, maximum = safe_int(enemy.get("current_hp"), 0), max(1, safe_int(enemy.get("max_hp"), 1))
    if kind == "hp_percent": actual = current * 100 / maximum
    elif kind == "hp_value": actual = current
    elif kind == "rounds": actual = safe_int(battle.get("round_number"), 1)
    elif kind == "level_difference": actual = safe_int(player.get("level"), 1) - safe_int(enemy.get("level"), 1)
    elif kind == "alone": return len(alive_enemies(battle)) == 1
    elif kind in {"leader_dead", "boss_dead", "summoner_dead", "allies_dead"}:
        role = kind.removesuffix("_dead")
        return not any(safe_int(row.get("current_hp"), 0) > 0 and (row.get("role") == role or role in str(row.get("constructor_rank") or "")) for row in battle.get("enemies") or [])
    elif kind in {"has_effect", "missing_effect"}:
        effects = {str(row.get("effect_id") or row.get("id") or row) for row in enemy.get("effects") or []}
        return (str(value) in effects) == (kind == "has_effect")
    elif kind == "phase": return str(battle.get("phase") or enemy.get("phase") or "") == str(value)
    elif kind == "scenario": return bool(rule.get("scenario_active", True))
    else: return bool(battle.get(kind) or enemy.get(kind))
    try: expected = float(value or 0)
    except (TypeError, ValueError): expected = 0
    operator = str(rule.get("operator") or ("<=" if kind.startswith("hp_") else ">="))
    return {"<": actual < expected, "<=": actual <= expected, ">": actual > expected, ">=": actual >= expected, "==": actual == expected, "!=": actual != expected}.get(operator, False)


def process_mob_escape(player: dict[str, Any], battle: dict[str, Any], rng: random.Random, log: list[str], trigger: str = "end_player_turn") -> dict[str, Any]:
    """Executes authored individual/group/scenario retreat rules for living mobs."""
    profile = battle.get("combat_profile") if isinstance(battle.get("combat_profile"), dict) else {}
    rules = profile.get("mob_escape_rules") or []
    escaped: list[dict[str, Any]] = []
    result = "victory"
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("enabled", True): continue
        timing = str(rule.get("check_timing") or "end_player_turn")
        if timing not in {trigger, "each_turn", "any"}: continue
        interval = max(1, safe_int(rule.get("check_interval"), 1))
        if safe_int(battle.get("round_number"), 1) % interval: continue
        mob_id, group_id = str(rule.get("mob_id") or ""), str(rule.get("group_id") or "")
        candidates = [row for row in alive_enemies(battle) if (not mob_id or str(row.get("source_mob_id") or row.get("mob_id") or "") == mob_id) and (not group_id or str(row.get("group_id") or "") == group_id)]
        if not candidates: continue
        anchors = candidates if str(rule.get("mode") or "individual") == "individual" else candidates[:1]
        for anchor in anchors:
            if not _escape_condition(rule, anchor, battle, player): continue
            log.append(_profile_text(battle, "mob_escape_attempt", str(rule.get("attempt_text") or "{mob} пытается сбежать."), mob=anchor.get("name")))
            chance = float(rule.get("chance") if rule.get("chance") is not None else 100)
            if rule.get("formula_id"):
                from services.formula_runtime import evaluate
                chance = float(evaluate(rule["formula_id"], {"mob_hp": anchor.get("current_hp", 0), "mob_hp_percent": safe_int(anchor.get("current_hp"), 0) * 100 / max(1, safe_int(anchor.get("max_hp"), 1)), "round": battle.get("round_number", 1), "player_level": player.get("level", 1)}, default=chance))
            if rng.uniform(0, 100) > max(0, min(100, chance)):
                log.append(str(rule.get("fail_text") or f"{anchor.get('name')} не удалось сбежать.")); continue
            can_stop = bool(rule.get("player_can_stop")) or (bool(rule.get("npc_can_stop")) and any(safe_int(row.get("current_hp"), 0) > 0 for row in battle.get("allies") or [] if isinstance(row, dict)))
            if can_stop:
                stop_chance = float(rule.get("stop_chance") or 0)
                if rule.get("stop_formula_id"):
                    from services.formula_runtime import evaluate
                    stop_chance = float(evaluate(rule["stop_formula_id"], {"player_level": player.get("level", 1), "round": battle.get("round_number", 1)}, default=stop_chance))
                if rng.uniform(0, 100) <= max(0, min(100, stop_chance)):
                    log.append(str(rule.get("stop_text") or f"Побег {anchor.get('name')} остановлен.")); continue
            targets = candidates if str(rule.get("mode") or "individual") in {"group", "scenario", "boss_retreat"} else [anchor]
            for target in targets:
                if target in escaped: continue
                target["escaped"] = True; target["current_hp"] = 0
                target["escape_reward_policy"] = {key: rule.get(key) for key in ("cancel_rewards", "xp_factor", "coin_factor", "drop_factor", "quest_counts", "achievement_counts")}
                escaped.append(target)
            log.append(str(rule.get("success_text") or rule.get("group_text") or f"{anchor.get('name')} сбегает из боя."))
            event_id = str(rule.get("event_id") or "")
            if event_id: battle["post_escape_event_id"] = event_id
            future_id = str(rule.get("future_encounter_id") or "")
            if future_id: player.setdefault("future_encounters", {})[future_id] = True
            reinforcement = str(rule.get("reinforcement_mob_id") or "")
            if reinforcement:
                try:
                    from services.world_runtime import get_published, registry
                    mob = get_published(registry.KIND_MOB, reinforcement)
                    if mob: battle.setdefault("enemies", []).append(hydrate_constructor_enemy(asdict(build_constructor_enemy(mob, safe_int(mob.get("level"), 1), len(battle.get("enemies") or []))), reinforcement, mob))
                except Exception: logger.exception("Could not summon escape reinforcement %s", reinforcement)
            result = str(rule.get("boss_result") if str(rule.get("mode")) == "boss_retreat" else rule.get("all_escaped_result") or "victory")
    return {"escaped": escaped, "all_gone": not alive_enemies(battle), "result": result}


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


def _item_name_for(item_id: str) -> str:
    try:
        from services.item_registry import get_item_definition_by_id
        definition = get_item_definition_by_id(item_id)
        return str((definition or {}).get("name") or item_id)
    except Exception:
        return item_id


def _constructor_mob_drop(source_mob_id: str) -> list[tuple[str, str, Any, Any, Any]]:
    """Опубликованный drop конструкторного моба → (item_id, name, chance, min, max).

    Конструкторный враг несёт source_mob_id; его карточка хранит таблицу drop
    (item_id/chance/min_count/max_count). Без этого бой брал лут только из
    хардкод-каталога по имени, и конструкторные мобы не давали свою добычу."""
    try:
        from services import world_content_registry as wcr
        env = wcr.get_content(wcr.KIND_MOB, str(source_mob_id))
    except Exception:
        return []
    if not isinstance(env, dict) or env.get("status") != "published":
        return []
    rows: list[tuple[str, str, Any, Any, Any]] = []
    for row in (env.get("data") or {}).get("drop") or []:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "").strip()
        if not item_id:
            continue
        name = str(row.get("name") or "").strip() or _item_name_for(item_id)
        cmin = row.get("min_count") or 1
        rows.append((item_id, name, row.get("chance") or 0, cmin, row.get("max_count") or cmin))
    return rows


def _enemy_loot_table(enemy: dict[str, Any], catalog: dict[str, Any]) -> list[tuple[str, str, Any, Any, Any]]:
    """Таблица лута врага: опубликованный drop конструкторного моба в приоритете,
    иначе — легаси-каталог по имени. Кортежи: (item_id, name, chance, min, max)."""
    source_mob_id = enemy.get("source_mob_id")
    authored=enemy.get("constructor_drop_rows") or []
    if authored:
        return [(str(row.get("item_id") or ""),str(row.get("name") or row.get("item_id") or ""),row.get("chance") or 0,row.get("min_count") or 1,row.get("max_count") or row.get("min_count") or 1) for row in authored if isinstance(row,dict) and row.get("item_id")]
    if source_mob_id:
        drop = _constructor_mob_drop(str(source_mob_id))
        if drop:
            return drop
    template_key = next((key for key, value in catalog.items() if value["name"] == enemy.get("name")), "")
    return [
        ("", name, chance, min_amount, max_amount)
        for name, chance, min_amount, max_amount in catalog.get(template_key, {}).get("loot", [])
    ]


def apply_mob_win_reward(player:dict[str,Any],enemy:dict[str,Any])->list[str]:
    mob_id=str(enemy.get("source_mob_id") or "");wins=player.setdefault("mob_victories",{});first=safe_int(wins.get(mob_id),0)==0;raw=enemy.get("first_win_reward" if first else "repeat_win_reward");wins[mob_id]=safe_int(wins.get(mob_id),0)+1
    if not raw:return []
    if isinstance(raw,str):
        try:raw=json.loads(raw)
        except Exception:return [raw]
    rows=raw if isinstance(raw,list) else [raw];lines=[]
    for row in rows:
        if not isinstance(row,dict):continue
        kind=str(row.get("type") or "item");amount=max(1,safe_int(row.get("amount"),1));object_id=str(row.get("object_id") or row.get("item_id") or "")
        if kind=="item" and object_id:
            result=add_inventory_item(player,object_id,amount,item_id=object_id);lines.append(str(row.get("text") or f"Особая награда: {object_id} ×{result.added}"))
        elif kind in {"coins","currency"}:
            try:
                from services.economy_runtime import change,reward_amount
                amount=reward_amount("mob",amount,{"mob_id":mob_id,"first_win":int(first)});change(player,"copper",amount,operation="mob_special_reward",source="mob",source_id=mob_id)
            except (ImportError,ValueError):
                key="money_copper" if "money_copper" in player else "money";player[key]=safe_int(player.get(key),0)+amount
                if key=="money_copper":player["money"]=player[key]
            lines.append(str(row.get("text") or f"Особая награда: {amount} монет"))
    return lines


def grant_battle_rewards(player: dict[str, Any], battle: dict[str, Any], rng: random.Random) -> str:
    try:
        from services.npc_ally_runtime import record_battle
        record_battle(player, battle, victory=True)
    except Exception:
        pass
    from services.item_effect_trigger_runtime import trigger_equipped
    trigger_equipped(player, "after_battle", context={"victory": 1}, rng=rng)
    enemies = battle.get("enemies", [])
    defeated_enemies = [row for row in enemies if not row.get("escaped")]
    source_npc_id=str(battle.get("source_npc_id") or "")
    if source_npc_id:
        try:
            from services.world_runtime import get_published,registry
            npc=get_published(registry.KIND_NPC,source_npc_id) or {}
            for enemy in enemies:enemy.setdefault("constructor_drop_rows",[]).extend(dict(row) for row in npc.get("combat_drop") or [] if isinstance(row,dict))
            fine_id=str(npc.get("kill_fine_id") or "")
            if fine_id:
                from services.fine_service import create_raid_fine
                create_raid_fine(player,fine_id)
            for consequence in npc.get("kill_consequences") or []:
                if not isinstance(consequence,dict):continue
                if consequence.get("type") in {"reputation","hidden_reputation"}:
                    bucket=player.setdefault("hidden_reputations" if consequence.get("type")=="hidden_reputation" else "reputations",{});oid=str(consequence.get("object_id") or "");bucket[oid]=safe_int(bucket.get(oid),0)+safe_int(consequence.get("amount"),0)
            if npc.get("combat_reward"):
                for enemy in enemies:enemy["first_win_reward"]=npc.get("combat_reward")
        except Exception:logger.exception("Failed to apply NPC combat consequences for %s",source_npc_id)
    player_level = max(1, safe_int(player.get("level"), 1))
    reward_location_id = battle_return_location(battle)
    try:
        from services.world_event_runtime import modifiers as world_modifiers
        world_mods = world_modifiers(context={"location_id": reward_location_id, "game_id": player.get("game_id"), "level": player.get("level", 1)})
    except Exception:
        world_mods = {"drop_multiplier": 1.0, "resource_multiplier": 1.0, "exp_multiplier": 1.0, "reward_multiplier": 1.0}
    catalog = mob_catalog(reward_location_id)
    xp_total = 0
    coins_total=0
    loot_lines: list[str] = []
    # Конструктор локаций §18/§22/§23: при победе списываем недельный запас
    # мобов и дропа. Активно только при включённом WORLD_CONSTRUCTOR_LIVE и для
    # конструкторных боёв (враг несёт mob_id) — легаси-враги дают no-op.
    try:
        from services import location_runtime as _loc_rt
    except Exception:
        _loc_rt = None
    for enemy in enemies:
        escape_policy = enemy.get("escape_reward_policy") if isinstance(enemy.get("escape_reward_policy"), dict) else {}
        if enemy.get("escaped") and escape_policy.get("cancel_rewards"):
            continue
        xp_factor = float(escape_policy.get("xp_factor") if escape_policy.get("xp_factor") is not None else (0 if enemy.get("escaped") else 1))
        coin_factor = float(escape_policy.get("coin_factor") if escape_policy.get("coin_factor") is not None else (0 if enemy.get("escaped") else 1))
        drop_factor = float(escape_policy.get("drop_factor") if escape_policy.get("drop_factor") is not None else (0 if enemy.get("escaped") else 1))
        rank = enemy_rank(enemy)
        level = max(1, safe_int(enemy.get("level"), 1))
        rank_xp = RANK_MULTIPLIERS.get(rank, RANK_MULTIPLIERS[EnemyRank.NORMAL])["xp"]
        base_xp = safe_int(enemy.get("authored_experience"),0) or math.ceil((20 + level * 12) * rank_xp)
        base_xp=math.ceil(base_xp*float(enemy.get("rank_reward_multiplier") or 1))
        difference = level - player_level
        if difference >= 0:
            diff_mult = min(2.5, 1 + difference * 0.04)
        else:
            diff_mult = max(0.1, 1 + difference * 0.08)
        calculated_xp = math.ceil(base_xp * diff_mult)
        if enemy.get("exp_formula_id"):
            from services.formula_runtime import evaluate
            calculated_xp = max(0, safe_int(evaluate(enemy.get("exp_formula_id"), {
                "mob_level": level, "player_level": player_level, "level_diff": difference,
                "base_amount": calculated_xp, "multiplier": diff_mult,
            }, default=calculated_xp), calculated_xp))
        xp_total += max(0, math.floor(calculated_xp * xp_factor))
        coin_min=safe_int(enemy.get("coins_min"),0);coin_max=max(coin_min,safe_int(enemy.get("coins_max"),0));authored=safe_int(enemy.get("authored_coins"),0)
        coins_total+=max(0, math.floor((rng.randint(coin_min,coin_max) if coin_max else authored) * coin_factor))
        for item_id_hint, item_name, chance, min_amount, max_amount in _enemy_loot_table(enemy, catalog):
            drop_meta=next((row for row in enemy.get("constructor_drop_rows") or [] if str(row.get("item_id") or "")==str(item_id_hint or "")),{})
            condition=str(drop_meta.get("condition") or "")
            if condition=="first_win" and safe_int((player.get("mob_victories") or {}).get(str(enemy.get("source_mob_id") or "")),0)>0:continue
            drop_limit=max(0,safe_int(drop_meta.get("drop_limit"),0));usage_key=f"{enemy.get('source_mob_id')}:{item_id_hint}";drop_usage=player.setdefault("mob_drop_usage",{})
            if drop_limit and safe_int(drop_usage.get(usage_key),0)>=drop_limit:continue
            loot_chance, loot_min, loot_max = loot_parameters_for_rank(rank, chance, min_amount, max_amount)
            loot_chance = min(100.0, loot_chance * float(world_mods.get("drop_multiplier", 1) or 0) * max(0, drop_factor))
            resolved_item_id = item_id_hint or battle_loot_item_id(reward_location_id, item_name)
            if resolved_item_id:
                from services.item_formula_runtime import drop_chance as item_drop_chance
                loot_chance = item_drop_chance(resolved_item_id, loot_chance, player=player, context={
                    "mob_level": level, "player_level": player_level, "level_diff": level - player_level,
                })
            if rng.uniform(0, 100) <= loot_chance:
                amount = max(1, math.floor(rng.randint(loot_min, loot_max) * float(world_mods.get("resource_multiplier", 1) or 0)))
                # Конструкторный drop несёт точный item_id; легаси-каталог — нет,
                # для него разрешаем id по имени с учётом локации.
                item_id = resolved_item_id
                add_result = add_inventory_item(player, item_name, amount, item_id=item_id)
                if add_result.added > 0:
                    if drop_limit:drop_usage[usage_key]=safe_int(drop_usage.get(usage_key),0)+add_result.added
                    if drop_meta.get("bind_on_receive"):
                        for inventory_row in reversed(player.get("inventory") or []):
                            if isinstance(inventory_row,dict) and str(inventory_row.get("item_id") or inventory_row.get("id") or "")==str(item_id):inventory_row["bound"]=True;break
                    note = inventory_add_result_notice(add_result, item_name)
                    loot_lines.append(str(drop_meta.get("drop_text") or f"{item_name} ×{add_result.added}{note}"))
                    if _loc_rt is not None and item_id:
                        try:
                            _loc_rt.consume_for_item(reward_location_id, item_id, add_result.added)
                        except Exception:
                            pass
                elif add_result.discarded > 0:
                    loot_lines.append(f"{item_name}: не поместилось ×{add_result.discarded}")
        try:
            from services.world_event_runtime import roll_special_loot
            source_id = str(enemy.get("source_mob_id") or enemy.get("mob_id") or enemy.get("id") or "")
            for special in roll_special_loot(player, "battle", location_id=reward_location_id, object_id=source_id, rng=rng):
                item_id = str(special.get("item_id") or "")
                amount = int(special.get("amount") or 0)
                if item_id and amount > 0:
                    from services.item_registry import build_inventory_item
                    result = add_inventory_item(player, build_inventory_item(item_id, amount, item_id=item_id), amount, item_id=item_id, default_source="Мировое событие")
                    loot_lines.append(f"Мировое событие: {item_id} ×{result.added}")
        except Exception:
            pass
        if not enemy.get("escaped"): loot_lines.extend(apply_mob_win_reward(player,enemy))
    # Списываем побеждённых мобов из недельного запаса локации. Берём именно
    # source_mob_id (конструкторный id), а не инстансный mob_id — у легаси-врагов
    # source_mob_id нет, поэтому для них это no-op.
    if _loc_rt is not None:
        for enemy in defeated_enemies:
            source_mob_id = enemy.get("source_mob_id")
            if source_mob_id:
                try:
                    _loc_rt.consume_for_mob(reward_location_id, str(source_mob_id), 1)
                except Exception:
                    pass

    group_count = max(1, len(defeated_enemies))
    xp_total = math.ceil(xp_total * max(0.55, 1 - ((group_count - 1) * 0.05)))
    # Global balance change: experience received from killing mobs is reduced by 20%.
    xp_total = max(1, math.floor(xp_total * 0.8)) if xp_total > 0 else 0
    if xp_total > 0:
        xp_total = max(1, math.floor(xp_total * float(world_mods.get("exp_multiplier", 1) or 0)))
    old_sword_xp_penalty = old_iron_sword_penalty_percent(player, "mob_xp_penalty_percent")
    if old_sword_xp_penalty and xp_total > 0:
        xp_total = max(1, math.floor(xp_total * (1 - old_sword_xp_penalty / 100)))
    progress = grant_experience(player, xp_total, source_type="mob_kill", context={
        "mob_count": len(enemies), "mob_level": max((safe_int(e.get("level"), 1) for e in enemies), default=1),
        "level_diff": max((safe_int(e.get("level"), 1) for e in enemies), default=1) - player_level,
    })
    player["pve_kills"] = safe_int(player.get("pve_kills"), 0) + len(defeated_enemies)
    try:
        from services.quest_runtime_service import progress as quest_progress
        from services.reputation_runtime_service import apply_trigger as reputation_trigger
        from services.achievement_engine import record_game_event
        for enemy in enemies:
            policy = enemy.get("escape_reward_policy") if isinstance(enemy.get("escape_reward_policy"), dict) else {}
            if enemy.get("escaped") and not (policy.get("quest_counts") or policy.get("achievement_counts")): continue
            target = str(enemy.get("source_mob_id") or enemy.get("mob_id") or enemy.get("id") or "")
            if not enemy.get("escaped") or policy.get("quest_counts"): quest_progress(player, "kill_mob", target, 1)
            if not enemy.get("escaped"): reputation_trigger(player, "mob_kill", target)
            if not enemy.get("escaped") or policy.get("achievement_counts"): record_game_event(player, "kill_mob", 1, target)
            from services.event_campaign_runtime import progress as event_progress
            event_progress(player, "kill_mob", target, 1)
            if enemy_rank(enemy) in (EnemyRank.ELITE, EnemyRank.MINI_BOSS, EnemyRank.BOSS, EnemyRank.RAID_BOSS):
                quest_progress(player, "kill_boss", target, 1)
                record_game_event(player, "kill_boss", 1, target)
                event_progress(player, "kill_boss", target, 1)
        record_game_event(player, "gain_experience", progress["gained"])
        record_game_event(player, "reach_level", progress["level"])
        record_game_event(player, "finish_pve", 1)
        record_game_event(player, "win_battle", 1, "pve")
    except Exception:
        pass
    if coins_total>0:
        try:
            from services.economy_runtime import change, reward_amount
            coins_total=reward_amount("battle",coins_total,{"mob_count":len(enemies),"player_level":player_level})
            change(player,"copper",coins_total,operation="battle_reward",source="pve",source_id=str(battle.get("battle_id") or ""))
        except (ImportError, ValueError):
            money_key="money_copper" if "money_copper" in player else "money";player[money_key]=safe_int(player.get(money_key),0)+coins_total
            if money_key=="money_copper" and "money" in player:player["money"]=player[money_key]
    rewards = [f"Опыт: +{progress['gained']}"]
    if coins_total:rewards.append(f"Монеты: +{coins_total}")
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
    profile = battle.get("combat_profile") if isinstance(battle.get("combat_profile"), dict) else {}
    for row in profile.get("victory_rewards") or []:
        if not isinstance(row, dict) or rng.uniform(0, 100) > float(row.get("chance") or 100): continue
        kind, object_id, amount = str(row.get("type") or "item"), str(row.get("object_id") or ""), max(1, safe_int(row.get("amount"), 1))
        if kind == "item" and object_id: add_inventory_item(player, object_id, amount, item_id=object_id)
        elif kind in {"coins", "currency"}: player["money"] = safe_int(player.get("money"), 0) + amount
        elif kind in {"experience", "xp"}: grant_experience(player, amount, source_type="pve_victory")
        elif kind == "effect" and object_id:
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player, object_id, source="pve_victory")
        rewards.append(str(row.get("text") or f"Награда боя: {object_id or kind} ×{amount}"))
    if profile.get("victory_event_id"): player["constructor_event_id"] = str(profile["victory_event_id"])
    try:
        from services.bot_message_queue import release_waiting
        release_waiting(str(player.get("game_id") or ""),"battle")
    except Exception:pass
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
    acting_enemies=[enemy for enemy in alive_enemies(battle) for _ in range(max(1,safe_int(enemy.get("actions_per_turn"),1)))]
    for enemy in acting_enemies:
        if safe_int(enemy.get("current_hp"),0)<=0:continue
        apply_constructor_phase(enemy,battle,log)
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
    from services.effect_runtime_service import advance_turn as advance_effect_turn

    player_state = battle.setdefault("player_state", {})
    for resource in ("hp", "mana", "spirit"):
        current_key = f"current_{resource}"
        if current_key in player_state:
            player[resource] = player_state[current_key]
        if f"max_{resource}" in player_state:
            player[f"max_{resource}"] = player_state[f"max_{resource}"]
    effect_report = advance_effect_turn(player)
    for resource in ("hp", "mana", "spirit"):
        if resource in player:
            player_state[f"current_{resource}"] = player[resource]
    if effect_report["ticks"]:
        total = sum(int(row.get("delta") or 0) for row in effect_report["ticks"])
        log.append(f"⏱ Периодические эффекты срабатывают ({total:+d}).")
    if effect_report["removed"]:
        log.append("⌛ Временный эффект завершился.")
    from services.item_effect_trigger_runtime import trigger_equipped
    trigger_equipped(player, "on_battle_turn", context={"round": battle.get("round_number", 1)}, rng=rng)
    apply_enemy_status_effects(battle, log)
    from services.effect_runtime_service import combat_flags
    authored_flags = combat_flags(player)
    if safe_int(player_state.get("invulnerable_turns"), 0) > 0 or authored_flags.get("invulnerable"):
        # One-turn invulnerability (e.g. Last Chance artifact resurrection).
        player_state["invulnerable_turns"] = safe_int(player_state.get("invulnerable_turns"), 0) - 1
        log.append("✨ Неуязвимость: весь урон этого хода заблокирован.")
        battle["round_number"] = safe_int(battle.get("round_number"), 1) + 1
        battle["last_turn_log"] = log[:]
        battle.setdefault("battle_log", []).extend(log)
        sync_player_from_battle(player, battle)
        return False
    for enemy in alive_enemies(battle):
        from services.combat_group_runtime import choose_enemy_target, damage_ally
        ally_target = choose_enemy_target(battle, rng)
        from services.skill_action_runtime import choose_mob_skill
        mob_skill = choose_mob_skill(enemy, rng)
        target_dodge = safe_int((ally_target or player_state).get("dodge"), 1)
        hit_chance = calculate_hit_chance(safe_int(enemy.get("accuracy"), 1), target_dodge)
        if rng.random() > hit_chance:
            log.append(f"{enemy.get('name')} промахивается.")
            continue
        raw = enemy_raw_damage(enemy)
        if mob_skill:
            from services.formula_runtime import evaluate, numeric_context
            raw = max(0, safe_int(evaluate(mob_skill.get("damage_formula_id"), numeric_context({"base_amount": mob_skill.get("base_damage", raw), "mob_level": enemy.get("level", 1)}, player=player), default=mob_skill.get("base_damage", raw)), raw))
        if defending:
            raw = math.ceil(raw * 0.65)
        if ally_target is not None:
            damage_ally(ally_target, raw, log, str(enemy.get("name") or "Противник"))
            continue
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
        reflect_key = "reflect_magic_percent" if damage_type == DamageType.MAGIC else "reflect_physical_percent"
        reflected = round(final_damage * float(authored_flags.get(reflect_key) or 0) / 100)
        if reflected:
            enemy["current_hp"] = max(0, safe_int(enemy.get("current_hp"), 0) - reflected)
            log.append(f"↩️ Отражено {reflected} урона противнику.")
        trigger_equipped(player, "on_receive_damage", context={"base_amount": final_damage, "mob_level": enemy.get("level", 1)}, rng=rng)
        log.append(f"{enemy.get('name')} применяет «{mob_skill.get('name')}» и наносит {final_damage} урона." if mob_skill else f"{enemy.get('name')} атакует и наносит {final_damage} урона.")
        if mob_skill and mob_skill.get("apply_effect_id"):
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player, str(mob_skill.get("apply_effect_id")), source="mob_skill", context={"mob_id": enemy.get("source_mob_id")})
        for effect in enemy.get("constructor_effects") or []:
            if str(effect.get("trigger") or "on_attack") not in {"on_attack","on_hit","attack","hit"}:continue
            if rng.uniform(0,100)>max(0,min(100,float(effect.get("chance") or 100))):continue
            effect_id=str(effect.get("effect_id") or "")
            if effect_id:
                from services.effect_formula_runtime import apply_to_player
                apply_to_player(player,effect_id,source="constructor_mob_effect",context={"mob_id":enemy.get("source_mob_id"),"duration_turns":effect.get("duration")})

    for enemy in alive_enemies(battle):
        for passive in enemy.get("constructor_passives") or []:
            ptype=str(passive.get("passive_type") or passive.get("name") or "").lower()
            if ptype in {"regeneration","regen","регенерация","регенерирующий"}:
                amount=max(0,safe_int(passive.get("value"),0));before=safe_int(enemy.get("current_hp"),0);enemy["current_hp"]=min(safe_int(enemy.get("max_hp"),before),before+amount)
                if enemy["current_hp"]>before:log.append(f"{enemy.get('name')} восстанавливает {enemy['current_hp']-before} HP.")

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
    from services.item_effect_trigger_runtime import trigger_equipped
    try:
        from services.npc_ally_runtime import record_battle
        record_battle(player, battle, victory=False)
    except Exception:
        pass
    trigger_equipped(player, "on_death"); trigger_equipped(player, "after_battle", context={"victory": 0})
    try:
        from services.quest_runtime_service import progress as quest_progress
        quest_progress(player,"death","pve",1)
    except Exception:pass
    player["in_battle"] = False
    player["active_battle"] = None
    player["active_event"] = None
    death_location_id = move_player_to_death_camp(player, battle)
    player["hp"] = max(1, math.ceil(safe_int(player.get("max_hp"), 100) * 0.2))
    profile = battle.get("combat_profile") if isinstance(battle.get("combat_profile"), dict) else {}
    consequences = [row for row in profile.get("defeat_consequences") or [] if isinstance(row, dict)]
    xp_percent = next((safe_int(row.get("percent"), 10) for row in consequences if row.get("type") in {"experience", "xp"}), 10)
    penalty = apply_death_experience_penalty(player, xp_percent)
    for row in consequences:
        kind, amount = str(row.get("type") or ""), max(0, safe_int(row.get("amount"), 0))
        if kind in {"coins", "currency"}: player["money"] = max(0, safe_int(player.get("money"), 0) - amount)
        elif kind == "effect" and row.get("object_id"):
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player, str(row["object_id"]), source="pve_defeat")
    if profile.get("defeat_event_id"): player["constructor_event_id"] = str(profile["defeat_event_id"])
    player_name = battle_player_name(battle)
    penalty_text = "Штраф смерти: опыт не потерян."
    if penalty["lost"] > 0:
        penalty_text = f"Штраф смерти: -{penalty['lost']} опыта (-10%)."
    from services.text_runtime import game_text
    defeat_text = _profile_text(battle, "defeat", game_text("battle.defeat", f"❌ {player_name} проигрывает бой и отступает в лагерь локации. HP частично восстановлено."), player=player_name)
    try:
        from services.bot_message_queue import release_waiting
        release_waiting(str(player.get("game_id") or ""),"battle")
    except Exception:pass
    return (
        "\n".join(log)
        + f"\n\n{defeat_text}\n{penalty_text}"
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
        from services.text_runtime import game_text
        return f"{game_text('battle.victory', 'Победа!')}\n\n{rewards}", []

    from services.effect_runtime_service import combat_flags
    authored_flags = combat_flags(player)
    if authored_flags.get("skip_turn") and action not in {BATTLE_POUCH, BATTLE_POUCH_NEXT, BATTLE_POUCH_PREV} and not action.startswith("Предмет "):
        log = [authored_flags.get("trigger_text") or "💫 Оглушение: ход пропущен."]
        defeated = apply_enemy_phase(player, battle, rng, log)
        if defeated:
            return finish_player_defeat(player, battle, log)
        return format_battle_status(battle), battle_buttons(player)

    if action.startswith("Приказ: "):
        profile = battle.get("combat_profile") if isinstance(battle.get("combat_profile"), dict) else {}
        labels = {"Атаковать": "auto", "Защищать": "protect_player", "Лечить": "heal_allies",
                  "Использовать навык": "random_skill", "Ждать": "wait", "Сменить цель": "weakest", "Отступить": "retreat"}
        if not profile.get("allow_ally_commands") or not (battle.get("allies") or []):
            return str(profile.get("command_error_text") or "Сейчас некому отдать приказ."), battle_buttons(player)
        command = action.removeprefix("Приказ: ").strip()
        behavior = labels.get(command)
        if not behavior:
            return str(profile.get("command_error_text") or "Этот приказ недоступен."), battle_buttons(player)
        for ally in battle.get("allies") or []:
            if safe_int(ally.get("current_hp"), 0) > 0:
                ally["behavior"] = behavior
                if behavior == "retreat" and ally.get("can_escape"):
                    ally["current_hp"] = 0
        text = str(profile.get("command_text") or "Приказ союзникам принят.")
        battle.setdefault("battle_log", []).append(text)
        player["active_battle"] = battle
        if profile.get("command_uses_action"):
            log = [text]
            defeated = apply_enemy_phase(player, battle, rng, log)
            if defeated:
                return finish_player_defeat(player, battle, log)
        return format_battle_status(battle), battle_buttons(player)

    # If a player selected a skill and then presses any other battle button,
    # cancel the stale target prompt. This prevents a later «Цель: N» click from
    # firing an old skill after opening the pouch, waiting, or choosing another
    # action.
    if battle.get("pending_skill") and not action.startswith("Цель: "):
        battle.pop("pending_skill", None)

    if action in {BATTLE_ESCAPE, "Отступить"}:
        profile = battle.get("combat_profile") if isinstance(battle.get("combat_profile"), dict) else {}
        if profile.get("player_escape_allowed") is False or battle.get("can_escape") is False or any(enemy.get("escape_forbidden") for enemy in alive_enemies(battle)):
            return "🚫 От этого противника нельзя сбежать.",battle_buttons(player)
        if player.get("inventory_overflow_no_escape"):
            return "🎒 Вы перегружены: при 4+ занятых доп. слотах нельзя сбежать от противника.", battle_buttons(player)
        decrement_cooldowns_once_at_player_turn(battle, player_state)
        authored=(safe_int(profile.get("player_escape_chance"), -1) if profile.get("player_escape_chance") is not None else -1)
        if authored < 0: authored=min([safe_int(enemy.get("player_escape_chance"),40) for enemy in alive_enemies(battle)] or [40])
        if profile.get("player_escape_formula_id"):
            from services.formula_runtime import evaluate
            authored=safe_int(evaluate(profile["player_escape_formula_id"], {"player_level": player.get("level", 1), "round": battle.get("round_number", 1)}, default=authored), authored)
        authored=authored/100
        escape_chance = min(0.95, max(0,authored) + safe_int(player_state.get("escape_bonus_chance_percent"), 0) / 100)
        if rng.random() < escape_chance:
            player["in_battle"] = False
            player["active_battle"] = None
            player["active_event"] = None
            move_player_to_battle_return_location(player, battle)
            return _profile_text(battle, "player_escape_success", f"🏃 {player_name} находит просвет между противниками и сбегает. Бой завершён без награды.", player=player_name), []
        log = [_profile_text(battle, "player_escape_fail", f"🏃 {player_name} пытается сбежать, но противники отрезают путь. Ход пропущен.", player=player_name)]
        if profile.get("player_escape_attack_on_fail") is False:
            player["active_battle"] = battle
            return format_battle_status(battle), battle_buttons(player)
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
            from services.text_runtime import game_text
            return f"{chr(10).join(log)}\n\n{game_text('battle.victory', '✅ Победа!')}\n\n{rewards}", []
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
            from services.text_runtime import game_text
            return f"{chr(10).join(log)}\n\n{game_text('battle.victory', '✅ Победа!')}\n\n{rewards}", []
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
    if equipped_skill is not None:
        from services.skill_action_runtime import can_use
        allowed, denied_text = can_use(player, equipped_skill, in_battle=True)
        if not allowed:
            return denied_text, battle_buttons(player)
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
    utility_used = False
    if equipped_skill is not None:
        from services.skill_action_runtime import NON_DAMAGE_ACTIONS, action_type, apply_non_damage, cooldown_turns
        if action_type(equipped_skill) in NON_DAMAGE_ACTIONS:
            spirit_cost, mana_cost = skill_costs(equipped_skill, player)
            if spirit_cost > safe_int(player_state.get("current_spirit"), 0):
                return f"🔥 Не хватает духа для навыка «{equipped_skill.get('name')}». Нужно: {spirit_cost}.", battle_buttons(player)
            if mana_cost > safe_int(player_state.get("current_mana"), 0):
                return f"✨ Не хватает маны для навыка «{equipped_skill.get('name')}». Нужно: {mana_cost}.", battle_buttons(player)
            ammo_ok, ammo_message = consume_skill_ammo(player, equipped_skill)
            if not ammo_ok:
                return f"🏹 {ammo_message}", battle_buttons(player)
            player_state["current_spirit"] = max(0, safe_int(player_state.get("current_spirit"), 0) - spirit_cost)
            player_state["current_mana"] = max(0, safe_int(player_state.get("current_mana"), 0) - mana_cost)
            player["spirit"] = player_state["current_spirit"]
            player["mana"] = player_state["current_mana"]
            outcome = apply_non_damage(player, equipped_skill)
            for resource in ("hp", "mana", "spirit"):
                if resource in player:
                    player_state[f"current_{resource}"] = safe_int(player.get(resource), player_state.get(f"current_{resource}"))
            cooldown_key = str(equipped_skill.get("id") or equipped_skill.get("name"))
            cooldown = cooldown_turns(player, equipped_skill)
            if cooldown:
                player_state.setdefault("cooldowns", {})[cooldown_key] = cooldown
            log.append(f"{player_name} применяет «{equipped_skill.get('name')}». {outcome['text']}")
            utility_used = True
    defending = action == BATTLE_DEFEND
    waiting = action == BATTLE_WAIT or utility_used
    if defending:
        log.append(f"{player_name} занимает защитную стойку. Входящий урон в этом ходе снижен.")
    elif waiting and not utility_used:
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
            from services.skill_action_runtime import cooldown_turns
            cooldown = cooldown_turns(player, equipped_skill)
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
            from services.effect_runtime_service import combat_flags
            is_crit = not combat_flags(player).get("disable_critical") and crit_chance > 0 and rng.random() * 100 < crit_chance
            if is_crit:
                final_damage = max(1, math.ceil(final_damage * crit_damage / 100))
            final_damage=max(0,math.ceil(final_damage*constructor_damage_multiplier(target,damage_type,player)))
            target["current_hp"] = max(0, safe_int(target.get("current_hp"), 0) - final_damage)
            crit_suffix = " 💥 Критический удар!" if is_crit else ""
            log.append(f"{player_name} бьёт {action_text}: {target.get('name')} получает {final_damage} урона.{crit_suffix}")
            if damage_type in {DamageType.PHYSICAL, DamageType.MIXED}:
                maybe_apply_old_sword_on_hit(player, battle, target, rng, log)
        else:
            log.append(f"{player_name} промахивается: {target.get('name')} успевает уйти с линии атаки.")

    from services.combat_group_runtime import apply_ally_phase
    apply_ally_phase(battle, rng, log)

    escape_outcome = process_mob_escape(player, battle, rng, log)

    if not alive_enemies(battle):
        battle.setdefault("battle_log", []).extend(log)
        sync_player_from_battle(player, battle)
        player["in_battle"] = False
        player["active_battle"] = None
        player["active_event"] = None
        move_player_to_battle_return_location(player, battle)
        outcome = str(escape_outcome.get("result") or "victory")
        rewards = "Награды не начислены."
        if outcome not in {"draw", "defeat", "cancel"}:
            rewards = grant_battle_rewards(player, battle, rng)
        event_id = str(battle.get("post_escape_event_id") or "")
        if event_id:
            player["constructor_event_id"] = event_id
        from services.text_runtime import game_text
        default_result = game_text('battle.victory', '✅ Победа!') if outcome not in {"draw", "defeat", "cancel"} else "🤝 Бой завершён без победителя."
        result_text = _profile_text(battle, f"mob_escape_{outcome}", default_result)
        return f"{chr(10).join(log)}\n\n{result_text}\n\n{rewards}", []

    defeated = apply_enemy_phase(player, battle, rng, log, defending=defending)
    if defeated:
        return finish_player_defeat(player, battle, log)

    player["active_battle"] = battle
    return format_battle_status(battle), battle_buttons(player)
