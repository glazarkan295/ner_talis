import logging
import os
import threading
import traceback

from handlers.vk_registration import VkRegistrationBot
from main_telegram import build_application, run_application
from project_paths import load_project_env, resolve_project_path

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SUPPORTED_BOT_MODES = {"both", "telegram", "vk"}


def require_env(name: str) -> str:
    value = os.getenv(name)

    if value:
        value = value.strip()

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
        logger.error("VK bot stopped because of an error:\n%s", traceback.format_exc())
        os._exit(1)


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
