
"""Fishing and waterside loot helpers for Ner-Talis locations.

The service keeps the loot table data-driven so port fishing and later boat/ocean
fishing can share the same item-granting code without hard-coding every reward
inside the city router.
"""

from __future__ import annotations

import json
import math
import random
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from project_paths import resolve_project_path
from services.inventory_service import add_inventory_item, apply_generated_item_level_and_price, inventory_add_result_notice
from services.item_registry import build_inventory_item, get_item_definition_by_id, slugify_fallback_item_id

PIER_FISHING_ACTION = "Рыбалка на пристани"
START_PIER_FISHING = "Забросить удочку"
CHECK_FISHING_TIMER = "Проверить таймер"
BACK_TO_PIER = "Пристань"
FISHING_ACTIONS = frozenset({PIER_FISHING_ACTION, START_PIER_FISHING, CHECK_FISHING_TIMER})
FISHING_ZONE = "seldar_pier_fishing"
FISHING_SOURCE_TEXT = "Рыбалка на пристани"
FISHING_TIMER_TYPE = "fishing"
FISHING_TIMER_SECONDS = 60
FISHING_ENERGY_COST = 1
FISHING_COMPLETION_OWNER = "fishing_completion"


@dataclass(frozen=True)
class FishingResponse:
    text: str
    buttons: list[list[str]]
    zone_id: str = FISHING_ZONE
    scheduled_timer: dict[str, Any] | None = None


def _now_ts() -> float:
    return time.time()


def _fishing_timer_remaining(timer: dict[str, Any] | None) -> int:
    if not isinstance(timer, dict):
        return 0
    return max(0, math.ceil(float(timer.get("ends_at") or 0) - _now_ts()))


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    minutes, sec = divmod(seconds, 60)
    if minutes and sec:
        return f"{minutes} мин {sec} сек"
    if minutes:
        return f"{minutes} мин"
    return f"{sec} сек"


def fishing_buttons() -> list[list[str]]:
    return [[START_PIER_FISHING], [BACK_TO_PIER, "Портовый квартал"], ["⬅️ Центральная площадь"]]


def fishing_timer_buttons() -> list[list[str]]:
    return [[CHECK_FISHING_TIMER], [BACK_TO_PIER, "Портовый квартал"], ["⬅️ Центральная площадь"]]


def _is_fishing_timer(timer: Any) -> bool:
    return isinstance(timer, dict) and timer.get("type") == FISHING_TIMER_TYPE


def load_fishing_sources() -> dict[str, Any]:
    path = resolve_project_path("data/location_fishing_sources.json")
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def weighted_choice(weighted_items: Iterable[tuple[Any, int]], rng: random.Random) -> Any:
    items = [(item, max(0, int(weight))) for item, weight in weighted_items if int(weight) > 0]
    if not items:
        raise ValueError("empty weighted choice")
    total = sum(weight for _item, weight in items)
    roll = rng.uniform(0, total)
    upto = 0.0
    for item, weight in items:
        upto += weight
        if roll <= upto:
            return item
    return items[-1][0]


def _amount_from_entry(entry: dict[str, Any], rng: random.Random) -> int:
    raw = entry.get("amount", 1)
    if isinstance(raw, list) and len(raw) >= 2:
        return max(1, int(rng.randint(int(raw[0]), int(raw[1]))))
    if isinstance(raw, tuple) and len(raw) >= 2:
        return max(1, int(rng.randint(int(raw[0]), int(raw[1]))))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def item_display_name(item_id: str) -> str:
    definition = get_item_definition_by_id(item_id)
    if isinstance(definition, dict):
        return str(definition.get("name_ru") or definition.get("name") or item_id)
    return item_id


def player_has_fishing_rod(player: dict[str, Any]) -> bool:
    for item in player.get("inventory", []) if isinstance(player.get("inventory"), list) else []:
        if not isinstance(item, dict):
            continue
        identity = str(item.get("id") or item.get("item_id") or "").strip()
        name = str(item.get("name") or item.get("name_ru") or "").strip().casefold()
        amount = int(item.get("amount", 1) or 1)
        if amount <= 0:
            continue
        if identity == "fishing_rod" or name == "удочка рыбака":
            return True
    return False


def grant_item_to_player(player: dict[str, Any], item_id: str, amount: int, *, source: str, rng: random.Random | None = None):
    rng = rng or random.Random()
    definition = get_item_definition_by_id(item_id)
    if isinstance(definition, dict):
        name = str(definition.get("name_ru") or definition.get("name") or item_id)
        max_stack = definition.get("max_stack") or definition.get("stack_size")
    else:
        name = item_id
        max_stack = 20
    inventory_item = build_inventory_item(name, amount, item_id=item_id, max_stack=int(max_stack or 20))
    apply_generated_item_level_and_price(player, inventory_item, "found", rng=rng)
    inventory_item.setdefault("source", source)
    inventory_item.setdefault("actions", [])
    return add_inventory_item(
        player,
        inventory_item,
        amount,
        item_id=str(inventory_item.get("id") or inventory_item.get("item_id") or slugify_fallback_item_id(name)),
        max_stack=int(inventory_item.get("max_stack", max_stack or 20) or max_stack or 20),
        default_source=source,
        default_category="Ресурсы",
    )


def choose_loot_entry(table: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
    return weighted_choice([(entry, int(entry.get("weight", 1) or 1)) for entry in table], rng)


def choose_pier_fishing_reward(rng: random.Random | None = None) -> tuple[str, dict[str, Any]]:
    rng = rng or random.Random()
    config = load_fishing_sources().get("pier_fishing") or {}
    rarity_weights = config.get("rarity_weights") or {"common": 50, "uncommon": 19, "rare": 1, "trash": 30}
    rarity = weighted_choice([(key, int(value)) for key, value in rarity_weights.items()], rng)
    tables = config.get("tables") or {}
    table = tables.get(rarity) or tables.get("trash") or []
    if not table:
        return str(rarity), {"item_id": "old_torn_boot", "amount": [1, 1], "weight": 1}
    return str(rarity), choose_loot_entry(table, rng)


def fishing_intro_text() -> str:
    return (
        "🎣 Рыбалка на пристани\n\n"
        "Для действия нужна удочка рыбака. Один заброс тратит 1 энергию, "
        "после заброса поклёвки нужно ждать 60 секунд.\n\n"
        "Шансы:\n"
        "• обычный улов — 50%\n"
        "• необычный улов — 19%\n"
        "• редкий улов — 1%\n"
        "• мусор — 30%\n\n"
        "Возможный улов:\n"
        "• обычный: простая небольшая рыбка, крупная рыба;\n"
        "• необычный: угорь, медуза, моллюск, старый железный меч;\n"
        "• редкий: перламутровая рыба, золотая рыбка, старый маленький сундучок;\n"
        "• мусор: старый рваный башмак, ракушка, водоросли."
    )


def _fishing_timer_schedule(player: dict[str, Any], timer: dict[str, Any]) -> dict[str, Any]:
    return {
        "timer_id": timer.get("id"),
        "game_id": player.get("game_id") or player.get("id"),
        "seconds": int(timer.get("seconds") or FISHING_TIMER_SECONDS),
        "type": FISHING_TIMER_TYPE,
    }


def _grant_fishing_catch(player: dict[str, Any], rng: random.Random) -> str:
    rarity, entry = choose_pier_fishing_reward(rng)
    item_id = str(entry.get("item_id") or "old_torn_boot")
    amount = _amount_from_entry(entry, rng)
    add_result = grant_item_to_player(player, item_id, amount, source=FISHING_SOURCE_TEXT, rng=rng)
    name = item_display_name(item_id)
    rarity_name = {"common": "обычный улов", "uncommon": "необычный улов", "rare": "редкий улов", "trash": "мусор"}.get(rarity, rarity)
    notice = inventory_add_result_notice(add_result, name)
    return (
        "🎣 Поклёвка! Вы вытягиваете снасть.\n\n"
        f"Категория: {rarity_name}.\n"
        f"Получено: {name} ×{add_result.added}.{notice}"
    )


def complete_fishing_timer(storage: Any, player: dict[str, Any], timer_id: str | None = None, rng: random.Random | None = None) -> FishingResponse:
    """Resolve a finished fishing cast: grant the catch and clear the timer."""
    rng = rng or random.Random()
    timer = player.get("active_timer")
    if not _is_fishing_timer(timer):
        return FishingResponse("⏳ Активной рыбалки нет.", fishing_buttons())
    if timer_id and str(timer.get("id") or "") != str(timer_id):
        return FishingResponse("⏳ Этот заброс уже неактуален.", fishing_buttons())
    remaining = _fishing_timer_remaining(timer)
    if remaining > 0:
        return FishingResponse(
            f"⏳ Удочка ещё в воде. Поклёвка через {_format_duration(remaining)}.",
            fishing_timer_buttons(),
        )
    player["active_timer"] = None
    player["current_city"] = "seldar"
    player["current_zone"] = FISHING_ZONE
    player["location_id"] = FISHING_ZONE
    text = _grant_fishing_catch(player, rng)
    storage.update_player(player)
    return FishingResponse(text, fishing_buttons())


def _complete_fishing_once(storage: Any, player: dict[str, Any], rng: random.Random) -> FishingResponse:
    """Complete an expired fishing timer exactly once across platforms."""
    timer = player.get("active_timer")
    if not _is_fishing_timer(timer):
        return FishingResponse("⏳ Активной рыбалки нет.", fishing_buttons())
    if _fishing_timer_remaining(timer) > 0:
        return complete_fishing_timer(storage, player, timer.get("id"), rng)
    game_id = str(player.get("game_id") or player.get("id") or "")
    timer_id = str(timer.get("id") or "")
    claim = getattr(storage, "claim_active_timer_for_delivery", None)
    if game_id and timer_id and callable(claim):
        claimed = claim(game_id, timer_id, FISHING_COMPLETION_OWNER, claim_ttl_seconds=120, platform_filter=None)
        if not isinstance(claimed, dict):
            return FishingResponse("⏳ Этот заброс уже обработан (награда не выдаётся повторно).", fishing_buttons())
        # Переносим заклеймленную перезагрузку В исходный объект игрока: боты
        # после действия пересохраняют именно его. Иначе устаревший оригинал
        # (с истёкшим таймером и без улова) затёр бы выдачу награды.
        if claimed is not player:
            player.clear()
            player.update(claimed)
        return complete_fishing_timer(storage, player, timer_id, rng)
    return complete_fishing_timer(storage, player, timer_id, rng)


def handle_fishing_action(storage: Any, player: dict[str, Any], action: str, rng: random.Random | None = None) -> FishingResponse | None:
    rng = rng or random.Random()
    timer = player.get("active_timer")
    fishing_active = _is_fishing_timer(timer)
    in_fishing_zone = str(player.get("current_zone") or player.get("location_id") or "") == FISHING_ZONE

    if action == PIER_FISHING_ACTION:
        player["current_city"] = "seldar"
        player["current_zone"] = FISHING_ZONE
        player["location_id"] = FISHING_ZONE
        player.pop("market_context", None)
        player.pop("crafting_context", None)
        storage.update_player(player)
        if fishing_active and _fishing_timer_remaining(timer) > 0:
            return FishingResponse(
                f"🎣 Удочка уже заброшена. Поклёвка через {_format_duration(_fishing_timer_remaining(timer))}.",
                fishing_timer_buttons(),
            )
        return FishingResponse(fishing_intro_text(), fishing_buttons())

    if action == CHECK_FISHING_TIMER:
        # Only handle the timer check when a fishing cast is actually running;
        # otherwise let other workshop timers handle their own check button.
        if not fishing_active:
            return None
        return _complete_fishing_once(storage, player, rng)

    if action != START_PIER_FISHING:
        return None
    if not in_fishing_zone:
        return None

    player["current_city"] = "seldar"
    player["current_zone"] = FISHING_ZONE
    player["location_id"] = FISHING_ZONE
    player.pop("market_context", None)
    player.pop("crafting_context", None)

    if fishing_active:
        if _fishing_timer_remaining(timer) > 0:
            return FishingResponse(
                f"🎣 Удочка уже заброшена. Поклёвка через {_format_duration(_fishing_timer_remaining(timer))}.",
                fishing_timer_buttons(),
            )
        return _complete_fishing_once(storage, player, rng)

    # Another (non-fishing) timed action is running.
    if isinstance(timer, dict) and _fishing_timer_remaining(timer) > 0:
        storage.update_player(player)
        return FishingResponse("🎣 Сначала завершите текущее действие с таймером.", fishing_buttons())

    if not player_has_fishing_rod(player):
        storage.update_player(player)
        return FishingResponse("🎣 Для рыбалки нужна удочка рыбака. Без неё забросить снасть не получится.", fishing_buttons())

    energy = max(0, int(player.get("energy", player.get("current_energy", 0)) or 0))
    if energy < FISHING_ENERGY_COST:
        storage.update_player(player)
        return FishingResponse(f"🎣 Для заброса нужно {FISHING_ENERGY_COST} энергии. Сейчас энергии недостаточно.", fishing_buttons())

    player["energy"] = energy - FISHING_ENERGY_COST
    player["current_energy"] = player["energy"]
    new_timer = {
        "id": f"fishing_{uuid.uuid4().hex[:12]}",
        "type": FISHING_TIMER_TYPE,
        "seconds": FISHING_TIMER_SECONDS,
        "ends_at": _now_ts() + FISHING_TIMER_SECONDS,
        "energy_spent": FISHING_ENERGY_COST,
        "location_id": FISHING_ZONE,
    }
    player["active_timer"] = new_timer
    storage.update_player(player)
    text = (
        "🎣 Вы забрасываете удочку с пристани и ждёте поклёвку.\n\n"
        f"⏳ Поклёвка через {_format_duration(FISHING_TIMER_SECONDS)}.\n"
        f"⚡ Потрачено энергии: {FISHING_ENERGY_COST}. Осталось: {player['energy']}.\n\n"
        "Когда таймер закончится, придёт сообщение с уловом."
    )
    return FishingResponse(text, fishing_timer_buttons(), scheduled_timer=_fishing_timer_schedule(player, new_timer))


def choose_location_waterside_reward(location_id: str, rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.Random()
    sources = load_fishing_sources().get("location_waterside_find") or {}
    table = sources.get(location_id) or sources.get("hilly_meadows") or []
    if not table:
        return {"item_id": "seaweed", "amount": [1, 1], "weight": 1}
    return choose_loot_entry(table, rng)


def grant_waterside_reward(player: dict[str, Any], location_id: str, rng: random.Random | None = None) -> tuple[str, int, str]:
    rng = rng or random.Random()
    entry = choose_location_waterside_reward(location_id, rng)
    item_id = str(entry.get("item_id") or "seaweed")
    amount = _amount_from_entry(entry, rng)
    source = "Событие у воды: " + ("Обыкновенный лес" if location_id == "ordinary_forest" else "Холмистые луга")
    add_result = grant_item_to_player(player, item_id, amount, source=source, rng=rng)
    name = item_display_name(item_id)
    notice = inventory_add_result_notice(add_result, name)
    return name, int(add_result.added), notice
