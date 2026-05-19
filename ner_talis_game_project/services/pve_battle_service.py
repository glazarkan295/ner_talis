"""Runnable PVE battle service for Telegram/VK exploration events.

The module integrates the uploaded PVE battle data structures into the existing
project. It keeps the first implementation intentionally compact: random PVE
encounters in «Холмистые луга» become real turn-based battles, but the API is
stable enough to later replace damage/AI/skill formulas with the full combat
system.
"""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import asdict
from typing import Any

from services.item_registry import build_inventory_item, get_item_definition_by_name
from services.progression_service import grant_experience
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

BATTLE_ACTIONS = frozenset({BATTLE_ATTACK, BATTLE_MAGIC_SPARK, BATTLE_DEFEND, BATTLE_POUCH, BATTLE_ESCAPE, "Отступить"})
BATTLE_BUTTONS = [[BATTLE_ATTACK, BATTLE_DEFEND], [BATTLE_POUCH, BATTLE_ESCAPE]]

RANK_MULTIPLIERS = {
    EnemyRank.NORMAL: {"hp": 1.0, "damage": 1.0, "accuracy": 1.0, "dodge": 1.0, "defense": 1.0, "xp": 1.0},
    EnemyRank.EMPOWERED: {"hp": 1.45, "damage": 1.35, "accuracy": 1.18, "dodge": 1.1, "defense": 1.25, "xp": 1.7},
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


def battle_buttons(player: dict[str, Any] | None = None) -> list[list[str]]:
    rows = [row[:] for row in BATTLE_BUTTONS]
    skills = ((player or {}).get("skills") or {}).get("equipped", []) if isinstance((player or {}).get("skills"), dict) else []
    skill_names = [str(skill.get("name") or skill.get("id")) for skill in skills if isinstance(skill, dict)]
    for index in range(0, len(skill_names), 2):
        rows.append(skill_names[index:index + 2])
    return rows


def target_buttons(battle: dict[str, Any]) -> list[list[str]]:
    rows = [[f"Цель: {index + 1}" for index, _enemy in enumerate(alive_enemies(battle))]]
    rows.extend(battle_buttons())
    return rows


def soft_level(level: int) -> int:
    return int(math.floor(10 * math.log2(max(1, level) + 1)))


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _player_stat(player: dict[str, Any], key: str) -> float:
    stats = player.get("stats") or {}
    invested = player.get("invested_stats") or {}
    bonuses = player.get("stat_bonuses") or {}
    raw = safe_int(stats.get(key), 0) + safe_int(invested.get(key), 0)
    return raw * stat_multiplier(player, key) + safe_int(bonuses.get(key), 0)


def calculate_player_derived_stats(player: dict[str, Any]) -> dict[str, int]:
    """Small local copy of the project formulas, enough for PVE state creation."""
    level = max(1, safe_int(player.get("level"), 1))
    s_level = soft_level(level)
    strength = _player_stat(player, "strength")
    endurance = _player_stat(player, "endurance")
    dexterity = _player_stat(player, "dexterity")
    perception = _player_stat(player, "perception")
    intelligence = _player_stat(player, "intelligence")
    wisdom = _player_stat(player, "wisdom")

    equipment_armor = 0
    equipment_magic_armor = 0
    bonus_hp = safe_int(player.get("bonus_hp"), 0)
    bonus_spirit = safe_int(player.get("bonus_spirit"), 0)
    bonus_mana = safe_int(player.get("bonus_mana"), 0)
    bonus_accuracy = safe_int(player.get("bonus_accuracy"), 0)
    bonus_dodge = safe_int(player.get("bonus_dodge"), 0)
    bonus_physical_defense = safe_int(player.get("bonus_physical_defense"), 0)
    bonus_magic_defense = safe_int(player.get("bonus_magic_defense"), 0)

    for item in (player.get("equipment") or {}).values():
        if not isinstance(item, dict):
            continue
        mods = item.get("stat_modifiers") or {}
        equipment_armor += safe_int(mods.get("armor"), 0)
        equipment_magic_armor += safe_int(mods.get("magic_armor"), 0)
        bonus_hp += safe_int(mods.get("bonus_hp"), 0)
        bonus_spirit += safe_int(mods.get("bonus_spirit"), 0)
        bonus_mana += safe_int(mods.get("bonus_mana"), 0)
        bonus_accuracy += safe_int(mods.get("bonus_accuracy"), 0)
        bonus_dodge += safe_int(mods.get("bonus_dodge"), 0)
        bonus_physical_defense += safe_int(mods.get("bonus_physical_defense"), 0)
        bonus_magic_defense += safe_int(mods.get("bonus_magic_defense"), 0)

    armor = max(0, safe_int(player.get("armor"), 0) + equipment_armor)
    magic_armor = max(0, safe_int(player.get("magic_armor"), 0) + equipment_magic_armor)
    max_hp = math.ceil((100 + endurance * 4.0 + strength * 0.8 + s_level * 4 + bonus_hp) * hp_multiplier(player))
    max_spirit = math.ceil(20 + endurance * 1.2 + strength * 1.0 + dexterity * 0.7 + s_level * 1.2 + bonus_spirit)
    max_mana = math.ceil(20 + intelligence * 1.6 + wisdom * 1.3 + s_level * 1.2 + bonus_mana)
    physical_defense = math.ceil(armor * 1.5 + endurance * 0.9 + strength * 0.6 + dexterity * 0.2 + bonus_physical_defense)
    magic_defense = math.ceil((magic_armor if magic_armor else armor * 0.8) + wisdom * 0.9 + intelligence * 0.6 + endurance * 0.2 + bonus_magic_defense)
    accuracy = math.ceil(perception * 1.8 + dexterity * 1.1 + s_level * 0.7 + bonus_accuracy)
    dodge = math.ceil(dexterity * 1.8 + perception * 0.9 + wisdom * 0.3 + s_level * 0.5 + bonus_dodge)
    return {
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
        "strength": strength,
        "intelligence": intelligence,
        "perception": perception,
    }


def ensure_player_resources(player: dict[str, Any]) -> dict[str, int]:
    stats = calculate_player_derived_stats(player)
    for current_key, max_key in (("hp", "max_hp"), ("spirit", "max_spirit"), ("mana", "max_mana")):
        max_value = stats[max_key]
        player[max_key] = max_value
        if player.get(current_key) is None:
            player[current_key] = max_value
        player[current_key] = max(0, min(max_value, safe_int(player.get(current_key), max_value)))
    return stats


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


def choose_battle_rank(rng: random.Random, player_level: int = 1) -> EnemyRank:
    roll = rng.uniform(0, 100)
    if player_level <= 3:
        if roll <= 92:
            return EnemyRank.NORMAL
        return EnemyRank.EMPOWERED
    if roll <= 78:
        return EnemyRank.NORMAL
    if roll <= 96:
        return EnemyRank.EMPOWERED
    return EnemyRank.ELITE


def enemy_level_for_rank(player_level: int, rank: EnemyRank, rng: random.Random) -> int:
    if player_level <= 3:
        if rank == EnemyRank.NORMAL:
            return max(1, min(50, player_level + rng.randint(-1, 0)))
        if rank == EnemyRank.EMPOWERED:
            return max(1, min(50, player_level + rng.randint(1, 2)))
        return max(1, min(50, player_level + rng.randint(3, 4)))
    if rank == EnemyRank.NORMAL:
        return max(1, min(50, player_level + rng.randint(-1, 1)))
    if rank == EnemyRank.EMPOWERED:
        return max(1, min(50, player_level + rng.randint(3, 5)))
    return max(1, min(50, player_level + rng.randint(7, 9)))


def choose_mob_key(rank: EnemyRank, rng: random.Random, player_level: int = 1) -> str:
    if rank == EnemyRank.ELITE:
        return "hill_bull"
    if rank == EnemyRank.EMPOWERED:
        if player_level <= 3:
            return rng.choice(["overgrown_gopher", "wild_jackal", "rabid_rabbit"])
        return rng.choice(["overgrown_gopher", "wild_jackal", "rabid_rabbit", "hill_bull"])
    return rng.choice(["overgrown_gopher", "wild_jackal", "rabid_rabbit"])


def build_enemy(mob_key: str, rank: EnemyRank, level: int, index: int) -> EnemyBattleState:
    template = HILLY_MEADOWS_MOBS[mob_key]
    mult = RANK_MULTIPLIERS[rank]
    base_hp = 28 + level * 8
    if mob_key == "hill_bull":
        base_hp = 70 + level * 14
    elif mob_key == "rabid_rabbit":
        base_hp = 20 + level * 6
    max_hp = max(1, math.ceil(base_hp * mult["hp"]))
    armor = math.ceil(level * (1.0 if mob_key != "hill_bull" else 2.2) * mult["defense"])
    physical_defense = math.ceil(armor * 1.5 + level * 1.4 * mult["defense"])
    magic_defense = math.ceil(level * 0.8 * mult["defense"])
    accuracy = math.ceil((18 + level * 2.1) * mult["accuracy"])
    dodge_base = 14 + level * (1.7 if mob_key != "hill_bull" else 0.8)
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


def create_hilly_meadows_battle(player: dict[str, Any], rng: random.Random | None = None) -> tuple[dict[str, Any], str]:
    rng = rng or random.Random()
    player_level = max(1, safe_int(player.get("level"), 1))
    rank = choose_battle_rank(rng, player_level)
    mob_key = choose_mob_key(rank, rng, player_level)
    template = HILLY_MEADOWS_MOBS[mob_key]
    min_count, max_count = template["group"][rank]
    if player_level <= 3:
        min_count = 1
        max_count = 1 if rank != EnemyRank.NORMAL else min(2, max_count)
    count = 1 if rank == EnemyRank.ELITE else rng.randint(min_count, max_count)
    enemies = [build_enemy(mob_key, rank, enemy_level_for_rank(player_level, rank, rng), index + 1) for index in range(count)]
    battle = BattleState(
        battle_id=f"pve_{uuid.uuid4().hex[:12]}",
        player_id=str(player.get("game_id") or player.get("id") or "player"),
        location_id=str(player.get("location_id") or player.get("current_location") or "hilly_meadows"),
        battle_type="random_event",
        round_number=1,
        player_state=make_player_battle_state(player),
        enemies=enemies,
        can_escape=True,
        battle_log=[template["text"]],
    )
    battle_dict = serialize_battle(battle)
    player["active_battle"] = battle_dict
    player["active_event"] = None
    player["in_battle"] = True
    player["current_zone"] = "hilly_meadows_battle"
    player["location_id"] = "hilly_meadows_battle"
    sync_player_from_battle(player, battle_dict)
    return battle_dict, format_battle_started_text(battle_dict)


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
    return [enemy for enemy in battle.get("enemies", []) if safe_int(enemy.get("current_hp"), 0) > 0]


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
    stats = calculate_player_derived_stats(player)
    damage = skill.get("damage")
    if not isinstance(damage, (int, float)):
        if skill.get("id") == "magic_spark" or str(skill.get("name")) == BATTLE_MAGIC_SPARK:
            damage = math.ceil(4 + stats["level"] * 1.1 + stats["intelligence"] * 0.8)
        else:
            damage = math.ceil(5 + stats["level"] * 1.2 + stats["strength"] * 0.8)
    damage_type = skill_damage_type(skill)
    damage = math.ceil(float(damage) * outgoing_damage_multiplier(player, damage_type.value))
    return max(1, safe_int(damage, 1)), damage_type, str(skill.get("name") or "навыком")


def is_food_item(item: dict[str, Any]) -> bool:
    category = str(item.get("category") or item.get("type") or item.get("subtype") or "").casefold()
    item_class = str(item.get("item_class") or "").casefold()
    tags = {str(tag).casefold() for tag in item.get("integration_tags", []) if isinstance(tag, str)}
    return bool(
        "еда" in category
        or "напит" in category
        or "food" in category
        or "drink" in category
        or item_class == "camp_food"
        or "food" in tags
        or "energy_restore" in tags
        or item.get("energy_restore")
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
        player_state[current_key] = min(maximum, before + restore)
        actual = player_state[current_key] - before
        if actual:
            restored_parts.append(f"+{actual} {current_key.removeprefix('current_')}")
    if not restored_parts:
        return f"🎒 {item_name} сейчас не даёт боевого эффекта.", False
    remove_inventory_item_by_name(player, item_name, 1)
    return f"🎒 Вы использовали {item_name}: " + ", ".join(restored_parts) + ".", True


def sync_player_from_battle(player: dict[str, Any], battle: dict[str, Any]) -> None:
    player_state = battle.get("player_state") or {}
    for battle_key, player_key in (("current_hp", "hp"), ("max_hp", "max_hp"), ("current_spirit", "spirit"), ("max_spirit", "max_spirit"), ("current_mana", "mana"), ("max_mana", "max_mana")):
        if battle_key in player_state:
            player[player_key] = safe_int(player_state.get(battle_key), safe_int(player.get(player_key), 0))


def format_enemy_line(enemy: dict[str, Any]) -> str:
    hp = max(0, safe_int(enemy.get("current_hp"), 0))
    max_hp = max(1, safe_int(enemy.get("max_hp"), 1))
    rank = ENEMY_RANK_LABELS.get(str(enemy.get("rank") or "normal"), str(enemy.get("rank") or "обычный"))
    damage_type = DAMAGE_TYPE_LABELS.get(str(enemy.get("damage_type") or "physical"), str(enemy.get("damage_type") or "физический"))
    return (
        f"• {enemy.get('name')} ур. {enemy.get('level')} — ❤️ {hp}/{max_hp}\n"
        f"  Тип: {rank} · Урон: {damage_type}\n"
        f"  🎯 {safe_int(enemy.get('accuracy'), 0)} · 🌀 {safe_int(enemy.get('dodge'), 0)} · "
        f"🛡 {safe_int(enemy.get('physical_defense'), 0)} · ✨ {safe_int(enemy.get('magic_defense'), 0)}"
    )


def format_battle_started_text(battle: dict[str, Any]) -> str:
    intro = battle.get("battle_log", ["Начался бой."])[0]
    enemy_lines = "\n".join(format_enemy_line(enemy) for enemy in battle.get("enemies", []))
    player_state = battle.get("player_state") or {}
    return (
        f"⚔️ Бой начался!\n{intro}\n\n"
        f"Ход: {battle.get('round_number', 1)}.\n\n"
        f"🧍 Вы:\n"
        f"❤️ {player_state.get('current_hp')}/{player_state.get('max_hp')} · "
        f"🔥 {player_state.get('current_spirit')}/{player_state.get('max_spirit')} · "
        f"✨ {player_state.get('current_mana')}/{player_state.get('max_mana')}\n"
        f"🎯 {player_state.get('accuracy')} · 🌀 {player_state.get('dodge')} · "
        f"🛡 {player_state.get('physical_defense')} · ✨🛡 {player_state.get('magic_defense')}\n"
        f"Тип урона: физический/магический по выбранному действию\n\n"
        f"👹 Противники:\n{enemy_lines}"
    )


def format_battle_status(battle: dict[str, Any]) -> str:
    enemy_lines = "\n".join(format_enemy_line(enemy) for enemy in battle.get("enemies", [])) or "• врагов не осталось"
    player_state = battle.get("player_state") or {}
    last_log = "\n".join(battle.get("last_turn_log") or battle.get("battle_log", [])[-4:]) or "—"
    return (
        f"⚔️ PVE-бой. Ход: {battle.get('round_number', 1)}.\n\n"
        f"🧍 Вы:\n"
        f"❤️ {player_state.get('current_hp')}/{player_state.get('max_hp')} · "
        f"🔥 {player_state.get('current_spirit')}/{player_state.get('max_spirit')} · "
        f"✨ {player_state.get('current_mana')}/{player_state.get('max_mana')}\n"
        f"🎯 Точность: {player_state.get('accuracy')} · 🌀 Уклонение: {player_state.get('dodge')}\n"
        f"🛡 Физ. защита: {player_state.get('physical_defense')} · ✨ Маг. защита: {player_state.get('magic_defense')}\n"
        f"Тип урона: зависит от выбранного действия\n\n"
        f"👹 Противники:\n{enemy_lines}\n\n"
        f"📜 Действие прошлого хода:\n{last_log}"
    )


def grant_battle_rewards(player: dict[str, Any], battle: dict[str, Any], rng: random.Random) -> str:
    enemies = battle.get("enemies", [])
    player_level = max(1, safe_int(player.get("level"), 1))
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
        template_key = next((key for key, value in HILLY_MEADOWS_MOBS.items() if value["name"] == enemy.get("name")), "")
        for item_name, chance, min_amount, max_amount in HILLY_MEADOWS_MOBS.get(template_key, {}).get("loot", []):
            if rng.uniform(0, 100) <= chance:
                amount = rng.randint(min_amount, max_amount)
                add_inventory_item(player, item_name, amount)
                loot_lines.append(f"{item_name} ×{amount}")
    group_count = max(1, len(enemies))
    xp_total = math.ceil(xp_total * max(0.55, 1 - ((group_count - 1) * 0.05)))
    progress = grant_experience(player, xp_total)
    player["pve_kills"] = safe_int(player.get("pve_kills"), 0) + len(enemies)
    rewards = [f"Опыт: +{progress['gained']}"]
    if progress["levels_gained"]:
        rewards.append(
            f"Новый уровень: {player.get('level')} "
            f"(+{progress['levels_gained'] * 5} очков характеристик, +{progress['levels_gained']} очков навыков)"
        )
    if loot_lines:
        rewards.append("Добыча: " + ", ".join(loot_lines))
    else:
        rewards.append("Добыча: ничего")
    return "\n".join(rewards)


def add_inventory_item(player: dict[str, Any], item_name: str, amount: int) -> None:
    if amount <= 0:
        return
    definition = get_item_definition_by_name(item_name)
    inventory_item = build_inventory_item(item_name, amount)
    item_id = inventory_item.get("id")
    max_stack = max(1, safe_int(inventory_item.get("max_stack"), 999))
    remaining = amount
    inventory = player.setdefault("inventory", [])
    for item in inventory:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or item.get("item_id")) != str(item_id):
            continue
        current = safe_int(item.get("amount"), 1)
        free = max_stack - current
        if free <= 0:
            continue
        added = min(free, remaining)
        item["amount"] = current + added
        item.setdefault("icon", inventory_item.get("icon"))
        item.setdefault("asset_icon", inventory_item.get("asset_icon"))
        remaining -= added
        if remaining <= 0:
            return
    while remaining > 0:
        added = min(max_stack, remaining)
        new_item = build_inventory_item(item_name, added, item_id=str(item_id), max_stack=max_stack)
        if definition:
            new_item.setdefault("source", "PVE-бой")
        inventory.append(new_item)
        remaining -= added


def apply_enemy_phase(
    player: dict[str, Any],
    battle: dict[str, Any],
    rng: random.Random,
    log: list[str],
    *,
    defending: bool = False,
) -> bool:
    player_state = battle.setdefault("player_state", {})
    for enemy in alive_enemies(battle):
        hit_chance = calculate_hit_chance(safe_int(enemy.get("accuracy"), 1), safe_int(player_state.get("dodge"), 1))
        if rng.random() > hit_chance:
            log.append(f"{enemy.get('name')} промахивается.")
            continue
        raw = enemy_raw_damage(enemy)
        if defending:
            raw = math.ceil(raw * 0.65)
        final_damage = calculate_final_damage(
            raw_damage=raw,
            damage_type=enemy_damage_type(enemy),
            target_physical_defense=safe_int(player_state.get("physical_defense"), 0),
            target_magic_defense=safe_int(player_state.get("magic_defense"), 0),
            target_soft_level=soft_level(safe_int(player.get("level"), 1)),
            damage_split=enemy_damage_split(enemy),
        )
        if enemy_damage_type(enemy) == DamageType.PHYSICAL:
            final_damage = max(1, math.ceil(final_damage * incoming_physical_damage_multiplier(player)))
        player_state["current_hp"] = max(0, safe_int(player_state.get("current_hp"), 0) - final_damage)
        log.append(f"{enemy.get('name')} атакует и наносит {final_damage} урона.")

    if safe_int(player_state.get("current_hp"), 0) > 0:
        regen_percent = combat_hp_regen_percent(player)
        if regen_percent > 0:
            maximum = max(1, safe_int(player_state.get("max_hp"), 1))
            before = safe_int(player_state.get("current_hp"), maximum)
            restored = max(1, math.ceil(maximum * regen_percent / 100))
            player_state["current_hp"] = min(maximum, before + restored)
            actual = player_state["current_hp"] - before
            if actual > 0:
                log.append(f"Регенерация восстанавливает {actual} HP.")

    cooldowns = player_state.setdefault("cooldowns", {})
    for key in list(cooldowns.keys()):
        cooldowns[key] = max(0, safe_int(cooldowns.get(key), 0) - 1)
        if cooldowns[key] <= 0:
            cooldowns.pop(key, None)

    battle["round_number"] = safe_int(battle.get("round_number"), 1) + 1
    return safe_int(player_state.get("current_hp"), 0) <= 0


def finish_player_defeat(player: dict[str, Any], battle: dict[str, Any], log: list[str]) -> tuple[str, list[list[str]]]:
    sync_player_from_battle(player, battle)
    player["in_battle"] = False
    player["active_battle"] = None
    player["active_event"] = None
    player["current_zone"] = "hilly_meadows"
    player["location_id"] = "hilly_meadows"
    player["hp"] = max(1, math.ceil(safe_int(player.get("max_hp"), 100) * 0.2))
    return "\n".join(log) + "\n\n❌ Вы проиграли бой и отступили к безопасному месту. HP частично восстановлено.", []


def handle_battle_action(player: dict[str, Any], action: str, rng: random.Random | None = None) -> tuple[str, list[list[str]]]:
    rng = rng or random.Random()
    battle = player.get("active_battle")
    if not player.get("in_battle") or not isinstance(battle, dict):
        player["in_battle"] = False
        player["active_battle"] = None
        return "Активного боя нет.", []

    if action in {BATTLE_ESCAPE, "Отступить"}:
        player["in_battle"] = False
        player["active_battle"] = None
        player["active_event"] = None
        player["current_zone"] = "hilly_meadows"
        player["location_id"] = "hilly_meadows"
        return "Вы отступаете и разрываете дистанцию. Бой завершён без награды.", []

    player_state = battle.setdefault("player_state", {})
    enemies = alive_enemies(battle)
    if not enemies:
        player["in_battle"] = False
        player["active_battle"] = None
        player["active_event"] = None
        rewards = grant_battle_rewards(player, battle, rng)
        return f"Победа!\n\n{rewards}", []

    if action == BATTLE_POUCH:
        return format_pouch(player)

    if action.startswith("Использовать: "):
        item_name = action.removeprefix("Использовать: ").strip()
        message, consumed = use_pouch_item(player, battle, item_name)
        log = [message]
        if consumed and alive_enemies(battle):
            if apply_enemy_phase(player, battle, rng, log, defending=False):
                battle["last_turn_log"] = log[:]
                battle.setdefault("battle_log", []).extend(log)
                return finish_player_defeat(player, battle, log)
        battle["last_turn_log"] = log
        battle.setdefault("battle_log", []).extend(log)
        player["active_battle"] = battle
        sync_player_from_battle(player, battle)
        return format_battle_status(battle), battle_buttons(player)

    pending_skill = battle.get("pending_skill") if isinstance(battle.get("pending_skill"), dict) else None
    target_index: int | None = None
    if action.startswith("Цель: ") and pending_skill:
        raw_target = action.removeprefix("Цель: ").strip().split()[0]
        try:
            target_index = max(0, int(raw_target) - 1)
        except ValueError:
            target_index = 0
        action = str(pending_skill.get("name") or pending_skill.get("id") or action)
        battle.pop("pending_skill", None)

    equipped_skill = get_equipped_skill(player, action)
    if equipped_skill is not None and target_index is None and len(enemies) > 1:
        battle["pending_skill"] = equipped_skill
        player["active_battle"] = battle
        return f"🎯 Выберите противника для навыка «{equipped_skill.get('name')}».", target_buttons(battle)

    log: list[str] = []
    defending = action == BATTLE_DEFEND
    if defending:
        log.append("Вы занимаете защитную стойку. Входящий урон в этом ходе снижен.")
    else:
        target = enemies[target_index] if target_index is not None and 0 <= target_index < len(enemies) else enemies[0]
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
            log.append(f"Вы бьёте {action_text}: {target.get('name')} получает {final_damage} урона.")
        else:
            log.append(f"Вы промахиваетесь: {target.get('name')} успевает уйти с линии атаки.")

    if not alive_enemies(battle):
        battle.setdefault("battle_log", []).extend(log)
        sync_player_from_battle(player, battle)
        player["in_battle"] = False
        player["active_battle"] = None
        player["active_event"] = None
        player["current_zone"] = "hilly_meadows"
        player["location_id"] = "hilly_meadows"
        rewards = grant_battle_rewards(player, battle, rng)
        return f"{chr(10).join(log)}\n\n✅ Победа!\n\n{rewards}", []

    defeated = apply_enemy_phase(player, battle, rng, log, defending=defending)
    battle["last_turn_log"] = log[:]
    battle.setdefault("battle_log", []).extend(log)
    sync_player_from_battle(player, battle)

    if defeated:
        return finish_player_defeat(player, battle, log)

    player["active_battle"] = battle
    return format_battle_status(battle), battle_buttons(player)
