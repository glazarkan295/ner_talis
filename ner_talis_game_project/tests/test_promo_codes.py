import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.admin_command_service import execute_admin_command
from services.promo_service import load_promo_data, redeem_promo_code
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class PromoCodeCreationTest(unittest.TestCase):
    def setUp(self):
        self._old_promo_path = os.environ.get("PROMO_CODES_PATH")
        self._old_audit_path = os.environ.get("ADMIN_AUDIT_LOG_PATH")

    def tearDown(self):
        if self._old_promo_path is None:
            os.environ.pop("PROMO_CODES_PATH", None)
        else:
            os.environ["PROMO_CODES_PATH"] = self._old_promo_path
        if self._old_audit_path is None:
            os.environ.pop("ADMIN_AUDIT_LOG_PATH", None)
        else:
            os.environ["ADMIN_AUDIT_LOG_PATH"] = self._old_audit_path

    def _make_player(self, storage, *, platform="telegram", external_user_id="111", name="ПромоТест", race_id="human"):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform=platform,
            external_user_id=external_user_id,
            name=name,
            race_id=race_id,
            races=races,
        )
        storage.save_new_player(player, platform, external_user_id)
        return game_id

    def test_admin_promo_add_creates_code_and_redeem_enriches_registry_item_json_storage(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["PROMO_CODES_PATH"] = str(Path(tmp_dir) / "promo_codes.json")
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)

            result = execute_admin_command(
                text='/admin_promo_add MEAT20 2 {"money":1000,"items":[{"item_id":"dried_meat","amount":20}]}',
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )

            self.assertTrue(result.handled)
            self.assertIn("Промокод MEAT20 создан", result.text)
            promo_data = load_promo_data(storage)
            self.assertIn("MEAT20", promo_data["codes"])
            self.assertEqual(promo_data["codes"]["MEAT20"]["uses_left"], 2)

            ok, message = redeem_promo_code(storage, game_id, "meat20")

            self.assertTrue(ok, message)
            self.assertIn("успешно", message)
            player = storage.get_player_by_game_id(game_id)
            self.assertEqual(player["money_copper"], 1000)
            stack = next(item for item in player["inventory"] if item.get("item_id") == "dried_meat")
            self.assertEqual(stack["name"], "Сушёное мясо")
            self.assertEqual(stack["amount"], 20)
            self.assertEqual(stack["max_stack"], 20)
            self.assertEqual(stack["energy_restore"], 7)
            self.assertEqual(stack["sell_price_copper"], 10)
            self.assertEqual(stack["source"], "promo_code")

            promo_data = load_promo_data(storage)
            self.assertEqual(promo_data["codes"]["MEAT20"]["uses_left"], 1)
            self.assertIn(game_id, promo_data["codes"]["MEAT20"]["used_by"])


    def test_promo_experience_reward_uses_progression_handler_and_levels_player(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["PROMO_CODES_PATH"] = str(Path(tmp_dir) / "promo_codes.json")
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage, race_id="elf")

            result = execute_admin_command(
                text='/admin_promo_add EXP4500 1 {"experience":4500}',
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            ok, message = redeem_promo_code(storage, game_id, "exp4500")

            self.assertTrue(result.handled)
            self.assertIn("Промокод EXP4500 создан", result.text)
            self.assertTrue(ok, message)
            player = storage.get_player_by_game_id(game_id)
            self.assertEqual(player["total_experience"], 4500)
            self.assertEqual(player["experience"], 0)
            self.assertEqual(player["level"], 10)
            self.assertEqual(player["experience_to_next"], 1000)
            self.assertEqual(player["free_stat_points"], 45)
            self.assertEqual(player["free_skill_points"], 18)

    def test_redeem_rejects_second_use_by_same_player(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["PROMO_CODES_PATH"] = str(Path(tmp_dir) / "promo_codes.json")
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)
            execute_admin_command(
                text='/admin_promo_add ONCE 5 {"money":100}',
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )

            ok, _message = redeem_promo_code(storage, game_id, "ONCE")
            second_ok, second_message = redeem_promo_code(storage, game_id, "ONCE")

            self.assertTrue(ok)
            self.assertFalse(second_ok)
            self.assertIn("уже использован", second_message)
            player = storage.get_player_by_game_id(game_id)
            self.assertEqual(player["money_copper"], 100)

    def test_admin_promo_add_works_with_sqlite_storage(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = SQLiteStorage(str(Path(tmp_dir) / "players.sqlite3"))
            game_id = self._make_player(storage, platform="vk", external_user_id="222", name="ПромоSQLite")

            result = execute_admin_command(
                text='/admin_promo_add SQLMEAT 1 {"items":[{"item_id":"dried_meat","amount":20}]}',
                storage=storage,
                platform="vk",
                admin_user_id="999",
            )
            ok, message = redeem_promo_code(storage, game_id, "SQLMEAT")

            self.assertTrue(result.handled)
            self.assertTrue(ok, message)
            player = storage.get_player_by_game_id(game_id)
            stack = next(item for item in player["inventory"] if item.get("item_id") == "dried_meat")
            self.assertEqual(stack["name"], "Сушёное мясо")
            self.assertEqual(stack["sell_price_copper"], 10)
            self.assertEqual(load_promo_data(storage)["codes"]["SQLMEAT"]["uses_left"], 0)

    def test_promo_zero_and_negative_item_amounts_are_not_upgraded_to_one(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["PROMO_CODES_PATH"] = str(Path(tmp_dir) / "promo_codes.json")
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)

            execute_admin_command(
                text='/admin_promo_add EMPTYITEMS 1 {"items":[{"item_id":"dried_meat","amount":0},{"item_id":"small_potion","amount":-3}]}',
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )

            ok, message = redeem_promo_code(storage, game_id, "EMPTYITEMS")

            self.assertTrue(ok, message)
            player = storage.get_player_by_game_id(game_id)
            self.assertFalse(any(item.get("item_id") == "dried_meat" for item in player["inventory"] if isinstance(item, dict)))
            self.assertFalse(any(item.get("item_id") == "small_potion" for item in player["inventory"] if isinstance(item, dict)))

    def test_promo_custom_fallback_keeps_promo_source(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["PROMO_CODES_PATH"] = str(Path(tmp_dir) / "promo_codes.json")
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)

            execute_admin_command(
                text='/admin_promo_add CUSTOM 1 {"items":[{"item_id":"unknown_promo_item","name":"Особый жетон","amount":2}]}',
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            ok, message = redeem_promo_code(storage, game_id, "CUSTOM")

            self.assertTrue(ok, message)
            player = storage.get_player_by_game_id(game_id)
            stack = next(item for item in player["inventory"] if item.get("item_id") == "unknown_promo_item")
            self.assertEqual(stack["source"], "promo_code")
            self.assertEqual(stack["name"], "Особый жетон")
            self.assertEqual(stack["amount"], 2)

    def test_promo_mistyped_item_id_does_not_enrich_from_matching_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["PROMO_CODES_PATH"] = str(Path(tmp_dir) / "promo_codes.json")
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "admin_audit.log")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)

            execute_admin_command(
                text='/admin_promo_add TYPO 1 {"items":[{"item_id":"dried_meat_typo","name":"Сушёное мясо","amount":1}]}',
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )
            ok, message = redeem_promo_code(storage, game_id, "TYPO")

            self.assertTrue(ok, message)
            player = storage.get_player_by_game_id(game_id)
            stack = next(item for item in player["inventory"] if item.get("item_id") == "dried_meat_typo")
            self.assertEqual(stack["name"], "Сушёное мясо")
            self.assertEqual(stack["source"], "promo_code")
            self.assertNotEqual(stack.get("max_stack"), 20)
            self.assertNotIn("energy_restore", stack)
            self.assertNotIn("sell_price_copper", stack)


if __name__ == "__main__":
    unittest.main()
