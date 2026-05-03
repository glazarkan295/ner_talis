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


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Не указана переменная {name} в .env")
    return value


def build_vk_bot() -> VkRegistrationBot:
    token = require_env("VK_GROUP_TOKEN")
    group_id = int(require_env("VK_GROUP_ID"))
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
        raise


def start_vk_thread() -> threading.Thread:
    thread = threading.Thread(
        target=run_vk_bot,
        name="NerTalisVKBot",
        daemon=True,
    )
    thread.start()
    return thread


def run_bots() -> None:
    """Запускает оба бота из одной точки входа.

    Telegram-бот работает в основном потоке, потому что python-telegram-bot
    управляет своим event loop и обработчиками остановки процесса.
    VK-бот работает параллельно в фоновом потоке.
    """
    start_vk_thread()

    logger.info("Telegram bot is starting")
    telegram_application = build_application()
    run_application(telegram_application)


def main() -> None:
    load_project_env()

    # Проверяем все ключевые переменные заранее, чтобы запуск не был частичным.
    require_env("TELEGRAM_BOT_TOKEN")
    require_env("VK_GROUP_TOKEN")
    require_env("VK_GROUP_ID")

    run_bots()


if __name__ == "__main__":
    main()
