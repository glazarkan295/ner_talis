"""External location mechanics for Ner-Talis.

This module converts the uploaded design document for city gates and the
starting location "Холмистые луга" into runnable game logic used by both
Telegram and VK adapters.
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
from services.derived_stats_service import calculate_energy_stats, ensure_player_resources
from services.item_registry import build_inventory_item, get_item_definition_by_name, slugify_fallback_item_id
from services.inventory_service import add_inventory_item as add_inventory_stack, remove_empty_stacks_and_recalculate
from services.pve_battle_service import BATTLE_ACTIONS, battle_buttons, create_hilly_meadows_battle, handle_battle_action
from services.race_bonus_service import extra_alchemy_ingredient_chance_percent, search_event_weights


OUTSIDE_CITY = "Выход из города"
LEGACY_OUTSIDE_CITY = "Выйти к локациям"
RETURN_TO_GATES = "Вернуться к воротам"
RETURN_TO_SELDAR_GATES = "Вернуться к воротам Селдара"
RETURN_TO_CITY = "Вернуться в город"
HILLY_MEADOWS = "Холмистые луга"
FORTRESS_IN_GORGE = "Крепость в ущелье"
SMALL_PLATEAU = "Малое плато"
COMMON_FOREST = "Обыкновенный лес"
START_SEARCH = "Начать поиск"
SET_CAMP = "Разбить лагерь"
COOK_FOOD = "Приготовить еду"
EAT_FOOD = "Съесть еду"
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
RETREAT = "Отступить"
def load_hilly_meadows_config() -> dict[str, Any]:
    path = resolve_project_path("data/hilly_meadows.json")
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


HILLY_MEADOWS_CONFIG = load_hilly_meadows_config()
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
    "Сытная похлёбка": {"restore_energy": 50, "ingredients": {"Чистая вода": 1, "Луговой корень": 1, "Съедобный гриб": 1, "Сырое мясо": 1}},
}

EDIBLE_BERRIES = {"Сладкая луговая ягода", "Терпкая синяя ягода", "Любая съедобная ягода"}

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
}

CAMP_FOOD_CATEGORY = "Еда"
LOCATION_RESOURCE_CATEGORY = "Ресурсы"


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
        SMALL_PLATEAU,
        COMMON_FOREST,
        START_SEARCH,
        SET_CAMP,
        COOK_FOOD,
        EAT_FOOD,
        BREAK_CAMP,
        BACK_TO_CAMP,
        CHECK_TIMER,
        BACK,
        COLLECT,
        SKIP,
        INSPECT_AND_TAKE,
        LOOK,
        LEAVE,
        RETREAT,
        *BATTLE_ACTIONS,
        "Внутренний двор",
        "Доска объявлений",
        "Торговец припасами",
        "Отдых",
        "Маршруты",
        *CAMP_DISHES.keys(),
        *(f"Приготовить: {dish_name} ×1" for dish_name in CAMP_DISHES),
        *(f"Приготовить: {dish_name} ×10" for dish_name in CAMP_DISHES),
        *(f"Съесть: {dish_name}" for dish_name in CAMP_DISHES),
        *(f"Съесть: {dish_name} ×1" for dish_name in CAMP_DISHES),
        *(f"Съесть: {dish_name} ×10" for dish_name in CAMP_DISHES),
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
    player["active_timer"] = None
    player["current_zone"] = "hilly_meadows" if player.get("current_location") == "hilly_meadows" else player.get("current_zone", "outside_city_crossroads")
    player["location_id"] = player["current_zone"]
    player.pop("pending_timer_delivery", None)
    storage.update_player(player)

    if timer_type == "search":
        return LocationResponse(
            "🔎 Вы прекратили поиск. Таймер сброшен, событие не найдено.",
            hilly_meadows_buttons(),
            "hilly_meadows",
        )
    if timer_type == "camp_rest":
        return LocationResponse(
            "⛺ Вы прервали отдых. Таймер сброшен, показатели не восстановлены.",
            camp_buttons(),
            "hilly_meadows_camp",
        )
    return LocationResponse("⏳ Таймер сброшен.", hilly_meadows_buttons(), str(player.get("current_zone") or "hilly_meadows"))


def current_location_back_response(player: dict[str, Any]) -> LocationResponse:
    current_location = str(player.get("current_location") or "")
    if current_location == "hilly_meadows":
        timer = player.get("active_timer")
        extra = ""
        if isinstance(timer, dict) and timer.get("type") == "search":
            remaining = timer_remaining_seconds(timer)
            extra = f"\n\n⏳ Поиск ещё идёт. Осталось: {format_duration(remaining)}. Когда таймер закончится, придёт сообщение с найденным событием."
        return LocationResponse(HILLY_MEADOWS_TEXT + extra, hilly_meadows_buttons(), "hilly_meadows")
    if current_location == "fortress_in_gorge":
        return LocationResponse(FORTRESS_TEXT, fortress_buttons(), "fortress_in_gorge_courtyard")
    return LocationResponse(OUTSIDE_CITY_TEXT, outside_city_buttons(), "outside_city_crossroads")


def event_choice_buttons(event_type: str) -> list[list[str]]:
    if event_type == "alchemy_ingredient":
        return [[COLLECT], [SKIP]]
    if event_type == "stone_or_ore":
        return [[INSPECT_AND_TAKE], [SKIP]]
    if event_type == "berries":
        return [[COLLECT], [SKIP]]
    if event_type == "glint":
        return [[LOOK], [LEAVE]]
    if event_type in {"battle", "battle_preview"}:
        return battle_buttons()
    return hilly_meadows_buttons()


def camp_buttons() -> list[list[str]]:
    return [
        [PROFILE_BUTTON],
        [COOK_FOOD, EAT_FOOD],
        [BREAK_CAMP],
    ]


def cook_buttons(player: dict[str, Any] | None = None) -> list[list[str]]:
    rows: list[list[str]] = []
    for dish_name in CAMP_DISHES:
        row = [f"Приготовить: {dish_name} ×1"]
        if player is not None and available_craft_count(player, dish_name) >= 10:
            row.append(f"Приготовить: {dish_name} ×10")
        rows.append(row)
    rows.append([BACK_TO_CAMP])
    return rows


def eat_buttons(player: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for name in CAMP_DISHES:
        count = get_item_count(player, name)
        if count <= 0:
            continue
        if count > 10:
            rows.append([f"Съесть: {name} ×1", f"Съесть: {name} ×10"])
        else:
            rows.append([f"Съесть: {name} ×1"])
    rows.append([BACK_TO_CAMP])
    return rows


def fortress_buttons() -> list[list[str]]:
    return [
        ["Внутренний двор", "Доска объявлений"],
        ["Торговец припасами", "Отдых"],
        ["Маршруты"],
        [RETURN_TO_SELDAR_GATES],
    ]


OUTSIDE_CITY_TEXT = """🗺 Выход из города

Покинув безопасные стены Селдара, вы оказываетесь на развилке. Дороги ведут к ближайшим землям, где можно искать травы, руду, дичь и случайные находки.

Доступные направления:
• Малое плато
• Обыкновенный лес
• Холмистые луга
• Крепость в ущелье"""

HILLY_MEADOWS_TEXT = """🌿 Холмистые луга

Перед вами раскинулись Холмистые луга. Невысокие зелёные холмы тянутся до самого горизонта, трава колышется под ветром, а между склонами прячутся цветы, ягоды, звериные норы и случайные следы чужих путников.

Поиск тратит энергию и запускает случайное событие."""

FORTRESS_TEXT = """🏰 Крепость в ущелье

Крепость в ущелье — безопасная внешняя зона и перевалочный пункт. Здесь не запускаются обычные случайные боевые события и не используется стандартное меню внешних локаций.

Доступно:
• внутренний двор;
• доска объявлений;
• торговец припасами;
• отдых;
• маршруты."""

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


def available_craft_count(player: dict[str, Any], dish_name: str) -> int:
    dish = CAMP_DISHES[dish_name]
    counts: list[int] = []
    for ingredient, amount in dish["ingredients"].items():
        if ingredient == "Любая съедобная ягода":
            available = sum(get_item_count(player, berry) for berry in EDIBLE_BERRIES)
        else:
            available = get_item_count(player, ingredient)
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


def add_item(player: dict[str, Any], name: str, amount: int, *, item_id: str | None = None, max_stack: int = 999):
    if amount <= 0:
        return add_inventory_stack(player, name, 0)

    inventory_item = build_inventory_item(name, amount, item_id=item_id, max_stack=max_stack)
    apply_location_item_category(inventory_item, name)
    inventory_item.setdefault("source", "Холмистые луга")
    inventory_item.setdefault("actions", [])
    return add_inventory_stack(
        player,
        inventory_item,
        amount,
        item_id=str(inventory_item.get("id") or inventory_item.get("item_id") or slugify_item_name(name)),
        max_stack=int(inventory_item.get("max_stack", max_stack) or max_stack),
        default_source="Холмистые луга",
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
    if name == "Любая съедобная ягода":
        return sum(get_item_count(player, berry) for berry in EDIBLE_BERRIES) >= amount
    return get_item_count(player, name) >= amount


def consume_ingredient(player: dict[str, Any], name: str, amount: int) -> bool:
    if name != "Любая съедобная ягода":
        return remove_item(player, name, amount)

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
    player["current_city"] = "outside_seldar"
    player["current_zone"] = "hilly_meadows"
    player["location_id"] = "hilly_meadows"
    player["current_location"] = "hilly_meadows"
    player["active_event"] = None
    player["active_timer"] = None
    storage.update_player(player)
    return LocationResponse(HILLY_MEADOWS_TEXT, hilly_meadows_buttons(), "hilly_meadows")


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
    if player.get("current_location") != "hilly_meadows":
        return LocationResponse("Лагерь можно разбить только в обычной внешней локации.", hilly_meadows_buttons(), player.get("current_zone", "hilly_meadows"))
    if player.get("active_event"):
        return LocationResponse("Сначала завершите текущее событие.", event_choice_buttons(player["active_event"].get("type", "")), player.get("current_zone", "hilly_meadows"))
    if player.get("in_battle"):
        return LocationResponse("Нельзя разбить лагерь во время боя.", hilly_meadows_buttons(), player.get("current_zone", "hilly_meadows"))

    rest_time = calculate_scaled_seconds(int(player.get("energy", 100)), int(player.get("max_energy", 100)), 30, 600)
    timer = {
        "id": new_timer_id("camp_rest"),
        "type": "camp_rest",
        "seconds": rest_time,
        "ends_at": now_ts() + rest_time,
        "location_id": "hilly_meadows_camp",
    }
    player["current_zone"] = "hilly_meadows_camp"
    player["location_id"] = "hilly_meadows_camp"
    player["active_timer"] = timer
    storage.update_player(player)
    hp, max_hp = hp_pair(player)
    text = (
        f"{CAMP_TEXT}\n\n"
        "🛏 Отдых начался.\n"
        f"⏳ Время отдыха: {format_duration(rest_time)}\n"
        f"❤️ Жизни сейчас: {hp}/{max_hp}\n\n"
        "Если свернуть лагерь раньше окончания отдыха, восстановление не сработает."
    )
    return LocationResponse(text, camp_buttons(), "hilly_meadows_camp", scheduled_timer=build_timer_schedule(player, timer))


def leave_camp(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    player["current_zone"] = "hilly_meadows"
    player["location_id"] = "hilly_meadows"
    was_resting = isinstance(player.get("active_timer"), dict) and player["active_timer"].get("type") == "camp_rest"
    player["active_timer"] = None
    storage.update_player(player)
    if was_resting:
        return LocationResponse("⛺ Вы свернули лагерь раньше окончания отдыха. Таймер сброшен, показатели не восстановлены.", hilly_meadows_buttons(), "hilly_meadows")
    return LocationResponse("⛺ Вы сворачиваете лагерь и возвращаетесь к тропам Холмистых лугов.", hilly_meadows_buttons(), "hilly_meadows")


def return_to_gates(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    if player.get("in_battle"):
        return LocationResponse("Нельзя вернуться к воротам во время боя.", hilly_meadows_buttons(), player.get("current_zone", "hilly_meadows"))
    if player.get("active_event"):
        event_type = player["active_event"].get("type", "")
        return LocationResponse("Сначала завершите активное событие.", event_choice_buttons(event_type), player.get("current_zone", "hilly_meadows"))
    if player.get("active_timer"):
        return LocationResponse("Сначала завершите текущее действие с таймером.", hilly_meadows_buttons(), player.get("current_zone", "hilly_meadows"))

    player["current_city"] = "seldar"
    player["current_zone"] = "seldar_city_gates"
    player["location_id"] = "seldar_city_gates"
    player["current_location"] = None
    player["active_event"] = None
    storage.update_player(player)
    text = "🚪 Вы возвращаетесь к стенам Селдара. После открытых лугов городские ворота кажутся особенно надёжными."
    return LocationResponse(text, [[OUTSIDE_CITY], ["⬅️ Центральная площадь"]], "seldar_city_gates")


def start_search(storage: Any, player: dict[str, Any], rng: random.Random | None = None) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)
    if player.get("current_location") != "hilly_meadows":
        return LocationResponse("Поиск сейчас доступен только в Холмистых лугах.", outside_city_buttons(), player.get("current_zone", "outside_city_crossroads"))
    if player.get("in_battle"):
        return LocationResponse("Нельзя начать новый поиск во время боя.", hilly_meadows_buttons(), "hilly_meadows")
    if player.get("active_event"):
        event_type = player["active_event"].get("type", "")
        return LocationResponse("Сначала завершите текущее событие.", event_choice_buttons(event_type), "hilly_meadows")
    if isinstance(player.get("active_timer"), dict):
        remaining = timer_remaining_seconds(player.get("active_timer"))
        if remaining > 0:
            return LocationResponse(
                f"⏳ Уже идёт действие с таймером. Осталось: {format_duration(remaining)}.",
                search_timer_buttons(),
                player.get("current_zone", "hilly_meadows"),
            )
        return complete_active_timer(storage, player, player.get("active_timer", {}).get("id"), rng)
    if not has_equipped_attack_skill(player):
        return missing_attack_skill_response(player)

    energy_stats = calculate_energy_stats(player)
    energy = int(energy_stats["current_energy"])
    max_energy = int(energy_stats["max_energy"])
    if energy <= 0:
        player["last_zero_energy_search"] = True

    seconds = calculate_scaled_seconds(energy, max_energy, BASE_SEARCH_TIME_SECONDS, MAX_SEARCH_TIME_SECONDS)
    cost = min(SEARCH_ENERGY_COST, energy)
    player["energy"] = max(0, energy - cost)
    player["current_energy"] = player["energy"]
    player["last_search_time_seconds"] = seconds

    event_type = weighted_choice(search_event_weights(player, BASE_SEARCH_EVENT_WEIGHTS), rng)

    payload: dict[str, Any]
    if event_type == "trap":
        payload = {"type": "trap"}
    elif event_type == "battle":
        payload = {"type": "battle"}
    else:
        payload = create_search_event(event_type, rng)

    timer = {
        "id": new_timer_id("search"),
        "type": "search",
        "seconds": seconds,
        "ends_at": now_ts() + seconds,
        "energy_spent": cost,
        "event": payload,
        "location_id": "hilly_meadows",
    }
    player["active_timer"] = timer
    warnings = collect_energy_warning_messages(player)
    storage.update_player(player)
    hp, max_hp = hp_pair(player)
    lines = [
        "🔎 Поиск начался",
        "━━━━━━━━━━━━",
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
        "hilly_meadows_search",
        scheduled_timer=build_timer_schedule(player, timer),
    )


def complete_active_timer(storage: Any, player: dict[str, Any], timer_id: str | None = None, rng: random.Random | None = None) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)
    timer = player.get("active_timer")
    if not isinstance(timer, dict):
        return LocationResponse("⏳ Активного таймера нет.", hilly_meadows_buttons(), player.get("current_zone", "hilly_meadows"))
    if timer_id and timer.get("id") != timer_id:
        return LocationResponse("⏳ Этот таймер уже неактуален.", hilly_meadows_buttons(), player.get("current_zone", "hilly_meadows"))
    remaining = timer_remaining_seconds(timer)
    if remaining > 0:
        return LocationResponse(
            f"⏳ Таймер ещё идёт. Осталось: {format_duration(remaining)}.",
            search_timer_buttons(),
            player.get("current_zone", "hilly_meadows"),
        )

    timer_type = timer.get("type")
    if timer_type == "camp_rest":
        for current_key, max_key in (("hp", "max_hp"), ("mana", "max_mana"), ("spirit", "max_spirit")):
            if player.get(max_key) is not None:
                player[current_key] = player[max_key]
        player["active_timer"] = None
        storage.update_player(player)
        return LocationResponse(
            "✅ Отдых завершён.\n\n❤️ Жизни, ✨ мана и 🔥 дух восстановлены до максимума.",
            camp_buttons(),
            "hilly_meadows_camp",
        )

    if timer_type != "search":
        player["active_timer"] = None
        storage.update_player(player)
        return LocationResponse("⏳ Неизвестный таймер завершён и был очищен.", hilly_meadows_buttons(), "hilly_meadows")

    event = timer.get("event") or {}
    event_type = event.get("type")
    player["active_timer"] = None
    player["current_zone"] = "hilly_meadows"
    player["location_id"] = "hilly_meadows"

    if event_type == "trap":
        text = resolve_trap(player, rng)
        warnings = collect_energy_warning_messages(player)
        storage.update_player(player)
        extra = "\n\n" + "\n".join(warnings) if warnings else ""
        return LocationResponse(f"✅ Поиск завершён.\n\n{text}{extra}", hilly_meadows_buttons(), "hilly_meadows")

    if event_type == "battle":
        _battle, battle_text = create_hilly_meadows_battle(player, rng)
        storage.update_player(player)
        return LocationResponse(f"✅ Поиск завершён.\n\n{battle_text}", battle_buttons(player), "hilly_meadows_battle")

    player["active_event"] = event
    storage.update_player(player)
    return LocationResponse(
        f"✅ Поиск завершён.\n\n{event.get('text', 'Вы нашли событие.')}",
        event_choice_buttons(str(event_type or "")),
        "hilly_meadows",
    )


def create_search_event(event_type: str, rng: random.Random) -> dict[str, Any]:
    if event_type == "alchemy_ingredient":
        return {
            "type": "alchemy_ingredient",
            "text": rng.choice(
                [
                    "🌱 На вершине холма среди бесконечной травы вы замечаете несколько растений, чуть отличающихся от остальных. Их стебли плотнее, а листья имеют необычный оттенок.",
                    "🌼 На склоне холма из высокой травы выглядывает небольшой цветок. Он едва заметен, но его запах выбивается из обычного лугового аромата.",
                ]
            ),
        }
    if event_type == "stone_or_ore":
        return {
            "type": "stone_or_ore",
            "text": "🪨 У подножья холма вы замечаете подозрительный камень. Он выделяется среди обычной россыпи и выглядит так, будто его недавно вымыло дождём из земли.",
        }
    if event_type == "berries":
        return {
            "type": "berries",
            "text": "🫐 В низине между холмами вы замечаете кустик ягод. С виду они съедобные, хотя проверять это лучше осторожно.",
        }
    if event_type == "glint":
        variant = weighted_choice([("old_knife_up_slope", 50), ("search_traces_down_slope", 50)], rng)
        if variant == "old_knife_up_slope":
            text = "✨ Выйдя на солнечную сторону холма, вы замечаете короткий блик чуть выше по склону."
        else:
            text = "✨ Выйдя на солнечную сторону холма, вы замечаете короткий блик чуть ниже по склону."
        return {"type": "glint", "variant": variant, "text": text}
    raise ValueError(f"Unknown event type: {event_type}")


def resolve_trap(player: dict[str, Any], rng: random.Random) -> str:
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


def resolve_active_event(storage: Any, player: dict[str, Any], action: str, rng: random.Random | None = None) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)
    event = player.get("active_event")
    if not event:
        storage.update_player(player)
        return LocationResponse("Активного события нет.", hilly_meadows_buttons(), "hilly_meadows")

    event_type = event.get("type")

    if action in {SKIP, LEAVE, RETREAT}:
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse("Вы оставляете событие позади и продолжаете путь по Холмистым лугам.", hilly_meadows_buttons(), "hilly_meadows")

    if event_type == "alchemy_ingredient" and action == COLLECT:
        loot_name = rng.choice(["Луговая мята", "Серебристая ромашка", "Жёлтый клевер", "Горная полынь", "Луговой корень"])
        amount = rng.randint(1, 2)
        extra_chance = extra_alchemy_ingredient_chance_percent(player)
        got_extra = bool(extra_chance and rng.uniform(0, 100) <= extra_chance)
        if got_extra:
            amount += 1
        add_result = add_item(player, loot_name, amount)
        amount = add_result.added
        player["active_event"] = None
        storage.update_player(player)
        extra_text = "\n🧝 Знание трав помогло найти дополнительный ингредиент." if got_extra else ""
        return LocationResponse(f"Вы аккуратно собираете растение и убираете его в сумку. Получено: {loot_name} ×{amount}.{extra_text}", hilly_meadows_buttons(), "hilly_meadows")

    if event_type == "stone_or_ore" and action == INSPECT_AND_TAKE:
        result = weighted_choice([("Обычный камень", 92), ("Кусок медной руды", 5), ("Кусок железной руды", 3)], rng)
        amount = rng.randint(1, 3) if result == "Обычный камень" else rng.randint(1, 2)
        add_result = add_item(player, result, amount)
        amount = add_result.added
        player["active_event"] = None
        storage.update_player(player)
        if result == "Обычный камень":
            text = f"Это оказался самый обычный камень. Ничего ценного, но в хозяйстве может пригодиться. Получено: {result} ×{amount}."
        else:
            text = f"При осмотре вы замечаете металлические прожилки. Это не простой камень, а небольшой кусок руды. Получено: {result} ×{amount}."
        return LocationResponse(text, hilly_meadows_buttons(), "hilly_meadows")

    if event_type == "berries" and action == COLLECT:
        loot_name = rng.choice(["Сладкая луговая ягода", "Терпкая синяя ягода"])
        amount = rng.randint(2, 5)
        add_result = add_item(player, loot_name, amount)
        amount = add_result.added
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse(f"Вы собираете ягоды с нижних веток куста, стараясь не раздавить самые спелые. Получено: {loot_name} ×{amount}.", hilly_meadows_buttons(), "hilly_meadows")

    if event_type == "glint" and action == LOOK:
        response = resolve_glint_event(player, event, rng)
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse(response, hilly_meadows_buttons(), "hilly_meadows")

    return LocationResponse("Выберите действие кнопкой события.", event_choice_buttons(event_type or ""), "hilly_meadows")


def resolve_glint_event(player: dict[str, Any], event: dict[str, Any], rng: random.Random) -> str:
    variant = event.get("variant")
    if variant == "old_knife_up_slope":
        result = weighted_choice([("Железный лом", 70), ("Старый нож", 30)], rng)
        add_result = add_item(player, result, 1)
        if add_result.added <= 0:
            return "Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. Но места в инвентаре нет, и забрать находку некуда."
        if result == "Железный лом":
            return "Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. Скорее всего, кто-то пытался замедлить спуск вниз по траве, но вышло не слишком удачно.\n\nОсмотрев находку, вы понимаете, что это почти полный хлам, пригодный только на переплавку. Получено: Железный лом ×1."
        return "Поднявшись выше по склону, вы замечаете нож, воткнутый в землю. Скорее всего, кто-то пытался замедлить спуск вниз по траве, но вышло не слишком удачно.\n\nНож в сносном состоянии, но для боя почти не годится. Его можно продать или разобрать. Получено: Старый нож ×1."

    result = weighted_choice([("copper", 75), ("silver", 2), ("nothing", 23)], rng)
    if result == "copper":
        amount = rng.randint(1, 10)
        player["money_copper"] = int(player.get("money_copper", player.get("money", 0)) or 0) + amount
        player["money"] = player["money_copper"]
        return f"Спустившись ниже по склону, вы видите примятую и разбросанную вырванную траву. Похоже, здесь кто-то что-то потерял и долго пытался найти.\n\nНемного поискав в траве, вы находите несколько монет. Видимо, именно их здесь и искали. Получено: медные монеты ×{amount}."
    if result == "silver":
        player["money_copper"] = int(player.get("money_copper", player.get("money", 0)) or 0) + 1000
        player["money"] = player["money_copper"]
        return "Спустившись ниже по склону, вы видите примятую и разбросанную вырванную траву. Похоже, здесь кто-то что-то потерял и долго пытался найти.\n\nСреди примятой травы блестит одна серебряная монета. Странно, что её не заметили раньше. Получено: серебряная монета ×1."
    return "Спустившись ниже по склону, вы видите примятую и разбросанную вырванную траву. Похоже, здесь кто-то что-то потерял и долго пытался найти.\n\nВы тратите немного времени на поиски, но ничего не находите. Видимо, тот, кто искал до вас, всё-таки нашёл пропажу."


def show_cooking_menu(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    player["current_zone"] = "hilly_meadows_camp_cooking"
    storage.update_player(player)
    recipe_lines = ["🔥 Готовка в лагере", "", "Выберите простое лагерное блюдо:"]
    for dish_name, data in CAMP_DISHES.items():
        ingredients = "; ".join(f"{name} ×{amount}" for name, amount in data["ingredients"].items())
        can_craft = available_craft_count(player, dish_name)
        mark = "✅" if can_craft > 0 else "❌"
        recipe_lines.append(f"{mark} {dish_name}: {ingredients}. ⚡ Энергия +{data['restore_energy']}. Можно приготовить: {can_craft}.")
    return LocationResponse("\n".join(recipe_lines), cook_buttons(player), "hilly_meadows_camp_cooking")


def cook_dish(storage: Any, player: dict[str, Any], dish_name: str, amount: int = 1) -> LocationResponse:
    ensure_external_fields(player)
    amount = max(1, min(10, int(amount or 1)))
    dish = CAMP_DISHES[dish_name]
    missing = [f"{name} ×{needed * amount}" for name, needed in dish["ingredients"].items() if not has_ingredient(player, name, needed * amount)]
    if missing:
        return LocationResponse("У вас не хватает простых ингредиентов для этого блюда.\n\nНе хватает: " + ", ".join(missing), cook_buttons(player), "hilly_meadows_camp_cooking")
    for name, needed in dish["ingredients"].items():
        consume_ingredient(player, name, needed * amount)
    add_result = add_item(player, dish_name, amount, item_id=slugify_item_name(dish_name), max_stack=20)
    storage.update_player(player)
    if add_result.added <= 0:
        return LocationResponse(
            "🔥 Вы приготовили походное блюдо, но в инвентаре нет места. Блюдо пришлось оставить у костра.",
            cook_buttons(player),
            "hilly_meadows_camp_cooking",
        )
    extra = f"\n🎒 В доп. слот попало: ×{add_result.added_to_overflow}." if add_result.added_to_overflow else ""
    return LocationResponse(f"🔥 Вы готовите походное блюдо на маленьком костре.\nПолучено: {dish_name} ×{add_result.added}.{extra}", cook_buttons(player), "hilly_meadows_camp_cooking")


def show_eating_menu(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    player["current_zone"] = "hilly_meadows_camp_eating"
    storage.update_player(player)
    lines = ["🍽 Еда в лагере", ""]
    has_food = False
    for dish_name, data in CAMP_DISHES.items():
        count = get_item_count(player, dish_name)
        if count > 0:
            has_food = True
            lines.append(f"• {dish_name} ×{count} — восстановит {data['restore_energy']} энергии")
    if not has_food:
        lines.append("В инвентаре нет готовых лагерных блюд.")
    return LocationResponse("\n".join(lines), eat_buttons(player), "hilly_meadows_camp_eating")


def eat_dish(storage: Any, player: dict[str, Any], dish_name: str, amount: int = 1) -> LocationResponse:
    ensure_external_fields(player)
    amount = max(1, min(10, int(amount or 1)))
    dish = CAMP_DISHES[dish_name]
    if not remove_item(player, dish_name, amount):
        return LocationResponse("Такого блюда нет в инвентаре.", eat_buttons(player), "hilly_meadows_camp_eating")
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
    return LocationResponse(f"🍽 Вы использовали {dish_name} ×{amount}.\n⚡ Энергия восстановлена: +{actual}. Сейчас: {player['energy']}/{max_energy}.", eat_buttons(player), "hilly_meadows_camp_eating")


def handle_fortress_action(storage: Any, player: dict[str, Any], action: str) -> LocationResponse:
    ensure_external_fields(player)
    player["current_location"] = "fortress_in_gorge"
    player["current_city"] = "outside_seldar"
    mapping = {
        "Внутренний двор": "🏰 Внутренний двор крепости\n\nВо дворе спокойно. Здесь можно передохнуть, проверить снаряжение и подготовиться к будущим маршрутам.",
        "Доска объявлений": "📜 Доска объявлений крепости\n\nПока объявлений нет. Позже здесь появятся задания перевалочного пункта и сообщения о маршрутах.",
        "Торговец припасами": "🎒 Торговец припасами\n\nТорговец сможет продавать простые припасы для дороги: воду, грубую муку, недорогие ягоды и другие обычные вещи. Полная торговля будет подключена позже.",
        "Отдых": "🛏 Отдых в крепости\n\nКрепость безопасна, поэтому отдых здесь работает ближе к городскому. Полная механика восстановления будет подключена отдельным модулем.",
        "Маршруты": "🧭 Маршруты\n\nКрепость станет перевалочным пунктом к будущим дальним территориям. Пока доступен возврат к воротам Селдара.",
    }
    player["current_zone"] = "fortress_in_gorge_" + slugify_item_name(action).removeprefix("item_")
    player["location_id"] = player["current_zone"]
    storage.update_player(player)
    return LocationResponse(mapping.get(action, FORTRESS_TEXT), fortress_buttons(), player["current_zone"])


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


def _is_equipped_skill_action(player: dict[str, Any], action: str) -> bool:
    skills = player.get("skills") or {}
    for skill in skills.get("equipped", []) if isinstance(skills, dict) else []:
        if isinstance(skill, dict) and str(skill.get("name") or skill.get("id") or "") == action:
            return True
    return False


def _equipped_attack_skills(player: dict[str, Any]) -> list[dict[str, Any]]:
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
        "hilly_meadows",
    )


def handle_external_location_action(
    storage: Any,
    player: dict[str, Any],
    action: str,
    rng: random.Random | None = None,
) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)

    if player.get("in_battle"):
        if action in BATTLE_ACTIONS or action.startswith("Цель: ") or action.startswith("Использовать: ") or _is_equipped_skill_action(player, action):
            text, buttons = handle_battle_action(player, action, rng)
            storage.update_player(player)
            return LocationResponse(text, buttons or hilly_meadows_buttons(), player.get("current_zone", "hilly_meadows"))
        return LocationResponse("⚔️ Сейчас вы в бою. Сначала завершите бой или сбегите.", battle_buttons(player), player.get("current_zone", "hilly_meadows_battle"))

    if isinstance(player.get("active_timer"), dict):
        active_timer = player.get("active_timer") or {}
        if action == BACK:
            return cancel_active_timer(storage, player)
        if action == CHECK_TIMER:
            return complete_active_timer(storage, player, active_timer.get("id"), rng)
        if timer_remaining_seconds(active_timer) <= 0:
            return complete_active_timer(storage, player, active_timer.get("id"), rng)
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
    if action in {SMALL_PLATEAU, COMMON_FOREST}:
        player["current_city"] = "outside_seldar"
        player["current_zone"] = "outside_city_crossroads"
        player["location_id"] = "outside_city_crossroads"
        player["current_location"] = None
        storage.update_player(player)
        return LocationResponse(PLACEHOLDER_LOCATION_TEXT, outside_city_buttons(), "outside_city_crossroads")
    if action == FORTRESS_IN_GORGE:
        return enter_fortress(storage, player)
    if action in {"Внутренний двор", "Доска объявлений", "Торговец припасами", "Отдых", "Маршруты"}:
        return handle_fortress_action(storage, player, action)
    if action == START_SEARCH:
        return start_search(storage, player, rng)
    if action == SET_CAMP:
        return enter_camp(storage, player)
    if action == BREAK_CAMP:
        return leave_camp(storage, player)
    if action == COOK_FOOD:
        return show_cooking_menu(storage, player)
    if action == EAT_FOOD:
        return show_eating_menu(storage, player)
    if action == BACK_TO_CAMP:
        player["current_zone"] = "hilly_meadows_camp"
        player["location_id"] = "hilly_meadows_camp"
        storage.update_player(player)
        return LocationResponse(CAMP_TEXT, camp_buttons(), "hilly_meadows_camp")
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
    if action in {COLLECT, SKIP, INSPECT_AND_TAKE, LOOK, LEAVE, RETREAT}:
        return resolve_active_event(storage, player, action, rng)

    return LocationResponse("Неизвестное действие внешней локации.", outside_city_buttons(), player.get("current_zone", "outside_city_crossroads"))
