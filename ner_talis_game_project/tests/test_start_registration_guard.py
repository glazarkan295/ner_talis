import asyncio
import sys
import tempfile
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

    telegram_stub.ReplyKeyboardMarkup = _ReplyKeyboardMarkup
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

    class _FakeKeyboard:
        def __init__(self, *args, **kwargs):
            self.buttons = []

        def add_line(self):
            self.buttons.append("line")

        def add_button(self, label, color=None):
            self.buttons.append(label)

        def get_keyboard(self):
            return "{}"

    keyboard_stub.VkKeyboard = _FakeKeyboard
    keyboard_stub.VkKeyboardColor = types.SimpleNamespace(PRIMARY="primary")
    sys.modules["vk_api"] = vk_api_stub
    sys.modules["vk_api.bot_longpoll"] = bot_longpoll_stub
    sys.modules["vk_api.utils"] = utils_stub
    sys.modules["vk_api.keyboard"] = keyboard_stub

from handlers.registration import TELEGRAM_PLATFORM, start_command
from handlers.vk_registration import VK_PLATFORM, STATE_AWAITING_RACE, VkRegistrationBot, VkRegistrationSession
from storage.json_storage import JsonStorage


class FakeStorage:
    def __init__(self, player=None):
        self.player = player
        self.calls = []

    def get_player_by_platform(self, platform, external_user_id):
        self.calls.append((platform, external_user_id))
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
        self.user_data = {"registration_name": "СтароеИмя"}


class StartRegistrationGuardTest(unittest.TestCase):
    def test_telegram_start_does_not_reopen_registration_for_registered_player(self):
        player = {"game_id": "NT-REGISTERED", "name": "Готовый"}
        storage = FakeStorage(player)
        update = FakeUpdate()
        context = FakeContext(storage)

        result = asyncio.run(start_command(update, context))

        self.assertEqual(result, -1)
        self.assertEqual(storage.calls, [(TELEGRAM_PLATFORM, "111")])
        self.assertEqual(context.user_data, {})
        self.assertTrue(update.message.replies)
        self.assertIn("уже зарегистрирован", update.message.replies[0][0].casefold())
        self.assertIn("повторно не запускает", update.message.replies[0][0].casefold())
        self.assertNotIn("Выберите действие", update.message.replies[0][0])
        self.assertIsNone(update.message.replies[0][1])

    def test_telegram_start_still_opens_registration_menu_for_new_player(self):
        storage = FakeStorage(None)
        update = FakeUpdate()
        context = FakeContext(storage)

        result = asyncio.run(start_command(update, context))

        self.assertNotEqual(result, -1)
        self.assertEqual(context.user_data, {})
        self.assertEqual(update.message.replies[0][0], "Выберите действие:")

    def test_vk_start_does_not_reset_session_for_registered_player(self):
        player = {"game_id": "NT-REGISTERED", "name": "Готовый"}
        bot = object.__new__(VkRegistrationBot)
        bot.storage = FakeStorage(player)
        bot.sessions = {f"{VK_PLATFORM}:222": VkRegistrationSession(state="awaiting_name", name="Черновик")}
        sent = []
        bot.send = lambda peer_id, text, keyboard=None: sent.append((peer_id, text, keyboard))

        bot.handle_message("222", 123, "/start")

        self.assertEqual(bot.sessions, {})
        self.assertEqual(bot.storage.calls[0], (VK_PLATFORM, "222"))
        self.assertTrue(sent)
        self.assertIn("уже зарегистрирован", sent[0][1].casefold())
        self.assertIn("повторно не запускает", sent[0][1].casefold())
        self.assertNotIn("Выберите действие", sent[0][1])
        self.assertIsNone(sent[0][2])


class VkRegistrationFullFlowTest(unittest.TestCase):
    def _make_bot(self):
        temp_dir = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(temp_dir.name) / "players.json"))
        bot = object.__new__(VkRegistrationBot)
        bot.storage = storage
        bot.sessions = {}
        sent = []
        bot.send = lambda peer_id, text, keyboard=None: sent.append((peer_id, text, keyboard))
        return temp_dir, storage, bot, sent

    def test_vk_registration_confirmation_buttons_are_not_captured_by_city_router(self):
        temp_dir, storage, bot, sent = self._make_bot()
        self.addCleanup(temp_dir.cleanup)

        for text in ["/start", "Начать", "Тестовый", "Человек", "Выбрать", "Да"]:
            bot.handle_message("333", 1001, text)

        player = storage.get_player_by_platform(VK_PLATFORM, "333")
        self.assertIsNotNone(player)
        self.assertEqual(player["name"], "Тестовый")
        self.assertEqual(player["race_name"], "Человек")
        self.assertNotIn(f"{VK_PLATFORM}:333", bot.sessions)
        self.assertTrue(sent)
        self.assertIn("добро пожаловать в город Селдар", sent[-1][1])
        self.assertFalse(any("Сначала нужно создать персонажа" in message for _peer, message, _keyboard in sent[-2:]))

    def test_vk_registration_back_button_stays_in_registration_flow(self):
        temp_dir, _storage, bot, sent = self._make_bot()
        self.addCleanup(temp_dir.cleanup)

        for text in ["/start", "Начать", "ИгрокНазад", "Эльф", "Назад"]:
            bot.handle_message("444", 1002, text)

        session = bot.sessions.get(f"{VK_PLATFORM}:444")
        self.assertIsNotNone(session)
        self.assertEqual(session.state, STATE_AWAITING_RACE)
        self.assertIn("Выбери расу", sent[-1][1])
        self.assertFalse(any("Сначала нужно создать персонажа" in message for _peer, message, _keyboard in sent[-2:]))


class TelegramRegistrationEntryPointGuardTest(unittest.TestCase):
    def test_telegram_start_menu_buttons_can_enter_conversation_after_lost_session(self):
        source = (ROOT_DIR / "main_telegram.py").read_text(encoding="utf-8")
        self.assertIn('MessageHandler(filters.Regex("^Начать$"), runtime["begin_registration"])', source)
        self.assertIn('MessageHandler(filters.Regex("^Кратко о мире$"), runtime["show_world_short"])', source)
        entry_block_start = source.index("registration_conversation = ConversationHandler(")
        city_handler_index = source.index('MessageHandler(filters.Regex(runtime["CITY_BUTTON_PATTERN"]), runtime["city_message"])')
        self.assertLess(entry_block_start, city_handler_index)


if __name__ == "__main__":
    unittest.main()
