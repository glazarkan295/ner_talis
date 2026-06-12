
"""Fishing and waterside loot helpers for Ner-Talis locations.

The service keeps the loot table data-driven so port fishing and later boat/ocean
fishing can share the same item-granting code without hard-coding every reward
inside the city router.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Iterable

from project_paths import resolve_project_path
from services.inventory_service import add_inventory_item, apply_generated_item_level_and_price, inventory_add_result_notice
from services.item_registry import build_inventory_item, get_item_definition_by_id, slugify_fallback_item_id

PIER_FISHING_ACTION = "Рыбалка на пристани"
START_PIER_FISHING = "Забросить удочку"
BACK_TO_PIER = "Пристань"
FISHING_ACTIONS = frozenset({PIER_FISHING_ACTION, START_PIER_FISHING})
FISHING_ZONE = "seldar_pier_fishing"
FISHING_SOURCE_TEXT = "Рыбалка на пристани"


@dataclass(frozen=True)
class FishingResponse:
    text: str
    buttons: list[list[str]]
    zone_id: str = FISHING_ZONE


def fishing_buttons() -> list[list[str]]:
    return [[START_PIER_FISHING], [BACK_TO_PIER, "Портовый квартал"], ["⬅️ Центральная площадь"]]


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
        "Для действия нужна удочка рыбака. Один заброс тратит 2 энергии.\n\n"
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


def handle_fishing_action(storage: Any, player: dict[str, Any], action: str, rng: random.Random | None = None) -> FishingResponse | None:
    rng = rng or random.Random()
    if action == PIER_FISHING_ACTION:
        player["current_city"] = "seldar"
        player["current_zone"] = FISHING_ZONE
        player["location_id"] = FISHING_ZONE
        player.pop("market_context", None)
        player.pop("crafting_context", None)
        storage.update_player(player)
        return FishingResponse(fishing_intro_text(), fishing_buttons())

    if action != START_PIER_FISHING:
        return None
    if str(player.get("current_zone") or player.get("location_id") or "") != FISHING_ZONE:
        return None

    player["current_city"] = "seldar"
    player["current_zone"] = FISHING_ZONE
    player["location_id"] = FISHING_ZONE
    player.pop("market_context", None)
    player.pop("crafting_context", None)

    if not player_has_fishing_rod(player):
        storage.update_player(player)
        return FishingResponse("🎣 Для рыбалки нужна удочка рыбака. Без неё забросить снасть не получится.", fishing_buttons())

    energy = max(0, int(player.get("energy", player.get("current_energy", 0)) or 0))
    energy_cost = int((load_fishing_sources().get("pier_fishing") or {}).get("energy_cost", 2) or 2)
    if energy < energy_cost:
        storage.update_player(player)
        return FishingResponse(f"🎣 Для заброса нужно {energy_cost} энергии. Сейчас энергии недостаточно.", fishing_buttons())

    player["energy"] = energy - energy_cost
    player["current_energy"] = player["energy"]
    rarity, entry = choose_pier_fishing_reward(rng)
    item_id = str(entry.get("item_id") or "old_torn_boot")
    amount = _amount_from_entry(entry, rng)
    add_result = grant_item_to_player(player, item_id, amount, source=FISHING_SOURCE_TEXT, rng=rng)
    name = item_display_name(item_id)
    rarity_name = {"common": "обычный улов", "uncommon": "необычный улов", "rare": "редкий улов", "trash": "мусор"}.get(rarity, rarity)
    notice = inventory_add_result_notice(add_result, name)
    storage.update_player(player)
    text = (
        "🎣 Вы забрасываете удочку с пристани и ждёте поклёвку.\n\n"
        f"Категория: {rarity_name}.\n"
        f"Получено: {name} ×{add_result.added}."
        f"{notice}\n\n"
        f"⚡ Потрачено энергии: {energy_cost}. Осталось: {player['energy']}."
    )
    return FishingResponse(text, fishing_buttons())


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
