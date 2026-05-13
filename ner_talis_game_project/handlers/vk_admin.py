"""VK-обработчики административных команд."""

from __future__ import annotations

from typing import Any

from services.admin_access import check_vk_admin
from services.admin_command_service import execute_admin_command, is_admin_command


def try_handle_vk_admin_command(*, text: str, peer_id: str | int | None, external_user_id: str | int | None, storage: Any, vk_api: Any) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False

    if stripped == "/admin_id":
        vk_api.messages.send(
            peer_id=peer_id,
            random_id=0,
            message=f"ID для настройки админ-беседы:\npeer_id: {peer_id}\nuser_id: {external_user_id}",
        )
        return True

    if not is_admin_command(stripped):
        return False

    access = check_vk_admin(peer_id, external_user_id)
    if not access.allowed:
        vk_api.messages.send(peer_id=peer_id, random_id=0, message=access.reason)
        return True

    result = execute_admin_command(
        text=stripped,
        storage=storage,
        platform="vk",
        admin_user_id=external_user_id or "unknown",
    )
    if result.handled:
        vk_api.messages.send(peer_id=peer_id, random_id=0, message=result.text)
        return True

    return False
