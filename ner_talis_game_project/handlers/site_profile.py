from telegram import Update
from telegram.ext import ContextTypes

from keyboards.reply_keyboards import after_registration_keyboard, start_keyboard
from services.web_profile import create_profile_site_link

TELEGRAM_PLATFORM = "telegram"


def get_external_user_id(update: Update) -> str:
    return str(update.effective_user.id)


async def profile_site_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = context.bot_data["storage"]
    external_user_id = get_external_user_id(update)
    player = storage.get_player_by_platform(TELEGRAM_PLATFORM, external_user_id)

    if player is None:
        await update.message.reply_text(
            "У тебя ещё нет персонажа. Нажми /start и выбери «Начать».",
            reply_markup=start_keyboard(),
        )
        return

    profile_url = create_profile_site_link(storage, player, TELEGRAM_PLATFORM)
    await update.message.reply_text(
        "🌐 Профиль на сайте готов.\n\n"
        f"Персонаж: {player['name']}\n"
        f"Единый игровой ID: {player['game_id']}\n"
        f"Открыть профиль: {profile_url}\n\n"
        "Ссылка временная и действует ограниченное время.",
        reply_markup=after_registration_keyboard(),
        disable_web_page_preview=True,
    )


async def profile_site_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await profile_site_command(update, context)
