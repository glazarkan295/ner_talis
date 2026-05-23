import asyncio
import logging
import os
import re
import threading
import time
import traceback
from typing import Any

from project_paths import load_project_env, resolve_project_path

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

logging.basicConfig(
    format=LOG_FORMAT,
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SENSITIVE_ENV_NAMES = ("TELEGRAM_BOT_TOKEN", "VK_GROUP_TOKEN")

# Эти имена оставлены на уровне модуля, чтобы smoke-тесты могли подменять их
# без установки telegram/vk зависимостей. Реальные импорты выполняются лениво.
build_application = None
run_application = None
VkRegistrationBot = None


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
        os.environ[name] = value

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


def get_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    value = normalize_env_value(name, raw_value).casefold()
    return value in {"1", "true", "yes", "on", "да"}


def get_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(float(normalize_env_value(name, raw_value)))
    except ValueError:
        logger.warning("Переменная окружения %s должна быть числом, получено: %r", name, raw_value)
        return default


def get_telegram_application_builder():
    if callable(build_application):
        return build_application

    from main_telegram import build_application as real_build_application

    return real_build_application


def get_telegram_application_runner():
    if callable(run_application):
        return run_application

    if callable(build_application):
        return lambda application: application.run_polling(allowed_updates=None)

    from main_telegram import run_application as real_run_application

    return real_run_application


def get_vk_bot_class():
    if callable(VkRegistrationBot):
        return VkRegistrationBot

    from handlers.vk_admin_runtime import patch_vk_registration_bot
    from handlers.vk_registration import VkRegistrationBot as RealVkRegistrationBot

    return patch_vk_registration_bot(RealVkRegistrationBot)


def build_vk_bot() -> Any:
    token = require_env("VK_GROUP_TOKEN")
    group_id = require_int_env("VK_GROUP_ID")
    storage_path = str(
        resolve_project_path(os.getenv("PLAYERS_STORAGE_PATH", "data/players.json"))
    )

    return get_vk_bot_class()(
        token=token,
        group_id=group_id,
        storage_path=storage_path,
    )


def run_vk_bot() -> None:
    """Запускает VK-бота внутри фонового потока."""
    retry_on_error = get_bool_env("VK_RESTART_ON_ERROR", True)
    retry_seconds = max(5, get_int_env("VK_RESTART_RETRY_SECONDS", 30))

    while True:
        try:
            logger.info("VK bot is starting")
            build_vk_bot().run()
            return
        except Exception:
            logger.error(
                "VK bot stopped because of an error:\n%s",
                redact_sensitive_text(traceback.format_exc()),
            )
            if not retry_on_error:
                raise
            logger.info("VK bot will restart in %s seconds", retry_seconds)
            time.sleep(retry_seconds)


def start_vk_thread() -> threading.Thread:
    thread = threading.Thread(
        target=run_vk_bot,
        name="NerTalisVKBot",
        daemon=True,
    )
    thread.start()
    return thread


def build_telegram_bot_application() -> Any:
    logger.info("Telegram bot is starting")
    return get_telegram_application_builder()()


def run_telegram_application(telegram_application: Any) -> None:
    get_telegram_application_runner()(telegram_application)


def run_telegram_bot() -> None:
    run_telegram_application(build_telegram_bot_application())



def _timer_worker_interval_seconds() -> int:
    return int(os.getenv("TIMER_RECOVERY_INTERVAL_SECONDS", "30") or 30)


def recover_telegram_runtime_timers(telegram_application: Any, storage: Any) -> int:
    """Recover Telegram timer notifications without depending on VK modules."""

    from services.runtime_timer_scheduler import recover_saved_timers, start_persistent_timer_worker

    try:
        from keyboards.reply_keyboards import make_keyboard as telegram_keyboard
    except ModuleNotFoundError:
        logger.warning("Telegram timer recovery skipped: telegram keyboard dependencies are unavailable")
        return 0

    def send_telegram(_platform: str, target_id: str, response: Any) -> None:
        asyncio.run(
            telegram_application.bot.send_message(
                chat_id=int(target_id),
                text=response.text,
                reply_markup=telegram_keyboard(response.buttons),
                disable_web_page_preview=True,
            )
        )

    recovered = recover_saved_timers(
        storage=storage,
        send_callback=send_telegram,
        platform_filter="telegram",
        schedule_future=True,
    )
    start_persistent_timer_worker(
        storage=storage,
        send_callback=send_telegram,
        platform_filter="telegram",
        interval_seconds=_timer_worker_interval_seconds(),
    )
    return recovered


def recover_vk_runtime_timers(storage: Any) -> int:
    """Recover VK timer notifications independently from Telegram recovery."""

    if not os.getenv("VK_GROUP_TOKEN"):
        return 0

    from services.runtime_timer_scheduler import recover_saved_timers, start_persistent_timer_worker

    try:
        from keyboards.vk_keyboards import make_keyboard as vk_keyboard
        from vk_api.utils import get_random_id
        import vk_api
    except ModuleNotFoundError:
        logger.warning("VK timer recovery skipped: vk_api dependencies are unavailable")
        return 0

    vk_api_client = vk_api.VkApi(token=require_env("VK_GROUP_TOKEN")).get_api()

    def send_vk(_platform: str, target_id: str, response: Any) -> None:
        vk_api_client.messages.send(
            peer_id=int(target_id),
            message=response.text,
            random_id=get_random_id(),
            keyboard=vk_keyboard(response.buttons),
        )

    recovered = recover_saved_timers(
        storage=storage,
        send_callback=send_vk,
        platform_filter="vk",
        schedule_future=True,
    )
    start_persistent_timer_worker(
        storage=storage,
        send_callback=send_vk,
        platform_filter="vk",
        interval_seconds=_timer_worker_interval_seconds(),
    )
    return recovered


def recover_runtime_timers(telegram_application: Any) -> None:
    """Restore real-time search/rest notifications after app restart."""
    bot_data = getattr(telegram_application, "bot_data", None)
    if not isinstance(bot_data, dict):
        return

    storage = bot_data.get("storage")
    if storage is None:
        return

    telegram_count = 0
    vk_count = 0
    try:
        telegram_count = recover_telegram_runtime_timers(telegram_application, storage)
    except Exception:
        logger.error("Telegram timer recovery failed:\n%s", redact_sensitive_text(traceback.format_exc()))

    try:
        vk_count = recover_vk_runtime_timers(storage)
    except Exception:
        logger.error("VK timer recovery failed:\n%s", redact_sensitive_text(traceback.format_exc()))

    if telegram_count or vk_count:
        logger.info(
            "Recovered persisted timers: telegram=%s, vk=%s",
            telegram_count,
            vk_count,
        )

def run_bots() -> None:
    """Запускает Telegram и VK из единой точки входа.

    Раздельных режимов запуска больше нет: проект всегда поднимает оба бота.
    Telegram-бот работает в основном потоке, потому что python-telegram-bot
    управляет своим event loop и обработчиками остановки процесса.
    VK-бот работает параллельно в фоновом потоке.
    """
    telegram_application = build_telegram_bot_application()
    recover_runtime_timers(telegram_application)
    start_vk_thread()
    run_telegram_application(telegram_application)


def main() -> None:
    load_project_env()
    configure_safe_logging()

    # Единый запуск требует сразу все переменные для обоих ботов.
    require_env("TELEGRAM_BOT_TOKEN")
    require_env("VK_GROUP_TOKEN")
    require_int_env("VK_GROUP_ID")

    run_bots()


if __name__ == "__main__":
    main()
