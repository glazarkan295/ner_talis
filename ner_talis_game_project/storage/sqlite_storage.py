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
            "admin_panel_sessions": {},
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

                CREATE TABLE IF NOT EXISTS admin_panel_sessions (
                    token TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outgoing_messages (
                    id TEXT PRIMARY KEY,
                    delivery_key TEXT,
                    game_id TEXT,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    next_attempt_at TEXT,
                    created_at TEXT NOT NULL,
                    data TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outgoing_message_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_site_sessions_expires_at
                    ON site_sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_admin_panel_sessions_expires_at
                    ON admin_panel_sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_outgoing_status_next
                    ON outgoing_messages(status, next_attempt_at);
                CREATE INDEX IF NOT EXISTS idx_outgoing_delivery_key
                    ON outgoing_messages(delivery_key);
                CREATE INDEX IF NOT EXISTS idx_outgoing_game_id
                    ON outgoing_messages(game_id);
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

            for row in connection.execute("SELECT token, data FROM admin_panel_sessions"):
                data["admin_panel_sessions"][row["token"]] = self._deserialize(row["data"])

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
                connection.execute("DELETE FROM admin_panel_sessions")
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

                for token, session in data.get("admin_panel_sessions", {}).items():
                    if not isinstance(session, dict):
                        continue
                    connection.execute(
                        "INSERT OR REPLACE INTO admin_panel_sessions(token, data, expires_at) VALUES (?, ?, ?)",
                        (token, self._serialize(session), session.get("expires_at") or now),
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
                "SELECT data FROM players WHERE game_id = ?",
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

            # pending_bot_messages — атомарный outbox (enqueue/dequeue). Полное
            # сохранение игрока не должно его перезаписывать: сохраняем копию с
            # durable-значением, не мутируя объект вызывающей стороны.
            durable_pending = []
            try:
                durable_pending = self._deserialize(existing["data"]).get("pending_bot_messages", [])
            except Exception:
                durable_pending = []
            to_store = dict(player)
            to_store["pending_bot_messages"] = durable_pending

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
                        self._serialize(to_store),
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

    def enqueue_bot_messages(self, game_id: str, messages: list[Any]) -> bool:
        items = [message for message in (messages or []) if message not in (None, "")]
        if not items:
            return False
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT data FROM players WHERE game_id = ?", (game_id,)
                ).fetchone()
                if not row:
                    connection.execute("ROLLBACK")
                    return False
                data = self._deserialize(row["data"])
                pending = data.get("pending_bot_messages")
                if not isinstance(pending, list):
                    pending = []
                pending.extend(items)
                data["pending_bot_messages"] = pending
                connection.execute(
                    "UPDATE players SET data = ? WHERE game_id = ?",
                    (self._serialize(data), game_id),
                )
                connection.execute("COMMIT")
                return True
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def dequeue_bot_messages(self, game_id: str) -> list[Any]:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT data FROM players WHERE game_id = ?", (game_id,)
                ).fetchone()
                if not row:
                    connection.execute("ROLLBACK")
                    return []
                data = self._deserialize(row["data"])
                pending = data.get("pending_bot_messages")
                if not isinstance(pending, list) or not pending:
                    connection.execute("ROLLBACK")
                    return []
                data["pending_bot_messages"] = []
                connection.execute(
                    "UPDATE players SET data = ? WHERE game_id = ?",
                    (self._serialize(data), game_id),
                )
                connection.execute("COMMIT")
                return list(pending)
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def enqueue_bot_messages_bulk(self, game_ids: list[str], messages: list[Any]) -> int:
        items = [message for message in (messages or []) if message not in (None, "")]
        targets = [str(gid) for gid in (game_ids or []) if gid]
        if not items or not targets:
            return 0
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                count = 0
                for gid in targets:
                    row = connection.execute(
                        "SELECT data FROM players WHERE game_id = ?", (gid,)
                    ).fetchone()
                    if not row:
                        continue
                    data = self._deserialize(row["data"])
                    pending = data.get("pending_bot_messages")
                    if not isinstance(pending, list):
                        pending = []
                    pending.extend(items)
                    data["pending_bot_messages"] = pending
                    connection.execute(
                        "UPDATE players SET data = ? WHERE game_id = ?",
                        (self._serialize(data), gid),
                    )
                    count += 1
                connection.execute("COMMIT")
                return count
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def list_player_audience_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._lock, self._connect() as connection:
            for row in connection.execute("SELECT game_id, data FROM players"):
                try:
                    data = self._deserialize(row["data"])
                except Exception:
                    data = {}
                rows.append({
                    "game_id": row["game_id"],
                    "gender": data.get("gender"),
                    "level": data.get("level", 1),
                })
        return rows

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

    def save_promo_code(self, code: str, promo: dict[str, Any]) -> None:
        """Upsert одного промокода без полной перезаписи таблицы."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO promo_codes(code, data, updated_at) VALUES (?, ?, ?)",
                (str(code), self._serialize(promo), promo.get("updated_at") or now),
            )

    def delete_promo_code(self, code: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM promo_codes WHERE code = ?", (str(code),))
            return cursor.rowcount > 0

    def claim_promo_use(self, code: str, game_id: str, *, one_use_per_player: bool = True) -> tuple[bool, str, dict[str, Any] | None]:
        """Атомарно занимает одно использование промокода.

        BEGIN IMMEDIATE берёт write-lock SQLite, поэтому read-modify-write над
        одной строкой не пересекается с другим погашением того же кода.
        """
        now = datetime.now(timezone.utc)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT data FROM promo_codes WHERE code = ?",
                    (str(code),),
                ).fetchone()
                if not row:
                    connection.execute("ROLLBACK")
                    return False, "not_found", None
                promo = self._deserialize(row["data"])
                if not isinstance(promo, dict) or not promo.get("active"):
                    connection.execute("ROLLBACK")
                    return False, "inactive", None
                raw_expires = promo.get("expires_at")
                if raw_expires:
                    try:
                        expires_at = datetime.fromisoformat(str(raw_expires).replace("Z", "+00:00"))
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                    except ValueError:
                        connection.execute("ROLLBACK")
                        return False, "broken_expiry", None
                    if expires_at < now:
                        connection.execute("ROLLBACK")
                        return False, "expired", None
                used_by = {str(value) for value in promo.get("used_by", [])}
                if one_use_per_player and promo.get("one_use_per_player", True) and str(game_id) in used_by:
                    connection.execute("ROLLBACK")
                    return False, "already_used", None
                uses_left = int(promo.get("uses_left", 0) or 0)
                if uses_left <= 0:
                    connection.execute("ROLLBACK")
                    return False, "exhausted", None
                promo["uses_left"] = uses_left - 1
                promo.setdefault("used_by", []).append(str(game_id))
                promo["updated_at"] = now.isoformat()
                connection.execute(
                    "UPDATE promo_codes SET data = ?, updated_at = ? WHERE code = ?",
                    (self._serialize(promo), now.isoformat(), str(code)),
                )
                connection.execute("COMMIT")
                return True, "ok", promo.get("reward") or {}
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def refund_promo_use(self, code: str, game_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT data FROM promo_codes WHERE code = ?",
                    (str(code),),
                ).fetchone()
                if not row:
                    connection.execute("ROLLBACK")
                    return
                promo = self._deserialize(row["data"])
                if not isinstance(promo, dict):
                    connection.execute("ROLLBACK")
                    return
                promo["uses_left"] = int(promo.get("uses_left", 0) or 0) + 1
                used_by = [str(value) for value in promo.get("used_by", [])]
                if str(game_id) in used_by:
                    used_by.remove(str(game_id))
                promo["used_by"] = used_by
                connection.execute(
                    "UPDATE promo_codes SET data = ?, updated_at = ? WHERE code = ?",
                    (self._serialize(promo), now, str(code)),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    # --- Точечные методы админ-сессий -------------------------------------
    # admin_panel_service использует их вместо load()/save(), чтобы запросы
    # админ-панели не переписывали таблицу игроков целиком.

    def get_admin_panel_session(self, token: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM admin_panel_sessions WHERE token = ?",
                (str(token),),
            ).fetchone()
            return self._deserialize(row["data"]) if row else None

    def put_admin_panel_session(self, token: str, session: dict[str, Any]) -> None:
        expires_at = session.get("expires_at") or datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO admin_panel_sessions(token, data, expires_at) VALUES (?, ?, ?)",
                (str(token), self._serialize(session), str(expires_at)),
            )

    def list_admin_panel_sessions(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            result: list[dict[str, Any]] = []
            for row in connection.execute("SELECT token, data FROM admin_panel_sessions"):
                session = self._deserialize(row["data"])
                if isinstance(session, dict):
                    session = dict(session)
                    session["token"] = row["token"]
                    result.append(session)
            return result

    def delete_admin_panel_session(self, token: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM admin_panel_sessions WHERE token = ?", (str(token),))
            # rowcount > 0 служит атомарным «claim» одноразового токена активации.
            return bool((cursor.rowcount or 0) > 0)

    def delete_admin_panel_sessions_for_admin(self, admin_key: str, scope: str) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM admin_panel_sessions"
                " WHERE json_extract(data, '$.admin_key') = ? AND json_extract(data, '$.scope') = ?",
                (str(admin_key), str(scope)),
            )
            return cursor.rowcount

    def cleanup_expired_admin_panel_sessions(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM admin_panel_sessions WHERE expires_at <= ?",
                (now,),
            )
            return cursor.rowcount

    # --- Исходящая очередь сообщений (row-per-message, для масштаба) -------
    _OUTGOING_PRIORITY_ORDER = (
        "CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
        " WHEN 'normal' THEN 2 WHEN 'low' THEN 3 ELSE 4 END"
    )

    def _outgoing_cols(self, message: dict[str, Any]) -> tuple:
        return (
            str(message.get("id")),
            str(message.get("delivery_key") or ""),
            str(message.get("game_id") or ""),
            str(message.get("status") or "queued"),
            str(message.get("priority") or "normal"),
            message.get("next_attempt_at"),
            str(message.get("created_at") or ""),
            self._serialize(message),
        )

    def enqueue_outgoing_message(self, message: dict[str, Any]) -> dict[str, Any]:
        delivery_key = str(message.get("delivery_key") or "")
        with self._lock, self._connect() as connection:
            if delivery_key:
                row = connection.execute(
                    "SELECT data FROM outgoing_messages WHERE delivery_key = ? LIMIT 1",
                    (delivery_key,),
                ).fetchone()
                if row:
                    return self._deserialize(row["data"])
            connection.execute(
                "INSERT OR REPLACE INTO outgoing_messages"
                "(id, delivery_key, game_id, status, priority, next_attempt_at, created_at, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                self._outgoing_cols(message),
            )
            return dict(message)

    def get_outgoing_message(self, message_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM outgoing_messages WHERE id = ?", (str(message_id),)
            ).fetchone()
            return self._deserialize(row["data"]) if row else None

    def update_outgoing_message(self, message_id: str, message: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO outgoing_messages"
                "(id, delivery_key, game_id, status, priority, next_attempt_at, created_at, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                self._outgoing_cols({**message, "id": str(message_id)}),
            )

    def list_outgoing_messages(self, *, status: str | None = None, game_id: str | None = None, errors_only: bool = False, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(str(status))
        if game_id:
            clauses.append("game_id = ?")
            params.append(str(game_id))
        if errors_only:
            clauses.append("status IN ('failed', 'blocked', 'retry_wait')")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([max(1, min(int(limit), 1000)), max(0, int(offset))])
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"SELECT data FROM outgoing_messages{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params),
            ).fetchall()
            return [self._deserialize(r["data"]) for r in rows]

    def claim_due_outgoing_messages(self, *, now_iso: str, limit: int = 25) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id, data FROM outgoing_messages"
                " WHERE status IN ('queued', 'retry_wait')"
                " AND (next_attempt_at IS NULL OR next_attempt_at <= ?)"
                f" ORDER BY {self._OUTGOING_PRIORITY_ORDER}, created_at LIMIT ?",
                (now_iso, max(1, int(limit))),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                message = self._deserialize(row["data"])
                if not isinstance(message, dict):
                    continue
                message["status"] = "sending"
                connection.execute(
                    "UPDATE outgoing_messages SET status = 'sending', data = ? WHERE id = ?",
                    (self._serialize(message), row["id"]),
                )
                claimed.append(message)
            return claimed

    def outgoing_message_status_counts(self) -> dict[str, int]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS n FROM outgoing_messages GROUP BY status"
            ).fetchall()
            return {row["status"]: int(row["n"]) for row in rows}

    def get_outgoing_dispatcher_meta(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM outgoing_message_meta WHERE id = 1"
            ).fetchone()
            meta = self._deserialize(row["data"]) if row else {}
            return meta if isinstance(meta, dict) else {}

    def set_outgoing_dispatcher_meta(self, meta: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO outgoing_message_meta(id, data) VALUES (1, ?)",
                (self._serialize(meta or {}),),
            )

    def list_admin_player_cards(self, query: str = "", limit: int = 200) -> list[dict[str, Any]]:
        """Лёгкий список игроков для админ-панели без чтения полных профилей."""
        limit = max(1, min(int(limit or 200), 1000))
        needle = f"%{str(query or '').strip().casefold()}%"
        with self._lock, self._connect() as connection:
            if str(query or "").strip():
                rows = connection.execute(
                    "SELECT game_id, public_id, data FROM players"
                    " WHERE name_key LIKE ? OR lower(game_id) LIKE ? OR lower(public_id) LIKE ?"
                    " ORDER BY name_key, game_id LIMIT ?",
                    (needle, needle, needle, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT game_id, public_id, data FROM players ORDER BY name_key, game_id LIMIT ?",
                    (limit,),
                ).fetchall()
        cards = []
        for row in rows:
            player = self._deserialize(row["data"])
            cards.append({
                "game_id": row["game_id"],
                "name": player.get("name") or "без имени",
                "level": int(player.get("level") or 1),
                "public_id": row["public_id"],
            })
        return cards


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
