"""External location mechanics for Ner-Talis.

This module converts the uploaded design document for city gates and the
starting location "Холмистые луга" into runnable game logic used by both
Telegram and VK adapters.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Iterable

from services.item_registry import build_inventory_item, get_item_definition_by_name, slugify_fallback_item_id
from services.pve_battle_service import BATTLE_ACTIONS, battle_buttons, create_hilly_meadows_battle, handle_battle_action


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
COLLECT = "Собрать"
SKIP = "Пропустить"
INSPECT_AND_TAKE = "Осмотреть и забрать"
LOOK = "Посмотреть"
LEAVE = "Уйти"
RETREAT = "Отступить"

CAMP_DISHES = {
    "Сушёное мясо": {
        "restore_energy": 7,
        "ingredients": {"Сырое мясо": 1},
    },
    "Травяной чай": {
        "restore_energy": 20,
        "ingredients": {"Чистая вода": 1, "Любая съедобная ягода": 1, "Луговая мята": 1},
    },
    "Лепёшка с мясом": {
        "restore_energy": 35,
        "ingredients": {"Чистая вода": 1, "Сырое мясо": 1, "Грубая мука": 1},
    },
    "Сытная похлёбка": {
        "restore_energy": 50,
        "ingredients": {
            "Чистая вода": 1,
            "Съедобный корень": 1,
            "Съедобный гриб": 1,
            "Сырое мясо": 1,
        },
    },
}

EDIBLE_BERRIES = {"Сладкая луговая ягода", "Терпкая синяя ягода", "Любая съедобная ягода"}

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
        *(f"Съесть: {dish_name}" for dish_name in CAMP_DISHES),
    }
)


@dataclass(frozen=True)
class LocationResponse:
    text: str
    buttons: list[list[str]]
    zone_id: str


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
        [COOK_FOOD, EAT_FOOD],
        [BREAK_CAMP],
    ]


def cook_buttons() -> list[list[str]]:
    return [
        ["Сушёное мясо", "Травяной чай"],
        ["Лепёшка с мясом"],
        ["Сытная похлёбка"],
        [BACK_TO_CAMP],
    ]


def eat_buttons(player: dict[str, Any]) -> list[list[str]]:
    dishes = [name for name in CAMP_DISHES if get_item_count(player, name) > 0]
    rows = [[f"Съесть: {name}"] for name in dishes]
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

Покинув безопасные стены Селдара, вы оказываетесь на развилке. Дороги ведут к ближайшим землям, где можно искать травы, руду, дичь, случайные находки и опасности.

Доступные направления:
• Малое плато
• Обыкновенный лес
• Холмистые луга
• Крепость в ущелье"""

HILLY_MEADOWS_TEXT = """🌿 Холмистые луга

Перед вами раскинулись Холмистые луга. Невысокие зелёные холмы тянутся до самого горизонта, трава колышется под ветром, а между склонами прячутся цветы, ягоды, звериные норы и случайные следы чужих путников.

Опасность: низкая.
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
    max_energy = max(1, max_energy)
    ratio = min(1.0, max(0.0, current_energy / max_energy))
    return min(maximum, max(base, math.ceil(base + (maximum - base) * ((1 - ratio) ** 1.35))))


def add_item(player: dict[str, Any], name: str, amount: int, *, item_id: str | None = None, max_stack: int = 999) -> None:
    if amount <= 0:
        return

    inventory_item = build_inventory_item(name, amount, item_id=item_id, max_stack=max_stack)
    item_id = str(inventory_item.get("id") or inventory_item.get("item_id") or slugify_item_name(name))
    max_stack = int(inventory_item.get("max_stack", max_stack) or max_stack)
    remaining = amount
    inventory = player.setdefault("inventory", [])

    for item in inventory:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or item.get("item_id")) != item_id:
            continue
        current_amount = int(item.get("amount", 1) or 1)
        free = max_stack - current_amount
        if free <= 0:
            continue
        added = min(free, remaining)
        item["amount"] = current_amount + added
        # Backfill visual metadata for old stacks.
        for key in ("icon", "asset_icon", "category", "type", "subtype", "quality", "max_stack", "stackable"):
            if inventory_item.get(key) is not None:
                item.setdefault(key, inventory_item.get(key))
        remaining -= added
        if remaining <= 0:
            return

    while remaining > 0:
        added = min(max_stack, remaining)
        item = build_inventory_item(name, added, item_id=item_id, max_stack=max_stack)
        item.setdefault("source", "Холмистые луга")
        item.setdefault("actions", [])
        inventory.append(item)
        remaining -= added

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
            return True
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
    player["current_zone"] = "hilly_meadows_camp"
    player["location_id"] = "hilly_meadows_camp"
    player["active_timer"] = {"type": "camp_rest", "seconds": rest_time}
    for current_key, max_key in (("hp", "max_hp"), ("mana", "max_mana"), ("spirit", "max_spirit")):
        if player.get(max_key) is not None:
            player[current_key] = player[max_key]
    player["active_timer"] = None
    storage.update_player(player)
    return LocationResponse(f"{CAMP_TEXT}\n\nВремя отдыха по текущей энергии: {rest_time} сек.", camp_buttons(), "hilly_meadows_camp")


def leave_camp(storage: Any, player: dict[str, Any]) -> LocationResponse:
    ensure_external_fields(player)
    player["current_zone"] = "hilly_meadows"
    player["location_id"] = "hilly_meadows"
    player["active_timer"] = None
    storage.update_player(player)
    return LocationResponse("Вы сворачиваете лагерь и возвращаетесь к тропам Холмистых лугов.", hilly_meadows_buttons(), "hilly_meadows")


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

    energy = int(player.get("energy", 0) or 0)
    max_energy = int(player.get("max_energy", 100) or 100)
    if energy < 1:
        return LocationResponse("Недостаточно энергии даже для минимального поиска. Съешьте блюдо или восстановитесь другим способом.", hilly_meadows_buttons(), "hilly_meadows")

    seconds = calculate_scaled_seconds(energy, max_energy, 60, 600)
    cost = 4 if energy >= 4 else 1
    player["energy"] = max(0, energy - cost)
    player["current_energy"] = player["energy"]
    player["last_search_time_seconds"] = seconds

    event_type = weighted_choice(
        [
            ("alchemy_ingredient", 25),
            ("stone_or_ore", 17),
            ("berries", 20),
            ("trap", 10),
            ("glint", 8),
            ("battle", 20),
        ],
        rng,
    )

    if event_type == "trap":
        text = resolve_trap(player, rng)
        storage.update_player(player)
        return LocationResponse(f"🔎 Поиск занял примерно {seconds} сек. Потрачено энергии: {cost}.\n\n{text}", hilly_meadows_buttons(), "hilly_meadows")

    if event_type == "battle":
        _battle, battle_text = create_hilly_meadows_battle(player, rng)
        storage.update_player(player)
        return LocationResponse(
            f"🔎 Поиск занял примерно {seconds} сек. Потрачено энергии: {cost}.\n\n{battle_text}",
            battle_buttons(),
            "hilly_meadows_battle",
        )

    event = create_search_event(event_type, rng)
    player["active_event"] = event
    storage.update_player(player)
    return LocationResponse(
        f"🔎 Поиск занял примерно {seconds} сек. Потрачено энергии: {cost}.\n\n{event['text']}",
        event_choice_buttons(event_type),
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
        return f"🕳 Вы не замечаете яму, скрытую высокой травой, и проваливаетесь в неё почти по пояс. Выбираясь наружу, вы сильно ударяетесь о край. Потеряно: HP -{loss}."

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
        add_item(player, loot_name, amount)
        player["active_event"] = None
        storage.update_player(player)
        return LocationResponse(f"Вы аккуратно собираете растение и убираете его в сумку. Получено: {loot_name} ×{amount}.", hilly_meadows_buttons(), "hilly_meadows")

    if event_type == "stone_or_ore" and action == INSPECT_AND_TAKE:
        result = weighted_choice([("Обычный камень", 92), ("Кусок медной руды", 5), ("Кусок железной руды", 3)], rng)
        amount = rng.randint(1, 3) if result == "Обычный камень" else rng.randint(1, 2)
        add_item(player, result, amount)
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
        add_item(player, loot_name, amount)
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
        add_item(player, result, 1)
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
        recipe_lines.append(f"• {dish_name}: {ingredients}. Энергия +{data['restore_energy']}.")
    return LocationResponse("\n".join(recipe_lines), cook_buttons(), "hilly_meadows_camp_cooking")


def cook_dish(storage: Any, player: dict[str, Any], dish_name: str) -> LocationResponse:
    ensure_external_fields(player)
    dish = CAMP_DISHES[dish_name]
    missing = [f"{name} ×{amount}" for name, amount in dish["ingredients"].items() if not has_ingredient(player, name, amount)]
    if missing:
        return LocationResponse("У вас не хватает простых ингредиентов для этого блюда.\n\nНе хватает: " + ", ".join(missing), cook_buttons(), "hilly_meadows_camp_cooking")
    for name, amount in dish["ingredients"].items():
        consume_ingredient(player, name, amount)
    add_item(player, dish_name, 1, item_id=slugify_item_name(dish_name), max_stack=20)
    storage.update_player(player)
    return LocationResponse(f"Вы готовите простое походное блюдо на маленьком костре. Получено: {dish_name} ×1.", cook_buttons(), "hilly_meadows_camp_cooking")


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


def eat_dish(storage: Any, player: dict[str, Any], dish_name: str) -> LocationResponse:
    ensure_external_fields(player)
    dish = CAMP_DISHES[dish_name]
    if not remove_item(player, dish_name, 1):
        return LocationResponse("Такого блюда нет в инвентаре.", eat_buttons(player), "hilly_meadows_camp_eating")
    before = int(player.get("energy", 0) or 0)
    restored = int(dish["restore_energy"])
    player["energy"] = min(int(player.get("max_energy", 100) or 100), before + restored)
    player["current_energy"] = player["energy"]
    actual = player["energy"] - before
    storage.update_player(player)
    return LocationResponse(f"Вы съели {dish_name}. Энергия восстановлена: +{actual}.", eat_buttons(player), "hilly_meadows_camp_eating")


def handle_fortress_action(storage: Any, player: dict[str, Any], action: str) -> LocationResponse:
    ensure_external_fields(player)
    player["current_location"] = "fortress_in_gorge"
    player["current_city"] = "outside_seldar"
    mapping = {
        "Внутренний двор": "🏰 Внутренний двор крепости\n\nВо дворе спокойно. Здесь можно передохнуть, проверить снаряжение и подготовиться к будущим маршрутам.",
        "Доска объявлений": "📜 Доска объявлений крепости\n\nПока объявлений нет. Позже здесь появятся задания перевалочного пункта и сообщения о маршрутах.",
        "Торговец припасами": "🎒 Торговец припасами\n\nТорговец сможет продавать простые припасы для дороги: воду, грубую муку, недорогие ягоды и другие обычные вещи. Полная торговля будет подключена позже.",
        "Отдых": "🛏 Отдых в крепости\n\nКрепость безопасна, поэтому отдых здесь работает ближе к городскому. Полная механика восстановления будет подключена отдельным модулем.",
        "Маршруты": "🧭 Маршруты\n\nКрепость станет перевалочным пунктом к будущим более опасным территориям. Пока доступен возврат к воротам Селдара.",
    }
    player["current_zone"] = "fortress_in_gorge_" + slugify_item_name(action).removeprefix("item_")
    player["location_id"] = player["current_zone"]
    storage.update_player(player)
    return LocationResponse(mapping.get(action, FORTRESS_TEXT), fortress_buttons(), player["current_zone"])


def handle_external_location_action(
    storage: Any,
    player: dict[str, Any],
    action: str,
    rng: random.Random | None = None,
) -> LocationResponse:
    rng = rng or random.Random()
    ensure_external_fields(player)

    if player.get("in_battle"):
        if action in BATTLE_ACTIONS:
            text, buttons = handle_battle_action(player, action, rng)
            storage.update_player(player)
            return LocationResponse(text, buttons or hilly_meadows_buttons(), player.get("current_zone", "hilly_meadows"))
        return LocationResponse("Сейчас вы в бою. Сначала завершите бой или сбегите.", battle_buttons(), player.get("current_zone", "hilly_meadows_battle"))

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
    if action.startswith("Съесть: "):
        dish_name = action.removeprefix("Съесть: ").strip()
        if dish_name in CAMP_DISHES:
            return eat_dish(storage, player, dish_name)
    if action in {COLLECT, SKIP, INSPECT_AND_TAKE, LOOK, LEAVE, RETREAT}:
        return resolve_active_event(storage, player, action, rng)

    return LocationResponse("Неизвестное действие внешней локации.", outside_city_buttons(), player.get("current_zone", "outside_city_crossroads"))
