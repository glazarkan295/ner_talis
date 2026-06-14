"""External location mechanics for Ner-Talis.

This module converts the uploaded design document for city gates and the
starting location "Холмистые луга" into runnable game logic used by both
Telegram and VK adapters.
"""

from __future__ import annotations

import json
import math
import random
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from project_paths import resolve_project_path
from services.derived_stats_service import calculate_energy_stats, ensure_player_resources
from services.item_registry import build_inventory_item, get_item_definition_by_name, slugify_fallback_item_id
from services.inventory_service import add_inventory_item as add_inventory_stack, apply_generated_item_level_and_price, inventory_add_result_notice, remove_empty_stacks_and_recalculate
from services.active_skill_service import normalize_starter_only_skills
from services.pve_battle_service import BATTLE_ACTIONS, battle_buttons, create_location_battle, handle_battle_action
from services.race_bonus_service import extra_alchemy_ingredient_chance_percent, search_event_weights
from services.fishing_service import grant_waterside_reward
from services.small_plateau_service import (
    LOCATION_ID as SMALL_PLATEAU_ID,
    resolve_small_plateau_search,
    handle_cursed_coin_choice,
    roll_ancient_curse_trigger,
    cleanse_ancient_curse_at_hidden_place,
    leave_hidden_coin_place_with_curse,
)
from services.fine_service import (
    CITY_FINE_PAY_ACTION,
    FORTRESS_BACK,
    FORTRESS_HALL,
    MAINLAND_EXTERNAL,
    STAY_IN_FORTRESS,
    advance_fine_state,
    fine_card,
    movement_block_buttons,
    movement_block_text,
    pay_fine,
    should_block_movement_action,
)
from storage.event_claims import ensure_event_id


OUTSIDE_CITY = "Выход из города"
LEGACY_OUTSIDE_CITY = "Выйти к локациям"
RETURN_TO_GATES = "Вернуться к воротам"
RETURN_TO_SELDAR_GATES = "Вернуться к воротам Селдара"
RETURN_TO_CITY = "Вернуться в город"
HILLY_MEADOWS = "Холмистые луга"
FORTRESS_IN_GORGE = "Крепость в ущелье"
FORTRESS_COURTYARD = "Внутренний двор"
FORTRESS_ALLEYS = "Переулки"
FORTRESS_SEEKER_OUTPOST = "Застава Искателей"
FORTRESS_MANAGER = "Управляющий"
FORTRESS_COMMANDANT = "Комендант Крепости"
FORTRESS_RESOURCE_BUYER = "Скупщик ресурсов"
FORTRESS_COORDINATOR = "Координатор"
FORTRESS_ORDER_BOARD = "Доска заказов"
FORTRESS_QUESTS = "Квесты"
FORTRESS_ASSASSIN_GUILD = "Гильдия Убийц"
FORTRESS_CREATE_ORDER_MENU = "Выставить заказ"
FORTRESS_VIEW_ORDERS = "Посмотреть заказы"
FORTRESS_MY_ORDERS = "Мои заказы"
FORTRESS_TAKEN_ORDERS = "Взятые заказы"
FORTRESS_CREATE_ORDER = "Создать заказ"
FORTRESS_CANCEL_CREATE_ORDER = "Отменить создание заказа"
FORTRESS_NOTICE_BOARD = "Доска объявлений"
FORTRESS_GUILD_AGENT = "Агент Гильдии"
FORTRESS_HIRE = "Найм"
FORTRESS_ROAD_TO_CITY = "Вернуться на дорогу в город"
FORTRESS_EXIT_GATE = "Выйти за ворота"
SMALL_PLATEAU = "Малое плато"
COMMON_FOREST = "Обыкновенный лес"
START_SEARCH = "Начать поиск"
SET_CAMP = "Разбить лагерь"
COOK_FOOD = "Приготовить еду"
EAT_FOOD = "Съесть еду"
SHORT_COOK_FOOD = "Готовка"
SHORT_EAT_FOOD = "Еда"
BREAK_CAMP = "Свернуть лагерь"
BACK_TO_CAMP = "⬅️ В лагерь"
CHECK_TIMER = "Проверить таймер"
BACK = "Назад"
PROFILE_BUTTON = "Профиль"
COLLECT = "Собрать"
SKIP = "Пропустить"
INSPECT_AND_TAKE = "Осмотреть и забрать"
LOOK = "Посмотреть"
LEAVE = "Уйти"
COLLECT_TREE = "Собрать дерево"
COLLECT_MUSHROOMS = "Собрать грибы"
GATHER_WATER = "Набрать воду"
PUT_HAND_IN_BURROW = "Засунуть руку"
RETREAT = "Отступить"
APPROACH_ARCH = "Подойти к арке"
INSPECT_ARCH = "Осмотреть Арку"
RETURN_SMALL_PLATEAU = "Вернуться на Малое плато"
TAKE_CURSED_COINS = "Взять монеты"
PAY_100_SILVER = "Положить 100 серебряных"
LEAVE_WITH_CURSE = "Уйти с проклятьем"
EVENT_RESOLUTION_OWNER = f"{socket.gethostname()}:{__name__}"
def load_json_config(relative_path: str) -> dict[str, Any]:
    path = resolve_project_path(relative_path)
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def load_hilly_meadows_config() -> dict[str, Any]:
    return load_json_config("data/hilly_meadows.json")


def load_ordinary_forest_config() -> dict[str, Any]:
    return load_json_config("data/ordinary_forest.json")


def load_small_plateau_config() -> dict[str, Any]:
    return load_json_config("data/small_plateau_location.json")


def load_fortress_config() -> dict[str, Any]:
    return load_json_config("data/fortress_in_gorge.json")


HILLY_MEADOWS_CONFIG = load_hilly_meadows_config()
ORDINARY_FOREST_CONFIG = load_ordinary_forest_config()
SMALL_PLATEAU_CONFIG = load_small_plateau_config()
FORTRESS_CONFIG = load_fortress_config()
EXPLORATION_LOCATION_IDS = {"hilly_meadows", "ordinary_forest", "small_plateau"}
LOCATION_CONFIGS = {"hilly_meadows": HILLY_MEADOWS_CONFIG, "ordinary_forest": ORDINARY_FOREST_CONFIG, "small_plateau": SMALL_PLATEAU_CONFIG}
SEARCH_ENERGY_COST = int(HILLY_MEADOWS_CONFIG.get("base_search_energy_cost", 2) or 2)
BASE_SEARCH_TIME_SECONDS = int(HILLY_MEADOWS_CONFIG.get("base_search_time_seconds", 30) or 30)
MAX_SEARCH_TIME_SECONDS = int(HILLY_MEADOWS_CONFIG.get("max_search_time_seconds", 600) or 600)
BASE_SEARCH_EVENT_WEIGHTS = [
    (key, int(value))
    for key, value in (HILLY_MEADOWS_CONFIG.get("events") or {
        "alchemy_ingredient": 25,
        "stone_or_ore": 17,
        "berries": 20,
        "trap": 10,
        "glint": 8,
        "battle": 20,
    }).items()
]

CAMP_DISHES = HILLY_MEADOWS_CONFIG.get("camp_recipes") or {
    "Сушёное мясо": {"restore_energy": 7, "ingredients": {"Сырое мясо": 1}},
    "Травяной чай": {"restore_energy": 20, "ingredients": {"Чистая вода": 1, "Любая съедобная ягода": 1, "Луговая мята": 1}},
    "Лепёшка с мясом": {"restore_energy": 35, "ingredients": {"Чистая вода": 1, "Сырое мясо": 1, "Грубая мука": 1}},
    "Сытная похлёбка": {"restore_energy": 40, "ingredients": {"Чистая вода": 1, "Луговой корень": 1, "Съедобный лесной гриб": 1, "Сырое мясо": 1}},
}

EDIBLE_BERRIES = {"Сладкая луговая ягода", "Терпкая синяя ягода", "Любая съедобная ягода"}
INGREDIENT_ALIASES = {
    "Съедобный гриб": ["Съедобный гриб", "Съедобный лесной гриб"],
    "Съедобный лесной гриб": ["Съедобный лесной гриб", "Съедобный гриб"],
}

LOCATION_RESOURCE_NAMES = {
    "Луговая мята",
    "Серебристая ромашка",
    "Жёлтый клевер",
    "Горная полынь",
    "Луговой корень",
    "Обычный камень",
    "Кусок медной руды",
    "Кусок железной руды",
    "Сладкая луговая ягода",
    "Терпкая синяя ягода",
    "Съедобный корень",
    "Съедобный гриб",
    "Чистая вода",
    "Мутная вода",
    "Сухое бревно",
    "Съедобный лесной гриб",
    "Горький серый гриб",
    "Бледная поганка",
    "Куски ткани",
    "Водоросли",
}

CAMP_FOOD_CATEGORY = "Еда"
LOCATION_RESOURCE_CATEGORY = "Ресурсы"


def _location_resource_tables(location_id: str) -> dict[str, Any]:
    config = LOCATION_CONFIGS.get(location_id) or HILLY_MEADOWS_CONFIG
    tables = config.get("resource_find_tables") if isinstance(config, dict) else None
    return tables if isinstance(tables, dict) else {}


def _choose_resource_entry(table: Any, rng: random.Random, fallback: list[dict[str, Any]]) -> dict[str, Any]:
    raw_table = table if isinstance(table, list) and table else fallback
    weighted: list[tuple[str, int]] = []
    entries: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(raw_table):
        if not isinstance(entry, dict):
            continue
        key = str(index)
        weight = int(entry.get("weight", 1) or 1)
        if weight <= 0:
            continue
        entries[key] = entry
        weighted.append((key, weight))
    if not weighted:
        return dict(fallback[0])
    return dict(entries[weighted_choice(weighted, rng)])


def _roll_resource_entry(location_id: str, table_name: str, rng: random.Random, fallback: list[dict[str, Any]]) -> dict[str, Any]:
    tables = _location_resource_tables(location_id)
    raw_table = tables.get(table_name)
    return _choose_resource_entry(raw_table, rng, fallback)


def _entry_amount(entry: dict[str, Any], rng: random.Random) -> int:
    amount_min = int(entry.get("amount_min", entry.get("amount", 1)) or 0)
    amount_max = int(entry.get("amount_max", amount_min) or amount_min)
    if amount_max < amount_min:
        amount_max = amount_min
    return rng.randint(amount_min, amount_max)


def _entry_max_stack(entry: dict[str, Any], fallback: int = 20) -> int:
    return max(1, int(entry.get("max_stack", fallback) or fallback))



def apply_location_item_category(item: dict[str, Any], name: str) -> None:
    if name in CAMP_DISHES:
        item["category"] = CAMP_FOOD_CATEGORY
        item["type"] = "Блюдо"
        return
    if name in LOCATION_RESOURCE_NAMES:
        item["category"] = LOCATION_RESOURCE_CATEGORY
        item.setdefault("type", "Ресурс")
        item.setdefault("source", "Локация")


EXTERNAL_LOCATION_BUTTONS = frozenset(
    {
        OUTSIDE_CITY,
        LEGACY_OUTSIDE_CITY,
        RETURN_TO_GATES,
        RETURN_TO_SELDAR_GATES,
        RETURN_TO_CITY,
        HILLY_MEADOWS,
        FORTRESS_IN_GORGE,
        FORTRESS_HALL,
        CITY_FINE_PAY_ACTION,
        FORTRESS_BACK,
        STAY_IN_FORTRESS,
        MAINLAND_EXTERNAL,
        SMALL_PLATEAU,
        COMMON_FOREST,
        START_SEARCH,
        SET_CAMP,
        COOK_FOOD,
        EAT_FOOD,
        SHORT_COOK_FOOD,
        SHORT_EAT_FOOD,
        BREAK_CAMP,
        BACK_TO_CAMP,
        CHECK_TIMER,
        BACK,
        COLLECT,
        SKIP,
        INSPECT_AND_TAKE,
        LOOK,
        LEAVE,
        COLLECT_TREE,
        COLLECT_MUSHROOMS,
        GATHER_WATER,
        PUT_HAND_IN_BURROW,
        RETREAT,
        APPROACH_ARCH,
        INSPECT_ARCH,
        RETURN_SMALL_PLATEAU,
        TAKE_CURSED_COINS,
        PAY_100_SILVER,
        LEAVE_WITH_CURSE,
        *BATTLE_ACTIONS,
        FORTRESS_COURTYARD,
        FORTRESS_HALL,
        FORTRESS_MANAGER,
        FORTRESS_COMMANDANT,
        FORTRESS_ALLEYS,
        FORTRESS_RESOURCE_BUYER,
        FORTRESS_COORDINATOR,
        FORTRESS_ORDER_BOARD,
        FORTRESS_QUESTS,
        FORTRESS_ASSASSIN_GUILD,
        FORTRESS_CREATE_ORDER_MENU,
        FORTRESS_VIEW_ORDERS,
        FORTRESS_MY_ORDERS,
        FORTRESS_TAKEN_ORDERS,
        FORTRESS_CREATE_ORDER,
        FORTRESS_CANCEL_CREATE_ORDER,
        FORTRESS_SEEKER_OUTPOST,
        FORTRESS_NOTICE_BOARD,
        FORTRESS_GUILD_AGENT,
        FORTRESS_HIRE,
        FORTRESS_ROAD_TO_CITY,
        FORTRESS_EXIT_GATE,
        *CAMP_DISHES.keys(),
        *(f"Приготовить: {dish_name} ×1" for dish_name in CAMP_DISHES),
        *(f"Приготовить: {dish_name} ×10" for dish_name in CAMP_DISHES),
        *(f"Съесть: {dish_name}" for dish_name in CAMP_DISHES),
        *(f"Съесть: {dish_name} ×1" for dish_name in CAMP_DISHES),
        *(f"Съесть: {dish_name} ×10" for dish_name in CAMP_DISHES),
        *(f"Готовить {index} ×1" for index, _dish_name in enumerate(CAMP_DISHES, start=1)),
        *(f"Готовить {index} ×10" for index, _dish_name in enumerate(CAMP_DISHES, start=1)),
        *(f"Есть {index} ×1" for index, _dish_name in enumerate(CAMP_DISHES, start=1)),
        *(f"Есть {index} ×10" for index, _dish_name in enumerate(CAMP_DISHES, start=1)),
    }
)


@dataclass(frozen=True)
class LocationResponse:
    text: str
    buttons: list[list[str]]
    zone_id: str
    scheduled_timer: dict[str, Any] | None = None


def outside_city_buttons() -> list[list[str]]:
    return [
        [SMALL_PLATEAU, COMMON_FOREST],
        [HILLY_MEADOWS],
        [FORTRESS_IN_GORGE],
        [RETURN_TO_GATES],
    ]


def hilly_meadows_buttons() -> list[list[str]]:
    return [
        [START_SEARCH],
        [SET_CAMP],
        [RETURN_TO_CITY],
    ]


def ordinary_forest_buttons() -> list[list[str]]:
    return [
        [START_SEARCH],
        [SET_CAMP],
        [RETURN_TO_CITY],
    ]


def small_plateau_buttons() -> list[list[str]]:
    return [
        [START_SEARCH],
        [SET_CAMP],
        [APPROACH_ARCH],
        [RETURN_TO_CITY],
    ]


def small_plateau_arch_buttons() -> list[list[str]]:
    return [
        [RETURN_SMALL_PLATEAU],
        [INSPECT_ARCH],
    ]


def small_plateau_hidden_coin_buttons() -> list[list[str]]:
    return [
        [LEAVE_WITH_CURSE],
        [PAY_100_SILVER],
    ]


def current_location_id(player: dict[str, Any] | None, default: str = "hilly_meadows") -> str:
    location_id = str((player or {}).get("current_location") or default)
    return location_id if location_id in EXPLORATION_LOCATION_IDS else default


def location_buttons(location_id: str | None) -> list[list[str]]:
    if location_id == "ordinary_forest":
        return ordinary_forest_buttons()
    if location_id == "small_plateau":
        return small_plateau_buttons()
    return hilly_meadows_buttons()


def location_name(location_id: str | None) -> str:
    if location_id == "ordinary_forest":
        return "Обыкновенный лес"
    if location_id == "small_plateau":
        return "Малое плато"
    return "Холмистые луга"


def location_text(location_id: str | None) -> str:
    if location_id == "ordinary_forest":
        return ORDINARY_FOREST_CONFIG.get("entry_text") or ORDINARY_FOREST_TEXT
    if location_id == "small_plateau":
        return SMALL_PLATEAU_CONFIG.get("entrance_text") or SMALL_PLATEAU_TEXT
    return HILLY_MEADOWS_TEXT


def camp_text(location_id: str | None) -> str:
    if location_id == "ordinary_forest":
        return ORDINARY_FOREST_CONFIG.get("camp_text") or FOREST_CAMP_TEXT
    if location_id == "small_plateau":
        camp = SMALL_PLATEAU_CONFIG.get("camp") if isinstance(SMALL_PLATEAU_CONFIG, dict) else {}
        return (camp or {}).get("text") or SMALL_PLATEAU_CAMP_TEXT
    return CAMP_TEXT


def search_timer_buttons() -> list[list[str]]:
    return [
        [CHECK_TIMER],
        [BACK],
    ]


def cancel_active_timer(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    timer = player.get("active_timer")
    if not isinstance(timer, dict):
        return current_location_back_response(player)

    timer_type = str(timer.get("type") or "")
    location_id = current_location_id(player)
    player["active_timer"] = None
    player["current_zone"] = location_id
    player["location_id"] = location_id
    player.pop("pending_timer_delivery", None)
    storage.update_player(player)

    if timer_type == "search":
        return LocationResponse(
            "🔎 Вы прекратили поиск. Таймер сброшен, событие не найдено.",
            location_buttons(location_id),
            location_id,
        )
    if timer_type == "camp_rest":
        return LocationResponse(
            "⛺ Вы прервали отдых. Таймер сброшен, показатели не восстановлены.",
            camp_buttons(),
            f"{location_id}_camp",
        )
    return LocationResponse("⏳ Таймер сброшен.", location_buttons(location_id), str(player.get("current_zone") or location_id))


def current_location_back_response(player: dict[str, Any]) -> LocationResponse:
    current_location = str(player.get("current_location") or "")
    if current_location in EXPLORATION_LOCATION_IDS:
        timer = player.get("active_timer")
        extra = ""
        if isinstance(timer, dict) and timer.get("type") == "search":
            remaining = timer_remaining_seconds(timer)
            extra = f"\n\n⏳ Поиск ещё идёт. Осталось: {format_duration(remaining)}. Когда таймер закончится, придёт сообщение с найденным событием."
        return LocationResponse(location_text(current_location) + extra, location_buttons(current_location), current_location)
    if current_location == "fortress_in_gorge":
        return LocationResponse(FORTRESS_TEXT, fortress_buttons(), "fortress_in_gorge_courtyard")
    return LocationResponse(OUTSIDE_CITY_TEXT, outside_city_buttons(), "outside_city_crossroads")


def event_choice_buttons(event_type: str) -> list[list[str]]:
    if event_type == "alchemy_ingredient":
        return [[COLLECT], [SKIP]]
    if event_type == "stone_or_ore":
        return [[INSPECT_AND_TAKE], [SKIP]]
    if event_type == "waterside_loot":
        return [[INSPECT_AND_TAKE], [SKIP]]
    if event_type == "berries":
        return [[COLLECT], [SKIP]]
    if event_type == "dry_tree":
        return [[COLLECT_TREE], [SKIP]]
    if event_type == "mushrooms":
        return [[COLLECT_MUSHROOMS], [SKIP]]
    if event_type == "river":
        return [[GATHER_WATER], [LEAVE]]
    if event_type == "small_burrow":
        return [[PUT_HAND_IN_BURROW], [LEAVE]]
    if event_type == "glint":
        return [[LOOK], [LEAVE]]
    if event_type == "small_plateau_cursed_coins":
        return [[TAKE_CURSED_COINS], [LEAVE]]
    if event_type in {"battle", "battle_preview"}:
        return battle_buttons()
    return hilly_meadows_buttons()


def camp_buttons() -> list[list[str]]:
    return [
        [PROFILE_BUTTON],
        [SHORT_COOK_FOOD, SHORT_EAT_FOOD],
        [BREAK_CAMP],
    ]


def current_external_buttons(player: dict[str, Any]) -> list[list[str]]:
    """Return buttons for the player's real external-location state.

    Unknown text and unrelated stale city buttons must not push a player to the
    outside crossroads or into a city screen. This helper keeps the visible
    keyboard tied to the exact external state: location, camp, fortress, active
    event or crossroads.
    """
    if player.get("in_battle"):
        return battle_buttons(player)

    active_event = player.get("active_event")
    if isinstance(active_event, dict):
        event_type = str(active_event.get("type") or "")
        return event_choice_buttons(event_type)

    zone = str(player.get("current_zone") or player.get("location_id") or "")
    current_location = str(player.get("current_location") or "")

    if zone.endswith("_camp"):
        return camp_buttons()
    if zone == "small_plateau_arch":
        return small_plateau_arch_buttons()
    if zone == "small_plateau_hidden_coin_place":
        return small_plateau_hidden_coin_buttons()
    if zone == "outside_city_crossroads":
        return outside_city_buttons()
    if current_location == "fortress_in_gorge" or zone.startswith("fortress_in_gorge"):
        return current_fortress_buttons(player)
    if current_location in EXPLORATION_LOCATION_IDS:
        return location_buttons(current_location)
    if zone in EXPLORATION_LOCATION_IDS:
        return location_buttons(zone)
    return outside_city_buttons()


def camp_dish_name_by_index(index: int) -> str | None:
    dishes = list(CAMP_DISHES.keys())
    if 1 <= index <= len(dishes):
        return dishes[index - 1]
    return None


def cook_buttons(player: dict[str, Any] | None = None) -> list[list[str]]:
    rows: list[list[str]] = []
    for index, dish_name in enumerate(CAMP_DISHES, start=1):
        row = [f"Готовить {index} ×1"]
        if player is not None and available_craft_count(player, dish_name) >= 10:
            row.append(f"Готовить {index} ×10")
        rows.append(row)
    rows.append([BACK_TO_CAMP])
    return rows


def eat_buttons(player: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for index, name in enumerate(CAMP_DISHES, start=1):
        count = get_item_count(player, name)
        if count <= 0:
            continue
        if count >= 10:
            rows.append([f"Есть {index} ×1", f"Есть {index} ×10"])
        else:
            rows.append([f"Есть {index} ×1"])
    rows.append([BACK_TO_CAMP])
    return rows


def fortress_buttons() -> list[list[str]]:
    return [
        [FORTRESS_HALL, FORTRESS_ALLEYS],
        [FORTRESS_SEEKER_OUTPOST],
        [FORTRESS_ROAD_TO_CITY, FORTRESS_EXIT_GATE],
    ]


def fortress_town_hall_buttons() -> list[list[str]]:
    return [
        [FORTRESS_MANAGER, FORTRESS_COMMANDANT],
        [FORTRESS_COURTYARD],
    ]


def fortress_alleys_buttons() -> list[list[str]]:
    return [
        [FORTRESS_RESOURCE_BUYER, FORTRESS_COORDINATOR],
        [FORTRESS_COURTYARD],
    ]


def fortress_coordinator_buttons(player: dict[str, Any] | None = None) -> list[list[str]]:
    rows = [[FORTRESS_ORDER_BOARD, FORTRESS_QUESTS]]
    player = player or {}
    if player.get("assassin_guild_unlocked") or player.get("assassin_mark"):
        rows.append([FORTRESS_ASSASSIN_GUILD])
    rows.append([FORTRESS_ALLEYS, FORTRESS_COURTYARD])
    return rows


def fortress_order_board_buttons() -> list[list[str]]:
    return [
        [FORTRESS_CREATE_ORDER_MENU, FORTRESS_VIEW_ORDERS],
        [FORTRESS_MY_ORDERS, FORTRESS_TAKEN_ORDERS],
        [FORTRESS_COURTYARD],
    ]


def fortress_create_order_buttons() -> list[list[str]]:
    return [
        [FORTRESS_CREATE_ORDER],
        [FORTRESS_ORDER_BOARD, FORTRESS_COURTYARD],
    ]


def fortress_seeker_outpost_buttons() -> list[list[str]]:
    return [
        [FORTRESS_NOTICE_BOARD, FORTRESS_GUILD_AGENT],
        [FORTRESS_HIRE],
        [FORTRESS_COURTYARD],
    ]


def fortress_mainland_buttons() -> list[list[str]]:
    return [
        [FORTRESS_COURTYARD],
        [RETURN_TO_SELDAR_GATES],
    ]


def current_fortress_buttons(player: dict[str, Any]) -> list[list[str]]:
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    if zone == "fortress_in_gorge_town_hall":
        return fortress_town_hall_buttons()
    if zone == "fortress_in_gorge_alleys":
        return fortress_alleys_buttons()
    if zone == "fortress_in_gorge_coordinator":
        return fortress_coordinator_buttons(player)
    if zone == "fortress_in_gorge_order_board":
        return fortress_order_board_buttons()
    if zone in {"fortress_in_gorge_create_order_menu", "fortress_in_gorge_order_form_pending"}:
        return fortress_create_order_buttons()
    if zone == "fortress_in_gorge_seeker_outpost":
        return fortress_seeker_outpost_buttons()
    if zone == "fortress_in_gorge_mainland_gate":
        return fortress_mainland_buttons()
    if zone.startswith("fortress_in_gorge_") and zone != "fortress_in_gorge_courtyard":
        return [[FORTRESS_COURTYARD]]
    return fortress_buttons()


OUTSIDE_CITY_TEXT = """🗺 Выход из города

Покинув безопасные стены Селдара, вы оказываетесь на развилке. Дороги ведут к ближайшим землям, где можно искать травы, руду, дичь и случайные находки.

Доступные направления:
• Малое плато
• Обыкновенный лес
• Холмистые луга
• Крепость в ущелье"""

SMALL_PLATEAU_TEXT = """🏛 Малое плато

Локация занимает примерно 28% полуострова. С запада, юга и юго-востока её окружает океан. Среди сотен старых руин, ближе к южному краю, на площади стоит очень древняя арка со сколами, трещинами, отломанными кусками и полустёртыми рунами. Рядом видны остатки постамента.

Действия:
• Начать поиск — 2 энергии.
• При полной энергии поиск длится 30 сек.
• При низкой энергии поиск замедляется максимум до 5 минут.
• При 0 энергии поиск длится 10 минут и не тратит энергию.
• Можно разбить лагерь или подойти к арке."""

SMALL_PLATEAU_CAMP_TEXT = """⛺ Лагерь на Малом плато

Вы находите относительно ровное место среди древних руин и разводите небольшой костёр. В воздухе витает запах соли и пыли, а прохладный ветерок доносит едва уловимые отголоски давних времён."""

HILLY_MEADOWS_TEXT = """🌿 Холмистые луга

Перед вами раскинулись Холмистые луга. Невысокие зелёные холмы тянутся до самого горизонта, трава колышется под ветром, а между склонами прячутся цветы, ягоды, звериные норы и случайные следы чужих путников.

Поиск в лугах тратит 2 энергии и запускает случайное событие. Базовое время поиска — 30 сек. При низкой энергии время растёт, но пока энергия выше 0, оно не превышает 5 минут. При 0 энергии поиск занимает 10 минут.

Возможные события: травы, ягоды, камень или руда, ловушка, блик в траве или бой."""

ORDINARY_FOREST_TEXT = """🌲 Обыкновенный лес

Вы входите в Обыкновенный лес. Между стволами тянутся узкие звериные тропы, под ногами хрустит сухая листва, а в глубине слышатся шорохи, треск веток и далёкое журчание воды.

📋 Старая дощечка у тропы:
«Кто в лес впервые идёт — не геройствуй. Тут уже не луга: волки по следу ходят, кабаны из кустов вылетают, а под листьями и старый капкан попасться может. Сначала окрепни, снаряжение поправь, еды возьми. Обычно сюда соваться начинают, когда хоть до десятка доросли.»

Поиск в лесу тратит 2 энергии и запускает случайное событие. Базовое время поиска — 30 сек. При низкой энергии время растёт, но пока энергия выше 0, оно не превышает 5 минут. При 0 энергии поиск занимает 10 минут и не тратит энергию.

Возможные события: сухое дерево, грибы, речушка, небольшая нора, лесная ловушка или бой."""

FORTRESS_TEXT = """🏰 Крепость в ущелье

Крепость стоит на дороге между полуостровом Селдара и внутренними землями материка. Со стороны материка стены укреплены особенно серьёзно: бойницы, тяжёлые ворота, сторожевые площадки и следы старых осад.

Это локация городского типа: здесь нет обычного поиска как на стартовых землях. Внутренний двор ведёт ко всем местам крепости.

Доступно:
• Крепостная ратуша — Управляющий и Комендант Крепости;
• Переулки — Скупщик ресурсов и Координатор;
• Застава Искателей — Доска объявлений, Агент Гильдии и найм;
• дорога обратно к городу и стартовым локациям;
• выход за ворота к будущим внешним локациям материка."""
FORTRESS_TOWN_HALL_TEXT = """🏛 Крепостная ратуша

В каменном зале прохладно и строго. Здесь ведут книги взысканий, принимают перенаправленные городские награды и хранят распоряжения крепостной администрации.

Доступно:
• Управляющий — оплата долгов и будущая выдача перенаправленных наград;
• Комендант Крепости — будущие награды за защиту от волн монстров и особые квесты."""

FORTRESS_ALLEYS_TEXT = """🌘 Переулки крепости

Между складами, задними воротами и лавками ходят люди, которые не любят громких вывесок. Здесь можно найти скупщика ресурсов и Координатора.

Доступно:
• Скупщик ресурсов — будет скупать ресурсы на 30% ниже базовой цены;
• Координатор — доска заказов на убийства игроков и будущие особые квесты."""

FORTRESS_SEEKER_OUTPOST_TEXT = """🛡 Застава Искателей

Здесь собираются те, кто уходит дальше материка: разведчики, охотники, наёмники и искатели рейдов.

Доступно:
• Доска объявлений — будущие заказы на добычу ресурсов;
• Агент Гильдии — будущие рейды на мировых боссов, подземелья и походы;
• Найм — будущие наёмники для сражений, добычи и особых задач."""

FORTRESS_COORDINATOR_TEXT = """🗡 Координатор

Координатор сидит в тени и ведёт записи без лишних вопросов.

Доступно:
• Доска заказов — выставить, посмотреть, проверить свои и взятые заказы;
• Квесты — будущие особые задания с ограничением по времени;
• Гильдия Убийц — скрытый путь, который будет доступен не всем."""

FORTRESS_ORDER_BOARD_TEXT = """📋 Доска заказов

На доске висят заказы на убийство игроков. Полный runtime заказов будет подключён отдельным шагом.

Доступно:
• Выставить заказ;
• Посмотреть заказы;
• Мои заказы;
• Взятые заказы."""

FORTRESS_CREATE_ORDER_TEXT = """📝 Выставить заказ

Для создания заказа будет использоваться анкета:

Ник игрока: игровой ник цели
Сколько раз убить игрока: число
Цена за 1 убийство игрока: сумма в медных монетах
Сколько игроков могут взять этот заказ: число
Сколько действует заказ: часы
Анонимность заказчика: да/нет

Стоимость выставления заказа:
(цена за 1 убийство × сколько раз убить) + (стоимость часа × срок действия).

Обычная стоимость часа — 50 медных. При анонимности — 200 медных за час.

Создание заказа, проверка анкеты и списание монет будут подключены следующим runtime-шагом."""

FORTRESS_RESOURCE_BUYER_TEXT = """⚖️ Скупщик ресурсов

Скупщик осматривает мешки, ящики и связки материалов.

— Ресурсы беру быстро, без лишних вопросов. Но дешевле рынка.

Будущая механика: скупка ресурсов у игроков на 30% ниже базовой цены."""

FORTRESS_COMMANDANT_TEXT = """⚔️ Комендант Крепости

Комендант изучает карту укреплений и отчёты дозорных.

Позже здесь появятся:
• награды за вклад в защиту от волн монстров;
• особые квесты крепости."""

FORTRESS_NOTICE_BOARD_TEXT = """📜 Доска объявлений Заставы Искателей

Позже игроки смогут выставлять здесь заказы на добычу определённых ресурсов, а другие игроки смогут принимать эти заказы."""

FORTRESS_GUILD_AGENT_TEXT = """🧭 Агент Гильдии

Агент Гильдии будет собирать рейды на мировых боссов, подземелья и дальние походы. Сейчас этот раздел подготовлен как заготовка."""

FORTRESS_HIRE_TEXT = """🤝 Найм

Позже здесь можно будет нанимать помощников для совместных сражений, добычи ресурсов и выполнения особых задач."""

FORTRESS_MAINLAND_TEXT = """🚧 Ворота на материк

За внешними воротами начинаются внутренние земли материка. Полный список материковых локаций будет подключён позже.

Пока это безопасная заглушка маршрута: вы можете вернуться во Внутренний двор крепости или к дороге на Селдар."""


FOREST_CAMP_TEXT = """⛺ Лагерь в Обыкновенном лесу

Вы находите сухое место между деревьями и разводите небольшой костёр. Вокруг слышны шорохи леса, поэтому долго расслабляться не стоит.

В лагере можно приготовить еду, съесть походное блюдо или свернуть лагерь.

Отдых в лагере восстанавливает HP, ману и очки духа до максимума. Энергия напрямую отдыхом не восстанавливается — для неё используются блюда и напитки."""

CAMP_TEXT = """⛺ Лагерь в Холмистых лугах

Вы находите ровное место между холмами и разбиваете небольшой лагерь. Ветер здесь слабее, трава мягче, а вокруг достаточно сухих веток для маленького костра.

В лагере можно приготовить еду, съесть походное блюдо или свернуть лагерь.

Отдых в лагере восстанавливает HP, ману и очки духа до максимума. Энергия напрямую отдыхом не восстанавливается — для неё используются блюда и напитки."""


PLACEHOLDER_LOCATION_TEXT = """🚧 Эта внешняя локация пока не открыта.

Сейчас в код полностью подключены «Холмистые луга» и безопасная «Крепость в ущелье». Остальные направления оставлены как заготовки для следующих локаций."""


def ensure_external_fields(player: dict[str, Any]) -> bool:
    changed = False
    defaults: dict[str, Any] = {
        "current_location": None,
        "active_event": None,
        "active_timer": None,
        "energy": 100,
        "current_energy": None,
        "max_energy": 100,
        "bonus_max_energy": 0,
        "money": 0,
        "money_copper": None,
        "in_battle": False,
        "is_dead": False,
        "inventory": [],
    }
    for key, value in defaults.items():
        if key not in player:
            player[key] = value
            changed = True

    if player.get("current_energy") is None:
        player["current_energy"] = int(player.get("energy", 100) or 0)
        changed = True
    if player.get("money_copper") is None:
        player["money_copper"] = int(player.get("money", 0) or 0)
        changed = True

    sync_energy_fields(player)
    sync_money_fields(player)

    before_resources = (player.get("max_hp"), player.get("max_spirit"), player.get("max_mana"), player.get("hp"), player.get("spirit"), player.get("mana"))
    ensure_player_resources(player)
    after_resources = (player.get("max_hp"), player.get("max_spirit"), player.get("max_mana"), player.get("hp"), player.get("spirit"), player.get("mana"))
    if after_resources != before_resources:
        changed = True

    return changed


def sync_energy_fields(player: dict[str, Any]) -> None:
    max_energy = max(1, int(player.get("max_energy", 100) or 100))
    energy = int(player.get("current_energy", player.get("energy", max_energy)) or 0)
    energy = min(max_energy, max(0, energy))
    player["max_energy"] = max_energy
    player["energy"] = energy
    player["current_energy"] = energy


def sync_money_fields(player: dict[str, Any]) -> None:
    money = int(player.get("money_copper", player.get("money", 0)) or 0)
    money = max(0, money)
    player["money"] = money
    player["money_copper"] = money


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if sec or not parts:
        parts.append(f"{sec} сек")
    return " ".join(parts)


def now_ts() -> float:
    return time.time()


def new_timer_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def timer_remaining_seconds(timer: dict[str, Any] | None) -> int:
    if not isinstance(timer, dict):
        return 0
    ends_at = float(timer.get("ends_at") or 0)
    return max(0, math.ceil(ends_at - now_ts()))


def clear_energy_warning_if_recovered(player: dict[str, Any]) -> None:
    energy = int(player.get("energy", 0) or 0)
    if energy > 50:
        player.pop("energy_warning_50_sent", None)
    if energy > 10:
        player.pop("energy_warning_10_sent", None)


def collect_energy_warning_messages(player: dict[str, Any]) -> list[str]:
    """Returns threshold messages once when energy falls to 50 or 10."""
    energy = int(player.get("energy", 0) or 0)
    messages: list[str] = []
    if energy <= 50 and not player.get("energy_warning_50_sent"):
        player["energy_warning_50_sent"] = True
        messages.append("⚠️ Энергия опустилась до 50 единиц или ниже. Лучше съешьте еду или вернитесь в город.")
    if energy <= 10 and not player.get("energy_warning_10_sent"):
        player["energy_warning_10_sent"] = True
        messages.append("🚨 Энергия почти закончилась: 10 единиц или меньше. Дальнейшие поиски могут стать недоступны.")
    return messages


def hp_pair(player: dict[str, Any]) -> tuple[int, int]:
    max_hp = int(player.get("max_hp") or 100)
    hp = int(player.get("hp") or max_hp)
    return max(0, hp), max(1, max_hp)


def ingredient_count(player: dict[str, Any], name: str) -> int:
    if name == "Любая съедобная ягода":
        return sum(get_item_count(player, berry) for berry in EDIBLE_BERRIES)
    aliases = INGREDIENT_ALIASES.get(name)
    if aliases:
        return sum(get_item_count(player, alias) for alias in aliases)
    return get_item_count(player, name)


def available_craft_count(player: dict[str, Any], dish_name: str) -> int:
    dish = CAMP_DISHES[dish_name]
    counts: list[int] = []
    for ingredient, amount in dish["ingredients"].items():
        available = ingredient_count(player, ingredient)
        counts.append(available // max(1, amount))
    return min(counts) if counts else 0


def build_timer_schedule(player: dict[str, Any], timer: dict[str, Any]) -> dict[str, Any]:
    return {
        "timer_id": timer.get("id"),
        "game_id": player.get("game_id") or player.get("id"),
        "seconds": int(timer.get("seconds") or timer_remaining_seconds(timer)),
        "type": timer.get("type"),
    }


def weighted_choice(weighted_items: Iterable[tuple[str, int]], rng: random.Random) -> str:
    items = list(weighted_items)
    total = sum(weight for _, weight in items)
    roll = rng.uniform(0, total)
    upto = 0.0
    for item, weight in items:
        upto += weight
        if roll <= upto:
            return item
    return items[-1][0]


def calculate_scaled_seconds(current_energy: int, max_energy: int, base: int, maximum: int) -> int:
    """Scale action time by current energy.

    Rules for exploration timers:
    - full energy keeps the base time;
    - if energy is above 0, low-energy slowdown is capped at 5 minutes;
    - exactly 0 energy gives the full 10 minute timer.

    ``maximum`` is kept as an argument for older calls and tests; with the
    standard 600 second maximum this means 300 seconds for any positive energy
    and 600 seconds only at zero energy.
    """

    max_energy = max(1, max_energy)
    current_energy = max(0, current_energy)
    if current_energy <= 0:
        return min(maximum, max(base, maximum))

    positive_energy_maximum = min(maximum, 300)
    ratio = min(1.0, max(0.0, current_energy / max_energy))
    scaled = math.ceil(base + (positive_energy_maximum - base) * ((1 - ratio) ** 1.35))
    return min(positive_energy_maximum, max(base, scaled))


def add_item(player: dict[str, Any], name: str, amount: int, *, item_id: str | None = None, max_stack: int = 999, source: str = "Холмистые луга"):
    if amount <= 0:
        return add_inventory_stack(player, name, 0)

    inventory_item = build_inventory_item(name, amount, item_id=item_id, max_stack=max_stack)
    apply_generated_item_level_and_price(player, inventory_item, "found")
    if not inventory_item.get("level"):
        apply_location_item_category(inventory_item, name)
    inventory_item.setdefault("source", source)
    inventory_item.setdefault("actions", [])
    return add_inventory_stack(
        player,
        inventory_item,
        amount,
        item_id=str(inventory_item.get("id") or inventory_item.get("item_id") or slugify_item_name(name)),
        max_stack=int(inventory_item.get("max_stack", max_stack) or max_stack),
        default_source=source,
    )


def remove_item(player: dict[str, Any], name: str, amount: int) -> bool:
    if amount <= 0:
        return True
    count = get_item_count(player, name)
    if count < amount:
        return False

    inventory = player.setdefault("inventory", [])
    remaining = amount
    for item in list(inventory):
        if item.get("name") != name:
            continue
        item_amount = int(item.get("amount", 1) or 1)
        taken = min(item_amount, remaining)
        item["amount"] = item_amount - taken
        remaining -= taken
        if item["amount"] <= 0:
            inventory.remove(item)
        if remaining <= 0:
            remove_empty_stacks_and_recalculate(player)
            return True
    remove_empty_stacks_and_recalculate(player)
    return True


def get_item_count(player: dict[str, Any], name: str) -> int:
    return sum(int(item.get("amount", 1) or 1) for item in player.get("inventory", []) if item.get("name") == name)


def has_ingredient(player: dict[str, Any], name: str, amount: int) -> bool:
    return ingredient_count(player, name) >= amount


def consume_ingredient(player: dict[str, Any], name: str, amount: int) -> bool:
    if name != "Любая съедобная ягода":
        aliases = INGREDIENT_ALIASES.get(name)
        if not aliases:
            return remove_item(player, name, amount)
        remaining = amount
        for alias in aliases:
            available = get_item_count(player, alias)
            if available <= 0:
                continue
            taken = min(available, remaining)
            remove_item(player, alias, taken)
            remaining -= taken
            if remaining <= 0:
                return True
        return False

    remaining = amount
    for berry in EDIBLE_BERRIES:
        available = get_item_count(player, berry)
        if available <= 0:
            continue
        taken = min(available, remaining)
        remove_item(player, berry, taken)
        remaining -= taken
        if remaining <= 0:
            return True
    return False


def slugify_item_name(name: str) -> str:
    definition = get_item_definition_by_name(name)
    if definition and definition.get("id"):
        return str(definition["id"])
    return slugify_fallback_item_id(name)


def enter_outside_city(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    player["current_city"] = "outside_seldar"
    player["current_zone"] = "outside_city_crossroads"
    player["location_id"] = "outside_city_crossroads"
    player["current_location"] = None
    player["active_event"] = None
    player["active_timer"] = None
    storage.update_player(player)
    return LocationResponse(OUTSIDE_CITY_TEXT, outside_city_buttons(), "outside_city_crossroads")


def enter_hilly_meadows(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    location_id = "hilly_meadows"
    player["current_city"] = "outside_seldar"
    player["current_zone"] = location_id
    player["location_id"] = location_id
    player["current_location"] = location_id
    player["active_event"] = None
    player["active_timer"] = None
    storage.update_player(player)
    return LocationResponse(HILLY_MEADOWS_TEXT, location_buttons(location_id), location_id)


def enter_common_forest(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    player["current_city"] = "outside_seldar"
    player["current_zone"] = "ordinary_forest"
    player["location_id"] = "ordinary_forest"
    player["current_location"] = "ordinary_forest"
    player["active_event"] = None
    player["active_timer"] = None
    storage.update_player(player)
    return LocationResponse(location_text("ordinary_forest"), ordinary_forest_buttons(), "ordinary_forest")


def enter_small_plateau(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    player["current_city"] = "outside_seldar"
    player["current_zone"] = "small_plateau"
    player["location_id"] = "small_plateau"
    player["current_location"] = "small_plateau"
    player["active_event"] = None
    player["active_timer"] = None
    storage.update_player(player)
    return LocationResponse(location_text("small_plateau"), small_plateau_buttons(), "small_plateau")


def enter_fortress(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    player["current_city"] = "outside_seldar"
    player["current_zone"] = "fortress_in_gorge_courtyard"
    player["location_id"] = "fortress_in_gorge_courtyard"
    player["current_location"] = "fortress_in_gorge"
    player["active_event"] = None
    player["active_timer"] = None
    player["in_battle"] = False
    storage.update_player(player)
    return LocationResponse(FORTRESS_TEXT, fortress_buttons(), "fortress_in_gorge_courtyard")


def enter_camp(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    location_id = current_location_id(player, default="")
    if location_id not in EXPLORATION_LOCATION_IDS:
        return LocationResponse("Лагерь можно разбить только в обычной внешней локации.", outside_city_buttons(), player.get("current_zone", "outside_city_crossroads"))
    if player.get("active_event"):
        return LocationResponse("Сначала завершите текущее событие.", event_choice_buttons(player["active_event"].get("type", "")), player.get("current_zone", location_id))
    if player.get("in_battle"):
        return LocationResponse("Нельзя разбить лагерь во время боя.", location_buttons(location_id), player.get("current_zone", location_id))

    rest_time = calculate_scaled_seconds(int(player.get("energy", 100)), int(player.get("max_energy", 100)), 30, 600)
    timer = {
        "id": new_timer_id("camp_rest"),
        "type": "camp_rest",
        "seconds": rest_time,
        "ends_at": now_ts() + rest_time,
        "location_id": f"{location_id}_camp",
    }
    player["current_zone"] = f"{location_id}_camp"
    player["location_id"] = f"{location_id}_camp"
    player["active_timer"] = timer
    storage.update_player(player)
    hp, max_hp = hp_pair(player)
    text = (
        f"{camp_text(location_id)}\n\n"
        "🛏 Отдых начался.\n"
        f"⏳ Время отдыха: {format_duration(rest_time)}\n"
        f"❤️ Жизни сейчас: {hp}/{max_hp}\n\n"
        "Если свернуть лагерь раньше окончания отдыха, восстановление не сработает."
    )
    return LocationResponse(text, camp_buttons(), f"{location_id}_camp", scheduled_timer=build_timer_schedule(player, timer))


def leave_camp(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    location_id = current_location_id(player)
    player["current_zone"] = location_id
    player["location_id"] = location_id
    was_resting = isinstance(player.get("active_timer"), dict) and player["active_timer"].get("type") == "camp_rest"
    player["active_timer"] = None
    storage.update_player(player)
    if was_resting:
        return LocationResponse("⛺ Вы свернули лагерь раньше окончания отдыха. Таймер сброшен, показатели не восстановлены.", location_buttons(location_id), location_id)
    return LocationResponse(f"⛺ Вы сворачиваете лагерь и возвращаетесь в локацию «{location_name(location_id)}».", location_buttons(location_id), location_id)


def return_to_gates(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    location_id = current_location_id(player)
    if player.get("in_battle"):
        return LocationResponse("Нельзя вернуться к воротам во время боя.", location_buttons(location_id), player.get("current_zone", location_id))
    if player.get("active_event"):
        event_type = player["active_event"].get("type", "")
        return LocationResponse("Сначала завершите активное событие.", event_choice_buttons(event_type), player.get("current_zone", location_id))
    if player.get("active_timer"):
        return LocationResponse("Сначала завершите текущее действие с таймером.", location_buttons(location_id), player.get("current_zone", location_id))

    player["current_city"] = "seldar"
    player["current_zone"] = "seldar_city_gates"
    player["location_id"] = "seldar_city_gates"
    player["current_location"] = None
    player["active_event"] = None
    storage.update_player(player)
    text = "🚪 Вы возвращаетесь к стенам Селдара. После открытой местности городские ворота кажутся особенно надёжными."
    return LocationResponse(text, [[OUTSIDE_CITY], ["⬅️ Центральная площадь"]], "seldar_city_gates")


def start_search(storage: Any, player: dict[str, Any], rng: random.Random | None = None) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)
    location_id = current_location_id(player, default="")
    if location_id not in EXPLORATION_LOCATION_IDS:
        return LocationResponse("Поиск сейчас доступен только в обычных внешних локациях.", outside_city_buttons(), player.get("current_zone", "outside_city_crossroads"))
    location_config = LOCATION_CONFIGS.get(location_id, HILLY_MEADOWS_CONFIG)
    if player.get("in_battle"):
        return LocationResponse("Нельзя начать новый поиск во время боя.", location_buttons(location_id), location_id)
    if player.get("active_event"):
        event_type = player["active_event"].get("type", "")
        return LocationResponse("Сначала завершите текущее событие.", event_choice_buttons(event_type), location_id)
    if isinstance(player.get("active_timer"), dict):
        remaining = timer_remaining_seconds(player.get("active_timer"))
        if remaining > 0:
            return LocationResponse(
                f"⏳ Уже идёт действие с таймером. Осталось: {format_duration(remaining)}.",
                search_timer_buttons(),
                player.get("current_zone", "hilly_meadows"),
            )
        return complete_active_timer_once(storage, player, player.get("active_timer", {}).get("id"), rng)
    curse_result = roll_ancient_curse_trigger(player, "location_search", rng)
    if curse_result.get("triggered"):
        player["active_timer"] = None
        storage.update_player(player)
        return LocationResponse(str(curse_result.get("text") or "Древнее Проклятье переносит вас на Малое плато."), small_plateau_hidden_coin_buttons(), "small_plateau_hidden_coin_place")

    if location_id != "small_plateau" and not has_equipped_attack_skill(player):
        return missing_attack_skill_response(player)

    energy_stats = calculate_energy_stats(player)
    energy = int(energy_stats["current_energy"])
    max_energy = int(energy_stats["max_energy"])
    if energy <= 0:
        player["last_zero_energy_search"] = True

    base_seconds = int(location_config.get("base_search_time_seconds", BASE_SEARCH_TIME_SECONDS) or BASE_SEARCH_TIME_SECONDS)
    maximum_seconds = int(location_config.get("zero_energy_search_time_seconds", location_config.get("max_search_time_seconds", MAX_SEARCH_TIME_SECONDS)) or MAX_SEARCH_TIME_SECONDS)
    seconds = calculate_scaled_seconds(energy, max_energy, base_seconds, maximum_seconds)
    cost = min(int(location_config.get("base_search_energy_cost", SEARCH_ENERGY_COST) or SEARCH_ENERGY_COST), energy)
    player["energy"] = max(0, energy - cost)
    player["current_energy"] = player["energy"]
    player["last_search_time_seconds"] = seconds

    if location_id == "small_plateau":
        payload = {"type": "small_plateau_search", "location_id": location_id}
    else:
        raw_events = location_config.get("events") or dict(BASE_SEARCH_EVENT_WEIGHTS)
        event_weights = [(key, int(value)) for key, value in raw_events.items()] if isinstance(raw_events, dict) else BASE_SEARCH_EVENT_WEIGHTS
        event_type = weighted_choice(search_event_weights(player, event_weights), rng)

        payload: dict[str, Any]
        if event_type in {"trap", "forest_trap"}:
            payload = {"type": event_type, "location_id": location_id}
        elif event_type == "battle":
            payload = {"type": "battle"}
        else:
            payload = create_search_event(event_type, rng, location_id)

    timer_id = new_timer_id("search")
    if isinstance(payload, dict):
        payload.setdefault("event_id", f"{timer_id}_event")
    timer = {
        "id": timer_id,
        "type": "search",
        "seconds": seconds,
        "ends_at": now_ts() + seconds,
        "energy_spent": cost,
        "event": payload,
        "location_id": location_id,
    }
    player["active_timer"] = timer
    warnings = collect_energy_warning_messages(player)
    storage.update_player(player)
    hp, max_hp = hp_pair(player)
    lines = [
        "🔎 Поиск начался",
        "━━━━━━━━━━━━",
        f"📍 Локация: {location_name(location_id)}",
        f"⏳ Время поиска: {format_duration(seconds)}",
        f"⚡ Потрачено энергии: {cost}",
        f"⚡ Осталось энергии: {player['energy']}/{max_energy}",
        f"❤️ Жизни: {hp}/{max_hp}",
    ]
    if warnings:
        lines.extend(["", *warnings])
    lines.append("\nКогда таймер закончится, придёт сообщение с найденным событием.")
    return LocationResponse(
        "\n".join(lines),
        search_timer_buttons(),
        f"{location_id}_search",
        scheduled_timer=build_timer_schedule(player, timer),
    )


def complete_active_timer_once(storage: Any, player: dict[str, Any], timer_id: str | None = None, rng: random.Random | None = None) -> LocationResponse:
    """Complete an expired timer only once across linked platforms/processes."""

    timer = player.get("active_timer")
    if not isinstance(timer, dict):
        location_id = current_location_id(player)
        return LocationResponse("⏳ Активного таймера нет.", location_buttons(location_id), player.get("current_zone", location_id))
    current_timer_id = str(timer_id or timer.get("id") or "")
    if timer_id and str(timer.get("id") or "") != current_timer_id:
        location_id = current_location_id(player)
        return LocationResponse("⏳ Этот таймер уже неактуален.", location_buttons(location_id), player.get("current_zone", location_id))
    if timer_remaining_seconds(timer) > 0:
        return complete_active_timer(storage, player, current_timer_id, rng)

    game_id = str(player.get("game_id") or player.get("id") or "")
    claim_method = getattr(storage, "claim_active_timer_for_delivery", None)
    if game_id and current_timer_id and callable(claim_method):
        claimed_player = claim_method(
            game_id,
            current_timer_id,
            EVENT_RESOLUTION_OWNER,
            claim_ttl_seconds=120,
            platform_filter=None,
        )
        if not isinstance(claimed_player, dict):
            location_id = current_location_id(player)
            return LocationResponse(
                "⏳ Этот таймер уже завершён или обрабатывается с другой привязанной платформы. Повторная награда не выдаётся.",
                location_buttons(location_id),
                player.get("current_zone", location_id),
            )
        return complete_active_timer(storage, claimed_player, current_timer_id, rng)

    return complete_active_timer(storage, player, current_timer_id, rng)


def complete_active_timer(storage: Any, player: dict[str, Any], timer_id: str | None = None, rng: random.Random | None = None) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)
    timer = player.get("active_timer")
    if not isinstance(timer, dict):
        location_id = current_location_id(player)
        return LocationResponse("⏳ Активного таймера нет.", location_buttons(location_id), player.get("current_zone", location_id))
    if timer_id and timer.get("id") != timer_id:
        location_id = current_location_id(player)
        return LocationResponse("⏳ Этот таймер уже неактуален.", location_buttons(location_id), player.get("current_zone", location_id))
    remaining = timer_remaining_seconds(timer)
    if remaining > 0:
        return LocationResponse(
            f"⏳ Таймер ещё идёт. Осталось: {format_duration(remaining)}.",
            search_timer_buttons(),
            player.get("current_zone", "hilly_meadows"),
        )

    if timer.get("type") == "craft":
        from services.crafting_service import complete_craft_timer

        craft_response = complete_craft_timer(storage, player, timer.get("id"))
        return LocationResponse(craft_response.text, craft_response.buttons, craft_response.zone_id, craft_response.scheduled_timer)

    if timer.get("type") == "fishing":
        from services.fishing_service import complete_fishing_timer

        fishing_response = complete_fishing_timer(storage, player, timer.get("id"), rng)
        return LocationResponse(fishing_response.text, fishing_response.buttons, fishing_response.zone_id)

    raw_location_id = str(timer.get("location_id") or current_location_id(player))
    location_id = raw_location_id.removesuffix("_camp").removesuffix("_search").removesuffix("_battle")
    if location_id not in EXPLORATION_LOCATION_IDS:
        location_id = "hilly_meadows"

    timer_type = timer.get("type")
    if timer_type == "camp_rest":
        for current_key, max_key in (("hp", "max_hp"), ("mana", "max_mana"), ("spirit", "max_spirit")):
            if player.get(max_key) is not None:
                player[current_key] = player[max_key]
        player["active_timer"] = None
        player["current_location"] = location_id
        curse_result = roll_ancient_curse_trigger(player, "camp_rest", rng)
        if curse_result.get("triggered"):
            storage.update_player(player)
            return LocationResponse(str(curse_result.get("text") or "Древнее Проклятье переносит вас на Малое плато."), small_plateau_hidden_coin_buttons(), "small_plateau_hidden_coin_place")
        storage.update_player(player)
        return LocationResponse(
            "✅ Отдых завершён.\n\n❤️ Жизни, ✨ мана и 🔥 дух восстановлены до максимума.",
            camp_buttons(),
            f"{location_id}_camp",
        )

    if timer_type != "search":
        player["active_timer"] = None
        storage.update_player(player)
        return LocationResponse("⏳ Неизвестный таймер завершён и был очищен.", location_buttons(location_id), location_id)

    event = timer.get("event") or {}
    event_type = event.get("type")
    location_id = str(timer.get("location_id") or (event.get("location_id") if isinstance(event, dict) else "") or location_id)
    if location_id not in EXPLORATION_LOCATION_IDS:
        location_id = "hilly_meadows"
    player["active_timer"] = None
    player["current_zone"] = location_id
    player["location_id"] = location_id
    player["current_location"] = location_id

    if event_type in {"trap", "forest_trap"}:
        text = resolve_trap(player, rng, location_id)
        warnings = collect_energy_warning_messages(player)
        storage.update_player(player)
        extra = "\n\n" + "\n".join(warnings) if warnings else ""
        return LocationResponse(f"✅ Поиск завершён.\n📍 Локация: {location_name(location_id)}\n\n{text}{extra}", location_buttons(location_id), location_id)

    if event_type == "battle":
        _battle, battle_text = create_location_battle(player, rng, location_id)
        storage.update_player(player)
        return LocationResponse(f"✅ Поиск завершён.\n📍 Локация: {location_name(location_id)}\n\n{battle_text}", battle_buttons(player), f"{location_id}_battle")

    if event_type == "small_plateau_search":
        result = resolve_small_plateau_search(player, rng)
        lines = ["✅ Поиск завершён.", f"📍 Локация: {location_name(location_id)}", ""]
        if result.get("text"):
            lines.append(str(result.get("text")))
        if result.get("result_text"):
            lines.extend(["", str(result.get("result_text"))])
        milestone = result.get("milestone")
        if isinstance(milestone, dict) and milestone.get("message"):
            lines.extend(["", str(milestone.get("message"))])
        if result.get("requires_choice"):
            small_event = result.get("event") if isinstance(result.get("event"), dict) else {}
            player["active_event"] = {
                "type": "small_plateau_cursed_coins",
                "location_id": "small_plateau",
                "event_id": str(small_event.get("event_id") or f"{timer.get('id')}_cursed_coins"),
                "text": str(small_event.get("text") or "Вы нашли серебряные монеты в углублении."),
            }
            storage.update_player(player)
            if small_event.get("choice_text"):
                lines.extend(["", str(small_event.get("choice_text"))])
            return LocationResponse("\n".join(lines), event_choice_buttons("small_plateau_cursed_coins"), "small_plateau")
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse("\n".join(lines), small_plateau_buttons(), "small_plateau")

    if isinstance(event, dict):
        ensure_event_id(event, fallback=f"{timer.get('id')}_event")
    player["active_event"] = event
    storage.update_player(player)
    return LocationResponse(
        f"✅ Поиск завершён.\n📍 Локация: {location_name(location_id)}\n\n{event.get('text', 'Вы нашли событие.')}",
        event_choice_buttons(str(event_type or "")),
        location_id,
    )



def _event_text_from_config(location_id: str, event_type: str, rng: random.Random, fallback: list[str] | str) -> str:
    """Return a discovery text for a location event from JSON config.

    Old hardcoded texts are kept as fallbacks, but Hilly Meadows can now rebuild
    event texts in data/hilly_meadows.json without changing Python code.
    """
    config = LOCATION_CONFIGS.get(location_id) or HILLY_MEADOWS_CONFIG
    event_texts = config.get("event_texts") or {}
    event_data = event_texts.get(event_type) if isinstance(event_texts, dict) else None
    raw: Any = None
    if isinstance(event_data, dict):
        raw = event_data.get("discovery") or event_data.get("texts")
    elif isinstance(event_data, list):
        raw = event_data
    if isinstance(raw, list):
        options = [str(value) for value in raw if value]
        if options:
            return rng.choice(options)
    if isinstance(raw, str) and raw:
        return raw
    if isinstance(fallback, list):
        return rng.choice(fallback)
    return str(fallback)


def create_search_event(event_type: str, rng: random.Random, location_id: str = "hilly_meadows") -> dict[str, Any]:
    if event_type == "alchemy_ingredient":
        return {
            "type": "alchemy_ingredient",
            "location_id": location_id,
            "text": _event_text_from_config(
                location_id,
                "alchemy_ingredient",
                rng,
                [
                    "🌱 На вершине холма среди бесконечной травы вы замечаете несколько растений, чуть отличающихся от остальных. Их стебли плотнее, а листья имеют необычный оттенок.",
                    "🌼 На склоне холма из высокой травы выглядывает небольшой цветок. Он едва заметен, но его запах выбивается из обычного лугового аромата.",
                ],
            ),
        }
    if event_type == "stone_or_ore":
        return {
            "type": "stone_or_ore",
            "location_id": location_id,
            "text": _event_text_from_config(
                location_id,
                "stone_or_ore",
                rng,
                "🪨 У подножья холма вы замечаете подозрительный камень. Он выделяется среди обычной россыпи и выглядит так, будто его недавно вымыло дождём из земли.",
            ),
        }
    if event_type == "berries":
        return {
            "type": "berries",
            "location_id": location_id,
            "text": _event_text_from_config(
                location_id,
                "berries",
                rng,
                "🫐 В низине между холмами вы замечаете кустик ягод. С виду они съедобные, хотя проверять это лучше осторожно.",
            ),
        }
    if event_type == "glint":
        config = LOCATION_CONFIGS.get(location_id) or HILLY_MEADOWS_CONFIG
        glint_variants = config.get("glint_variants") or {
            "old_knife_up_slope": {"chance": 50, "text": "✨ Выйдя на солнечную сторону холма, вы замечаете короткий блик чуть выше по склону."},
            "search_traces_down_slope": {"chance": 50, "text": "✨ Выйдя на солнечную сторону холма, вы замечаете короткий блик чуть ниже по склону."},
        }
        weights: list[tuple[str, int]] = []
        if isinstance(glint_variants, dict):
            for key, data in glint_variants.items():
                if isinstance(data, dict):
                    weights.append((str(key), int(data.get("chance", data.get("weight", 0)) or 0)))
        if not weights:
            weights = [("old_knife_up_slope", 50), ("search_traces_down_slope", 50)]
        variant = weighted_choice(weights, rng)
        data = glint_variants.get(variant, {}) if isinstance(glint_variants, dict) else {}
        text = str(data.get("text") or "✨ Солнечный луч на мгновение отражается от чего-то в траве.") if isinstance(data, dict) else "✨ Солнечный луч на мгновение отражается от чего-то в траве."
        return {"type": "glint", "variant": variant, "text": text, "location_id": location_id}
    if event_type == "dry_tree":
        return {
            "type": "dry_tree",
            "location_id": location_id,
            "text": _event_text_from_config(
                location_id,
                "dry_tree",
                rng,
                "🪵 Вы обнаружили достаточно сухое дерево. Его нижние ветви давно высохли, а рядом лежит несколько обломанных кусков ствола.",
            ),
        }
    if event_type == "mushrooms":
        return {
            "type": "mushrooms",
            "location_id": location_id,
            "text": _event_text_from_config(
                location_id,
                "mushrooms",
                rng,
                "🍄 У подножья дерева вы замечаете грибы. Одни выглядят вполне съедобными, другие вызывают сомнение уже по одному запаху.",
            ),
        }
    if event_type == "river":
        return {
            "type": "river",
            "location_id": location_id,
            "text": _event_text_from_config(
                location_id,
                "river",
                rng,
                "💧 Пойдя на шум журчания воды, вы выходите к маленькой речушке. Вода течёт между корнями деревьев и камнями. Возможно, удастся набрать немного воды с собой.",
            ),
        }
    if event_type == "small_burrow":
        return {
            "type": "small_burrow",
            "location_id": location_id,
            "text": _event_text_from_config(
                location_id,
                "small_burrow",
                rng,
                "🕳 Между корнями старого дерева вы замечаете небольшую нору. Внутри темно, но кажется, что там что-то лежит.",
            ),
        }
    if event_type == "waterside_loot":
        if location_id == "ordinary_forest":
            text = "🌊 У влажного берега лесной речушки вы замечаете зацепившиеся за корни водоросли и несколько мелких водных находок."
        else:
            text = "🌊 В низине между холмами после дождя осталась вода. На влажной земле видны ракушки, водоросли и следы мелкого улова."
        return {"type": "waterside_loot", "location_id": location_id, "text": text}
    raise ValueError(f"Unknown event type: {event_type}")


def resolve_trap(player: dict[str, Any], rng: random.Random, location_id: str = "hilly_meadows") -> str:
    if location_id == "ordinary_forest":
        trap = weighted_choice([("mire", 45), ("tick", 50), ("bear_trap", 5)], rng)
        if trap == "mire":
            max_energy = int(player.get("max_energy", 100) or 100)
            loss = max(1, math.ceil(max_energy * rng.uniform(0.01, 0.02)))
            player["energy"] = max(0, int(player.get("energy", 0) or 0) - loss)
            player["current_energy"] = player["energy"]
            return f"🟫 Выйдя на поляну в лесу, вы умудряетесь угодить в трясину. Пока вы выбираетесь из неё, одежда тяжелеет от грязи, а силы быстро уходят. Потеряно: энергия -{loss}."
        if trap == "tick":
            max_hp = int(player.get("max_hp") or 100)
            hp = int(player.get("hp") or max_hp)
            loss = max(1, math.ceil(max_hp * rng.uniform(0.01, 0.02)))
            player["max_hp"] = max_hp
            player["hp"] = max(0, hp - loss)
            return f"🪲 Проводя поиски в лесу, вы не замечаете, как вас кусает большой клещ. Место укуса быстро начинает болеть и чесаться. Потеряно: HP -{loss}."
        max_hp = int(player.get("max_hp") or 100)
        hp = int(player.get("hp") or max_hp)
        loss = max(1, math.ceil(max_hp * rng.uniform(0.01, 0.02)))
        player["max_hp"] = max_hp
        player["hp"] = max(0, hp - loss)
        stat_keys = ["strength", "endurance", "agility", "perception", "intelligence", "wisdom"]
        stat_key = rng.choice(stat_keys)
        penalty = rng.randint(1, 3)
        player.setdefault("active_effects", []).append({
            "id": f"forest_bear_trap_{int(now_ts())}",
            "name": "Боль от капкана",
            "type": "debuff",
            "expires_at": now_ts() + 600,
            "stat_modifiers": {stat_key: -penalty},
        })
        return f"🪤 Идя по лесу, вы наступаете в старый капкан. Железные зубья всё ещё держат крепко. Потеряно: HP -{loss}. Дебаф: -{penalty} к случайной основной характеристике на 10 минут."

    trap = weighted_choice([("wet_grass", 45), ("pit", 35), ("coins", 20)], rng)
    if trap == "wet_grass":
        max_energy = int(player.get("max_energy", 100) or 100)
        loss = max(1, math.ceil(max_energy * rng.uniform(0.005, 0.02)))
        player["energy"] = max(0, int(player.get("energy", 0) or 0) - loss)
        player["current_energy"] = player["energy"]
        return f"💧 Поднимаясь на холм, вы наступаете на влажную траву, поскальзываетесь и съезжаете вниз по склону. Теперь придётся снова забираться наверх. Потеряно: энергия -{loss}."
    if trap == "pit":
        max_hp = int(player.get("max_hp") or 100)
        hp = int(player.get("hp") or max_hp)
        loss = max(1, math.ceil(max_hp * rng.uniform(0.005, 0.02)))
        player["max_hp"] = max_hp
        player["hp"] = max(0, hp - loss)
        return f"🕳 Ваши ноги запутались в высокой траве, из-за чего вы падаете. Потеряно: HP -{loss}."

    loss = rng.randint(1, 20)
    money = int(player.get("money_copper", player.get("money", 0)) or 0)
    actual_loss = min(money, loss)
    player["money_copper"] = max(0, money - actual_loss)
    player["money"] = player["money_copper"]
    return f"👝 Пробираясь через высокую траву, вы цепляете поясной кошель за сухую ветку. При проверке оказывается, что несколько монет пропали. Потеряно: медные монеты -{actual_loss}."


def claim_active_event(storage: Any, player: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Claim the current active event before granting rewards.

    This prevents duplicated event rewards when one linked Telegram/VK account
    presses the same event button from both platforms.
    """

    game_id = str(player.get("game_id") or player.get("id") or "")
    event = player.get("active_event")
    if not game_id or not isinstance(event, dict):
        return None, None

    event_id = ensure_event_id(event)
    claim_method = getattr(storage, "claim_active_event_for_resolution", None)
    if callable(claim_method):
        claimed_player = claim_method(
            game_id,
            event_id,
            EVENT_RESOLUTION_OWNER,
            claim_ttl_seconds=120,
        )
        if not isinstance(claimed_player, dict):
            return None, None
        claimed_event = claimed_player.get("active_event")
        if not isinstance(claimed_event, dict):
            return None, None
        return claimed_player, claimed_event

    # Legacy fallback: not fully atomic across processes, but still avoids
    # duplicate rewards in the common in-process case.
    return player, event


def event_already_resolving_response(player: dict[str, Any]) -> LocationResponse:
    location_id = current_location_id(player)
    return LocationResponse(
        "Это событие уже завершено или обрабатывается с другой привязанной платформы. Награда повторно не выдаётся.",
        location_buttons(location_id),
        player.get("current_zone", location_id),
    )


def resolve_active_event(storage: Any, player: dict[str, Any], action: str, rng: random.Random | None = None) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)
    event = player.get("active_event")
    location_id = current_location_id(player)
    if not event:
        storage.update_player(player)
        return LocationResponse("Активного события нет.", location_buttons(location_id), location_id)

    event_type = event.get("type")

    should_resolve = (
        action in {SKIP, LEAVE, RETREAT}
        or (event_type == "alchemy_ingredient" and action == COLLECT)
        or (event_type == "stone_or_ore" and action == INSPECT_AND_TAKE)
        or (event_type == "waterside_loot" and action == INSPECT_AND_TAKE)
        or (event_type == "berries" and action == COLLECT)
        or (event_type == "glint" and action == LOOK)
        or (event_type == "dry_tree" and action == COLLECT_TREE)
        or (event_type == "mushrooms" and action == COLLECT_MUSHROOMS)
        or (event_type == "river" and action == GATHER_WATER)
        or (event_type == "small_burrow" and action == PUT_HAND_IN_BURROW)
        or (event_type == "small_plateau_cursed_coins" and action in {TAKE_CURSED_COINS, LEAVE})
    )
    if should_resolve:
        claimed_player, claimed_event = claim_active_event(storage, player)
        if claimed_player is None or claimed_event is None:
            return event_already_resolving_response(player)
        player = claimed_player
        event = claimed_event
        event_type = event.get("type")

    location_id = str(event.get("location_id") or current_location_id(player))
    if location_id not in EXPLORATION_LOCATION_IDS:
        location_id = "hilly_meadows"

    if event_type == "small_plateau_cursed_coins" and action in {TAKE_CURSED_COINS, LEAVE}:
        result = handle_cursed_coin_choice(player, take_coins=(action == TAKE_CURSED_COINS), rng=rng)
        player["active_event"] = None
        player["current_location"] = "small_plateau"
        player["current_zone"] = "small_plateau"
        player["location_id"] = "small_plateau"
        storage.update_player(player)
        return LocationResponse(str(result.get("text") or "Событие завершено."), small_plateau_buttons(), "small_plateau")

    if action in {SKIP, LEAVE, RETREAT}:
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse(f"Вы оставляете событие позади и продолжаете путь по локации «{location_name(location_id)}».", location_buttons(location_id), location_id)


    if event_type == "dry_tree" and action == COLLECT_TREE:
        entry = _roll_resource_entry(location_id, "dry_tree", rng, [
            {"item_id": "dry_log", "name_ru": "Сухое бревно", "weight": 100, "amount_min": 1, "amount_max": 3, "max_stack": 20},
        ])
        loot_name = str(entry.get("name_ru") or entry.get("name") or "Сухое бревно")
        amount = _entry_amount(entry, rng)
        add_result = add_item(player, loot_name, amount, item_id=entry.get("item_id"), max_stack=_entry_max_stack(entry, 20), source="Обыкновенный лес")
        player["active_event"] = None
        storage.update_player(player)
        extra = inventory_add_result_notice(add_result, loot_name)
        return LocationResponse(f"🪵 Вы собираете подходящие сухие куски дерева и складываете их в связку. Получено: {loot_name} ×{add_result.added}.{extra}", location_buttons(location_id), location_id)

    if event_type == "mushrooms" and action == COLLECT_MUSHROOMS:
        entry = _roll_resource_entry(location_id, "mushrooms", rng, [
            {"item_id": "edible_forest_mushroom", "name_ru": "Съедобный лесной гриб", "weight": 70, "amount_min": 1, "amount_max": 3, "max_stack": 40},
            {"item_id": "bitter_gray_mushroom", "name_ru": "Горький серый гриб", "weight": 20, "amount_min": 1, "amount_max": 3, "max_stack": 40},
            {"item_id": "pale_toadstool", "name_ru": "Бледная поганка", "weight": 10, "amount_min": 1, "amount_max": 3, "max_stack": 40},
        ])
        loot_name = str(entry.get("name_ru") or entry.get("name") or "Съедобный лесной гриб")
        amount = _entry_amount(entry, rng)
        add_result = add_item(player, loot_name, amount, item_id=entry.get("item_id"), max_stack=_entry_max_stack(entry, 40), source="Обыкновенный лес")
        player["active_event"] = None
        storage.update_player(player)
        extra = inventory_add_result_notice(add_result, loot_name)
        return LocationResponse(f"🍄 Вы аккуратно собираете грибы. Получено: {loot_name} ×{add_result.added}.{extra}", location_buttons(location_id), location_id)

    if event_type == "river" and action == GATHER_WATER:
        river_data = _location_resource_tables(location_id).get("river_water")
        if not isinstance(river_data, dict):
            river_data = {
                "guaranteed": [{"item_id": "clean_water", "name_ru": "Чистая вода", "amount": 1, "max_stack": 20}],
                "extra_rolls": {
                    "rolls_min": 0,
                    "rolls_max": 4,
                    "table": [
                        {"item_id": "clean_water", "name_ru": "Чистая вода", "weight": 50, "amount": 1, "max_stack": 20},
                        {"item_id": "muddy_water", "name_ru": "Мутная вода", "weight": 50, "amount": 1, "max_stack": 20},
                    ],
                },
                "bonus": {"currency": "silver", "chance_percent": 1, "amount": 1, "copper_equivalent": 1000},
            }

        amounts: dict[str, dict[str, Any]] = {}
        for entry in river_data.get("guaranteed", []):
            if not isinstance(entry, dict):
                continue
            loot_name = str(entry.get("name_ru") or entry.get("name") or "Чистая вода")
            bucket = amounts.setdefault(loot_name, {"amount": 0, "item_id": entry.get("item_id"), "max_stack": _entry_max_stack(entry, 20)})
            bucket["amount"] += _entry_amount(entry, rng)

        extra_rolls = river_data.get("extra_rolls") if isinstance(river_data.get("extra_rolls"), dict) else {}
        rolls_min = int(extra_rolls.get("rolls_min", 0) or 0)
        rolls_max = int(extra_rolls.get("rolls_max", rolls_min) or rolls_min)
        if rolls_max < rolls_min:
            rolls_max = rolls_min
        extra_table = extra_rolls.get("table")
        for _ in range(rng.randint(rolls_min, rolls_max)):
            entry = _choose_resource_entry(extra_table, rng, [
                {"item_id": "clean_water", "name_ru": "Чистая вода", "weight": 50, "amount": 1, "max_stack": 20},
                {"item_id": "muddy_water", "name_ru": "Мутная вода", "weight": 50, "amount": 1, "max_stack": 20},
            ])
            loot_name = str(entry.get("name_ru") or entry.get("name") or "Чистая вода")
            bucket = amounts.setdefault(loot_name, {"amount": 0, "item_id": entry.get("item_id"), "max_stack": _entry_max_stack(entry, 20)})
            bucket["amount"] += _entry_amount(entry, rng)

        parts: list[str] = []
        notices = ""
        for loot_name, data in amounts.items():
            add_result = add_item(player, loot_name, int(data.get("amount", 0) or 0), item_id=data.get("item_id"), max_stack=int(data.get("max_stack", 20) or 20), source="Обыкновенный лес")
            if add_result.added:
                parts.append(f"{loot_name} ×{add_result.added}")
            notices += inventory_add_result_notice(add_result, loot_name)

        bonus = ""
        bonus_data = river_data.get("bonus") if isinstance(river_data.get("bonus"), dict) else {}
        if rng.uniform(0, 100) <= float(bonus_data.get("chance_percent", 1) or 1):
            bonus_amount = max(1, int(bonus_data.get("amount", 1) or 1))
            copper = int(bonus_data.get("copper_equivalent", 1000) or 1000) * bonus_amount
            player["money_copper"] = int(player.get("money_copper", player.get("money", 0)) or 0) + copper
            player["money"] = player["money_copper"]
            bonus = f"\n✨ Уже отходя от речушки, вы замечаете короткий блик в воде и достаёте серебряную монету. Получено: серебряная монета ×{bonus_amount}."
        player["active_event"] = None
        storage.update_player(player)
        obtained = ", ".join(parts) if parts else "ничего"
        return LocationResponse(f"💧 Вы набираете воду в пустые банки. Получено: {obtained}.{notices}{bonus}", location_buttons(location_id), location_id)

    if event_type == "small_burrow" and action == PUT_HAND_IN_BURROW:
        entry = _roll_resource_entry(location_id, "small_burrow", rng, [
            {"result": "old_gloves", "item_id": "old_gloves", "name_ru": "Старые перчатки (необычные)", "weight": 12, "amount": 1, "max_stack": 1},
            {"result": "fabric_pieces", "item_id": "fabric_pieces", "name_ru": "Куски ткани", "weight": 36, "amount_min": 1, "amount_max": 3, "max_stack": 20},
            {"result": "decent_belt", "item_id": "decent_belt", "name_ru": "Неплохой пояс (необычные)", "weight": 12, "amount": 1, "max_stack": 1},
            {"result": "bite", "name_ru": "Укус из норы", "weight": 40, "effect": "hp_loss_10_percent"},
        ])
        result = str(entry.get("result") or "")
        player["active_event"] = None
        if result == "old_gloves":
            loot_name = str(entry.get("name_ru") or "Старые перчатки")
            add_result = add_item(player, loot_name, _entry_amount(entry, rng), item_id=entry.get("item_id"), max_stack=_entry_max_stack(entry, 1), source="Обыкновенный лес")
            extra = inventory_add_result_notice(add_result, loot_name)
            storage.update_player(player)
            return LocationResponse(f"🧤 Нащупав что-то мягкое, вы вытаскиваете из норы пару старых перчаток. Получено: {loot_name} ×{add_result.added}.{extra}", location_buttons(location_id), location_id)
        if result == "fabric_pieces":
            loot_name = str(entry.get("name_ru") or "Куски ткани")
            add_result = add_item(player, loot_name, _entry_amount(entry, rng), item_id=entry.get("item_id"), max_stack=_entry_max_stack(entry, 20), source="Обыкновенный лес")
            extra = inventory_add_result_notice(add_result, loot_name)
            storage.update_player(player)
            return LocationResponse(f"🧵 В норе оказывается старый сгнивший свёрток. Несколько кусков ткани ещё можно использовать. Получено: {loot_name} ×{add_result.added}.{extra}", location_buttons(location_id), location_id)
        if result == "decent_belt":
            loot_name = str(entry.get("name_ru") or "Неплохой пояс")
            add_result = add_item(player, loot_name, _entry_amount(entry, rng), item_id=entry.get("item_id"), max_stack=_entry_max_stack(entry, 1), source="Обыкновенный лес")
            extra = inventory_add_result_notice(add_result, loot_name)
            storage.update_player(player)
            return LocationResponse(f"🟫 Вы тянете руку глубже и вытаскиваете крепкий пояс. Получено: {loot_name} ×{add_result.added}.{extra}", location_buttons(location_id), location_id)
        max_hp = int(player.get("max_hp") or 100)
        hp = int(player.get("hp") or max_hp)
        loss = max(1, math.ceil(max_hp * 0.10))
        player["hp"] = max(0, hp - loss)
        storage.update_player(player)
        return LocationResponse(f"🩸 Стоит вам просунуть руку внутрь, как что-то резко кусает вас за пальцы. Потеря: HP -{loss}.", location_buttons(location_id), location_id)

    if event_type == "alchemy_ingredient" and action == COLLECT:
        entry = _roll_resource_entry(location_id, "alchemy_ingredient", rng, [
            {"name_ru": "Луговая мята", "weight": 20, "amount_min": 1, "amount_max": 2},
            {"name_ru": "Серебристая ромашка", "weight": 20, "amount_min": 1, "amount_max": 2},
            {"name_ru": "Жёлтый клевер", "weight": 20, "amount_min": 1, "amount_max": 2},
            {"name_ru": "Горная полынь", "weight": 20, "amount_min": 1, "amount_max": 2},
            {"name_ru": "Луговой корень", "weight": 20, "amount_min": 1, "amount_max": 2},
        ])
        loot_name = str(entry.get("name_ru") or entry.get("name") or "Луговая мята")
        amount = _entry_amount(entry, rng)
        extra_chance = extra_alchemy_ingredient_chance_percent(player)
        got_extra = bool(extra_chance and rng.uniform(0, 100) <= extra_chance)
        if got_extra:
            amount += 1
        add_result = add_item(player, loot_name, amount, item_id=entry.get("item_id"))
        amount = add_result.added
        player["active_event"] = None
        storage.update_player(player)
        extra_text = inventory_add_result_notice(add_result, loot_name)
        if got_extra:
            extra_text += "\n🧝 Знание трав помогло найти дополнительный ингредиент."
        return LocationResponse(f"Вы аккуратно собираете растение и убираете его в сумку. Получено: {loot_name} ×{amount}.{extra_text}", location_buttons(location_id), location_id)


    
    if event_type == "waterside_loot" and action == INSPECT_AND_TAKE:
        name, amount, notice = grant_waterside_reward(player, location_id, rng)
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse(f"🌊 Вы осматриваете влажный берег и забираете полезную находку. Получено: {name} ×{amount}.{notice}", location_buttons(location_id), location_id)

    if event_type == "stone_or_ore" and action == INSPECT_AND_TAKE:
        entry = _roll_resource_entry(location_id, "stone_or_ore", rng, [
            {"name_ru": "Обычный камень", "weight": 92, "amount_min": 1, "amount_max": 3},
            {"name_ru": "Кусок медной руды", "weight": 5, "amount_min": 1, "amount_max": 2},
            {"name_ru": "Кусок железной руды", "weight": 3, "amount_min": 1, "amount_max": 2},
        ])
        result = str(entry.get("name_ru") or entry.get("name") or "Обычный камень")
        amount = _entry_amount(entry, rng)
        add_result = add_item(player, result, amount, item_id=entry.get("item_id"))
        amount = add_result.added
        extra = inventory_add_result_notice(add_result, result)
        player["active_event"] = None
        storage.update_player(player)
        if result == "Обычный камень":
            text = f"Это оказался самый обычный камень. Ничего ценного, но в хозяйстве может пригодиться. Получено: {result} ×{amount}.{extra}"
        else:
            text = f"При осмотре вы замечаете металлические прожилки. Это не простой камень, а небольшой кусок руды. Получено: {result} ×{amount}.{extra}"
        return LocationResponse(text, location_buttons(location_id), location_id)

    
    if event_type == "berries" and action == COLLECT:
        entry = _roll_resource_entry(location_id, "berries", rng, [
            {"name_ru": "Сладкая луговая ягода", "weight": 50, "amount_min": 2, "amount_max": 5},
            {"name_ru": "Терпкая синяя ягода", "weight": 50, "amount_min": 2, "amount_max": 5},
        ])
        loot_name = str(entry.get("name_ru") or entry.get("name") or "Сладкая луговая ягода")
        amount = _entry_amount(entry, rng)
        add_result = add_item(player, loot_name, amount, item_id=entry.get("item_id"))
        amount = add_result.added
        extra = inventory_add_result_notice(add_result, loot_name)
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse(f"Вы собираете ягоды с нижних веток куста, стараясь не раздавить самые спелые. Получено: {loot_name} ×{amount}.{extra}", location_buttons(location_id), location_id)

    
    if event_type == "glint" and action == LOOK:
        response = resolve_glint_event(player, event, rng)
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse(response, location_buttons(location_id), location_id)

    return LocationResponse("Выберите действие кнопкой события.", event_choice_buttons(event_type or ""), location_id)


def resolve_glint_event(player: dict[str, Any], event: dict[str, Any], rng: random.Random) -> str:
    variant = event.get("variant")
    location_id = str(event.get("location_id") or current_location_id(player))
    if variant == "old_knife_up_slope":
        entry = _roll_resource_entry(location_id, "glint_old_knife_up_slope", rng, [
            {"name_ru": "Железный лом", "weight": 70, "amount_min": 1, "amount_max": 1},
            {"name_ru": "Старый нож", "weight": 30, "amount_min": 1, "amount_max": 1},
        ])
        result = str(entry.get("name_ru") or entry.get("name") or "Железный лом")
        amount = _entry_amount(entry, rng)
        add_result = add_item(player, result, amount, item_id=entry.get("item_id"))
        if add_result.added <= 0:
            return "Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. Но места в инвентаре нет, и забрать находку некуда."
        amount = add_result.added
        extra = inventory_add_result_notice(add_result, result)
        if result == "Железный лом":
            return (
                "Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. "
                "Скорее всего, кто-то пытался замедлить спуск вниз по траве, но вышло не слишком удачно.\n\n"
                f"Осмотрев находку, вы понимаете, что это почти полный хлам, пригодный только на переплавку. Получено: Железный лом ×{amount}.{extra}"
            )
        return (
            "Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. "
            "Скорее всего, кто-то пытался замедлить спуск вниз по траве, но вышло не слишком удачно.\n\n"
            f"Нож в сносном состоянии, но для боя почти не годится. Его можно продать или разобрать. Получено: Старый нож ×{amount}.{extra}"
        )

    entry = _roll_resource_entry(location_id, "glint_search_traces_down_slope", rng, [
        {"currency": "copper", "name_ru": "Медные монеты", "weight": 75, "amount_min": 1, "amount_max": 10},
        {"currency": "silver", "name_ru": "Серебряная монета", "weight": 2, "amount_min": 1, "amount_max": 1, "copper_equivalent": 1000},
        {"nothing": True, "name_ru": "Ничего", "weight": 23, "amount_min": 0, "amount_max": 0},
    ])
    if entry.get("nothing"):
        return (
            "Спустившись ниже по склону, вы видите примятую и разбросанную вырванную траву. "
            "Похоже, здесь кто-то что-то потерял и долго пытался найти.\n\n"
            "Вы тратите немного времени на поиски, но ничего не находите. Видимо, тот, кто искал до вас, всё-таки нашёл пропажу."
        )
    if entry.get("currency") == "silver":
        amount = _entry_amount(entry, rng)
        copper = int(entry.get("copper_equivalent", 1000) or 1000) * amount
        player["money_copper"] = int(player.get("money_copper", player.get("money", 0)) or 0) + copper
        player["money"] = player["money_copper"]
        return (
            "Спустившись ниже по склону, вы видите примятую и разбросанную вырванную траву. "
            "Похоже, здесь кто-то что-то потерял и долго пытался найти.\n\n"
            f"Среди примятой травы блестит серебряная монета. Странно, что её не заметили раньше. Получено: серебряная монета ×{amount}."
        )
    amount = _entry_amount(entry, rng)
    player["money_copper"] = int(player.get("money_copper", player.get("money", 0)) or 0) + amount
    player["money"] = player["money_copper"]
    return (
        "Спустившись ниже по склону, вы видите примятую и разбросанную вырванную траву. "
        "Похоже, здесь кто-то что-то потерял и долго пытался найти.\n\n"
        f"Немного поискав в траве, вы находите несколько монет. Видимо, именно их здесь и искали. Получено: медные монеты ×{amount}."
    )

def show_cooking_menu(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    location_id = current_location_id(player)
    player["current_zone"] = f"{location_id}_camp_cooking"
    player["location_id"] = player["current_zone"]
    storage.update_player(player)
    recipe_lines = ["🔥 Готовка в лагере", "", "Выберите блюдо по номеру на кнопке:"]
    for index, (dish_name, data) in enumerate(CAMP_DISHES.items(), start=1):
        ingredients = "; ".join(f"{name} ×{amount}" for name, amount in data["ingredients"].items())
        can_craft = available_craft_count(player, dish_name)
        mark = "✅" if can_craft > 0 else "❌"
        recipe_lines.append(f"{index}. {mark} {dish_name}: {ingredients}. ⚡ Энергия +{data['restore_energy']}. Можно приготовить: {can_craft}.")
    return LocationResponse("\n".join(recipe_lines), cook_buttons(player), f"{location_id}_camp_cooking")


def cook_dish(storage: Any, player: dict[str, Any], dish_name: str, amount: int = 1) -> LocationResponse:
    ensure_external_fields(player)
    location_id = current_location_id(player)
    amount = max(1, min(10, int(amount or 1)))
    dish = CAMP_DISHES[dish_name]
    missing = [f"{name} ×{needed * amount}" for name, needed in dish["ingredients"].items() if not has_ingredient(player, name, needed * amount)]
    if missing:
        return LocationResponse("У вас не хватает простых ингредиентов для этого блюда.\n\nНе хватает: " + ", ".join(missing), cook_buttons(player), f"{location_id}_camp_cooking")
    for name, needed in dish["ingredients"].items():
        consume_ingredient(player, name, needed * amount)
    add_result = add_item(player, dish_name, amount, item_id=slugify_item_name(dish_name), max_stack=20, source=location_name(location_id))
    storage.update_player(player)
    if add_result.added <= 0:
        return LocationResponse(
            "🔥 Вы приготовили походное блюдо, но в инвентаре нет места. Блюдо пришлось оставить у костра.",
            cook_buttons(player),
            f"{location_id}_camp_cooking",
        )
    extra = inventory_add_result_notice(add_result, dish_name)
    return LocationResponse(f"🔥 Вы готовите походное блюдо на маленьком костре.\nПолучено: {dish_name} ×{add_result.added}.{extra}", cook_buttons(player), f"{location_id}_camp_cooking")


def show_eating_menu(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    location_id = current_location_id(player)
    player["current_zone"] = f"{location_id}_camp_eating"
    player["location_id"] = player["current_zone"]
    storage.update_player(player)
    lines = ["🍽 Еда в лагере", ""]
    has_food = False
    for index, (dish_name, data) in enumerate(CAMP_DISHES.items(), start=1):
        count = get_item_count(player, dish_name)
        if count > 0:
            has_food = True
            lines.append(f"{index}. {dish_name} ×{count} — восстановит {data['restore_energy']} энергии")
    if not has_food:
        lines.append("В инвентаре нет готовых лагерных блюд.")
    return LocationResponse("\n".join(lines), eat_buttons(player), f"{location_id}_camp_eating")


def eat_dish(storage: Any, player: dict[str, Any], dish_name: str, amount: int = 1) -> LocationResponse:
    ensure_external_fields(player)
    location_id = current_location_id(player)
    amount = max(1, min(10, int(amount or 1)))
    dish = CAMP_DISHES[dish_name]
    if not remove_item(player, dish_name, amount):
        return LocationResponse("Такого блюда нет в инвентаре.", eat_buttons(player), f"{location_id}_camp_eating")
    energy_stats = calculate_energy_stats(player)
    before = int(energy_stats["current_energy"])
    max_energy = int(energy_stats["max_energy"])
    restored = int(dish["restore_energy"]) * amount
    player.setdefault("base_max_energy", int(energy_stats["base_max_energy"]))
    player["energy"] = min(max_energy, before + restored)
    player["current_energy"] = player["energy"]
    actual = player["energy"] - before
    clear_energy_warning_if_recovered(player)
    storage.update_player(player)
    return LocationResponse(f"🍽 Вы использовали {dish_name} ×{amount}.\n⚡ Энергия восстановлена: +{actual}. Сейчас: {player['energy']}/{max_energy}.", eat_buttons(player), f"{location_id}_camp_eating")


def handle_fortress_action(storage: Any, player: dict[str, Any], action: str) -> LocationResponse:
    ensure_external_fields(player)
    player["current_location"] = "fortress_in_gorge"
    player["current_city"] = "outside_seldar"
    player["active_event"] = None
    player["active_timer"] = None
    player["in_battle"] = False

    if action in {FORTRESS_COURTYARD, FORTRESS_BACK, STAY_IN_FORTRESS}:
        player["current_zone"] = "fortress_in_gorge_courtyard"
        player["location_id"] = "fortress_in_gorge_courtyard"
        storage.update_player(player)
        return LocationResponse(FORTRESS_TEXT, fortress_buttons(), "fortress_in_gorge_courtyard")

    if action == FORTRESS_HALL:
        player["current_zone"] = "fortress_in_gorge_town_hall"
        player["location_id"] = "fortress_in_gorge_town_hall"
        storage.update_player(player)
        return LocationResponse(FORTRESS_TOWN_HALL_TEXT, fortress_town_hall_buttons(), "fortress_in_gorge_town_hall")

    if action == FORTRESS_MANAGER:
        result = fine_card(player, place="fortress")
        player["current_zone"] = result.zone_id
        player["location_id"] = result.zone_id
        storage.update_player(player)
        return LocationResponse(result.text, result.buttons, result.zone_id)

    if action == FORTRESS_COMMANDANT:
        player["current_zone"] = "fortress_in_gorge_commandant"
        player["location_id"] = "fortress_in_gorge_commandant"
        storage.update_player(player)
        return LocationResponse(FORTRESS_COMMANDANT_TEXT, [[FORTRESS_HALL], [FORTRESS_COURTYARD]], "fortress_in_gorge_commandant")

    if action == FORTRESS_ALLEYS:
        player["current_zone"] = "fortress_in_gorge_alleys"
        player["location_id"] = "fortress_in_gorge_alleys"
        storage.update_player(player)
        return LocationResponse(FORTRESS_ALLEYS_TEXT, fortress_alleys_buttons(), "fortress_in_gorge_alleys")

    if action == FORTRESS_RESOURCE_BUYER:
        player["current_zone"] = "fortress_in_gorge_resource_buyer"
        player["location_id"] = "fortress_in_gorge_resource_buyer"
        storage.update_player(player)
        return LocationResponse(FORTRESS_RESOURCE_BUYER_TEXT, [[FORTRESS_ALLEYS], [FORTRESS_COURTYARD]], "fortress_in_gorge_resource_buyer")

    if action == FORTRESS_COORDINATOR:
        player["current_zone"] = "fortress_in_gorge_coordinator"
        player["location_id"] = "fortress_in_gorge_coordinator"
        storage.update_player(player)
        return LocationResponse(FORTRESS_COORDINATOR_TEXT, fortress_coordinator_buttons(player), "fortress_in_gorge_coordinator")

    if action == FORTRESS_ORDER_BOARD:
        player["current_zone"] = "fortress_in_gorge_order_board"
        player["location_id"] = "fortress_in_gorge_order_board"
        storage.update_player(player)
        return LocationResponse(FORTRESS_ORDER_BOARD_TEXT, fortress_order_board_buttons(), "fortress_in_gorge_order_board")

    if action == FORTRESS_CREATE_ORDER_MENU:
        player["current_zone"] = "fortress_in_gorge_create_order_menu"
        player["location_id"] = "fortress_in_gorge_create_order_menu"
        storage.update_player(player)
        return LocationResponse(FORTRESS_CREATE_ORDER_TEXT, fortress_create_order_buttons(), "fortress_in_gorge_create_order_menu")

    if action == FORTRESS_CREATE_ORDER:
        player["current_zone"] = "fortress_in_gorge_order_form_pending"
        player["location_id"] = "fortress_in_gorge_order_form_pending"
        player["fortress_order_creation"] = {"status": "pending_form"}
        storage.update_player(player)
        text = FORTRESS_CREATE_ORDER_TEXT + "\n\nОтправьте анкету одним сообщением. Обработка формы будет подключена следующим шагом."
        return LocationResponse(text, [[FORTRESS_CANCEL_CREATE_ORDER], [FORTRESS_ORDER_BOARD]], "fortress_in_gorge_order_form_pending")

    if action == FORTRESS_CANCEL_CREATE_ORDER:
        player.pop("fortress_order_creation", None)
        player["current_zone"] = "fortress_in_gorge_create_order_menu"
        player["location_id"] = "fortress_in_gorge_create_order_menu"
        storage.update_player(player)
        return LocationResponse("Создание заказа отменено.", fortress_create_order_buttons(), "fortress_in_gorge_create_order_menu")

    if action == FORTRESS_VIEW_ORDERS:
        player["current_zone"] = "fortress_in_gorge_view_orders"
        player["location_id"] = "fortress_in_gorge_view_orders"
        storage.update_player(player)
        return LocationResponse("Заказов нет. Никто пока никого не заказал.\n\nПолный список заказов будет подключён следующим runtime-шагом.", [[FORTRESS_ORDER_BOARD], [FORTRESS_COURTYARD]], "fortress_in_gorge_view_orders")

    if action == FORTRESS_MY_ORDERS:
        player["current_zone"] = "fortress_in_gorge_my_orders"
        player["location_id"] = "fortress_in_gorge_my_orders"
        storage.update_player(player)
        return LocationResponse("Вы ещё никого не заказали.", [[FORTRESS_ORDER_BOARD], [FORTRESS_COURTYARD]], "fortress_in_gorge_my_orders")

    if action == FORTRESS_TAKEN_ORDERS:
        player["current_zone"] = "fortress_in_gorge_taken_orders"
        player["location_id"] = "fortress_in_gorge_taken_orders"
        storage.update_player(player)
        return LocationResponse("У вас нет активных заказов.\n\nАрхив заказов и сдача мешков с доказательствами будут подключены следующим runtime-шагом.", [[FORTRESS_ORDER_BOARD], [FORTRESS_COURTYARD]], "fortress_in_gorge_taken_orders")

    if action == FORTRESS_QUESTS:
        player["current_zone"] = "fortress_in_gorge_coordinator_quests"
        player["location_id"] = "fortress_in_gorge_coordinator_quests"
        storage.update_player(player)
        return LocationResponse("⏳ Особые квесты Координатора будут подключены позже.", [[FORTRESS_COORDINATOR], [FORTRESS_COURTYARD]], "fortress_in_gorge_coordinator_quests")

    if action == FORTRESS_ASSASSIN_GUILD:
        player["current_zone"] = "fortress_in_gorge_assassin_guild"
        player["location_id"] = "fortress_in_gorge_assassin_guild"
        storage.update_player(player)
        if player.get("assassin_guild_unlocked") or player.get("assassin_mark"):
            text = "🕯 Скрытый вход в Гильдию Убийц отмечен старым знаком. Полная механика вступления будет подключена позже."
        else:
            text = "Вы не видите здесь ничего, похожего на вход в гильдию."
        return LocationResponse(text, [[FORTRESS_COORDINATOR], [FORTRESS_COURTYARD]], "fortress_in_gorge_assassin_guild")

    if action == FORTRESS_SEEKER_OUTPOST:
        player["current_zone"] = "fortress_in_gorge_seeker_outpost"
        player["location_id"] = "fortress_in_gorge_seeker_outpost"
        storage.update_player(player)
        return LocationResponse(FORTRESS_SEEKER_OUTPOST_TEXT, fortress_seeker_outpost_buttons(), "fortress_in_gorge_seeker_outpost")

    if action == FORTRESS_NOTICE_BOARD:
        player["current_zone"] = "fortress_in_gorge_notice_board"
        player["location_id"] = "fortress_in_gorge_notice_board"
        storage.update_player(player)
        return LocationResponse(FORTRESS_NOTICE_BOARD_TEXT, [[FORTRESS_SEEKER_OUTPOST], [FORTRESS_COURTYARD]], "fortress_in_gorge_notice_board")

    if action == FORTRESS_GUILD_AGENT:
        player["current_zone"] = "fortress_in_gorge_guild_agent"
        player["location_id"] = "fortress_in_gorge_guild_agent"
        storage.update_player(player)
        return LocationResponse(FORTRESS_GUILD_AGENT_TEXT, [[FORTRESS_SEEKER_OUTPOST], [FORTRESS_COURTYARD]], "fortress_in_gorge_guild_agent")

    if action == FORTRESS_HIRE:
        player["current_zone"] = "fortress_in_gorge_hire"
        player["location_id"] = "fortress_in_gorge_hire"
        storage.update_player(player)
        return LocationResponse(FORTRESS_HIRE_TEXT, [[FORTRESS_SEEKER_OUTPOST], [FORTRESS_COURTYARD]], "fortress_in_gorge_hire")

    if action == FORTRESS_ROAD_TO_CITY:
        return return_to_gates(storage, player)

    if action == FORTRESS_EXIT_GATE:
        player["current_zone"] = "fortress_in_gorge_mainland_gate"
        player["location_id"] = "fortress_in_gorge_mainland_gate"
        storage.update_player(player)
        return LocationResponse(FORTRESS_MAINLAND_TEXT, fortress_mainland_buttons(), "fortress_in_gorge_mainland_gate")

    return LocationResponse(FORTRESS_TEXT, fortress_buttons(), "fortress_in_gorge_courtyard")



def _parse_name_amount(payload: str) -> tuple[str, int]:
    payload = str(payload or "").strip()
    if "×" not in payload:
        return payload, 1
    name, raw_amount = payload.rsplit("×", 1)
    try:
        amount = int(raw_amount.strip())
    except ValueError:
        amount = 1
    return name.strip(), max(1, amount)


def _parse_numbered_camp_action(action: str, prefix: str) -> tuple[str | None, int]:
    tail = str(action or "").removeprefix(prefix).strip()
    if "×" in tail:
        raw_index, raw_amount = tail.rsplit("×", 1)
    else:
        raw_index, raw_amount = tail, "1"
    try:
        index = int(raw_index.strip())
    except ValueError:
        return None, 1
    try:
        amount = int(raw_amount.strip())
    except ValueError:
        amount = 1
    return camp_dish_name_by_index(index), max(1, amount)


def _is_equipped_skill_action(player: dict[str, Any], action: str) -> bool:
    skills = player.get("skills") or {}
    for skill in skills.get("equipped", []) if isinstance(skills, dict) else []:
        if isinstance(skill, dict) and str(skill.get("name") or skill.get("id") or "") == action:
            return True
    return False


def _equipped_attack_skills(player: dict[str, Any]) -> list[dict[str, Any]]:
    normalize_starter_only_skills(player)
    skills = player.get("skills") or {}
    equipped = skills.get("equipped", []) if isinstance(skills, dict) else []
    result: list[dict[str, Any]] = []
    for skill in equipped:
        if not isinstance(skill, dict):
            continue
        damage_type = str(skill.get("damage_type") or skill.get("damageType") or "").casefold()
        category = str(skill.get("category") or skill.get("skill_type") or skill.get("type") or "").casefold()
        has_damage = bool(skill.get("damage") or skill.get("base_damage_formula") or skill.get("damage_formula"))
        if has_damage or damage_type in {"physical", "magic", "mixed"} or "атака" in category or "attack" in category:
            result.append(skill)
    return result


def has_equipped_attack_skill(player: dict[str, Any]) -> bool:
    return bool(_equipped_attack_skills(player))


def missing_attack_skill_response(player: dict[str, Any]) -> LocationResponse:
    location_id = current_location_id(player)
    skills = player.get("skills") or {}
    active = skills.get("active", []) if isinstance(skills, dict) else []
    known_attack_names = [
        str(skill.get("name") or skill.get("id"))
        for skill in active
        if isinstance(skill, dict) and (skill.get("damage") or skill.get("base_damage_formula") or str(skill.get("category") or "").casefold().find("атака") >= 0)
    ]
    hint = ""
    if known_attack_names:
        hint = "\n\nДоступные атакующие навыки для экипировки: " + ", ".join(known_attack_names[:4]) + "."
    return LocationResponse(
        "⚔️ Перед первым поиском экипируйте хотя бы один атакующий навык в профиле. "
        "Иначе в бою останутся только «Подсумок» и «Сбежать»."
        "\n\nНажмите «Профиль», экипируйте «Обычный удар» и вернитесь к поиску." + hint,
        [[PROFILE_BUTTON], [START_SEARCH, SET_CAMP], [RETURN_TO_CITY]],
        location_id,
    )


def handle_external_location_action(
    storage: Any,
    player: dict[str, Any],
    action: str,
    rng: random.Random | None = None,
) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)

    fine_advance = advance_fine_state(player)
    if fine_advance.changed:
        storage.update_player(player)

    if action == MAINLAND_EXTERNAL:
        return LocationResponse(OUTSIDE_CITY_TEXT, [[SMALL_PLATEAU], [FORTRESS_IN_GORGE]], "outside_city_crossroads")

    if action == STAY_IN_FORTRESS:
        return enter_fortress(storage, player)

    if action == CITY_FINE_PAY_ACTION:
        result = pay_fine(player, place="fortress")
        storage.update_player(player)
        return LocationResponse(result.text, result.buttons, result.zone_id)

    if should_block_movement_action(player, action):
        storage.update_player(player)
        return LocationResponse(movement_block_text(), movement_block_buttons(), player.get("current_zone", "fortress_in_gorge_courtyard"))

    if player.get("in_battle"):
        if (
            action in BATTLE_ACTIONS
            or action in {"Подсумок далее", "Подсумок назад"}
            or action.startswith("Предмет ")
            or action.startswith("Цель: ")
            or action.startswith("Использовать: ")
            or _is_equipped_skill_action(player, action)
        ):
            text, buttons = handle_battle_action(player, action, rng)
            storage.update_player(player)
            location_id = current_location_id(player)
            return LocationResponse(text, buttons or location_buttons(location_id), player.get("current_zone", location_id))
        return LocationResponse("⚔️ Сейчас вы в бою. Сначала завершите бой или сбегите.", battle_buttons(player), player.get("current_zone", "hilly_meadows_battle"))

    if isinstance(player.get("active_timer"), dict):
        active_timer = player.get("active_timer") or {}
        if action == BACK:
            return cancel_active_timer(storage, player)
        if action == CHECK_TIMER:
            return complete_active_timer_once(storage, player, active_timer.get("id"), rng)
        if timer_remaining_seconds(active_timer) <= 0:
            return complete_active_timer_once(storage, player, active_timer.get("id"), rng)
        if action == BREAK_CAMP:
            return leave_camp(storage, player)
        if active_timer.get("type") != "camp_rest":
            remaining = timer_remaining_seconds(active_timer)
            return LocationResponse(
                f"⏳ Сначала дождитесь окончания таймера. Осталось: {format_duration(remaining)}.",
                search_timer_buttons(),
                player.get("current_zone", "hilly_meadows"),
            )

    if action == BACK:
        return current_location_back_response(player)
    if action in {OUTSIDE_CITY, LEGACY_OUTSIDE_CITY}:
        return enter_outside_city(storage, player)
    if action in {RETURN_TO_GATES, RETURN_TO_SELDAR_GATES, RETURN_TO_CITY}:
        return return_to_gates(storage, player)
    if action == HILLY_MEADOWS:
        return enter_hilly_meadows(storage, player)
    if action == COMMON_FOREST:
        return enter_common_forest(storage, player)
    if action == SMALL_PLATEAU:
        return enter_small_plateau(storage, player)
    if action == APPROACH_ARCH:
        player["current_zone"] = "small_plateau_arch"
        player["location_id"] = "small_plateau_arch"
        player["current_location"] = "small_plateau"
        storage.update_player(player)
        return LocationResponse("🏛 Древняя арка\n\nВы подходите к очень древней повреждённой арке. Рядом видны остатки постамента.", small_plateau_arch_buttons(), "small_plateau_arch")
    if action == RETURN_SMALL_PLATEAU:
        return enter_small_plateau(storage, player)
    if action == INSPECT_ARCH:
        arch = SMALL_PLATEAU_CONFIG.get("arch_menu") if isinstance(SMALL_PLATEAU_CONFIG, dict) else {}
        text = str((arch or {}).get("inspect_text") or "Осмотрев арку, вы находите только полустёртые символы, трещины, сколы и мох. Починить и активировать её без чертежей, умений и дорогих ресурсов нельзя.")
        player["current_zone"] = "small_plateau_arch"
        player["location_id"] = "small_plateau_arch"
        player["current_location"] = "small_plateau"
        storage.update_player(player)
        return LocationResponse(text, small_plateau_arch_buttons(), "small_plateau_arch")
    if action == PAY_100_SILVER:
        result = cleanse_ancient_curse_at_hidden_place(player)
        storage.update_player(player)
        return LocationResponse(str(result.get("text") or ""), small_plateau_buttons() if result.get("success") else small_plateau_hidden_coin_buttons(), player.get("current_zone", "small_plateau_hidden_coin_place"))
    if action == LEAVE_WITH_CURSE:
        result = leave_hidden_coin_place_with_curse(player)
        storage.update_player(player)
        return LocationResponse(str(result.get("text") or ""), small_plateau_buttons(), "small_plateau")
    if action == FORTRESS_IN_GORGE:
        return enter_fortress(storage, player)
    if action in {
        FORTRESS_COURTYARD,
        FORTRESS_HALL,
        FORTRESS_BACK,
        STAY_IN_FORTRESS,
        FORTRESS_MANAGER,
        FORTRESS_COMMANDANT,
        FORTRESS_ALLEYS,
        FORTRESS_RESOURCE_BUYER,
        FORTRESS_COORDINATOR,
        FORTRESS_ORDER_BOARD,
        FORTRESS_QUESTS,
        FORTRESS_ASSASSIN_GUILD,
        FORTRESS_CREATE_ORDER_MENU,
        FORTRESS_VIEW_ORDERS,
        FORTRESS_MY_ORDERS,
        FORTRESS_TAKEN_ORDERS,
        FORTRESS_CREATE_ORDER,
        FORTRESS_CANCEL_CREATE_ORDER,
        FORTRESS_SEEKER_OUTPOST,
        FORTRESS_NOTICE_BOARD,
        FORTRESS_GUILD_AGENT,
        FORTRESS_HIRE,
        FORTRESS_ROAD_TO_CITY,
        FORTRESS_EXIT_GATE,
    }:
        return handle_fortress_action(storage, player, action)
    if action == START_SEARCH:
        return start_search(storage, player, rng)
    if action == SET_CAMP:
        return enter_camp(storage, player)
    if action == BREAK_CAMP:
        return leave_camp(storage, player)
    if action in {COOK_FOOD, SHORT_COOK_FOOD}:
        return show_cooking_menu(storage, player)
    if action in {EAT_FOOD, SHORT_EAT_FOOD}:
        return show_eating_menu(storage, player)
    if action == BACK_TO_CAMP:
        location_id = current_location_id(player)
        player["current_zone"] = f"{location_id}_camp"
        player["location_id"] = f"{location_id}_camp"
        storage.update_player(player)
        return LocationResponse(camp_text(location_id), camp_buttons(), f"{location_id}_camp")
    if action in CAMP_DISHES:
        return cook_dish(storage, player, action)
    if action.startswith("Приготовить: "):
        payload = action.removeprefix("Приготовить: ").strip()
        dish_name, amount = _parse_name_amount(payload)
        if dish_name in CAMP_DISHES:
            return cook_dish(storage, player, dish_name, amount)
    if action.startswith("Съесть: "):
        payload = action.removeprefix("Съесть: ").strip()
        dish_name, amount = _parse_name_amount(payload)
        if dish_name in CAMP_DISHES:
            return eat_dish(storage, player, dish_name, amount)
    if action.startswith("Готовить "):
        dish_name, amount = _parse_numbered_camp_action(action, "Готовить")
        if dish_name in CAMP_DISHES:
            return cook_dish(storage, player, dish_name, amount)
    if action.startswith("Есть "):
        dish_name, amount = _parse_numbered_camp_action(action, "Есть")
        if dish_name in CAMP_DISHES:
            return eat_dish(storage, player, dish_name, amount)
    if action in {COLLECT, SKIP, INSPECT_AND_TAKE, LOOK, LEAVE, RETREAT, COLLECT_TREE, COLLECT_MUSHROOMS, GATHER_WATER, PUT_HAND_IN_BURROW, TAKE_CURSED_COINS}:
        return resolve_active_event(storage, player, action, rng)

    return LocationResponse("Неизвестное действие внешней локации.", current_external_buttons(player), player.get("current_zone", "outside_city_crossroads"))
