"""Entry point for Timeweb App Platform.

Starts a small HTTP health server on PORT and then launches the game bots
from the existing main.py. This is useful for app platforms that expect the
container to listen on a port, while Telegram/VK bots themselves use polling.
"""

from __future__ import annotations

import logging
import os
import re
import runpy
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
APP_STATE = {
    "status": "starting",
    "error": "",
}
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


def get_app_dir() -> Path:
    if (BASE_DIR / "main.py").exists():
        return BASE_DIR
    if (PACKAGE_DIR / "main.py").exists():
        return PACKAGE_DIR
    return BASE_DIR


def ensure_import_paths() -> None:
    for path in (get_app_dir(), BASE_DIR):
        raw_path = str(path)
        if raw_path not in sys.path:
            sys.path.insert(0, raw_path)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path in {"/", "/health", "/healthz"}:
            body = b"OK\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/ready":
            status = APP_STATE["status"]
            error = APP_STATE["error"]
            if status == "error":
                body = f"ERROR\n{error}\n".encode("utf-8")
                self.send_response(503)
            else:
                body = f"{status.upper()}\n".encode("utf-8")
                self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("health: " + format, *args)


def load_env_file_if_possible() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    for env_path in (BASE_DIR / ".env", get_app_dir() / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)


def get_port() -> int:
    raw_port = os.getenv("PORT", "8080")
    try:
        return int(raw_port)
    except ValueError as exc:
        raise RuntimeError(f"PORT должен быть целым числом, получено: {raw_port!r}") from exc


def build_health_server() -> ThreadingHTTPServer:
    port = get_port()
    return ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)


def serve_health(server: ThreadingHTTPServer) -> None:
    host, port = server.server_address
    logger.info("Health server started on %s:%s", host, port)
    server.serve_forever()


def start_health_server() -> ThreadingHTTPServer:
    server = build_health_server()
    health_thread = threading.Thread(
        target=serve_health,
        args=(server,),
        name="NerTalisHealthServer",
        daemon=True,
    )
    health_thread.start()
    return server


def run_existing_main() -> None:
    try:
        ensure_import_paths()
        import main as game_main

        main_func = getattr(game_main, "main", None)
        if callable(main_func):
            logger.info("Starting bots from main.main()")
            APP_STATE["status"] = "running"
            main_func()
            APP_STATE["status"] = "stopped"
            return

        logger.info("main.py has no callable main(); running it as __main__")
        APP_STATE["status"] = "running"
        runpy.run_module("main", run_name="__main__")
        APP_STATE["status"] = "stopped"
    except Exception:
        APP_STATE["status"] = "error"
        APP_STATE["error"] = redact_sensitive_text(traceback.format_exc())
        logger.error("Application crashed\n%s", APP_STATE["error"])


def main() -> None:
    ensure_import_paths()
    load_env_file_if_possible()
    configure_safe_logging()
    start_health_server()

    run_existing_main()
    threading.Event().wait()


if __name__ == "__main__":
    main()
