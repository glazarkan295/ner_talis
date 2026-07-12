"""Runtime helpers for race bonuses used by combat, profile, crafting and exploration."""

from __future__ import annotations

import math
import random
from typing import Any


UNDEAD_RESISTED_EFFECTS = {"poison", "bleed", "stun", "curse", "яд", "кровотечение", "оглушение", "проклятие"}
METAL_CRAFT_TYPES = {"weapon", "armor", "equipment", "blacksmithing", "leatherworking", "оружие", "броня", "снаряжение", "кузнечное дело"}

# Эльф — «Чутьё зельевара»: при изготовлении зелий часть ингредиентов может не
# потратиться. Шанс зависит от позиции ингредиента в рецепте (скрыт от игрока),
# 6-й и далее — 2%. Ингредиент, которого в рецепте всего 1 шт, не участвует.
ALCHEMY_REFUND_CHANCES_BY_POSITION = (10, 8, 6, 4, 2)
ALCHEMY_REFUND_TAIL_CHANCE = 2

# Дворф — «Каменное чутьё»: шанс выпадения драгоценного камня при добыче руды.
DWARF_GEM_DROP_CHANCE_PERCENT = 4
DWARF_GEM_DROP_POOL = (
    "ruby_shards",
    "sapphire_shards",
    "emerald_shards",
    "amethyst_shards",
    "diamond_shards",
)

# Дворф — «Мастерская закалка»: небольшой шанс +1 эффект на оружии/броне.
DWARF_EXTRA_EFFECT_CHANCE_PERCENT = 3


def race_id(player: dict[str, Any]) -> str:
    return str(player.get("race_id") or "").casefold()


def published_race(player: dict[str, Any]) -> dict[str, Any] | None:
    try:
        from services.race_constructor_service import published_definition
        return published_definition(race_id(player))
    except Exception:
        return None


def _bonus_rows(player: dict[str, Any], kind: str, target: str = "", context: str = "") -> list[dict[str, Any]]:
    data = published_race(player) or {}; out = []
    for row in data.get("bonuses") or []:
        if not isinstance(row, dict) or str(row.get("type") or "") != kind: continue
        if target and str(row.get("target") or "") not in {"", target}: continue
        declared = str(row.get("context") or "always")
        if context and declared not in {"", "always", context}: continue
        out.append(row)
    return out


def _value(player: dict[str, Any], row: dict[str, Any], default: float = 0.0, **context: Any) -> float:
    base = row.get("percent") if row.get("percent") not in (None, "") else row.get("value", default)
    try: value = float(base)
    except (TypeError, ValueError): value = default
    if row.get("formula_id"):
        try:
            from services.formula_runtime import evaluate
            value = float(evaluate(row.get("formula_id"), {"base_amount": value, "player_level": player.get("level", 1), **context}, default=value))
        except Exception: pass
    return value


def _sum_bonus(player: dict[str, Any], kind: str, target: str = "", context: str = "", **values: Any) -> float:
    rows = _bonus_rows(player, kind, target, context)
    rows += _bonus_rows(player, "formula", target or kind, context)
    return sum(_value(player, row, **values) for row in rows)


def sync_passive_effects(player: dict[str, Any]) -> None:
    """Remove previous race effects and apply effects of the current published race."""
    for field in ("active_effects", "active_curses"):
        player[field] = [row for row in player.get(field) or [] if not isinstance(row, dict) or row.get("source") != "race"]
    for row in _bonus_rows(player, "effect"):
        effect_id = str(row.get("effect_id") or "")
        if not effect_id: continue
        try:
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player, effect_id, source="race", context={"duration_seconds": row.get("duration_seconds")})
        except Exception:
            player.setdefault("active_effects", []).append({"effect_id": effect_id, "source": "race"})


def stat_multiplier(player: dict[str, Any], stat_key: str) -> float:
    dynamic = _sum_bonus(player, "stat_percent", stat_key, "always")
    if dynamic: return max(0.0, 1.0 + dynamic / 100)
    race = race_id(player)
    if race == "human":
        return 1.01
    if race == "dwarf" and stat_key == "endurance":
        return 1.03
    return 1.0


def hp_multiplier(player: dict[str, Any]) -> float:
    dynamic = _sum_bonus(player, "resource_percent", "hp", "always")
    if dynamic: return max(0.0, 1.0 + dynamic / 100)
    return 1.04 if race_id(player) == "undead" else 1.0


def experience_multiplier(player: dict[str, Any]) -> float:
    dynamic = _sum_bonus(player, "experience_percent", "experience", "always")
    if dynamic: return max(0.0, 1.0 + dynamic / 100)
    return 1.02 if race_id(player) == "human" else 1.0


def npc_transaction_bonus_amount(player: dict[str, Any], copper_amount: int, rng: random.Random | None = None) -> int:
    """Human racial bonus for NPC trading.

    After buying from or selling to an NPC, humans have a 5% chance to receive
    an additional 3% of the spent/received copper amount.
    """

    rows = _bonus_rows(player, "trade_chance", context="trade")
    if rows and copper_amount > 0:
        rng = rng or random.Random(); total = 0
        for row in rows:
            if rng.uniform(0, 100) <= float(row.get("chance", 100) or 0): total += max(0, int(math.ceil(copper_amount * _value(player, row) / 100)))
        return total
    if race_id(player) != "human" or copper_amount <= 0:
        return 0
    rng = rng or random.Random()
    if rng.uniform(0, 100) > 5:
        return 0
    return max(1, int(math.ceil(copper_amount * 0.03)))


def npc_purchase_refund_amount(player: dict[str, Any], spent_copper: int, rng: random.Random | None = None) -> int:
    """Backward-compatible name for the human NPC trade bonus."""

    return npc_transaction_bonus_amount(player, spent_copper, rng)


def outgoing_damage_multiplier(player: dict[str, Any], damage_type: str) -> float:
    dynamic = _sum_bonus(player, "damage_percent", str(damage_type).casefold(), "combat")
    if dynamic: return max(0.0, 1.0 + dynamic / 100)
    if race_id(player) == "elf" and str(damage_type).casefold() == "magic":
        return 1.03
    return 1.0


def extra_alchemy_ingredient_chance_percent(player: dict[str, Any]) -> int:
    dynamic = _sum_bonus(player, "resource_chance", "alchemy_ingredient", "craft")
    if dynamic: return max(0, int(dynamic))
    return 3 if race_id(player) == "elf" else 0


def alchemy_ingredient_refund(
    player: dict[str, Any],
    ingredients: list[tuple[str, int]],
    quantity: int = 1,
    rng: random.Random | None = None,
) -> dict[str, int]:
    """Эльф «Чутьё зельевара»: какие ингредиенты вернутся при варке зелий.

    ``ingredients`` — список ``(ключ, расход_на_одну_варку)`` в порядке рецепта.
    Возвращает ``{ключ: возвращаемое_количество}``. Ингредиенты, которых в
    рецепте всего 1 шт, не участвуют. Шанс зависит от позиции участвующего
    ингредиента (скрыт от игрока).
    """
    if race_id(player) != "elf":
        return {}
    rng = rng or random.Random()
    quantity = max(1, int(quantity or 1))
    refunds: dict[str, int] = {}
    position = 0
    for key, per_craft_amount in ingredients:
        per_craft = max(0, int(per_craft_amount or 0))
        if per_craft <= 1 or not key:
            continue  # «если предметов используется 1 в рецепте — не участвует»
        position += 1
        if position <= len(ALCHEMY_REFUND_CHANCES_BY_POSITION):
            chance = ALCHEMY_REFUND_CHANCES_BY_POSITION[position - 1]
        else:
            chance = ALCHEMY_REFUND_TAIL_CHANCE
        total = per_craft * quantity
        if total <= 1:
            continue
        if rng.uniform(0, 100) < chance:
            refunds[str(key)] = refunds.get(str(key), 0) + rng.randint(1, total - 1)
    return refunds


def mining_gem_drop(player: dict[str, Any], rng: random.Random | None = None) -> str | None:
    """Дворф «Каменное чутьё»: 4% шанс выпадения камня при добыче руды.

    Возвращает item_id драгоценного камня или ``None``.
    """
    if race_id(player) != "dwarf":
        return None
    rng = rng or random.Random()
    if rng.uniform(0, 100) >= DWARF_GEM_DROP_CHANCE_PERCENT:
        return None
    return rng.choice(DWARF_GEM_DROP_POOL) if DWARF_GEM_DROP_POOL else None


def crafting_extra_effect_triggered(
    player: dict[str, Any], craft_type: str, rng: random.Random | None = None
) -> bool:
    """Дворф «Мастерская закалка»: небольшой шанс +1 эффект на оружии/броне."""
    craft = str(craft_type or "").casefold()
    if race_id(player) != "dwarf" or craft not in METAL_CRAFT_TYPES:
        return False
    rng = rng or random.Random()
    return rng.uniform(0, 100) < DWARF_EXTRA_EFFECT_CHANCE_PERCENT


def effect_resistance_bonus_percent(player: dict[str, Any], effect_type: str) -> int:
    dynamic = _sum_bonus(player, "resistance", str(effect_type).casefold(), "combat")
    if dynamic: return max(0, int(dynamic))
    effect = str(effect_type or "").casefold()
    if race_id(player) == "undead" and effect in UNDEAD_RESISTED_EFFECTS:
        return 5
    return 0


def incoming_periodic_damage_multiplier(player: dict[str, Any]) -> float:
    dynamic = _sum_bonus(player, "damage_percent", "incoming_periodic", "combat")
    if dynamic: return max(0.0, 1.0 + dynamic / 100)
    return 0.97 if race_id(player) == "undead" else 1.0


def incoming_physical_damage_multiplier(player: dict[str, Any]) -> float:
    dynamic = _sum_bonus(player, "damage_percent", "incoming_physical", "combat")
    if dynamic: return max(0.0, 1.0 + dynamic / 100)
    return 0.98 if race_id(player) == "lizardfolk" else 1.0


def combat_hp_regen_percent(player: dict[str, Any]) -> float:
    dynamic = _sum_bonus(player, "regeneration", "hp", "combat")
    if dynamic: return max(0.0, dynamic)
    return 0.5 if race_id(player) == "lizardfolk" else 0.0


def search_event_weights(player: dict[str, Any], base_weights: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Return race-adjusted exploration weights while keeping integer weights."""

    race = race_id(player)
    weights = {key: int(value) for key, value in base_weights}
    for row in _bonus_rows(player, "event_chance", context="search") + _bonus_rows(player, "resource_chance", context="search"):
        target = str(row.get("target") or "")
        if target in weights: weights[target] = max(1, weights[target] + int(round(_value(player, row))))

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
