import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.admin_access import check_telegram_admin, check_vk_admin
from services.admin_command_service import execute_admin_command
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class AdminHardDeleteByGameIdTest(unittest.TestCase):
    def _make_player(self, storage, platform="telegram", external_user_id="111"):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform=platform,
            external_user_id=external_user_id,
            name=f"Игрок{external_user_id}",
            race_id="human",
            races=races,
        )
        storage.save_new_player(player, platform, external_user_id)
        return game_id, player

    def test_json_hard_delete_by_nt_game_id_removes_all_links_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["ADMIN_BACKUP_DIR"] = str(Path(tmp_dir) / "admin_backups")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id, player = self._make_player(storage, "telegram", "111")
            storage.create_link_code(game_id)
            token = storage.create_site_session(game_id, "profile", "telegram")

            result = execute_admin_command(
                text=f"/admin_delete_player {game_id.lower()} CONFIRM_DELETE",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )

            self.assertTrue(result.handled)
            self.assertIn("полностью удалён", result.text)
            self.assertIsNone(storage.get_player_by_game_id(game_id))
            self.assertIsNone(storage.get_player_by_platform("telegram", "111"))
            self.assertFalse(storage.is_name_taken(player["name"]))
            data = storage.load()
            self.assertNotIn(token, data.get("site_sessions", {}))
            self.assertFalse((Path(tmp_dir) / "admin_backups").exists())

    def test_sqlite_hard_delete_by_nt_game_id_removes_all_links(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = SQLiteStorage(str(Path(tmp_dir) / "players.sqlite3"))
            game_id, player = self._make_player(storage, "vk", "222")
            token = storage.create_site_session(game_id, "profile", "vk")

            result = execute_admin_command(
                text=f"/admin_delete_player {game_id} CONFIRM_DELETE",
                storage=storage,
                platform="vk",
                admin_user_id="999",
            )

            self.assertTrue(result.handled)
            self.assertIsNone(storage.get_player_by_game_id(game_id))
            self.assertIsNone(storage.get_player_by_platform("vk", "222"))
            self.assertFalse(storage.is_name_taken(player["name"]))
            self.assertNotIn(token, storage.load().get("site_sessions", {}))

    def test_delete_requires_real_nt_game_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            result = execute_admin_command(
                text="/admin_delete_player GAME_ID CONFIRM_DELETE",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertTrue(result.handled)
            self.assertIn("NT-XXXXXXXXXX", result.text)

            result = execute_admin_command(
                text="/admin_delete_player tg_123 CONFIRM_DELETE",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertIn("только по игровому ID", result.text)

    def test_admin_chat_is_optional_when_admin_user_is_set(self):
        old = dict(os.environ)
        try:
            os.environ.pop("TELEGRAM_ADMIN_CHAT_IDS", None)
            os.environ.pop("ADMIN_TELEGRAM_CHAT_IDS", None)
            os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
            self.assertTrue(check_telegram_admin(chat_id=123, user_id=999).allowed)

            os.environ.pop("VK_ADMIN_PEER_IDS", None)
            os.environ.pop("ADMIN_VK_PEER_IDS", None)
            os.environ["VK_ADMIN_USER_IDS"] = "555"
            self.assertTrue(check_vk_admin(peer_id=2000000001, user_id=555).allowed)
        finally:
            os.environ.clear()
            os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
