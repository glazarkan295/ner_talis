import random
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT_DIR.parent
for path in (ROOT_DIR, PROJECT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services.active_skill_service import (
    consume_skill_ammo,
    runtime_skill_from_catalog,
    validate_skill_ammo,
)
from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item
from services.pve_battle_service import create_location_battle, handle_battle_action
from services.registration_service import create_player, load_races
from services.web_profile import PROFILE_SCOPE, create_profile_site_link
from site_api import create_profile_api_router, frontend_profile
from storage.json_storage import JsonStorage


def bow_test_skill(skill_id: str = "test_aimed_shot", consume_per_use: int = 1) -> dict:
    return {
        "id": skill_id,
        "name": "Учебный выстрел",
        "resource_branch": "neutral",
        "resource": "none",
        "base_resource_cost": 0,
        "damage_type": "physical",
        "targeting": "single_enemy",
        "weapon_requirements": ["bow"],
        "ammo_requirements": {
            "enabled": True,
            "requirements_by_weapon": {
                "bow": {
                    "ammo_item_id": "arrow_for_bow",
                    "ammo_name": "стрела",
                    "ammo_short_name": "стрела",
                    "consume_per_use": consume_per_use,
                    "quiver_requirement": {
                        "quiver_slot": "arrow_quiver",
                        "quiver_kind": "arrow",
                    },
                    "missing_message": "Нужны стрелы для лука.",
                    "missing_quiver_message": "Нужен колчан для стрел лука.",
                    "missing_loaded_ammo_message": "В колчане нет стрел.",
                }
            },
        },
    }


class AmmoQuiverIntegrationTest(unittest.TestCase):
    def make_player(self):
        races = load_races("data/races.json")
        player = create_player("NT-AMMO", "telegram", "111", "Стрелок", "human", races)
        player["equipment"] = {
            "weapon1": {
                "id": "test_bow",
                "name": "Учебный лук",
                "type": "Оружие",
                "subtype": "Лук",
                "weapon_type": "bow",
                "slotKey": "weapon1",
                "two_handed": True,
            }
        }
        return player

    def test_custom_bow_skill_contains_ammo_and_quiver_rules(self):
        skill = bow_test_skill("test_arrow_rain", 3)
        ammo = skill.get("ammo_requirements")
        self.assertTrue(ammo.get("enabled"))
        bow_rule = ammo["requirements_by_weapon"]["bow"]
        self.assertEqual(bow_rule["ammo_item_id"], "arrow_for_bow")
        self.assertEqual(bow_rule["quiver_requirement"]["quiver_slot"], "arrow_quiver")
        self.assertEqual(bow_rule["consume_per_use"], 3)

    def test_bow_skill_requires_equipped_loaded_arrow_quiver(self):
        player = self.make_player()
        skill = runtime_skill_from_catalog(bow_test_skill())

        ok, message = validate_skill_ammo(player, skill)
        self.assertFalse(ok)
        self.assertIn("колчан", message.casefold())

        player["equipment"]["weapon2"] = {
            "id": "arrow_quiver_empty",
            "name": "Пустой колчан для стрел лука",
            "slotKey": "weapon2",
            "ammo_item_id": "arrow_for_bow",
            "ammo_count": 0,
            "capacity": 30,
        }
        ok, message = validate_skill_ammo(player, skill)
        self.assertFalse(ok)
        self.assertIn("стрел", message.casefold())

        player["equipment"]["weapon2"]["ammo_count"] = 2
        ok, message = consume_skill_ammo(player, skill)
        self.assertTrue(ok)
        self.assertIn("×1", message)
        self.assertEqual(player["equipment"]["weapon2"]["ammo_count"], 1)

    def test_profile_use_loads_arrows_into_equipped_quiver(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "players.json"
            storage = JsonStorage(db_path)
            player = self.make_player()
            player["equipment"]["weapon2"] = registry_item_to_inventory_item(get_item_definition_by_id("arrow_quiver_empty"), 1)
            player["equipment"]["weapon2"]["slotKey"] = "weapon2"
            player["inventory"] = [registry_item_to_inventory_item(get_item_definition_by_id("arrow_for_bow"), 12)]
            storage.save_new_player(player, "telegram", "111")
            link = create_profile_site_link(storage, player, "telegram")
            token = link.split("token=", 1)[1].split("&", 1)[0]

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)
            response = client.post(f"/api/profile/{token}/inventory/use", json={"item_id": "arrow_for_bow"})

            self.assertEqual(response.status_code, 200, response.text)
            updated = storage.get_player_by_game_id("NT-AMMO")
            self.assertEqual(updated["equipment"]["weapon2"]["ammo_count"], 12)
            self.assertEqual(updated.get("inventory", []), [])
            profile = frontend_profile(updated)
            quiver = profile["equipment"]["weapon2"]
            self.assertTrue(any("12/30" in str(line) for line in quiver["stats"]))

    def test_profile_equip_quiver_requires_matching_weapon1(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "players.json"
            storage = JsonStorage(db_path)
            player = self.make_player()
            player["inventory"] = [registry_item_to_inventory_item(get_item_definition_by_id("arrow_quiver_empty"), 1)]
            storage.save_new_player(player, "telegram", "111")
            link = create_profile_site_link(storage, player, "telegram")
            token = link.split("token=", 1)[1].split("&", 1)[0]

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)
            response = client.post(f"/api/profile/{token}/equipment/equip", json={"item_id": "arrow_quiver_empty", "slot_key": "weapon2"})

            self.assertEqual(response.status_code, 200, response.text)
            updated = storage.get_player_by_game_id("NT-AMMO")
            self.assertEqual(updated["equipment"]["weapon2"]["id"], "arrow_quiver_empty")

    def test_profile_rejects_quiver_without_matching_weapon1(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "players.json"
            storage = JsonStorage(db_path)
            player = self.make_player()
            player["equipment"]["weapon1"] = {"id": "test_sword", "name": "Учебный меч", "weapon_type": "sword", "slotKey": "weapon1"}
            player["inventory"] = [registry_item_to_inventory_item(get_item_definition_by_id("arrow_quiver_empty"), 1)]
            storage.save_new_player(player, "telegram", "111")
            link = create_profile_site_link(storage, player, "telegram")
            token = link.split("token=", 1)[1].split("&", 1)[0]

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)
            response = client.post(f"/api/profile/{token}/equipment/equip", json={"item_id": "arrow_quiver_empty", "slot_key": "weapon2"})

            self.assertEqual(response.status_code, 400)
            self.assertIn("лук", response.text.lower())

    def test_changing_weapon1_removes_incompatible_quiver(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "players.json"
            storage = JsonStorage(db_path)
            player = self.make_player()
            player["equipment"]["weapon2"] = registry_item_to_inventory_item(get_item_definition_by_id("arrow_quiver_empty"), 1)
            player["equipment"]["weapon2"]["slotKey"] = "weapon2"
            player["inventory"] = [{"id": "test_sword", "name": "Учебный меч", "type": "Оружие", "weapon_type": "sword", "slot": "weapon", "targetSlotKey": "weapon1"}]
            storage.save_new_player(player, "telegram", "111")
            link = create_profile_site_link(storage, player, "telegram")
            token = link.split("token=", 1)[1].split("&", 1)[0]

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)
            response = client.post(f"/api/profile/{token}/equipment/equip", json={"item_id": "test_sword", "slot_key": "weapon1"})

            self.assertEqual(response.status_code, 200, response.text)
            updated = storage.get_player_by_game_id("NT-AMMO")
            self.assertNotIn("weapon2", updated["equipment"])
            self.assertTrue(any(item.get("id") == "arrow_quiver_empty" for item in updated.get("inventory", [])))

    def test_pve_skill_consumes_arrow_from_quiver_before_hit_roll(self):
        player = self.make_player()
        player["equipment"]["weapon2"] = {
            "id": "arrow_quiver_empty",
            "name": "Пустой колчан для стрел лука",
            "slotKey": "weapon2",
            "ammo_item_id": "arrow_for_bow",
            "ammo_count": 1,
            "capacity": 30,
        }
        skill = runtime_skill_from_catalog(bow_test_skill())
        player["skills"]["equipped"] = [skill]
        create_location_battle(player, random.Random(1), "hilly_meadows")

        text, buttons = handle_battle_action(player, "Учебный выстрел", random.Random(1))

        self.assertEqual(player["equipment"]["weapon2"]["ammo_count"], 1)
        self.assertIn("Выберите действие боя", text)


if __name__ == "__main__":
    unittest.main()
