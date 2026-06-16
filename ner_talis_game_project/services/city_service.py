import logging
import os
from dataclasses import dataclass
from typing import Any

from services.active_skill_service import (
    ACTIVE_BRANCH_TEXT,
    MANA_BRANCH,
    MANA_PATHS,
    SPIRIT_BRANCH,
    SPIRIT_PATHS,
    choose_active_skill_branch,
    choose_main_path,
    choose_secondary_path,
    confirm_pending_skill_choice,
    current_available_choice,
    ensure_active_skill_fields,
    load_branch_choice_messages,
    main_path_level,
    next_threshold_for_path,
    path_level,
    preview_skill_choice,
    selected_main_path,
    selected_secondary_path,
    player_branch,
)

from services.external_location_service import (
    EXTERNAL_LOCATION_BUTTONS,
    LEGACY_OUTSIDE_CITY,
    OUTSIDE_CITY,
    current_external_buttons,
    handle_external_location_action,
    outside_city_buttons,
    small_plateau_hidden_coin_buttons,
)
from services.small_plateau_service import roll_ancient_curse_trigger
from services.player_time_service import advance_player_time
from services.web_profile import create_profile_site_link
from services.market_service import (
    MARKET_ACTIONS,
    MARKET_BACK,
    MARKET_BACK_TO_MAIN,
    MARKET_BUY,
    MARKET_SELL,
    MARKET_ENTRY,
    MARKET_ENTRY_ACTIONS,
    MARKET_ZONE_PREFIX,
    handle_market_action,
    is_market_context,
    market_main_buttons,
)
from services.crafting_service import (
    CRAFT_ACTIONS,
    clear_stale_crafting_context_if_needed,
    handle_crafting_action,
    should_handle_crafting_action,
)


from services.fishing_service import (
    FISHING_ACTIONS,
    PIER_FISHING_ACTION,
    START_PIER_FISHING,
    fishing_buttons,
    handle_fishing_action,
)
from services.fine_service import (
    CITY_FINE_PAY_ACTION,
    CITY_HALL_BACK,
    FORTRESS_HALL,
    MAINLAND_EXTERNAL,
    STAY_IN_FORTRESS,
    advance_fine_state,
    fine_card,
    maybe_trigger_raid,
    movement_block_buttons,
    movement_block_text,
    pay_fine,
    should_block_movement_action,
)
from services.promo_service import redeem_promo_code


CENTRAL_SQUARE = "Центральная площадь"
BACK_TO_CENTRAL = "⬅️ Центральная площадь"
OPEN_PAVILION_SITE = "🌐 Открыть торговый павильон"
ORDER_STONE = "Распорядительный камень"
APPLY_ID_AMULET = "Приложить идентификационный амулет"
CHOOSE_SPIRIT_BRANCH = "Выбрать Ветвь Духа"
CHOOSE_MANA_BRANCH = "Выбрать Ветвь Маны"
PREVIEW_SPIRIT_BRANCH = "Ветка Духа"
PREVIEW_MANA_BRANCH = "Ветка Маны"
CONFIRM_BRANCH = "Выбрать ветку"
BACK_TO_BRANCH_CHOICE = "Вернуться к выбору"
CONFIRM_PATH = "Выбрать путь"
BACK_TO_PATHS = "Вернуться к путям"
CONFIRM_SKILL = "Выбрать навык"
BACK_TO_SKILL_CHOICE = "Вернуться к выбору навыка"
SECONDARY_PATH_ACTION = "Выбрать дополнительный путь"
PROFILE_BUTTON = "Профиль"
CITY_MANAGER = "Городской управляющий"
CITY_REWARD_CLAIM_ACTION = "Получить награду"
logger = logging.getLogger(__name__)


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
    extra_messages: tuple[str, ...] = ()


def central_square_buttons() -> list[list[str]]:
    return [
        ["Портовый квартал", "Торговый квартал"],
        ["Ремесленный квартал", "Верхний квартал"],
        ["Городские ворота", "Объявления"],
        [PROFILE_BUTTON],
    ]


# Переходы между кварталами Селдара — «хождение по кварталам города», на котором
# Древнее Проклятье с шансом 20% уводит игрока на скрытое место Малого плато.
CITY_QUARTER_WALK_ACTIONS = frozenset({
    "Портовый квартал",
    "Торговый квартал",
    "Ремесленный квартал",
    "Верхний квартал",
})


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


TAVERN_WORK = "Работа в Таверне"


def tavern_buttons() -> list[list[str]]:
    return [
        ["Поесть в таверне", "Отдохнуть в таверне"],
        [TAVERN_WORK],
        ["Портовый квартал", BACK_TO_CENTRAL],
    ]


def tavern_work_buttons() -> list[list[str]]:
    return [
        ["Работа официантом", "Работа на кухне"],
        ["Работа на складе"],
        ["Таверна", BACK_TO_CENTRAL],
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
        [CITY_MANAGER],
        ["Верхний квартал", BACK_TO_CENTRAL],
    ]


def city_manager_buttons() -> list[list[str]]:
    return [
        [CITY_FINE_PAY_ACTION, CITY_REWARD_CLAIM_ACTION],
        ["Ратуша"],
        [BACK_TO_CENTRAL],
    ]


def order_stone_buttons(player: dict[str, Any]) -> list[list[str]]:
    ensure_active_skill_fields(player)
    return [["Ратуша"], [BACK_TO_CENTRAL]]


def branch_choice_buttons() -> list[list[str]]:
    return [[PREVIEW_SPIRIT_BRANCH, PREVIEW_MANA_BRANCH], ["Ратуша"]]


def path_choice_buttons(branch: str, exclude: str | None = None) -> list[list[str]]:
    paths = SPIRIT_PATHS if branch == SPIRIT_BRANCH else MANA_PATHS
    values = [path for path in paths if path != exclude]
    rows = [[f"Путь: {values[index]}", f"Путь: {values[index + 1]}"] for index in range(0, len(values) - 1, 2)]
    if len(values) % 2:
        rows.append([f"Путь: {values[-1]}"])
    rows.append(["Ратуша"])
    return rows


def skill_choice_buttons(choice: dict[str, Any]) -> list[list[str]]:
    options = choice.get("options") or []
    rows = [[f"Навык {index + 1}"] for index, _skill in enumerate(options)]
    rows.append(["Ратуша"])
    return rows


def skill_preview_buttons() -> list[list[str]]:
    return [[CONFIRM_SKILL], [BACK_TO_SKILL_CHOICE, "Ратуша"]]



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

Важно: при любых действиях в запретных местах есть 15% шанс облавы. Если стража поймает игрока, игрока перенесут на Центральную площадь и наложат городской штраф."""

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

Для действия нужна удочка рыбака. Один заброс тратит 2 энергии.

Шансы:
• обычный улов — 50%
• необычный улов — 19%
• редкий улов — 1%
• мусор — 30%

Возможный улов: водоросли, рыба, моллюски, ракушки, медузы, угорь, старый башмак, старый сундучок и редкие морские находки."""

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

TAVERN_WORK_TEXT = """💼 Работа в Таверне

Выберите подработку. Каждая работа даёт монеты и небольшие награды, имеет своё время выполнения и откат."""

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

CITY_MANAGER_TEXT = """📜 Городской управляющий

Здесь оформляют городские штрафы, награды и служебные вопросы.

Доступно:
• оплатить активные штрафы;
• получить доступные награды, когда они будут назначены."""

CITY_REWARD_CLAIM_TEXT = """🎁 Получить награду

Сейчас у вас нет назначенных городских наград. Когда появятся события, грамоты или выплаты от администрации, они будут выдаваться здесь."""

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
    "Рыбалка на пристани": CityResponse(PIER_FISHING_TEXT, fishing_buttons(), "seldar_pier_fishing"),
    "Аренда лодки": CityResponse(BOAT_RENT_TEXT, pier_buttons(), "seldar_boat_rent"),
    "Портовый рынок": CityResponse(PORT_MARKET_TEXT, port_buttons(), "seldar_port_market"),
    "Таверна": CityResponse(TAVERN_TEXT, tavern_buttons(), "seldar_tavern"),
    "Поесть в таверне": CityResponse(TAVERN_FOOD_TEXT, tavern_buttons(), "seldar_tavern_food"),
    "Отдохнуть в таверне": CityResponse(TAVERN_REST_TEXT, tavern_buttons(), "seldar_tavern_rest"),
    TAVERN_WORK: CityResponse(TAVERN_WORK_TEXT, tavern_work_buttons(), "seldar_tavern_work"),
    "Работа официантом": CityResponse(TAVERN_WORK_WAITER_TEXT, tavern_work_buttons(), "seldar_tavern_waiter_work"),
    "Работа на кухне": CityResponse(TAVERN_WORK_KITCHEN_TEXT, tavern_work_buttons(), "seldar_tavern_kitchen_work"),
    "Работа на складе": CityResponse(TAVERN_WORK_STORAGE_TEXT, tavern_work_buttons(), "seldar_tavern_storage_work"),
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
    # «Ювелирная мастерская» обрабатывается крафт-сервисом (should_handle_crafting_action)
    # раньше CITY_ACTIONS — отдельная запись-заглушка здесь была бы недостижимой.
    "Алхимическая мастерская": CityResponse(ALCHEMY_WORKSHOP_TEXT, craft_buttons(), "seldar_alchemy_workshop"),
    "Мастерская чародея": CityResponse("🔮 Мастерская чародея\n\nМастерская временно закрыта на техническое обслуживание.", craft_buttons(), "seldar_craft_district"),
    "Верхний квартал": CityResponse(UPPER_TEXT, upper_buttons(), "seldar_upper_district"),
    "Ратуша": CityResponse(TOWN_HALL_TEXT, town_hall_buttons(), "seldar_town_hall"),
    CITY_MANAGER: CityResponse(CITY_MANAGER_TEXT, city_manager_buttons(), "seldar_town_manager"),
    CITY_REWARD_CLAIM_ACTION: CityResponse(CITY_REWARD_CLAIM_TEXT, city_manager_buttons(), "seldar_town_manager"),
    "Жилой район": CityResponse(HOUSING_TEXT, upper_buttons(), "seldar_residential_district"),
    "Городские ворота": CityResponse(GATES_TEXT, gates_buttons(), "seldar_city_gates"),
    LEGACY_OUTSIDE_CITY: CityResponse(LEAVE_CITY_TEXT, outside_city_buttons(), "outside_city_crossroads"),
    OUTSIDE_CITY: CityResponse(LEAVE_CITY_TEXT, outside_city_buttons(), "outside_city_crossroads"),
    "Объявления": CityResponse(ANNOUNCEMENTS_TEXT, central_square_buttons(), "seldar_announcements"),
}

BRANCH_CHOICE_ACTIONS = frozenset({ORDER_STONE, APPLY_ID_AMULET, CHOOSE_SPIRIT_BRANCH, CHOOSE_MANA_BRANCH, PREVIEW_SPIRIT_BRANCH, PREVIEW_MANA_BRANCH, CONFIRM_BRANCH, BACK_TO_BRANCH_CHOICE, CONFIRM_PATH, BACK_TO_PATHS, CONFIRM_SKILL, BACK_TO_SKILL_CHOICE, SECONDARY_PATH_ACTION})
FINE_ACTIONS = frozenset({CITY_FINE_PAY_ACTION, CITY_HALL_BACK, FORTRESS_HALL, STAY_IN_FORTRESS, MAINLAND_EXTERNAL})
CITY_BUTTONS = frozenset(CITY_ACTIONS.keys()) | BRANCH_CHOICE_ACTIONS | EXTERNAL_LOCATION_BUTTONS | MARKET_ACTIONS | CRAFT_ACTIONS | FINE_ACTIONS | FISHING_ACTIONS


def _split_stone_and_administrator_text(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    marker = "Распорядитель"
    index = raw.find(marker)
    if index > 0:
        stone = raw[:index].strip()
        administrator = raw[index:].strip()
        return [part for part in (stone, administrator) if part]
    return [raw]


def _message_parts(key: str, fallback: str = "") -> list[str]:
    messages = load_branch_choice_messages()
    value = messages.get(key)
    if isinstance(value, dict):
        stone = str(value.get("stone_text") or "").strip()
        admin = str(value.get("administrator_text") or "").strip()
        if stone or admin:
            return [part for part in (stone, admin) if part] or ([fallback] if fallback else [])
        text = str(value.get("text") or "").strip()
        if text:
            return _split_stone_and_administrator_text(text)
    return [fallback] if fallback else []


def _message_text(key: str, fallback: str = "") -> str:
    return "\n\n".join(_message_parts(key, fallback))


def _result_from_parts(parts: list[str], buttons: list[list[str]], scheduled_timer: dict[str, Any] | None = None) -> WorldActionResult:
    clean = [str(part).strip() for part in parts if str(part or "").strip()]
    if not clean:
        clean = [""]
    return WorldActionResult(clean[-1], buttons, scheduled_timer=scheduled_timer, extra_messages=tuple(clean[:-1]))


def _branch_intro_text() -> str:
    return _message_text(
        "stone_branch_choice_intro",
        "Вы прикладываете идентификационный амулет к камню. Распорядитель предлагает выбрать ветвь развития.",
    )


def _path_intro_text(branch: str) -> str:
    messages = load_branch_choice_messages()
    intro = messages.get("main_path_choice_intro") if isinstance(messages.get("main_path_choice_intro"), dict) else {}
    data = intro.get("spirit" if branch == SPIRIT_BRANCH else "mana") if isinstance(intro, dict) else None
    if isinstance(data, dict) and data.get("text"):
        return str(data["text"])
    return "Камень показывает доступные пути выбранной ветки. Выберите основной путь."


def _secondary_intro_text(player: dict[str, Any]) -> str:
    return _message_text(
        "secondary_path_choice_intro",
        "Камень открывает возможность второго пути. Он не сможет превысить 60% уровня основного пути.",
    )


def _no_choices_text() -> str:
    return _message_text("stone_no_available_choices", "Вы притрагиваетесь к камню и ощущаете его холод. Сейчас он ничего не показывает.")


def _skill_choice_text(choice: dict[str, Any]) -> str:
    lines = [f"Путь: {choice.get('path')} · порог: {choice.get('threshold')} · уровень пути: доступен"]
    for index, skill in enumerate(choice.get("options") or [], 1):
        kind = "пассивный" if skill.get("is_passive") else "активный"
        lines.append(f"{index}. {skill.get('name')} — {kind}. {skill.get('effect')}")
    return "\n".join(lines)


def _skill_preview_text(player: dict[str, Any], skill: dict[str, Any]) -> str:
    kind = "пассивный навык" if skill.get("is_passive") else "активный навык"
    path = skill.get("path") or "—"
    threshold = skill.get("unlock_path_level") or 0
    reqs = skill.get("usage_requirements") or skill.get("required_equipment") or "—"
    if isinstance(reqs, list):
        reqs = "; ".join(str(item) for item in reqs)
    resource = "нет" if skill.get("is_passive") else str(skill.get("resource_cost_text") or "—")
    cooldown = "нет" if skill.get("is_passive") else str(skill.get("cooldown_turns_text") or "—")
    return (
        f"Название: {skill.get('name')}\n\n"
        f"Тип: {kind}\nПуть: {path}\nПорог: {threshold}\n\n"
        f"Описание:\n{skill.get('effect') or '—'}\n\n"
        f"Расход:\n{resource}\n\nОткат:\n{cooldown}\n\nТребования:\n{reqs}"
    )


def _branch_preview_text(branch: str) -> str:
    messages = load_branch_choice_messages()
    previews = messages.get("branch_previews") if isinstance(messages.get("branch_previews"), dict) else {}
    data = previews.get("spirit" if branch == SPIRIT_BRANCH else "mana") if isinstance(previews, dict) else None
    if isinstance(data, dict) and data.get("text"):
        return str(data["text"])
    paths = ", ".join(SPIRIT_PATHS if branch == SPIRIT_BRANCH else MANA_PATHS)
    return f"Ветвь {branch}. Пути: {paths}."


def _path_preview_text(path: str) -> str:
    messages = load_branch_choice_messages()
    previews = messages.get("path_previews") if isinstance(messages.get("path_previews"), dict) else {}
    for data in previews.values() if isinstance(previews, dict) else []:
        if isinstance(data, dict) and data.get("name") == path:
            return str(data.get("text") or path)
    return f"Путь: {path}."


def _stone_main_screen(player: dict[str, Any]) -> WorldActionResult:
    ensure_active_skill_fields(player)
    level = int(player.get("level") or 1)
    if level < 10 and not player_branch(player):
        return _result_from_parts(_message_parts("stone_no_level_10", "— Рано. Возвращайся, когда дорастёшь до 10 уровня."), [["Ратуша"]])
    if not player_branch(player):
        return _result_from_parts(_message_parts("stone_branch_choice_intro", "Вы прикладываете идентификационный амулет к камню. Распорядитель предлагает выбрать ветвь развития."), branch_choice_buttons())
    branch = player_branch(player) or SPIRIT_BRANCH
    if not selected_main_path(player):
        return WorldActionResult(_path_intro_text(branch), path_choice_buttons(branch))
    if level >= 100 and not selected_secondary_path(player):
        return _result_from_parts(_message_parts("secondary_path_choice_intro", "Камень открывает возможность второго пути. Он не сможет превысить 60% уровня основного пути."), [[SECONDARY_PATH_ACTION], ["Ратуша"]])
    choice = current_available_choice(player)
    if choice:
        parts = _message_parts("skill_choice_available", "Камень предлагает три возможности. Выберите одну из них вдумчиво.")
        choice_text = _skill_choice_text(choice)
        if parts:
            parts[-1] = parts[-1] + "\n\n" + choice_text
        else:
            parts = [choice_text]
        return _result_from_parts(parts, skill_choice_buttons(choice))
    return _result_from_parts(_message_parts("stone_no_available_choices", "Вы притрагиваетесь к камню и ощущаете его холод. Сейчас он ничего не показывает."), [["Ратуша"]])


def order_stone_text(player: dict[str, Any]) -> str:
    return _stone_main_screen(player).text


def _current_zone_id(player: dict[str, Any]) -> str:
    return str(player.get("current_zone") or player.get("location_id") or "").strip()


def _branch_gate_response(player: dict[str, Any], action: str) -> WorldActionResult | None:
    zone = _current_zone_id(player)
    if zone not in {"seldar_town_hall", "seldar_town_hall_order_stone"} and not (not zone and action == ORDER_STONE):
        return WorldActionResult(
            "🪨 К Распорядительному камню нельзя обратиться отсюда. Сначала перейдите в Селдар → Верхний квартал → Ратуша.",
            central_square_buttons(),
        )
    return None


def _order_stone_interaction_allowed(player: dict[str, Any], action: str) -> bool:
    zone = _current_zone_id(player)
    if action == ORDER_STONE:
        return zone in {"", "seldar_town_hall", "seldar_town_hall_order_stone"}
    return zone == "seldar_town_hall_order_stone"


def process_branch_choice_action(storage: Any, player: dict[str, Any], action: str) -> WorldActionResult | None:
    dynamic = action.startswith("Путь: ") or action.startswith("Навык ")
    if action not in BRANCH_CHOICE_ACTIONS and not dynamic:
        return None
    ensure_active_skill_fields(player)
    player.pop("market_context", None)

    gate_response = _branch_gate_response(player, action)
    if gate_response is not None:
        storage.update_player(player)
        return gate_response
    if not _order_stone_interaction_allowed(player, action):
        storage.update_player(player)
        return WorldActionResult("🪨 Сначала подойдите к Распорядительному камню в Ратуше.", town_hall_buttons())

    player["current_city"] = "seldar"
    player["current_zone"] = "seldar_town_hall_order_stone"
    player["location_id"] = "seldar_town_hall_order_stone"

    if action in {ORDER_STONE, APPLY_ID_AMULET, BACK_TO_BRANCH_CHOICE, BACK_TO_PATHS, BACK_TO_SKILL_CHOICE}:
        result = _stone_main_screen(player)
        storage.update_player(player)
        return result

    if action in {CHOOSE_SPIRIT_BRANCH, CHOOSE_MANA_BRANCH}:
        branch = SPIRIT_BRANCH if action == CHOOSE_SPIRIT_BRANCH else MANA_BRANCH
        try:
            choose_active_skill_branch(player, branch)
        except ValueError as exc:
            storage.update_player(player)
            return WorldActionResult(f"🪨 {exc}", [["Ратуша"]])
        parts = _message_parts("after_branch_choice", "Камень принимает ваш выбор. Теперь выберите основной путь.")
        parts.append(_path_intro_text(branch))
        storage.update_player(player)
        return _result_from_parts(parts, path_choice_buttons(branch))

    if action in {PREVIEW_SPIRIT_BRANCH, PREVIEW_MANA_BRANCH}:
        branch = SPIRIT_BRANCH if action == PREVIEW_SPIRIT_BRANCH else MANA_BRANCH
        player["pending_branch_choice"] = branch
        storage.update_player(player)
        return WorldActionResult(_branch_preview_text(branch), [[CONFIRM_BRANCH], [BACK_TO_BRANCH_CHOICE, "Ратуша"]])

    if action == CONFIRM_BRANCH:
        branch = player.get("pending_branch_choice")
        try:
            choose_active_skill_branch(player, str(branch or ""))
        except ValueError as exc:
            storage.update_player(player)
            return WorldActionResult(f"🪨 {exc}", [["Ратуша"]])
        player.pop("pending_branch_choice", None)
        parts = _message_parts("after_branch_choice", "Камень принимает ваш выбор. Теперь выберите основной путь.")
        parts.append(_path_intro_text(player_branch(player) or SPIRIT_BRANCH))
        storage.update_player(player)
        return _result_from_parts(parts, path_choice_buttons(player_branch(player) or SPIRIT_BRANCH))

    if action == SECONDARY_PATH_ACTION:
        branch = player_branch(player) or SPIRIT_BRANCH
        storage.update_player(player)
        return _result_from_parts(_message_parts("secondary_path_choice_intro", "Камень открывает возможность второго пути. Он не сможет превысить 60% уровня основного пути."), path_choice_buttons(branch, exclude=selected_main_path(player)))

    if action.startswith("Путь: "):
        path = action.split(":", 1)[1].strip()
        branch = player_branch(player)
        if not branch:
            storage.update_player(player)
            return WorldActionResult("Сначала выберите ветку развития.", branch_choice_buttons())
        if not selected_main_path(player):
            choose_main_path(player, path)
            parts = _message_parts("after_main_path_choice", "Основной путь выбран. Развивайте его и возвращайтесь к камню на новых порогах.")
            storage.update_player(player)
            return _result_from_parts(parts, [["Ратуша"]])
        if int(player.get("level") or 1) >= 100 and not selected_secondary_path(player):
            try:
                choose_secondary_path(player, path)
            except ValueError as exc:
                storage.update_player(player)
                return WorldActionResult(f"🪨 {exc}", [[SECONDARY_PATH_ACTION], ["Ратуша"]])
            parts = _message_parts("after_secondary_path_choice", "Дополнительный путь выбран. Его развитие ограничено 60% уровня основного пути.")
            storage.update_player(player)
            return _result_from_parts(parts, [["Ратуша"]])
        storage.update_player(player)
        return WorldActionResult(_path_preview_text(path), [[CONFIRM_PATH], [BACK_TO_PATHS, "Ратуша"]])

    if action.startswith("Навык "):
        number = action.split(" ", 1)[1].strip()
        skill = preview_skill_choice(player, number)
        storage.update_player(player)
        if not skill:
            return WorldActionResult("Этот выбор сейчас недоступен.", [[BACK_TO_SKILL_CHOICE], ["Ратуша"]])
        return WorldActionResult(_skill_preview_text(player, skill), skill_preview_buttons())

    if action == CONFIRM_SKILL:
        selected = confirm_pending_skill_choice(player)
        if not selected:
            storage.update_player(player)
            return WorldActionResult("Навык не выбран или выбор уже недоступен.", [[BACK_TO_SKILL_CHOICE], ["Ратуша"]])
        next_threshold = next_threshold_for_path(player, str(selected.get("path") or ""))
        messages = load_branch_choice_messages()
        after = messages.get("after_skill_choice") if isinstance(messages.get("after_skill_choice"), dict) else {}
        if next_threshold:
            template = str(after.get("text_template") or "Камень принимает выбор. Навык «{skill_name}» теперь ваш. Следующий порог пути: {next_threshold}.")
            text = template.format(skill_name=selected.get("name"), next_threshold=next_threshold)
        else:
            text = str(after.get("final_threshold_text") or f"Камень принимает выбор. Навык «{selected.get('name')}» теперь ваш. Этот путь достиг последнего порога.")
        text = text.replace("теперь твой", "теперь ваш")
        storage.update_player(player)
        return _result_from_parts(_split_stone_and_administrator_text(text), [["Ратуша"]])

    result = _stone_main_screen(player)
    storage.update_player(player)
    return result

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




def _has_active_craft_timer(player: dict[str, Any]) -> bool:
    active_timer = player.get("active_timer")
    return isinstance(active_timer, dict) and active_timer.get("type") == "craft"


def _is_market_zone(player: dict[str, Any]) -> bool:
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    return zone.startswith(MARKET_ZONE_PREFIX)


def _clear_stale_market_context_if_needed(player: dict[str, Any]) -> bool:
    if player.get("market_context") and not _is_market_zone(player):
        player.pop("market_context", None)
        return True
    return False


def _current_context_buttons(player: dict[str, Any]) -> list[list[str]]:
    if _is_external_location_state(player):
        return current_external_buttons(player)
    return _current_city_buttons(player)

def _market_should_own_back(player: dict[str, Any], action: str) -> bool:
    """Return True when the shared ``Назад`` button belongs to the market."""
    return action == MARKET_BACK and _is_market_zone(player) and is_market_context(player) and not _is_external_location_state(player)


def _market_should_handle_action(player: dict[str, Any], action: str) -> bool:
    """Return True when input should stay inside the NPC market state machine.

    The market may own item names and typed quantities while its context is
    active, but it must not intercept explicit city, branch-choice or
    external-location buttons such as ``Выход из города`` and
    ``Распорядительный камень``.
    """
    if action in MARKET_ENTRY_ACTIONS:
        return True
    if _is_external_location_state(player) or not _is_market_zone(player):
        return False
    if not is_market_context(player):
        return False
    if action in BRANCH_CHOICE_ACTIONS:
        return False
    if action in EXTERNAL_LOCATION_BUTTONS and not _market_should_own_back(player, action):
        return False
    if action in CITY_ACTIONS and action not in MARKET_ENTRY_ACTIONS and action not in {MARKET_BUY, MARKET_SELL, MARKET_BACK, MARKET_BACK_TO_MAIN}:
        return False
    return True


def _external_should_handle_action(player: dict[str, Any], action: str) -> bool:
    if action not in EXTERNAL_LOCATION_BUTTONS:
        return False
    return not _market_should_own_back(player, action)


def _current_city_buttons(player: dict[str, Any]) -> list[list[str]]:
    zone = str(player.get("current_zone") or player.get("location_id") or "")
    for response in CITY_ACTIONS.values():
        if response.zone_id == zone:
            return response.buttons
    return central_square_buttons()


def _unknown_input_result(player: dict[str, Any], text: str) -> WorldActionResult:
    return WorldActionResult(text=text, buttons=_current_city_buttons(player))


def _with_extra_messages(result: WorldActionResult, messages: tuple[str, ...]) -> WorldActionResult:
    if not messages:
        return result
    return WorldActionResult(
        text=result.text,
        buttons=result.buttons,
        scheduled_timer=result.scheduled_timer,
        extra_messages=tuple(messages) + tuple(result.extra_messages),
    )


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
    # Догоняем фоновые время-зависимые эффекты ДО любых ранних возвратов (бой,
    # таймер крафта), иначе бой и «Проверить таймер» не засчитывались бы как
    # активность для суточного счётчика проклятья.
    if advance_player_time(player):
        storage.update_player(player)

    if player.get("in_battle"):
        response = handle_external_location_action(storage, player, action)
        return WorldActionResult(text=response.text, buttons=response.buttons, scheduled_timer=response.scheduled_timer)

    # Active crafting timers are a hard lock: no city shortcuts, slash commands
    # or stale navigation buttons may move the player for one inconsistent step.
    if _has_active_craft_timer(player):
        response = handle_crafting_action(storage, player, action)
        return WorldActionResult(
            text=response.text,
            buttons=response.buttons,
            scheduled_timer=response.scheduled_timer,
        )

    context_changed = False
    context_changed = clear_stale_crafting_context_if_needed(player) or context_changed
    context_changed = _clear_stale_market_context_if_needed(player) or context_changed
    if context_changed:
        storage.update_player(player)

    fine_advance = advance_fine_state(player)
    if fine_advance.changed:
        storage.update_player(player)

    if action in {CITY_HALL_BACK}:
        response = get_city_response("Ратуша")
        updated_player = apply_city_transition(storage, player, response)
        text = build_response_text(storage=storage, player=updated_player, response=response, platform=platform)
        return _with_extra_messages(WorldActionResult(text=text, buttons=response.buttons), fine_advance.messages)

    if action == CITY_FINE_PAY_ACTION:
        zone = str(player.get("current_zone") or player.get("location_id") or "")
        place = "fortress" if zone.startswith("fortress_in_gorge") else "city"
        fine_result = pay_fine(player, place=place)
        storage.update_player(player)
        return _with_extra_messages(WorldActionResult(text=fine_result.text, buttons=fine_result.buttons), fine_advance.messages)

    if should_block_movement_action(player, action):
        storage.update_player(player)
        return _with_extra_messages(
            WorldActionResult(text=movement_block_text(), buttons=movement_block_buttons()),
            fine_advance.messages,
        )

    if action == PROFILE_BUTTON:
        try:
            profile_url = create_profile_site_link(storage, player, platform)
            text = (
                "🌐 Профиль на сайте готов.\n\n"
                f"Ссылка: {profile_url}\n\n"
                "Она привязана к вашему единому игровому ID и действует ограниченное время."
            )
        except Exception:
            logger.exception("Failed to create profile site link for player=%s platform=%s", player.get("game_id"), platform)
            text = "Профиль сейчас недоступен. Попробуйте ещё раз позже."
        return WorldActionResult(text=text, buttons=_current_context_buttons(player))

    fishing_response = handle_fishing_action(storage, player, action)
    if fishing_response is not None:
        return WorldActionResult(
            text=fishing_response.text,
            buttons=fishing_response.buttons,
            scheduled_timer=getattr(fishing_response, "scheduled_timer", None),
        )

    # While outside the city, every non-profile input belongs to the external
    # location router. This prevents old/random city buttons from teleporting
    # the player back into Seldar.
    if _is_external_location_state(player):
        response = handle_external_location_action(storage, player, action)
        return WorldActionResult(text=response.text, buttons=response.buttons, scheduled_timer=response.scheduled_timer)

    if str(action or "").strip().startswith("/"):
        command = str(action or "").strip()
        # Promocodes are single custom commands such as /promo_code.
        # Multi-word slash commands stay with the normal command router.
        if " " not in command and len(command) > 1:
            ok, message = redeem_promo_code(storage, str(player.get("game_id") or ""), command)
            if ok or command.lower().startswith("/promo"):
                storage.update_player(player)
                prefix = "✅" if ok else "⚠️"
                return WorldActionResult(text=f"{prefix} {message}", buttons=_current_context_buttons(player))
        return _unknown_input_result(player, "Неизвестная команда или команда недоступна в этом месте.")

    raid_result = maybe_trigger_raid(player, action)
    if raid_result is not None:
        storage.update_player(player)
        return _with_extra_messages(
            WorldActionResult(text=raid_result.text, buttons=raid_result.buttons),
            fine_advance.messages,
        )

    # Древнее Проклятье: 20% «заблудиться» при хождении по кварталам города.
    if action in CITY_QUARTER_WALK_ACTIONS:
        curse_result = roll_ancient_curse_trigger(player, "city_quarter_walk")
        if curse_result.get("triggered"):
            storage.update_player(player)
            return _with_extra_messages(
                WorldActionResult(
                    text=str(curse_result.get("text") or "Древнее Проклятье переносит вас на Малое плато."),
                    buttons=small_plateau_hidden_coin_buttons(),
                ),
                fine_advance.messages,
            )

    if action in {CENTRAL_SQUARE, BACK_TO_CENTRAL, "В город"}:
        player.pop("crafting_context", None)
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

    if should_handle_crafting_action(player, action):
        response = handle_crafting_action(storage, player, action)
        return WorldActionResult(
            text=response.text,
            buttons=response.buttons,
            scheduled_timer=response.scheduled_timer,
        )

    # Explicit city navigation breaks stale market context. ``Рынок`` is the
    # only city button that intentionally enters the market state machine.
    # External-location labels are handled below so ``Выход из города`` cannot
    # be swallowed by stale market context.
    if action in CITY_ACTIONS and action not in MARKET_ENTRY_ACTIONS and action not in EXTERNAL_LOCATION_BUTTONS:
        player.pop("market_context", None)
        player.pop("crafting_context", None)
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
        player.pop("crafting_context", None)
        response = handle_external_location_action(storage, player, action)
        return WorldActionResult(text=response.text, buttons=response.buttons, scheduled_timer=response.scheduled_timer)

    if _market_should_handle_action(player, action):
        response = handle_market_action(storage, player, action)
        return WorldActionResult(text=response.text, buttons=response.buttons)

    if _is_external_location_state(player):
        response = handle_external_location_action(storage, player, action)
        return WorldActionResult(text=response.text, buttons=response.buttons, scheduled_timer=response.scheduled_timer)

    if action not in CITY_ACTIONS:
        return _unknown_input_result(player, UNKNOWN_CITY_ACTION_TEXT)

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
