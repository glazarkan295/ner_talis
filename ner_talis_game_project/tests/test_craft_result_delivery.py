import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.craft_result_delivery import can_place, claim, place
from services.inventory_service import build_inventory_item
from services.crafting_service import _apply_recipe_result_settings
from unittest.mock import patch


class CraftResultDeliveryTest(unittest.TestCase):
    def test_reject_detects_full_regular_inventory(self):
        player = {"inventory_capacity": 1, "inventory": [{"item_id": "occupied", "amount": 1, "stackable": False}]}
        item = build_inventory_item("Меч", 1, item_id="sword", max_stack=1)
        self.assertFalse(can_place(player, item, 1, "reject"))
        self.assertEqual(len(player["inventory"]), 1)

    def test_delivery_mode_keeps_result_outside_inventory_until_claim(self):
        player = {"inventory_capacity": 2, "inventory": []}
        item = build_inventory_item("Меч", 1, item_id="sword", max_stack=1)
        result, delivered = place(player, item, 1, mode="delivery")
        self.assertIsNone(result)
        self.assertEqual(delivered, 1)
        self.assertEqual(player["inventory"], [])
        claimed = claim(player)
        self.assertEqual(claimed, {"claimed": 1, "remaining": 0})
        self.assertEqual(player["inventory"][0]["item_id"], "sword")

    def test_completed_overflow_result_is_never_silently_discarded(self):
        player = {"inventory_capacity": 1, "inventory": [{"item_id": "occupied", "amount": 1, "stackable": False}]}
        item = build_inventory_item("Меч", 1, item_id="sword", max_stack=1)
        result, delivered = place(player, item, 1, mode="overload")
        self.assertEqual(result.discarded, 0)
        self.assertEqual(delivered, 1)
        self.assertEqual(player["craft_delivery_inbox"][0]["amount"], 1)

    def test_partial_mode_may_leave_remainder_unissued_by_design(self):
        player = {"inventory_capacity": 1, "inventory": [{"item_id": "occupied", "amount": 1, "stackable": False}]}
        item = build_inventory_item("Меч", 1, item_id="sword", max_stack=1)
        result, delivered = place(player, item, 1, mode="partial")
        self.assertEqual((result.added, result.discarded, delivered), (0, 1, 0))

    def test_recipe_result_settings_apply_quality_binding_effect_and_handedness(self):
        item = {"item_id": "blade", "quality": "rare", "can_be_two_handed": True, "two_handed": False}
        recipe = {"result_quality": "rare", "critical_quality_upgrade": True, "result_level": 7,
                  "bind_on_create": True, "unique_result": True, "crafted_handedness": "two_handed",
                  "result_effects": ["flame"]}
        with patch("services.crafting_service.random.randint", return_value=1):
            result = _apply_recipe_result_settings(item, recipe, critical=True)
        self.assertEqual(result["quality"], "epic")
        self.assertEqual(result["item_level"], 7)
        self.assertTrue(result["bound"] and result["unique"] and result["two_handed"])
        self.assertIn("flame", result["effect_ids"])


if __name__ == "__main__":
    unittest.main()
