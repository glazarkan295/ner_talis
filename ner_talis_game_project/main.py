import logging
import os
import re
import threading
import traceback

from handlers.vk_registration import VkRegistrationBot
from main_telegram import build_application, run_application
from project_paths import load_project_env, resolve_project_path

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

logging.basicConfig(
    format=LOG_FORMAT,
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SUPPORTED_BOT_MODES = {"both", "telegram", "vk"}
SENSITIVE_ENV_NAMES = ("TELEGRAM_BOT_TOKEN", "VK_GROUP_TOKEN")


def redact_sensitive_text(text: str) -> str:
    redacted = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot<REDACTED>", text)
    redacted = re.sub(
        r"(TELEGRAM_BOT_TOKEN|VK_GROUP_TOKEN)=[^\s`'\"]+",
        r"\1=<REDACTED>",
        redacted,
    )

    for name in SENSITIVE_ENV_NAMES:
        value = os.getenv(name, "").strip()
        if value.startswith(f"{name}="):
            value = value.split("=", 1)[1].strip()
        if len(value) >= 8:
            redacted = redacted.replace(value, "<REDACTED>")

    return redacted


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record))


def configure_safe_logging() -> None:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        formatter = handler.formatter
        if getattr(formatter, "_redacts_sensitive_text", False):
            continue

        safe_formatter = RedactingFormatter(
            fmt=getattr(formatter, "_fmt", LOG_FORMAT),
            datefmt=getattr(formatter, "datefmt", None),
        )
        safe_formatter._redacts_sensitive_text = True
        handler.setFormatter(safe_formatter)


def normalize_env_value(name: str, value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()

    prefix = f"{name}="
    if value.startswith(prefix):
        logger.warning(
            "Переменная окружения %s содержит префикс %r. "
            "В Timeweb указывайте имя переменной отдельно, а в значение вставляйте только значение.",
            name,
            prefix,
        )
        value = value[len(prefix):].strip()

    return value


def require_env(name: str) -> str:
    value = os.getenv(name)

    if value:
        value = normalize_env_value(name, value)

    if not value:
        similar_vars = [
            key for key in os.environ.keys()
            if "TELEGRAM" in key or "TOKEN" in key or "VK" in key
        ]

        raise RuntimeError(
            f"Не указана переменная окружения {name}. "
            f"Контейнер не видит эту переменную. "
            f"Похожие найденные переменные: {similar_vars}"
        )

    return value


def require_int_env(name: str) -> int:
    value = require_env(name)
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"Переменная окружения {name} должна быть целым числом, получено: {value!r}"
        ) from exc


def get_bot_mode() -> str:
    mode = os.getenv("BOT_MODE", "both").strip().casefold()
    if mode not in SUPPORTED_BOT_MODES:
        raise RuntimeError(
            "Некорректный BOT_MODE. "
            f"Допустимые значения: {', '.join(sorted(SUPPORTED_BOT_MODES))}."
        )
    return mode


def build_vk_bot() -> VkRegistrationBot:
    token = require_env("VK_GROUP_TOKEN")
    group_id = require_int_env("VK_GROUP_ID")
    storage_path = str(
        resolve_project_path(os.getenv("PLAYERS_STORAGE_PATH", "data/players.json"))
    )

    return VkRegistrationBot(
        token=token,
        group_id=group_id,
        storage_path=storage_path,
    )


def run_vk_bot() -> None:
    """Запускает VK-бота внутри фонового потока."""
    try:
        logger.info("VK bot is starting")
        build_vk_bot().run()
    except Exception:
        logger.error(
            "VK bot stopped because of an error:\n%s",
            redact_sensitive_text(traceback.format_exc()),
        )
        raise


def start_vk_thread() -> threading.Thread:
    thread = threading.Thread(
        target=run_vk_bot,
        name="NerTalisVKBot",
        daemon=True,
    )
    thread.start()
    return thread


def run_bots(bot_mode: str) -> None:
    """Запускает оба бота из одной точки входа.

    Telegram-бот работает в основном потоке, потому что python-telegram-bot
    управляет своим event loop и обработчиками остановки процесса.
    VK-бот работает параллельно в фоновом потоке.
    """
    if bot_mode == "vk":
        run_vk_bot()
        return

    if bot_mode == "both":
        start_vk_thread()

    logger.info("Telegram bot is starting")
    telegram_application = build_application()
    run_application(telegram_application)


def main() -> None:
    load_project_env()
    configure_safe_logging()
    bot_mode = get_bot_mode()

    # Проверяем все ключевые переменные заранее, чтобы запуск не был частичным.
    if bot_mode in {"both", "telegram"}:
        require_env("TELEGRAM_BOT_TOKEN")
    if bot_mode in {"both", "vk"}:
        require_env("VK_GROUP_TOKEN")
        require_int_env("VK_GROUP_ID")

    run_bots(bot_mode)


if __name__ == "__main__":
    main()
