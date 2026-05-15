"""PostgreSQL storage for Ner-Talis players, platform links and web sessions."""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from storage.starter_pack_runtime import (
    POSTGRES_COLUMN_FIELDS,
    STARTER_EXTRA_FIELDS,
    build_extra_payload,
    ensure_starter_pack,
)


class PostgresStorage:
    """Player storage backed by PostgreSQL.

    Keeps the public API close to JsonStorage/SQLiteStorage so Telegram, VK and
    the FastAPI website can use the same storage factory.
    """

    LINK_CODE_LIFETIME_MINUTES = 15
    _lock = threading.RLock()
    _starter_pack_native = True
    COLUMN_FIELDS = POSTGRES_COLUMN_FIELDS
    DEFAULT_EXTRA_FIELDS = STARTER_EXTRA_FIELDS
    _ensure_starter_pack = staticmethod(ensure_starter_pack)
    _build_extra_payload = staticmethod(build_extra_payload)

    def __init__(self, database_url: str | None = None, legacy_json_path: str | Path | None = None):
        self.database_url = database_url or os.getenv("DATABASE_URL", "").strip()
        if not self.database_url:
            raise RuntimeError("Для STORAGE_BACKEND=postgres нужно указать DATABASE_URL.")
        if self.database_url.startswith("postgres://"):
            self.database_url = "postgresql+psycopg://" + self.database_url.removeprefix("postgres://")
        elif self.database_url.startswith("postgresql://") and "+" not in self.database_url.split("://", 1)[0]:
            self.database_url = "postgresql+psycopg://" + self.database_url.removeprefix("postgresql://")
        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path else None
        self.engine: Engine = create_engine(self.database_url, pool_pre_ping=True, future=True)
        self.init_db()
        self.import_legacy_json_if_needed()

    @staticmethod
    def empty_schema() -> dict[str, Any]:
        return {
            "players": {},
            "platform_links": {},
            "names": {},
            "link_codes": {},
            "web_sessions": {},
            "site_sessions": {},
        }

    @staticmethod
    def make_platform_key(platform: str, external_user_id: str | int) -> str:
        return f"{platform}:{external_user_id}"

    @staticmethod
    def parse_old_platform_user_id(platform_user_id: str, platform: str | None = None) -> tuple[str | None, str | None]:
        if platform == "telegram":
            return "telegram", str(platform_user_id).removeprefix("tg_")
        if platform == "vk":
            return "vk", str(platform_user_id).removeprefix("vk_")
        raw = str(platform_user_id)
        if raw.startswith("tg_"):
            return "telegram", raw[3:]
        if raw.startswith("vk_"):
            return "vk", raw[3:]
        return None, None

    @staticmethod
    def _dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))

    @staticmethod
    def _loads(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return default

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
                CREATE TABLE IF NOT EXISTS link_codes (
                    code TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL REFERENCES players(game_id) ON DELETE CASCADE,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_platform_links_game_id ON platform_links(game_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_web_sessions_game_id ON web_sessions(game_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_web_sessions_expires_at ON web_sessions(expires_at)"))

    def check_connection(self) -> bool:
        with self.engine.begin() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def import_legacy_json_if_needed(self) -> None:
        if not self.legacy_json_path or not self.legacy_json_path.exists():
            return
        with self.engine.begin() as connection:
            if connection.execute(text("SELECT 1 FROM players LIMIT 1")).first():
                return
        try:
            data = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
        except Exception:
            return
        for player in (data.get("players") or {}).values():
            if isinstance(player, dict):
                self.save_player(player)

    def generate_game_id(self) -> str:
        with self.engine.begin() as connection:
            existing = set(connection.execute(text("SELECT game_id FROM players")).scalars().all())
        while True:
            game_id = f"NT-{uuid.uuid4().hex[:10].upper()}"
            if game_id not in existing:
                return game_id

    def _normalize_player(self, player: dict[str, Any]) -> dict[str, Any]:
        player = dict(player)
        game_id = str(player.get("game_id") or player.get("id") or self.generate_game_id())
        player["game_id"] = game_id
        player["id"] = game_id
        player.setdefault("public_id", str(uuid.uuid4()))
        player.setdefault("linked_accounts", {})
        player.setdefault("current_city", "seldar")
        player.setdefault("energy", 100)
        player.setdefault("max_energy", 100)
        self._ensure_starter_pack(player)
        player["extra"] = self._build_extra_payload(player)
        return player

    def _row_to_player(self, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        player = dict(row)
        player["id"] = player["game_id"]
        player["stats"] = self._loads(player.get("stats"), {})
        player["inventory"] = self._loads(player.get("inventory"), [])
        player["crafting_levels"] = self._loads(player.get("crafting_levels"), {})
        player["housing"] = self._loads(player.get("housing"), {})
        player["extra"] = self._loads(player.get("extra"), {})
        if isinstance(player["extra"], dict):
            for key, value in player["extra"].items():
                if key not in {"game_id", "id"}:
                    player.setdefault(key, value)
        for date_key in ("created_at", "updated_at"):
            if hasattr(player.get(date_key), "isoformat"):
                player[date_key] = player[date_key].isoformat()
        links = self.get_links_for_game_id(player["game_id"])
        player["linked_accounts"] = links
        if links.get("telegram"):
            player["telegram_id"] = links["telegram"]
        if links.get("vk"):
            player["vk_id"] = links["vk"]
        self._ensure_starter_pack(player)
        player["extra"] = self._build_extra_payload(player)
        return player

    def get_links_for_game_id(self, game_id: str) -> dict[str, str]:
        with self.engine.begin() as connection:
            rows = connection.execute(text("""
                SELECT platform, platform_user_id FROM platform_links WHERE game_id = :game_id
            """), {"game_id": str(game_id)}).mappings().all()
        return {row["platform"]: row["platform_user_id"] for row in rows}

    def get_player_by_game_id(self, game_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(text("SELECT * FROM players WHERE game_id = :game_id"), {"game_id": str(game_id)}).mappings().first()
        return self._row_to_player(row)

    def get_player_by_platform(self, platform: str, external_user_id: str | int) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(text("""
                SELECT p.* FROM players p
                JOIN platform_links l ON l.game_id = p.game_id
                WHERE l.platform = :platform AND l.platform_user_id = :platform_user_id
            """), {"platform": platform, "platform_user_id": str(external_user_id)}).mappings().first()
        return self._row_to_player(row)

    def get_player_by_platform_id(self, platform: str, platform_user_id: str | int) -> dict[str, Any] | None:
        return self.get_player_by_platform(platform, platform_user_id)

    def get_player_by_telegram_id(self, telegram_id: str | int) -> dict[str, Any] | None:
        return self.get_player_by_platform("telegram", telegram_id)

    def get_player_by_vk_id(self, vk_id: str | int) -> dict[str, Any] | None:
        return self.get_player_by_platform("vk", vk_id)

    def get_player(self, platform_user_id: str, external_user_id: str | int | None = None) -> dict[str, Any] | None:
        if external_user_id is not None:
            return self.get_player_by_platform(platform_user_id, external_user_id)
        platform, parsed_id = self.parse_old_platform_user_id(str(platform_user_id))
        if platform and parsed_id:
            return self.get_player_by_platform(platform, parsed_id)
        return None

    def is_name_taken(self, name: str) -> bool:
        with self.engine.begin() as connection:
            return connection.execute(text("""
                SELECT 1 FROM players WHERE lower(name) = :name LIMIT 1
            """), {"name": name.casefold()}).first() is not None

    def _upsert_player(self, player: dict[str, Any]) -> dict[str, Any]:
        player = self._normalize_player(player)
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
                "game_id": player["game_id"],
                "public_id": player.get("public_id") or player["game_id"],
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
                "extra": self._dumps(player.get("extra") or self._build_extra_payload(player)),
            })
        for platform, platform_user_id in (player.get("linked_accounts") or {}).items():
            if platform_user_id:
                self._link_platform(player["game_id"], platform, platform_user_id)
        return player

    def _link_platform(self, game_id: str, platform: str, external_user_id: str | int) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO platform_links(platform, platform_user_id, game_id)
                VALUES (:platform, :platform_user_id, :game_id)
                ON CONFLICT (platform, platform_user_id) DO UPDATE SET game_id = EXCLUDED.game_id
            """), {"platform": platform, "platform_user_id": str(external_user_id), "game_id": str(game_id)})

    def save_new_player(self, player: dict[str, Any], platform: str, external_user_id: str | int) -> None:
        if self.get_player_by_platform(platform, external_user_id):
            raise ValueError("Эта платформа уже привязана к персонажу.")
        if player.get("name") and self.is_name_taken(player["name"]):
            raise ValueError("Это имя уже занято.")
        player = self._normalize_player(player)
        player["linked_accounts"][platform] = str(external_user_id)
        self._upsert_player(player)
        self._link_platform(player["game_id"], platform, external_user_id)

    def save_player(self, platform_user_id: Any, player: dict[str, Any] | None = None) -> Any:
        if player is None and isinstance(platform_user_id, dict):
            return self._upsert_player(platform_user_id)
        platform, external_user_id = self.parse_old_platform_user_id(str(platform_user_id))
        if not platform or not external_user_id or player is None:
            raise ValueError("Неизвестный формат platform_user_id.")
        return self.save_new_player(player, platform, external_user_id)

    def update_player(self, player: dict[str, Any]) -> None:
        if not (player.get("game_id") or player.get("id")):
            raise ValueError("Нельзя обновить игрока без game_id.")
        self._upsert_player(player)

    def update_player_by_platform(self, platform: str, external_user_id: str | int, updates: dict[str, Any]) -> dict[str, Any] | None:
        player = self.get_player_by_platform(platform, external_user_id)
        if player is None:
            return None
        player.update(updates)
        self.update_player(player)
        return self.get_player_by_game_id(player["game_id"])

    def create_link_code(self, game_id: str) -> str:
        self.clear_expired_link_codes()
        code = secrets.token_hex(3).upper()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.LINK_CODE_LIFETIME_MINUTES)
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO link_codes(code, game_id, expires_at)
                VALUES (:code, :game_id, :expires_at)
                ON CONFLICT (code) DO UPDATE SET game_id = EXCLUDED.game_id, expires_at = EXCLUDED.expires_at
            """), {"code": code, "game_id": str(game_id), "expires_at": expires_at})
        return code

    def clear_expired_link_codes(self, data: dict[str, Any] | None = None) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM link_codes WHERE expires_at <= now()"))

    def connect_platform_by_code(self, code: str, platform: str, external_user_id: str | int) -> tuple[bool, str, dict[str, Any] | None]:
        normalized_code = code.strip().upper().replace(" ", "")
        self.clear_expired_link_codes()
        with self.engine.begin() as connection:
            link_row = connection.execute(text("SELECT game_id FROM link_codes WHERE code = :code"), {"code": normalized_code}).mappings().first()
            if not link_row:
                return False, "Код привязки не найден или уже истёк.", None
            game_id = link_row["game_id"]
            linked_player = self.get_player_by_platform(platform, external_user_id)
            if linked_player and linked_player.get("game_id") == game_id:
                connection.execute(text("DELETE FROM link_codes WHERE code = :code"), {"code": normalized_code})
                return True, "Эта платформа уже была привязана к этому персонажу.", linked_player
            if linked_player and linked_player.get("game_id") != game_id:
                return False, "Эта платформа уже привязана к другому персонажу. Автоматически объединять разных персонажей нельзя.", None
        player = self.get_player_by_game_id(game_id)
        if player is None:
            with self.engine.begin() as connection:
                connection.execute(text("DELETE FROM link_codes WHERE code = :code"), {"code": normalized_code})
            return False, "Персонаж для этого кода не найден.", None
        player.setdefault("linked_accounts", {})[platform] = str(external_user_id)
        self.update_player(player)
        self._link_platform(game_id, platform, external_user_id)
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM link_codes WHERE code = :code"), {"code": normalized_code})
        return True, "Платформа успешно привязана к персонажу.", self.get_player_by_game_id(game_id)

    def create_web_session(
        self,
        game_id: str,
        scope: str = "profile",
        platform: str | None = None,
        lifetime_minutes: int = 15,
        ttl_minutes: int | None = None,
    ) -> str:
        minutes = ttl_minutes if ttl_minutes is not None else lifetime_minutes
        if not self.get_player_by_game_id(game_id):
            raise ValueError("Игрок не найден.")
        self.cleanup_expired_web_sessions()
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(minutes)))
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

    def create_site_session(self, game_id: str, scope: str = "profile", platform: str | None = None, lifetime_minutes: int = 15) -> str:
        return self.create_web_session(game_id, scope=scope, platform=platform, lifetime_minutes=lifetime_minutes)

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
            session = dict(row)
            session["created_at"] = session["created_at"].isoformat() if hasattr(session["created_at"], "isoformat") else session["created_at"]
            session["expires_at"] = expires_at.isoformat()
            return session

    def get_player_by_web_token(self, token: str, scope: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        session = self.get_web_session(token, scope=scope)
        if not session:
            return None, None
        return self.get_player_by_game_id(session["game_id"]), session

    def cleanup_expired_web_sessions(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM web_sessions WHERE expires_at <= now()"))

    def load_data(self) -> dict[str, Any]:
        return self.load()

    def save_data(self, data: dict[str, Any]) -> None:
        self.save(data)

    def load(self) -> dict[str, Any]:
        data = self.empty_schema()
        with self.engine.begin() as connection:
            players = connection.execute(text("SELECT * FROM players")).mappings().all()
            sessions = connection.execute(text("SELECT * FROM web_sessions")).mappings().all()
            codes = connection.execute(text("SELECT * FROM link_codes")).mappings().all()
        for row in players:
            player = self._row_to_player(row)
            if player:
                data["players"][player["game_id"]] = player
                if player.get("name"):
                    data["names"][player["name"].casefold()] = player["game_id"]
                for platform, platform_user_id in player.get("linked_accounts", {}).items():
                    data["platform_links"][self.make_platform_key(platform, platform_user_id)] = player["game_id"]
        for row in sessions:
            session = dict(row)
            data["web_sessions"][row["token"]] = session
            data["site_sessions"][row["token"]] = session
        for row in codes:
            data["link_codes"][row["code"]] = {"game_id": row["game_id"], "expires_at": row["expires_at"].isoformat()}
        return data

    def save(self, data: dict[str, Any]) -> None:
        for player in (data.get("players") or {}).values():
            if isinstance(player, dict):
                self._upsert_player(player)
