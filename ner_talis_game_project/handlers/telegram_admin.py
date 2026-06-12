"""Telegram-обработчики административных команд."""

from __future__ import annotations

from typing import Any

from services.admin_access import check_telegram_admin, telegram_admin_chat_ids
from services.admin_command_service import execute_admin_command

ADMIN_COMMANDS = (
    "admin_help",
    "admin_panel",
    "admin_promo_add",
    "admin_promo_bulk",
    "admin_promo_off",
    "admin_promo_list",
    "admin_find_player",
    "admin_player_info",
    "admin_add_money",
    "admin_add_experience",
    "admin_add_exp",
    "admin_add_stat_points",
    "admin_add_attribute_points",
    "admin_add_skill_points",
    "admin_kick_profile_sessions",
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


async def telegram_admin_chat_guard(update: Any, context: Any) -> None:
    """Глушит обычные команды/кнопки в админ-чате.

    В админ-чате не должен запускаться игровой роутер и не должны показываться
    обычные игровые клавиатуры. Разрешены только /admin_id, /admin_help и
    /admin_panel через специальные CommandHandler выше.
    """
    message = getattr(update, "effective_message", None)
    chat = getattr(update, "effective_chat", None)
    if message is None or chat is None:
        return
    # The handler is registered only for configured admin chat ids, so an empty
    # return here intentionally consumes the update and prevents regular game
    # handlers from running in the admin chat.
    return


def register_telegram_admin_handlers(application: Any, command_handler_class: Any, message_handler_class: Any | None = None, filters_module: Any | None = None) -> None:
    application.add_handler(command_handler_class("admin_id", admin_id))
    for command in ADMIN_COMMANDS:
        application.add_handler(command_handler_class(command, telegram_admin_command))
    if message_handler_class is not None and filters_module is not None:
        chat_ids: list[int] = []
        for raw_chat_id in telegram_admin_chat_ids():
            try:
                chat_ids.append(int(raw_chat_id))
            except (TypeError, ValueError):
                continue
        if chat_ids:
            application.add_handler(message_handler_class(filters_module.Chat(chat_ids), telegram_admin_chat_guard))
