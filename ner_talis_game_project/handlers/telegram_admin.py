"""Telegram-обработчики административных команд."""

from __future__ import annotations

from typing import Any

from services.admin_access import check_telegram_admin
from services.admin_command_service import execute_admin_command

ADMIN_COMMANDS = (
    "admin_help",
    "admin_promo_add",
    "admin_promo_bulk",
    "admin_promo_off",
    "admin_promo_list",
    "admin_reset_player",
    "admin_delete_player",
    "admin_add_item",
    "admin_add_item_json",
)


async def admin_id(update: Any, context: Any) -> None:
    message = getattr(update, "effective_message", None)
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    if message is None:
        return
    await message.reply_text(
        "ID для настройки админ-чата:\n"
        f"chat_id: {getattr(chat, 'id', None)}\n"
        f"user_id: {getattr(user, 'id', None)}"
    )


async def telegram_admin_command(update: Any, context: Any) -> None:
    message = getattr(update, "effective_message", None)
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    if message is None:
        return

    chat_id = getattr(chat, "id", None)
    user_id = getattr(user, "id", None)
    access = check_telegram_admin(chat_id, user_id)
    if not access.allowed:
        await message.reply_text(access.reason)
        return

    storage = context.application.bot_data.get("storage")
    result = execute_admin_command(
        text=getattr(message, "text", ""),
        storage=storage,
        platform="telegram",
        admin_user_id=user_id,
    )
    if result.handled:
        await message.reply_text(result.text)


def register_telegram_admin_handlers(application: Any, command_handler_class: Any) -> None:
    application.add_handler(command_handler_class("admin_id", admin_id))
    for command in ADMIN_COMMANDS:
        application.add_handler(command_handler_class(command, telegram_admin_command))
