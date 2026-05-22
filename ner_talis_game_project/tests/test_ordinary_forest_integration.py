import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import (
    COLLECT_TREE,
    COMMON_FOREST,
    START_SEARCH,
    add_item,
    create_search_event,
    handle_external_location_action,
    resolve_active_event,
)
from services.item_registry import get_item_definition_by_id, get_item_definition_by_name, load_all_item_definitions
from services.pve_battle_service import create_location_battle
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class OrdinaryForestIntegrationTest(unittest.TestCase):
    def make_player_and_storage(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        player = create_player(storage.generate_game_id(), "telegram", "forest_user", "Лесник", "human", races)
        skills = player.setdefault("skills", {})
        active = skills.setdefault("active", [])
        equipped = skills.setdefault("equipped", [])
        basic = next(skill for skill in active if skill.get("id") == "basic_attack")
        active.remove(basic)
        equipped.append(basic)
        storage.save_new_player(player, "telegram", "forest_user")
        return storage, storage.get_player_by_platform("telegram", "forest_user")

    def test_ordinary_forest_assets_are_loaded_by_runtime_registry(self):
        dry_log = get_item_definition_by_name("Сухое бревно")
        self.assertIsNotNone(dry_log)
        self.assertEqual(dry_log["id"], "dry_log")
        self.assertIn("ordinary_forest", dry_log["icon"])

    def test_shared_items_keep_hilly_meadows_definitions(self):
        shared_ids = {
            "clean_water",
            "raw_meat",
            "silver_coin",
            "hearty_stew",
            "herbal_tea",
            "meat_flatbread",
            "dried_meat",
        }
        loaded_shared_ids = [
            item.get("id")
            for item in load_all_item_definitions()
            if item.get("id") in shared_ids
        ]

        self.assertEqual(set(loaded_shared_ids), shared_ids)
        self.assertEqual(len(loaded_shared_ids), len(shared_ids))
        for item_id in shared_ids:
            definition = get_item_definition_by_id(item_id)
            self.assertIsNotNone(definition)
            self.assertIn("hilly_meadows", definition["icon"])
            self.assertNotIn("ordinary_forest", definition["icon"])

    def test_enter_ordinary_forest_and_start_search(self):
        storage, player = self.make_player_and_storage()
        response = handle_external_location_action(storage, player, COMMON_FOREST, random.Random(1))
        self.assertEqual(response.zone_id, "ordinary_forest")
        self.assertIn("Обыкновенный лес", response.text)

        player = storage.get_player_by_platform("telegram", "forest_user")
        response = handle_external_location_action(storage, player, START_SEARCH, random.Random(1))
        self.assertEqual(response.zone_id, "ordinary_forest_search")
        self.assertIsNotNone(response.scheduled_timer)
        updated = storage.get_player_by_platform("telegram", "forest_user")
        self.assertEqual(updated["active_timer"]["location_id"], "ordinary_forest")

    def test_ordinary_forest_tree_event_grants_forest_resource(self):
        storage, player = self.make_player_and_storage()
        player["current_zone"] = "ordinary_forest"
        player["location_id"] = "ordinary_forest"
        player["current_location"] = "ordinary_forest"
        player["active_event"] = create_search_event("dry_tree", random.Random(1), "ordinary_forest")
        storage.update_player(player)

        player = storage.get_player_by_platform("telegram", "forest_user")
        response = resolve_active_event(storage, player, COLLECT_TREE, random.Random(1))
        self.assertEqual(response.zone_id, "ordinary_forest")
        self.assertIn("Сухое бревно", response.text)
        updated = storage.get_player_by_platform("telegram", "forest_user")
        self.assertTrue(any(item.get("name") == "Сухое бревно" for item in updated.get("inventory", [])))


    def test_event_reward_message_mentions_overflow_slot(self):
        storage, player = self.make_player_and_storage()
        player["inventory_capacity"] = 20
        player["inventory"] = [
            {"id": f"regular_{index}", "name": f"Занятый слот {index}", "amount": 1, "max_stack": 1}
            for index in range(20)
        ]
        player["current_zone"] = "ordinary_forest"
        player["location_id"] = "ordinary_forest"
        player["current_location"] = "ordinary_forest"
        player["active_event"] = create_search_event("dry_tree", random.Random(1), "ordinary_forest")
        storage.update_player(player)

        response = resolve_active_event(storage, storage.get_player_by_platform("telegram", "forest_user"), COLLECT_TREE, random.Random(1))

        self.assertIn("В доп. слот попало", response.text)

    def test_ordinary_forest_camp_eating_keeps_forest_zone(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "ordinary_forest"
        player["current_zone"] = "ordinary_forest_camp_eating"
        player["location_id"] = "ordinary_forest_camp_eating"
        player["energy"] = 20
        player["current_energy"] = 20
        add_item(player, "Сушёное мясо", 1, source="Обыкновенный лес")
        storage.update_player(player)

        response = handle_external_location_action(storage, player, "Съесть: Сушёное мясо")

        self.assertIn("Энергия восстановлена", response.text)
        self.assertEqual(response.zone_id, "ordinary_forest_camp_eating")
        updated = storage.get_player_by_platform("telegram", "forest_user")
        self.assertEqual(updated["current_location"], "ordinary_forest")

    def test_ordinary_forest_battle_uses_forest_mobs_and_return_location(self):
        _storage, player = self.make_player_and_storage()
        battle, text = create_location_battle(player, random.Random(3), "ordinary_forest")
        self.assertEqual(player["current_zone"], "ordinary_forest_battle")
        self.assertEqual(battle["return_location"], "ordinary_forest")
        self.assertTrue(any(enemy["name"] in {"Волк", "Разъярённый олень", "Кабан", "Медведь"} for enemy in battle["enemies"]))
        self.assertIn("Бой начался", text)


if __name__ == "__main__":
    unittest.main()
