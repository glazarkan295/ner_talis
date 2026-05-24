import math
import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.derived_stats_service import calculate_player_derived_stats
from services.inventory_service import add_inventory_item
from services.item_registry import build_inventory_item
from services.pve_battle_models import EnemyRank
from services.pve_battle_service import build_enemy, create_hilly_meadows_battle, grant_battle_rewards, loot_parameters_for_rank
from services.registration_service import create_player, load_races


class DeathBalanceStackRulesTest(unittest.TestCase):
    def make_player(self, level: int = 1):
        return create_player("NT-RULES", "telegram", "111", "Проверка", "human", load_races()) | {"level": level}

    def test_magic_defense_uses_new_formula_and_battle_state_matches_profile_stats(self):
        player = self.make_player()
        player.update(
            {
                "level": 12,
                "wisdom": 14,
                "intelligence": 11,
                "endurance": 9,
                "armor": 6,
                "magic_armor": 999,  # no longer replaces the new magic-defense formula
                "bonus_magic_defense": 5,
            }
        )
        stats = calculate_player_derived_stats(player)
        expected = math.ceil((stats["armor"] * 1.5) + (stats["wisdom"] * 0.9) + (stats["intelligence"] * 0.6) + (stats["endurance"] * 0.2) + 5)
        self.assertEqual(stats["magic_defense"], expected)

        battle, _ = create_hilly_meadows_battle(player, rng=random.Random(2))
        for key in ("max_hp", "max_spirit", "max_mana", "armor", "magic_armor", "physical_defense", "magic_defense", "accuracy", "dodge"):
            self.assertEqual(battle["player_state"][key], stats[key])

    def test_enemy_battle_parameters_are_calculated_from_rank_level_and_template(self):
        enemy = build_enemy("hill_bull", EnemyRank.ELITE, level=5, index=1, location_id="hilly_meadows")
        mult = 1.6
        expected_armor = math.ceil(5 * 2.6 * mult)
        expected_physical = math.ceil(expected_armor * 1.5 + 5 * 1.4 * mult)
        expected_magic = math.ceil(5 * 0.8 * mult)
        self.assertEqual(enemy.armor, expected_armor)
        self.assertEqual(enemy.physical_defense, expected_physical)
        self.assertEqual(enemy.magic_defense, expected_magic)
        self.assertGreater(enemy.accuracy, 0)
        self.assertGreater(enemy.dodge, 0)

    def test_level_ten_mob_experience_gets_additional_thirty_percent_reduction(self):
        player = self.make_player(level=10)
        player["race_id"] = "elf"
        battle = {"enemies": [{"name": "Тестовый моб", "level": 10, "rank": "normal", "current_hp": 0, "max_hp": 1}]}
        rewards = grant_battle_rewards(player, battle, rng=random.Random(1))
        self.assertIn("Опыт: +78", rewards)
        self.assertEqual(player["experience"], 78)

    def test_elite_loot_has_higher_chance_and_amount(self):
        self.assertEqual(loot_parameters_for_rank(EnemyRank.ELITE, 20, 1, 1), (30, 2, 2))
        self.assertEqual(loot_parameters_for_rank(EnemyRank.NORMAL, 20, 1, 1), (20, 1, 1))

    def test_inventory_stack_limits_split_full_stacks_into_new_slots(self):
        player = {"inventory_capacity": 20, "inventory": []}
        add_inventory_item(player, "Чистая вода", 25, item_id="clean_water")
        water_stacks = [item["amount"] for item in player["inventory"] if item.get("item_id") == "clean_water"]
        self.assertEqual(water_stacks, [20, 5])

        add_inventory_item(player, "Старый нож", 21, item_id="old_knife")
        knife_stacks = [item["amount"] for item in player["inventory"] if item.get("item_id") == "old_knife"]
        self.assertEqual(knife_stacks, [20, 1])

    def test_item_card_types_are_normalized(self):
        self.assertEqual(build_inventory_item("Куски ткани", item_id="fabric_pieces")["type"], "Хлам")
        self.assertEqual(build_inventory_item("Старый нож", item_id="old_knife")["type"], "Хлам")
        self.assertEqual(build_inventory_item("Железный лом", item_id="iron_scrap")["type"], "Хлам")
        self.assertEqual(build_inventory_item("Маленькая шкурка", item_id="small_pelt")["type"], "Шкура")
        self.assertEqual(build_inventory_item("Серебристая ромашка", item_id="silver_chamomile")["type"], "Цветы")


if __name__ == "__main__":
    unittest.main()
