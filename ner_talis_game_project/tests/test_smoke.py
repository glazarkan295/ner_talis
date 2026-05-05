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

from services.city_service import apply_city_transition, get_city_response
from services.registration_service import create_player, load_races, validate_name
from storage.json_storage import JsonStorage


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

    def test_main_starts_both_bots(self):
        import main as combined_main

        events: list[str] = []

        def fake_build_application():
            return FakeTelegramApplication(events)

        def fake_vk_constructor(token: str, group_id: int, storage_path: str):
            return FakeVkBot(token, group_id, storage_path, events)

        env = {
            "TELEGRAM_BOT_TOKEN": "telegram-test-token",
            "VK_GROUP_TOKEN": "vk-test-token",
            "VK_GROUP_ID": "123456",
            "BOT_MODE": "both",
            "PLAYERS_STORAGE_PATH": "data/players.json",
        }

        with patch.dict(os.environ, env, clear=False), \
             patch.object(combined_main, "load_project_env", lambda: None), \
             patch.object(combined_main, "build_application", fake_build_application), \
             patch.object(combined_main, "VkRegistrationBot", fake_vk_constructor):
            combined_main.main()

        self.assertIn("vk_run", events)
        self.assertIn("telegram_run_polling", events)

    def test_main_can_start_only_telegram(self):
        import main as combined_main

        events: list[str] = []

        def fake_build_application():
            return FakeTelegramApplication(events)

        def fail_if_vk_thread_starts():
            raise AssertionError("VK thread should not start in telegram mode")

        env = {
            "TELEGRAM_BOT_TOKEN": "telegram-test-token",
            "BOT_MODE": "telegram",
            "PLAYERS_STORAGE_PATH": "data/players.json",
        }

        with patch.dict(os.environ, env, clear=True), \
             patch.object(combined_main, "load_project_env", lambda: None), \
             patch.object(combined_main, "build_application", fake_build_application), \
             patch.object(combined_main, "start_vk_thread", fail_if_vk_thread_starts):
            combined_main.main()

        self.assertEqual(events, ["telegram_run_polling"])

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
