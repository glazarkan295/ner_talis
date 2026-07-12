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
VK_MAX_ROWS = 10
VK_MAX_BUTTONS_PER_ROW = 4
VK_MAX_BUTTONS = VK_MAX_ROWS * VK_MAX_BUTTONS_PER_ROW


def _fit_vk_button_rows(buttons: ButtonRows) -> ButtonRows:
    """Fit arbitrary game keyboards into VK reply-keyboard limits.

    Telegram can display long one-column lists, but VK rejects keyboards with
    too many lines. Market buy/sell lists are the most visible case: the
    shared service returns one item per row, so VK users could press
    ``Купить``/``Продать`` and then fail to receive the list keyboard.
    """
    cleaned: list[list[str]] = []
    for row in buttons or []:
        labels = [str(label).strip() for label in row if str(label).strip()]
        if labels:
            cleaned.append(labels[:VK_MAX_BUTTONS_PER_ROW])

    if len(cleaned) <= VK_MAX_ROWS and all(len(row) <= VK_MAX_BUTTONS_PER_ROW for row in cleaned):
        return cleaned

    flattened = [label for row in cleaned for label in row]
    if len(flattened) > VK_MAX_BUTTONS:
        # Keep navigation actions visible when truncation is unavoidable.
        priority_labels = {
            "Назад",
            "Назад на рынок",
            "В город",
            "Вернуться в город",
            "Вернуться к воротам",
            "Торговый квартал",
            "Сбежать",
            "Подсумок",
            "Подсумок далее",
            "Подсумок назад",
            "Профиль",
            "Свернуть лагерь",
            "⬅️ В лагерь",
            "Готовка",
            "Еда",
        }
        priority_tail = []
        seen_priority = set()
        for label in flattened:
            if label in priority_labels and label not in seen_priority:
                priority_tail.append(label)
                seen_priority.add(label)
        head_limit = max(0, VK_MAX_BUTTONS - len(priority_tail))
        flattened = flattened[:head_limit] + priority_tail[:VK_MAX_BUTTONS - head_limit]

    return [
        flattened[index:index + VK_MAX_BUTTONS_PER_ROW]
        for index in range(0, len(flattened), VK_MAX_BUTTONS_PER_ROW)
    ][:VK_MAX_ROWS]


def make_keyboard(buttons: ButtonRows) -> str:
    keyboard = VkKeyboard(one_time=False, inline=False)

    for row_index, row in enumerate(_fit_vk_button_rows(buttons)):
        if row_index > 0:
            keyboard.add_line()

        for label in row:
            keyboard.add_button(label, color=VkKeyboardColor.PRIMARY)

    return keyboard.get_keyboard()


def consent_keyboard() -> str:
    return make_keyboard([
        ["Я прочитал и согласен"],
    ])


def start_keyboard() -> str:
    return make_keyboard([
        ["Кратко о мире"],
        ["Начать"],
    ])


def name_confirm_keyboard() -> str:
    return make_keyboard([
        ["Подтвердить"],
        ["Ввести заново"],
    ])


def gender_keyboard() -> str:
    return make_keyboard([
        ["Муж.", "Жен."],
    ])


def gender_confirm_keyboard() -> str:
    return make_keyboard([
        ["Да"],
        ["Нет"],
    ])


def race_keyboard() -> str:
    from services.registration_service import load_races
    rows=[]; names=[str(row.get("name") or rid) for rid,row in load_races(platform="vk").items()]
    for index in range(0,len(names),2): rows.append(names[index:index+2])
    return make_keyboard(rows)


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
