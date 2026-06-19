from typing import Any, Protocol


class PlayerStorage(Protocol):
    def load(self) -> dict[str, Any]:
        ...

    def save(self, data: dict[str, Any]) -> None:
        ...

    def generate_game_id(self) -> str:
        ...

    def get_player_by_game_id(self, game_id: str) -> dict[str, Any] | None:
        ...

    def get_player_by_platform(
        self,
        platform: str,
        external_user_id: str | int,
    ) -> dict[str, Any] | None:
        ...

    def save_new_player(
        self,
        player: dict[str, Any],
        platform: str,
        external_user_id: str | int,
    ) -> None:
        ...

    def update_player(self, player: dict[str, Any]) -> None:
        ...

    def enqueue_bot_messages(
        self,
        game_id: str,
        messages: list[Any],
    ) -> bool:
        """Atomically append outbox messages to a player's pending_bot_messages.

        Implementations MUST modify only the pending_bot_messages field at the
        storage row level, never via a full-player read-modify-write, so a
        concurrent player save cannot clobber freshly queued messages.
        """
        ...

    def dequeue_bot_messages(self, game_id: str) -> list[Any]:
        """Atomically read and clear a player's pending_bot_messages."""
        ...

    def enqueue_bot_messages_bulk(
        self,
        game_ids: list[str],
        messages: list[Any],
    ) -> int:
        """Append the same outbox messages to many players in one operation."""
        ...

    def list_player_audience_rows(self) -> list[dict[str, Any]]:
        """Lightweight rows (game_id/gender/level) for broadcast targeting.

        Avoids reconstructing full player objects (and per-player link queries)
        just to filter recipients by gender/level.
        """
        ...

    def hard_delete_player_by_game_id(self, game_id: str) -> bool:
        ...

    def delete_player(self, game_id: str) -> bool:
        ...

    def get_player_by_public_id(self, public_id: str) -> dict[str, Any] | None:
        ...

    def is_name_taken(self, name: str) -> bool:
        ...

    def create_link_code(self, game_id: str) -> str:
        ...

    def connect_platform_by_code(
        self,
        code: str,
        platform: str,
        external_user_id: str | int,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        ...


    def claim_active_event_for_resolution(
        self,
        game_id: str,
        event_id: str | None,
        owner: str,
        *,
        claim_ttl_seconds: int = 120,
    ) -> dict[str, Any] | None:
        ...

    def create_site_session(
        self,
        game_id: str,
        scope: str,
        platform: str,
        lifetime_minutes: int = 1440,
    ) -> str:
        ...
