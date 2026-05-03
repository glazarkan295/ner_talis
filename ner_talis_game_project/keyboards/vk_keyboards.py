from vk_api.keyboard import VkKeyboard, VkKeyboardColor

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

ButtonRows = list[list[str]]


def make_keyboard(buttons: ButtonRows) -> str:
    keyboard = VkKeyboard(one_time=False, inline=False)

    for row_index, row in enumerate(buttons):
        if row_index > 0:
            keyboard.add_line()

        for label in row:
            keyboard.add_button(label, color=VkKeyboardColor.PRIMARY)

    return keyboard.get_keyboard()


def start_keyboard() -> str:
    return make_keyboard([
        ["Кратко о мире"],
        ["Начать"],
    ])


def race_keyboard() -> str:
    return make_keyboard([
        ["Человек", "Эльф"],
        ["Дворф", "Нежить"],
        ["Ящеролюд"],
    ])


def race_card_keyboard() -> str:
    return make_keyboard([
        ["Выбрать"],
        ["Назад"],
    ])


def race_confirm_keyboard() -> str:
    return make_keyboard([
        ["Да"],
        ["Нет"],
    ])


def after_registration_keyboard() -> str:
    return make_keyboard([
        ["Профиль"],
        ["В город"],
    ])


def city_keyboard() -> str:
    return make_keyboard(central_square_buttons())


def port_keyboard() -> str:
    return make_keyboard(port_buttons())


def dark_alleys_keyboard() -> str:
    return make_keyboard(dark_alleys_buttons())


def pier_keyboard() -> str:
    return make_keyboard(pier_buttons())


def tavern_keyboard() -> str:
    return make_keyboard(tavern_buttons())


def trade_keyboard() -> str:
    return make_keyboard(trade_buttons())


def pavilion_keyboard() -> str:
    return make_keyboard(pavilion_buttons())


def craft_keyboard() -> str:
    return make_keyboard(craft_buttons())


def upper_keyboard() -> str:
    return make_keyboard(upper_buttons())


def gates_keyboard() -> str:
    return make_keyboard(gates_buttons())
