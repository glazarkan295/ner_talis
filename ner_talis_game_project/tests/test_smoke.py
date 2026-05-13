import logging
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from unittest.mock import patch

from services.admin_access import check_telegram_admin
from services.admin_command_service import execute_admin_command
from services.city_service import apply_city_transition, get_city_response
from services.registration_service import create_player, load_races, validate_name
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage
from storage.storage_factory import normalize_backend, normalize_env_value


class FakeTelegramApplication:
    def __init__(self, events: list[str]):
        self.events = events

    def run_polling(self, allowed_updates=None):
        self.events.append("telegram_run_polling")


class FakeVkBot:
    def __init__(self, token: str, group_id: int, storage_path: str, events: list[str]):
        self.token = token
        self.group_id = group_id
        self.storage_path = storage_path
        self.events = events

    def run(self):
        self.events.append("vk_run")


class GameSmokeTest(unittest.TestCase):
    def test_name_validation(self):
        ok, name = validate_name("  Арден   Тир  ")
        self.assertTrue(ok)
        self.assertEqual(name, "Арден Тир")

        ok, message = validate_name("Админ")
        self.assertFalse(ok)
        self.assertIn("нельзя", message)

    def test_registration_link_and_city(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            races = load_races("data/races.json")

            game_id = storage.generate_game_id()
            player = create_player(
                game_id=game_id,
                platform="telegram",
                external_user_id="111",
                name="Арден",
                race_id="human",
                races=races,
            )
            storage.save_new_player(player, "telegram", "111")

            loaded = storage.get_player_by_platform("telegram", "111")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["game_id"], game_id)
            self.assertTrue(storage.is_name_taken("арден"))

            code = storage.create_link_code(game_id)
            ok, message, linked = storage.connect_platform_by_code(code, "vk", "222")
            self.assertTrue(ok, message)
            self.assertIsNotNone(linked)
            self.assertEqual(linked["game_id"], game_id)

            same = storage.get_player_by_platform("vk", "222")
            self.assertIsNotNone(same)
            self.assertEqual(same["game_id"], game_id)

            response = get_city_response("В город")
            updated = apply_city_transition(storage, same, response)
            self.assertEqual(updated["current_city"], "seldar")
            self.assertEqual(updated["current_zone"], "seldar_central_square")
            self.assertEqual(updated["energy"], 100)

    def test_sqlite_storage_persists_player_between_instances(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "players.sqlite3"
            races = load_races("data/races.json")

            storage = SQLiteStorage(str(db_path))
            game_id = storage.generate_game_id()
            player = create_player(
                game_id=game_id,
                platform="telegram",
                external_user_id="111",
                name="Селдарец",
                race_id="human",
                races=races,
            )
            storage.save_new_player(player, "telegram", "111")

            reopened_storage = SQLiteStorage(str(db_path))
            loaded = reopened_storage.get_player_by_platform("telegram", "111")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["game_id"], game_id)
            self.assertEqual(loaded["name"], "Селдарец")

    def test_admin_delete_player_command_supports_telegram_group_suffix_and_real_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            races = load_races("data/races.json")
            game_id = storage.generate_game_id()
            player = create_player(
                game_id=game_id,
                platform="telegram",
                external_user_id="111",
                name="Удаляемый",
                race_id="human",
                races=races,
            )
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(game_id, "profile", "telegram")
            self.assertIsNotNone(storage.get_player_by_platform("telegram", "111"))

            result = execute_admin_command(
                text=f"/admin_delete_player@NerTalisBot {game_id} CONFIRM_DELETE",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )

            self.assertTrue(result.handled)
            self.assertIn("удалён", result.text)
            self.assertIsNone(storage.get_player_by_game_id(game_id))
            self.assertIsNone(storage.get_player_by_platform("telegram", "111"))
            self.assertNotIn(token, storage.load().get("site_sessions", {}))
            self.assertFalse(storage.is_name_taken("Удаляемый"))

    def test_admin_delete_player_command_rejects_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            result = execute_admin_command(
                text="/admin_delete_player GAME_ID CONFIRM_DELETE",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertTrue(result.handled)
            self.assertIn("пример", result.text)

    def test_admin_delete_player_can_use_raw_unique_platform_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = SQLiteStorage(str(Path(tmp_dir) / "players.sqlite3"))
            races = load_races("data/races.json")
            game_id = storage.generate_game_id()
            player = create_player(
                game_id=game_id,
                platform="telegram",
                external_user_id="555",
                name="Стереть",
                race_id="human",
                races=races,
            )
            storage.save_new_player(player, "telegram", "555")

            result = execute_admin_command(
                text="/admin_delete_player 555 CONFIRM_DELETE",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )

            self.assertTrue(result.handled)
            self.assertIn("удалён", result.text)
            self.assertIsNone(storage.get_player_by_game_id(game_id))
            self.assertIsNone(storage.get_player_by_platform("telegram", "555"))

    def test_admin_access_allows_user_only_configuration(self):
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_USER_IDS": "999"}, clear=True):
            access = check_telegram_admin(chat_id=999, user_id=999)
            self.assertTrue(access.allowed, access.reason)

    def test_main_starts_both_bots(self):
        import main as combined_main

        events: list[str] = []

        def fake_build_application():
            return FakeTelegramApplication(events)

        def fake_vk_constructor(token: str, group_id: int, storage_path: str):
            return FakeVkBot(token, group_id, storage_path, events)

        def fake_start_vk_thread():
            combined_main.run_vk_bot()
            return None

        env = {
            "TELEGRAM_BOT_TOKEN": "telegram-test-token",
            "VK_GROUP_TOKEN": "vk-test-token",
            "VK_GROUP_ID": "123456",
            "PLAYERS_STORAGE_PATH": "data/players.json",
        }

        with patch.dict(os.environ, env, clear=False), \
             patch.object(combined_main, "load_project_env", lambda: None), \
             patch.object(combined_main, "build_application", fake_build_application), \
             patch.object(combined_main, "start_vk_thread", fake_start_vk_thread), \
             patch.object(combined_main, "VkRegistrationBot", fake_vk_constructor):
            combined_main.main()

        self.assertIn("vk_run", events)
        self.assertIn("telegram_run_polling", events)

    def test_main_requires_vk_settings_for_unified_start(self):
        import main as combined_main

        env = {
            "TELEGRAM_BOT_TOKEN": "telegram-test-token",
            "PLAYERS_STORAGE_PATH": "data/players.json",
        }

        with patch.dict(os.environ, env, clear=True), \
             patch.object(combined_main, "load_project_env", lambda: None):
            with self.assertRaises(RuntimeError) as context:
                combined_main.main()

        self.assertIn("VK_GROUP_TOKEN", str(context.exception))

    def test_vk_thread_does_not_start_if_telegram_build_fails(self):
        import main as combined_main

        env = {
            "TELEGRAM_BOT_TOKEN": "telegram-test-token",
            "VK_GROUP_TOKEN": "vk-test-token",
            "VK_GROUP_ID": "123456",
            "PLAYERS_STORAGE_PATH": "data/players.json",
        }

        def fail_build_application():
            raise RuntimeError("telegram build failed")

        def fail_if_vk_thread_starts():
            raise AssertionError("VK thread should not start before Telegram is built")

        with patch.dict(os.environ, env, clear=False), \
             patch.object(combined_main, "load_project_env", lambda: None), \
             patch.object(combined_main, "build_application", fail_build_application), \
             patch.object(combined_main, "start_vk_thread", fail_if_vk_thread_starts):
            with self.assertRaises(RuntimeError) as context:
                combined_main.main()

        self.assertIn("telegram build failed", str(context.exception))

    def test_env_values_with_names_are_normalized(self):
        import main as combined_main

        env = {
            "TELEGRAM_BOT_TOKEN": "TELEGRAM_BOT_TOKEN=telegram-test-token",
            "VK_GROUP_ID": "VK_GROUP_ID=123456",
        }

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                combined_main.require_env("TELEGRAM_BOT_TOKEN"),
                "telegram-test-token",
            )
            self.assertEqual(combined_main.require_int_env("VK_GROUP_ID"), 123456)
            self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "telegram-test-token")
            self.assertEqual(os.environ["VK_GROUP_ID"], "123456")

    def test_storage_backend_is_normalized(self):
        self.assertEqual(normalize_backend(None), "sqlite")
        self.assertEqual(normalize_backend(" 'JSON' "), "json")
        self.assertEqual(normalize_backend("STORAGE_BACKEND=sqlite"), "sqlite")
        self.assertEqual(
            normalize_env_value("SQLITE_STORAGE_PATH", "SQLITE_STORAGE_PATH=data/db.sqlite3"),
            "data/db.sqlite3",
        )

        with self.assertRaises(RuntimeError):
            normalize_backend("postgres")

    def test_telegram_timeout_env_values_are_normalized(self):
        import main_telegram

        env = {
            "TELEGRAM_GET_UPDATES_READ_TIMEOUT": "TELEGRAM_GET_UPDATES_READ_TIMEOUT=75",
            "TELEGRAM_BOOTSTRAP_RETRIES": "-1",
        }

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                main_telegram.get_float_env("TELEGRAM_GET_UPDATES_READ_TIMEOUT", 60.0),
                75.0,
            )
            self.assertEqual(main_telegram.get_int_env("TELEGRAM_BOOTSTRAP_RETRIES", 0), -1)

        with patch.dict(os.environ, {"TELEGRAM_POLL_TIMEOUT": "bad"}, clear=True):
            with self.assertRaises(RuntimeError):
                main_telegram.get_int_env("TELEGRAM_POLL_TIMEOUT", 30)

    def test_sensitive_values_are_redacted(self):
        import main as combined_main

        env = {
            "TELEGRAM_BOT_TOKEN": "123456:secret-token-value",
        }
        text = (
            "telegram.error.InvalidToken: "
            "The token `TELEGRAM_BOT_TOKEN=123456:secret-token-value` was rejected. "
            "POST https://api.telegram.org/bot123456:secret-token-value/getUpdates"
        )

        with patch.dict(os.environ, env, clear=True):
            redacted = combined_main.redact_sensitive_text(text)

        self.assertNotIn("secret-token-value", redacted)
        self.assertIn("<REDACTED>", redacted)

    def test_sensitive_values_are_redacted_from_exception_logs(self):
        import main as combined_main

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(combined_main.RedactingFormatter("%(message)s"))

        test_logger = logging.getLogger("ner_talis_redaction_test")
        original_handlers = list(test_logger.handlers)
        original_propagate = test_logger.propagate
        test_logger.handlers = [handler]
        test_logger.propagate = False

        try:
            with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:secret-token-value"}, clear=True):
                try:
                    raise RuntimeError("The token `123456:secret-token-value` was rejected")
                except RuntimeError:
                    test_logger.exception("Application crashed")

            logs = log_stream.getvalue()
            self.assertNotIn("secret-token-value", logs)
            self.assertIn("<REDACTED>", logs)
        finally:
            test_logger.handlers = original_handlers
            test_logger.propagate = original_propagate


if __name__ == "__main__":
    unittest.main()
