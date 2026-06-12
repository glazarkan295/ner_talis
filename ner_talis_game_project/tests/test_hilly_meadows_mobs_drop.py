import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.pve_battle_models import EnemyRank
from services.pve_battle_service import (
    BATTLE_LOOT_ITEM_IDS,
    HILLY_MEADOWS_MOBS,
    choose_mob_key,
    create_location_battle,
    loot_parameters_for_rank,
)


class HillyMeadowsMobsDropTest(unittest.TestCase):
    def test_hilly_meadows_mob_catalog_has_expected_mobs_and_loot(self):
        self.assertEqual(
            {"overgrown_gopher", "wild_jackal", "rabid_rabbit", "hill_bull"},
            set(HILLY_MEADOWS_MOBS),
        )
        for mob_key, mob in HILLY_MEADOWS_MOBS.items():
            self.assertTrue(mob.get("loot"), mob_key)
            for item_name, chance, min_amount, max_amount in mob["loot"]:
                self.assertIn(item_name, BATTLE_LOOT_ITEM_IDS["hilly_meadows"])
                self.assertGreaterEqual(chance, 1)
                self.assertLessEqual(chance, 100)
                self.assertGreaterEqual(min_amount, 1)
                self.assertGreaterEqual(max_amount, min_amount)

    def test_hilly_meadows_mob_selection_keeps_bull_out_of_normal_pool(self):
        normal_seen = {choose_mob_key(EnemyRank.NORMAL, random.Random(seed), 20, "hilly_meadows") for seed in range(80)}
        self.assertLessEqual(normal_seen, {"overgrown_gopher", "wild_jackal", "rabid_rabbit"})
        self.assertNotIn("hill_bull", normal_seen)

        elite_seen = {choose_mob_key(EnemyRank.ELITE, random.Random(seed), 20, "hilly_meadows") for seed in range(10)}
        self.assertEqual({"hill_bull"}, elite_seen)

    def test_hilly_meadows_battle_uses_hilly_location_and_enemy_data(self):
        player = {"game_id": "p1", "level": 5, "current_location": "hilly_meadows", "stats": {}}
        battle, text = create_location_battle(player, random.Random(3), "hilly_meadows")
        self.assertEqual("hilly_meadows", battle["location_id"])
        self.assertIn("Холмистые луга", text)
        self.assertTrue(battle["enemies"])
        for enemy in battle["enemies"]:
            self.assertIn(enemy["name"], {mob["name"] for mob in HILLY_MEADOWS_MOBS.values()})

    def test_ranked_loot_still_boosts_stronger_mobs(self):
        normal = loot_parameters_for_rank(EnemyRank.NORMAL, 60, 1, 1)
        empowered = loot_parameters_for_rank(EnemyRank.EMPOWERED, 60, 1, 1)
        elite = loot_parameters_for_rank(EnemyRank.ELITE, 60, 1, 1)
        self.assertEqual((60, 1, 1), normal)
        self.assertEqual((66, 1, 1), empowered)
        self.assertEqual((90, 2, 2), elite)


if __name__ == "__main__":
    unittest.main()
