import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import HILLY_MEADOWS, OUTSIDE_CITY, START_SEARCH, add_item, handle_external_location_action
from services.item_registry import get_item_definition_by_name, load_item_definitions
from services.pve_battle_service import (
    BATTLE_ATTACK,
    BATTLE_ESCAPE,
    BATTLE_MAGIC_SPARK,
    battle_buttons,
    calculate_player_derived_stats,
    handle_battle_action,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class AssetsAndPveIntegrationTest(unittest.TestCase):
    def make_player_and_storage(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(game_id, "telegram", "111", "Боец", "human", races)
        storage.save_new_player(player, "telegram", "111")
        return storage, storage.get_player_by_platform("telegram", "111")

    def test_hilly_meadows_item_registry_is_loaded(self):
        items = load_item_definitions()
        self.assertEqual(len(items), 35)
        mint = get_item_definition_by_name("Луговая мята")
        self.assertIsNotNone(mint)
        self.assertEqual(mint["id"], "meadow_mint")

    def test_add_item_enriches_inventory_with_icon_and_stable_id(self):
        player = {"inventory": []}
        add_item(player, "Луговая мята", 2)
        self.assertEqual(player["inventory"][0]["id"], "meadow_mint")
        self.assertEqual(player["inventory"][0]["amount"], 2)
        self.assertTrue(player["inventory"][0]["icon"].startswith("/assets/items/hilly_meadows/"))

    def test_equipment_magic_armor_is_not_double_counted(self):
        player = {
            "level": 1,
            "stats": {},
            "equipment": {
                "cloak": {
                    "stat_modifiers": {
                        "magic_armor": 7,
                    },
                },
            },
        }

        stats = calculate_player_derived_stats(player)

        self.assertEqual(stats["magic_armor"], 7)

    def test_search_battle_starts_real_pve_battle(self):
        storage, player = self.make_player_and_storage()
        handle_external_location_action(storage, player, OUTSIDE_CITY)
        player = storage.get_player_by_platform("telegram", "111")
        handle_external_location_action(storage, player, HILLY_MEADOWS)
        player = storage.get_player_by_platform("telegram", "111")

        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(0))
        self.assertIn("Бой начался", response.text)
        self.assertEqual(response.buttons, battle_buttons())
        player = storage.get_player_by_platform("telegram", "111")
        self.assertTrue(player["in_battle"])
        self.assertIsInstance(player.get("active_battle"), dict)
        self.assertGreaterEqual(len(player["active_battle"]["enemies"]), 1)

    def test_battle_action_updates_or_ends_battle(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(0))
        self.assertIn("Бой начался", response.text)
        player = storage.get_player_by_platform("telegram", "111")

        attack = handle_external_location_action(storage, player, BATTLE_ATTACK, rng=random.Random(2))
        self.assertTrue("PVE-бой" in attack.text or "Победа" in attack.text or "проиграли" in attack.text)
        player = storage.get_player_by_platform("telegram", "111")
        if player.get("in_battle"):
            escape = handle_external_location_action(storage, player, BATTLE_ESCAPE, rng=random.Random(3))
            self.assertIn("отступ", escape.text.casefold())
            player = storage.get_player_by_platform("telegram", "111")
            self.assertFalse(player.get("in_battle"))


if __name__ == "__main__":
    unittest.main()
