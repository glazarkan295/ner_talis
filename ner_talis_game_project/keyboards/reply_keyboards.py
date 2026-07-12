import os

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

from services.city_service import (
    central_square_buttons,
    craft_buttons,
    dark_alleys_buttons,
    gates_buttons,
    pier_buttons,
    port_buttons,
    pavilion_buttons,
    tavern_buttons,
    trade_buttons,
    upper_buttons,
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().casefold() in {"1", "true", "yes", "on", "да"}


def make_keyboard(buttons: list[list[str]]) -> ReplyKeyboardMarkup:
    # ТЗ 14: по умолчанию НЕ persistent и НЕ one-time — Telegram сам показывает
    # стандартную кнопку сворачивания/разворачивания, а меню не навязчиво на
    # телефонах. Значения можно переопределить через ENV, не меняя код.
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=_env_bool("TG_REPLY_KEYBOARD_ONE_TIME", False),
        is_persistent=_env_bool("TG_REPLY_KEYBOARD_PERSISTENT", False),
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Полное удаление нижней reply-клавиатуры (команда /hide_menu, ТЗ 14 §5.2)."""
    return ReplyKeyboardRemove()


def consent_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard([
        ["Я прочитал и согласен"],
    ])


def start_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard([
        ["Кратко о мире"],
        ["Начать"],
    ])


def name_confirm_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard([
        ["Подтвердить"],
        ["Ввести заново"],
    ])


def gender_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard([
        ["Муж.", "Жен."],
    ])


def gender_confirm_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard([
        ["Да"],
        ["Нет"],
    ])


def race_keyboard() -> ReplyKeyboardMarkup:
    from services.registration_service import load_races
    rows=[]; names=[str(row.get("name") or rid) for rid,row in load_races(platform="telegram").items()]
    for index in range(0,len(names),2): rows.append(names[index:index+2])
    return make_keyboard(rows)


def race_card_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard([
        ["Выбрать"],
        ["Назад"],
    ])


def race_confirm_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard([
        ["Да"],
        ["Нет"],
    ])


def after_registration_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard([
        ["Профиль"],
        ["В город"],
    ])


def city_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(central_square_buttons())


def port_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(port_buttons())


def dark_alleys_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(dark_alleys_buttons())


def pier_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(pier_buttons())


def tavern_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(tavern_buttons())


def trade_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(trade_buttons())


def pavilion_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(pavilion_buttons())


def craft_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(craft_buttons())


def upper_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(upper_buttons())


def gates_keyboard() -> ReplyKeyboardMarkup:
    return make_keyboard(gates_buttons())
