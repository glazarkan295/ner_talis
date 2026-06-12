"""Runtime storage compatibility patches.

The large storage files can be difficult to replace through the GitHub
connector. This module adds small, focused compatibility methods at import time:
- web-session helpers for JSON/SQLite storages;
- generic hard-delete for JSON-like storages;
- native SQL hard-delete for PostgreSQL.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


def normalize_game_id(value: str | int | None) -> str:
    return str(value or "").strip().strip("'\"").upper()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _session_maps(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    site_sessions = data.setdefault("site_sessions", {})
    web_sessions = data.setdefault("web_sessions", {})
    return site_sessions, web_sessions


def _new_unique_session_token(site_sessions: dict[str, Any], web_sessions: dict[str, Any]) -> str:
    while True:
        token = secrets.token_urlsafe(32)
        if token not in site_sessions and token not in web_sessions:
            return token


def _purge_sessions_for_player_scope(
    site_sessions: dict[str, Any],
    web_sessions: dict[str, Any],
    game_id: str,
    scope: str,
) -> None:
    target_game_id = str(game_id)
    target_scope = str(scope)
    for sessions in (site_sessions, web_sessions):
        for existing_token, existing_session in list(sessions.items()):
            if not isinstance(existing_session, dict):
                continue
            if str(existing_session.get("game_id") or "") == target_game_id and str(existing_session.get("scope") or "") == target_scope:
                sessions.pop(existing_token, None)


def _normalize_session(token: str, session: dict[str, Any], expires_at: datetime) -> dict[str, Any]:
    normalized = dict(session)
    normalized["token"] = token
    normalized["expires_at"] = expires_at.isoformat()
    created_at = _parse_datetime(normalized.get("created_at"))
    if created_at:
        normalized["created_at"] = created_at.isoformat()
    return normalized


def cleanup_expired_web_sessions(self: Any) -> None:
    data = self.load()
    now = datetime.now(timezone.utc)
    site_sessions, web_sessions = _session_maps(data)
    expired_tokens: set[str] = set()

    for sessions in (site_sessions, web_sessions):
        for token, session in list(sessions.items()):
            if not isinstance(session, dict):
                expired_tokens.add(token)
                continue
            expires_at = _parse_datetime(session.get("expires_at"))
            if expires_at is None or expires_at <= now:
                expired_tokens.add(token)

    for token in expired_tokens:
        site_sessions.pop(token, None)
        web_sessions.pop(token, None)

    if expired_tokens:
        self.save(data)


def create_web_session(
    self: Any,
    game_id: str,
    scope: str = "profile",
    platform: str | None = None,
    lifetime_minutes: int = 1440,
    ttl_minutes: int | None = None,
) -> str:
    minutes = ttl_minutes if ttl_minutes is not None else lifetime_minutes
    if not self.get_player_by_game_id(game_id):
        raise ValueError("Игрок не найден.")

    cleanup_expired_web_sessions(self)
    data = self.load()
    site_sessions, web_sessions = _session_maps(data)
    now = datetime.now(timezone.utc)

    # New bot link invalidates every older one-time token and every active
    # browser session for the same player/scope. This is the server-side
    # "logout everywhere for this profile page" switch.
    _purge_sessions_for_player_scope(site_sessions, web_sessions, str(game_id), scope)

    token = _new_unique_session_token(site_sessions, web_sessions)
    session = {
        "game_id": str(game_id),
        "scope": scope,
        "platform": platform,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=max(1, int(minutes)))).isoformat(),
        "used": False,
        "kind": "activation",
    }
    site_sessions[token] = dict(session)
    web_sessions[token] = dict(session)
    self.save(data)
    return token


def get_web_session(self: Any, token: str, scope: str | None = None) -> dict[str, Any] | None:
    data = self.load()
    site_sessions, web_sessions = _session_maps(data)
    session = web_sessions.get(token) or site_sessions.get(token)
    if not isinstance(session, dict):
        return None

    expires_at = _parse_datetime(session.get("expires_at"))
    if expires_at is None or expires_at <= datetime.now(timezone.utc):
        site_sessions.pop(token, None)
        web_sessions.pop(token, None)
        self.save(data)
        return None

    if scope and session.get("scope") != scope:
        return None

    # used=False is a one-time URL activation token. Consume it immediately and
    # replace it with a private active session token. The URL token is removed,
    # so opening the same link again cannot enter the profile.
    if not bool(session.get("used")):
        game_id = str(session.get("game_id") or "")
        session_scope = str(session.get("scope") or "")
        if not game_id or not session_scope:
            site_sessions.pop(token, None)
            web_sessions.pop(token, None)
            self.save(data)
            return None
        active_token = _new_unique_session_token(site_sessions, web_sessions)
        now = datetime.now(timezone.utc)
        active_session = dict(session)
        active_session.update({
            "used": True,
            "kind": "active",
            "activated_at": now.isoformat(),
            "activation_token_used": token,
        })
        _purge_sessions_for_player_scope(site_sessions, web_sessions, game_id, session_scope)
        site_sessions[active_token] = dict(active_session)
        web_sessions[active_token] = dict(active_session)
        self.save(data)
        return _normalize_session(active_token, active_session, expires_at)

    return _normalize_session(token, session, expires_at)


def get_player_by_web_token(self: Any, token: str, scope: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    session = get_web_session(self, token, scope=scope)
    if not session:
        return None, None
    return self.get_player_by_game_id(str(session.get("game_id"))), session


def get_player_by_public_id(self: Any, public_id: str) -> dict[str, Any] | None:
    target = str(public_id or "").strip()
    if not target:
        return None
    for player in self.load().get("players", {}).values():
        if isinstance(player, dict) and str(player.get("public_id") or "") == target:
            return player
    return None


def hard_delete_player_by_game_id(self: Any, game_id: str) -> bool:
    """Completely remove a player and every registration trace by game_id.

    Generic implementation for load()/save() storages. PostgreSQL gets a native
    SQL implementation below because generic save() there only upserts rows.
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


def postgres_hard_delete_player_by_game_id(self: Any, game_id: str) -> bool:
    """Native hard-delete for PostgreSQL tables."""
    from sqlalchemy import text

    normalized_game_id = normalize_game_id(game_id)
    if not normalized_game_id:
        return False

    with self.engine.begin() as connection:
        row = connection.execute(
            text("SELECT game_id FROM players WHERE upper(game_id) = :game_id"),
            {"game_id": normalized_game_id},
        ).mappings().first()
        if not row:
            return False

        real_game_id = row["game_id"]
        connection.execute(text("DELETE FROM web_sessions WHERE game_id = :game_id"), {"game_id": real_game_id})
        connection.execute(text("DELETE FROM link_codes WHERE game_id = :game_id"), {"game_id": real_game_id})
        connection.execute(text("DELETE FROM platform_links WHERE game_id = :game_id"), {"game_id": real_game_id})
        result = connection.execute(text("DELETE FROM players WHERE game_id = :game_id"), {"game_id": real_game_id})
        return result.rowcount > 0


def postgres_delete_player(self: Any, game_id: str) -> bool:
    return self.hard_delete_player_by_game_id(game_id)


def patch_document_storage_class(storage_class: type[Any]) -> type[Any]:
    # Override site/web session helpers so JSON and SQLite share the same
    # one-time activation semantics even if the concrete class has an older
    # create_site_session implementation.
    storage_class.create_web_session = create_web_session
    storage_class.create_site_session = create_web_session
    storage_class.get_web_session = get_web_session
    if not callable(getattr(storage_class, "get_player_by_web_token", None)):
        storage_class.get_player_by_web_token = get_player_by_web_token
    if not callable(getattr(storage_class, "cleanup_expired_web_sessions", None)):
        storage_class.cleanup_expired_web_sessions = cleanup_expired_web_sessions
    if not callable(getattr(storage_class, "get_player_by_public_id", None)):
        storage_class.get_player_by_public_id = get_player_by_public_id
    if not callable(getattr(storage_class, "hard_delete_player_by_game_id", None)):
        storage_class.hard_delete_player_by_game_id = hard_delete_player_by_game_id
    if not callable(getattr(storage_class, "delete_player", None)):
        storage_class.delete_player = hard_delete_player_by_game_id
    return storage_class


def patch_postgres_storage_class(storage_class: type[Any]) -> type[Any]:
    # Always use native SQL delete for PostgreSQL. The generic load()/save()
    # fallback only upserts rows in PostgresStorage and cannot delete missing
    # profiles from database tables.
    storage_class.hard_delete_player_by_game_id = postgres_hard_delete_player_by_game_id
    storage_class.delete_player = postgres_delete_player
    return storage_class


def patch_known_storage_classes() -> None:
    from storage.json_storage import JsonStorage
    from storage.sqlite_storage import SQLiteStorage

    patch_document_storage_class(JsonStorage)
    patch_document_storage_class(SQLiteStorage)

    try:
        from storage.postgres_storage import PostgresStorage
    except Exception:
        return

    patch_postgres_storage_class(PostgresStorage)
