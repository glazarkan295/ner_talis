"""PostgreSQL storage for Ner-Talis players and web sessions.

Tables:
- players: persistent player profiles keyed by game_id.
- platform_links: Telegram/VK account links to one game_id.
- web_sessions: short-lived tokens for website entry from bots.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


class PostgresStorage:
    """Player storage backed by PostgreSQL.

    DATABASE_URL example:
    postgresql+psycopg://USER:PASSWORD@HOST:5432/DB_NAME
    """

    def __init__(self, database_url: str | None = None, legacy_json_path: str | Path | None = None):
        self.database_url = database_url or os.getenv("DATABASE_URL", "").strip()
        if not self.database_url:
            raise RuntimeError("Для STORAGE_BACKEND=postgres нужно указать DATABASE_URL.")

        if self.database_url.startswith("postgres://"):
            self.database_url = "postgresql+psycopg://" + self.database_url.removeprefix("postgres://")
        elif self.database_url.startswith("postgresql://"):
            self.database_url = "postgresql+psycopg://" + self.database_url.removeprefix("postgresql://")

        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path else None
        self.engine: Engine = create_engine(self.database_url, pool_pre_ping=True, future=True)
        self.init_db()
        self.import_legacy_json_if_needed()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _loads(raw: str | None, default: Any) -> Any:
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def init_db(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS players (
                    game_id TEXT PRIMARY KEY,
                    public_id TEXT UNIQUE,
                    name TEXT NOT NULL,
                    race_id TEXT,
                    race_name TEXT,
                    level INTEGER NOT NULL DEFAULT 1,
                    experience INTEGER NOT NULL DEFAULT 0,
                    money BIGINT NOT NULL DEFAULT 0,
                    debt BIGINT NOT NULL DEFAULT 0,
                    energy INTEGER NOT NULL DEFAULT 100,
                    max_energy INTEGER NOT NULL DEFAULT 100,
                    current_city TEXT NOT NULL DEFAULT 'seldar',
                    current_zone TEXT,
                    stats JSONB NOT NULL DEFAULT '{}'::jsonb,
                    inventory JSONB NOT NULL DEFAULT '[]'::jsonb,
                    crafting_levels JSONB NOT NULL DEFAULT '{}'::jsonb,
                    housing JSONB NOT NULL DEFAULT '{}'::jsonb,
                    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS platform_links (
                    platform TEXT NOT NULL,
                    platform_user_id TEXT NOT NULL,
                    game_id TEXT NOT NULL REFERENCES players(game_id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (platform, platform_user_id)
                )
            """))
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS web_sessions (
                    token TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL REFERENCES players(game_id) ON DELETE CASCADE,
                    scope TEXT NOT NULL DEFAULT 'profile',
                    platform TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    used BOOLEAN NOT NULL DEFAULT FALSE
                )
            """))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_web_sessions_game_id ON web_sessions(game_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_web_sessions_expires_at ON web_sessions(expires_at)"))

    def import_legacy_json_if_needed(self) -> None:
        if not self.legacy_json_path or not self.legacy_json_path.exists():
            return
        with self.engine.begin() as connection:
            has_players = connection.execute(text("SELECT 1 FROM players LIMIT 1")).first()
            if has_players:
                return
        try:
            data = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
        except Exception:
            return
        players = data.get("players") if isinstance(data, dict) else None
        if isinstance(players, dict):
            for player in players.values():
                if isinstance(player, dict):
                    self.save_player(player)

    def _row_to_player(self, row: Any) -> dict[str, Any]:
        if row is None:
            return {}
        player = dict(row)
        for key in ("stats", "inventory", "crafting_levels", "housing", "extra"):
            if isinstance(player.get(key), str):
                player[key] = self._loads(player[key], {} if key != "inventory" else [])
        links = self.get_links_for_game_id(player["game_id"])
        player["linked_accounts"] = links
        if links.get("telegram"):
            player["telegram_id"] = links["telegram"]
        if links.get("vk"):
            player["vk_id"] = links["vk"]
        return player

    def save_player(self, player: dict[str, Any]) -> dict[str, Any]:
        game_id = str(player.get("game_id") or player.get("user_global_id") or secrets.token_hex(8))
        player = dict(player, game_id=game_id)
        public_id = player.get("public_id") or game_id
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO players(
                    game_id, public_id, name, race_id, race_name, level, experience, money, debt,
                    energy, max_energy, current_city, current_zone, stats, inventory,
                    crafting_levels, housing, extra, updated_at
                ) VALUES (
                    :game_id, :public_id, :name, :race_id, :race_name, :level, :experience, :money, :debt,
                    :energy, :max_energy, :current_city, :current_zone, CAST(:stats AS jsonb), CAST(:inventory AS jsonb),
                    CAST(:crafting_levels AS jsonb), CAST(:housing AS jsonb), CAST(:extra AS jsonb), now()
                )
                ON CONFLICT (game_id) DO UPDATE SET
                    public_id = EXCLUDED.public_id,
                    name = EXCLUDED.name,
                    race_id = EXCLUDED.race_id,
                    race_name = EXCLUDED.race_name,
                    level = EXCLUDED.level,
                    experience = EXCLUDED.experience,
                    money = EXCLUDED.money,
                    debt = EXCLUDED.debt,
                    energy = EXCLUDED.energy,
                    max_energy = EXCLUDED.max_energy,
                    current_city = EXCLUDED.current_city,
                    current_zone = EXCLUDED.current_zone,
                    stats = EXCLUDED.stats,
                    inventory = EXCLUDED.inventory,
                    crafting_levels = EXCLUDED.crafting_levels,
                    housing = EXCLUDED.housing,
                    extra = EXCLUDED.extra,
                    updated_at = now()
            """), {
                "game_id": game_id,
                "public_id": public_id,
                "name": player.get("name") or "Безымянный",
                "race_id": player.get("race_id"),
                "race_name": player.get("race_name"),
                "level": int(player.get("level", 1)),
                "experience": int(player.get("experience", 0)),
                "money": int(player.get("money", 0)),
                "debt": int(player.get("debt", 0)),
                "energy": int(player.get("energy", 100)),
                "max_energy": int(player.get("max_energy", 100)),
                "current_city": player.get("current_city", "seldar"),
                "current_zone": player.get("current_zone"),
                "stats": self._dumps(player.get("stats", {})),
                "inventory": self._dumps(player.get("inventory", [])),
                "crafting_levels": self._dumps(player.get("crafting_levels", {})),
                "housing": self._dumps(player.get("housing", {})),
                "extra": self._dumps(player.get("extra", {})),
            })
            for platform, key in (("telegram", "telegram_id"), ("vk", "vk_id")):
                value = player.get(key) or (player.get("linked_accounts") or {}).get(platform)
                if value:
                    connection.execute(text("""
                        INSERT INTO platform_links(platform, platform_user_id, game_id)
                        VALUES (:platform, :platform_user_id, :game_id)
                        ON CONFLICT (platform, platform_user_id) DO UPDATE SET game_id = EXCLUDED.game_id
                    """), {"platform": platform, "platform_user_id": str(value), "game_id": game_id})
        return self.get_player_by_game_id(game_id) or player

    def get_links_for_game_id(self, game_id: str) -> dict[str, str]:
        with self.engine.begin() as connection:
            rows = connection.execute(text("""
                SELECT platform, platform_user_id FROM platform_links WHERE game_id = :game_id
            """), {"game_id": str(game_id)}).mappings().all()
        return {row["platform"]: row["platform_user_id"] for row in rows}

    def get_player_by_game_id(self, game_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(text("SELECT * FROM players WHERE game_id = :game_id"), {"game_id": str(game_id)}).mappings().first()
        return self._row_to_player(row) if row else None

    def get_player_by_platform_id(self, platform: str, platform_user_id: str | int) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(text("""
                SELECT p.* FROM players p
                JOIN platform_links l ON l.game_id = p.game_id
                WHERE l.platform = :platform AND l.platform_user_id = :platform_user_id
            """), {"platform": platform, "platform_user_id": str(platform_user_id)}).mappings().first()
        return self._row_to_player(row) if row else None

    def get_player_by_telegram_id(self, telegram_id: str | int) -> dict[str, Any] | None:
        return self.get_player_by_platform_id("telegram", telegram_id)

    def get_player_by_vk_id(self, vk_id: str | int) -> dict[str, Any] | None:
        return self.get_player_by_platform_id("vk", vk_id)

    def create_web_session(self, game_id: str, scope: str = "profile", platform: str | None = None, ttl_minutes: int = 15) -> str:
        self.cleanup_expired_web_sessions()
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO web_sessions(token, game_id, scope, platform, expires_at)
                VALUES (:token, :game_id, :scope, :platform, :expires_at)
            """), {
                "token": token,
                "game_id": str(game_id),
                "scope": scope,
                "platform": platform,
                "expires_at": expires_at,
            })
        return token

    def get_web_session(self, token: str, scope: str | None = None) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(text("""
                SELECT token, game_id, scope, platform, created_at, expires_at, used
                FROM web_sessions WHERE token = :token
            """), {"token": token}).mappings().first()
            if not row:
                return None
            expires_at = row["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                connection.execute(text("DELETE FROM web_sessions WHERE token = :token"), {"token": token})
                return None
            if scope and row["scope"] != scope:
                return None
            return dict(row)

    def get_player_by_web_token(self, token: str, scope: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        session = self.get_web_session(token, scope=scope)
        if not session:
            return None, None
        return self.get_player_by_game_id(session["game_id"]), session

    def cleanup_expired_web_sessions(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM web_sessions WHERE expires_at <= now()"))

    # Compatibility helpers used by existing services.
    def load_data(self) -> dict[str, Any]:
        with self.engine.begin() as connection:
            players = connection.execute(text("SELECT * FROM players")).mappings().all()
            sessions = connection.execute(text("SELECT * FROM web_sessions")).mappings().all()
        return {
            "players": {row["game_id"]: self._row_to_player(row) for row in players},
            "web_sessions": {row["token"]: dict(row) for row in sessions},
            "site_sessions": {row["token"]: dict(row) for row in sessions},
        }

    def save_data(self, data: dict[str, Any]) -> None:
        for player in (data.get("players") or {}).values():
            if isinstance(player, dict):
                self.save_player(player)

    def get_player(self, platform: str, platform_user_id: str | int) -> dict[str, Any] | None:
        return self.get_player_by_platform_id(platform, platform_user_id)
