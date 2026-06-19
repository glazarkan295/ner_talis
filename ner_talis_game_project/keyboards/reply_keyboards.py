from telegram import ReplyKeyboardMarkup

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


def make_keyboard(buttons: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


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
    return make_keyboard([
        ["Человек", "Эльф"],
        ["Дворф", "Нежить"],
        ["Ящеролюд"],
    ])


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
