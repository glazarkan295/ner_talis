"""ТЗ 14: нижняя Telegram-клавиатура — /menu, /hide_menu, параметры, состояние."""

import asyncio
import os
import sys
import types
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if "telegram" not in sys.modules:
    telegram_stub = types.ModuleType("telegram")

    class _ReplyKeyboardMarkup:
        def __init__(self, keyboard, **kwargs):
            self.keyboard = keyboard
            self.kwargs = kwargs

    class _ReplyKeyboardRemove:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    telegram_stub.ReplyKeyboardMarkup = _ReplyKeyboardMarkup
    telegram_stub.ReplyKeyboardRemove = _ReplyKeyboardRemove
    telegram_stub.Update = object
    sys.modules["telegram"] = telegram_stub

if "telegram.ext" not in sys.modules:
    telegram_ext_stub = types.ModuleType("telegram.ext")
    telegram_ext_stub.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
    telegram_ext_stub.ConversationHandler = types.SimpleNamespace(END=-1)
    sys.modules["telegram.ext"] = telegram_ext_stub

if "vk_api" not in sys.modules:
    vk_api_stub = types.ModuleType("vk_api")
    vk_api_stub.VkApi = lambda *args, **kwargs: None
    bot_longpoll_stub = types.ModuleType("vk_api.bot_longpoll")
    bot_longpoll_stub.VkBotEventType = types.SimpleNamespace(MESSAGE_NEW="message_new")
    bot_longpoll_stub.VkBotLongPoll = lambda *args, **kwargs: None
    utils_stub = types.ModuleType("vk_api.utils")
    utils_stub.get_random_id = lambda: 1
    keyboard_stub = types.ModuleType("vk_api.keyboard")
    keyboard_stub.VkKeyboard = object
    keyboard_stub.VkKeyboardColor = types.SimpleNamespace(PRIMARY="primary")
    sys.modules["vk_api"] = vk_api_stub
    sys.modules["vk_api.bot_longpoll"] = bot_longpoll_stub
    sys.modules["vk_api.utils"] = utils_stub
    sys.modules["vk_api.keyboard"] = keyboard_stub

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove  # noqa: E402
from keyboards.reply_keyboards import make_keyboard, remove_keyboard  # noqa: E402
from handlers.menu import (  # noqa: E402
    hide_menu_command,
    is_menu_hidden,
    menu_command,
    set_menu_hidden,
)


class FakeStorage:
    def __init__(self, player=None):
        self.player = player

    def get_player_by_platform(self, platform, external_user_id):
        return self.player


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, reply_markup=None, **kwargs):
        self.replies.append((text, reply_markup, kwargs))


class FakeUser:
    id = 111


class FakeUpdate:
    def __init__(self):
        self.effective_user = FakeUser()
        self.message = FakeMessage()


class FakeContext:
    def __init__(self, storage):
        self.bot_data = {"storage": storage}
        self.user_data = {}


class KeyboardParamsTest(unittest.TestCase):
    def tearDown(self):
        for k in ("TG_REPLY_KEYBOARD_PERSISTENT", "TG_REPLY_KEYBOARD_ONE_TIME"):
            os.environ.pop(k, None)

    def test_defaults_not_persistent_not_one_time(self):
        kb = make_keyboard([["A"]])
        self.assertIsInstance(kb, ReplyKeyboardMarkup)
        self.assertFalse(kb.kwargs.get("is_persistent"))
        self.assertFalse(kb.kwargs.get("one_time_keyboard"))
        self.assertTrue(kb.kwargs.get("resize_keyboard"))

    def test_env_override_persistent(self):
        os.environ["TG_REPLY_KEYBOARD_PERSISTENT"] = "true"
        self.assertTrue(make_keyboard([["A"]]).kwargs.get("is_persistent"))

    def test_remove_keyboard_type(self):
        self.assertIsInstance(remove_keyboard(), ReplyKeyboardRemove)


class MenuCommandTest(unittest.TestCase):
    def test_hide_menu_removes_keyboard_and_sets_flag(self):
        update, context = FakeUpdate(), FakeContext(FakeStorage())
        asyncio.run(hide_menu_command(update, context))
        text, markup, _ = update.message.replies[-1]
        self.assertIsInstance(markup, ReplyKeyboardRemove)
        self.assertIn("скрыто", text.lower())
        self.assertTrue(is_menu_hidden(context))

    def test_hide_menu_twice_says_already(self):
        update, context = FakeUpdate(), FakeContext(FakeStorage())
        asyncio.run(hide_menu_command(update, context))
        asyncio.run(hide_menu_command(update, context))
        self.assertIn("уже скрыто", update.message.replies[-1][0].lower())

    def test_menu_returns_keyboard_and_clears_flag(self):
        # Незарегистрированный игрок → стартовая клавиатура (ReplyKeyboardMarkup).
        update, context = FakeUpdate(), FakeContext(FakeStorage(player=None))
        set_menu_hidden(context, True)
        asyncio.run(menu_command(update, context))
        text, markup, _ = update.message.replies[-1]
        self.assertIsInstance(markup, ReplyKeyboardMarkup)
        self.assertIn("открыто", text.lower())
        self.assertFalse(is_menu_hidden(context))

    def test_state_helpers(self):
        context = FakeContext(FakeStorage())
        self.assertFalse(is_menu_hidden(context))
        set_menu_hidden(context, True)
        self.assertTrue(is_menu_hidden(context))
        set_menu_hidden(context, False)
        self.assertFalse(is_menu_hidden(context))


if __name__ == "__main__":
    unittest.main()
