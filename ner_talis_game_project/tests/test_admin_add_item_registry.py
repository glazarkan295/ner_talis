import os
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


class AdminAddItemRegistryTest(unittest.TestCase):
    def _make_player(self, storage):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="111",
            name="АдминТест",
            race_id="human",
            races=races,
        )
        storage.save_new_player(player, "telegram", "111")
        return game_id

    def test_simple_add_item_uses_registry_definition(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["ADMIN_BACKUP_DIR"] = str(Path(tmp_dir) / "admin_backups")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)

            result = execute_admin_command(
                text=f"/admin_add_item {game_id} dried_meat 20 обычный",
                storage=storage,
                platform="telegram",
                admin_user_id="999",
            )

            self.assertTrue(result.handled)
            self.assertIn("dried_meat x20", result.text)
            player = storage.get_player_by_game_id(game_id)
            stack = next(item for item in player["inventory"] if item.get("item_id") == "dried_meat")
            self.assertEqual(stack["name"], "Сушёное мясо")
            self.assertEqual(stack["amount"], 20)
            self.assertEqual(stack["max_stack"], 20)
            self.assertEqual(stack["energy_restore"], 7)
            self.assertEqual(stack["sell_price_copper"], 10)


if __name__ == "__main__":
    unittest.main()
