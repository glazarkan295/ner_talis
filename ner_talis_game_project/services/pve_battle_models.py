"""PVE battle models and helper formulas for Ner-Talis.

This module contains only the base combat data structures and safe helper
formulas. It does not use a separate Concentration parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Optional


class DamageType(str, Enum):
    PHYSICAL = "physical"
    MAGIC = "magic"
    MIXED = "mixed"


class EnemyRank(str, Enum):
    NORMAL = "normal"
    EMPOWERED = "empowered"
    ELITE = "elite"
    MINI_BOSS = "mini_boss"
    BOSS = "boss"
    RAID_BOSS = "raid_boss"


@dataclass(slots=True)
class DamageSplit:
    physical: int = 100
    magic: int = 0

    def validate(self) -> None:
        if self.physical < 0 or self.magic < 0:
            raise ValueError("Damage split values cannot be negative.")
        if self.physical + self.magic != 100:
            raise ValueError("Damage split must equal 100% in total.")


@dataclass(slots=True)
class BattleEffect:
    effect_id: str
    name: str
    effect_type: str
    duration_rounds: int
    power: int = 0
    source_id: str = ""
    can_stack: bool = False
    stack_count: int = 1
    max_stacks: int = 1
    remove_condition: Optional[str] = None


@dataclass(slots=True)
class Shield:
    shield_id: str
    value: int
    duration_rounds: int


@dataclass(slots=True)
class PlayerBattleState:
    current_hp: int
    max_hp: int
    current_spirit: int
    max_spirit: int
    current_mana: int
    max_mana: int
    armor: int
    magic_armor: int
    physical_defense: int
    magic_defense: int
    accuracy: int
    dodge: int
    crit_chance: int = 0
    crit_damage: int = 100
    temporary_shields: list[Shield] = field(default_factory=list)
    active_effects: list[BattleEffect] = field(default_factory=list)
    cooldowns: dict[str, int] = field(default_factory=dict)
    used_items: list[str] = field(default_factory=list)
    defense_stance: Optional[str] = None


@dataclass(slots=True)
class EnemyBattleState:
    mob_id: str
    name: str
    rank: EnemyRank
    biological_type: str
    role: str
    level: int
    damage_type: DamageType
    current_hp: int
    max_hp: int
    armor: int
    magic_armor: int
    physical_defense: int
    magic_defense: int
    accuracy: int
    dodge: int
    crit_chance: int = 0
    crit_damage: int = 100
    damage_split: DamageSplit = field(default_factory=DamageSplit)
    current_spirit: int = 0
    max_spirit: int = 0
    current_mana: int = 0
    max_mana: int = 0
    skills: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    active_effects: list[BattleEffect] = field(default_factory=list)
    cooldowns: dict[str, int] = field(default_factory=dict)
    ai_behavior: str = "aggressive"

    def validate_damage_type(self) -> None:
        if self.damage_type == DamageType.MIXED:
            self.damage_split.validate()
        elif self.damage_type == DamageType.PHYSICAL:
            self.damage_split = DamageSplit(physical=100, magic=0)
        elif self.damage_type == DamageType.MAGIC:
            self.damage_split = DamageSplit(physical=0, magic=100)


@dataclass(slots=True)
class BattleState:
    battle_id: str
    player_id: str
    location_id: str
    battle_type: str
    round_number: int
    player_state: PlayerBattleState
    enemies: list[EnemyBattleState]
    can_escape: bool = True
    battle_log: list[str] = field(default_factory=list)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def calculate_hit_chance(accuracy: int, target_dodge: int) -> float:
    """Return hit chance in the 0.10..0.95 range."""
    raw = accuracy / (accuracy + max(1, target_dodge))
    return clamp(raw, 0.10, 0.95)


def apply_defense(incoming_damage: int, defense: int, soft_level: int) -> int:
    """Apply physical or magical defense with the 70% reduction cap."""
    damage_reduction = min(0.70, defense / (defense + 300 + soft_level * 8))
    return max(1, ceil(incoming_damage * (1 - damage_reduction)))


def calculate_final_damage(
    raw_damage: int,
    damage_type: DamageType,
    target_physical_defense: int,
    target_magic_defense: int,
    target_soft_level: int,
    damage_split: Optional[DamageSplit] = None,
) -> int:
    """Calculate final damage for physical, magic or mixed damage."""
    if raw_damage <= 0:
        return 0

    if damage_type == DamageType.PHYSICAL:
        return apply_defense(raw_damage, target_physical_defense, target_soft_level)

    if damage_type == DamageType.MAGIC:
        return apply_defense(raw_damage, target_magic_defense, target_soft_level)

    if damage_type == DamageType.MIXED:
        split = damage_split or DamageSplit(physical=50, magic=50)
        split.validate()
        physical_part = ceil(raw_damage * split.physical / 100)
        magic_part = raw_damage - physical_part
        final_physical = apply_defense(physical_part, target_physical_defense, target_soft_level)
        final_magic = apply_defense(magic_part, target_magic_defense, target_soft_level)
        return final_physical + final_magic

    raise ValueError(f"Unsupported damage type: {damage_type}")


EXAMPLE_WOLF = EnemyBattleState(
    mob_id="field_wolf_001",
    name="Полевой волк",
    rank=EnemyRank.NORMAL,
    biological_type="beast",
    role="attacker",
    level=3,
    damage_type=DamageType.PHYSICAL,
    current_hp=45,
    max_hp=45,
    armor=3,
    magic_armor=0,
    physical_defense=9,
    magic_defense=3,
    accuracy=24,
    dodge=18,
    skills=["Укус", "Рывок"],
)


EXAMPLE_ANOMALY_BEAR = EnemyBattleState(
    mob_id="anomaly_bear_001",
    name="Аномальный медведь",
    rank=EnemyRank.BOSS,
    biological_type="anomaly",
    role="attacker",
    level=35,
    damage_type=DamageType.MIXED,
    damage_split=DamageSplit(physical=80, magic=20),
    current_hp=1200,
    max_hp=1200,
    armor=80,
    magic_armor=40,
    physical_defense=220,
    magic_defense=130,
    accuracy=140,
    dodge=45,
    skills=["Сокрушающий удар", "Аномальный выброс", "Рёв разлома"],
    features=["Кровавое бешенство", "Разломанная шкура"],
)
