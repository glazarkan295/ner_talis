"""Runnable PVE battle service for Telegram/VK exploration events.

The module integrates the uploaded PVE battle data structures into the existing
project. It keeps the first implementation intentionally compact: random PVE
encounters in external locations become real turn-based battles, but the API is
stable enough to later replace damage/AI/skill formulas with the full combat
system.
"""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import asdict
from typing import Any

from services.derived_stats_service import calculate_player_derived_stats, calculate_player_skill_raw_damage, ensure_player_resources, safe_int, soft_level
from services.item_registry import build_inventory_item, get_item_definition_by_name
from services.inventory_service import add_inventory_item as add_inventory_stack, recalculate_inventory_overflow
from services.progression_service import apply_death_experience_penalty, grant_experience
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

# В интерфейсе боя показываются только подсумок, побег и экипированные активные навыки.
# Обычная атака и защита оставлены как внутренние fallback-действия для старых сохранений.
BATTLE_ACTIONS = frozenset({BATTLE_POUCH, BATTLE_ESCAPE, BATTLE_WAIT, "Отступить"})


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
        "role": "attacker",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (2, 5), EnemyRank.EMPOWERED: (2, 4), EnemyRank.ELITE: (1, 1)},
        "skills": ["Укус", "Рывок из норы"],
        "features": ["Стайный инстинкт"],
        "text": "Земля впереди начинает шевелиться. Из нор выбираются крупные суслики с непропорционально большими зубами.",
        "loot": [("Маленькая шкура", 60, 1, 1), ("Кусочек мяса", 50, 1, 1), ("Острый зуб", 20, 1, 1), ("Коготок суслика", 10, 1, 1)],
    },
    "wild_jackal": {
        "name": "Дикий шакал",
        "biological_type": "beast",
        "role": "attacker",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 4), EnemyRank.EMPOWERED: (1, 3), EnemyRank.ELITE: (1, 1)},
        "skills": ["Укус", "Рывок"],
        "features": ["Прыжок хищника"],
        "text": "Из-за холма доносится низкое рычание. Из травы выходят дикие шакалы, отрезая путь назад.",
        "loot": [("Шкура шакала", 70, 1, 1), ("Клык шакала", 25, 1, 1), ("Жёсткое сухожилие", 20, 1, 1), ("Сырое мясо", 60, 1, 2)],
    },
    "rabid_rabbit": {
        "name": "Бешеный кролик",
        "biological_type": "beast",
        "role": "attacker",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 1), EnemyRank.EMPOWERED: (1, 1), EnemyRank.ELITE: (1, 1)},
        "skills": ["Резкий прыжок", "Укус"],
        "features": ["Прыжок хищника"],
        "text": "Из высокой травы выскакивает кролик. Мутные глаза и пена у пасти быстро меняют первое впечатление.",
        "loot": [("Маленькая шкурка", 60, 1, 1), ("Сырое мясо", 50, 1, 1), ("Зуб бешеного кролика", 15, 1, 1)],
    },
    "hill_bull": {
        "name": "Бык",
        "biological_type": "beast",
        "role": "defender",
        "damage_type": DamageType.PHYSICAL,
        "damage_split": DamageSplit(physical=100, magic=0),
        "group": {EnemyRank.NORMAL: (1, 1), EnemyRank.EMPOWERED: (1, 1), EnemyRank.ELITE: (1, 1)},
        "skills": ["Удар рогами", "Тяжёлый рывок"],
        "features": ["Толстая шкура"],
        "text": "На соседнем склоне пасётся огромный бык. Зверь резко поднимает голову и начинает рыть землю копытом.",
        "loot": [("Плотная шкура", 75, 1, 1), ("Сырое мясо", 80, 1, 3), ("Бычий рог", 25, 1, 1), ("Крепкое сухожилие", 25, 1, 1)],
    },
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
        "loot": [("Сырое мясо", 60, 1, 2), ("Волчья шкура", 65, 1, 1), ("Волчий клык", 25, 1, 1), ("Жёсткое сухожилие", 20, 1, 1)],
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
        "loot": [("Сырое мясо", 70, 1, 2), ("Оленья шкура", 60, 1, 1), ("Рог оленя", 30, 1, 1), ("Крепкое сухожилие", 25, 1, 1)],
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
        "loot": [("Сырое мясо", 75, 1, 3), ("Кабанья шкура", 65, 1, 1), ("Кабаний клык", 30, 1, 1), ("Жир зверя", 25, 1, 1)],
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
        "loot": [("Сырое мясо", 85, 1, 3), ("Медвежья шкура", 75, 1, 1), ("Медвежий коготь", 35, 1, 1), ("Медвежий клык", 30, 1, 1), ("Жир зверя", 25, 1, 1)],
        "hp_base": 90,
        "hp_per_level": 16,
        "armor_factor": 2.4,
        "dodge_per_level": 0.7,
        "damage_bonus_per_level": 1.3,
    },
}

BATTLE_MOB_CATALOGS = {
    "hilly_meadows": HILLY_MEADOWS_MOBS,
    "ordinary_forest": ORDINARY_FOREST_MOBS,
}



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
    )


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


def choose_battle_rank(rng: random.Random, player_level: int = 1, location_id: str = "hilly_meadows") -> EnemyRank:
    location_id = normalize_battle_location(location_id)
    roll = rng.uniform(0, 100)
    if location_id == "ordinary_forest":
        if roll <= 72:
            return EnemyRank.NORMAL
        if roll <= 94:
            return EnemyRank.EMPOWERED
        return EnemyRank.ELITE
    if player_level <= 3:
        if roll <= 92:
            return EnemyRank.NORMAL
        return EnemyRank.EMPOWERED
    if roll <= 74:
        return EnemyRank.NORMAL
    if roll <= 95:
        return EnemyRank.EMPOWERED
    return EnemyRank.ELITE


def enemy_level_for_rank(player_level: int, rank: EnemyRank, rng: random.Random, *, cap: int = 50) -> int:
    if player_level <= 3:
        if rank == EnemyRank.NORMAL:
            return max(1, min(cap, player_level + rng.randint(-1, 0)))
        if rank == EnemyRank.EMPOWERED:
            return max(1, min(cap, player_level + rng.randint(1, 2)))
        return max(1, min(cap, player_level + rng.randint(3, 4)))
    if rank == EnemyRank.NORMAL:
        return max(1, min(cap, player_level + rng.randint(-1, 1)))
    if rank == EnemyRank.EMPOWERED:
        return max(1, min(cap, player_level + rng.randint(3, 5)))
    return max(1, min(cap, player_level + rng.randint(7, 9)))


def choose_mob_key(rank: EnemyRank, rng: random.Random, player_level: int = 1, location_id: str = "hilly_meadows") -> str:
    location_id = normalize_battle_location(location_id)
    if location_id == "ordinary_forest":
        if rank == EnemyRank.ELITE:
            return "forest_bear"
        if rank == EnemyRank.EMPOWERED:
            choices = ["forest_wolf", "angry_deer", "forest_boar"]
            if player_level >= 4:
                choices.append("forest_bear")
            return rng.choice(choices)
        return rng.choice(["forest_wolf", "angry_deer", "forest_boar"])
    if rank == EnemyRank.ELITE:
        return "hill_bull"
    if rank == EnemyRank.EMPOWERED:
        if player_level <= 3:
            return rng.choice(["overgrown_gopher", "wild_jackal", "rabid_rabbit"])
        return rng.choice(["overgrown_gopher", "wild_jackal", "rabid_rabbit", "hill_bull"])
    return rng.choice(["overgrown_gopher", "wild_jackal", "rabid_rabbit"])


def build_enemy(mob_key: str, rank: EnemyRank, level: int, index: int, location_id: str = "hilly_meadows") -> EnemyBattleState:
    catalog = mob_catalog(location_id)
    if mob_key not in catalog:
        catalog = HILLY_MEADOWS_MOBS
    template = catalog[mob_key]
    mult = RANK_MULTIPLIERS[rank]
    base_hp = int(template.get("hp_base", 28)) + level * int(template.get("hp_per_level", 8))
    if mob_key == "hill_bull":
        base_hp = 70 + level * 14
    elif mob_key == "rabid_rabbit":
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
    magic_defense = math.ceil(level * 0.8 * mult["defense"])
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
    enemies = [
        build_enemy(mob_key, rank, enemy_level_for_rank(player_level, rank, rng, cap=cap), index + 1, location_id)
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
    if enemy.get("name") == "Бык":
        base += level * 1.2
    if enemy.get("name") == "Медведь":
        base += level * 1.3
    if enemy.get("name") == "Кабан":
        base += level * 0.7
    return max(1, math.ceil(base * mult["damage"]))


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
    skills = player.get("skills") if isinstance(player.get("skills"), dict) else {}
    for skill in skills.get("equipped", []):
        if not isinstance(skill, dict):
            continue
        if str(skill.get("name") or skill.get("id") or "") == action or str(skill.get("id") or "") == action:
            return skill
    return None


def skill_costs(skill: dict[str, Any]) -> tuple[int, int]:
    spirit = safe_int(skill.get("spirit_cost") if "spirit_cost" in skill else skill.get("spiritCost"), 0)
    mana = safe_int(skill.get("mana_cost") if "mana_cost" in skill else skill.get("manaCost"), 0)
    return max(0, spirit), max(0, mana)


def skill_damage_type(skill: dict[str, Any]) -> DamageType:
    raw = str(skill.get("damage_type") or skill.get("damageType") or "physical").casefold()
    if "маг" in raw or raw == "magic":
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
    category = str(item.get("category") or item.get("type") or "")
    allowed_categories = {"Алхимия", "Расходник", "Расходники"}
    return category in allowed_categories or combat_restore_amount(item) > 0


def pouch_items(player: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in player.get("inventory", []):
        if not isinstance(item, dict):
            continue
        if is_combat_pouch_item(item):
            result.append(item)
    return result


def format_pouch(player: dict[str, Any]) -> tuple[str, list[list[str]]]:
    items = pouch_items(player)
    if not items:
        return "🎒 Подсумок пуст. В инвентаре нет зелий или расходников для боя.", battle_buttons(player)
    lines = ["🎒 Подсумок", "", "Можно использовать один расходник за ход:"]
    buttons: list[list[str]] = []
    for item in items[:10]:
        name = str(item.get("name") or "Предмет")
        amount = safe_int(item.get("amount"), 1)
        lines.append(f"• {name} ×{amount}")
        buttons.append([f"Использовать: {name}"])
    buttons.extend(battle_buttons(player))
    return "\n".join(lines), buttons


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


def use_pouch_item(player: dict[str, Any], battle: dict[str, Any], item_name: str) -> tuple[str, bool]:
    source_item = next((item for item in player.get("inventory", []) if isinstance(item, dict) and str(item.get("name") or "") == item_name), None)
    if source_item is None:
        return "🎒 Такого предмета нет в подсумке.", False
    if not is_combat_pouch_item(source_item):
        return "🎒 Этот предмет нельзя использовать в бою.", False

    player_state = battle.setdefault("player_state", {})
    restored_parts: list[str] = []
    updated_values: dict[str, int] = {}
    # Common consumable fields. Energy is outside combat, so combat shows only HP/spirit/mana effects.
    for current_key, max_key, labels in (("current_hp", "max_hp", ("restore_hp", "hp_restore")), ("current_spirit", "max_spirit", ("restore_spirit", "spirit_restore")), ("current_mana", "max_mana", ("restore_mana", "mana_restore"))):
        restore = 0
        for label in labels:
            restore = max(restore, safe_int(source_item.get(label), 0))
            effect = source_item.get("use_effect") if isinstance(source_item.get("use_effect"), dict) else {}
            restore = max(restore, safe_int(effect.get(label), 0))
        if restore <= 0:
            continue
        before = safe_int(player_state.get(current_key), 0)
        maximum = max(1, safe_int(player_state.get(max_key), before))
        after = min(maximum, before + restore)
        actual = after - before
        if actual:
            updated_values[current_key] = after
            restored_parts.append(f"+{actual} {current_key.removeprefix('current_')}")
    if not restored_parts:
        return f"🎒 {item_name} сейчас не даёт боевого эффекта.", False
    remove_inventory_item_by_name(player, item_name, 1)
    player_state.update(updated_values)
    return f"🎒 {player_display_name(player)} использует {item_name}: " + ", ".join(restored_parts) + ".", True


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


def format_battle_started_text(battle: dict[str, Any]) -> str:
    intro = battle.get("battle_log", ["Начался бой."])[0]
    enemy_lines = "\n".join(format_enemy_line(enemy, index + 1) for index, enemy in enumerate(battle.get("enemies", [])))
    player_state = battle.get("player_state") or {}
    player_name = battle_player_name(battle)
    return (
        f"⚔️ Бой начался!\n{intro}\n\n"
        f"Ход: {battle.get('round_number', 1)}.\n\n"
        f"🧍 {player_name}:\n"
        f"❤️ {player_state.get('current_hp')}/{player_state.get('max_hp')} · "
        f"🔥 {player_state.get('current_spirit')}/{player_state.get('max_spirit')} · "
        f"✨ {player_state.get('current_mana')}/{player_state.get('max_mana')}\n"
        f"🎯 {player_state.get('accuracy')} · 🌀 {player_state.get('dodge')} · "
        f"🛡 {player_state.get('physical_defense')} · ✨🛡 {player_state.get('magic_defense')}\n\n"
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


def grant_battle_rewards(player: dict[str, Any], battle: dict[str, Any], rng: random.Random) -> str:
    enemies = battle.get("enemies", [])
    player_level = max(1, safe_int(player.get("level"), 1))
    catalog = mob_catalog(battle_return_location(battle))
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
            if rng.uniform(0, 100) <= chance:
                amount = rng.randint(min_amount, max_amount)
                add_result = add_inventory_item(player, item_name, amount)
                if add_result.added > 0:
                    loot_lines.append(f"{item_name} ×{add_result.added}")
                if add_result.discarded > 0:
                    loot_lines.append(f"{item_name}: не поместилось ×{add_result.discarded}")
    group_count = max(1, len(enemies))
    xp_total = math.ceil(xp_total * max(0.55, 1 - ((group_count - 1) * 0.05)))
    # Global balance change: experience received from killing mobs is reduced by 20%.
    xp_total = max(1, math.floor(xp_total * 0.8)) if xp_total > 0 else 0
    progress = grant_experience(player, xp_total)
    player["pve_kills"] = safe_int(player.get("pve_kills"), 0) + len(enemies)
    rewards = [f"Опыт: +{progress['gained']}"]
    if progress["level_ups"]:
        rewards.append(
            f"Уровень повышен: {progress['level']} "
            f"(+{progress['level_ups'] * 5} очк. характеристик, +{progress['level_ups'] * 2} очк. навыков)"
        )
    if loot_lines:
        rewards.append("Добыча: " + ", ".join(loot_lines))
    else:
        rewards.append("Добыча: ничего")
    return "\n".join(rewards)


def add_inventory_item(player: dict[str, Any], item_name: str, amount: int):
    if amount <= 0:
        return add_inventory_stack(player, item_name, 0)
    definition = get_item_definition_by_name(item_name)
    inventory_item = build_inventory_item(item_name, amount)
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


def apply_enemy_phase(player: dict[str, Any], battle: dict[str, Any], rng: random.Random, log: list[str], *, defending: bool = False) -> bool:
    player_state = battle.setdefault("player_state", {})
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

    battle["round_number"] = safe_int(battle.get("round_number"), 1) + 1
    battle["last_turn_log"] = log[:]
    battle.setdefault("battle_log", []).extend(log)
    sync_player_from_battle(player, battle)
    return safe_int(player_state.get("current_hp"), 0) <= 0


def finish_player_defeat(player: dict[str, Any], battle: dict[str, Any], log: list[str]) -> tuple[str, list[list[str]]]:
    player["in_battle"] = False
    player["active_battle"] = None
    player["active_event"] = None
    move_player_to_battle_return_location(player, battle)
    player["hp"] = max(1, math.ceil(safe_int(player.get("max_hp"), 100) * 0.2))
    penalty = apply_death_experience_penalty(player, 10)
    player_name = battle_player_name(battle)
    penalty_text = "Штраф смерти: опыт не потерян."
    if penalty["lost"] > 0:
        penalty_text = f"Штраф смерти: -{penalty['lost']} опыта (-10%)."
    return (
        "\n".join(log)
        + f"\n\n❌ {player_name} проигрывает бой и отступает к безопасному месту. HP частично восстановлено.\n{penalty_text}"
    ), []


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
    if action in {BATTLE_ESCAPE, "Отступить"}:
        if player.get("inventory_overflow_no_escape"):
            return "🎒 Вы перегружены: при 4+ занятых доп. слотах нельзя сбежать от противника.", battle_buttons(player)
        player["in_battle"] = False
        player["active_battle"] = None
        player["active_event"] = None
        move_player_to_battle_return_location(player, battle)
        return f"{player_name} отступает и разрывает дистанцию. Бой завершён без награды.", []

    player_state = battle.setdefault("player_state", {})
    enemies = alive_enemies(battle)
    if not enemies:
        player["in_battle"] = False
        player["active_battle"] = None
        player["active_event"] = None
        move_player_to_battle_return_location(player, battle)
        rewards = grant_battle_rewards(player, battle, rng)
        return f"Победа!\n\n{rewards}", []

    if action == BATTLE_POUCH:
        return format_pouch(player)

    if action.startswith("Использовать: "):
        item_name = action.removeprefix("Использовать: ").strip()
        item_text, consumed = use_pouch_item(player, battle, item_name)
        log = [item_text]
        if consumed:
            defeated = apply_enemy_phase(player, battle, rng, log)
            if defeated:
                return finish_player_defeat(player, battle, log)
        else:
            battle["last_turn_log"] = log
            battle.setdefault("battle_log", []).extend(log)
            sync_player_from_battle(player, battle)
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
    if equipped_skill is not None and target_number is None and not skill_uses_without_target(equipped_skill):
        cooldown_key = str(equipped_skill.get("id") or equipped_skill.get("name"))
        cooldowns = player_state.setdefault("cooldowns", {})
        if safe_int(cooldowns.get(cooldown_key), 0) > 0:
            return f"⏳ Навык «{equipped_skill.get('name')}» ещё на откате: {cooldowns[cooldown_key]} ход.", battle_buttons(player)
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

    log: list[str] = []
    defending = action == BATTLE_DEFEND
    waiting = action == BATTLE_WAIT
    if equipped_skill is None and action in {BATTLE_DEFEND, BATTLE_ATTACK, BATTLE_MAGIC_SPARK, BATTLE_WAIT}:
        decrement_cooldowns_at_turn_start(player_state)
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
            spirit_cost, mana_cost = skill_costs(equipped_skill)
            cooldown_key = str(equipped_skill.get("id") or equipped_skill.get("name"))
            cooldowns = player_state.setdefault("cooldowns", {})
            if safe_int(cooldowns.get(cooldown_key), 0) > 0:
                return f"⏳ Навык «{equipped_skill.get('name')}» ещё на откате: {cooldowns[cooldown_key]} ход.", battle_buttons(player)
            if spirit_cost > safe_int(player_state.get("current_spirit"), 0):
                return f"🔥 Не хватает духа для навыка «{equipped_skill.get('name')}». Нужно: {spirit_cost}.", battle_buttons(player)
            if mana_cost > safe_int(player_state.get("current_mana"), 0):
                return f"✨ Не хватает маны для навыка «{equipped_skill.get('name')}». Нужно: {mana_cost}.", battle_buttons(player)
            player_state["current_spirit"] = max(0, safe_int(player_state.get("current_spirit"), 0) - spirit_cost)
            player_state["current_mana"] = max(0, safe_int(player_state.get("current_mana"), 0) - mana_cost)
            cooldown = safe_int(equipped_skill.get("cooldown_turns") if "cooldown_turns" in equipped_skill else equipped_skill.get("cooldown"), 0)
            if cooldown > 0:
                cooldowns[cooldown_key] = cooldown
            raw_damage, damage_type, action_text = player_skill_raw_damage(player, equipped_skill)
            action_text = f"навыком «{action_text}»"
        else:
            raw_damage, damage_type, action_text = player_attack_raw_damage(player, action)
        hit_chance = calculate_hit_chance(safe_int(player_state.get("accuracy"), 1), safe_int(target.get("dodge"), 1))
        if rng.random() <= hit_chance:
            final_damage = calculate_final_damage(
                raw_damage=raw_damage,
                damage_type=damage_type,
                target_physical_defense=safe_int(target.get("physical_defense"), 0),
                target_magic_defense=safe_int(target.get("magic_defense"), 0),
                target_soft_level=soft_level(safe_int(target.get("level"), 1)),
            )
            target["current_hp"] = max(0, safe_int(target.get("current_hp"), 0) - final_damage)
            log.append(f"{player_name} бьёт {action_text}: {target.get('name')} получает {final_damage} урона.")
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
