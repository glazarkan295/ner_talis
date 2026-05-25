import asyncio
import logging
import re
from telegram import Update
from telegram.ext import ContextTypes

from keyboards.reply_keyboards import make_keyboard, start_keyboard
from services.city_service import CITY_BUTTONS, process_world_action
from services.external_location_service import complete_active_timer
from services.runtime_timer_scheduler import attach_timer_notification, schedule_timer_delivery
from storage.base import PlayerStorage

TELEGRAM_PLATFORM = "telegram"
CITY_BUTTON_PATTERN = r"^.+$"
logger = logging.getLogger(__name__)


def schedule_telegram_timer(context: ContextTypes.DEFAULT_TYPE, chat_id: int, timer_data: dict | None) -> None:
    if not timer_data:
        return
    storage: PlayerStorage = context.bot_data["storage"]
    seconds = max(0.05, float(timer_data.get("seconds") or 0.05))
    game_id = timer_data.get("game_id")
    timer_id = timer_data.get("timer_id")
    if not game_id or not timer_id:
        return

    attach_timer_notification(
        storage=storage,
        game_id=str(game_id),
        timer_id=str(timer_id),
        platform=TELEGRAM_PLATFORM,
        target_id=str(chat_id),
    )

    loop = asyncio.get_running_loop()

    def send_timer_result(_platform: str, target_id: str, response) -> None:
        future = asyncio.run_coroutine_threadsafe(
            context.bot.send_message(
                chat_id=int(target_id),
                text=response.text,
                reply_markup=make_keyboard(response.buttons),
                disable_web_page_preview=True,
            ),
            loop,
        )
        try:
            future.result(timeout=30)
        except Exception:
            logger.exception("Failed to send Telegram timer result to chat_id=%s", target_id)

    schedule_timer_delivery(
        storage=storage,
        game_id=str(game_id),
        timer_id=str(timer_id),
        seconds=seconds,
        send_callback=send_timer_result,
        platform_filter=TELEGRAM_PLATFORM,
    )


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

    result = process_world_action(
        storage=storage,
        player=player,
        action=action,
        platform=TELEGRAM_PLATFORM,
    )

    for message in getattr(result, "extra_messages", ()):
        await update.message.reply_text(
            message,
            disable_web_page_preview=True,
        )

    await update.message.reply_text(
        result.text,
        reply_markup=make_keyboard(result.buttons),
        disable_web_page_preview=True,
    )
    schedule_telegram_timer(context, update.effective_chat.id, result.scheduled_timer)
