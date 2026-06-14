"""NPC market logic for Seldar Trade District.

The market is intentionally handled in the shared service layer so Telegram and
VK use the same state machine, prices, inventory limits, overflow notices and
sell checks.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from project_paths import project_path
from services.currency import format_price
from services.derived_stats_service import equipment_modifier_totals, safe_int
from services.inventory_service import (
    add_inventory_item,
    inventory_add_result_notice,
    recalculate_inventory_overflow,
    remove_empty_stacks_and_recalculate,
)
from services.item_registry import build_inventory_item, get_item_definition_by_id, get_item_definition_by_name, load_all_item_definitions, registry_item_to_inventory_item
from services.race_bonus_service import npc_purchase_refund_amount, npc_transaction_bonus_amount

MARKET_ZONE_PREFIX = "seldar_npc_market"
MARKET_MAIN_ZONE = "seldar_npc_market"
MARKET_BUY_ZONE = "seldar_npc_market_buy"
MARKET_SELL_ZONE = "seldar_npc_market_sell"

MARKET_ENTRY = "Рынок"
PORT_MARKET_ENTRY = "Портовый рынок"
BLACK_MARKET_ENTRY = "Чёрный рынок"
MARKET_BUY = "Купить"
MARKET_SELL = "Продать"
MARKET_BACK = "Назад"
MARKET_BACK_TO_MAIN = "Назад на рынок"
MARKET_EXIT_TO_TRADE_DISTRICT = "Торговый квартал"
LEGACY_MARKET_EXIT_TO_PAVILION = "Торговый павильон"
OPEN_PAVILION_SITE = "🌐 Открыть торговый павильон"
BACK_TO_CENTRAL = "⬅️ Центральная площадь"
MARKET_BUY_PAGE_NEXT = "Покупка далее"
MARKET_BUY_PAGE_PREV = "Покупка назад"
MARKET_SELL_PAGE_NEXT = "Продажа далее"
MARKET_SELL_PAGE_PREV = "Продажа назад"
MARKET_LIST_PAGE_SIZE = 16

MARKET_ENTRY_ACTIONS = frozenset({MARKET_ENTRY, PORT_MARKET_ENTRY, BLACK_MARKET_ENTRY})

MARKET_KIND_NPC = "npc"
MARKET_KIND_PORT = "port"
MARKET_KIND_BLACK = "black"
MARKET_KIND_BY_ENTRY = {
    MARKET_ENTRY: MARKET_KIND_NPC,
    PORT_MARKET_ENTRY: MARKET_KIND_PORT,
    BLACK_MARKET_ENTRY: MARKET_KIND_BLACK,
}
MARKET_CONFIGS = {
    MARKET_KIND_NPC: {
        "title": "Рынок Торгового квартала",
        "emoji": "🛒",
        "main_zone": MARKET_MAIN_ZONE,
        "buy_zone": MARKET_BUY_ZONE,
        "sell_zone": MARKET_SELL_ZONE,
        "exit": MARKET_EXIT_TO_TRADE_DISTRICT,
        "exit_text": "💰 Торговый квартал\n\nВы вышли с рынка в Торговый квартал Селдара.",
        "source_tag": None,
    },
    MARKET_KIND_PORT: {
        "title": "Портовый рынок",
        "emoji": "🧺",
        "main_zone": "seldar_npc_market_port",
        "buy_zone": "seldar_npc_market_port_buy",
        "sell_zone": "seldar_npc_market_port_sell",
        "exit": "Портовый квартал",
        "exit_text": "⚓ Портовый квартал\n\nВы вышли с портового рынка к шумным причалам Селдара.",
        "source_tag": "port_market",
    },
    MARKET_KIND_BLACK: {
        "title": "Чёрный рынок",
        "emoji": "🕯",
        "main_zone": "seldar_npc_market_black",
        "buy_zone": "seldar_npc_market_black_buy",
        "sell_zone": "seldar_npc_market_black_sell",
        "exit": "Тёмные переулки",
        "exit_text": "🌑 Тёмные переулки\n\nВы отходите от чёрного рынка в тень узких переулков.",
        "source_tag": "black_market",
    },
}

MARKET_ACTIONS = frozenset({
    MARKET_ENTRY,
    PORT_MARKET_ENTRY,
    BLACK_MARKET_ENTRY,
    MARKET_BUY,
    MARKET_SELL,
    MARKET_BACK,
    MARKET_BACK_TO_MAIN,
    MARKET_EXIT_TO_TRADE_DISTRICT,
    LEGACY_MARKET_EXIT_TO_PAVILION,
    MARKET_BUY_PAGE_NEXT,
    MARKET_BUY_PAGE_PREV,
    MARKET_SELL_PAGE_NEXT,
    MARKET_SELL_PAGE_PREV,
})
MARKET_DATA_PATH = project_path("data", "seldar_market.json")
SELL_PRICES_PATH = project_path("data", "item_sell_prices.json")

# --- Port market rotation -------------------------------------------------
# The port market sells only a rotating subset of this fixed pool. Each
# rotation shows 4-7 items, each with a random in-stock quantity in its range,
# and refreshes every 5-10 days. Prices are in copper.
PORT_MARKET_POOL = [
    {"item_id": "common_cleansing_potion", "name": "Обычное зелье очищения", "min": 50, "max": 100, "price": 1000},
    {"item_id": "minor_regeneration_potion", "name": "Малое зелье регенерации", "min": 30, "max": 70, "price": 4000},
    {"item_id": "artifact_free_space", "name": "Артефакт Свободного Пространства", "min": 1, "max": 10, "price": 1_000_000},
    {"item_id": "one_time_artifact_last_chance", "name": "Одноразовый Артефакт Последнего Шанса", "min": 1, "max": 3, "price": 10_000_000},
    {"item_id": "artifact_lucky_buyer", "name": "Артефакт Счастливого покупателя", "min": 1, "max": 10, "price": 20_000_000},
    {"item_id": "arrow_for_bow", "name": "Стрела для лука", "min": 400, "max": 1000, "price": 4},
    {"item_id": "bolt_for_crossbow", "name": "Болт для арбалета", "min": 400, "max": 1000, "price": 4},
    {"item_id": "professional_bolt_quiver", "name": "Колчан профессионала для болтов", "min": 20, "max": 60, "price": 300},
    {"item_id": "professional_arrow_quiver", "name": "Колчан профессионала для стрел", "min": 20, "max": 60, "price": 300},
    {"item_id": "mana_crystal", "name": "Кристалл маны", "min": 10, "max": 30, "price": 7000},
    {"item_id": "spirit_crystal", "name": "Кристалл духа", "min": 10, "max": 30, "price": 7000},
    {"item_id": "life_crystal", "name": "Кристалл жизни", "min": 10, "max": 30, "price": 7000},
]
PORT_MARKET_POOL_BY_ID = {entry["item_id"]: entry for entry in PORT_MARKET_POOL}
PORT_ROTATION_MIN_ITEMS = 4
PORT_ROTATION_MAX_ITEMS = 7
PORT_ROTATION_MIN_DAYS = 5
PORT_ROTATION_MAX_DAYS = 10
DAY_SECONDS = 86400


def _port_state_path():
    return project_path(*os.getenv("PORT_MARKET_STATE_PATH", "data/port_market_state.json").split("/"))


def _load_port_state() -> dict[str, Any]:
    path = _port_state_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_port_state(state: dict[str, Any]) -> None:
    path = _port_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def _generate_port_rotation(now: float, rng: random.Random) -> dict[str, Any]:
    count = rng.randint(PORT_ROTATION_MIN_ITEMS, PORT_ROTATION_MAX_ITEMS)
    chosen = rng.sample(PORT_MARKET_POOL, min(count, len(PORT_MARKET_POOL)))
    items = [{"item_id": entry["item_id"], "stock": rng.randint(entry["min"], entry["max"])} for entry in chosen]
    days = rng.randint(PORT_ROTATION_MIN_DAYS, PORT_ROTATION_MAX_DAYS)
    return {"generated_at": now, "expires_at": now + days * DAY_SECONDS, "items": items}


def port_market_rotation(now: float | None = None, rng: random.Random | None = None) -> dict[str, Any]:
    """Return the current port rotation, regenerating it when it has expired."""
    now = time.time() if now is None else now
    rng = rng or random.Random()
    state = _load_port_state()
    items = state.get("items")
    if not isinstance(items, list) or not items or float(state.get("expires_at") or 0) <= now:
        state = _generate_port_rotation(now, rng)
        _save_port_state(state)
    return state


def deplete_port_stock(item_id: str, amount: int) -> None:
    """Reduce the rotation stock of a port item after a purchase."""
    state = _load_port_state()
    items = state.get("items")
    if not isinstance(items, list):
        return
    changed = False
    for entry in items:
        if isinstance(entry, dict) and str(entry.get("item_id")) == str(item_id):
            entry["stock"] = max(0, safe_int(entry.get("stock"), 0) - max(0, int(amount)))
            changed = True
            break
    if changed:
        _save_port_state(state)


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
    stock: int = -1  # -1 = unlimited; >=0 = limited rotation stock (port market)


def _chunk_buttons(labels: list[str], row_size: int = 2) -> list[list[str]]:
    return [labels[index:index + row_size] for index in range(0, len(labels), row_size)]


def _clamped_page(total_items: int, page: int, page_size: int = MARKET_LIST_PAGE_SIZE) -> int:
    if total_items <= 0:
        return 0
    max_page = max(0, (total_items - 1) // page_size)
    return max(0, min(page, max_page))


def _page_slice(items: list[Any], page: int, page_size: int = MARKET_LIST_PAGE_SIZE) -> tuple[int, int, int, list[Any]]:
    page = _clamped_page(len(items), page, page_size)
    start = page * page_size
    end = min(len(items), start + page_size)
    return page, start, end, items[start:end]


def _parse_numbered_action(action: str, prefix: str) -> int | None:
    text = str(action or "").strip()
    marker = f"{prefix} "
    if not text.startswith(marker):
        return None
    raw_number = text[len(marker):].strip()
    if not raw_number.isdigit():
        return None
    number = int(raw_number)
    return number if number > 0 else None


def _market_config(kind: str | None) -> dict[str, Any]:
    return MARKET_CONFIGS.get(str(kind or MARKET_KIND_NPC), MARKET_CONFIGS[MARKET_KIND_NPC])


def _market_kind_from_context(player: dict[str, Any]) -> str:
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    kind = str(context.get("market_kind") or "").strip()
    if kind in MARKET_CONFIGS:
        return kind
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    if "_port" in zone:
        return MARKET_KIND_PORT
    if "_black" in zone:
        return MARKET_KIND_BLACK
    return MARKET_KIND_NPC


def _market_zone(kind: str, section: str = "main") -> str:
    config = _market_config(kind)
    if section == "buy":
        return str(config["buy_zone"])
    if section == "sell":
        return str(config["sell_zone"])
    return str(config["main_zone"])


def market_main_buttons(kind: str = MARKET_KIND_NPC) -> list[list[str]]:
    return [[MARKET_BUY, MARKET_SELL], [str(_market_config(kind)["exit"])] ]


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
    if "market_kind" not in context:
        context["market_kind"] = _market_kind_from_context(player)
    player["market_context"] = context


def is_market_context(player: dict[str, Any]) -> bool:
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    return bool(player.get("market_context")) or zone.startswith(MARKET_ZONE_PREFIX)


def leave_market(player: dict[str, Any]) -> MarketResult:
    kind = _market_kind_from_context(player)
    config = _market_config(kind)
    _clear_context(player)
    exit_label = str(config["exit"])
    if kind == MARKET_KIND_PORT:
        _set_zone(player, "seldar_port_district")
        buttons = [["Тёмные переулки", "Пристань"], [PORT_MARKET_ENTRY, "Таверна"], [BACK_TO_CENTRAL]]
        zone = "seldar_port_district"
    elif kind == MARKET_KIND_BLACK:
        _set_zone(player, "seldar_dark_alleys")
        buttons = [[BLACK_MARKET_ENTRY, "Информатор Крот"], ["Подпольное казино"], ["Портовый квартал", BACK_TO_CENTRAL]]
        zone = "seldar_dark_alleys"
    else:
        _set_zone(player, "seldar_trade_district")
        buttons = [["Торговая гильдия", LEGACY_MARKET_EXIT_TO_PAVILION], [MARKET_ENTRY, "Аукцион"], ["Торговый представитель"], [BACK_TO_CENTRAL]]
        zone = "seldar_trade_district"
    return MarketResult(str(config["exit_text"]), buttons, zone)


def _port_market_items() -> list[MarketItem]:
    """Build the port market list from the current (live) rotation + stock."""
    rotation = port_market_rotation()
    result: list[MarketItem] = []
    for entry in rotation.get("items") or []:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id") or "").strip()
        pool = PORT_MARKET_POOL_BY_ID.get(item_id)
        if not pool:
            continue
        definition = get_item_definition_by_id(item_id) or {}
        result.append(
            MarketItem(
                item_id=item_id,
                display_name=str(pool["name"]),
                category=str(definition.get("category_ru") or definition.get("category") or "Портовый товар"),
                description=str(definition.get("description") or "Товар портового рынка."),
                buy_price_copper=max(0, int(pool["price"])),
                stock=max(0, safe_int(entry.get("stock"), 0)),
            )
        )
    return result


def load_market_items(kind: str = MARKET_KIND_NPC) -> list[MarketItem]:
    if kind == MARKET_KIND_PORT:
        return _port_market_items()
    return _load_static_market_items(kind)


@lru_cache(maxsize=4)
def _load_static_market_items(kind: str = MARKET_KIND_NPC) -> list[MarketItem]:
    config = _market_config(kind)
    source_tag = config.get("source_tag")
    raw_items: list[dict[str, Any]] = []
    if source_tag:
        for definition in load_all_item_definitions():
            if not isinstance(definition, dict):
                continue
            tags = {str(tag) for tag in (definition.get("integration_tags") or [])}
            if str(source_tag) not in tags:
                continue
            buy_price = safe_int(definition.get("buy_price_copper"), -1)
            if buy_price < 0:
                continue
            raw_items.append({
                "item_id": definition.get("item_id") or definition.get("id"),
                "display_name": definition.get("name_ru") or definition.get("name"),
                "category": definition.get("category_ru") or definition.get("category") or "Товар",
                "description": definition.get("description") or "Описание товара пока не добавлено.",
                "buy_price_copper": buy_price,
            })
    else:
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
                category=str(item.get("category") or definition.get("category_ru") or definition.get("category") or "Товар"),
                description=description,
                buy_price_copper=max(0, safe_int(item.get("buy_price_copper"), 0)),
            )
        )
    if source_tag:
        result.sort(key=lambda item: (item.category.casefold(), item.display_name.casefold()))
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


def market_item_by_display_name(name: str, kind: str = MARKET_KIND_NPC) -> MarketItem | None:
    needle = str(name or "").strip().casefold()
    for item in load_market_items(kind):
        if item.display_name.casefold() == needle:
            return item
    return None


def market_item_by_id(item_id: str, kind: str = MARKET_KIND_NPC) -> MarketItem | None:
    item_id = str(item_id or "").strip()
    for item in load_market_items(kind):
        if item.item_id == item_id:
            return item
    return None


def market_item_by_number(number: int | None, kind: str = MARKET_KIND_NPC) -> MarketItem | None:
    if number is None:
        return None
    items = load_market_items(kind)
    index = number - 1
    if 0 <= index < len(items):
        return items[index]
    return None


def sell_entry_by_number(player: dict[str, Any], number: int | None) -> dict[str, Any] | None:
    if number is None:
        return None
    entries = sellable_inventory_entries(player)
    index = number - 1
    if 0 <= index < len(entries):
        return entries[index]
    return None


def market_buy_buttons(kind: str = MARKET_KIND_NPC, page: int = 0) -> list[list[str]]:
    items = load_market_items(kind)
    page, start, end, _page_items = _page_slice(items, page)
    labels = [f"{MARKET_BUY} {index}" for index in range(start + 1, end + 1)]
    rows = _chunk_buttons(labels, 2)
    nav = []
    if page > 0:
        nav.append(MARKET_BUY_PAGE_PREV)
    if end < len(items):
        nav.append(MARKET_BUY_PAGE_NEXT)
    if nav:
        rows.append(nav)
    return rows + market_list_back_buttons()


def _npc_buy_discount_percent(player: dict[str, Any]) -> int:
    mods = equipment_modifier_totals(player)
    return max(0, min(90, safe_int(mods.get("bonus_npc_buy_discount_percent"), 0)))


def _npc_sell_bonus_percent(player: dict[str, Any]) -> int:
    mods = equipment_modifier_totals(player)
    return max(0, safe_int(mods.get("bonus_npc_sell_bonus_percent"), 0))


def _discounted_buy_price(player: dict[str, Any], unit_price: int) -> int:
    discount = _npc_buy_discount_percent(player)
    if discount <= 0:
        return max(0, unit_price)
    return max(0, math.floor(unit_price * (100 - discount) / 100))


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


def open_market(player: dict[str, Any], kind: str | None = None) -> MarketResult:
    kind = kind or _market_kind_from_context(player)
    config = _market_config(kind)
    _set_zone(player, _market_zone(kind, "main"))
    _set_context(player, mode="main", market_kind=kind)
    text = (
        f"{config['emoji']} {config['title']}\n\n"
        "Здесь можно покупать товары у NPC и продавать лишние предметы.\n"
        "На запрещённых рынках каждое действие может привлечь стражу.\n\n"
        "Выберите действие:"
    )
    return MarketResult(text, market_main_buttons(kind), _market_zone(kind, "main"))


def open_buy_list(player: dict[str, Any], page: int | None = None) -> MarketResult:
    kind = _market_kind_from_context(player)
    config = _market_config(kind)
    items = load_market_items(kind)
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    page_value = safe_int(page if page is not None else context.get("page"), 0)
    page_value, start, end, page_items = _page_slice(items, page_value)
    _set_zone(player, _market_zone(kind, "buy"))
    _set_context(player, mode="buy_list", page=page_value, market_kind=kind)
    if not items:
        return MarketResult(
            f"{config['emoji']} Покупка у NPC: {config['title']}\n\nСейчас у торговца нет товаров.",
            market_list_back_buttons(),
            _market_zone(kind, "buy"),
        )
    lines = [
        f"{config['emoji']} Покупка у NPC: {config['title']}",
        "",
        "Цены указаны за 1 единицу товара.",
        f"Страница {page_value + 1} из {max(1, (len(items) - 1) // MARKET_LIST_PAGE_SIZE + 1)}.",
        "Выберите товар: нажмите короткую кнопку с номером товара:",
        "",
    ]
    for offset, item in enumerate(page_items, start=start + 1):
        stock_suffix = f" (в наличии: {item.stock})" if item.stock >= 0 else ""
        lines.append(f"{offset}. {item.display_name} — {format_price(item.buy_price_copper)}{stock_suffix}")
    return MarketResult("\n".join(lines), market_buy_buttons(kind, page_value), _market_zone(kind, "buy"))


def market_sell_buttons(player: dict[str, Any], page: int = 0) -> list[list[str]]:
    entries = sellable_inventory_entries(player)
    page, start, end, _page_entries = _page_slice(entries, page)
    labels = [f"{MARKET_SELL} {index}" for index in range(start + 1, end + 1)]
    rows = _chunk_buttons(labels, 2)
    nav = []
    if page > 0:
        nav.append(MARKET_SELL_PAGE_PREV)
    if end < len(entries):
        nav.append(MARKET_SELL_PAGE_NEXT)
    if nav:
        rows.append(nav)
    return rows + market_list_back_buttons()


def open_sell_list(player: dict[str, Any], page: int | None = None) -> MarketResult:
    kind = _market_kind_from_context(player)
    config = _market_config(kind)
    _set_zone(player, _market_zone(kind, "sell"))
    sellable = sellable_inventory_entries(player)
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    page_value = safe_int(page if page is not None else context.get("page"), 0)
    page_value, start, _end, page_entries = _page_slice(sellable, page_value)
    _set_context(player, mode="sell_list", page=page_value, market_kind=kind)
    if not sellable:
        return MarketResult(
            f"💰 Продажа NPC: {config['title']}\n\nВ инвентаре нет предметов, которые можно продать NPC-рынку.",
            market_list_back_buttons(),
            _market_zone(kind, "sell"),
        )
    lines = [
        f"💰 Продажа NPC: {config['title']}",
        "",
        "Выберите предмет из инвентаря для продажи. Экипированные, квестовые и защищённые предметы не показываются.",
        f"Страница {page_value + 1} из {max(1, (len(sellable) - 1) // MARKET_LIST_PAGE_SIZE + 1)}.",
        "Выберите предмет: нажмите короткую кнопку с номером предмета:",
        "",
    ]
    for offset, entry in enumerate(page_entries, start=start + 1):
        lines.append(f"{offset}. {entry['name']} ×{entry['quantity']} — {format_price(entry['price'])}/ед.")
    return MarketResult(
        "\n".join(lines),
        market_sell_buttons(player, page_value),
        _market_zone(kind, "sell"),
    )


def show_buy_card(player: dict[str, Any], item: MarketItem) -> MarketResult:
    kind = _market_kind_from_context(player)
    _set_zone(player, _market_zone(kind, "buy"))
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    _set_context(player, mode="buy_card", item_id=item.item_id, page=safe_int(context.get("page"), 0), market_kind=kind)
    stock_line = f"\nВ наличии: {item.stock} шт" if item.stock >= 0 else ""
    text = (
        f"{item.display_name}\n"
        f"Описание: {item.description}\n"
        f"Категория: {item.category}\n"
        f"Цена покупки за 1 единицу: {format_price(item.buy_price_copper)}"
        f"{stock_line}"
    )
    return MarketResult(text, market_card_buttons(MARKET_BUY), _market_zone(kind, "buy"))


def ask_buy_quantity(player: dict[str, Any], item: MarketItem) -> MarketResult:
    kind = _market_kind_from_context(player)
    _set_zone(player, _market_zone(kind, "buy"))
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    _set_context(player, mode="buy_quantity", item_id=item.item_id, page=safe_int(context.get("page"), 0), market_kind=kind)
    return MarketResult(
        f"Введите количество товара, которое хотите купить.\n\nТовар: {item.display_name}\nЦена за 1 единицу: {format_price(item.buy_price_copper)}",
        [[MARKET_BACK]],
        _market_zone(kind, "buy"),
    )


def handle_buy_quantity(storage: Any, player: dict[str, Any], item: MarketItem, raw_quantity: str) -> MarketResult:
    kind = _market_kind_from_context(player)
    buy_zone = _market_zone(kind, "buy")
    quantity = _parse_positive_int(raw_quantity)
    if quantity is None:
        return MarketResult(
            "Такое количество купить нельзя. Введите целое число больше 0.",
            [[MARKET_BACK]],
            buy_zone,
        )

    # Port market sells from a limited rotation stock.
    if kind == MARKET_KIND_PORT:
        current = next((m for m in load_market_items(kind) if m.item_id == item.item_id), None)
        available = current.stock if current is not None else 0
        if available <= 0:
            return MarketResult("Этот товар закончился до следующего обновления ассортимента.", [[MARKET_BACK]], buy_zone)
        if quantity > available:
            return MarketResult(f"В наличии только {available} шт. Введите число не больше {available}.", [[MARKET_BACK]], buy_zone)

    unit_price = _discounted_buy_price(player, item.buy_price_copper)
    total_price = unit_price * quantity
    balance = _money(player)
    if balance < total_price:
        return MarketResult(
            f"Недостаточно монет. Нужно: {format_price(total_price)}. На балансе: {format_price(balance)}. Не хватает: {format_price(total_price - balance)}.",
            [[MARKET_BACK]],
            buy_zone,
        )

    inventory_item = _inventory_item_from_market(item, quantity)
    simulated = deepcopy(player)
    result = add_inventory_item(simulated, inventory_item, quantity)
    if result.added < quantity:
        return MarketResult(
            "Покупка не выполнена: в инвентаре и дополнительных слотах не хватает места для всего количества. "
            f"Можно было бы разместить: {result.added}/{quantity}.",
            [[MARKET_BACK]],
            buy_zone,
        )

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

    if kind == MARKET_KIND_PORT:
        deplete_port_stock(item.item_id, quantity)

    notice = inventory_add_result_notice(result, item.display_name)
    refund_text = f" Возврат золота: +{format_price(refund)}." if refund else ""
    list_result = open_buy_list(player)
    storage.update_player(player)
    return MarketResult(
        f"Куплено: {item.display_name} ×{quantity}. Потрачено: {format_price(total_price)}.{refund_text}{notice}\n\nВыберите следующий товар:",
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


def sellable_inventory_stack_entry(item: dict[str, Any], index: int | None = None) -> dict[str, Any] | None:
    """Return a sell entry for one concrete inventory stack.

    The profile UI must decorate actions per stack, not only by aggregated
    ``item_id``.  Otherwise a protected stack can inherit the sell button from
    another sellable stack with the same id.
    """
    if not isinstance(item, dict) or _is_sell_protected(item):
        return None
    price = item_sell_price(item)
    if price < 0:
        return None
    item_id = _item_id(item)
    if not item_id:
        return None
    amount = max(0, safe_int(item.get("amount"), 1))
    if amount <= 0:
        return None
    entry = {
        "item_id": item_id,
        "name": _item_name(item),
        "description": item.get("description") or "Описание предмета пока не добавлено.",
        "quantity": amount,
        "price": price,
    }
    if index is not None:
        entry["inventory_index"] = index
    entry["label"] = f"{entry['name']} ×{entry['quantity']}"
    return entry


def sellable_inventory_stack_indexes(player: dict[str, Any]) -> set[int]:
    """Return indexes of concrete stacks sellable from the profile UI."""
    if not is_profile_market_sell_enabled(player):
        return set()
    inventory = player.get("inventory", [])
    if not isinstance(inventory, list):
        return set()
    return {
        index
        for index, item in enumerate(inventory)
        if isinstance(item, dict) and sellable_inventory_stack_entry(item, index) is not None
    }


def sellable_inventory_entries(player: dict[str, Any]) -> list[dict[str, Any]]:
    entries_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(player.get("inventory", [])):
        if not isinstance(item, dict):
            continue
        stack_entry = sellable_inventory_stack_entry(item, index)
        if stack_entry is None:
            continue
        item_id = stack_entry["item_id"]
        entry = entries_by_id.setdefault(
            item_id,
            {
                "item_id": item_id,
                "name": stack_entry["name"],
                "description": stack_entry["description"],
                "quantity": 0,
                "price": stack_entry["price"],
            },
        )
        entry["quantity"] += stack_entry["quantity"]
        entry["price"] = stack_entry["price"]
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
    kind = _market_kind_from_context(player)
    sell_zone = _market_zone(kind, "sell")
    _set_zone(player, sell_zone)
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    _set_context(player, mode="sell_card", item_id=entry["item_id"], page=safe_int(context.get("page"), 0), market_kind=kind)
    text = (
        f"{entry['name']}\n"
        f"Описание: {entry['description']}\n"
        f"Количество в инвентаре: {entry['quantity']}\n"
        f"Цена продажи за 1 единицу: {format_price(entry['price'])}"
    )
    return MarketResult(text, market_card_buttons(MARKET_SELL), sell_zone)


def ask_sell_quantity(player: dict[str, Any], entry: dict[str, Any]) -> MarketResult:
    kind = _market_kind_from_context(player)
    sell_zone = _market_zone(kind, "sell")
    _set_zone(player, sell_zone)
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    _set_context(player, mode="sell_quantity", item_id=entry["item_id"], page=safe_int(context.get("page"), 0), market_kind=kind)
    return MarketResult(
        f"Введите количество предметов, которое хотите продать.\n\nПредмет: {entry['name']}\nДоступно: {entry['quantity']}\nЦена за 1 единицу: {format_price(entry['price'])}",
        [[MARKET_BACK]],
        sell_zone,
    )


def _entry_by_id(player: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for entry in sellable_inventory_entries(player):
        if entry["item_id"] == item_id:
            return entry
    return None


def handle_sell_quantity(storage: Any, player: dict[str, Any], entry: dict[str, Any], raw_quantity: str, inventory_index: int | None = None) -> MarketResult:
    sell_zone = _market_zone(_market_kind_from_context(player), "sell")
    quantity = _parse_positive_int(raw_quantity)
    if quantity is None or quantity > safe_int(entry.get("quantity"), 0):
        return MarketResult(
            f"Такое количество продать нельзя. Введите число от 1 до {entry.get('quantity', 0)}.",
            [[MARKET_BACK]],
            sell_zone,
        )

    remaining = quantity
    inventory = player.setdefault("inventory", [])
    if not isinstance(inventory, list):
        inventory = []
        player["inventory"] = inventory
    indexed_items = list(enumerate(inventory))
    if inventory_index is not None:
        indexed_items = [(index, item) for index, item in indexed_items if index == inventory_index]

    for index, item in indexed_items:
        if remaining <= 0:
            break
        if not isinstance(item, dict) or _item_id(item) != entry["item_id"] or _is_sell_protected(item):
            continue
        current = max(0, safe_int(item.get("amount"), 1))
        take = min(current, remaining)
        item["amount"] = current - take
        remaining -= take

    if remaining > 0:
        return MarketResult("Продажа не выполнена: предмет уже недоступен в нужном количестве.", [[MARKET_BACK]], sell_zone)

    remove_empty_stacks_and_recalculate(player)
    total = quantity * safe_int(entry.get("price"), 0)
    artifact_bonus = math.floor(total * _npc_sell_bonus_percent(player) / 100)
    total += artifact_bonus
    bonus = npc_transaction_bonus_amount(player, total)
    _set_money(player, _money(player) + total + bonus)
    list_result = open_sell_list(player)
    storage.update_player(player)
    bonus_text = f" Возврат золота: +{format_price(bonus)}." if bonus else ""
    return MarketResult(
        f"Продано: {entry['name']} ×{quantity}. Получено: {format_price(total)}.{bonus_text}\n\n{list_result.text}",
        list_result.buttons,
        list_result.zone_id,
    )


def _parse_positive_int(raw: str) -> int | None:
    value = str(raw or "").strip()
    if not value.isdigit():
        return None
    result = int(value)
    return result if result > 0 else None


def is_profile_market_sell_enabled(player: dict[str, Any]) -> bool:
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    mode = str(context.get("mode") or "")
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    sell_zones = {str(config["sell_zone"]) for config in MARKET_CONFIGS.values()}
    return zone in sell_zones and mode in {"sell_list", "sell_card", "sell_quantity"}


def is_item_sellable_from_profile(player: dict[str, Any], item_id: str) -> bool:
    if not is_profile_market_sell_enabled(player):
        return False
    return _entry_by_id(player, item_id) is not None


def sell_item_from_profile(storage: Any, player: dict[str, Any], item_id: str, quantity: int, inventory_index: int | None = None) -> MarketResult:
    sell_zone = _market_zone(_market_kind_from_context(player), "sell")
    if not is_profile_market_sell_enabled(player):
        return MarketResult("Продажа через профиль доступна только когда игрок находится на рынке в разделе продажи.", [], str(player.get("current_zone") or ""))
    if inventory_index is not None:
        inventory = player.get("inventory", [])
        if not isinstance(inventory, list) or inventory_index < 0 or inventory_index >= len(inventory):
            return MarketResult("Этот стак предмета уже недоступен для продажи.", [], sell_zone)
        raw_item = inventory[inventory_index]
        entry = sellable_inventory_stack_entry(raw_item, inventory_index) if isinstance(raw_item, dict) else None
        if not entry or entry["item_id"] != item_id:
            return MarketResult("Этот стак предмета нельзя продать на рынке.", [], sell_zone)
        return handle_sell_quantity(storage, player, entry, str(quantity), inventory_index=inventory_index)

    entry = _entry_by_id(player, item_id)
    if not entry:
        return MarketResult("Этот предмет сейчас нельзя продать на рынке.", [], sell_zone)
    return handle_sell_quantity(storage, player, entry, str(quantity))


def handle_market_action(storage: Any, player: dict[str, Any], action: str) -> MarketResult:
    action = str(action or "").strip()
    context = player.get("market_context") if isinstance(player.get("market_context"), dict) else {}
    mode = str(context.get("mode") or "")
    kind = str(context.get("market_kind") or MARKET_KIND_BY_ENTRY.get(action) or _market_kind_from_context(player))
    if kind not in MARKET_CONFIGS:
        kind = MARKET_KIND_NPC
    exit_labels = {str(config["exit"]) for config in MARKET_CONFIGS.values()}

    if action in exit_labels or action in {MARKET_EXIT_TO_TRADE_DISTRICT, LEGACY_MARKET_EXIT_TO_PAVILION}:
        result = leave_market(player)
        storage.update_player(player)
        return result

    if action == MARKET_BACK_TO_MAIN:
        result = open_market(player, kind)
        storage.update_player(player)
        return result

    if action in {MARKET_BUY_PAGE_NEXT, MARKET_BUY_PAGE_PREV}:
        delta = 1 if action == MARKET_BUY_PAGE_NEXT else -1
        result = open_buy_list(player, safe_int(context.get("page"), 0) + delta)
        storage.update_player(player)
        return result

    if action in {MARKET_SELL_PAGE_NEXT, MARKET_SELL_PAGE_PREV}:
        delta = 1 if action == MARKET_SELL_PAGE_NEXT else -1
        result = open_sell_list(player, safe_int(context.get("page"), 0) + delta)
        storage.update_player(player)
        return result

    if action == MARKET_BACK:
        if mode in {"buy_card", "buy_quantity"}:
            result = open_buy_list(player, safe_int(context.get("page"), 0))
        elif mode in {"sell_card", "sell_quantity"}:
            result = open_sell_list(player, safe_int(context.get("page"), 0))
        elif mode in {"buy_list", "sell_list"}:
            result = open_market(player, kind)
        elif mode == "main":
            result = leave_market(player)
        else:
            result = leave_market(player)
        storage.update_player(player)
        return result

    if action in MARKET_KIND_BY_ENTRY:
        result = open_market(player, MARKET_KIND_BY_ENTRY[action])
        storage.update_player(player)
        return result

    if action == MARKET_BUY:
        if mode == "buy_card":
            item = market_item_by_id(str(context.get("item_id") or ""), kind)
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
        item = market_item_by_id(str(context.get("item_id") or ""), kind)
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
        item = market_item_by_number(_parse_numbered_action(action, MARKET_BUY), kind)
        if not item:
            item = market_item_by_display_name(action, kind)
        if item:
            result = show_buy_card(player, item)
            storage.update_player(player)
            return result

    if mode == "sell_list" or is_market_context(player):
        entry = sell_entry_by_number(player, _parse_numbered_action(action, MARKET_SELL))
        if not entry:
            entry = sell_entry_by_label(player, action)
        if entry:
            result = show_sell_card(player, entry)
            storage.update_player(player)
            return result

    result = open_market(player, kind)
    storage.update_player(player)
    return result
