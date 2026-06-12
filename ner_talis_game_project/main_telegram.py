from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from project_paths import load_project_env, resolve_project_path
from storage.storage_factory import create_storage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Telegram imports are intentionally lazy. This keeps project smoke tests and
# non-Telegram tooling working even when python-telegram-bot is not installed.
try:  # pragma: no cover - exercised in deployed environment
    from telegram.error import Conflict, TimedOut
except Exception:  # pragma: no cover - local checks without telegram package
    class Conflict(Exception):
        pass

    class TimedOut(Exception):
        pass


def get_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = raw_value.strip().casefold()
    prefix = f"{name}=".casefold()
    if value.startswith(prefix):
        value = value[len(prefix):].strip()
    return value in {"1", "true", "yes", "on", "да"}


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


async def log_telegram_error(update: object, context: Any) -> None:
    error = getattr(context, "error", None)
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


def _import_telegram_runtime():
    try:
        from telegram.ext import (
            Application,
            CommandHandler,
            ConversationHandler,
            MessageHandler,
            filters,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Не установлен python-telegram-bot. Установите зависимости из "
            "ner_talis_game_project/requirements.txt."
        ) from exc

    from handlers.city import CITY_BUTTON_PATTERN, city_command, city_message
    from handlers.registration import (
        AWAITING_GENDER,
        AWAITING_NAME,
        AWAITING_RACE,
        GENDER_CONFIRM,
        NAME_CONFIRM,
        RACE_CARD,
        RACE_CONFIRM,
        START_MENU,
        begin_registration,
        cancel,
        connect_command,
        handle_gender_confirmation,
        handle_name_confirmation,
        handle_race_card,
        handle_race_confirmation,
        link_command,
        profile_button,
        profile_command,
        promo_command,
        receive_gender,
        receive_name,
        receive_race,
        show_world_short,
        start_command,
    )
    from handlers.site_profile import profile_site_button, profile_site_command
    from handlers.telegram_admin import register_telegram_admin_handlers

    return {
        "Application": Application,
        "CommandHandler": CommandHandler,
        "ConversationHandler": ConversationHandler,
        "MessageHandler": MessageHandler,
        "filters": filters,
        "CITY_BUTTON_PATTERN": CITY_BUTTON_PATTERN,
        "city_command": city_command,
        "city_message": city_message,
        "AWAITING_GENDER": AWAITING_GENDER,
        "AWAITING_NAME": AWAITING_NAME,
        "AWAITING_RACE": AWAITING_RACE,
        "GENDER_CONFIRM": GENDER_CONFIRM,
        "NAME_CONFIRM": NAME_CONFIRM,
        "RACE_CARD": RACE_CARD,
        "RACE_CONFIRM": RACE_CONFIRM,
        "START_MENU": START_MENU,
        "begin_registration": begin_registration,
        "cancel": cancel,
        "connect_command": connect_command,
        "handle_gender_confirmation": handle_gender_confirmation,
        "handle_name_confirmation": handle_name_confirmation,
        "handle_race_card": handle_race_card,
        "handle_race_confirmation": handle_race_confirmation,
        "link_command": link_command,
        "profile_button": profile_button,
        "profile_command": profile_command,
        "promo_command": promo_command,
        "receive_gender": receive_gender,
        "receive_name": receive_name,
        "receive_race": receive_race,
        "show_world_short": show_world_short,
        "start_command": start_command,
        "profile_site_button": profile_site_button,
        "profile_site_command": profile_site_command,
        "register_telegram_admin_handlers": register_telegram_admin_handlers,
    }


def build_application():
    runtime = _import_telegram_runtime()
    Application = runtime["Application"]
    CommandHandler = runtime["CommandHandler"]
    ConversationHandler = runtime["ConversationHandler"]
    MessageHandler = runtime["MessageHandler"]
    filters = runtime["filters"]

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
        .get_updates_connect_timeout(get_float_env("TELEGRAM_GET_UPDATES_CONNECT_TIMEOUT", 30.0))
        .get_updates_read_timeout(get_float_env("TELEGRAM_GET_UPDATES_READ_TIMEOUT", 60.0))
        .get_updates_write_timeout(get_float_env("TELEGRAM_GET_UPDATES_WRITE_TIMEOUT", 30.0))
        .get_updates_pool_timeout(get_float_env("TELEGRAM_GET_UPDATES_POOL_TIMEOUT", 30.0))
        .build()
    )
    application.bot_data["storage"] = create_storage(
        resolve_project_path(os.getenv("PLAYERS_STORAGE_PATH", "data/players.json"))
    )
    application.add_error_handler(log_telegram_error)

    runtime["register_telegram_admin_handlers"](application, CommandHandler, MessageHandler, filters)

    registration_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", runtime["start_command"]),
            MessageHandler(filters.Regex("^Кратко о мире$"), runtime["show_world_short"]),
            MessageHandler(filters.Regex("^Начать$"), runtime["begin_registration"]),
        ],
        states={
            runtime["START_MENU"]: [
                MessageHandler(filters.Regex("^Кратко о мире$"), runtime["show_world_short"]),
                MessageHandler(filters.Regex("^Начать$"), runtime["begin_registration"]),
            ],
            runtime["AWAITING_NAME"]: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, runtime["receive_name"]),
            ],
            runtime["NAME_CONFIRM"]: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, runtime["handle_name_confirmation"]),
            ],
            runtime["AWAITING_GENDER"]: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, runtime["receive_gender"]),
            ],
            runtime["GENDER_CONFIRM"]: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, runtime["handle_gender_confirmation"]),
            ],
            runtime["AWAITING_RACE"]: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, runtime["receive_race"]),
            ],
            runtime["RACE_CARD"]: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, runtime["handle_race_card"]),
            ],
            runtime["RACE_CONFIRM"]: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, runtime["handle_race_confirmation"]),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", runtime["cancel"]),
            CommandHandler("profile", runtime["profile_command"]),
            CommandHandler("promo", runtime["promo_command"]),
            CommandHandler("site_profile", runtime["profile_site_command"]),
            CommandHandler("link", runtime["link_command"]),
            CommandHandler("connect", runtime["connect_command"]),
            CommandHandler("start", runtime["start_command"]),
        ],
        allow_reentry=True,
    )

    application.add_handler(registration_conversation)
    application.add_handler(CommandHandler("profile", runtime["profile_command"]))
    application.add_handler(CommandHandler("promo", runtime["promo_command"]))
    application.add_handler(CommandHandler("site_profile", runtime["profile_site_command"]))
    application.add_handler(CommandHandler("link", runtime["link_command"]))
    application.add_handler(CommandHandler("connect", runtime["connect_command"]))
    application.add_handler(CommandHandler("city", runtime["city_command"]))
    application.add_handler(MessageHandler(filters.Regex("^Профиль$"), runtime["profile_button"]))
    application.add_handler(MessageHandler(filters.Regex("^Профиль на сайте$"), runtime["profile_site_button"]))
    application.add_handler(MessageHandler(filters.Regex(runtime["CITY_BUTTON_PATTERN"]), runtime["city_message"]))

    return application


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def run_application(application) -> None:
    """Run Telegram polling and keep the process alive on temporary conflicts."""
    retry_on_conflict = get_bool_env("TELEGRAM_RETRY_ON_CONFLICT", True)
    retry_seconds = max(5, get_int_env("TELEGRAM_CONFLICT_RETRY_SECONDS", 30))

    while True:
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
                drop_pending_updates=get_bool_env("TELEGRAM_DROP_PENDING_UPDATES", False),
            )
            return
        except Conflict:
            if not retry_on_conflict:
                raise
            logger.error(
                "Telegram polling conflict: another bot instance is already using this token. "
                "Stop the duplicate instance. Retrying in %s seconds.",
                retry_seconds,
            )
            time.sleep(retry_seconds)
            application = build_application()
        finally:
            if not loop.is_running() and not loop.is_closed():
                loop.close()
                asyncio.set_event_loop(None)


# Этот модуль используется только как внутренний сборщик Telegram-приложения.
# Единая точка запуска проекта: ner_talis_game_project/main.py
