import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.inventory_service import apply_generated_item_level_and_price, calculate_generated_item_sell_price, is_levelled_equipment_item
from services.item_registry import build_inventory_item
from services.registration_service import create_player, load_races
from site_api import frontend_profile, validate_equipment_level_requirement


class FixedRng:
    def __init__(self, value):
        self.value = value

    def randint(self, _left, _right):
        return self.value


class ItemLevelPriceRulesTest(unittest.TestCase):
    def _player(self, level=25):
        return {"level": level}

    def test_only_weapon_equipment_and_jewelry_get_generated_level(self):
        player = self._player(25)
        weapon = build_inventory_item("Простой меч", 1, item_id="simple_sword")
        resource = build_inventory_item("Медный слиток", 1, item_id="copper_ingot")
        ring = build_inventory_item("Грубое медное кольцо", 1, item_id="rough_copper_ring")

        self.assertTrue(is_levelled_equipment_item(weapon))
        self.assertTrue(is_levelled_equipment_item(ring))
        self.assertFalse(is_levelled_equipment_item(resource))

        apply_generated_item_level_and_price(player, weapon, "crafted", rng=FixedRng(3))
        apply_generated_item_level_and_price(player, ring, "crafted", rng=FixedRng(0))
        apply_generated_item_level_and_price(player, resource, "crafted", rng=FixedRng(0))

        self.assertEqual(weapon["level"], 22)
        self.assertEqual(weapon["required_level"], 22)
        self.assertEqual(ring["level"], 25)
        self.assertNotIn("level", resource)
        self.assertNotIn("required_level", resource)

    def test_found_equipment_level_rolls_plus_minus_twenty(self):
        player = self._player(25)
        weapon = build_inventory_item("Простой меч", 1, item_id="simple_sword")

        apply_generated_item_level_and_price(player, weapon, "found", rng=FixedRng(17))

        self.assertEqual(weapon["level"], 42)
        self.assertEqual(weapon["generation_type"], "found")

    def test_sell_price_depends_on_quality_level_and_set_membership(self):
        item = build_inventory_item("Простой меч", 1, item_id="simple_sword")
        item["quality"] = "редкий"
        item["set_id"] = "demo_set"
        item["base_sell_price_copper"] = 100
        item["level"] = 25

        # rare floor 500, level multiplier 1 + 24*0.02, set multiplier 1.25
        self.assertEqual(calculate_generated_item_sell_price(item), 925)

    def test_equipment_level_requirement_allows_player_level_plus_three_only(self):
        player = self._player(10)
        allowed = build_inventory_item("Простой меч", 1, item_id="simple_sword")
        allowed["level"] = 13
        blocked = build_inventory_item("Простой меч", 1, item_id="simple_sword")
        blocked["level"] = 14

        validate_equipment_level_requirement(player, allowed)
        with self.assertRaises(HTTPException) as ctx:
            validate_equipment_level_requirement(player, blocked)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("слишком высок", ctx.exception.detail)

    def test_frontend_profile_does_not_show_level_for_non_equipment(self):
        player = create_player(
            game_id="NT-LEVEL-PROFILE",
            platform="telegram",
            external_user_id="111",
            name="Уровни",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["inventory"] = [
            build_inventory_item("Медный слиток", 1, item_id="copper_ingot"),
            {**build_inventory_item("Простой меч", 1, item_id="simple_sword"), "level": 5},
        ]

        profile = frontend_profile(player)
        items = {item["item_id"]: item for item in profile["inventory"]}

        self.assertNotIn("level", items["copper_ingot"])
        self.assertEqual(items["simple_sword"]["level"], 5)


if __name__ == "__main__":
    unittest.main()
