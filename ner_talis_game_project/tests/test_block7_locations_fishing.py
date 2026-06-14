import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import CITY_BUTTONS, process_world_action
from services.fishing_service import START_PIER_FISHING, load_fishing_sources
from services.inventory_service import add_inventory_item
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class Block7LocationsFishingTest(unittest.TestCase):
    def make_storage_player(self):
        tmp = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(tmp.name) / "players.json"))
        player = create_player(
            game_id="NT-FISH",
            platform="telegram",
            external_user_id="111",
            name="Рыбак",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["energy"] = 10
        player["current_energy"] = 10
        player["inventory"] = []
        add_inventory_item(player, "Удочка рыбака", 1, item_id="fishing_rod", max_stack=1)
        storage.save_new_player(player, "telegram", "111")
        return tmp, storage, storage.get_player_by_game_id("NT-FISH")

    def test_city_buttons_include_fishing_cast(self):
        self.assertIn(START_PIER_FISHING, CITY_BUTTONS)

    def test_pier_fishing_cast_starts_timer_and_spends_one_energy(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        result = process_world_action(storage, player, "Рыбалка на пристани", "telegram")
        self.assertIn(START_PIER_FISHING, sum(result.buttons, []))
        player = storage.get_player_by_game_id("NT-FISH")
        result = process_world_action(storage, player, START_PIER_FISHING, "telegram")

        # Cast starts a 60s timer, spends exactly 1 energy, no instant loot yet.
        self.assertIn("Поклёвка через", result.text)
        self.assertIsNotNone(result.scheduled_timer)
        self.assertEqual(result.scheduled_timer["seconds"], 60)
        updated = storage.get_player_by_game_id("NT-FISH")
        self.assertEqual(updated["energy"], 9)
        timer = updated.get("active_timer")
        self.assertIsInstance(timer, dict)
        self.assertEqual(timer.get("type"), "fishing")
        # Only the fishing rod is in the inventory; the catch comes later.
        self.assertEqual(len(updated.get("inventory", [])), 1)

    def test_pier_fishing_timer_completion_grants_loot(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Рыбалка на пристани", "telegram")
        player = storage.get_player_by_game_id("NT-FISH")
        process_world_action(storage, player, START_PIER_FISHING, "telegram")

        # Force the timer to be finished, then check it.
        player = storage.get_player_by_game_id("NT-FISH")
        player["active_timer"]["ends_at"] = 0
        storage.update_player(player)
        result = process_world_action(storage, storage.get_player_by_game_id("NT-FISH"), "Проверить таймер", "telegram")

        self.assertIn("Получено:", result.text)
        updated = storage.get_player_by_game_id("NT-FISH")
        self.assertIsNone(updated.get("active_timer"))
        self.assertGreaterEqual(len(updated.get("inventory", [])), 2)

    def test_pier_fishing_requires_rod(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        player["inventory"] = []
        storage.update_player(player)
        process_world_action(storage, player, "Рыбалка на пристани", "telegram")
        player = storage.get_player_by_game_id("NT-FISH")

        result = process_world_action(storage, player, START_PIER_FISHING, "telegram")
        self.assertIn("нужна удочка", result.text.casefold())

    def test_pier_fishing_tables_match_corrected_groups(self):
        sources = load_fishing_sources()
        tables = sources["pier_fishing"]["tables"]
        self.assertEqual({entry["item_id"] for entry in tables["common"]}, {"small_fish", "large_fish"})
        self.assertEqual({entry["item_id"] for entry in tables["uncommon"]}, {"eel", "jellyfish", "mollusk", "old_iron_sword"})
        self.assertEqual({entry["item_id"] for entry in tables["rare"]}, {"pearlescent_fish", "golden_fish", "old_small_chest"})
        self.assertEqual({entry["item_id"] for entry in tables["trash"]}, {"old_torn_boot", "shell", "seaweed"})
        self.assertEqual(sources["pier_fishing"]["rarity_weights"], {"common": 50, "uncommon": 19, "rare": 1, "trash": 30})

    def test_waterside_location_event_removed_from_configs(self):
        import json
        from project_paths import resolve_project_path

        for relative_path in ("data/hilly_meadows.json", "data/ordinary_forest.json"):
            with resolve_project_path(relative_path).open("r", encoding="utf-8") as file:
                config = json.load(file)
            self.assertNotIn("waterside_loot", config.get("events", {}))
        self.assertNotIn("location_waterside_find", load_fishing_sources())


if __name__ == "__main__":
    unittest.main()
