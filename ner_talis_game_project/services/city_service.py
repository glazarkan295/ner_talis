import os
from dataclasses import dataclass
from typing import Any

from services.active_skill_service import (
    DISABLED_BRANCH_TEXT,
    ensure_active_skill_fields,
)
from services.external_location_service import (
    EXTERNAL_LOCATION_BUTTONS,
    LEGACY_OUTSIDE_CITY,
    OUTSIDE_CITY,
    handle_external_location_action,
)
from services.web_profile import create_profile_site_link
from services.market_service import (
    MARKET_ACTIONS,
    MARKET_BACK,
    MARKET_BACK_TO_MAIN,
    MARKET_BUY,
    MARKET_SELL,
    MARKET_ENTRY,
    MARKET_ZONE_PREFIX,
    handle_market_action,
    is_market_context,
    market_main_buttons,
)


CENTRAL_SQUARE = "Центральная площадь"
BACK_TO_CENTRAL = "⬅️ Центральная площадь"
OPEN_PAVILION_SITE = "🌐 Открыть торговый павильон"
ORDER_STONE = "Распорядительный камень"
APPLY_ID_AMULET = "Приложить идентификационный амулет"
CHOOSE_SPIRIT_BRANCH = "Выбрать Ветвь Духа"
CHOOSE_MANA_BRANCH = "Выбрать Ветвь Маны"
PROFILE_BUTTON = "Профиль"


@dataclass(frozen=True)
class CityResponse:
    text: str
    buttons: list[list[str]]
    zone_id: str
    needs_site_session: bool = False


@dataclass(frozen=True)
class WorldActionResult:
    text: str
    buttons: list[list[str]]
    scheduled_timer: dict[str, Any] | None = None


def central_square_buttons() -> list[list[str]]:
    return [
        ["Портовый квартал", "Торговый квартал"],
        ["Ремесленный квартал", "Верхний квартал"],
        ["Городские ворота", "Объявления"],
        [PROFILE_BUTTON],
    ]


def port_buttons() -> list[list[str]]:
    return [
        ["Тёмные переулки", "Пристань"],
        ["Портовый рынок", "Таверна"],
        [BACK_TO_CENTRAL],
    ]


def dark_alleys_buttons() -> list[list[str]]:
    return [
        ["Чёрный рынок", "Информатор Крот"],
        ["Подпольное казино"],
        ["Портовый квартал", BACK_TO_CENTRAL],
    ]


def pier_buttons() -> list[list[str]]:
    return [
        ["Рыбалка на пристани", "Аренда лодки"],
        ["Портовый рынок", "Портовый квартал"],
        [BACK_TO_CENTRAL],
    ]


def tavern_buttons() -> list[list[str]]:
    return [
        ["Поесть в таверне", "Отдохнуть в таверне"],
        ["Работа официантом", "Работа на кухне"],
        ["Работа на складе"],
        ["Портовый квартал", BACK_TO_CENTRAL],
    ]


def trade_buttons() -> list[list[str]]:
    return [
        ["Торговая гильдия", "Торговый павильон"],
        ["Рынок", "Аукцион"],
        ["Торговый представитель"],
        [BACK_TO_CENTRAL],
    ]


def pavilion_buttons() -> list[list[str]]:
    return [
        [OPEN_PAVILION_SITE],
        ["Торговый квартал", BACK_TO_CENTRAL],
    ]


def craft_buttons() -> list[list[str]]:
    return [
        ["Плавильня", "Кузница"],
        ["Кожевенная мастерская", "Ювелирная мастерская"],
        ["Алхимическая мастерская", "Мастерская чародея"],
        [BACK_TO_CENTRAL],
    ]


def upper_buttons() -> list[list[str]]:
    return [
        ["Ратуша", "Жилой район"],
        [BACK_TO_CENTRAL],
    ]


def town_hall_buttons() -> list[list[str]]:
    return [
        [ORDER_STONE],
        ["Верхний квартал", BACK_TO_CENTRAL],
    ]


def order_stone_buttons(player: dict[str, Any]) -> list[list[str]]:
    ensure_active_skill_fields(player)
    return [["Ратуша"], [BACK_TO_CENTRAL]]


def branch_choice_buttons() -> list[list[str]]:
    # Kept only for compatibility with old imports; no branch choice is shown.
    return [["Ратуша"], [BACK_TO_CENTRAL]]


def gates_buttons() -> list[list[str]]:
    return [
        [OUTSIDE_CITY],
        [BACK_TO_CENTRAL],
    ]


CENTRAL_TEXT = """🏙 Центральная площадь Селдара

Вы стоите на Центральной площади Селдара. Отсюда расходятся дороги ко всем кварталам города. На доске объявлений висят новости, задания и городские события.

Доступные направления:
• Портовый квартал
• Торговый квартал
• Ремесленный квартал
• Верхний квартал
• Городские ворота"""

PORT_TEXT = """⚓ Портовый квартал

Самая шумная и рискованная часть Селдара. Здесь пахнет солью, рыбой, смолой, чужими специями и деньгами.

Доступно:
• Тёмные переулки
• Пристань
• Портовый рынок
• Таверна"""

DARK_ALLEYS_TEXT = """🌑 Тёмные переулки

Здесь работают те, кто не любит городские правила: чёрный рынок, информатор Крот и подпольное казино.

Важно: при значимых действиях в переулках есть 3% шанс облавы. Если стража поймает игрока, придётся заплатить штраф. Если денег не хватит, остаток станет долгом в ратуше."""

BLACK_MARKET_TEXT = """🕯 Чёрный рынок

Нелегальная торговая точка с 1–3 редкими товарами. Ассортимент меняется раз в 3–5 дней.

Здесь могут появиться древние обломки, странные чертежи, ограниченные рецепты, проклятые вещи, редкие инструменты, карты и ключи.

Покупка и продажа здесь считаются рискованными действиями."""

INFORMER_TEXT = """🕳 Информатор Крот

Крот продаёт информацию о сильных игроках и принимает дорогие заказы.

Услуги:
• информация о местоположении игроков уровня 1000+ из топ-100 рейтинга;
• магический компас для быстрого пути к цели;
• заказ убийц на игрока.

Ограничения: нельзя заказать игрока, который меньше заказчика более чем в 2 раза по уровню, и нельзя заказать цель, если разница уровней больше 400."""

CASINO_TEXT = """🎲 Подпольное казино

Игры:
• кости;
• напёрстки;
• карты «Очко»;
• Колесо Удачи.

Казино — рискованное развлечение. Шанс проигрыша должен быть выше шанса выигрыша, чтобы казино не стало стабильным способом заработка."""

PIER_TEXT = """🪝 Пристань

На пристани можно рыбачить, арендовать лодку или маленький корабль, посетить портовый рынок и готовиться к морским экспедициям.

Для рыбалки нужна удочка. Рыбалка вдали от берега требует аренды лодки."""

PIER_FISHING_TEXT = """🎣 Рыбалка на пристани

Для действия нужна удочка.

Шансы:
• обычный улов — 50%
• необычный улов — 19%
• редкий улов — 1%
• мусор — 30%

Рыбалка может тратить энергию, если используется как добывающее действие."""

BOAT_RENT_TEXT = """⛵ Аренда лодки

Лодка нужна для рыбалки вдали от берега.

Шансы рыбалки вдали от берега:
• обычный улов — 40%
• необычный улов — 15%
• редкий улов — 9%
• эпический улов — 0,9989%
• легендарный улов — 0,001%
• мифический улов — 0,0001%
• мусор — 20%
• рыба сорвалась — 15%"""

PORT_MARKET_TEXT = """🧺 Портовый рынок

Здесь продаются товары из-за океана, которых почти нет на материке. Ассортимент обычно состоит из 4–10 товаров и обновляется раз в 5–12 дней из-за штормов.

Портовый рынок также может выдавать общие задания для всех игроков на поставку больших партий товаров."""

TAVERN_TEXT = """🍲 Таверна

Здесь можно поесть, отдохнуть, восстановить энергию и взять временную работу.

Обычные блюда восстанавливают энергию. Особые блюда дороже, но могут давать кратковременные баффы."""

TAVERN_FOOD_TEXT = """🍽 Блюда таверны

Обычные блюда:
• Каша из морской капусты — +15 энергии
• Картофельные лепёшки — +20 энергии
• Рыба в тесте — +25 энергии
• Уха простая — +30 энергии

Особые блюда:
• Уха из призрачной рыбы — +55 энергии и бонус восприятия
• Эль забытых моряков — +35 энергии и сопротивление усталости
• Суп оракула — +45 энергии и бонус мудрости
• Салат «Память веков» — +40 энергии и бонус интеллекта
• Пельмени вслепую — +60 энергии и случайный слабый эффект
• Настойка «Риск и Награда» — +30 энергии и рискованный эффект"""

TAVERN_REST_TEXT = """🛏 Отдых в таверне

Можно снять комнату, восстановиться и подготовиться к дальнейшим поискам.

Полная механика отдыха будет подключена позже: время отдыха, цена комнаты, восстановление HP/духа/маны/энергии и возможные бонусы от качества комнаты."""

TAVERN_WORK_WAITER_TEXT = """🍻 Работа официантом

Время: 30 минут.
Откат: 2 часа.
Награда: монеты и чаевые.

Каждое выполнение повышает уровень этой работы на 1. От уровня зависит награда, время и откат, но уменьшение времени и отката не может превышать 40%."""

TAVERN_WORK_KITCHEN_TEXT = """🥘 Работа на кухне

Время: 1 час.
Откат: 3 часа.
Награда: немного монет, небольшой перекус и 5% шанс получить ингредиент для готовки."""

TAVERN_WORK_STORAGE_TEXT = """📦 Работа на складе

Время: 2 часа.
Откат: 5 часов.
Награда: больше монет, простой предмет и 1% шанс повысить одну случайную базовую характеристику на 1."""

TRADE_TEXT = """💰 Торговый квартал

Торговый квартал делится на Торговую гильдию и Торговый павильон.

Гильдия работает в боте: рынок NPC, аукцион, торговый представитель, контракты и кредиты.

Торговый павильон открывается на сайте, потому что там удобнее управлять слотами продажи, складом и товарами игроков."""

TRADE_GUILD_TEXT = """⚖️ Торговая гильдия

Здесь находятся:
• рынок NPC;
• городской аукцион;
• торговый представитель;
• контракты;
• кредиты под проценты."""

NPC_MARKET_TEXT = """🛒 Рынок Торгового квартала

Безопасная NPC-покупка и NPC-продажа базовых товаров: расходники, ингредиенты, инструменты, колчаны, боеприпасы, простая экипировка и дешёвые материалы.

Доступные действия:
• Купить
• Продать
• Торговый квартал"""

AUCTION_TEXT = """🏷 Аукцион

Город выставляет предметы разной редкости. Игроки смогут анонимно выкладывать лоты на 1–3 дня.

Комиссия аукциона: 10–30%, зависит от стоимости лота и срока."""

TRADE_REPRESENTATIVE_TEXT = """📜 Торговый представитель

Занимается контрактами, арендой помещений в торговом павильоне, кредитами и торговыми условиями.

Большие долги могут ограничить кредиты, аренду и часть городских сделок."""

PAVILION_TEXT = """🏪 Торговый павильон

Торговый павильон Селдара слишком велик для обычного меню. Здесь игроки арендуют прилавки, лавки и магазины, выставляют товары и покупают вещи друг у друга.

Функционал павильона открывается на сайте:
• аренда малого прилавка, торговой лавки или магазина;
• выставление товаров;
• управление слотами;
• склад павильона;
• покупки у игроков;
• история сделок и уведомления."""

CRAFT_TEXT = """⚒ Ремесленный квартал

Здесь добытые ресурсы превращаются в материалы, оружие, броню, бижутерию, алхимические компоненты и зачарования.

Общей прокачки ремесла нет: каждая мастерская прокачивается отдельно."""

SMELTERY_TEXT = """🔥 Плавильня

Прокачка: плавильное дело.

Действия:
• переплавка руды в слитки;
• создание сплавов;
• подготовка металлических заготовок;
• переплавка лома."""

FORGE_TEXT = """🛠 Кузница

Прокачка: кузнечное дело.

Действия:
• создание оружия;
• создание тяжёлой брони;
• создание средней брони;
• создание щитов;
• создание металлических элементов для лёгкой брони."""

LEATHERWORK_TEXT = """🧵 Кожевенная мастерская

Прокачка: кожевничество.

Действия:
• создание лёгкой брони;
• кожаные элементы для средней брони;
• ремни, ножны, сумки;
• работа со шкурами, кожей, чешуёй, сухожилиями и пропитками."""

JEWELRY_TEXT = """💎 Ювелирная мастерская

Прокачка: ювелирное дело.

Действия:
• создание колец, ожерелий и амулетов;
• создание искусственных камней из осколков;
• огранка камней;
• вставка камней в оружие, броню и бижутерию."""

ALCHEMY_WORKSHOP_TEXT = """⚗️ Алхимическая мастерская

Прокачка: алхимия.

Действия:
• создание зелий;
• создание ядов;
• создание эликсиров;
• создание реагентов;
• создание специальных компонентов для высокоуровневого крафта."""

ENCHANTER_TEXT = """🔮 Мастерская чародея

Прокачка: зачарование.

Действия:
• наложение зачарований на оружие, броню и бижутерию;
• каменные зачарования;
• ритуалы усиления;
• проверка совместимости.

Древние предметы нельзя зачаровывать."""

UPPER_TEXT = """🏛 Верхний квартал

Административная и жилая часть Селдара.

Здесь находятся ратуша, городской управляющий, оформление кланов, долги, штрафы, грамоты, награды и жилой район."""

TOWN_HALL_TEXT = """🏛 Ратуша

Здесь можно:
• купить или продать участок;
• создать клан;
• получить грамоты и городские награды;
• посмотреть и оплатить долги, штрафы и кредиты;
• подойти к Распорядительному камню для выбора ветви активных навыков после 10 уровня."""

HOUSING_TEXT = """🏡 Жилой район

Жильё открывается после покупки участка.

Участки:
• малый участок;
• средний участок;
• большой участок.

Дом даёт отдых, почтовый ящик, постройки, специальные комнаты и будущие личные мастерские."""

GATES_TEXT = """🚪 Городские ворота

Вы стоите у городских ворот Селдара. За массивными створками начинается дорога к ближайшим землям Нер-Вира. Стражники лениво переговариваются, пропуская путников, торговцев и искателей добычи.

Отсюда можно выйти к внешним локациям или вернуться на Центральную площадь."""

LEAVE_CITY_TEXT = """🗺 Выход к локациям

Покинув безопасные стены Селдара, вы оказываетесь на развилке. Дороги ведут к ближайшим землям, где можно искать травы, руду, дичь и случайные находки."""

ANNOUNCEMENTS_TEXT = """📢 Объявления Селдара

На доске объявлений будут появляться:
• игровые ивенты;
• городские новости;
• конкурсы;
• мировые события;
• общие задания для игроков.

Пока активных объявлений нет."""

UNKNOWN_CITY_ACTION_TEXT = """Неизвестное городское действие.

Вернитесь на Центральную площадь и выберите действие кнопкой."""


CITY_ACTIONS: dict[str, CityResponse] = {
    "В город": CityResponse(CENTRAL_TEXT, central_square_buttons(), "seldar_central_square"),
    CENTRAL_SQUARE: CityResponse(CENTRAL_TEXT, central_square_buttons(), "seldar_central_square"),
    BACK_TO_CENTRAL: CityResponse(CENTRAL_TEXT, central_square_buttons(), "seldar_central_square"),
    "Портовый квартал": CityResponse(PORT_TEXT, port_buttons(), "seldar_port_district"),
    "Тёмные переулки": CityResponse(DARK_ALLEYS_TEXT, dark_alleys_buttons(), "seldar_dark_alleys"),
    "Чёрный рынок": CityResponse(BLACK_MARKET_TEXT, dark_alleys_buttons(), "seldar_black_market"),
    "Информатор Крот": CityResponse(INFORMER_TEXT, dark_alleys_buttons(), "seldar_informer_mole"),
    "Подпольное казино": CityResponse(CASINO_TEXT, dark_alleys_buttons(), "seldar_underground_casino"),
    "Пристань": CityResponse(PIER_TEXT, pier_buttons(), "seldar_pier"),
    "Рыбалка на пристани": CityResponse(PIER_FISHING_TEXT, pier_buttons(), "seldar_pier_fishing"),
    "Аренда лодки": CityResponse(BOAT_RENT_TEXT, pier_buttons(), "seldar_boat_rent"),
    "Портовый рынок": CityResponse(PORT_MARKET_TEXT, port_buttons(), "seldar_port_market"),
    "Таверна": CityResponse(TAVERN_TEXT, tavern_buttons(), "seldar_tavern"),
    "Поесть в таверне": CityResponse(TAVERN_FOOD_TEXT, tavern_buttons(), "seldar_tavern_food"),
    "Отдохнуть в таверне": CityResponse(TAVERN_REST_TEXT, tavern_buttons(), "seldar_tavern_rest"),
    "Работа официантом": CityResponse(TAVERN_WORK_WAITER_TEXT, tavern_buttons(), "seldar_tavern_waiter_work"),
    "Работа на кухне": CityResponse(TAVERN_WORK_KITCHEN_TEXT, tavern_buttons(), "seldar_tavern_kitchen_work"),
    "Работа на складе": CityResponse(TAVERN_WORK_STORAGE_TEXT, tavern_buttons(), "seldar_tavern_storage_work"),
    "Торговый квартал": CityResponse(TRADE_TEXT, trade_buttons(), "seldar_trade_district"),
    "Торговая гильдия": CityResponse(TRADE_GUILD_TEXT, trade_buttons(), "seldar_trade_guild"),
    MARKET_ENTRY: CityResponse(NPC_MARKET_TEXT, market_main_buttons(), "seldar_npc_market"),
    "Аукцион": CityResponse(AUCTION_TEXT, trade_buttons(), "seldar_auction"),
    "Торговый представитель": CityResponse(TRADE_REPRESENTATIVE_TEXT, trade_buttons(), "seldar_trade_representative"),
    "Торговый павильон": CityResponse(PAVILION_TEXT, pavilion_buttons(), "seldar_trade_pavilion", True),
    OPEN_PAVILION_SITE: CityResponse(PAVILION_TEXT, pavilion_buttons(), "seldar_trade_pavilion", True),
    "Ремесленный квартал": CityResponse(CRAFT_TEXT, craft_buttons(), "seldar_craft_district"),
    "Плавильня": CityResponse(SMELTERY_TEXT, craft_buttons(), "seldar_smeltery"),
    "Кузница": CityResponse(FORGE_TEXT, craft_buttons(), "seldar_forge"),
    "Кожевенная мастерская": CityResponse(LEATHERWORK_TEXT, craft_buttons(), "seldar_leatherwork"),
    "Ювелирная мастерская": CityResponse(JEWELRY_TEXT, craft_buttons(), "seldar_jewelry_workshop"),
    "Алхимическая мастерская": CityResponse(ALCHEMY_WORKSHOP_TEXT, craft_buttons(), "seldar_alchemy_workshop"),
    "Мастерская чародея": CityResponse(ENCHANTER_TEXT, craft_buttons(), "seldar_enchanter_workshop"),
    "Верхний квартал": CityResponse(UPPER_TEXT, upper_buttons(), "seldar_upper_district"),
    "Ратуша": CityResponse(TOWN_HALL_TEXT, town_hall_buttons(), "seldar_town_hall"),
    "Жилой район": CityResponse(HOUSING_TEXT, upper_buttons(), "seldar_residential_district"),
    "Городские ворота": CityResponse(GATES_TEXT, gates_buttons(), "seldar_city_gates"),
    LEGACY_OUTSIDE_CITY: CityResponse(LEAVE_CITY_TEXT, gates_buttons(), "outside_city_crossroads"),
    OUTSIDE_CITY: CityResponse(LEAVE_CITY_TEXT, gates_buttons(), "outside_city_crossroads"),
    "Объявления": CityResponse(ANNOUNCEMENTS_TEXT, central_square_buttons(), "seldar_announcements"),
}

BRANCH_CHOICE_ACTIONS = frozenset({ORDER_STONE, APPLY_ID_AMULET, CHOOSE_SPIRIT_BRANCH, CHOOSE_MANA_BRANCH})
CITY_BUTTONS = frozenset(CITY_ACTIONS.keys()) | BRANCH_CHOICE_ACTIONS | EXTERNAL_LOCATION_BUTTONS | MARKET_ACTIONS


def order_stone_text(player: dict[str, Any]) -> str:
    ensure_active_skill_fields(player)
    return (
        "🪨 Распорядительный камень\n\n"
        "Камень молчит. Система выбора ветви Духа или ветви Маны отключена.\n\n"
        f"{DISABLED_BRANCH_TEXT}"
    )


def _current_zone_id(player: dict[str, Any]) -> str:
    return str(player.get("current_zone") or player.get("location_id") or "").strip()


def _branch_gate_response(player: dict[str, Any], action: str) -> WorldActionResult | None:
    zone = _current_zone_id(player)
    if zone not in {"seldar_town_hall", "seldar_town_hall_order_stone"} and not (not zone and action == ORDER_STONE):
        return WorldActionResult(
            "🪨 К Распорядительному камню нельзя обратиться отсюда. "
            "Сначала перейдите в Селдар → Верхний квартал → Ратуша.",
            central_square_buttons(),
        )
    return None


def _order_stone_interaction_allowed(player: dict[str, Any], action: str) -> bool:
    zone = _current_zone_id(player)
    if action == ORDER_STONE:
        return zone in {"", "seldar_town_hall", "seldar_town_hall_order_stone"}
    return zone == "seldar_town_hall_order_stone"


def process_branch_choice_action(storage: Any, player: dict[str, Any], action: str) -> WorldActionResult | None:
    if action not in BRANCH_CHOICE_ACTIONS:
        return None
    ensure_active_skill_fields(player)
    player.pop("market_context", None)

    gate_response = _branch_gate_response(player, action)
    if gate_response is not None:
        storage.update_player(player)
        return gate_response
    if not _order_stone_interaction_allowed(player, action):
        storage.update_player(player)
        return WorldActionResult(
            "🪨 Сначала подойдите к Распорядительному камню в Ратуше.",
            town_hall_buttons(),
        )

    if action == ORDER_STONE:
        player["current_city"] = "seldar"
        player["current_zone"] = "seldar_town_hall_order_stone"
        player["location_id"] = "seldar_town_hall_order_stone"

    storage.update_player(player)
    return WorldActionResult(order_stone_text(player), order_stone_buttons(player))


def _is_external_location_state(player: dict[str, Any]) -> bool:
    """Return True when the player is already outside the city flow.

    This keeps shared labels such as ``Назад`` under the external-location
    handler while a player is searching, camping, fighting or standing at the
    outside crossroads, but still lets the market handler own its own ``Назад``
    button inside the NPC market.
    """
    values = {
        str(player.get("current_city") or ""),
        str(player.get("current_zone") or ""),
        str(player.get("location_id") or ""),
        str(player.get("current_location") or ""),
    }
    if "outside_seldar" in values:
        return True
    external_prefixes = (
        "outside_city_crossroads",
        "hilly_meadows",
        "ordinary_forest",
        "fortress_in_gorge",
    )
    return any(value.startswith(external_prefixes) for value in values if value)


def _market_should_own_back(player: dict[str, Any], action: str) -> bool:
    """Return True when the shared ``Назад`` button belongs to the market."""
    return action == MARKET_BACK and is_market_context(player) and not _is_external_location_state(player)


def _market_should_handle_action(player: dict[str, Any], action: str) -> bool:
    """Return True when input should stay inside the NPC market state machine.

    The market may own item names and typed quantities while its context is
    active, but it must not intercept explicit city, branch-choice or
    external-location buttons such as ``Выход из города`` and
    ``Распорядительный камень``.
    """
    if action == MARKET_ENTRY:
        return True
    if not is_market_context(player) or _is_external_location_state(player):
        return False
    if action in BRANCH_CHOICE_ACTIONS:
        return False
    if action in EXTERNAL_LOCATION_BUTTONS and not _market_should_own_back(player, action):
        return False
    if action in CITY_ACTIONS and action != MARKET_ENTRY and action not in {MARKET_BUY, MARKET_SELL, MARKET_BACK, MARKET_BACK_TO_MAIN}:
        return False
    return True


def _external_should_handle_action(player: dict[str, Any], action: str) -> bool:
    if action not in EXTERNAL_LOCATION_BUTTONS:
        return False
    return not _market_should_own_back(player, action)


def process_world_action(
    storage: Any,
    player: dict[str, Any],
    action: str,
    platform: str,
) -> WorldActionResult:
    """Processes city, market, battle, branch and external-location actions.

    Priority rules are intentionally strict: explicit city/branch/external
    buttons must be able to break stale market context, while item names,
    quantities and the market-local ``Назад`` stay inside the market.
    """
    if player.get("in_battle"):
        response = handle_external_location_action(storage, player, action)
        return WorldActionResult(text=response.text, buttons=response.buttons, scheduled_timer=response.scheduled_timer)

    if action == PROFILE_BUTTON:
        try:
            profile_url = create_profile_site_link(storage, player, platform)
            text = (
                "🌐 Профиль на сайте готов.\n\n"
                f"Ссылка: {profile_url}\n\n"
                "Она привязана к вашему единому игровому ID и действует ограниченное время."
            )
        except Exception:
            text = "Профиль сейчас недоступен. Попробуйте ещё раз позже."
        return WorldActionResult(text=text, buttons=central_square_buttons())

    # Explicit city navigation breaks stale market context. ``Рынок`` is the
    # only city button that intentionally enters the market state machine.
    # External-location labels are handled below so ``Выход из города`` cannot
    # be swallowed by stale market context.
    if action in CITY_ACTIONS and action != MARKET_ENTRY and action not in EXTERNAL_LOCATION_BUTTONS:
        player.pop("market_context", None)
        response = get_city_response(action)
        updated_player = apply_city_transition(storage, player, response)
        text = build_response_text(
            storage=storage,
            player=updated_player,
            response=response,
            platform=platform,
        )
        return WorldActionResult(text=text, buttons=response.buttons)

    # Branch-choice buttons must never be handled by the market. This prevents
    # stale market_context from teleporting the Order Stone flow back to the
    # NPC market.
    branch_response = process_branch_choice_action(storage, player, action)
    if branch_response is not None:
        return branch_response

    # External-location buttons also break stale market context. The only
    # exception is the shared ``Назад`` label while the player is actually in
    # a market screen, where it belongs to the market card/list flow.
    if _external_should_handle_action(player, action):
        player.pop("market_context", None)
        response = handle_external_location_action(storage, player, action)
        return WorldActionResult(text=response.text, buttons=response.buttons, scheduled_timer=response.scheduled_timer)

    if _market_should_handle_action(player, action):
        response = handle_market_action(storage, player, action)
        return WorldActionResult(text=response.text, buttons=response.buttons)

    response = get_city_response(action)
    updated_player = apply_city_transition(storage, player, response)
    text = build_response_text(
        storage=storage,
        player=updated_player,
        response=response,
        platform=platform,
    )
    return WorldActionResult(text=text, buttons=response.buttons)


def build_pavilion_url(token: str) -> str:
    base_url = os.getenv("SITE_PAVILION_URL", "https://example.com/pavilion")
    return f"{base_url.rstrip('/')}?token={token}"


def ensure_city_fields(player: dict[str, Any]) -> bool:
    changed = False

    defaults = {
        "current_city": "seldar",
        "current_zone": "seldar_central_square",
        "location_id": "seldar_central_square",
        "money": 0,
        "debt": 0,
        "energy": 100,
        "max_energy": 100,
        "bonus_max_energy": 0,
        "in_battle": False,
        "is_dead": False,
        "crafting_levels": {
            "smelting": {"level": 1, "experience": 0},
            "blacksmithing": {"level": 1, "experience": 0},
            "leatherworking": {"level": 1, "experience": 0},
            "jewelcrafting": {"level": 1, "experience": 0},
            "alchemy": {"level": 1, "experience": 0},
            "enchanting": {"level": 1, "experience": 0},
        },
        "housing": {
            "plot_type": None,
            "buildings": [],
        },
    }

    for key, value in defaults.items():
        if key not in player:
            player[key] = value
            changed = True

    return changed


def get_city_response(action: str) -> CityResponse:
    return CITY_ACTIONS.get(
        action,
        CityResponse(
            UNKNOWN_CITY_ACTION_TEXT,
            central_square_buttons(),
            "seldar_central_square",
        ),
    )


def apply_city_transition(
    storage: Any,
    player: dict[str, Any],
    response: CityResponse,
) -> dict[str, Any]:
    ensure_city_fields(player)
    player["current_city"] = "seldar"
    player["current_zone"] = response.zone_id
    player["location_id"] = response.zone_id
    if not str(response.zone_id).startswith(MARKET_ZONE_PREFIX):
        player.pop("market_context", None)
    storage.update_player(player)
    return player


def build_response_text(
    storage: Any,
    player: dict[str, Any],
    response: CityResponse,
    platform: str,
) -> str:
    if not response.needs_site_session:
        return response.text

    if player.get("in_battle"):
        return (
            "🏪 Торговый павильон сейчас недоступен. "
            "Нельзя открывать торговые операции во время боя."
        )

    token = storage.create_site_session(
        game_id=player["game_id"],
        scope="pavilion",
        platform=platform,
    )
    url = build_pavilion_url(token)

    return (
        f"{response.text}\n\n"
        "Ссылка действует ограниченное время и привязана к вашему единому игровому ID.\n"
        f"Открыть павильон: {url}"
    )
