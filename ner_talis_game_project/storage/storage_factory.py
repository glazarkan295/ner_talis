import os
from pathlib import Path
from typing import Any

from project_paths import resolve_project_path
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


def normalize_env_value(name: str, value: str | Path | None, default: str | None = None) -> str:
    raw = str(value if value is not None else (default or "")).strip().strip("'\"")
    prefix = f"{name}="
    if raw.casefold().startswith(prefix.casefold()):
        raw = raw[len(prefix):].strip().strip("'\"")
    return raw


def normalize_backend(value: str | None) -> str:
    backend = normalize_env_value("STORAGE_BACKEND", value, "sqlite").casefold()
    if backend in {"postgres", "postgresql"}:
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("Для STORAGE_BACKEND=postgres нужно указать DATABASE_URL.")
        return "postgres"
    if backend in {"sqlite", "json"}:
        return backend
    raise RuntimeError("Некорректный STORAGE_BACKEND. Допустимые значения: postgres, sqlite, json.")


def create_storage(default_json_path: str | Path | None = None) -> Any:
    """Создаёт хранилище профилей игроков.

    Для Timeweb/продакшена рекомендуется PostgreSQL:
        STORAGE_BACKEND=postgres
        DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME

    Для локальной разработки доступны SQLite и JSON.
    """
    backend = normalize_backend(os.getenv("STORAGE_BACKEND", "sqlite"))

    legacy_json_path = resolve_project_path(
        normalize_env_value(
            "PLAYERS_STORAGE_PATH",
            os.getenv("PLAYERS_STORAGE_PATH"),
            str(default_json_path or "data/players.json"),
        )
    )

    if backend == "json":
        return JsonStorage(str(legacy_json_path))

    if backend == "sqlite":
        sqlite_path = resolve_project_path(
            normalize_env_value("SQLITE_STORAGE_PATH", os.getenv("SQLITE_STORAGE_PATH"), "data/players.sqlite3")
        )
        return SQLiteStorage(str(sqlite_path), legacy_json_path=str(legacy_json_path))

    if backend == "postgres":
        from storage.postgres_storage import PostgresStorage

        return PostgresStorage(legacy_json_path=str(legacy_json_path))

    raise RuntimeError("Некорректный STORAGE_BACKEND. Допустимые значения: postgres, sqlite, json.")
