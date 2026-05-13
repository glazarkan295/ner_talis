"""Runtime-подключение VK-админ-команд без переписывания всего vk_registration.py."""

from __future__ import annotations

from typing import Any, TypeVar

from handlers.vk_admin import normalize_vk_command_text, try_handle_vk_admin_command

T = TypeVar("T")


def patch_vk_registration_bot(base_class: type[T]) -> type[T]:
    """Возвращает наследника VkRegistrationBot с перехватом админ-команд.

    Так мы подключаем админ-команды к VK без большой замены файла
    handlers/vk_registration.py. Base.run() внутри всё равно вызывает
    self.handle_message(...), поэтому достаточно переопределить handle_message.
    """

    class VkAdminRegistrationBot(base_class):  # type: ignore[misc, valid-type]
        def handle_message(self, external_user_id: str, peer_id: int, text: str) -> None:
            if try_handle_vk_admin_command(
                text=text,
                peer_id=peer_id,
                external_user_id=external_user_id,
                storage=self.storage,
                vk_api=self.vk,
            ):
                return

            command_text = normalize_vk_command_text(text)
            return super().handle_message(external_user_id, peer_id, command_text)

    VkAdminRegistrationBot.__name__ = "VkAdminRegistrationBot"
    VkAdminRegistrationBot.__qualname__ = "VkAdminRegistrationBot"
    return VkAdminRegistrationBot
