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

from handlers.registration import (
    AWAITING_GENDER,
    AWAITING_NAME,
    AWAITING_RACE,
    CONSENT_GATE,
    GENDER_CONFIRM,
    NAME_CONFIRM,
    START_MENU,
    TELEGRAM_PLATFORM,
    accept_consent,
    connect_command,
    handle_gender_confirmation,
    handle_name_confirmation,
    handle_race_confirmation,
    link_command,
    profile_command,
    promo_command,
    receive_gender,
    receive_name,
    start_command,
)
from handlers.vk_registration import (
    CONSENT_BUTTON,
    STATE_AWAITING_NAME,
    STATE_AWAITING_RACE,
    STATE_CONSENT,
    STATE_START_MENU,
    VK_PLATFORM,
    VkRegistrationBot,
    VkRegistrationSession,
)
from services.registration_service import create_player, load_races
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

    def test_telegram_start_shows_consent_before_menu_for_new_player(self):
        storage = FakeStorage(None)
        update = FakeUpdate()
        context = FakeContext(storage)

        result = asyncio.run(start_command(update, context))

        self.assertEqual(result, CONSENT_GATE)
        self.assertEqual(context.user_data, {})
        self.assertIn("ознакомьтесь", update.message.replies[0][0].casefold())
        self.assertEqual(
            update.message.replies[0][1].keyboard,
            [["Я прочитал и согласен"]],
        )

    def test_telegram_accept_consent_opens_registration_menu(self):
        storage = FakeStorage(None)
        update = FakeUpdate()
        context = FakeContext(storage)

        result = asyncio.run(accept_consent(update, context))

        self.assertEqual(result, START_MENU)
        self.assertEqual(update.message.replies[-1][0], "Спасибо! Выберите действие:")
        self.assertEqual(
            update.message.replies[-1][1].keyboard,
            [["Кратко о мире"], ["Начать"]],
        )

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

        for text in ["/start", CONSENT_BUTTON, "Начать", "Тестовый", "Подтвердить", "Муж.", "Да", "Человек", "Выбрать", "Да"]:
            bot.handle_message("333", 1001, text)

        player = storage.get_player_by_platform(VK_PLATFORM, "333")
        self.assertIsNotNone(player)
        self.assertEqual(player["name"], "Тестовый")
        self.assertEqual(player["gender"], "male")
        self.assertEqual(player["gender_label"], "Муж.")
        self.assertEqual(player["race_name"], "Человек")
        self.assertNotIn(f"{VK_PLATFORM}:333", bot.sessions)
        self.assertTrue(sent)
        self.assertIn("добро пожаловать в город Селдар", sent[-1][1])
        self.assertFalse(any("Сначала нужно создать персонажа" in message for _peer, message, _keyboard in sent[-2:]))

    def test_vk_registration_back_button_stays_in_registration_flow(self):
        temp_dir, _storage, bot, sent = self._make_bot()
        self.addCleanup(temp_dir.cleanup)

        for text in ["/start", CONSENT_BUTTON, "Начать", "ИгрокНазад", "Подтвердить", "Жен.", "Да", "Эльф", "Назад"]:
            bot.handle_message("444", 1002, text)

        session = bot.sessions.get(f"{VK_PLATFORM}:444")
        self.assertIsNotNone(session)
        self.assertEqual(session.state, STATE_AWAITING_RACE)
        self.assertIn("Выбери расу", sent[-1][1])
        self.assertFalse(any("Сначала нужно создать персонажа" in message for _peer, message, _keyboard in sent[-2:]))

    def test_vk_registration_can_reenter_name_before_gender_choice(self):
        temp_dir, _storage, bot, sent = self._make_bot()
        self.addCleanup(temp_dir.cleanup)

        for text in ["/start", CONSENT_BUTTON, "Начать", "ПервоеИмя", "Ввести заново"]:
            bot.handle_message("445", 1004, text)

        session = bot.sessions.get(f"{VK_PLATFORM}:445")
        self.assertIsNotNone(session)
        self.assertEqual(session.state, STATE_AWAITING_NAME)
        self.assertIsNone(session.name)
        self.assertIsNone(session.pending_name)
        self.assertIn("Назовите своё имя", sent[-1][1])

    def test_vk_first_contact_shows_consent_before_registration(self):
        temp_dir, _storage, bot, sent = self._make_bot()
        self.addCleanup(temp_dir.cleanup)

        # Первый контакт через кнопку запуска VK «Начать» не должен сразу
        # открывать регистрацию — сначала обязательно согласие.
        bot.handle_message("446", 1005, "Начать")

        session = bot.sessions.get(f"{VK_PLATFORM}:446")
        self.assertIsNotNone(session)
        self.assertEqual(session.state, STATE_CONSENT)
        self.assertIn("ознакомьтесь", sent[-1][1].casefold())
        self.assertNotIn("Назовите своё имя", sent[-1][1])

    def test_vk_consent_button_opens_start_menu(self):
        temp_dir, _storage, bot, sent = self._make_bot()
        self.addCleanup(temp_dir.cleanup)

        bot.handle_message("447", 1006, "Начать")
        bot.handle_message("447", 1006, CONSENT_BUTTON)

        session = bot.sessions.get(f"{VK_PLATFORM}:447")
        self.assertIsNotNone(session)
        self.assertEqual(session.state, STATE_START_MENU)
        self.assertIn("Выберите действие", sent[-1][1])


class FakeContextWithArgs(FakeContext):
    def __init__(self, storage, args=None, user_data=None):
        super().__init__(storage)
        self.args = list(args or [])
        if user_data is not None:
            self.user_data = dict(user_data)


def create_saved_player(storage, platform, external_user_id, name="Связной"):
    races = load_races("data/races.json")
    player = create_player(
        game_id=storage.generate_game_id(),
        platform=platform,
        external_user_id=external_user_id,
        name=name,
        race_id="human",
        races=races,
    )
    storage.save_new_player(player, platform, external_user_id)
    return player


class TelegramRegistrationNameGenderFlowTest(unittest.TestCase):
    def _make_storage(self):
        temp_dir = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(temp_dir.name) / "players.json"))
        self.addCleanup(temp_dir.cleanup)
        return storage

    def test_telegram_name_requires_confirmation_before_gender(self):
        storage = self._make_storage()
        update = FakeUpdate()
        update.message.text = "НовыйИгрок"
        context = FakeContextWithArgs(storage, user_data={})

        result = asyncio.run(receive_name(update, context))

        self.assertEqual(result, NAME_CONFIRM)
        self.assertEqual(context.user_data["registration_pending_name"], "НовыйИгрок")
        self.assertIn("НовыйИгрок", update.message.replies[-1][0])
        self.assertEqual(update.message.replies[-1][1].keyboard, [["Подтвердить"], ["Ввести заново"]])

    def test_telegram_can_reenter_name_from_confirmation(self):
        storage = self._make_storage()
        update = FakeUpdate()
        update.message.text = "Ввести заново"
        context = FakeContextWithArgs(storage, user_data={"registration_pending_name": "СтарыйНик"})

        result = asyncio.run(handle_name_confirmation(update, context))

        self.assertEqual(result, AWAITING_NAME)
        self.assertEqual(context.user_data, {})
        self.assertIn("Назовите своё имя", update.message.replies[-1][0])

    def test_telegram_gender_choice_has_confirmation_and_can_return_to_choice(self):
        storage = self._make_storage()
        update = FakeUpdate()
        context = FakeContextWithArgs(storage, user_data={"registration_pending_name": "ИгрокПол"})

        update.message.text = "Подтвердить"
        result = asyncio.run(handle_name_confirmation(update, context))

        self.assertEqual(result, AWAITING_GENDER)
        self.assertEqual(context.user_data["registration_name"], "ИгрокПол")
        self.assertIn("Какого вы пола", update.message.replies[-2][0])
        self.assertIn("Внимание", update.message.replies[-1][0])
        self.assertEqual(update.message.replies[-1][1].keyboard, [["Муж.", "Жен."]])

        update.message.text = "Жен."
        result = asyncio.run(receive_gender(update, context))
        self.assertEqual(result, GENDER_CONFIRM)
        self.assertIn("Вы уверены", update.message.replies[-1][0])

        update.message.text = "Нет"
        result = asyncio.run(handle_gender_confirmation(update, context))
        self.assertEqual(result, AWAITING_GENDER)
        self.assertNotIn("registration_gender", context.user_data)
        self.assertIn("Какого вы пола", update.message.replies[-1][0])

        update.message.text = "Муж."
        result = asyncio.run(receive_gender(update, context))
        self.assertEqual(result, GENDER_CONFIRM)

        update.message.text = "Да"
        result = asyncio.run(handle_gender_confirmation(update, context))
        self.assertEqual(result, AWAITING_RACE)
        self.assertEqual(context.user_data["registration_gender"], "male")
        self.assertEqual(context.user_data["registration_gender_label"], "Муж.")
        self.assertIn("ваша раса", update.message.replies[-1][0])

    def test_telegram_final_registration_saves_gender(self):
        storage = self._make_storage()
        update = FakeUpdate()
        update.message.text = "Да"
        context = FakeContextWithArgs(
            storage,
            user_data={
                "registration_name": "ГендерТест",
                "registration_gender": "female",
                "registration_gender_label": "Жен.",
                "registration_race_id": "human",
            },
        )

        result = asyncio.run(handle_race_confirmation(update, context))

        self.assertEqual(result, -1)
        player = storage.get_player_by_platform(TELEGRAM_PLATFORM, str(update.effective_user.id))
        self.assertIsNotNone(player)
        self.assertEqual(player["gender"], "female")
        self.assertEqual(player["gender_label"], "Жен.")


class TelegramRegistrationFallbackCleanupTest(unittest.TestCase):
    def _make_storage(self):
        temp_dir = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(temp_dir.name) / "players.json"))
        self.addCleanup(temp_dir.cleanup)
        return storage

    def test_telegram_connect_success_ends_stale_registration_conversation(self):
        storage = self._make_storage()
        source_player = create_saved_player(storage, VK_PLATFORM, "vk-source")
        code = storage.create_link_code(source_player["game_id"])
        update = FakeUpdate()
        context = FakeContextWithArgs(
            storage,
            args=[code],
            user_data={"registration_name": "Черновик", "registration_race_id": "human"},
        )

        result = asyncio.run(connect_command(update, context))

        self.assertEqual(result, -1)
        self.assertEqual(context.user_data, {})
        linked = storage.get_player_by_platform(TELEGRAM_PLATFORM, str(update.effective_user.id))
        self.assertIsNotNone(linked)
        self.assertEqual(linked["game_id"], source_player["game_id"])
        self.assertIn("Платформа успешно привязана", update.message.replies[-1][0])

    def test_telegram_profile_command_ends_stale_registration_for_registered_player(self):
        storage = self._make_storage()
        create_saved_player(storage, TELEGRAM_PLATFORM, "111")
        update = FakeUpdate()
        context = FakeContextWithArgs(storage, user_data={"registration_name": "Черновик"})

        result = asyncio.run(profile_command(update, context))

        self.assertEqual(result, -1)
        self.assertEqual(context.user_data, {})
        self.assertIn("Временная ссылка", update.message.replies[-1][0])

    def test_telegram_link_command_ends_stale_registration_for_registered_player(self):
        storage = self._make_storage()
        create_saved_player(storage, TELEGRAM_PLATFORM, "111")
        update = FakeUpdate()
        context = FakeContextWithArgs(storage, user_data={"registration_name": "Черновик"})

        result = asyncio.run(link_command(update, context))

        self.assertEqual(result, -1)
        self.assertEqual(context.user_data, {})
        self.assertIn("Код привязки создан", update.message.replies[-1][0])

    def test_telegram_promo_command_ends_stale_registration_for_registered_player(self):
        storage = self._make_storage()
        create_saved_player(storage, TELEGRAM_PLATFORM, "111")
        update = FakeUpdate()
        context = FakeContextWithArgs(storage, args=["UNKNOWN_PROMO"], user_data={"registration_name": "Черновик"})

        result = asyncio.run(promo_command(update, context))

        self.assertEqual(result, -1)
        self.assertEqual(context.user_data, {})
        self.assertTrue(update.message.replies[-1][0].startswith("⚠️"))


class VkRegistrationConnectCleanupTest(unittest.TestCase):
    def test_vk_connect_success_clears_stale_registration_session_immediately(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        storage = JsonStorage(str(Path(temp_dir.name) / "players.json"))
        source_player = create_saved_player(storage, TELEGRAM_PLATFORM, "tg-source")
        code = storage.create_link_code(source_player["game_id"])
        bot = object.__new__(VkRegistrationBot)
        bot.storage = storage
        bot.sessions = {f"{VK_PLATFORM}:999": VkRegistrationSession(state="awaiting_name", name="Черновик")}
        sent = []
        bot.send = lambda peer_id, text, keyboard=None: sent.append((peer_id, text, keyboard))

        bot.handle_message("999", 1003, f"/connect {code}")

        self.assertNotIn(f"{VK_PLATFORM}:999", bot.sessions)
        linked = storage.get_player_by_platform(VK_PLATFORM, "999")
        self.assertIsNotNone(linked)
        self.assertEqual(linked["game_id"], source_player["game_id"])
        self.assertIn("Платформа успешно привязана", sent[-1][1])


class VkRegisteredPlayerCityRoutingTest(unittest.TestCase):
    def _make_bot_with_player(self, external_user_id="777"):
        temp_dir = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(temp_dir.name) / "players.json"))
        player = create_saved_player(storage, VK_PLATFORM, external_user_id, name="Городской")
        bot = object.__new__(VkRegistrationBot)
        bot.storage = storage
        bot.sessions = {}
        sent = []
        bot.send = lambda peer_id, text, keyboard=None: sent.append((peer_id, text, keyboard))
        bot.schedule_timer_notification = lambda peer_id, timer_data: None
        self.addCleanup(temp_dir.cleanup)
        return storage, player, bot, sent

    def test_vk_registered_player_free_text_stays_in_city_router(self):
        storage, player, bot, sent = self._make_bot_with_player("777")

        bot.handle_message("777", 2001, "случайный текст")

        self.assertTrue(sent)
        self.assertIn("Неизвестное городское действие", sent[-1][1])
        self.assertNotIn("Нажми /start", sent[-1][1])
        updated = storage.get_player_by_game_id(player["game_id"])
        self.assertEqual(updated.get("current_zone"), "seldar_central_square")

    def test_vk_registered_player_free_text_stays_at_outside_crossroads(self):
        storage, player, bot, sent = self._make_bot_with_player("778")
        player["current_city"] = "outside_seldar"
        player["current_zone"] = "outside_city_crossroads"
        player["location_id"] = "outside_city_crossroads"
        player["current_location"] = "outside_city_crossroads"
        storage.update_player(player)

        bot.handle_message("778", 2002, "случайный текст")

        self.assertTrue(sent)
        self.assertIn("Неизвестное действие внешней локации", sent[-1][1])
        self.assertNotIn("Нажми /start", sent[-1][1])
        updated = storage.get_player_by_game_id(player["game_id"])
        self.assertEqual(updated.get("current_city"), "outside_seldar")
        self.assertEqual(updated.get("current_zone"), "outside_city_crossroads")


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
