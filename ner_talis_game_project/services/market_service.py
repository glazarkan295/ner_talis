"""NPC market logic for Seldar Trade District.

The market is intentionally handled in the shared service layer so Telegram and
VK use the same state machine, prices, inventory limits, overflow notices and
sell checks.
"""

from __future__ import annotations

import json
import random
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from project_paths import project_path
from services.derived_stats_service import safe_int
from services.inventory_service import (
    add_inventory_item,
    inventory_add_result_notice,
    recalculate_inventory_overflow,
    remove_empty_stacks_and_recalculate,
)
from services.item_registry import build_inventory_item, get_item_definition_by_id, get_item_definition_by_name, registry_item_to_inventory_item
from services.race_bonus_service import npc_purchase_refund_amount

MARKET_ZONE_PREFIX = "seldar_npc_market"
MARKET_MAIN_ZONE = "seldar_npc_market"
MARKET_BUY_ZONE = "seldar_npc_market_buy"
MARKET_SELL_ZONE = "seldar_npc_market_sell"

MARKET_ENTRY = "Рынок"
MARKET_BUY = "Купить"
MARKET_SELL = "Продать"
MARKET_BACK = "Назад"
MARKET_BACK_TO_MAIN = "Назад на рынок"
MARKET_EXIT_TO_TRADE_DISTRICT = "Торговый квартал"
LEGACY_MARKET_EXIT_TO_PAVILION = "Торговый павильон"
OPEN_PAVILION_SITE = "🌐 Открыть торговый павильон"
BACK_TO_CENTRAL = "⬅️ Центральная площадь"

MARKET_ACTIONS = frozenset({
    MARKET_ENTRY,
    MARKET_BUY,
    MARKET_SELL,
    MARKET_BACK,
    MARKET_BACK_TO_MAIN,
    MARKET_EXIT_TO_TRADE_DISTRICT,
    LEGACY_MARKET_EXIT_TO_PAVILION,
})
MARKET_DATA_PATH = project_path("data", "seldar_market.json")
SELL_PRICES_PATH = project_path("data", "item_sell_prices.json")


@dataclass(frozen=True)
class MarketResult:
    text: str
    buttons: list[list[str]]
    zone_id: str = MARKET_MAIN_ZONE


@dataclass(frozen=True)
class MarketItem:
    item_id: str
    display_name: str
    category: str
    description: str
    buy_price_copper: int


def _chunk_buttons(labels: list[str], row_size: int = 2) -> list[list[str]]:
    return [labels[index:index + row_size] for index in range(0, len(labels), row_size)]


def market_main_buttons() -> list[list[str]]:
    return [[MARKET_BUY, MARKET_SELL], [MARKET_EXIT_TO_TRADE_DISTRICT]]


def market_list_back_buttons() -> list[list[str]]:
    return [[MARKET_BACK_TO_MAIN]]


def market_card_buttons(confirm_label: str) -> list[list[str]]:
    return [[confirm_label], [MARKET_BACK]]


def _set_zone(player: dict[str, Any], zone_id: str) -> None:
    player["current_city"] = "seldar"
    player["current_zone"] = zone_id
    player["location_id"] = zone_id


def _clear_context(player: dict[str, Any]) -> None:
    player.pop("market_context", None)


def _set_context(player: dict[str, Any], **context: Any) -> None:
    player["market_context"] = context


def is_market_context(player: dict[str, Any]) -> bool:
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    return bool(player.get("market_context")) or zone.startswith(MARKET_ZONE_PREFIX)


def leave_market(player: dict[str, Any]) -> MarketResult:
    _clear_context(player)
    _set_zone(player, "seldar_trade_district")
    return MarketResult(
        "💰 Торговый квартал\n\nВы вышли с рынка в Торговый квартал Селдара. Здесь можно перейти в Торговую гильдию, Торговый павильон, аукцион или к торговому представителю.",
        [["Торговая гильдия", LEGACY_MARKET_EXIT_TO_PAVILION], [MARKET_ENTRY, "Аукцион"], ["Торговый представитель"], [BACK_TO_CENTRAL]],
        "seldar_trade_district",
    )


@lru_cache(maxsize=1)
def load_market_items() -> list[MarketItem]:
    if not MARKET_DATA_PATH.exists():
        return []
    payload = json.loads(MARKET_DATA_PATH.read_text(encoding="utf-8"))
    raw_items = payload.get("items", []) if isinstance(payload, dict) else []
    result: list[MarketItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or item.get("id") or "").strip()
        if not item_id:
            continue
        definition = get_item_definition_by_id(item_id) or {}
        display_name = str(item.get("display_name") or definition.get("name_ru") or definition.get("name") or item_id)
        description = str(item.get("description") or definition.get("description") or "Описание товара пока не добавлено.")
        result.append(
            MarketItem(
                item_id=item_id,
                display_name=display_name,
                category=str(item.get("category") or definition.get("category") or "Товар"),
                description=description,
                buy_price_copper=max(0, safe_int(item.get("buy_price_copper"), 0)),
            )
        )
    return result


@lru_cache(maxsize=1)
def _sell_price_index() -> dict[str, int]:
    if not SELL_PRICES_PATH.exists():
        return {}
    try:
        payload = json.loads(SELL_PRICES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    result: dict[str, int] = {}
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("id") or row.get("item_id") or "").strip()
            price = safe_int(row.get("sell_price_copper"), -1)
            if item_id and price >= 0:
                result[item_id] = price
    return result


def market_item_by_display_name(name: str) -> MarketItem | None:
    needle = str(name or "").strip().casefold()
    for item in load_market_items():
        if item.display_name.casefold() == needle:
            return item
    return None


def market_item_by_id(item_id: str) -> MarketItem | None:
    item_id = str(item_id or "").strip()
    for item in load_market_items():
        if item.item_id == item_id:
            return item
    return None


def market_buy_buttons() -> list[list[str]]:
    labels = [item.display_name for item in load_market_items()]
    return _chunk_buttons(labels, 1) + market_list_back_buttons()


def _money(player: dict[str, Any]) -> int:
    return max(0, safe_int(player.get("money_copper", player.get("money", 0)), 0))


def _set_money(player: dict[str, Any], value: int) -> None:
    value = max(0, safe_int(value, 0))
    player["money_copper"] = value
    player["money"] = value


def _inventory_item_from_market(item: MarketItem, amount: int) -> dict[str, Any]:
    definition = get_item_definition_by_id(item.item_id)
    if definition:
        result = registry_item_to_inventory_item(definition, amount)
    else:
        result = build_inventory_item(item.display_name, amount, item_id=item.item_id)
    result.setdefault("description", item.description)
    result.setdefault("category", item.category)
    result["purchase_price_copper"] = item.buy_price_copper
    result.setdefault("can_sell", True)
    return result


def open_market(player: dict[str, Any]) -> MarketResult:
    _set_zone(player, MARKET_MAIN_ZONE)
    _set_context(player, mode="main")
    text = (
        "🛒 Рынок Торгового квартала\n\n"
        "Здесь можно безопасно покупать базовые товары у NPC и продавать лишние предметы.\n\n"
        "Выберите действие:"
    )
    return MarketResult(text, market_main_buttons(), MARKET_MAIN_ZONE)


def open_buy_list(player: dict[str, Any]) -> MarketResult:
    _set_zone(player, MARKET_BUY_ZONE)
    _set_context(player, mode="buy_list")
    text = (
        "🛒 Покупка у NPC\n\n"
        "Все цены указаны в медных монетах за 1 единицу товара.\n"
        "Выберите товар:"
    )
    return MarketResult(text, market_buy_buttons(), MARKET_BUY_ZONE)


def open_sell_list(player: dict[str, Any]) -> MarketResult:
    _set_zone(player, MARKET_SELL_ZONE)
    sellable = sellable_inventory_entries(player)
    _set_context(player, mode="sell_list")
    if not sellable:
        return MarketResult(
            "💰 Продажа NPC\n\nВ инвентаре нет предметов, которые можно продать NPC-рынку.",
            market_list_back_buttons(),
            MARKET_SELL_ZONE,
        )
    labels = [entry["label"] for entry in sellable]
    return MarketResult(
        "💰 Продажа NPC\n\nВыберите предмет из инвентаря для продажи. Экипированные, квестовые и защищённые предметы не показываются.",
        _chunk_buttons(labels, 1) + market_list_back_buttons(),
        MARKET_SELL_ZONE,
    )


def show_buy_card(player: dict[str, Any], item: MarketItem) -> MarketResult:
    _set_zone(player, MARKET_BUY_ZONE)
    _set_context(player, mode="buy_card", item_id=item.item_id)
    text = (
        f"{item.display_name}\n"
        f"Описание: {item.description}\n"
        f"Категория: {item.category}\n"
        f"Цена покупки за 1 единицу: {item.buy_price_copper} медных"
    )
    return MarketResult(text, market_card_buttons(MARKET_BUY), MARKET_BUY_ZONE)


def ask_buy_quantity(player: dict[str, Any], item: MarketItem) -> MarketResult:
    _set_zone(player, MARKET_BUY_ZONE)
    _set_context(player, mode="buy_quantity", item_id=item.item_id)
    return MarketResult(
        f"Введите количество товара, которое хотите купить.\n\nТовар: {item.display_name}\nЦена за 1 единицу: {item.buy_price_copper} медных",
        [[MARKET_BACK]],
        MARKET_BUY_ZONE,
    )


def handle_buy_quantity(storage: Any, player: dict[str, Any], item: MarketItem, raw_quantity: str) -> MarketResult:
    quantity = _parse_positive_int(raw_quantity)
    if quantity is None:
        return MarketResult(
            "Такое количество купить нельзя. Введите целое число больше 0.",
            [[MARKET_BACK]],
            MARKET_BUY_ZONE,
        )

    total_price = item.buy_price_copper * quantity
    balance = _money(player)
    if balance < total_price:
        return MarketResult(
            f"Недостаточно монет. Нужно: {total_price}. На балансе: {balance}. Не хватает: {total_price - balance}.",
            [[MARKET_BACK]],
            MARKET_BUY_ZONE,
        )

    inventory_item = _inventory_item_from_market(item, quantity)
    simulated = deepcopy(player)
    result = add_inventory_item(simulated, inventory_item, quantity)
    if result.added < quantity:
        return MarketResult(
            "Покупка не выполнена: в инвентаре и дополнительных слотах не хватает места для всего количества. "
            f"Можно было бы разместить: {result.added}/{quantity}.",
            [[MARKET_BACK]],
            MARKET_BUY_ZONE,
        )

    # Commit inventory-related fields from the simulated profile, then charge money.
    for key in (
        "inventory",
        "active_effects",
        "overflow_inventory_slots_used",
        "overflow_inventory_slots_max",
        "inventory_overflow_no_escape",
    ):
        if key in simulated:
            player[key] = simulated[key]
    refund = npc_purchase_refund_amount(player, total_price)
    _set_money(player, balance - total_price + refund)

    notice = inventory_add_result_notice(result, item.display_name)
    refund_text = f" Возврат золота: +{refund} медных." if refund else ""
    list_result = open_buy_list(player)
    storage.update_player(player)
    return MarketResult(
        f"Куплено: {item.display_name} ×{quantity}. Потрачено: {total_price} медных.{refund_text}{notice}\n\nВыберите следующий товар:",
        list_result.buttons,
        list_result.zone_id,
    )


def _item_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("item_id") or item.get("name") or "").strip()


def _item_name(item: dict[str, Any]) -> str:
    return str(item.get("name_ru") or item.get("name") or item.get("id") or "Предмет")


def _is_sell_protected(item: dict[str, Any]) -> bool:
    if bool(item.get("equipped") or item.get("is_equipped")):
        return True
    if bool(item.get("quest_item") or item.get("locked") or item.get("protected")):
        return True
    # bound_on_receive blocks player trading, but NPC selling is controlled by
    # can_sell/sell_price_copper. Starter gear is bound but still sellable.
    if item.get("can_sell") is False:
        return True
    return False


def item_sell_price(item: dict[str, Any]) -> int:
    raw_price = item.get("sell_price_copper", item.get("sellPriceCopper"))
    price = safe_int(raw_price, -1)
    if price >= 0:
        return price
    item_id = _item_id(item)
    if item_id in _sell_price_index():
        return _sell_price_index()[item_id]
    definition = get_item_definition_by_id(item_id) or get_item_definition_by_name(_item_name(item))
    if definition:
        return safe_int(definition.get("sell_price_copper"), -1)
    return -1


def sellable_inventory_entries(player: dict[str, Any]) -> list[dict[str, Any]]:
    entries_by_id: dict[str, dict[str, Any]] = {}
    for item in player.get("inventory", []):
        if not isinstance(item, dict) or _is_sell_protected(item):
            continue
        price = item_sell_price(item)
        if price < 0:
            continue
        item_id = _item_id(item)
        if not item_id:
            continue
        amount = max(0, safe_int(item.get("amount"), 1))
        if amount <= 0:
            continue
        entry = entries_by_id.setdefault(
            item_id,
            {
                "item_id": item_id,
                "name": _item_name(item),
                "description": item.get("description") or "Описание предмета пока не добавлено.",
                "quantity": 0,
                "price": price,
            },
        )
        entry["quantity"] += amount
        entry["price"] = price
    result = []
    for entry in entries_by_id.values():
        entry["label"] = f"{entry['name']} ×{entry['quantity']}"
        result.append(entry)
    result.sort(key=lambda entry: entry["name"].casefold())
    return result


def sell_entry_by_label(player: dict[str, Any], label: str) -> dict[str, Any] | None:
    needle = str(label or "").strip().casefold()
    for entry in sellable_inventory_entries(player):
        if entry["label"].casefold() == needle or entry["name"].casefold() == needle:
            return entry
    return None


def show_sell_card(player: dict[str, Any], entry: dict[str, Any]) -> MarketResult:
    _set_zone(player, MARKET_SELL_ZONE)
    _set_context(player, mode="sell_card", item_id=entry["item_id"])
    text = (
        f"{entry['name']}\n"
        f"Описание: {entry['description']}\n"
        f"Количество в инвентаре: {entry['quantity']}\n"
        f"Цена продажи за 1 единицу: {entry['price']} медных"
    )
    return MarketResult(text, market_card_buttons(MARKET_SELL), MARKET_SELL_ZONE)


def ask_sell_quantity(player: dict[str, Any], entry: dict[str, Any]) -> MarketResult:
    _set_zone(player, MARKET_SELL_ZONE)
    _set_context(player, mode="sell_quantity", item_id=entry["item_id"])
    return MarketResult(
        f"Введите количество предметов, которое хотите продать.\n\nПредмет: {entry['name']}\nДоступно: {entry['quantity']}\nЦена за 1 единицу: {entry['price']} медных",
        [[MARKET_BACK]],
        MARKET_SELL_ZONE,
    )


def _entry_by_id(player: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for entry in sellable_inventory_entries(player):
        if entry["item_id"] == item_id:
            return entry
    return None


def handle_sell_quantity(storage: Any, player: dict[str, Any], entry: dict[str, Any], raw_quantity: str) -> MarketResult:
    quantity = _parse_positive_int(raw_quantity)
    if quantity is None or quantity > safe_int(entry.get("quantity"), 0):
        return MarketResult(
            f"Такое количество продать нельзя. Введите число от 1 до {entry.get('quantity', 0)}.",
            [[MARKET_BACK]],
            MARKET_SELL_ZONE,
        )

    remaining = quantity
    inventory = player.setdefault("inventory", [])
    if not isinstance(inventory, list):
        inventory = []
        player["inventory"] = inventory
    for item in inventory:
        if remaining <= 0:
            break
        if not isinstance(item, dict) or _item_id(item) != entry["item_id"] or _is_sell_protected(item):
            continue
        current = max(0, safe_int(item.get("amount"), 1))
        take = min(current, remaining)
        item["amount"] = current - take
        remaining -= take

    if remaining > 0:
        return MarketResult("Продажа не выполнена: предмет уже недоступен в нужном количестве.", [[MARKET_BACK]], MARKET_SELL_ZONE)

    remove_empty_stacks_and_recalculate(player)
    total = quantity * safe_int(entry.get("price"), 0)
    _set_money(player, _money(player) + total)
    list_result = open_sell_list(player)
    storage.update_player(player)
    return MarketResult(
        f"Продано: {entry['name']} ×{quantity}. Получено: {total} медных.\n\n{list_result.text}",
        list_result.buttons,
        list_result.zone_id,
    )


def _parse_positive_int(raw: str) -> int | None:
    value = str(raw or "").strip()
    if not value.isdigit():
        return None
    result = int(value)
    return result if result > 0 else None


def handle_market_action(storage: Any, player: dict[str, Any], action: str) -> MarketResult:
    action = str(action or "").strip()
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    mode = str(context.get("mode") or "")

    if action in {MARKET_EXIT_TO_TRADE_DISTRICT, LEGACY_MARKET_EXIT_TO_PAVILION}:
        result = leave_market(player)
        storage.update_player(player)
        return result

    if action == MARKET_BACK_TO_MAIN:
        result = open_market(player)
        storage.update_player(player)
        return result

    if action == MARKET_BACK:
        if mode in {"buy_card", "buy_quantity"}:
            result = open_buy_list(player)
        elif mode in {"sell_card", "sell_quantity"}:
            result = open_sell_list(player)
        elif mode in {"buy_list", "sell_list"}:
            result = open_market(player)
        elif mode == "main":
            result = leave_market(player)
        else:
            result = leave_market(player)
        storage.update_player(player)
        return result

    if action == MARKET_ENTRY:
        result = open_market(player)
        storage.update_player(player)
        return result

    if action == MARKET_BUY:
        if mode == "buy_card":
            item = market_item_by_id(str(context.get("item_id") or ""))
            result = ask_buy_quantity(player, item) if item else open_buy_list(player)
        else:
            result = open_buy_list(player)
        storage.update_player(player)
        return result

    if action == MARKET_SELL:
        if mode == "sell_card":
            entry = _entry_by_id(player, str(context.get("item_id") or ""))
            result = ask_sell_quantity(player, entry) if entry else open_sell_list(player)
        else:
            result = open_sell_list(player)
        storage.update_player(player)
        return result

    if mode == "buy_quantity":
        item = market_item_by_id(str(context.get("item_id") or ""))
        if not item:
            result = open_buy_list(player)
            storage.update_player(player)
            return result
        return handle_buy_quantity(storage, player, item, action)

    if mode == "sell_quantity":
        entry = _entry_by_id(player, str(context.get("item_id") or ""))
        if not entry:
            result = open_sell_list(player)
            storage.update_player(player)
            return result
        return handle_sell_quantity(storage, player, entry, action)

    if mode == "buy_list" or is_market_context(player):
        item = market_item_by_display_name(action)
        if item:
            result = show_buy_card(player, item)
            storage.update_player(player)
            return result

    if mode == "sell_list" or is_market_context(player):
        entry = sell_entry_by_label(player, action)
        if entry:
            result = show_sell_card(player, entry)
            storage.update_player(player)
            return result

    result = open_market(player)
    storage.update_player(player)
    return result
