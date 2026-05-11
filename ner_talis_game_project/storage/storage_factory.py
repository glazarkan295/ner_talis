import os
from pathlib import Path
from typing import Any

from project_paths import resolve_project_path
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


def _normalize(value: str | Path) -> str:
    return str(value).strip().strip("'\"")


def create_storage(default_json_path: str | Path | None = None) -> Any:
    """Создаёт хранилище профилей игроков.

    Для Timeweb/продакшена рекомендуется PostgreSQL:
        STORAGE_BACKEND=postgres
        DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME

    Для локальной разработки доступны SQLite и JSON.
    """
    backend = _normalize(os.getenv("STORAGE_BACKEND", "sqlite")).casefold()

    legacy_json_path = resolve_project_path(
        _normalize(os.getenv("PLAYERS_STORAGE_PATH", str(default_json_path or "data/players.json")))
    )

    if backend == "json":
        return JsonStorage(str(legacy_json_path))

    if backend == "sqlite":
        sqlite_path = resolve_project_path(
            _normalize(os.getenv("SQLITE_STORAGE_PATH", "data/players.sqlite3"))
        )
        return SQLiteStorage(str(sqlite_path), legacy_json_path=str(legacy_json_path))

    if backend in {"postgres", "postgresql"}:
        from storage.postgres_storage import PostgresStorage

        return PostgresStorage(legacy_json_path=str(legacy_json_path))

    raise RuntimeError(
        "Некорректный STORAGE_BACKEND. Допустимые значения: postgres, sqlite, json."
    )
