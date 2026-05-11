"""PostgreSQL storage for Ner-Talis players, platform links and web sessions."""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from storage.json_storage import JsonStorage


class PostgresStorage:
    LINK_CODE_LIFETIME_MINUTES = 15
    _lock = threading.RLock()

    def __init__(self, database_url: str | None = None, legacy_json_path: str | None = None):
        self.database_url = database_url or self._get_database_url()
        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path else None
        self._engine = None
        self._init_db()
        self._migrate_from_json_if_needed()

    @staticmethod
    def _get_database_url() -> str:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("Не указана переменная DATABASE_URL для PostgreSQL.")
        if database_url.startswith("postgres://"):
            return "postgresql+psycopg://" + database_url[len("postgres://"):]
        if database_url.startswith("postgresql://") and "+" not in database_url.split("://", 1)[0]:
            return "postgresql+psycopg://" + database_url[len("postgresql://"):]
        return database_url

    @staticmethod
    def empty_schema() -> dict[str, Any]:
        return {"players": {}, "platform_links": {}, "names": {}, "link_codes": {}, "web_sessions": {}, "site_sessions": {}}

    @staticmethod
    def make_platform_key(platform: str, external_user_id: str | int) -> str:
        return f"{platform}:{external_user_id}"

    @staticmethod
    def parse_old_platform_user_id(platform_user_id: str, platform: str | None = None) -> tuple[str | None, str | None]:
        return JsonStorage.parse_old_platform_user_id(platform_user_id, platform)

    @staticmethod
    def _serialize(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))

    @staticmethod
    def _deserialize(value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)

    def _text(self, sql: str):
        from sqlalchemy import text

        return text(sql)

    def _get_engine(self):
        if self._engine is None:
            try:
                from sqlalchemy import create_engine
            except ModuleNotFoundError as exc:
                raise RuntimeError("Для STORAGE_BACKEND=postgres нужны SQLAlchemy и psycopg[binary].") from exc
            self._engine = create_engine(self.database_url, future=True, pool_pre_ping=True)
        return self._engine

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        with self._get_engine().begin() as connection:
            yield connection

    def _init_db(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(self._text("""
                CREATE TABLE IF NOT EXISTS players (
                    game_id TEXT PRIMARY KEY,
                    public_id TEXT UNIQUE NOT NULL,
                    telegram_id TEXT UNIQUE,
                    vk_id TEXT UNIQUE,
                    name_key TEXT UNIQUE,
                    data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            connection.execute(self._text("""
                CREATE TABLE IF NOT EXISTS platform_links (
                    platform TEXT NOT NULL,
                    external_user_id TEXT NOT NULL,
                    game_id TEXT NOT NULL REFERENCES players(game_id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (platform, external_user_id)
                )
            """))
            connection.execute(self._text("""
                CREATE TABLE IF NOT EXISTS link_codes (
                    code TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL REFERENCES players(game_id) ON DELETE CASCADE,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            connection.execute(self._text("""
                CREATE TABLE IF NOT EXISTS web_sessions (
                    token TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL REFERENCES players(game_id) ON DELETE CASCADE,
                    scope TEXT NOT NULL DEFAULT 'profile',
                    platform TEXT,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            connection.execute(self._text("CREATE INDEX IF NOT EXISTS idx_platform_links_game_id ON platform_links(game_id)"))
            connection.execute(self._text("CREATE INDEX IF NOT EXISTS idx_web_sessions_game_id ON web_sessions(game_id)"))
            connection.execute(self._text("CREATE INDEX IF NOT EXISTS idx_web_sessions_expires_at ON web_sessions(expires_at)"))

    def check_connection(self) -> bool:
        with self._connect() as connection:
            connection.execute(self._text("SELECT 1"))
        return True

    def _migrate_from_json_if_needed(self) -> None:
        if not self.legacy_json_path or not self.legacy_json_path.exists():
            return
        with self._connect() as connection:
            if connection.execute(self._text("SELECT 1 FROM players LIMIT 1")).first():
                return
        try:
            data = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
        except Exception:
            return
        for player in (data.get("players") or {}).values():
            if isinstance(player, dict):
                game_id = player.get("game_id") or player.get("id") or self.generate_game_id()
                player["game_id"] = game_id
                player["id"] = game_id
                linked = player.get("linked_accounts") or {}
                if linked:
                    first_platform, first_id = next(iter(linked.items()))
                    self.save_new_player(player, first_platform, first_id)
                    for platform, external_user_id in linked.items():
                        self._link_platform(game_id, platform, external_user_id)
                else:
                    self._upsert_player(player)

    @staticmethod
    def _normalize_player(game_id: str, player: dict[str, Any]) -> dict[str, Any]:
        player = dict(player)
        player["game_id"] = game_id
        player["id"] = game_id
        player.setdefault("public_id", str(uuid.uuid4()))
        player.setdefault("linked_accounts", {})
        player.setdefault("current_city", "seldar")
        player.setdefault("energy", 100)
        player.setdefault("max_energy", 100)
        return player

    def _row_to_player(self, row: Any) -> dict[str, Any] | None:
        if not row:
            return None
        player = self._normalize_player(row["game_id"], self._deserialize(row["data"]))
        links = self._get_links(row["game_id"])
        player["linked_accounts"] = links
        if links.get("telegram"):
            player["telegram_id"] = links["telegram"]
        if links.get("vk"):
            player["vk_id"] = links["vk"]
        return player

    def _get_links(self, game_id: str) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute(self._text(
                "SELECT platform, external_user_id FROM platform_links WHERE game_id = :game_id"
            ), {"game_id": game_id}).mappings().all()
        return {row["platform"]: row["external_user_id"] for row in rows}

    def _upsert_player(self, player: dict[str, Any]) -> dict[str, Any]:
        game_id = player.get("game_id") or player.get("id") or self.generate_game_id()
        player = self._normalize_player(game_id, player)
        name = player.get("name") or ""
        name_key = name.casefold() if name else None
        telegram_id = (player.get("linked_accounts") or {}).get("telegram") or player.get("telegram_id")
        vk_id = (player.get("linked_accounts") or {}).get("vk") or player.get("vk_id")
        with self._connect() as connection:
            connection.execute(self._text("""
                INSERT INTO players(game_id, public_id, telegram_id, vk_id, name_key, data, updated_at)
                VALUES (:game_id, :public_id, :telegram_id, :vk_id, :name_key, CAST(:data AS jsonb), NOW())
                ON CONFLICT (game_id) DO UPDATE SET
                    public_id = EXCLUDED.public_id,
                    telegram_id = EXCLUDED.telegram_id,
                    vk_id = EXCLUDED.vk_id,
                    name_key = EXCLUDED.name_key,
                    data = EXCLUDED.data,
                    updated_at = NOW()
            """), {
                "game_id": game_id,
                "public_id": player["public_id"],
                "telegram_id": str(telegram_id) if telegram_id else None,
                "vk_id": str(vk_id) if vk_id else None,
                "name_key": name_key,
                "data": self._serialize(player),
            })
        for platform, external_user_id in (player.get("linked_accounts") or {}).items():
            if external_user_id:
                self._link_platform(game_id, platform, external_user_id)
        return player

    def _link_platform(self, game_id: str, platform: str, external_user_id: str | int) -> None:
        with self._connect() as connection:
            connection.execute(self._text("""
                INSERT INTO platform_links(platform, external_user_id, game_id)
                VALUES (:platform, :external_user_id, :game_id)
                ON CONFLICT (platform, external_user_id) DO UPDATE SET game_id = EXCLUDED.game_id
            """), {"platform": platform, "external_user_id": str(external_user_id), "game_id": game_id})

    def load(self) -> dict[str, Any]:
        with self._connect() as connection:
            players = connection.execute(self._text("SELECT * FROM players")).mappings().all()
            links = connection.execute(self._text("SELECT * FROM platform_links")).mappings().all()
            codes = connection.execute(self._text("SELECT * FROM link_codes")).mappings().all()
            sessions = connection.execute(self._text("SELECT * FROM web_sessions")).mappings().all()
        data = self.empty_schema()
        for row in players:
            player = self._row_to_player(row)
            if player:
                data["players"][player["game_id"]] = player
                if player.get("name"):
                    data["names"][player["name"].casefold()] = player["game_id"]
        for row in links:
            data["platform_links"][self.make_platform_key(row["platform"], row["external_user_id"])] = row["game_id"]
        for row in codes:
            data["link_codes"][row["code"]] = {"game_id": row["game_id"], "expires_at": row["expires_at"].isoformat()}
        for row in sessions:
            session = dict(row)
            session["expires_at"] = session["expires_at"].isoformat()
            session["created_at"] = session["created_at"].isoformat()
            data["web_sessions"][row["token"]] = session
            data["site_sessions"][row["token"]] = session
        return data

    def save(self, data: dict[str, Any]) -> None:
        for player in (data.get("players") or {}).values():
            if isinstance(player, dict):
                self._upsert_player(player)

    def generate_game_id(self) -> str:
        with self._connect() as connection:
            existing = set(connection.execute(self._text("SELECT game_id FROM players")).scalars().all())
        while True:
            game_id = f"NT-{uuid.uuid4().hex[:10].upper()}"
            if game_id not in existing:
                return game_id

    def get_player_by_game_id(self, game_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(self._text("SELECT * FROM players WHERE game_id = :game_id"), {"game_id": game_id}).mappings().first()
        return self._row_to_player(row)

    def get_player_by_platform(self, platform: str, external_user_id: str | int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(self._text("""
                SELECT p.* FROM players p
                JOIN platform_links l ON l.game_id = p.game_id
                WHERE l.platform = :platform AND l.external_user_id = :external_user_id
            """), {"platform": platform, "external_user_id": str(external_user_id)}).mappings().first()
        return self._row_to_player(row)

    def get_player(self, platform_user_id: str) -> dict[str, Any] | None:
        platform, external_user_id = self.parse_old_platform_user_id(platform_user_id)
        return self.get_player_by_platform(platform, external_user_id) if platform and external_user_id else None

    def save_new_player(self, player: dict[str, Any], platform: str, external_user_id: str | int) -> None:
        with self._lock:
            if self.get_player_by_platform(platform, external_user_id):
                raise ValueError("Эта платформа уже привязана к персонажу.")
            if player.get("name") and self.is_name_taken(player["name"]):
                raise ValueError("Это имя уже занято.")
            game_id = player.get("game_id") or self.generate_game_id()
            player = self._normalize_player(game_id, player)
            player["linked_accounts"][platform] = str(external_user_id)
            self._upsert_player(player)
            self._link_platform(game_id, platform, external_user_id)

    def save_player(self, platform_user_id: str, player: dict[str, Any] | None = None) -> None:
        if player is None and isinstance(platform_user_id, dict):
            self._upsert_player(platform_user_id)
            return
        platform, external_user_id = self.parse_old_platform_user_id(str(platform_user_id))
        if not platform or not external_user_id or player is None:
            raise ValueError("Неизвестный формат platform_user_id.")
        self.save_new_player(player, platform, external_user_id)

    def update_player(self, player: dict[str, Any]) -> None:
        if not (player.get("game_id") or player.get("id")):
            raise ValueError("Нельзя обновить игрока без game_id.")
        self._upsert_player(player)

    def update_player_by_platform(self, platform: str, external_user_id: str | int, updates: dict[str, Any]) -> dict[str, Any] | None:
        player = self.get_player_by_platform(platform, external_user_id)
        if not player:
            return None
        player.update(updates)
        self.update_player(player)
        return self.get_player_by_game_id(player["game_id"])

    def is_name_taken(self, name: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(self._text("SELECT 1 FROM players WHERE name_key = :name_key LIMIT 1"), {"name_key": name.casefold()}).first()
        return row is not None

    def create_link_code(self, game_id: str) -> str:
        self.clear_expired_link_codes()
        code = secrets.token_hex(3).upper()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.LINK_CODE_LIFETIME_MINUTES)
        with self._connect() as connection:
            connection.execute(self._text("""
                INSERT INTO link_codes(code, game_id, expires_at)
                VALUES (:code, :game_id, :expires_at)
                ON CONFLICT (code) DO UPDATE SET game_id = EXCLUDED.game_id, expires_at = EXCLUDED.expires_at
            """), {"code": code, "game_id": game_id, "expires_at": expires_at})
        return code

    def clear_expired_link_codes(self, data: dict[str, Any] | None = None) -> None:
        with self._connect() as connection:
            connection.execute(self._text("DELETE FROM link_codes WHERE expires_at <= NOW()"))

    def connect_platform_by_code(self, code: str, platform: str, external_user_id: str | int) -> tuple[bool, str, dict[str, Any] | None]:
        normalized_code = code.strip().upper().replace(" ", "")
        self.clear_expired_link_codes()
        with self._lock, self._connect() as connection:
            link_row = connection.execute(self._text(
                "SELECT game_id FROM link_codes WHERE code = :code"
            ), {"code": normalized_code}).mappings().first()
            if not link_row:
                return False, "Код привязки не найден или уже истёк.", None
            game_id = link_row["game_id"]
            player = self.get_player_by_game_id(game_id)
            if not player:
                connection.execute(self._text("DELETE FROM link_codes WHERE code = :code"), {"code": normalized_code})
                return False, "Персонаж для этого кода не найден.", None
            linked_player = self.get_player_by_platform(platform, external_user_id)
            if linked_player and linked_player.get("game_id") == game_id:
                connection.execute(self._text("DELETE FROM link_codes WHERE code = :code"), {"code": normalized_code})
                return True, "Эта платформа уже была привязана к этому персонажу.", player
            if linked_player and linked_player.get("game_id") != game_id:
                return False, "Эта платформа уже привязана к другому персонажу. Автоматически объединять разных персонажей нельзя.", None
            player.setdefault("linked_accounts", {})[platform] = str(external_user_id)
            self._upsert_player(player)
            self._link_platform(game_id, platform, external_user_id)
            connection.execute(self._text("DELETE FROM link_codes WHERE code = :code"), {"code": normalized_code})
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
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=max(1, int(minutes)))
        with self._connect() as connection:
            connection.execute(self._text("DELETE FROM web_sessions WHERE expires_at <= NOW()"))
            connection.execute(self._text("""
                INSERT INTO web_sessions(token, game_id, scope, platform, expires_at)
                VALUES (:token, :game_id, :scope, :platform, :expires_at)
            """), {"token": token, "game_id": game_id, "scope": scope, "platform": platform, "expires_at": expires_at})
        return token

    def create_site_session(self, game_id: str, scope: str = "profile", platform: str | None = None, lifetime_minutes: int = 15) -> str:
        return self.create_web_session(game_id, scope=scope, platform=platform, lifetime_minutes=lifetime_minutes)

    def get_web_session(self, token: str, scope: str | None = None) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(self._text("SELECT * FROM web_sessions WHERE token = :token"), {"token": token}).mappings().first()
            if not row:
                return None
            expires_at = row["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                connection.execute(self._text("DELETE FROM web_sessions WHERE token = :token"), {"token": token})
                return None
            if scope and row["scope"] != scope:
                return None
            session = dict(row)
            session["expires_at"] = expires_at.isoformat()
            session["created_at"] = session["created_at"].isoformat()
            return session

    def get_player_by_web_token(self, token: str, scope: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        session = self.get_web_session(token, scope=scope)
        if not session:
            return None, None
        return self.get_player_by_game_id(session["game_id"]), session
