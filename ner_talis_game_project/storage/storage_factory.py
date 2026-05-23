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


def is_production_environment() -> bool:
    value = normalize_env_value("APP_ENV", os.getenv("APP_ENV"), "development").casefold()
    return value in {"prod", "production", "timeweb"}


def allow_json_storage_in_production() -> bool:
    value = normalize_env_value("ALLOW_JSON_STORAGE_IN_PRODUCTION", os.getenv("ALLOW_JSON_STORAGE_IN_PRODUCTION"), "false").casefold()
    return value in {"1", "true", "yes", "on", "да"}


def normalize_backend(value: str | None) -> str:
    backend = normalize_env_value("STORAGE_BACKEND", value, "sqlite").casefold()
    if backend in {"postgres", "postgresql"}:
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("Для STORAGE_BACKEND=postgres нужно указать DATABASE_URL.")
        return "postgres"
    if backend == "json":
        if is_production_environment() and not allow_json_storage_in_production():
            raise RuntimeError(
                "STORAGE_BACKEND=json нельзя использовать в production: "
                "данные игроков и промокодов могут потеряться или получить гонки. "
                "Используйте STORAGE_BACKEND=postgres, либо явно задайте "
                "ALLOW_JSON_STORAGE_IN_PRODUCTION=true только для временного ручного запуска."
            )
        return "json"
    if backend == "sqlite":
        return backend
    raise RuntimeError("Некорректный STORAGE_BACKEND. Допустимые значения: postgres, sqlite, json.")


def create_storage(default_json_path: str | Path | None = None) -> Any:
    """Создаёт хранилище профилей игроков.

    Для Timeweb/продакшена рекомендуется PostgreSQL:
        STORAGE_BACKEND=postgres
        DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME

    Для локальной разработки доступны SQLite и JSON. JSON заблокирован в
    production, если явно не включить ALLOW_JSON_STORAGE_IN_PRODUCTION=true.
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
