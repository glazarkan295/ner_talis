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


class FakeLyingStorage:
    def __init__(self):
        self.player = {
            "game_id": "NT-ABC1234567",
            "id": "NT-ABC1234567",
            "name": "ЛжеУдаление",
            "linked_accounts": {"telegram": "777"},
        }

    def get_player_by_game_id(self, game_id):
        return self.player

    def get_player_by_platform(self, platform, external_user_id):
        return self.player

    def hard_delete_player_by_game_id(self, game_id):
        return True


class AdminDeleteRealStorageTest(unittest.TestCase):
    def _create_player(self, storage, platform="telegram", external_user_id="123"):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform=platform,
            external_user_id=external_user_id,
            name=f"Удалить{external_user_id}",
            race_id="human",
            races=races,
        )
        storage.save_new_player(player, platform, external_user_id)
        return game_id, player

    def test_json_native_method_really_deletes_player(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id, _player = self._create_player(storage, "telegram", "123")
            self.assertTrue(hasattr(storage, "hard_delete_player_by_game_id"))
            self.assertTrue(storage.hard_delete_player_by_game_id(game_id))
            self.assertIsNone(storage.get_player_by_game_id(game_id))
            self.assertIsNone(storage.get_player_by_platform("telegram", "123"))

    def test_sqlite_native_method_really_deletes_player(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = SQLiteStorage(str(Path(tmp_dir) / "players.sqlite3"))
            game_id, _player = self._create_player(storage, "vk", "321")
            self.assertTrue(hasattr(storage, "hard_delete_player_by_game_id"))
            self.assertTrue(storage.hard_delete_player_by_game_id(game_id))
            self.assertIsNone(storage.get_player_by_game_id(game_id))
            self.assertIsNone(storage.get_player_by_platform("vk", "321"))

    def test_admin_command_does_not_report_success_if_storage_lies(self):
        result = execute_admin_command(
            text="/admin_delete_player NT-ABC1234567 CONFIRM_DELETE",
            storage=FakeLyingStorage(),
            platform="telegram",
            admin_user_id="999",
        )
        self.assertTrue(result.handled)
        self.assertIn("всё ещё находится", result.text)
        self.assertNotIn("полностью удалён", result.text)


if __name__ == "__main__":
    unittest.main()
