"""Runtime helpers for the external location «Малое плато».

The module keeps the location-specific mechanics isolated while using the same
plain dict player state as the rest of the project.  It supports both the
newer project fields (``money_copper``, list-based ``active_effects``) and the
small standalone pack tests (``currency`` and dict-based ``effects``).
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

from project_paths import resolve_project_path

LOCATION_ID = "small_plateau"
ANCIENT_CURSE_ID = "ancient_curse"
AMULET_BURN_ID = "amulet_burn"
SEVERE_AMULET_BURN_ID = "severe_amulet_burn"
SEEKER_ACHIEVEMENT_ID = "seeker"
CURSE_ACHIEVEMENT_ID = "curse_what_curse"
COPPER_PER_SILVER = 1000


def _data_path(filename: str) -> Path:
    return resolve_project_path(Path("data") / filename)


def _load_json(filename: str) -> dict[str, Any]:
    try:
        with _data_path(filename).open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def get_location_data() -> dict[str, Any]:
    return _load_json("small_plateau_location.json")


def get_search_events_data() -> dict[str, Any]:
    return _load_json("small_plateau_search_events.json")


def get_mechanics_data() -> dict[str, Any]:
    return _load_json("small_plateau_mechanics.json")


def get_texts_data() -> dict[str, Any]:
    return _load_json("small_plateau_texts.json")


def weighted_choice(items: list[dict[str, Any]], rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.Random()
    valid = [item for item in items if isinstance(item, dict) and int(item.get("weight", 0) or 0) > 0]
    if not valid:
        raise ValueError("Weighted table is empty or has no positive weights")
    total = sum(int(item.get("weight", 0) or 0) for item in valid)
    roll = rng.randint(1, total)
    current = 0
    for item in valid:
        current += int(item.get("weight", 0) or 0)
        if roll <= current:
            return item
    return valid[-1]


def _small_plateau_state(player_state: dict[str, Any]) -> dict[str, Any]:
    return player_state.setdefault("small_plateau", {})


def _currency_dict(player_state: dict[str, Any]) -> dict[str, int]:
    value = player_state.setdefault("currency", {})
    return value if isinstance(value, dict) else {}


def _active_effects_list(player_state: dict[str, Any]) -> list[dict[str, Any]]:
    value = player_state.setdefault("active_effects", [])
    if not isinstance(value, list):
        value = []
        player_state["active_effects"] = value
    return value


def _effects_dict(player_state: dict[str, Any]) -> dict[str, Any]:
    value = player_state.setdefault("effects", {})
    if not isinstance(value, dict):
        value = {}
        player_state["effects"] = value
    return value


def _effect_id(effect: dict[str, Any]) -> str:
    return str(effect.get("id") or effect.get("effect_id") or "")


def has_effect(player_state: dict[str, Any], effect_id: str) -> bool:
    if effect_id in _effects_dict(player_state):
        return True
    return any(_effect_id(effect) == effect_id for effect in _active_effects_list(player_state) if isinstance(effect, dict))


def _mechanic_effect_template(effect_id: str) -> dict[str, Any]:
    for effect in get_mechanics_data().get("effects", []):
        if isinstance(effect, dict) and str(effect.get("effect_id")) == effect_id:
            return dict(effect)
    return {"effect_id": effect_id, "id": effect_id, "name": effect_id, "type": "effect"}


def add_effect(player_state: dict[str, Any], effect_id: str, payload: dict[str, Any] | None = None) -> None:
    payload = dict(payload or _mechanic_effect_template(effect_id))
    payload.setdefault("effect_id", effect_id)
    payload.setdefault("id", effect_id)
    payload.setdefault("active", True)
    _effects_dict(player_state)[effect_id] = dict(payload)
    effects = _active_effects_list(player_state)
    for index, effect in enumerate(list(effects)):
        if isinstance(effect, dict) and _effect_id(effect) == effect_id:
            effects[index] = dict(payload)
            break
    else:
        effects.append(dict(payload))


def remove_effect(player_state: dict[str, Any], effect_id: str) -> None:
    _effects_dict(player_state).pop(effect_id, None)
    player_state["active_effects"] = [
        effect for effect in _active_effects_list(player_state)
        if not (isinstance(effect, dict) and _effect_id(effect) == effect_id)
    ]


def _achievements(player_state: dict[str, Any]) -> list[Any]:
    value = player_state.setdefault("achievements", [])
    if not isinstance(value, list):
        value = []
        player_state["achievements"] = value
    return value


def has_achievement(player_state: dict[str, Any], achievement_id: str) -> bool:
    for value in _achievements(player_state):
        if value == achievement_id:
            return True
        if isinstance(value, dict) and str(value.get("id") or value.get("achievement_id")) == achievement_id:
            return True
    return False


def add_achievement(player_state: dict[str, Any], achievement_id: str) -> None:
    if has_achievement(player_state, achievement_id):
        return
    mechanics = get_mechanics_data()
    for achievement in mechanics.get("achievements", []):
        if isinstance(achievement, dict) and str(achievement.get("achievement_id")) == achievement_id:
            _achievements(player_state).append(dict(achievement))
            return
    _achievements(player_state).append(achievement_id)


def add_currency(player_state: dict[str, Any], currency: str, amount: int) -> None:
    amount = int(amount or 0)
    if amount <= 0:
        return
    wallet = _currency_dict(player_state)
    wallet[currency] = int(wallet.get(currency, 0) or 0) + amount
    copper_delta = amount * COPPER_PER_SILVER if currency == "silver" else amount if currency == "copper" else 0
    if copper_delta:
        player_state["money_copper"] = int(player_state.get("money_copper", player_state.get("money", 0)) or 0) + copper_delta
        player_state["money"] = player_state["money_copper"]


def spend_currency(player_state: dict[str, Any], currency: str, amount: int) -> bool:
    amount = int(amount or 0)
    if amount <= 0:
        return True
    copper_cost = amount * COPPER_PER_SILVER if currency == "silver" else amount if currency == "copper" else 0
    if copper_cost:
        money = int(player_state.get("money_copper", player_state.get("money", 0)) or 0)
        if money >= copper_cost:
            player_state["money_copper"] = money - copper_cost
            player_state["money"] = player_state["money_copper"]
            wallet = _currency_dict(player_state)
            wallet[currency] = max(0, int(wallet.get(currency, 0) or 0) - amount)
            return True
    wallet = _currency_dict(player_state)
    if int(wallet.get(currency, 0) or 0) < amount:
        return False
    wallet[currency] = int(wallet.get(currency, 0) or 0) - amount
    return True


def _item_defs() -> dict[str, dict[str, Any]]:
    try:
        with _data_path("items_small_plateau.json").open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        data = []
    raw_items = data.get("items", []) if isinstance(data, dict) else data
    result: dict[str, dict[str, Any]] = {}
    for item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("item_id") or "")
        if item_id:
            result[item_id] = item
    return result


def add_item(player_state: dict[str, Any], item_id: str, amount: int = 1) -> dict[str, Any]:
    amount = max(1, int(amount or 1))
    definition = _item_defs().get(item_id, {"item_id": item_id, "name": item_id, "stack_size": amount})
    name = str(definition.get("name_ru") or definition.get("name") or item_id)
    max_stack = int(definition.get("max_stack") or definition.get("stack_size") or amount or 1)
    inventory = player_state.setdefault("inventory", [])
    if isinstance(inventory, dict):
        inventory[item_id] = int(inventory.get(item_id, 0) or 0) + amount
        return {"item_id": item_id, "name": name, "amount": amount}
    if not isinstance(inventory, list):
        inventory = []
        player_state["inventory"] = inventory
    remaining = amount
    if max_stack > 1:
        for stack in inventory:
            if not isinstance(stack, dict):
                continue
            if str(stack.get("id") or stack.get("item_id")) != item_id:
                continue
            current = int(stack.get("amount", 1) or 1)
            if current >= max_stack:
                continue
            add = min(max_stack - current, remaining)
            stack["amount"] = current + add
            remaining -= add
            if remaining <= 0:
                break
    while remaining > 0:
        add = min(max_stack, remaining)
        sell_price = definition.get("base_sell_price") if isinstance(definition.get("base_sell_price"), dict) else {}
        inventory.append({
            "id": item_id,
            "item_id": item_id,
            "name": name,
            "name_ru": name,
            "amount": add,
            "category": definition.get("category"),
            "inventory": definition.get("inventory"),
            "inventory_section_ru": definition.get("inventory"),
            "stackable": max_stack > 1,
            "stack_size": max_stack,
            "max_stack": max_stack,
            "can_sell": True,
            "sell_price_copper": int(sell_price.get("amount", 0) or 0),
            "asset_path": definition.get("asset_path"),
            "icon": definition.get("asset_path"),
            "description": definition.get("description"),
            "source": "Малое плато",
        })
        remaining -= add
    return {"item_id": item_id, "name": name, "amount": amount}


def apply_rewards(player_state: dict[str, Any], rewards: list[dict[str, Any]], rng: random.Random | None = None) -> list[dict[str, Any]]:
    rng = rng or random.Random()
    applied: list[dict[str, Any]] = []
    for reward in rewards:
        if not isinstance(reward, dict):
            continue
        reward_type = reward.get("type")
        if reward_type == "currency":
            amount = reward.get("amount")
            if amount is None:
                amount = rng.randint(int(reward.get("amount_min", 1) or 1), int(reward.get("amount_max", 1) or 1))
            add_currency(player_state, str(reward.get("currency") or "copper"), int(amount))
            applied.append({**reward, "amount": int(amount)})
        elif reward_type == "item":
            amount = int(reward.get("amount", 1) or 1)
            item = add_item(player_state, str(reward.get("item_id") or reward.get("id")), amount)
            applied.append({**reward, "amount": amount, "name": item.get("name")})
    return applied


def get_small_plateau_search_count(player_state: dict[str, Any]) -> int:
    return int(_small_plateau_state(player_state).get("search_count", 0) or 0)


def increment_small_plateau_search_count(player_state: dict[str, Any]) -> int:
    state = _small_plateau_state(player_state)
    state["search_count"] = int(state.get("search_count", 0) or 0) + 1
    return int(state["search_count"])


def _milestone_by_count(count: int) -> dict[str, Any] | None:
    for milestone in get_mechanics_data().get("search_milestones", []):
        if isinstance(milestone, dict) and int(milestone.get("search_count", -1) or -1) == int(count):
            return milestone
    return None


def apply_search_milestone(player_state: dict[str, Any], count: int) -> dict[str, Any] | None:
    milestone = _milestone_by_count(count)
    if not milestone:
        return None
    for effect_id in milestone.get("effects_to_remove", []):
        remove_effect(player_state, str(effect_id))
    for effect_id in milestone.get("effects_to_add", []):
        add_effect(player_state, str(effect_id))
    for achievement_id in milestone.get("achievements_to_add", []):
        add_achievement(player_state, str(achievement_id))
    return milestone


def _choose_probability_outcome(outcomes: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    if not outcomes:
        return {"result_text": "", "rewards": []}
    roll = rng.random()
    current = 0.0
    for outcome in outcomes:
        current += float(outcome.get("chance", 0.0) or 0.0)
        if roll <= current:
            return outcome
    return outcomes[-1]


def resolve_small_plateau_search(player_state: dict[str, Any], rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.Random()
    table = get_search_events_data().get("events", [])
    event = weighted_choice(table, rng)
    count = increment_small_plateau_search_count(player_state)
    milestone = apply_search_milestone(player_state, count)
    applied_rewards: list[dict[str, Any]] = []
    result_text = str(event.get("result_text") or "")

    if event.get("type") == "minor_random_reward":
        outcome = _choose_probability_outcome(event.get("outcomes", []), rng)
        result_text = str(outcome.get("result_text") or "")
        applied_rewards = apply_rewards(player_state, outcome.get("rewards", []), rng)
    elif event.get("type") != "choice_cursed_coins":
        applied_rewards = apply_rewards(player_state, event.get("rewards", []), rng)

    return {
        "location_id": LOCATION_ID,
        "event": event,
        "search_count": count,
        "text": str(event.get("text") or ""),
        "result_text": result_text,
        "applied_rewards": applied_rewards,
        "milestone": milestone,
        "requires_choice": event.get("type") == "choice_cursed_coins",
    }


def handle_cursed_coin_choice(player_state: dict[str, Any], take_coins: bool, rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.Random()
    if not take_coins:
        return {"text": "Вы оставляете монеты в углублении и отходите от плиты.", "applied_rewards": [], "curse_applied": False}

    state = _small_plateau_state(player_state)
    take_count_before = int(state.get("cursed_coin_take_count", 0) or 0)
    state["cursed_coin_take_count"] = take_count_before + 1
    amount = rng.randint(1, 2)
    add_currency(player_state, "silver", amount)
    curse_chance = 0.0 if take_count_before == 0 else 0.15
    curse_applied = rng.random() < curse_chance
    texts = get_texts_data().get("ancient_curse", {})
    if curse_applied:
        add_effect(player_state, ANCIENT_CURSE_ID, {
            "id": ANCIENT_CURSE_ID,
            "effect_id": ANCIENT_CURSE_ID,
            "name": "Древнее Проклятье",
            "type": "curse",
            "active": True,
            "removable_by_standard_cleansing": False,
            "source": "small_plateau_cursed_silver_coins",
            "active_days_with_30m_activity": 0,
            "created_at": int(time.time()),
        })
        text = str(texts.get("coins_take_with_curse") or "Взяв монеты, вы слышите разочарованный вздох.\n\nВы прокляты!")
    else:
        text = str(texts.get("coins_take_without_curse") or "Взяв монеты, вы слышите разочарованный вздох.")
    return {
        "text": text,
        "applied_rewards": [{"type": "currency", "currency": "silver", "amount": amount}],
        "curse_applied": curse_applied,
        "curse_chance": curse_chance,
    }


def roll_ancient_curse_trigger(player_state: dict[str, Any], action_type: str, rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.Random()
    if not has_effect(player_state, ANCIENT_CURSE_ID):
        return {"triggered": False}
    if action_type not in {"city_quarter_walk", "fortress_quarter_walk", "location_search", "camp_rest"}:
        return {"triggered": False}
    if rng.random() >= 0.20:
        return {"triggered": False}
    player_state["current_city"] = "outside_seldar"
    player_state["current_location"] = LOCATION_ID
    player_state["current_zone"] = "small_plateau_hidden_coin_place"
    player_state["location_id"] = "small_plateau_hidden_coin_place"
    _small_plateau_state(player_state)["hidden_coin_place_active"] = True
    text = str(get_texts_data().get("ancient_curse", {}).get("curse_trigger") or "Путь перед вами размывается, и вы оказываетесь среди руин Малого плато.")
    return {"triggered": True, "target_location": LOCATION_ID, "hidden_place": "cursed_silver_coins_origin", "text": text}


def cleanse_ancient_curse_at_hidden_place(player_state: dict[str, Any]) -> dict[str, Any]:
    texts = get_texts_data().get("ancient_curse", {})
    if not has_effect(player_state, ANCIENT_CURSE_ID):
        return {"success": False, "text": "На вас нет Древнего Проклятья."}
    if not spend_currency(player_state, "silver", 100):
        return {"success": False, "text": str(texts.get("not_enough_silver") or "Вам нужно 100 серебряных монет, чтобы снять проклятье.")}
    remove_effect(player_state, ANCIENT_CURSE_ID)
    max_hp = int(player_state.get("max_hp", player_state.get("hp", 1)) or 1)
    damage = max(1, int(max_hp * 0.40))
    player_state["hp"] = max(1, int(player_state.get("hp", max_hp) or max_hp) - damage)
    _small_plateau_state(player_state)["hidden_coin_place_active"] = False
    player_state["current_zone"] = LOCATION_ID
    player_state["location_id"] = LOCATION_ID
    player_state["current_location"] = LOCATION_ID
    return {"success": True, "damage": damage, "text": str(texts.get("cleanse_hidden_place") or "Эффект «Древнее Проклятье» снят.\n−40% HP от максимального запаса.")}


def leave_hidden_coin_place_with_curse(player_state: dict[str, Any]) -> dict[str, Any]:
    _small_plateau_state(player_state)["hidden_coin_place_active"] = False
    player_state["current_city"] = "outside_seldar"
    player_state["current_location"] = LOCATION_ID
    player_state["current_zone"] = LOCATION_ID
    player_state["location_id"] = LOCATION_ID
    text = str(get_texts_data().get("ancient_curse", {}).get("leave_hidden_place") or "Уходя, вы чувствуете на себе взгляд полного разочарования.")
    return {"text": text}


def tick_amulet_burn_hourly(player_state: dict[str, Any]) -> dict[str, Any] | None:
    if has_effect(player_state, SEVERE_AMULET_BURN_ID):
        damage = 20
        message = "От жара идентификационного амулета вы потеряли 20 HP."
    elif has_effect(player_state, AMULET_BURN_ID):
        damage = 5
        message = "От тепла идентификационного амулета вы потеряли 5 HP."
    else:
        return None
    player_state["hp"] = max(1, int(player_state.get("hp", 1) or 1) - damage)
    return {"damage": damage, "text": message}


def register_ancient_curse_active_day(player_state: dict[str, Any], activity_minutes_today: int) -> dict[str, Any] | None:
    if not has_effect(player_state, ANCIENT_CURSE_ID):
        return None
    if int(activity_minutes_today) < 30:
        return None
    effects_dict = _effects_dict(player_state)
    effect = effects_dict.get(ANCIENT_CURSE_ID)
    if not isinstance(effect, dict):
        effect = {"id": ANCIENT_CURSE_ID, "effect_id": ANCIENT_CURSE_ID, "active": True}
        effects_dict[ANCIENT_CURSE_ID] = effect
    effect["active_days_with_30m_activity"] = int(effect.get("active_days_with_30m_activity", 0) or 0) + 1
    # Keep list representation in sync.
    add_effect(player_state, ANCIENT_CURSE_ID, effect)
    if effect["active_days_with_30m_activity"] >= 60 and not has_achievement(player_state, CURSE_ACHIEVEMENT_ID):
        add_achievement(player_state, CURSE_ACHIEVEMENT_ID)
        return {
            "achievement_id": CURSE_ACHIEVEMENT_ID,
            "text": "Получено легендарное достижение «Проклятье? Какое проклятье?»: ослабление всех проклятий на игроке в 2 раза.",
        }
    return None
