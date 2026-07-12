import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import craft_material_group_service as groups
from services import crafting_service as craft
from services import recipe_constructor_service as recipes


class CraftMaterialGroupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        for env, name in (("CRAFT_MATERIAL_GROUP_PATH", "groups.json"), ("RECIPE_CONSTRUCTOR_PATH", "recipes.json")):
            old = os.environ.get(env); os.environ[env] = str(Path(self.tmp.name) / name)
            self.addCleanup(lambda e=env, v=old: os.environ.pop(e, None) if v is None else os.environ.__setitem__(e, v))

    def test_published_group_matches_category_quality_and_level(self):
        groups.store().create("rare_ore", {"name": "Редкая руда", "categories": ["ore"], "allowed_qualities": ["rare"], "min_item_level": 3})
        groups.store().set_status("rare_ore", "published", force=True)
        self.assertTrue(groups.matches({"item_id": "moon_ore", "category": "ore", "quality": "rare", "item_level": 4}, "rare_ore"))
        self.assertFalse(groups.matches({"item_id": "iron", "category": "ore", "quality": "common", "item_level": 5}, "rare_ore"))

    def test_group_ingredient_is_checked_and_consumed_live(self):
        groups.store().create("any_ore", {"name": "Любая руда", "categories": ["ore"]})
        groups.store().set_status("any_ore", "published", force=True)
        player = {"inventory": [{"item_id": "copper_ore", "category": "ore", "amount": 2}]}
        recipe = {"ingredients": [{"material_group_id": "any_ore", "amount": 2}]}
        self.assertTrue(craft._has_ingredients(player, recipe))
        self.assertTrue(craft._consume_recipe_ingredients(player, recipe, 1))
        self.assertEqual(player["inventory"], [])

    def test_where_used_and_graph_source(self):
        groups.store().create("any_hide", {"name": "Любая кожа", "categories": ["hide"]})
        groups.store().set_status("any_hide", "published", force=True)
        recipes.store().create("boots", {"name": "Ботинки", "workshop": "leatherwork", "output_item_id": "boots", "ingredients": [{"material_group_id": "any_hide", "amount": 2}]})
        self.assertEqual(groups.where_used("any_hide")[0]["id"], "boots")


if __name__ == "__main__":
    unittest.main()
