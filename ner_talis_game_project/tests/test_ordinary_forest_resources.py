import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import (
    COLLECT_MUSHROOMS,
    COLLECT_TREE,
    GATHER_WATER,
    PUT_HAND_IN_BURROW,
    resolve_active_event,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage

DATA_DIR = ROOT_DIR.parent / "data"


class OrdinaryForestResourceTablesTest(unittest.TestCase):
    def make_player_and_storage(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="333",
            name="Лесник",
            race_id="human",
            races=races,
        )
        player["current_location"] = "ordinary_forest"
        player["current_zone"] = "ordinary_forest"
        storage.save_new_player(player, "telegram", "333")
        return storage, storage.get_player_by_platform("telegram", "333")

    def test_ordinary_forest_has_explicit_resource_tables_without_waterside(self):
        data = json.loads((DATA_DIR / "ordinary_forest.json").read_text(encoding="utf-8"))
        self.assertNotIn("waterside_loot", data.get("events", {}))
        self.assertEqual("ordinary_forest_resources_v1", data.get("resource_find_tables_version"))
        tables = data.get("resource_find_tables")
        self.assertIsInstance(tables, dict)
        self.assertEqual({"dry_tree", "mushrooms", "river_water", "small_burrow"}, set(tables))
        self.assertEqual(["Сухое бревно"], [entry["name_ru"] for entry in tables["dry_tree"]])
        self.assertEqual(
            ["Съедобный лесной гриб", "Горький серый гриб", "Бледная поганка"],
            [entry["name_ru"] for entry in tables["mushrooms"]],
        )
        self.assertEqual(
            ["Старые перчатки (необычные)", "Куски ткани", "Неплохой пояс (необычные)", "Укус из норы"],
            [entry["name_ru"] for entry in tables["small_burrow"]],
        )
        self.assertEqual([12, 36, 12, 40], [entry["weight"] for entry in tables["small_burrow"]])

    def test_dry_tree_reward_uses_configured_table(self):
        storage, player = self.make_player_and_storage()
        player["active_event"] = {"id": "test_dry_tree", "type": "dry_tree", "location_id": "ordinary_forest"}
        storage.update_player(player)
        response = resolve_active_event(storage, storage.get_player_by_platform("telegram", "333"), COLLECT_TREE, random.Random(1))
        self.assertRegex(response.text, r"Получено: Сухое бревно ×[1-3]")

    def test_mushroom_reward_uses_configured_table(self):
        storage, player = self.make_player_and_storage()
        player["active_event"] = {"id": "test_mushrooms", "type": "mushrooms", "location_id": "ordinary_forest"}
        storage.update_player(player)
        response = resolve_active_event(storage, storage.get_player_by_platform("telegram", "333"), COLLECT_MUSHROOMS, random.Random(2))
        self.assertRegex(response.text, r"Получено: (Съедобный лесной гриб|Горький серый гриб|Бледная поганка) ×[1-3]")

    def test_river_reward_uses_configured_water_table(self):
        storage, player = self.make_player_and_storage()
        player["active_event"] = {"id": "test_river", "type": "river", "location_id": "ordinary_forest"}
        storage.update_player(player)
        response = resolve_active_event(storage, storage.get_player_by_platform("telegram", "333"), GATHER_WATER, random.Random(3))
        self.assertIn("Получено:", response.text)
        self.assertIn("Чистая вода", response.text)

    def test_burrow_reward_uses_configured_table_or_bite(self):
        allowed = ("Старые перчатки", "Куски ткани", "Неплохой пояс", "Потеря: HP")
        for seed in range(8):
            storage, player = self.make_player_and_storage()
            player["active_event"] = {"id": f"test_burrow_{seed}", "type": "small_burrow", "location_id": "ordinary_forest"}
            storage.update_player(player)
            response = resolve_active_event(storage, storage.get_player_by_platform("telegram", "333"), PUT_HAND_IN_BURROW, random.Random(seed))
            self.assertTrue(any(token in response.text for token in allowed), response.text)


if __name__ == "__main__":
    unittest.main()
