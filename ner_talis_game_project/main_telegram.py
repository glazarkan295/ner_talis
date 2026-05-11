import asyncio
import logging
import os

from telegram.error import TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
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
from handlers.site_profile import profile_site_button, profile_site_command
from project_paths import load_project_env, resolve_project_path
from storage.storage_factory import create_storage


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if not raw_value:
        return default

    value = raw_value.strip()
    prefix = f"{name}="
    if value.startswith(prefix):
        value = value[len(prefix):].strip()

    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(
            f"Переменная окружения {name} должна быть числом, получено: {raw_value!r}"
        ) from exc


def get_int_env(name: str, default: int) -> int:
    return int(get_float_env(name, float(default)))


async def log_telegram_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, TimedOut):
        logger.warning("Telegram API request timed out: %s", error)
        return

    if error is None:
        logger.error("Unhandled Telegram error without exception context")
        return

    logger.error(
        "Unhandled Telegram error",
        exc_info=(type(error), error, error.__traceback__),
    )


def build_application() -> Application:
    load_project_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise RuntimeError("Не указан TELEGRAM_BOT_TOKEN в .env")

    application = (
        Application.builder()
        .token(token)
        .connect_timeout(get_float_env("TELEGRAM_CONNECT_TIMEOUT", 30.0))
        .read_timeout(get_float_env("TELEGRAM_READ_TIMEOUT", 30.0))
        .write_timeout(get_float_env("TELEGRAM_WRITE_TIMEOUT", 30.0))
        .pool_timeout(get_float_env("TELEGRAM_POOL_TIMEOUT", 30.0))
        .get_updates_connect_timeout(
            get_float_env("TELEGRAM_GET_UPDATES_CONNECT_TIMEOUT", 30.0)
        )
        .get_updates_read_timeout(
            get_float_env("TELEGRAM_GET_UPDATES_READ_TIMEOUT", 60.0)
        )
        .get_updates_write_timeout(
            get_float_env("TELEGRAM_GET_UPDATES_WRITE_TIMEOUT", 30.0)
        )
        .get_updates_pool_timeout(
            get_float_env("TELEGRAM_GET_UPDATES_POOL_TIMEOUT", 30.0)
        )
        .build()
    )
    application.bot_data["storage"] = create_storage(
        resolve_project_path(os.getenv("PLAYERS_STORAGE_PATH", "data/players.json"))
    )
    application.add_error_handler(log_telegram_error)

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
            CommandHandler("site_profile", profile_site_command),
            CommandHandler("link", link_command),
            CommandHandler("connect", connect_command),
            CommandHandler("start", start_command),
        ],
        allow_reentry=True,
    )

    application.add_handler(registration_conversation)
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("site_profile", profile_site_command))
    application.add_handler(CommandHandler("link", link_command))
    application.add_handler(CommandHandler("connect", connect_command))
    application.add_handler(CommandHandler("city", city_command))
    application.add_handler(MessageHandler(filters.Regex("^Профиль$"), profile_button))
    application.add_handler(MessageHandler(filters.Regex("^Профиль на сайте$"), profile_site_button))
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
        application.run_polling(
            allowed_updates=None,
            bootstrap_retries=get_int_env("TELEGRAM_BOOTSTRAP_RETRIES", -1),
            timeout=get_int_env("TELEGRAM_POLL_TIMEOUT", 30),
            connect_timeout=get_float_env("TELEGRAM_GET_UPDATES_CONNECT_TIMEOUT", 30.0),
            read_timeout=get_float_env("TELEGRAM_GET_UPDATES_READ_TIMEOUT", 60.0),
            write_timeout=get_float_env("TELEGRAM_GET_UPDATES_WRITE_TIMEOUT", 30.0),
            pool_timeout=get_float_env("TELEGRAM_GET_UPDATES_POOL_TIMEOUT", 30.0),
        )
    finally:
        if not loop.is_running() and not loop.is_closed():
            loop.close()
            asyncio.set_event_loop(None)


# Этот модуль используется только как внутренний сборщик Telegram-приложения.
# Единая точка запуска проекта: ner_talis_game_project/main.py
