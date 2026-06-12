import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.item_registry import get_item_definition_by_id

DATA_DIR = ROOT_DIR.parent / "data"


class OrdinaryForestBurrowItemsTest(unittest.TestCase):
    def test_burrow_equipment_definitions_are_uncommon_and_scaled(self):
        gloves = get_item_definition_by_id("old_gloves")
        belt = get_item_definition_by_id("decent_belt")
        self.assertEqual(gloves["name_ru"], "Старые перчатки (необычные)")
        self.assertEqual(gloves["quality"], "uncommon")
        self.assertEqual(gloves["sell_price_copper"], 300)
        self.assertIn("found_level_effect_scaling", gloves)
        self.assertEqual(belt["name_ru"], "Неплохой пояс (необычные)")
        self.assertEqual(belt["quality"], "uncommon")
        self.assertEqual(belt["sell_price_copper"], 300)
        self.assertEqual(belt["stat_modifiers"]["inventory_slots_bonus"], 2)

    def test_burrow_table_weights_match_design(self):
        data = json.loads((DATA_DIR / "ordinary_forest.json").read_text(encoding="utf-8"))
        table = data["resource_find_tables"]["small_burrow"]
        self.assertEqual([12, 36, 12, 40], [entry["weight"] for entry in table])


if __name__ == "__main__":
    unittest.main()
