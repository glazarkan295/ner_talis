import os
import sys
import tempfile
import unittest
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


class RegistrationSmokeTest(unittest.TestCase):
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
            "PLAYERS_STORAGE_PATH": "data/players.json",
        }

        with patch.dict(os.environ, env, clear=False), \
             patch.object(combined_main, "build_application", fake_build_application), \
             patch.object(combined_main, "VkRegistrationBot", fake_vk_constructor):
            combined_main.main()

        self.assertIn("vk_run", events)
        self.assertIn("telegram_run_polling", events)


if __name__ == "__main__":
    unittest.main()
