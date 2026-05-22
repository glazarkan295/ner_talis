import json
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from storage.json_storage import JsonStorage
from storage.timer_claims import try_mark_timer_claimed
from storage.event_claims import try_mark_active_event_claimed


class SQLiteStorage:
    """SQLite-хранилище игроков с единым игровым ID.

    Это рабочее постоянное хранилище для одновременной работы Telegram и VK
    в одном процессе. Профиль игрока хранится как JSON-документ, а быстрые
    индексы вынесены в отдельные таблицы: привязки платформ и имена.
    """

    LINK_CODE_LIFETIME_MINUTES = 15
    _lock = threading.RLock()

    def __init__(self, path: str, legacy_json_path: str | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path else None
        self._init_db()
        self._migrate_from_json_if_needed()

    @staticmethod
    def empty_schema() -> dict[str, Any]:
        return {
            "players": {},
            "platform_links": {},
            "names": {},
            "link_codes": {},
            "site_sessions": {},
            "promo_codes": {"codes": {}},
        }

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            yield connection
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS players (
                    game_id TEXT PRIMARY KEY,
                    public_id TEXT UNIQUE NOT NULL,
                    name_key TEXT UNIQUE,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS platform_links (
                    platform_key TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    external_user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (game_id) REFERENCES players(game_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS link_codes (
                    code TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (game_id) REFERENCES players(game_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS site_sessions (
                    token TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (game_id) REFERENCES players(game_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_platform_links_game_id
                    ON platform_links(game_id);
                CREATE INDEX IF NOT EXISTS idx_link_codes_created_at
                    ON link_codes(created_at);
                CREATE TABLE IF NOT EXISTS promo_codes (
                    code TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_site_sessions_expires_at
                    ON site_sessions(expires_at);
                """
            )

    @staticmethod
    def make_platform_key(platform: str, external_user_id: str | int) -> str:
        return f"{platform}:{external_user_id}"

    @staticmethod
    def parse_old_platform_user_id(
        platform_user_id: str,
        platform: str | None = None,
    ) -> tuple[str | None, str | None]:
        return JsonStorage.parse_old_platform_user_id(platform_user_id, platform)

    @staticmethod
    def _generate_game_id_from_existing(existing_game_ids: set[str]) -> str:
        while True:
            game_id = f"NT-{uuid.uuid4().hex[:10].upper()}"
            if game_id not in existing_game_ids:
                return game_id

    @staticmethod
    def _serialize(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _deserialize(raw: str) -> dict[str, Any]:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Некорректный формат профиля игрока в SQLite.")
        return data

    def _migrate_from_json_if_needed(self) -> None:
        if not self.legacy_json_path or not self.legacy_json_path.exists():
            return

        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM players").fetchone()
            if row and row["count"]:
                return

        if self.legacy_json_path.stat().st_size == 0:
            return

        legacy_storage = JsonStorage(str(self.legacy_json_path))
        legacy_data = legacy_storage.load()
        if not legacy_data.get("players"):
            return

        self.save(legacy_data)

    def load(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            data = self.empty_schema()

            for row in connection.execute("SELECT game_id, data FROM players"):
                data["players"][row["game_id"]] = self._deserialize(row["data"])

            for row in connection.execute("SELECT platform_key, game_id FROM platform_links"):
                data["platform_links"][row["platform_key"]] = row["game_id"]

            for game_id, player in data["players"].items():
                name = player.get("name")
                if name:
                    data["names"][name.casefold()] = game_id

            for row in connection.execute("SELECT code, game_id, created_at FROM link_codes"):
                data["link_codes"][row["code"]] = {
                    "game_id": row["game_id"],
                    "created_at": row["created_at"],
                }

            for row in connection.execute(
                "SELECT token, game_id, scope, platform, created_at, expires_at, used "
                "FROM site_sessions"
            ):
                data["site_sessions"][row["token"]] = {
                    "game_id": row["game_id"],
                    "scope": row["scope"],
                    "platform": row["platform"],
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "used": bool(row["used"]),
                }

            promo_data = {"codes": {}}
            for row in connection.execute("SELECT code, data FROM promo_codes"):
                promo_data["codes"][row["code"]] = self._deserialize(row["data"])
            data["promo_codes"] = promo_data

            return data

    def save(self, data: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            now = datetime.now(timezone.utc).isoformat()
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("DELETE FROM site_sessions")
                connection.execute("DELETE FROM link_codes")
                connection.execute("DELETE FROM platform_links")
                connection.execute("DELETE FROM players")

                for game_id, player in data.get("players", {}).items():
                    if not isinstance(player, dict):
                        continue
                    player["game_id"] = game_id
                    player["id"] = game_id
                    player.setdefault("public_id", str(uuid.uuid4()))
                    player.setdefault("linked_accounts", {})
                    created_at = player.get("created_at") or now
                    name = player.get("name") or ""
                    connection.execute(
                        """
                        INSERT INTO players(game_id, public_id, name_key, data, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            game_id,
                            player["public_id"],
                            name.casefold() if name else None,
                            self._serialize(player),
                            created_at,
                            now,
                        ),
                    )

                platform_links = data.get("platform_links") or {}
                if not platform_links:
                    for game_id, player in data.get("players", {}).items():
                        for platform, external_user_id in player.get("linked_accounts", {}).items():
                            if external_user_id:
                                platform_links[
                                    self.make_platform_key(platform, external_user_id)
                                ] = game_id

                for platform_key, game_id in platform_links.items():
                    if game_id not in data.get("players", {}):
                        continue
                    platform, _, external_user_id = platform_key.partition(":")
                    if not platform or not external_user_id:
                        continue
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO platform_links(
                            platform_key, game_id, platform, external_user_id, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (platform_key, game_id, platform, external_user_id, now),
                    )

                for code, link_data in data.get("link_codes", {}).items():
                    game_id = link_data.get("game_id")
                    if game_id not in data.get("players", {}):
                        continue
                    connection.execute(
                        "INSERT OR REPLACE INTO link_codes(code, game_id, created_at) VALUES (?, ?, ?)",
                        (code, game_id, link_data.get("created_at") or now),
                    )

                for token, session in data.get("site_sessions", {}).items():
                    game_id = session.get("game_id")
                    if game_id not in data.get("players", {}):
                        continue
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO site_sessions(
                            token, game_id, scope, platform, created_at, expires_at, used
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            token,
                            game_id,
                            session.get("scope") or "",
                            session.get("platform") or "",
                            session.get("created_at") or now,
                            session.get("expires_at") or now,
                            1 if session.get("used") else 0,
                        ),
                    )

                if "promo_codes" in data:
                    connection.execute("DELETE FROM promo_codes")
                    for code, promo in (data.get("promo_codes") or {}).get("codes", {}).items():
                        connection.execute(
                            "INSERT OR REPLACE INTO promo_codes(code, data, updated_at) VALUES (?, ?, ?)",
                            (code, self._serialize(promo), promo.get("updated_at") or now),
                        )

                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def generate_game_id(self) -> str:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT game_id FROM players").fetchall()
            existing = {row["game_id"] for row in rows}
            return self._generate_game_id_from_existing(existing)

    def get_player_by_game_id(self, game_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM players WHERE game_id = ?",
                (game_id,),
            ).fetchone()
            return self._deserialize(row["data"]) if row else None

    def get_player_by_platform(
        self,
        platform: str,
        external_user_id: str | int,
    ) -> dict[str, Any] | None:
        platform_key = self.make_platform_key(platform, external_user_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT players.data
                FROM platform_links
                JOIN players ON players.game_id = platform_links.game_id
                WHERE platform_links.platform_key = ?
                """,
                (platform_key,),
            ).fetchone()
            return self._deserialize(row["data"]) if row else None

    def get_player(self, platform_user_id: str) -> dict[str, Any] | None:
        platform, external_user_id = self.parse_old_platform_user_id(platform_user_id)
        if platform and external_user_id:
            return self.get_player_by_platform(platform, external_user_id)
        return None

    def save_new_player(
        self,
        player: dict[str, Any],
        platform: str,
        external_user_id: str | int,
    ) -> None:
        with self._lock, self._connect() as connection:
            game_id = player["game_id"]
            platform_key = self.make_platform_key(platform, external_user_id)
            name = player.get("name", "").casefold()
            now = datetime.now(timezone.utc).isoformat()

            if connection.execute(
                "SELECT 1 FROM players WHERE game_id = ?",
                (game_id,),
            ).fetchone():
                raise ValueError(f"Игрок с game_id {game_id} уже существует.")

            if connection.execute(
                "SELECT 1 FROM platform_links WHERE platform_key = ?",
                (platform_key,),
            ).fetchone():
                raise ValueError("Эта платформа уже привязана к персонажу.")

            if name and connection.execute(
                "SELECT 1 FROM players WHERE name_key = ?",
                (name,),
            ).fetchone():
                raise ValueError("Это имя уже занято.")

            player.setdefault("linked_accounts", {})[platform] = str(external_user_id)
            player["game_id"] = game_id
            player["id"] = game_id
            player.setdefault("public_id", str(uuid.uuid4()))
            created_at = player.get("created_at") or now

            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO players(game_id, public_id, name_key, data, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        game_id,
                        player["public_id"],
                        name or None,
                        self._serialize(player),
                        created_at,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO platform_links(
                        platform_key, game_id, platform, external_user_id, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (platform_key, game_id, platform, str(external_user_id), now),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def save_player(self, platform_user_id: str, player: dict[str, Any]) -> None:
        platform, external_user_id = self.parse_old_platform_user_id(platform_user_id)
        if not platform or not external_user_id:
            raise ValueError("Неизвестный формат platform_user_id.")
        self.save_new_player(player, platform, external_user_id)

    def update_player(self, player: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            game_id = player.get("game_id") or player.get("id")
            if not game_id:
                raise ValueError("Нельзя обновить игрока без game_id.")

            existing = connection.execute(
                "SELECT 1 FROM players WHERE game_id = ?",
                (game_id,),
            ).fetchone()
            if not existing:
                raise ValueError(f"Игрок с game_id {game_id} не найден.")

            player["game_id"] = game_id
            player["id"] = game_id
            player.setdefault("public_id", str(uuid.uuid4()))
            player.setdefault("linked_accounts", {})
            name = player.get("name", "").casefold()
            now = datetime.now(timezone.utc).isoformat()

            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    UPDATE players
                    SET public_id = ?, name_key = ?, data = ?, updated_at = ?
                    WHERE game_id = ?
                    """,
                    (
                        player["public_id"],
                        name or None,
                        self._serialize(player),
                        now,
                        game_id,
                    ),
                )
                connection.execute(
                    "DELETE FROM platform_links WHERE game_id = ?",
                    (game_id,),
                )
                for platform, external_user_id in player.get("linked_accounts", {}).items():
                    if not external_user_id:
                        continue
                    platform_key = self.make_platform_key(platform, external_user_id)
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO platform_links(
                            platform_key, game_id, platform, external_user_id, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (platform_key, game_id, platform, str(external_user_id), now),
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def load_promo_data(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            data = {"codes": {}}
            for row in connection.execute("SELECT code, data FROM promo_codes"):
                data["codes"][row["code"]] = self._deserialize(row["data"])
            return data

    def save_promo_data(self, data: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("DELETE FROM promo_codes")
                for code, promo in (data.get("codes") or {}).items():
                    if not isinstance(promo, dict):
                        continue
                    connection.execute(
                        "INSERT OR REPLACE INTO promo_codes(code, data, updated_at) VALUES (?, ?, ?)",
                        (code, self._serialize(promo), promo.get("updated_at") or now),
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise


    def claim_active_timer_for_delivery(
        self,
        game_id: str,
        timer_id: str,
        owner: str,
        *,
        claim_ttl_seconds: int = 300,
        platform_filter: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically claim an expired active timer before sending its result."""
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT data FROM players WHERE game_id = ?",
                    (str(game_id),),
                ).fetchone()
                if not row:
                    connection.execute("ROLLBACK")
                    return None

                player = self._deserialize(row["data"])
                if not try_mark_timer_claimed(
                    player,
                    str(timer_id),
                    str(owner),
                    claim_ttl_seconds=claim_ttl_seconds,
                    platform_filter=platform_filter,
                    now=time.time(),
                ):
                    connection.execute("ROLLBACK")
                    return None

                player["game_id"] = str(game_id)
                player["id"] = str(game_id)
                player.setdefault("public_id", str(uuid.uuid4()))
                player.setdefault("linked_accounts", {})
                name = str(player.get("name") or "").casefold()
                now_iso = datetime.now(timezone.utc).isoformat()
                connection.execute(
                    """
                    UPDATE players
                    SET public_id = ?, name_key = ?, data = ?, updated_at = ?
                    WHERE game_id = ?
                    """,
                    (
                        player["public_id"],
                        name or None,
                        self._serialize(player),
                        now_iso,
                        str(game_id),
                    ),
                )
                connection.execute("COMMIT")
                return player
            except Exception:
                connection.execute("ROLLBACK")
                raise


    def claim_active_event_for_resolution(
        self,
        game_id: str,
        event_id: str | None,
        owner: str,
        *,
        claim_ttl_seconds: int = 120,
    ) -> dict[str, Any] | None:
        """Atomically claim active_event before granting any event reward."""
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT data FROM players WHERE game_id = ?",
                    (str(game_id),),
                ).fetchone()
                if not row:
                    connection.execute("ROLLBACK")
                    return None

                player = self._deserialize(row["data"])
                if not try_mark_active_event_claimed(
                    player,
                    str(event_id) if event_id else None,
                    str(owner),
                    claim_ttl_seconds=claim_ttl_seconds,
                    now=time.time(),
                ):
                    connection.execute("ROLLBACK")
                    return None

                player["game_id"] = str(game_id)
                player["id"] = str(game_id)
                player.setdefault("public_id", str(uuid.uuid4()))
                player.setdefault("linked_accounts", {})
                name = str(player.get("name") or "").casefold()
                now_iso = datetime.now(timezone.utc).isoformat()
                connection.execute(
                    """
                    UPDATE players
                    SET public_id = ?, name_key = ?, data = ?, updated_at = ?
                    WHERE game_id = ?
                    """,
                    (
                        player["public_id"],
                        name or None,
                        self._serialize(player),
                        now_iso,
                        str(game_id),
                    ),
                )
                connection.execute("COMMIT")
                return player
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def update_player_by_platform(
        self,
        platform: str,
        external_user_id: str | int,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        player = self.get_player_by_platform(platform, external_user_id)
        if player is None:
            return None
        player.update(updates)
        self.update_player(player)
        return player

    def is_name_taken(self, name: str) -> bool:
        with self._lock, self._connect() as connection:
            return connection.execute(
                "SELECT 1 FROM players WHERE name_key = ?",
                (name.casefold(),),
            ).fetchone() is not None

    def create_link_code(self, game_id: str) -> str:
        with self._lock, self._connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM players WHERE game_id = ?",
                (game_id,),
            ).fetchone():
                raise ValueError("Игрок не найден.")

            self._clear_expired_link_codes_connection(connection)
            now = datetime.now(timezone.utc).isoformat()

            while True:
                code = secrets.token_hex(3).upper()
                if not connection.execute(
                    "SELECT 1 FROM link_codes WHERE code = ?",
                    (code,),
                ).fetchone():
                    break

            connection.execute(
                "INSERT INTO link_codes(code, game_id, created_at) VALUES (?, ?, ?)",
                (code, game_id, now),
            )
            return code

    def connect_platform_by_code(
        self,
        code: str,
        platform: str,
        external_user_id: str | int,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        normalized_code = code.strip().upper().replace(" ", "")
        platform_key = self.make_platform_key(platform, external_user_id)

        with self._lock, self._connect() as connection:
            self._clear_expired_link_codes_connection(connection)
            link_row = connection.execute(
                "SELECT game_id FROM link_codes WHERE code = ?",
                (normalized_code,),
            ).fetchone()
            if not link_row:
                return False, "Код привязки не найден или уже истёк.", None

            game_id = link_row["game_id"]
            player_row = connection.execute(
                "SELECT data FROM players WHERE game_id = ?",
                (game_id,),
            ).fetchone()
            if not player_row:
                connection.execute("DELETE FROM link_codes WHERE code = ?", (normalized_code,))
                return False, "Персонаж для этого кода не найден.", None

            linked_row = connection.execute(
                "SELECT game_id FROM platform_links WHERE platform_key = ?",
                (platform_key,),
            ).fetchone()
            if linked_row and linked_row["game_id"] == game_id:
                connection.execute("DELETE FROM link_codes WHERE code = ?", (normalized_code,))
                return True, "Эта платформа уже была привязана к этому персонажу.", self._deserialize(player_row["data"])

            if linked_row and linked_row["game_id"] != game_id:
                return (
                    False,
                    "Эта платформа уже привязана к другому персонажу. Автоматически объединять разных персонажей нельзя.",
                    None,
                )

            player = self._deserialize(player_row["data"])
            player.setdefault("linked_accounts", {})[platform] = str(external_user_id)
            now = datetime.now(timezone.utc).isoformat()

            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    UPDATE players SET data = ?, updated_at = ? WHERE game_id = ?
                    """,
                    (self._serialize(player), now, game_id),
                )
                connection.execute(
                    """
                    INSERT INTO platform_links(
                        platform_key, game_id, platform, external_user_id, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (platform_key, game_id, platform, str(external_user_id), now),
                )
                connection.execute("DELETE FROM link_codes WHERE code = ?", (normalized_code,))
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

            return True, "Платформа успешно привязана к персонажу.", player

    def create_site_session(
        self,
        game_id: str,
        scope: str,
        platform: str,
        lifetime_minutes: int = 1440,
    ) -> str:
        with self._lock, self._connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM players WHERE game_id = ?",
                (game_id,),
            ).fetchone():
                raise ValueError("Игрок не найден.")

            now = datetime.now(timezone.utc)
            now_raw = now.isoformat()
            connection.execute(
                "DELETE FROM site_sessions WHERE expires_at <= ?",
                (now_raw,),
            )

            while True:
                token = secrets.token_urlsafe(24)
                if not connection.execute(
                    "SELECT 1 FROM site_sessions WHERE token = ?",
                    (token,),
                ).fetchone():
                    break

            connection.execute(
                """
                INSERT INTO site_sessions(token, game_id, scope, platform, created_at, expires_at, used)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    token,
                    game_id,
                    scope,
                    platform,
                    now_raw,
                    (now + timedelta(minutes=lifetime_minutes)).isoformat(),
                ),
            )
            return token

    def clear_expired_link_codes(self, data: dict[str, Any]) -> None:
        JsonStorage.clear_expired_link_codes(self, data)

    def _clear_expired_link_codes_connection(self, connection: sqlite3.Connection) -> None:
        now = datetime.now(timezone.utc)
        expired_codes: list[str] = []
        for row in connection.execute("SELECT code, created_at FROM link_codes"):
            try:
                created_at = datetime.fromisoformat(row["created_at"])
            except ValueError:
                expired_codes.append(row["code"])
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if now - created_at > timedelta(minutes=self.LINK_CODE_LIFETIME_MINUTES):
                expired_codes.append(row["code"])

        for code in expired_codes:
            connection.execute("DELETE FROM link_codes WHERE code = ?", (code,))
