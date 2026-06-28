from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from keyboards.reply_keyboards import (
    after_registration_keyboard,
    consent_keyboard,
    gender_confirm_keyboard,
    gender_keyboard,
    name_confirm_keyboard,
    race_card_keyboard,
    race_confirm_keyboard,
    race_keyboard,
    start_keyboard,
)
from services.promo_service import redeem_promo_code
from services import referral_service
from services.registration_service import (
    CONSENT_BUTTON,
    consent_message,
    create_player,
    format_race_card,
    get_race_id_by_name,
    load_races,
    validate_name,
)
from services.web_profile import create_profile_site_link
from storage.base import PlayerStorage
from texts.registration_texts import (
    ASK_GENDER_TEXT,
    ASK_NAME_AGAIN_TEXT,
    ASK_NAME_TEXT,
    ASK_RACE_TEXT,
    FINAL_REGISTRATION_TEXT,
    GENDER_WARNING_TEXT,
    NAME_CONFIRM_TEXT_TEMPLATE,
    WORLD_SHORT_TEXT,
)

(
    CONSENT_GATE,
    START_MENU,
    AWAITING_NAME,
    NAME_CONFIRM,
    AWAITING_GENDER,
    GENDER_CONFIRM,
    AWAITING_RACE,
    RACE_CARD,
    RACE_CONFIRM,
) = range(9)
TELEGRAM_PLATFORM = "telegram"


def get_storage(context: ContextTypes.DEFAULT_TYPE) -> PlayerStorage:
    return context.bot_data["storage"]


def get_external_user_id(update: Update) -> str:
    return str(update.effective_user.id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)
    context.user_data.clear()

    if player is not None:
        await update.message.reply_text(
            "Ты уже зарегистрирован. Команда /start повторно не запускает регистрацию."
        )
        return ConversationHandler.END

    # Реферальная ссылка: deep-link payload «/start ref_<код>» запоминаем до конца
    # регистрации, чтобы привязать новичка к рефереру.
    args = getattr(context, "args", None)
    if isinstance(args, (list, tuple)) and args:
        ref_code = referral_service.parse_referral_code(" ".join(str(a) for a in args))
        if ref_code:
            context.user_data["referral_code"] = ref_code

    # Сначала — согласие с документами, и только после него — меню начала игры.
    await update.message.reply_text(
        consent_message(),
        reply_markup=consent_keyboard(),
        disable_web_page_preview=True,
    )
    return CONSENT_GATE


async def accept_consent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)
    if player is not None:
        await update.message.reply_text(
            "Ты уже зарегистрирован.",
            reply_markup=after_registration_keyboard(),
        )
        return ConversationHandler.END
    # Запоминаем согласие на уровне пользователя, чтобы кнопки «Начать»/«Кратко
    # о мире» (которые являются точками входа диалога) не могли провести нового
    # игрока в регистрацию в обход экрана согласия.
    context.user_data["consent_given"] = True
    await update.message.reply_text(
        "Спасибо! Выберите действие:",
        reply_markup=start_keyboard(),
    )
    return START_MENU


async def _require_consent_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Показывает экран согласия, если игрок ещё его не подтверждал."""
    if context.user_data.get("consent_given"):
        return False
    await update.message.reply_text(
        consent_message(),
        reply_markup=consent_keyboard(),
        disable_web_page_preview=True,
    )
    return True


async def show_world_short(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _require_consent_gate(update, context):
        return CONSENT_GATE
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

    # Регистрация недоступна без подтверждённого согласия (закрывает обход через
    # точку входа «Начать» для игрока, который не проходил экран согласия).
    if await _require_consent_gate(update, context):
        return CONSENT_GATE

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

    context.user_data["registration_pending_name"] = result

    await update.message.reply_text(
        NAME_CONFIRM_TEXT_TEMPLATE.format(player_name=result),
        reply_markup=name_confirm_keyboard(),
    )
    return NAME_CONFIRM


async def handle_name_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    storage = get_storage(context)
    text = update.message.text

    if text == "Ввести заново":
        context.user_data.pop("registration_pending_name", None)
        context.user_data.pop("registration_name", None)
        await update.message.reply_text(ASK_NAME_AGAIN_TEXT)
        return AWAITING_NAME

    if text != "Подтвердить":
        await update.message.reply_text(
            "Выбери действие на клавиатуре: «Подтвердить» или «Ввести заново».",
            reply_markup=name_confirm_keyboard(),
        )
        return NAME_CONFIRM

    pending_name = context.user_data.get("registration_pending_name")
    if not pending_name:
        await update.message.reply_text(ASK_NAME_AGAIN_TEXT)
        return AWAITING_NAME

    if storage.is_name_taken(pending_name):
        context.user_data.pop("registration_pending_name", None)
        await update.message.reply_text(
            "Пока ты подтверждал имя, его уже заняли. Введи другое имя."
        )
        return AWAITING_NAME

    context.user_data["registration_name"] = pending_name
    context.user_data.pop("registration_pending_name", None)

    await update.message.reply_text(ASK_GENDER_TEXT)
    await update.message.reply_text(
        GENDER_WARNING_TEXT,
        reply_markup=gender_keyboard(),
    )
    return AWAITING_GENDER


def _gender_choice_from_text(text: str) -> tuple[str, str] | None:
    if text == "Муж.":
        return "male", "Муж."
    if text == "Жен.":
        return "female", "Жен."
    return None


async def receive_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = _gender_choice_from_text(update.message.text)

    if choice is None:
        await update.message.reply_text(
            "Выбери пол кнопкой на клавиатуре.",
            reply_markup=gender_keyboard(),
        )
        return AWAITING_GENDER

    gender_id, gender_label = choice
    context.user_data["registration_pending_gender"] = gender_id
    context.user_data["registration_pending_gender_label"] = gender_label

    await update.message.reply_text(
        "— Вы уверены?",
        reply_markup=gender_confirm_keyboard(),
    )
    return GENDER_CONFIRM


async def handle_gender_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if text == "Нет":
        context.user_data.pop("registration_pending_gender", None)
        context.user_data.pop("registration_pending_gender_label", None)
        await update.message.reply_text(
            "— Какого вы пола?",
            reply_markup=gender_keyboard(),
        )
        return AWAITING_GENDER

    if text != "Да":
        await update.message.reply_text(
            "Выбери действие на клавиатуре: «Да» или «Нет».",
            reply_markup=gender_confirm_keyboard(),
        )
        return GENDER_CONFIRM

    gender_id = context.user_data.get("registration_pending_gender")
    gender_label = context.user_data.get("registration_pending_gender_label")

    if not gender_id or not gender_label:
        await update.message.reply_text(
            "— Какого вы пола?",
            reply_markup=gender_keyboard(),
        )
        return AWAITING_GENDER

    context.user_data["registration_gender"] = gender_id
    context.user_data["registration_gender_label"] = gender_label
    context.user_data.pop("registration_pending_gender", None)
    context.user_data.pop("registration_pending_gender_label", None)

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

    gender_id = context.user_data.get("registration_gender")
    gender_label = context.user_data.get("registration_gender_label")

    if not name or not race_id or not gender_id or not gender_label:
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
        gender_id=context.user_data.get("registration_gender"),
        gender_label=context.user_data.get("registration_gender_label"),
    )
    # Реферал (15-CODEX §6): помечаем новичка ДО сохранения (referred_by попадёт
    # в его запись), но начисляем рефереру ТОЛЬКО ПОСЛЕ успешного создания —
    # иначе при сбое save_new_player у реферера остался бы фиктивный приглашённый.
    referral_code = context.user_data.get("referral_code")
    if referral_code:
        try:
            referral_service.mark_referred_by(player, referral_code)
        except Exception:
            pass
    storage.save_new_player(player, TELEGRAM_PLATFORM, external_user_id)
    if player.get("referred_by"):
        try:
            referral_service.credit_referrer(storage, player)
        except Exception:
            pass
    context.user_data.clear()

    await update.message.reply_text(
        FINAL_REGISTRATION_TEXT.format(player_name=player["name"]),
        reply_markup=after_registration_keyboard(),
    )
    return ConversationHandler.END


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)

    if player is None:
        await update.message.reply_text(
            "У тебя ещё нет персонажа. Нажми /start и выбери «Начать».\n\n"
            "Если персонаж уже создан в VK, введи /connect код_привязки.",
            reply_markup=start_keyboard(),
        )
        return None

    profile_url = create_profile_site_link(storage, player, TELEGRAM_PLATFORM)
    # Не передаём reply_markup: кнопка «Профиль» должна выдать ссылку,
    # но не менять текущую клавиатуру локации, боя или лагеря.
    await update.message.reply_text(
        f"🔮 Временная ссылка на профиль игрока {player['name']}:\n"
        f"Единый игровой ID: {player['game_id']}\n"
        f"Ссылка: {profile_url}\n\n"
        "Ссылка действует ограниченное время. Когда она истечёт, нажми «Профиль» ещё раз.",
        disable_web_page_preview=True,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def profile_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await profile_command(update, context)


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)

    if player is None:
        await update.message.reply_text(
            "Сначала нужно создать персонажа. Нажми /start и выбери «Начать».",
            reply_markup=start_keyboard(),
        )
        return None

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
    context.user_data.clear()
    return ConversationHandler.END


async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    code = "".join(context.args).strip() if context.args else ""

    if not code:
        await update.message.reply_text(
            "Введите код привязки. Пример:\n/connect AB12CD",
            reply_markup=start_keyboard(),
        )
        return None

    ok, message, player = storage.connect_platform_by_code(
        code=code,
        platform=TELEGRAM_PLATFORM,
        external_user_id=external_user_id,
    )

    if not ok:
        await update.message.reply_text(message, reply_markup=start_keyboard())
        return None

    context.user_data.clear()
    await update.message.reply_text(
        f"✅ {message}\n\n"
        f"Персонаж: {player['name']}\n"
        f"Единый игровой ID: {player['game_id']}",
        reply_markup=after_registration_keyboard(),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Регистрация отменена. Чтобы начать заново, нажми /start.",
        reply_markup=start_keyboard(),
    )
    return ConversationHandler.END


async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)
    if player is None:
        await update.message.reply_text(
            "Сначала нужно создать персонажа. Нажми /start и выбери «Начать».",
            reply_markup=start_keyboard(),
        )
        return None

    args = getattr(context, "args", []) or []
    code = " ".join(str(arg) for arg in args).strip()
    if not code:
        await update.message.reply_text("Формат: /promo CODE")
        return None

    ok, message = redeem_promo_code(storage, str(player.get("game_id")), code)
    prefix = "✅" if ok else "⚠️"
    await update.message.reply_text(f"{prefix} {message}")
    context.user_data.clear()
    return ConversationHandler.END
