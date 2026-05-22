import json
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from storage.timer_claims import try_mark_timer_claimed
from storage.event_claims import try_mark_active_event_claimed


class JsonStorage:
    """JSON-хранилище игроков с единым игровым ID.

    Главный идентификатор персонажа: game_id.
    Telegram/VK ID хранятся как привязки к game_id.

    Важно: для прототипа используется JSON. При одновременной работе Telegram
    и VK в одном процессе используется общий lock и атомарная запись файла.
    Для продакшена лучше заменить этот слой на PostgreSQL.
    """

    LINK_CODE_LIFETIME_MINUTES = 15
    _lock = threading.RLock()

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            self.save(self.empty_schema())
        else:
            self.migrate_if_needed()

    @staticmethod
    def empty_schema() -> dict[str, Any]:
        return {
            "players": {},
            "platform_links": {},
            "names": {},
            "link_codes": {},
            "site_sessions": {},
        }

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists() or self.path.stat().st_size == 0:
                return self.empty_schema()

            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            data.setdefault("players", {})
            data.setdefault("platform_links", {})
            data.setdefault("names", {})
            data.setdefault("link_codes", {})
            data.setdefault("site_sessions", {})
            return data

    def save(self, data: dict[str, Any]) -> None:
        with self._lock:
            temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            temp_path.replace(self.path)

    def migrate_if_needed(self) -> None:
        """Мягко переводит старый формат players[tg_123/vk_123] в новый формат."""
        with self._lock:
            data = self.load()
            players = data.get("players", {})

            # Если хотя бы один игрок уже лежит по game_id, считаем схему новой.
            new_format_detected = any(
                isinstance(player, dict) and player.get("game_id") == key
                for key, player in players.items()
            )
            if new_format_detected:
                self.rebuild_indexes(data)
                self.save(data)
                return

            new_data = self.empty_schema()

            for old_key, player in players.items():
                if not isinstance(player, dict):
                    continue

                game_id = player.get("game_id") or player.get("id") or self._generate_game_id_from_data(new_data)
                player["game_id"] = game_id
                player["id"] = game_id
                player.setdefault("public_id", str(uuid.uuid4()))
                player.setdefault("linked_accounts", {})

                platform = player.get("platform")
                platform_user_id = player.get("platform_user_id") or old_key
                parsed_platform, external_user_id = self.parse_old_platform_user_id(
                    platform_user_id,
                    platform,
                )

                if parsed_platform and external_user_id:
                    player["linked_accounts"][parsed_platform] = str(external_user_id)
                    link_key = self.make_platform_key(parsed_platform, external_user_id)
                    new_data["platform_links"][link_key] = game_id

                new_data["players"][game_id] = player
                name = player.get("name")
                if name:
                    new_data["names"][name.casefold()] = game_id

            self.save(new_data)

    def rebuild_indexes(self, data: dict[str, Any] | None = None) -> None:
        if data is None:
            data = self.load()

        data["platform_links"] = {}
        data["names"] = {}

        for game_id, player in data.get("players", {}).items():
            if not isinstance(player, dict):
                continue

            player["game_id"] = game_id
            player["id"] = game_id
            player.setdefault("public_id", str(uuid.uuid4()))
            player.setdefault("linked_accounts", {})

            name = player.get("name")
            if name:
                data["names"][name.casefold()] = game_id

            for platform, external_user_id in player.get("linked_accounts", {}).items():
                if external_user_id:
                    key = self.make_platform_key(platform, str(external_user_id))
                    data["platform_links"][key] = game_id

    @staticmethod
    def make_platform_key(platform: str, external_user_id: str | int) -> str:
        return f"{platform}:{external_user_id}"

    @staticmethod
    def parse_old_platform_user_id(
        platform_user_id: str,
        platform: str | None = None,
    ) -> tuple[str | None, str | None]:
        if platform == "telegram":
            return "telegram", platform_user_id.removeprefix("tg_")
        if platform == "vk":
            return "vk", platform_user_id.removeprefix("vk_")

        if platform_user_id.startswith("tg_"):
            return "telegram", platform_user_id[3:]
        if platform_user_id.startswith("vk_"):
            return "vk", platform_user_id[3:]

        return None, None

    @staticmethod
    def _generate_game_id_from_data(data: dict[str, Any]) -> str:
        while True:
            game_id = f"NT-{uuid.uuid4().hex[:10].upper()}"
            if game_id not in data.get("players", {}):
                return game_id

    def generate_game_id(self) -> str:
        with self._lock:
            data = self.load()
            return self._generate_game_id_from_data(data)

    def get_player_by_game_id(self, game_id: str) -> dict[str, Any] | None:
        data = self.load()
        return data.get("players", {}).get(game_id)

    def get_player_by_platform(
        self,
        platform: str,
        external_user_id: str | int,
    ) -> dict[str, Any] | None:
        data = self.load()
        key = self.make_platform_key(platform, external_user_id)
        game_id = data.get("platform_links", {}).get(key)
        if not game_id:
            return None
        return data.get("players", {}).get(game_id)

    def get_player(self, platform_user_id: str) -> dict[str, Any] | None:
        """Совместимость со старым кодом: tg_123 / vk_123."""
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
        with self._lock:
            data = self.load()
            game_id = player["game_id"]

            if game_id in data.get("players", {}):
                raise ValueError(f"Игрок с game_id {game_id} уже существует.")

            link_key = self.make_platform_key(platform, external_user_id)
            if link_key in data.get("platform_links", {}):
                raise ValueError("Эта платформа уже привязана к персонажу.")

            name = player.get("name", "").casefold()
            if name and name in data.get("names", {}):
                raise ValueError("Это имя уже занято.")

            player.setdefault("linked_accounts", {})[platform] = str(external_user_id)
            player["game_id"] = game_id
            player["id"] = game_id

            data["players"][game_id] = player
            data["platform_links"][link_key] = game_id
            if name:
                data["names"][name] = game_id

            self.save(data)

    def save_player(self, platform_user_id: str, player: dict[str, Any]) -> None:
        """Совместимость со старым кодом."""
        platform, external_user_id = self.parse_old_platform_user_id(platform_user_id)
        if not platform or not external_user_id:
            raise ValueError("Неизвестный формат platform_user_id.")
        self.save_new_player(player, platform, external_user_id)

    def update_player(self, player: dict[str, Any]) -> None:
        """Обновляет существующего игрока по game_id и перестраивает индексы."""
        with self._lock:
            data = self.load()
            game_id = player.get("game_id") or player.get("id")

            if not game_id:
                raise ValueError("Нельзя обновить игрока без game_id.")

            if game_id not in data.get("players", {}):
                raise ValueError(f"Игрок с game_id {game_id} не найден.")

            player["game_id"] = game_id
            player["id"] = game_id
            data["players"][game_id] = player
            self.rebuild_indexes(data)
            self.save(data)


    def claim_active_timer_for_delivery(
        self,
        game_id: str,
        timer_id: str,
        owner: str,
        *,
        claim_ttl_seconds: int = 300,
        platform_filter: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically claim an expired active timer before sending its result.

        This prevents duplicate timer-completion messages when several bot
        processes recover or fire the same persisted timer.
        """
        with self._lock:
            data = self.load()
            player = data.get("players", {}).get(str(game_id))
            if not isinstance(player, dict):
                return None

            if not try_mark_timer_claimed(
                player,
                str(timer_id),
                str(owner),
                claim_ttl_seconds=claim_ttl_seconds,
                platform_filter=platform_filter,
                now=time.time(),
            ):
                return None

            player["game_id"] = str(game_id)
            player["id"] = str(game_id)
            data["players"][str(game_id)] = player
            self.rebuild_indexes(data)
            self.save(data)
            return player


    def claim_active_event_for_resolution(
        self,
        game_id: str,
        event_id: str | None,
        owner: str,
        *,
        claim_ttl_seconds: int = 120,
    ) -> dict[str, Any] | None:
        """Atomically claim active_event before granting any event reward."""
        with self._lock:
            data = self.load()
            player = data.get("players", {}).get(str(game_id))
            if not isinstance(player, dict):
                return None

            if not try_mark_active_event_claimed(
                player,
                str(event_id) if event_id else None,
                str(owner),
                claim_ttl_seconds=claim_ttl_seconds,
                now=time.time(),
            ):
                return None

            player["game_id"] = str(game_id)
            player["id"] = str(game_id)
            data["players"][str(game_id)] = player
            self.rebuild_indexes(data)
            self.save(data)
            return player

    def update_player_by_platform(
        self,
        platform: str,
        external_user_id: str | int,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Обновляет игрока, найденного по платформе, и возвращает новый профиль."""
        with self._lock:
            data = self.load()
            platform_key = self.make_platform_key(platform, external_user_id)
            game_id = data.get("platform_links", {}).get(platform_key)

            if not game_id:
                return None

            player = data.get("players", {}).get(game_id)
            if not player:
                return None

            player.update(updates)
            player["game_id"] = game_id
            player["id"] = game_id
            data["players"][game_id] = player
            self.rebuild_indexes(data)
            self.save(data)
            return player

    def is_name_taken(self, name: str) -> bool:
        data = self.load()
        return name.casefold() in data.get("names", {})

    def create_link_code(self, game_id: str) -> str:
        with self._lock:
            data = self.load()
            if game_id not in data.get("players", {}):
                raise ValueError("Игрок не найден.")

            self.clear_expired_link_codes(data)

            while True:
                code = secrets.token_hex(3).upper()
                if code not in data.get("link_codes", {}):
                    break

            data["link_codes"][code] = {
                "game_id": game_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.save(data)
            return code

    def connect_platform_by_code(
        self,
        code: str,
        platform: str,
        external_user_id: str | int,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        with self._lock:
            data = self.load()
            self.clear_expired_link_codes(data)

            normalized_code = code.strip().upper().replace(" ", "")
            link_data = data.get("link_codes", {}).get(normalized_code)
            if not link_data:
                self.save(data)
                return False, "Код привязки не найден или уже истёк.", None

            game_id = link_data.get("game_id")
            player = data.get("players", {}).get(game_id)
            if not player:
                data["link_codes"].pop(normalized_code, None)
                self.save(data)
                return False, "Персонаж для этого кода не найден.", None

            platform_key = self.make_platform_key(platform, external_user_id)
            linked_game_id = data.get("platform_links", {}).get(platform_key)

            if linked_game_id == game_id:
                data["link_codes"].pop(normalized_code, None)
                self.save(data)
                return True, "Эта платформа уже была привязана к этому персонажу.", player

            if linked_game_id and linked_game_id != game_id:
                return (
                    False,
                    "Эта платформа уже привязана к другому персонажу. Автоматически объединять разных персонажей нельзя.",
                    None,
                )

            player.setdefault("linked_accounts", {})[platform] = str(external_user_id)
            data["platform_links"][platform_key] = game_id
            data["players"][game_id] = player
            data["link_codes"].pop(normalized_code, None)
            self.save(data)

            return True, "Платформа успешно привязана к персонажу.", player

    def create_site_session(
        self,
        game_id: str,
        scope: str,
        platform: str,
        lifetime_minutes: int = 15,
    ) -> str:
        """Создаёт короткоживущий токен для входа на сайт из бота."""
        with self._lock:
            data = self.load()

            if game_id not in data.get("players", {}):
                raise ValueError("Игрок не найден.")

            data.setdefault("site_sessions", {})

            now = datetime.now(timezone.utc)
            expired_tokens = []
            for token, session in data["site_sessions"].items():
                raw_expires_at = session.get("expires_at")
                if not raw_expires_at:
                    expired_tokens.append(token)
                    continue

                try:
                    expires_at = datetime.fromisoformat(raw_expires_at)
                except ValueError:
                    expired_tokens.append(token)
                    continue

                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                if expires_at <= now:
                    expired_tokens.append(token)

            for token in expired_tokens:
                data["site_sessions"].pop(token, None)

            while True:
                token = secrets.token_urlsafe(24)
                if token not in data["site_sessions"]:
                    break

            data["site_sessions"][token] = {
                "game_id": game_id,
                "scope": scope,
                "platform": platform,
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=lifetime_minutes)).isoformat(),
                "used": False,
            }
            self.save(data)
            return token

    def clear_expired_link_codes(self, data: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        expired_codes: list[str] = []

        for code, link_data in data.get("link_codes", {}).items():
            raw_created_at = link_data.get("created_at")
            if not raw_created_at:
                expired_codes.append(code)
                continue

            try:
                created_at = datetime.fromisoformat(raw_created_at)
            except ValueError:
                expired_codes.append(code)
                continue

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            if now - created_at > timedelta(minutes=self.LINK_CODE_LIFETIME_MINUTES):
                expired_codes.append(code)

        for code in expired_codes:
            data.get("link_codes", {}).pop(code, None)
