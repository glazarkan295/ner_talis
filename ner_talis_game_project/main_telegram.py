import asyncio
import logging
import os

from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.city import CITY_BUTTON_PATTERN, city_command, city_message
from handlers.registration import (
    AWAITING_NAME,
    AWAITING_RACE,
    RACE_CARD,
    RACE_CONFIRM,
    START_MENU,
    begin_registration,
    cancel,
    connect_command,
    handle_race_card,
    handle_race_confirmation,
    link_command,
    profile_button,
    profile_command,
    receive_name,
    receive_race,
    show_world_short,
    start_command,
)
from project_paths import load_project_env, resolve_project_path
from storage.storage_factory import create_storage


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def build_application() -> Application:
    load_project_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError("Не указан TELEGRAM_BOT_TOKEN в .env")

    application = Application.builder().token(token).build()
    application.bot_data["storage"] = create_storage(
        resolve_project_path(os.getenv("PLAYERS_STORAGE_PATH", "data/players.json"))
    )

    registration_conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            START_MENU: [
                MessageHandler(filters.Regex("^Кратко о мире$"), show_world_short),
                MessageHandler(filters.Regex("^Начать$"), begin_registration),
            ],
            AWAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
            ],
            AWAITING_RACE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_race),
            ],
            RACE_CARD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_race_card),
            ],
            RACE_CONFIRM: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_race_confirmation,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("profile", profile_command),
            CommandHandler("link", link_command),
            CommandHandler("connect", connect_command),
            CommandHandler("start", start_command),
        ],
        allow_reentry=True,
    )

    application.add_handler(registration_conversation)
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("link", link_command))
    application.add_handler(CommandHandler("connect", connect_command))
    application.add_handler(CommandHandler("city", city_command))
    application.add_handler(MessageHandler(filters.Regex("^Профиль$"), profile_button))
    application.add_handler(MessageHandler(filters.Regex(CITY_BUTTON_PATTERN), city_message))

    return application


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def run_application(application: Application) -> None:
    loop = ensure_event_loop()
    try:
        application.run_polling(allowed_updates=None)
    finally:
        if not loop.is_running() and not loop.is_closed():
            loop.close()
            asyncio.set_event_loop(None)


# Этот модуль используется только как внутренний сборщик Telegram-приложения.
# Единая точка запуска проекта: ner_talis_game_project/main.py
