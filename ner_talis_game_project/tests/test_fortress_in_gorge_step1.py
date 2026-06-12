import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import (
    FORTRESS_ALLEYS,
    FORTRESS_COORDINATOR,
    FORTRESS_COURTYARD,
    FORTRESS_CREATE_ORDER_MENU,
    FORTRESS_HALL,
    FORTRESS_IN_GORGE,
    FORTRESS_ORDER_BOARD,
    FORTRESS_SEEKER_OUTPOST,
    handle_external_location_action,
)
from services.inventory_service import add_inventory_item
from services.item_registry import get_item_definition_by_id
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class FortressInGorgeStep1Test(unittest.TestCase):
    def make_player_and_storage(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        player = create_player(
            game_id="NT-FORT-1",
            platform="telegram",
            external_user_id="777",
            name="Крепостной путник",
            race_id="human",
            races=load_races("data/races.json"),
        )
        storage.save_new_player(player, "telegram", "777")
        return storage, storage.get_player_by_game_id("NT-FORT-1")

    def test_fortress_config_and_evidence_item_are_registered(self):
        config = json.loads((PROJECT_ROOT / "data" / "fortress_in_gorge.json").read_text(encoding="utf-8"))
        self.assertEqual("fortress_in_gorge_city_location_v1", config.get("version"))
        self.assertIn("courtyard", config.get("places", {}))
        self.assertIn("coordinator", config)
        self.assertEqual("evidence_bag", config["coordinator"]["evidence_item_id"])

        item = get_item_definition_by_id("evidence_bag")
        self.assertIsNotNone(item)
        self.assertEqual("мешок с доказательством", item.get("name_ru"))
        self.assertFalse(item.get("can_sell"))
        self.assertEqual(10, item.get("max_stack"))
        self.assertTrue(item.get("evidence_bag_rules", {}).get("cannot_stack_different_players"))
        self.assertTrue((PROJECT_ROOT / "web" / "public" / "assets" / "items" / "fortress" / "criminal" / "evidence_bag.png").exists())

    def test_fortress_navigation_uses_city_like_places(self):
        storage, player = self.make_player_and_storage()

        result = handle_external_location_action(storage, player, FORTRESS_IN_GORGE)
        self.assertIn("Крепость в ущелье", result.text)
        self.assertIn([FORTRESS_HALL, FORTRESS_ALLEYS], result.buttons)
        player = storage.get_player_by_game_id("NT-FORT-1")
        self.assertEqual("fortress_in_gorge_courtyard", player.get("current_zone"))

        result = handle_external_location_action(storage, player, FORTRESS_ALLEYS)
        self.assertIn("Переулки крепости", result.text)
        self.assertTrue(any(FORTRESS_COORDINATOR in row for row in result.buttons))
        player = storage.get_player_by_game_id("NT-FORT-1")
        self.assertEqual("fortress_in_gorge_alleys", player.get("current_zone"))

        result = handle_external_location_action(storage, player, FORTRESS_COORDINATOR)
        self.assertIn("Координатор", result.text)
        self.assertIn([FORTRESS_ORDER_BOARD, "Квесты"], result.buttons)

        player = storage.get_player_by_game_id("NT-FORT-1")
        result = handle_external_location_action(storage, player, FORTRESS_ORDER_BOARD)
        self.assertIn("Доска заказов", result.text)
        self.assertIn(["Выставить заказ", "Посмотреть заказы"], result.buttons)

        player = storage.get_player_by_game_id("NT-FORT-1")
        result = handle_external_location_action(storage, player, FORTRESS_CREATE_ORDER_MENU)
        self.assertIn("Для создания заказа", result.text)
        self.assertIn(["Создать заказ"], result.buttons)

    def test_evidence_bags_stack_only_by_same_victim(self):
        player = {"inventory": [], "inventory_slots": 10, "extra_inventory_slots": 0, "max_inventory_slots": 10}
        base = get_item_definition_by_id("evidence_bag")
        self.assertIsNotNone(base)

        first = dict(base)
        first.update({
            "evidence_victim_id": "NT-TARGET-1",
            "evidence_victim_name": "Цель Один",
            "description": "Мешок с доказательством, выбитый из игрока Цель Один.",
        })
        second_same = dict(first)
        third_other = dict(base)
        third_other.update({
            "evidence_victim_id": "NT-TARGET-2",
            "evidence_victim_name": "Цель Два",
            "description": "Мешок с доказательством, выбитый из игрока Цель Два.",
        })

        add_inventory_item(player, first, amount=1)
        add_inventory_item(player, second_same, amount=2)
        add_inventory_item(player, third_other, amount=1)

        stacks = [item for item in player["inventory"] if item.get("item_id") == "evidence_bag"]
        self.assertEqual(2, len(stacks))
        amounts_by_victim = {item.get("evidence_victim_id"): item.get("amount") for item in stacks}
        self.assertEqual(3, amounts_by_victim["NT-TARGET-1"])
        self.assertEqual(1, amounts_by_victim["NT-TARGET-2"])


if __name__ == "__main__":
    unittest.main()
