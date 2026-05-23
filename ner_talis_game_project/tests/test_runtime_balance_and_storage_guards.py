import os
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT_DIR.parent
for path in (ROOT_DIR, PROJECT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services.pve_battle_service import (
    BATTLE_POUCH,
    BATTLE_POUCH_NEXT,
    BATTLE_POUCH_ITEM_PREFIX,
    create_location_battle,
    handle_battle_action,
)
from services.registration_service import create_player, load_races
from storage.storage_factory import normalize_backend


class RuntimeBalanceAndStorageGuardsTest(unittest.TestCase):
    def make_player(self, game_id="NT-RUNTIME"):
        races = load_races("data/races.json")
        return create_player(game_id, "telegram", "111", "Тестер", "human", races)

    def test_ordinary_forest_mobs_start_at_level_10_and_cap_at_60(self):
        low_player = self.make_player("NT-FOREST-LOW")
        low_player["level"] = 1
        battle, _text = create_location_battle(low_player, random.Random(1), "ordinary_forest")
        self.assertTrue(all(10 <= enemy["level"] <= 60 for enemy in battle["enemies"]))

        high_player = self.make_player("NT-FOREST-HIGH")
        high_player["level"] = 100
        battle, _text = create_location_battle(high_player, random.Random(2), "ordinary_forest")
        self.assertTrue(all(10 <= enemy["level"] <= 60 for enemy in battle["enemies"]))

    def test_combat_pouch_uses_numbered_items_and_paginates(self):
        player = self.make_player()
        player["inventory"] = [
            {
                "id": f"test_potion_{index}",
                "name": f"Тестовое зелье {index}",
                "category": "Расходник",
                "amount": 1,
                "use_effect": {"hp_restore": 5},
            }
            for index in range(1, 10)
        ]
        battle, _text = create_location_battle(player, random.Random(1), "hilly_meadows")
        battle["player_state"]["current_hp"] = max(1, battle["player_state"]["max_hp"] - 20)
        for enemy in battle["enemies"]:
            enemy["accuracy"] = 0
        player["active_battle"] = battle
        player["in_battle"] = True

        text, buttons = handle_battle_action(player, BATTLE_POUCH, random.Random(1))
        flat = [button for row in buttons for button in row]
        self.assertIn("Страница 1/2", text)
        self.assertIn(f"{BATTLE_POUCH_ITEM_PREFIX}1", flat)
        self.assertIn(BATTLE_POUCH_NEXT, flat)
        self.assertNotIn("Использовать: Тестовое зелье 1", flat)

        text, _buttons = handle_battle_action(player, f"{BATTLE_POUCH_ITEM_PREFIX}1", random.Random(1))
        self.assertIn("Тестовое зелье 1", text)
        self.assertFalse(any(item.get("id") == "test_potion_1" for item in player["inventory"]))

    def test_json_storage_is_blocked_in_production_without_explicit_override(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            os.environ.pop("ALLOW_JSON_STORAGE_IN_PRODUCTION", None)
            with self.assertRaises(RuntimeError):
                normalize_backend("json")

        with patch.dict(os.environ, {"APP_ENV": "production", "ALLOW_JSON_STORAGE_IN_PRODUCTION": "true"}, clear=False):
            self.assertEqual(normalize_backend("json"), "json")


if __name__ == "__main__":
    unittest.main()
