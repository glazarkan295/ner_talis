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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_paths import resolve_project_path

LOCATION_ID = "small_plateau"
ANCIENT_CURSE_ID = "ancient_curse"
AMULET_BURN_ID = "amulet_burn"
SEVERE_AMULET_BURN_ID = "severe_amulet_burn"
SEEKER_ACHIEVEMENT_ID = "seeker"
CURSE_ACHIEVEMENT_ID = "curse_what_curse"
CURSE_BEARER_EFFECT_ID = "curse_bearer"
POSTMORTEM_CURSE_SOURCE = "curse_bearer_pvp_death"
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


def _effect_is_active(effect: dict[str, Any]) -> bool:
    if not isinstance(effect, dict):
        return False
    expires_at = effect.get("expires_at")
    if expires_at in (None, ""):
        return True
    if isinstance(expires_at, (int, float)):
        return float(expires_at) > time.time()
    try:
        parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed > datetime.now(timezone.utc)


def has_effect(player_state: dict[str, Any], effect_id: str) -> bool:
    stored = _effects_dict(player_state).get(effect_id)
    if isinstance(stored, dict):
        if _effect_is_active(stored):
            return True
    elif stored:
        # Legacy-представление: эффект как ключ-флаг (например {"ancient_curse":
        # True}). Раньше наличие ключа = активность; сохраняем это поведение,
        # иначе старые игроки/тесты теряют проклятие/амулет.
        return True
    return any(
        _effect_id(effect) == effect_id and _effect_is_active(effect)
        for effect in _active_effects_list(player_state)
        if isinstance(effect, dict)
    )


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


def grant_curse_bearer_effect(player_state: dict[str, Any]) -> None:
    """Permanent reward effect for «Проклятье? Какое проклятье?»."""
    add_effect(player_state, CURSE_BEARER_EFFECT_ID)


def ensure_curse_bearer_effect(player_state: dict[str, Any]) -> bool:
    """Sync legacy achievement-only players to the new permanent effect."""
    if not has_achievement(player_state, CURSE_ACHIEVEMENT_ID):
        return False
    already_had_effect = has_effect(player_state, CURSE_BEARER_EFFECT_ID)
    if not already_had_effect:
        grant_curse_bearer_effect(player_state)
    return not already_had_effect


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


def player_has_seeker(player_state: dict[str, Any]) -> bool:
    """Есть ли у игрока легендарное достижение «Ищущий»."""
    return has_achievement(player_state, SEEKER_ACHIEVEMENT_ID)


def filter_seeker_only(player_state: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Скрывает записи с флагом ``seeker_only`` от игроков без «Ищущего».

    Инфраструктура гейтинга скрытого контента: будущие события на локации и
    особые варианты ответов помечаются ``"seeker_only": true`` и становятся
    доступны только обладателям достижения «Ищущий».
    """
    if player_has_seeker(player_state):
        return list(items)
    return [item for item in items if not (isinstance(item, dict) and item.get("seeker_only"))]


def add_achievement(player_state: dict[str, Any], achievement_id: str) -> None:
    already_has_achievement = has_achievement(player_state, achievement_id)
    if not already_has_achievement:
        mechanics = get_mechanics_data()
        for achievement in mechanics.get("achievements", []):
            if isinstance(achievement, dict) and str(achievement.get("achievement_id")) == achievement_id:
                _achievements(player_state).append(dict(achievement))
                break
        else:
            _achievements(player_state).append(achievement_id)
    if achievement_id == CURSE_ACHIEVEMENT_ID:
        grant_curse_bearer_effect(player_state)


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
    # Обычные игроки не видят события с флагом seeker_only — их находят только
    # обладатели достижения «Ищущий».
    table = filter_seeker_only(player_state, get_search_events_data().get("events", []))
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
    trigger_chance = 0.20
    if rng.random() >= trigger_chance:
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
    penalty_percent = 0.40
    damage = max(1, int(max_hp * penalty_percent))
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
    ensure_curse_bearer_effect(player_state)
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
    if effect["active_days_with_30m_activity"] > 60 and not has_achievement(player_state, CURSE_ACHIEVEMENT_ID):
        add_achievement(player_state, CURSE_ACHIEVEMENT_ID)
        return {
            "achievement_id": CURSE_ACHIEVEMENT_ID,
            "effect_id": CURSE_BEARER_EFFECT_ID,
            "text": "Получено легендарное достижение «Проклятье? Какое проклятье?» и постоянный эффект «Носитель проклятья». Если вас убьют в PVP, убийцу на время настигнет одно из посмертных проклятий.",
        }
    return None


def _postmortem_curse_templates() -> list[dict[str, Any]]:
    templates = get_mechanics_data().get("postmortem_curses", [])
    return [dict(item) for item in templates if isinstance(item, dict)]


def _choose_postmortem_curse(rng: random.Random) -> dict[str, Any]:
    templates = _postmortem_curse_templates()
    if not templates:
        return {
            "effect_id": "postmortem_curse_weakness",
            "name": "Посмертная слабость",
            "description": "Проклятье носителя ослабляет убийцу после PVP-убийства.",
            "duration_seconds": 3600,
            "stat_modifiers": {"bonus_strength": -2, "bonus_endurance": -2},
        }
    return weighted_choice(templates, rng)


def apply_pvp_kill_postmortem_curse(killer: dict[str, Any], victim: dict[str, Any], rng: random.Random | None = None, now_ts: float | int | None = None) -> dict[str, Any]:
    """Apply the curse-bearer's postmortem PVP curse to the killer.

    Call this after a confirmed PVP kill, passing the killer and the killed
    victim. It is intentionally isolated from a concrete PVP implementation:
    current runtime has PVP counters/contracts, while the full PVP battle loop
    can wire this hook in when player-vs-player death is resolved.
    """
    ensure_curse_bearer_effect(victim)
    if not has_effect(victim, CURSE_BEARER_EFFECT_ID):
        return {"applied": False, "reason": "victim_has_no_curse_bearer"}

    rng = rng or random.Random()
    now = int(time.time() if now_ts is None else now_ts)
    template = _choose_postmortem_curse(rng)
    effect_id = str(template.get("effect_id") or template.get("id") or "postmortem_curse")
    duration_seconds = max(60, int(template.get("duration_seconds") or 3600))
    expires_at = datetime.fromtimestamp(now + duration_seconds, tz=timezone.utc).isoformat()
    payload = {
        **template,
        "id": effect_id,
        "effect_id": effect_id,
        "type": "curse",
        "kind": "negative",
        "active": True,
        "source": POSTMORTEM_CURSE_SOURCE,
        "duration_seconds": duration_seconds,
        "expires_at": expires_at,
        "pvp_victim_id": victim.get("game_id") or victim.get("public_id"),
        "pvp_victim_name": victim.get("name") or victim.get("nickname"),
    }
    add_effect(killer, effect_id, payload)
    return {
        "applied": True,
        "effect": payload,
        "text": f"Посмертное проклятье «{payload.get('name', 'Проклятье')}» настигло убийцу.",
    }
