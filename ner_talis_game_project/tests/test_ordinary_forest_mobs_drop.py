import json
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
    ORDINARY_FOREST_MOBS,
    choose_battle_rank,
    choose_mob_key,
    create_location_battle,
)

DATA_DIR = ROOT_DIR.parent / "data"


class OrdinaryForestMobsDropTest(unittest.TestCase):
    def test_ordinary_forest_json_contains_mob_and_drop_tables(self):
        data = json.loads((DATA_DIR / "ordinary_forest.json").read_text(encoding="utf-8"))
        self.assertEqual("ordinary_forest_mobs_drop_v1", data.get("battle_mobs_version"))
        self.assertEqual(100, sum(int(v) for v in data["battle_rank_chances"]["early"].values()))
        self.assertEqual(100, sum(int(v) for v in data["battle_rank_chances"]["default"].values()))
        self.assertEqual({"forest_wolf", "angry_deer", "forest_boar"}, {entry["mob_id"] for entry in data["battle_mob_tables"]["normal"]})
        self.assertEqual(["forest_bear"], [entry["mob_id"] for entry in data["battle_mob_tables"]["elite"]])
        self.assertEqual(set(ORDINARY_FOREST_MOBS), set(data["battle_drop_tables"]))

    def test_ordinary_forest_mob_catalog_has_mapped_loot(self):
        self.assertEqual({"forest_wolf", "angry_deer", "forest_boar", "forest_bear"}, set(ORDINARY_FOREST_MOBS))
        for mob_key, mob in ORDINARY_FOREST_MOBS.items():
            self.assertTrue(mob.get("loot"), mob_key)
            for item_name, chance, min_amount, max_amount in mob["loot"]:
                self.assertIn(item_name, BATTLE_LOOT_ITEM_IDS["ordinary_forest"])
                self.assertGreaterEqual(chance, 1)
                self.assertLessEqual(chance, 100)
                self.assertGreaterEqual(min_amount, 1)
                self.assertGreaterEqual(max_amount, min_amount)

    def test_ordinary_forest_mob_selection_keeps_bear_out_of_normal_pool(self):
        normal_seen = {choose_mob_key(EnemyRank.NORMAL, random.Random(seed), 20, "ordinary_forest") for seed in range(80)}
        self.assertLessEqual(normal_seen, {"forest_wolf", "angry_deer", "forest_boar"})
        self.assertNotIn("forest_bear", normal_seen)

        elite_seen = {choose_mob_key(EnemyRank.ELITE, random.Random(seed), 20, "ordinary_forest") for seed in range(10)}
        self.assertEqual({"forest_bear"}, elite_seen)

    def test_ordinary_forest_battle_uses_forest_location_level_and_enemy_data(self):
        player = {"game_id": "p1", "level": 5, "current_location": "ordinary_forest", "stats": {}}
        battle, text = create_location_battle(player, random.Random(3), "ordinary_forest")
        self.assertEqual("ordinary_forest", battle["location_id"])
        self.assertIn("Обыкновенный лес", text)
        self.assertTrue(battle["enemies"])
        for enemy in battle["enemies"]:
            self.assertIn(enemy["name"], {mob["name"] for mob in ORDINARY_FOREST_MOBS.values()})
            self.assertGreaterEqual(enemy["level"], 10)
            self.assertLessEqual(enemy["level"], 60)

    def test_ordinary_forest_rank_chances_follow_forest_balance(self):
        early_ranks = {choose_battle_rank(random.Random(seed), 3, "ordinary_forest") for seed in range(120)}
        later_ranks = {choose_battle_rank(random.Random(seed), 20, "ordinary_forest") for seed in range(120)}
        self.assertIn(EnemyRank.ELITE, early_ranks)
        self.assertIn(EnemyRank.ELITE, later_ranks)

    def test_ordinary_forest_drop_uses_canonical_common_trophies(self):
        data = json.loads((DATA_DIR / "ordinary_forest.json").read_text(encoding="utf-8"))
        item_ids = {entry["item_id"] for table in data["battle_drop_tables"].values() for entry in table}
        for old_id in ["wolf_fang", "boar_tusk", "bear_fang", "bear_claw", "deer_antler", "animal_fat"]:
            self.assertNotIn(old_id, item_ids)
        for new_id in ["simple_fang", "simple_claw", "deer_antlers", "fat_piece"]:
            self.assertIn(new_id, item_ids)
        self.assertEqual("fat_piece", BATTLE_LOOT_ITEM_IDS["ordinary_forest"]["Кусок жира"])
        self.assertEqual("deer_antlers", BATTLE_LOOT_ITEM_IDS["ordinary_forest"]["Оленьи рога"])


if __name__ == "__main__":
    unittest.main()
