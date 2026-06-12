import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.admin_command_service import admin_help_text, execute_admin_command
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class AdminChatCommandsV2Test(unittest.TestCase):
    def _make_player(self, storage, *, name="АдминИгрок", platform="telegram", external_user_id="111"):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform=platform,
            external_user_id=external_user_id,
            name=name,
            race_id="human",
            races=races,
        )
        player["money"] = 50
        player["hp"] = 80
        player["max_hp"] = 100
        player["energy"] = 75
        player["max_energy"] = 100
        storage.save_new_player(player, platform, external_user_id)
        return game_id

    def test_help_lists_new_admin_commands(self):
        text = admin_help_text()
        self.assertIn("/admin_find_player", text)
        self.assertIn("/admin_player_info", text)
        self.assertIn("/admin_add_money", text)
        self.assertIn("/admin_kick_profile_sessions", text)

    def test_find_player_by_name_and_show_info(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage, name="СеверныйТест", external_user_id="777")

            result = execute_admin_command(
                text="/admin_find_player Северный",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertTrue(result.handled)
            self.assertIn(game_id, result.text)
            self.assertIn("СеверныйТест", result.text)
            self.assertIn("telegram:777", result.text)

            info = execute_admin_command(
                text=f"/admin_player_info {game_id}",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertTrue(info.handled)
            self.assertIn("Игрок: СеверныйТест", info.text)
            self.assertIn("Монеты: 50", info.text)
            self.assertIn("Инвентарь:", info.text)

    def test_add_money_requires_confirm_and_writes_backup_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["ADMIN_BACKUP_DIR"] = str(Path(tmp_dir) / "admin_backups")
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)

            rejected = execute_admin_command(
                text=f"/admin_add_money {game_id} 100 NO",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertIn("CONFIRM", rejected.text)
            self.assertEqual(storage.get_player_by_game_id(game_id)["money"], 50)

            result = execute_admin_command(
                text=f"/admin_add_money {game_id} 100 CONFIRM",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertTrue(result.handled)
            self.assertIn("50 -> 150", result.text)
            self.assertEqual(storage.get_player_by_game_id(game_id)["money"], 150)
            self.assertTrue(any(Path(tmp_dir, "admin_backups").iterdir()))
            self.assertIn("add_money", Path(tmp_dir, "admin_audit.log").read_text(encoding="utf-8"))

            negative = execute_admin_command(
                text=f"/admin_add_money {game_id} -1000 CONFIRM",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertIn("Нельзя списать", negative.text)
            self.assertEqual(storage.get_player_by_game_id(game_id)["money"], 150)

    def test_kick_profile_sessions_json_and_sqlite(self):
        for storage_class, filename in ((JsonStorage, "players.json"), (SQLiteStorage, "players.sqlite3")):
            with self.subTest(storage=storage_class.__name__), tempfile.TemporaryDirectory() as tmp_dir:
                storage = storage_class(str(Path(tmp_dir) / filename))
                game_id = self._make_player(storage)
                activation = storage.create_site_session(game_id, "profile", "telegram")
                session = storage.get_web_session(activation, scope="profile")
                active_token = session["token"]
                self.assertIsNotNone(storage.get_web_session(active_token, scope="profile"))

                result = execute_admin_command(
                    text=f"/admin_kick_profile_sessions {game_id} CONFIRM",
                    storage=storage,
                    platform="telegram",
                    admin_user_id="999",
                )
                self.assertTrue(result.handled)
                self.assertIn("отключены", result.text)
                self.assertIsNone(storage.get_web_session(active_token, scope="profile"))


    def test_admin_chat_require_chat_env(self):
        from services.admin_access import check_telegram_admin, check_vk_admin

        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
            os.environ["VK_ADMIN_USER_IDS"] = "555"
            os.environ["ADMIN_COMMANDS_REQUIRE_CHAT"] = "true"

            self.assertFalse(check_telegram_admin(chat_id=123, user_id=999).allowed)
            self.assertFalse(check_vk_admin(peer_id=2000000001, user_id=555).allowed)

            os.environ["TELEGRAM_ADMIN_CHAT_IDS"] = "123"
            os.environ["VK_ADMIN_PEER_IDS"] = "2000000001"
            self.assertTrue(check_telegram_admin(chat_id=123, user_id=999).allowed)
            self.assertFalse(check_telegram_admin(chat_id=124, user_id=999).allowed)
            self.assertTrue(check_vk_admin(peer_id=2000000001, user_id=555).allowed)
            self.assertFalse(check_vk_admin(peer_id=2000000002, user_id=555).allowed)
        finally:
            os.environ.clear()
            os.environ.update(old)


    def test_add_progress_rewards_one_to_one_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["ADMIN_BACKUP_DIR"] = str(Path(tmp_dir) / "admin_backups")
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)

            stat_result = execute_admin_command(
                text=f"/admin_add_stat_points {game_id} 3 CONFIRM",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertTrue(stat_result.handled)
            self.assertIn("Очки характеристик", stat_result.text)
            self.assertEqual(storage.get_player_by_game_id(game_id)["free_stat_points"], 3)

            skill_result = execute_admin_command(
                text=f"/admin_add_skill_points {game_id} 4 CONFIRM",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertTrue(skill_result.handled)
            self.assertIn("Очки навыков", skill_result.text)
            self.assertEqual(storage.get_player_by_game_id(game_id)["free_skill_points"], 4)

            exp_result = execute_admin_command(
                text=f"/admin_add_experience {game_id} 100 CONFIRM",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertTrue(exp_result.handled)
            self.assertIn("+100", exp_result.text)
            player = storage.get_player_by_game_id(game_id)
            self.assertEqual(player["level"], 2)
            self.assertEqual(player["experience"], 0)
            self.assertEqual(player["total_experience"], 100)
            # 3/4 manually granted + 5/2 for level-up.
            self.assertEqual(player["free_stat_points"], 8)
            self.assertEqual(player["free_skill_points"], 6)
            audit = Path(tmp_dir, "admin_audit.log").read_text(encoding="utf-8")
            self.assertIn("add_stat_points", audit)
            self.assertIn("add_skill_points", audit)
            self.assertIn("add_experience", audit)

    def test_progress_rewards_require_confirm_and_do_not_go_below_zero(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)

            rejected = execute_admin_command(
                text=f"/admin_add_skill_points {game_id} 5 NO",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertIn("CONFIRM", rejected.text)
            self.assertEqual(storage.get_player_by_game_id(game_id).get("free_skill_points", 0), 0)

            negative = execute_admin_command(
                text=f"/admin_add_stat_points {game_id} -1 CONFIRM",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertIn("Нельзя списать", negative.text)
            self.assertEqual(storage.get_player_by_game_id(game_id).get("free_stat_points", 0), 0)

            bad_exp = execute_admin_command(
                text=f"/admin_add_exp {game_id} -10 CONFIRM",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            self.assertIn("больше 0", bad_exp.text)


if __name__ == "__main__":
    unittest.main()
