import os
from pathlib import Path

from project_paths import resolve_project_path
from storage.base import PlayerStorage
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage

SUPPORTED_STORAGE_BACKENDS = {"json", "sqlite"}


def normalize_env_value(name: str, value: str | Path) -> str:
    normalized = str(value).strip().strip("'\"")
    prefix = f"{name}="
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix):].strip()
    return normalized


def normalize_backend(raw_backend: str | None) -> str:
    backend = normalize_env_value("STORAGE_BACKEND", raw_backend or "sqlite").casefold()
    if backend not in SUPPORTED_STORAGE_BACKENDS:
        raise RuntimeError(
            "Некорректный STORAGE_BACKEND. Допустимые значения: json, sqlite."
        )
    return backend


def create_storage(default_json_path: str | Path | None = None) -> PlayerStorage:
    """Создаёт хранилище профилей игроков.

    По умолчанию используется SQLite, потому что он безопаснее JSON при
    одновременной работе Telegram и VK. Для локальной отладки можно вернуть
    старое JSON-хранилище: STORAGE_BACKEND=json.
    """
    backend = normalize_backend(os.getenv("STORAGE_BACKEND"))
    legacy_json_path = resolve_project_path(
        normalize_env_value(
            "PLAYERS_STORAGE_PATH",
            os.getenv("PLAYERS_STORAGE_PATH", str(default_json_path or "data/players.json")),
        )
    )

    if backend == "json":
        return JsonStorage(str(legacy_json_path))

    if backend == "sqlite":
        sqlite_path = resolve_project_path(
            normalize_env_value(
                "SQLITE_STORAGE_PATH",
                os.getenv("SQLITE_STORAGE_PATH", "data/players.sqlite3"),
            )
        )
        return SQLiteStorage(str(sqlite_path), legacy_json_path=str(legacy_json_path))

    raise AssertionError(f"Unsupported storage backend after validation: {backend}")
