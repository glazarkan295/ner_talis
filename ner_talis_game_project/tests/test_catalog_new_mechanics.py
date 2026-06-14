import copy
import os
import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.item_registry import get_item_definition_by_id
from services.derived_stats_service import calculate_player_derived_stats
from services.inventory_service import max_regular_slots
from services import market_service as ms
from services import pve_battle_service as pve
import site_api


def _player():
    return {
        "level": 20,
        "stats": {k: 30 for k in ("strength", "endurance", "dexterity", "perception", "intelligence", "wisdom")},
        "inventory": [],
        "equipment": {},
        "active_effects": [],
    }


class CatalogNewMechanicsTest(unittest.TestCase):
    def test_mana_crystal_buffs_max_mana_and_lowers_others(self):
        base = calculate_player_derived_stats(copy.deepcopy(_player()))
        crystal = get_item_definition_by_id("mana_crystal")
        self.assertTrue(site_api.is_inventory_item_usable(crystal))
        effect = site_api.resource_crystal_effect_from_item(crystal)
        p = _player()
        p["active_effects"] = [effect]
        buffed = calculate_player_derived_stats(p)
        self.assertGreater(buffed["max_mana"], base["max_mana"])
        self.assertLess(buffed["max_hp"], base["max_hp"])
        self.assertLess(buffed["max_spirit"], base["max_spirit"])

    def test_inventory_pocket_adds_slots_up_to_cap(self):
        simple = get_item_definition_by_id("simple_inventory_pocket")
        p = {"inventory_capacity": 20}
        base = max_regular_slots(p)
        for _ in range(5):
            ok, _msg = site_api.apply_inventory_pocket(p, simple)
            self.assertTrue(ok)
        self.assertEqual(max_regular_slots(p), base + 5)
        ok, _msg = site_api.apply_inventory_pocket(p, simple)
        self.assertFalse(ok)  # cap reached
        excellent = get_item_definition_by_id("excellent_inventory_pocket")
        ok, _msg = site_api.apply_inventory_pocket(p, excellent)
        self.assertTrue(ok)  # higher tier raises cap
        self.assertEqual(max_regular_slots(p), base + 6)

    def test_professional_quiver_capacity_60(self):
        from services.item_registry import registry_item_to_inventory_item
        quiver = registry_item_to_inventory_item(get_item_definition_by_id("professional_arrow_quiver"), 1)
        player = {"equipment": {"weapon1": {"id": "bow", "subtype": "bow"}, "weapon2": quiver}, "inventory": []}
        loaded, _msg = site_api.load_ammo_into_quiver(player, {"id": "arrow_for_bow", "item_id": "arrow_for_bow"}, 60)
        self.assertEqual(loaded, 60)
        self.assertEqual(player["equipment"]["weapon2"]["ammo_count"], 60)

    def test_lucky_buyer_artifact_npc_price_modifiers(self):
        lucky = get_item_definition_by_id("artifact_lucky_buyer")
        p = {"equipment": {"special": lucky}, "stats": {}}
        self.assertEqual(ms._npc_buy_discount_percent(p), 10)
        self.assertEqual(ms._npc_sell_bonus_percent(p), 10)
        self.assertEqual(ms._discounted_buy_price(p, 1000), 900)

    def test_last_chance_artifact_resurrects_once(self):
        last = get_item_definition_by_id("one_time_artifact_last_chance")
        player = {"equipment": {"special": dict(last)}, "max_hp": 400, "max_mana": 100, "max_spirit": 100, "level": 10}
        battle = {"player_state": {"max_hp": 400, "current_hp": 0, "max_mana": 100, "current_mana": 0, "max_spirit": 100, "current_spirit": 0}, "round_number": 3}
        text, _buttons = pve.finish_player_defeat(player, battle, [])
        self.assertIn("Последнего Шанса", text)
        self.assertEqual(battle["player_state"]["current_hp"], 400)
        self.assertEqual(battle["player_state"].get("invulnerable_turns"), 1)
        self.assertNotIn("special", player.get("equipment", {}))
        # second defeat (artifact gone) is a real defeat
        pve.finish_player_defeat(player, battle, [])
        self.assertFalse(player.get("in_battle"))

    def test_iron_armor_resistance_aggregates(self):
        from services.derived_stats_service import all_bonus_modifiers
        chest = copy.deepcopy(get_item_definition_by_id("simple_iron_chestpiece"))
        chest["stat_modifiers"] = {"armor": 2, "bonus_bleed_resist_chance": 6}
        p = {"equipment": {"chest": chest}, "stats": {}}
        mods = all_bonus_modifiers(p)
        self.assertEqual(mods.get("bonus_bleed_resist_chance"), 6)


if __name__ == "__main__":
    unittest.main()
