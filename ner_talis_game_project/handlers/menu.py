"""Команды нижней Telegram-клавиатуры: /menu и /hide_menu (ТЗ 14).

- /menu — вернуть нижнюю игровую клавиатуру (ReplyKeyboardMarkup), сбросить флаг
  скрытого меню и показать текущую локацию.
- /hide_menu — полностью скрыть нижнюю клавиатуру (ReplyKeyboardRemove) и запомнить,
  что игрок сам её скрыл, чтобы бот не возвращал её самовольно.

Состояние скрытого меню хранится в ``context.user_data[MENU_HIDDEN_KEY]``.
/start сбрасывает его (см. registration.start_command).
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from keyboards.reply_keyboards import remove_keyboard, start_keyboard
from handlers.registration import (
    TELEGRAM_PLATFORM,
    get_external_user_id,
    get_storage,
)

MENU_HIDDEN_KEY = "telegram_menu_hidden"

MENU_OPENED_TEXT = "⌨️ Игровое меню открыто."
MENU_ALREADY_OPENED_TEXT = "⌨️ Игровое меню уже открыто."
MENU_HIDDEN_TEXT = "⌨️ Игровое меню скрыто.\n\nЧтобы вернуть его, отправьте /menu."
MENU_ALREADY_HIDDEN_TEXT = "⌨️ Игровое меню уже скрыто.\n\nЧтобы вернуть его, отправьте /menu."


def is_menu_hidden(context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        return bool(context.user_data.get(MENU_HIDDEN_KEY))
    except Exception:
        return False


def set_menu_hidden(context: ContextTypes.DEFAULT_TYPE, value: bool) -> None:
    try:
        if value:
            context.user_data[MENU_HIDDEN_KEY] = True
        else:
            context.user_data.pop(MENU_HIDDEN_KEY, None)
    except Exception:
        pass


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вернуть нижнюю игровую клавиатуру (ТЗ 14 §5.1)."""
    set_menu_hidden(context, False)
    storage = get_storage(context)
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)
    if player is None:
        await update.message.reply_text(MENU_OPENED_TEXT, reply_markup=start_keyboard())
        return
    # Зарегистрированному игроку возвращаем реальную клавиатуру его локации.
    from handlers.city import city_command

    await update.message.reply_text(MENU_OPENED_TEXT)
    await city_command(update, context)


async def hide_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Полностью скрыть нижнюю клавиатуру (ТЗ 14 §5.2)."""
    already = is_menu_hidden(context)
    set_menu_hidden(context, True)
    text = MENU_ALREADY_HIDDEN_TEXT if already else MENU_HIDDEN_TEXT
    await update.message.reply_text(text, reply_markup=remove_keyboard())
