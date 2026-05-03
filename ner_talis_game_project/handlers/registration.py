from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from keyboards.reply_keyboards import (
    after_registration_keyboard,
    race_card_keyboard,
    race_confirm_keyboard,
    race_keyboard,
    start_keyboard,
)
from services.registration_service import (
    build_profile_url,
    create_player,
    format_race_card,
    get_race_id_by_name,
    load_races,
    validate_name,
)
from storage.json_storage import JsonStorage
from texts.registration_texts import (
    ASK_NAME_TEXT,
    ASK_RACE_TEXT,
    FINAL_REGISTRATION_TEXT,
    WORLD_SHORT_TEXT,
)

START_MENU, AWAITING_NAME, AWAITING_RACE, RACE_CARD, RACE_CONFIRM = range(5)
TELEGRAM_PLATFORM = "telegram"


def get_storage(context: ContextTypes.DEFAULT_TYPE) -> JsonStorage:
    return context.bot_data["storage"]


def get_external_user_id(update: Update) -> str:
    return str(update.effective_user.id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=start_keyboard(),
    )
    return START_MENU


async def show_world_short(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        WORLD_SHORT_TEXT,
        reply_markup=start_keyboard(),
    )
    return START_MENU


async def begin_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)

    if player is not None:
        await update.message.reply_text(
            "Ты уже зарегистрирован. Можно идти в город или открыть профиль.",
            reply_markup=after_registration_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(ASK_NAME_TEXT)
    return AWAITING_NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    storage = get_storage(context)
    raw_name = update.message.text
    is_valid, result = validate_name(raw_name)

    if not is_valid:
        await update.message.reply_text(result)
        return AWAITING_NAME

    if storage.is_name_taken(result):
        await update.message.reply_text(
            "Такое имя уже зарегистрировано. Введите другое имя."
        )
        return AWAITING_NAME

    context.user_data["registration_name"] = result

    await update.message.reply_text(
        ASK_RACE_TEXT,
        reply_markup=race_keyboard(),
    )
    return AWAITING_RACE


async def receive_race(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    races = load_races()
    race_id = get_race_id_by_name(races, update.message.text)

    if race_id is None:
        await update.message.reply_text(
            "Такой расы нет. Выбери расу с клавиатуры.",
            reply_markup=race_keyboard(),
        )
        return AWAITING_RACE

    context.user_data["registration_race_id"] = race_id

    await update.message.reply_text(
        format_race_card(race_id, races),
        reply_markup=race_card_keyboard(),
    )
    return RACE_CARD


async def handle_race_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if text == "Назад":
        await update.message.reply_text(
            "Выбери расу:",
            reply_markup=race_keyboard(),
        )
        return AWAITING_RACE

    if text == "Выбрать":
        races = load_races()
        race_id = context.user_data.get("registration_race_id")
        if not race_id:
            await update.message.reply_text(
                "Сначала выбери расу.",
                reply_markup=race_keyboard(),
            )
            return AWAITING_RACE

        race_name = races[race_id]["name"]
        await update.message.reply_text(
            f"Ты уверен, что хочешь выбрать расу: {race_name}?",
            reply_markup=race_confirm_keyboard(),
        )
        return RACE_CONFIRM

    await update.message.reply_text(
        "Выбери действие на клавиатуре: «Выбрать» или «Назад».",
        reply_markup=race_card_keyboard(),
    )
    return RACE_CARD


async def handle_race_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    storage = get_storage(context)
    text = update.message.text
    races = load_races()
    race_id = context.user_data.get("registration_race_id")

    if text == "Нет":
        if not race_id:
            await update.message.reply_text(
                "Выбери расу:",
                reply_markup=race_keyboard(),
            )
            return AWAITING_RACE

        await update.message.reply_text(
            format_race_card(race_id, races),
            reply_markup=race_card_keyboard(),
        )
        return RACE_CARD

    if text != "Да":
        await update.message.reply_text(
            "Выбери действие на клавиатуре: «Да» или «Нет».",
            reply_markup=race_confirm_keyboard(),
        )
        return RACE_CONFIRM

    external_user_id = get_external_user_id(update)
    name = context.user_data.get("registration_name")

    if not name or not race_id:
        context.user_data.clear()
        await update.message.reply_text(
            "Данные регистрации потеряны. Нажми /start и начни заново.",
            reply_markup=start_keyboard(),
        )
        return ConversationHandler.END

    if storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id) is not None:
        await update.message.reply_text(
            "Персонаж уже создан.",
            reply_markup=after_registration_keyboard(),
        )
        return ConversationHandler.END

    if storage.is_name_taken(name):
        await update.message.reply_text(
            "Пока ты выбирал расу, это имя уже заняли. Введи другое имя."
        )
        return AWAITING_NAME

    game_id = storage.generate_game_id()
    player = create_player(
        game_id=game_id,
        platform=TELEGRAM_PLATFORM,
        external_user_id=external_user_id,
        name=name,
        race_id=race_id,
        races=races,
    )
    storage.save_new_player(player, TELEGRAM_PLATFORM, external_user_id)
    context.user_data.clear()

    await update.message.reply_text(
        FINAL_REGISTRATION_TEXT.format(player_name=player["name"]),
        reply_markup=after_registration_keyboard(),
    )
    return ConversationHandler.END


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)

    if player is None:
        await update.message.reply_text(
            "У тебя ещё нет персонажа. Нажми /start и выбери «Начать».\n\n"
            "Если персонаж уже создан в VK, введи /connect код_привязки.",
            reply_markup=start_keyboard(),
        )
        return

    profile_url = build_profile_url(player)
    await update.message.reply_text(
        f"🔮 Профиль игрока {player['name']}:\n"
        f"Единый игровой ID: {player['game_id']}\n"
        f"Ссылка: {profile_url}",
        reply_markup=after_registration_keyboard(),
    )


async def profile_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await profile_command(update, context)


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)

    if player is None:
        await update.message.reply_text(
            "Сначала нужно создать персонажа. Нажми /start и выбери «Начать».",
            reply_markup=start_keyboard(),
        )
        return

    code = storage.create_link_code(player["game_id"])
    await update.message.reply_text(
        "🔗 Код привязки создан.\n\n"
        f"Единый игровой ID: {player['game_id']}\n"
        f"Код: {code}\n\n"
        "Открой VK-бота и введи:\n"
        f"/connect {code}\n\n"
        "Код одноразовый и действует 15 минут.",
        reply_markup=after_registration_keyboard(),
    )


async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    code = "".join(context.args).strip() if context.args else ""

    if not code:
        await update.message.reply_text(
            "Введите код привязки. Пример:\n/connect AB12CD",
            reply_markup=start_keyboard(),
        )
        return

    ok, message, player = storage.connect_platform_by_code(
        code=code,
        platform=TELEGRAM_PLATFORM,
        external_user_id=external_user_id,
    )

    if not ok:
        await update.message.reply_text(message, reply_markup=start_keyboard())
        return

    await update.message.reply_text(
        f"✅ {message}\n\n"
        f"Персонаж: {player['name']}\n"
        f"Единый игровой ID: {player['game_id']}",
        reply_markup=after_registration_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Регистрация отменена. Чтобы начать заново, нажми /start.",
        reply_markup=start_keyboard(),
    )
    return ConversationHandler.END
