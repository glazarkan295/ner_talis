"""VK-обработчики административных команд."""

from __future__ import annotations

from typing import Any

try:
    from vk_api.utils import get_random_id
except Exception:  # pragma: no cover - для локальных проверок без vk-api
    import random

    def get_random_id() -> int:
        return random.randint(1, 2_147_483_647)

from services.admin_access import check_vk_admin
from services.admin_command_service import execute_admin_command, is_admin_command


def normalize_vk_command_text(text: str) -> str:
    """Приводит VK-текст к формату обычной команды.

    В VK команда из беседы иногда приходит как:
    [club123|@bot] /admin_help
    /admin_help@clubname
    Поэтому перед разбором убираем упоминание и хвост после @.
    """

    stripped = str(text or "").strip()
    if stripped.startswith("[club") and "]" in stripped:
        stripped = stripped.split("]", 1)[1].strip()

    if stripped.startswith("/") and " " in stripped:
        command, rest = stripped.split(" ", 1)
        if "@" in command:
            command = command.split("@", 1)[0]
        return f"{command} {rest}".strip()

    if stripped.startswith("/") and "@" in stripped:
        return stripped.split("@", 1)[0].strip()

    return stripped


def _send(vk_api: Any, peer_id: str | int | None, message: str) -> None:
    vk_api.messages.send(
        peer_id=peer_id,
        random_id=get_random_id(),
        message=message,
    )


def try_handle_vk_admin_command(*, text: str, peer_id: str | int | None, external_user_id: str | int | None, storage: Any, vk_api: Any) -> bool:
    stripped = normalize_vk_command_text(text)
    if not stripped:
        return False

    if stripped == "/admin_id":
        _send(
            vk_api,
            peer_id,
            f"ID для настройки админ-беседы:\npeer_id: {peer_id}\nuser_id: {external_user_id}",
        )
        return True

    if not is_admin_command(stripped):
        return False

    access = check_vk_admin(peer_id, external_user_id)
    if not access.allowed:
        _send(vk_api, peer_id, access.reason)
        return True

    result = execute_admin_command(
        text=stripped,
        storage=storage,
        platform="vk",
        admin_user_id=external_user_id or "unknown",
    )
    if result.handled:
        _send(vk_api, peer_id, result.text)
        return True

    return False
