import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class WebSessionAndHardDeleteTest(unittest.TestCase):
    def _make_player(self, storage, platform="telegram", external_user_id="101"):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform=platform,
            external_user_id=external_user_id,
            name=f"Web{external_user_id}",
            race_id="human",
            races=races,
        )
        storage.save_new_player(player, platform, external_user_id)
        return game_id

    def _assert_web_session_and_hard_delete(self, storage):
        game_id = self._make_player(storage)
        token = storage.create_web_session(game_id, scope="profile", platform="telegram")
        player, session = storage.get_player_by_web_token(token, scope="profile")
        self.assertIsNotNone(player)
        self.assertEqual(player["game_id"], game_id)
        self.assertIsNotNone(session)

        self.assertTrue(storage.hard_delete_player_by_game_id(game_id))
        self.assertIsNone(storage.get_player_by_game_id(game_id))
        self.assertIsNone(storage.get_player_by_platform("telegram", "101"))
        player, session = storage.get_player_by_web_token(token, scope="profile")
        self.assertIsNone(player)
        self.assertIsNone(session)

    def test_json_web_session_removed_on_hard_delete(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._assert_web_session_and_hard_delete(JsonStorage(str(Path(tmp_dir) / "players.json")))

    def test_sqlite_web_session_removed_on_hard_delete(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._assert_web_session_and_hard_delete(SQLiteStorage(str(Path(tmp_dir) / "players.sqlite3")))


if __name__ == "__main__":
    unittest.main()
