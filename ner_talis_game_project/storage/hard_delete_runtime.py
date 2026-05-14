"""Runtime hard-delete support for all storage backends.

The storage classes already expose compatible load()/save() APIs. This module
adds a shared hard_delete_player_by_game_id(...) method without replacing large
storage files through GitHub.
"""

from __future__ import annotations

from typing import Any


def normalize_game_id(value: str | int | None) -> str:
    return str(value or "").strip().strip("'\"").upper()


def hard_delete_player_by_game_id(self: Any, game_id: str) -> bool:
    """Completely remove a player and every registration trace by game_id.

    Deletes profile data, platform links, name index, link codes and website
    sessions. This method intentionally does not create backups.
    """

    normalized_game_id = normalize_game_id(game_id)
    if not normalized_game_id:
        return False

    data = self.load()
    players = data.setdefault("players", {})
    real_key = normalized_game_id if normalized_game_id in players else None

    if real_key is None:
        for key, player in players.items():
            if not isinstance(player, dict):
                continue
            player_game_id = normalize_game_id(player.get("game_id") or player.get("id"))
            if player_game_id == normalized_game_id:
                real_key = key
                break

    if real_key is None:
        return False

    player = players.pop(real_key, None) or {}
    target_ids = {str(real_key), normalized_game_id}
    if isinstance(player, dict):
        target_ids.add(str(player.get("game_id") or ""))
        target_ids.add(str(player.get("id") or ""))

    for index_name in ("platform_links", "names"):
        data[index_name] = {
            key: value
            for key, value in data.get(index_name, {}).items()
            if str(value) not in target_ids
        }

    data["link_codes"] = {
        key: value
        for key, value in data.get("link_codes", {}).items()
        if not isinstance(value, dict) or str(value.get("game_id") or "") not in target_ids
    }

    for sessions_key in ("site_sessions", "web_sessions"):
        data[sessions_key] = {
            token: session
            for token, session in data.get(sessions_key, {}).items()
            if not isinstance(session, dict) or str(session.get("game_id") or "") not in target_ids
        }

    self.save(data)
    return True


def patch_storage_class(storage_class: type[Any]) -> type[Any]:
    storage_class.hard_delete_player_by_game_id = hard_delete_player_by_game_id
    return storage_class


def patch_known_storage_classes() -> None:
    from storage.json_storage import JsonStorage
    from storage.sqlite_storage import SQLiteStorage

    patch_storage_class(JsonStorage)
    patch_storage_class(SQLiteStorage)

    try:
        from storage.postgres_storage import PostgresStorage
    except Exception:
        return

    patch_storage_class(PostgresStorage)
