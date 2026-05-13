import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.admin_command_service import execute_admin_command
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class AdminDeletePlayerTest(unittest.TestCase):
    def test_command_supports_telegram_group_suffix_and_real_id(self):
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

    def test_command_rejects_placeholder(self):
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

    def test_can_use_raw_unique_platform_id(self):
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


if __name__ == "__main__":
    unittest.main()
