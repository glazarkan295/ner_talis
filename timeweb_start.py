"""Entry point for Timeweb App Platform.

Starts a small HTTP health server on PORT and then launches the game bots
from the existing main.py. This is useful for app platforms that expect the
container to listen on a port, while Telegram/VK bots themselves use polling.
"""

from __future__ import annotations

import logging
import os
import runpy
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("timeweb_start")

BASE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = BASE_DIR / "ner_talis_game_project"


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
            main_func()
            return

        logger.info("main.py has no callable main(); running it as __main__")
        runpy.run_module("main", run_name="__main__")
    except Exception:
        logger.exception("Application crashed")
        raise


def main() -> None:
    ensure_import_paths()
    load_env_file_if_possible()
    start_health_server()

    run_existing_main()


if __name__ == "__main__":
    main()
