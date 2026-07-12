import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import disassemble_constructor_service as disassemble
from services import enchant_constructor_service as enchant
from services import upgrade_constructor_service as upgrade
from services import repair_constructor_service as repair
from services.craft_operation_runtime import apply, available_rules


class CraftOperationRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for env, name in (("UPGRADE_CONSTRUCTOR_PATH", "up.json"), ("ENCHANT_CONSTRUCTOR_PATH", "en.json"), ("DISASSEMBLE_CONSTRUCTOR_PATH", "dis.json"), ("REPAIR_CONSTRUCTOR_PATH", "repair.json")):
            old = os.environ.get(env)
            os.environ[env] = str(Path(self.tmp.name) / name)
            self.addCleanup(lambda e=env, v=old: os.environ.pop(e, None) if v is None else os.environ.__setitem__(e, v))

    def test_published_upgrade_consumes_material_and_raises_level(self):
        upgrade.store().create("level_up", {"name": "Усиление", "upgrade_type": "raise_level", "materials": [{"item_id": "ore", "amount": 2}], "success_chance": 100})
        upgrade.store().set_status("level_up", "published", force=True)
        player = {"inventory": [{"item_id": "sword", "amount": 1, "item_level": 2}, {"item_id": "ore", "amount": 2}]}
        result = apply(player, "upgrade", "level_up", 0, rng=Mock(randint=Mock(return_value=1)))
        self.assertTrue(result["ok"])
        self.assertEqual(player["inventory"][0]["item_level"], 3)
        self.assertFalse(any(row.get("item_id") == "ore" for row in player["inventory"]))

    def test_enchant_and_purify_mutate_effects(self):
        enchant.store().create("fire", {"name": "Огонь", "enchant_effect": "fire_edge", "success_chance": 100})
        enchant.store().set_status("fire", "published", force=True)
        enchant.store().create("clean", {"name": "Очистка", "clear_enchant": True, "remove_effect_id": "fire_edge", "success_chance": 100})
        enchant.store().set_status("clean", "published", force=True)
        player = {"inventory": [{"item_id": "sword", "amount": 1, "effect_ids": []}]}
        apply(player, "enchant", "fire", 0, rng=Mock(randint=Mock(return_value=1)))
        self.assertIn("fire_edge", player["inventory"][0]["effect_ids"])
        apply(player, "purify", "clean", 0, rng=Mock(randint=Mock(return_value=1)))
        self.assertNotIn("fire_edge", player["inventory"][0]["effect_ids"])

    def test_disassembly_removes_target_and_grants_outputs(self):
        disassemble.store().create("scrap", {"name": "Разбор", "source_item_id": "sword", "outputs": [{"item_id": "metal_scrap", "amount": 2, "chance": 100}], "output_chance": 100})
        disassemble.store().set_status("scrap", "published", force=True)
        player = {"inventory": [{"item_id": "sword", "amount": 1}]}
        result = apply(player, "disassemble", "scrap", 0, rng=Mock(randint=Mock(return_value=1)))
        self.assertTrue(result["ok"])
        self.assertFalse(any(row.get("item_id") == "sword" for row in player["inventory"]))
        self.assertEqual(next(row for row in player["inventory"] if row.get("item_id") == "metal_scrap")["amount"], 2)

    def test_unpublished_rule_is_rejected(self):
        upgrade.store().create("draft", {"name": "Черновик"})
        with self.assertRaisesRegex(ValueError, "не опубликована"):
            apply({"inventory": [{"item_id": "sword"}]}, "upgrade", "draft", 0)

    def test_player_picker_contains_only_published_compatible_rules(self):
        disassemble.store().create("sword_only", {"name": "Разобрать меч", "source_item_id": "sword", "outputs": ["scrap"]})
        disassemble.store().set_status("sword_only", "published", force=True)
        disassemble.store().create("axe_only", {"name": "Разобрать топор", "source_item_id": "axe", "outputs": ["scrap"]})
        disassemble.store().set_status("axe_only", "published", force=True)
        upgrade.store().create("draft_hidden", {"name": "Черновик"})
        rules = available_rules({"item_id": "sword", "type": "weapon"})
        ids = {row["rule_id"] for row in rules}
        self.assertIn("sword_only", ids)
        self.assertNotIn("axe_only", ids)
        self.assertNotIn("draft_hidden", ids)

    def test_published_repair_restores_configured_durability(self):
        repair.store().create("field_repair", {"name": "Полевой ремонт", "repair_percent": 25, "success_chance": 100})
        repair.store().set_status("field_repair", "published", force=True)
        player = {"inventory": [{"item_id": "sword", "durability": 20, "max_durability": 100}]}
        result = apply(player, "repair", "field_repair", 0, rng=Mock(randint=Mock(return_value=1)))
        self.assertTrue(result["ok"])
        self.assertEqual(player["inventory"][0]["durability"], 45)
        self.assertIn("field_repair", {row["rule_id"] for row in available_rules(player["inventory"][0])})


if __name__ == "__main__":
    unittest.main()
