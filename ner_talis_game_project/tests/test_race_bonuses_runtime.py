import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.pve_battle_models import DamageType, calculate_final_damage
from services.pve_battle_service import calculate_player_derived_stats, player_attack_raw_damage
from services.race_bonus_service import (
    DWARF_GEM_DROP_POOL,
    alchemy_ingredient_refund,
    combat_hp_regen_percent,
    crafting_extra_effect_triggered,
    effect_resistance_bonus_percent,
    extra_alchemy_ingredient_chance_percent,
    incoming_periodic_damage_multiplier,
    incoming_physical_damage_multiplier,
    mining_gem_drop,
    npc_purchase_refund_amount,
    search_event_weights,
)


class _AlwaysHitRng:
    """RNG stub: uniform() returns 0 (always under any positive %), randint min."""

    def uniform(self, a, b):
        return 0.0

    def randint(self, a, b):
        return a

    def choice(self, seq):
        return seq[0]


class _NeverHitRng:
    def uniform(self, a, b):
        return 100.0

    def randint(self, a, b):
        return a

    def choice(self, seq):
        return seq[0]


class RaceBonusRuntimeTests(unittest.TestCase):
    def make_player(self, race_id: str) -> dict:
        return {
            "race_id": race_id,
            "level": 1,
            "stats": {
                "strength": 250,
                "dexterity": 250,
                "endurance": 250,
                "intelligence": 250,
                "wisdom": 250,
                "perception": 250,
            },
            "invested_stats": {},
            "stat_bonuses": {},
            "equipment": {},
        }

    def test_human_bonuses_work(self):
        human = self.make_player("human")
        other = self.make_player("elf")

        self.assertGreater(calculate_player_derived_stats(human)["strength"], calculate_player_derived_stats(other)["strength"])
        self.assertEqual(npc_purchase_refund_amount(human, 1000, random.Random(31)), 30)
        self.assertEqual(npc_purchase_refund_amount(other, 1000, random.Random(31)), 0)

    def test_elf_bonuses_work(self):
        elf = self.make_player("elf")
        human = self.make_player("human")

        elf_damage, elf_type, _ = player_attack_raw_damage(elf, "Магический сгусток")
        human_damage, human_type, _ = player_attack_raw_damage(human, "Магический сгусток")
        self.assertEqual(elf_type, DamageType.MAGIC)
        self.assertEqual(human_type, DamageType.MAGIC)
        self.assertGreater(elf_damage, human_damage)
        self.assertEqual(extra_alchemy_ingredient_chance_percent(elf), 3)

        # Чутьё зельевара: возвращает часть ингредиентов (qty>=2 участвуют).
        ingredients = [("water", 3), ("clover", 5), ("fat", 1)]
        refund = alchemy_ingredient_refund(elf, ingredients, 1, rng=_AlwaysHitRng())
        self.assertIn("water", refund)
        self.assertIn("clover", refund)
        self.assertNotIn("fat", refund)  # qty 1 не участвует
        self.assertTrue(1 <= refund["water"] <= 2)
        # Не-эльфы и никогда-срабатывающий rng ничего не возвращают.
        self.assertEqual(alchemy_ingredient_refund(human, ingredients, 1, rng=_AlwaysHitRng()), {})
        self.assertEqual(alchemy_ingredient_refund(elf, ingredients, 1, rng=_NeverHitRng()), {})

        base = [("alchemy_ingredient", 25), ("stone_or_ore", 17), ("berries", 20), ("trap", 10), ("glint", 8), ("battle", 20)]
        adjusted = dict(search_event_weights(elf, base))
        self.assertGreater(adjusted["alchemy_ingredient"], 25)

    def test_dwarf_bonuses_work(self):
        dwarf = self.make_player("dwarf")
        human = self.make_player("human")

        self.assertGreater(calculate_player_derived_stats(dwarf)["endurance"], calculate_player_derived_stats(human)["endurance"])
        # Каменное чутьё: 4% шанс камня при добыче руды.
        self.assertIn(mining_gem_drop(dwarf, _AlwaysHitRng()), DWARF_GEM_DROP_POOL)
        self.assertIsNone(mining_gem_drop(dwarf, _NeverHitRng()))
        self.assertIsNone(mining_gem_drop(human, _AlwaysHitRng()))
        # Мастерская закалка: +1 эффект на оружии/броне (по навыку).
        self.assertTrue(crafting_extra_effect_triggered(dwarf, "blacksmithing", _AlwaysHitRng()))
        self.assertTrue(crafting_extra_effect_triggered(dwarf, "leatherworking", _AlwaysHitRng()))
        self.assertFalse(crafting_extra_effect_triggered(dwarf, "alchemy", _AlwaysHitRng()))
        self.assertFalse(crafting_extra_effect_triggered(human, "blacksmithing", _AlwaysHitRng()))

    def test_undead_bonuses_work(self):
        undead = self.make_player("undead")
        human = self.make_player("human")

        self.assertGreater(calculate_player_derived_stats(undead)["max_hp"], calculate_player_derived_stats(human)["max_hp"])
        self.assertEqual(effect_resistance_bonus_percent(undead, "poison"), 5)
        self.assertEqual(incoming_periodic_damage_multiplier(undead), 0.97)
        self.assertEqual(effect_resistance_bonus_percent(human, "poison"), 0)

    def test_lizardfolk_bonuses_work(self):
        lizard = self.make_player("lizardfolk")
        physical = calculate_final_damage(
            raw_damage=50,
            damage_type=DamageType.PHYSICAL,
            target_physical_defense=0,
            target_magic_defense=0,
            target_soft_level=1,
        )
        self.assertEqual(round(physical * incoming_physical_damage_multiplier(lizard)), 49)
        self.assertEqual(combat_hp_regen_percent(lizard), 0.5)

        base = [("alchemy_ingredient", 25), ("stone_or_ore", 17), ("berries", 20), ("trap", 10), ("glint", 8), ("battle", 20)]
        adjusted = dict(search_event_weights(lizard, base))
        self.assertGreater(adjusted["stone_or_ore"], 17)
        self.assertLess(adjusted["battle"], 20)


if __name__ == "__main__":
    unittest.main()
