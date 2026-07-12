import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import formula_constructor_service as formulas


class FormulaRuntimeIntegrationsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.keys = ("FORMULA_CONSTRUCTOR_PATH", "LEVEL_CONSTRUCTOR_PATH", "EXP_CONSTRUCTOR_PATH", "PROFESSION_CONSTRUCTOR_PATH", "FINE_CONSTRUCTOR_PATH", "SKILL_CONSTRUCTOR_PATH", "EFFECT_CONSTRUCTOR_PATH")
        self.old = {key: os.environ.get(key) for key in self.keys}
        for key in self.keys:
            os.environ[key] = str(base / f"{key.lower()}.json")
        self.addCleanup(self.restore)

    def restore(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def publish_formula(self, formula_id, expression):
        formulas.store().create(formula_id, {"name": formula_id, "expression": expression})
        formulas.store().set_status(formula_id, formulas.STATUS_PUBLISHED, force=True)

    def test_published_level_formula_changes_real_threshold(self):
        from services import level_constructor_service as levels
        from services.progression_service import experience_to_next_level
        self.publish_formula("level_curve", "player_level * 250")
        levels.store().create("level_3", {"level": 3, "exp_required": 300, "exp_formula_id": "level_curve"})
        self.assertEqual(experience_to_next_level(3), 300)  # draft level card is not live
        levels.store().set_status("level_3", levels.STATUS_PUBLISHED, force=True)
        self.assertEqual(experience_to_next_level(3), 750)

    def test_profession_formula_grants_xp_and_levels_up(self):
        from services import profession_constructor_service as professions
        from services.crafting_service import _add_craft_experience
        self.publish_formula("profession_gain", "base_amount * 4")
        self.publish_formula("profession_next", "10")
        professions.store().create("smithing", {"name": "Smithing", "profession_type": "smithing", "max_level": 5,
                                                  "exp_formula_id": "profession_gain", "next_level_formula_id": "profession_next"})
        professions.store().set_status("smithing", professions.STATUS_PUBLISHED, force=True)
        player = {"level": 2, "crafting_levels": {"blacksmithing": {"level": 1, "experience": 0}}}
        _add_craft_experience(player, "forge", 1)  # legacy 5, formula -> 20, two thresholds
        self.assertEqual(player["crafting_levels"]["blacksmithing"], {"level": 3, "experience": 0})

    def test_fine_definition_formula_changes_issued_amount(self):
        from services import fine_constructor_service as fines
        from services.fine_service import create_raid_fine
        self.publish_formula("fine_amount", "base_amount + player_level * 10")
        fines.store().create("black_market", {"name": "Raid", "type": "raid", "source": "black_market_raid",
                                               "currency": "copper", "base_amount": 200,
                                               "amount_formula_id": "fine_amount"})
        fines.store().set_status("black_market", fines.STATUS_PUBLISHED, force=True)
        player = {"level": 4}
        fine = create_raid_fine(player, "black_market", now=1)
        self.assertEqual(fine["base_amount"], 240)

    def test_experience_source_formula_changes_gameplay_grant(self):
        from services import exp_constructor_service as sources
        from services.progression_service import grant_experience
        self.publish_formula("mob_xp", "base_amount + mob_level * 3")
        sources.store().create("mob", {"name": "Mob XP", "source_type": "mob_kill", "base_exp": 10,
                                        "formula_id": "mob_xp"})
        sources.store().set_status("mob", sources.STATUS_PUBLISHED, force=True)
        player = {"level": 1, "experience": 0, "total_experience": 0}
        result = grant_experience(player, 20, source_type="mob_kill", context={"mob_level": 4})
        self.assertEqual(result["gained"], 32)

    def test_recipe_item_price_and_delivery_formulas_use_live_resolver(self):
        from services.crafting_service import _recipe_cost_copper
        from services.market_service import _item_formula_price
        from services.courier_service import _item_delivery_values
        self.publish_formula("double", "base_amount * 2")
        player = {"level": 3, "money": 10_000}
        recipe = {"free": False, "price_copper": 25, "cost_formula_id": "double", "output": {"amount": 1}}
        self.assertEqual(_recipe_cost_copper(recipe, player, 3), 150)
        definition = {"price_formula_id": "double", "min_price": 10, "max_price": 500}
        self.assertEqual(_item_formula_price(definition, 80, player=player), 160)
        delivery_definition = {"delivery_allowed": True, "delivery_cost_formula_id": "double",
                               "delivery_time_formula_id": "double"}
        planned = [(0, 2, {"item_id": "parcel_item", "name": "Parcel", "amount": 2})]
        with patch("services.item_registry.get_item_definition_by_id", return_value=delivery_definition):
            self.assertEqual(_item_delivery_values(planned, player, 100, 600), (200, 1200))

    def test_published_skill_overlays_catalog_and_formulas_change_combat_values(self):
        from services import skill_constructor_service as skills
        from services.active_skill_service import catalog_skill_by_id, runtime_skill_from_catalog, resource_cost_with_modifiers, skill_learning_cost, skill_upgrade_cost
        from services.derived_stats_service import calculate_player_skill_raw_damage
        self.publish_formula("skill_cost", "base_amount + player_level")
        self.publish_formula("skill_damage", "player_level * 10")
        self.publish_formula("skill_scale", "base_amount * 2")
        skills.store().create("live_strike", {"name": "Live strike", "skill_type": "active", "branch": "neutral", "path": "none",
                                               "resource_type": "spirit", "resource_cost": 5, "damage_type": "physical",
                                               "target_mode": "single_enemy", "weapon_requirements": ["any"],
                                               "use_cost_formula_id": "skill_cost", "damage_formula_id": "skill_damage",
                                               "level_power_formula_id": "skill_scale", "learn_cost_skill_points": 2,
                                               "learn_cost_formula_id": "skill_scale", "upgrade_cost_formula_id": "skill_scale"})
        skills.store().set_status("live_strike", skills.STATUS_PUBLISHED, force=True)
        catalog = catalog_skill_by_id("live_strike")
        self.assertTrue(catalog["constructor_live"])
        runtime = runtime_skill_from_catalog(catalog)
        player = {"level": 3, "strength": 1, "agility": 1, "perception": 1, "endurance": 1,
                  "intelligence": 1, "wisdom": 1, "skills": {"passive": []}, "inventory": []}
        self.assertEqual(resource_cost_with_modifiers(runtime, player), (8, 0))
        self.assertEqual(skill_learning_cost(player, runtime), 4)
        self.assertEqual(skill_upgrade_cost(player, runtime, 3), 6)
        damage = calculate_player_skill_raw_damage(player, runtime)
        self.assertEqual(damage["damage"], 60)

    def test_item_use_drop_and_repair_formulas(self):
        from services.item_formula_runtime import use_result, drop_chance, repair_cost, repair_inventory_item
        self.publish_formula("item_use", "base_amount + player_level")
        self.publish_formula("item_drop", "base_chance / 2")
        self.publish_formula("item_repair", "difficulty * 3")
        definition = {"id": "formula_item", "item_level": 2, "max_durability": 100, "can_be_repaired": True,
                      "use_formula_id": "item_use", "drop_chance_formula_id": "item_drop",
                      "repair_cost_formula_id": "item_repair"}
        with patch("services.item_formula_runtime.get_item_definition_by_id", return_value=definition):
            self.assertEqual(use_result("formula_item", {"level": 4}, 10), 14)
            self.assertEqual(drop_chance("formula_item", 80), 40)
            self.assertEqual(repair_cost("formula_item", current_durability=70), 90)
            item = {"item_id": "formula_item", "durability": 70}
            player = {"money": 100}
            self.assertEqual(repair_inventory_item(player, item), {"cost": 90, "before": 70, "after": 100})
            self.assertEqual((player["money"], item["durability"]), (10, 100))

    def test_effect_value_duration_chance_and_stack_limit_formulas(self):
        from services import effect_constructor_service as effects
        from services.effect_formula_runtime import resolve, apply_to_player
        self.publish_formula("effect_double", "base_amount * 2")
        effects.store().create("formula_effect", {"effect_name": "Formula effect", "effect_type": "stat_modifier",
                                                   "source_type": "quest", "target": "self", "active_when": "always",
                                                   "stack_rule": "stack_limited", "stat": "strength", "flat_bonus": 5,
                                                   "value_formula_id": "effect_double", "duration_seconds": 10,
                                                   "duration_formula_id": "effect_double", "apply_chance_percent": 50,
                                                   "chance_formula_id": "effect_double", "max_stacks": 1,
                                                   "limit_formula_id": "effect_double"})
        effects.store().set_status("formula_effect", effects.STATUS_PUBLISHED, force=True)
        resolved = resolve("formula_effect", player={"level": 1})
        self.assertEqual((resolved["value"], resolved["flat_bonus"], resolved["duration_seconds"],
                          resolved["apply_chance_percent"], resolved["max_stacks"]), (10, 10, 20, 100, 2))
        player = {"active_effects": []}
        for _ in range(3):
            self.assertIsNotNone(apply_to_player(player, "formula_effect"))
        self.assertEqual(len(player["active_effects"]), 2)
        self.assertTrue(all(row.get("expires_at") for row in player["active_effects"]))
