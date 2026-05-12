"""Unified Timeweb entry point.

Starts in one process:
1. FastAPI website on APP_HOST:APP_PORT/PORT;
2. VK bot in a background thread;
3. Telegram bot in the main thread through ner_talis_game_project/main.py.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format=LOG_FORMAT,
)
logger = logging.getLogger("timeweb_start")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BASE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = BASE_DIR / "ner_talis_game_project"
APP_STATE = {"status": "starting", "error": ""}
SENSITIVE_ENV_NAMES = ("TELEGRAM_BOT_TOKEN", "VK_GROUP_TOKEN", "DATABASE_URL", "WEB_SESSION_SECRET")


def redact_sensitive_text(text: str) -> str:
    redacted = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot<REDACTED>", text)
    redacted = re.sub(
        r"(TELEGRAM_BOT_TOKEN|VK_GROUP_TOKEN|DATABASE_URL|WEB_SESSION_SECRET)=[^\s`'\"]+",
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


def ensure_import_paths() -> None:
    for path in (PACKAGE_DIR, BASE_DIR):
        raw_path = str(path)
        if raw_path not in sys.path:
            sys.path.insert(0, raw_path)


def load_env_file_if_possible() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    for env_path in (BASE_DIR / ".env", PACKAGE_DIR / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)


def resolve_log_file_path() -> Path | None:
    raw_path = os.getenv("LOG_FILE_PATH", "logs/ner_talis.log").strip()
    if raw_path.casefold() in {"", "off", "none", "-"}:
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else BASE_DIR / path


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

    log_path = resolve_log_file_path()
    if log_path is None:
        return
    for handler in root_logger.handlers:
        if getattr(handler, "_ner_talis_file_handler", False):
            return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler._ner_talis_file_handler = True
    file_handler.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    file_handler.setFormatter(RedactingFormatter(LOG_FORMAT))
    root_logger.addHandler(file_handler)


def get_app_host() -> str:
    return os.getenv("APP_HOST", "0.0.0.0")


def get_app_port() -> int:
    raw_port = os.getenv("APP_PORT") or os.getenv("PORT", "8080")
    try:
        return int(raw_port)
    except ValueError as exc:
        raise RuntimeError(f"APP_PORT/PORT должен быть целым числом, получено: {raw_port!r}") from exc


def start_fastapi_site() -> threading.Thread:
    """Starts FastAPI in a background thread via uvicorn."""

    def run_site() -> None:
        try:
            ensure_import_paths()
            import uvicorn

            logger.info("FastAPI site is starting on %s:%s", get_app_host(), get_app_port())
            uvicorn.run(
                "web_app:app",
                host=get_app_host(),
                port=get_app_port(),
                log_level=os.getenv("UVICORN_LOG_LEVEL", "info").lower(),
                access_log=os.getenv("UVICORN_ACCESS_LOG", "false").casefold() in {"1", "true", "yes", "on"},
            )
        except Exception:
            APP_STATE["status"] = "error"
            APP_STATE["error"] = redact_sensitive_text(traceback.format_exc())
            logger.error("FastAPI site crashed\n%s", APP_STATE["error"])
            raise

    thread = threading.Thread(target=run_site, name="NerTalisFastAPI", daemon=True)
    thread.start()
    return thread


def init_storage() -> None:
    from storage.storage_factory import create_storage

    storage = create_storage()
    if hasattr(storage, "check_connection"):
        storage.check_connection()
    logger.info("Player storage is ready")


def run_bots() -> None:
    try:
        ensure_import_paths()
        import main as game_main

        main_func = getattr(game_main, "main", None)
        if not callable(main_func):
            raise RuntimeError("ner_talis_game_project/main.py должен содержать функцию main().")
        APP_STATE["status"] = "running"
        logger.info("Starting Telegram and VK bots from main.main()")
        main_func()
        APP_STATE["status"] = "stopped"
    except Exception:
        APP_STATE["status"] = "error"
        APP_STATE["error"] = redact_sensitive_text(traceback.format_exc())
        logger.error("Bots crashed\n%s", APP_STATE["error"])
        raise


def main() -> None:
    ensure_import_paths()
    load_env_file_if_possible()
    configure_safe_logging()

    # Timeweb проверяет HTTP-порт. Поэтому сайт стартует первым: /health
    # должен отвечать даже если PostgreSQL временно недоступен или неверно задан.
    start_fastapi_site()

    retry_seconds = max(5, int(os.getenv("APP_RESTART_RETRY_SECONDS", "30")))
    while True:
        try:
            init_storage()
            run_bots()
        except KeyboardInterrupt:
            raise
        except Exception:
            APP_STATE["status"] = "error"
            APP_STATE["error"] = redact_sensitive_text(traceback.format_exc())
            logger.error(
                "Background services are not ready. Retrying in %s seconds.\n%s",
                retry_seconds,
                APP_STATE["error"],
            )
            time.sleep(retry_seconds)


if __name__ == "__main__":
    main()
