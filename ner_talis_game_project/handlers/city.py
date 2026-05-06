import re

from telegram import Update
from telegram.ext import ContextTypes

from keyboards.reply_keyboards import make_keyboard, start_keyboard
from services.city_service import (
    CITY_BUTTONS,
    apply_city_transition,
    build_response_text,
    get_city_response,
)
from storage.base import PlayerStorage

TELEGRAM_PLATFORM = "telegram"
CITY_BUTTON_PATTERN = "^(" + "|".join(re.escape(button) for button in CITY_BUTTONS) + ")$"


def get_external_user_id(update: Update) -> str:
    return str(update.effective_user.id)


async def city_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_city_response(update, context, "В город")


async def city_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_city_response(update, context, update.message.text)


async def send_city_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: str,
) -> None:
    storage: PlayerStorage = context.bot_data["storage"]
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)

    if player is None:
        await update.message.reply_text(
            "Сначала нужно создать персонажа. Нажми /start и выбери «Начать».",
            reply_markup=start_keyboard(),
        )
        return

    response = get_city_response(action)
    player = apply_city_transition(storage, player, response)
    text = build_response_text(
        storage=storage,
        player=player,
        response=response,
        platform=TELEGRAM_PLATFORM,
    )

    await update.message.reply_text(
        text,
        reply_markup=make_keyboard(response.buttons),
        disable_web_page_preview=True,
    )
