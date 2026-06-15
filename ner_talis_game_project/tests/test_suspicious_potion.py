import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.item_registry import get_item_definition_by_id
from site_api import is_suspicious_potion_item, suspicious_potion_effect


class SuspiciousPotionTest(unittest.TestCase):
    def test_item_definition(self):
        item = get_item_definition_by_id("suspicious_potion")
        self.assertIsNotNone(item)
        self.assertEqual(item.get("sell_price_copper"), 50)
        self.assertEqual(item.get("max_stack"), 10)
        self.assertIsNone(item.get("buy_price_copper"))  # купить нельзя
        self.assertTrue(is_suspicious_potion_item(item))

    def test_effect_is_random_buff_or_debuff_1_to_3_stats_30_minutes(self):
        seen_signs = set()
        for seed in range(40):
            effect = suspicious_potion_effect({"level": 30}, random.Random(seed))
            mods = effect["stat_modifiers"]
            self.assertEqual(effect["duration_seconds"], 1800)
            self.assertTrue(1 <= len(mods) <= 3)
            signs = {1 if value > 0 else -1 for value in mods.values()}
            self.assertEqual(len(signs), 1)  # все одного знака (баф ИЛИ дебаф)
            seen_signs.add(signs.pop())
        self.assertEqual(seen_signs, {1, -1})  # встречаются и бафы, и дебафы

    def test_magnitude_scales_with_level(self):
        low = max(abs(v) for _ in range(60) for v in suspicious_potion_effect({"level": 1}, random.Random(_)).get("stat_modifiers").values())
        high = max(abs(v) for _ in range(60) for v in suspicious_potion_effect({"level": 50}, random.Random(_)).get("stat_modifiers").values())
        self.assertGreater(high, low)

    def test_alchemy_failure_yields_suspicious_potion(self):
        from services import crafting_service
        source = Path(crafting_service.__file__).read_text(encoding="utf-8")
        self.assertNotIn("alchemy_sludge", source)
        self.assertIn('"failure_item_id": "suspicious_potion"', source)


if __name__ == "__main__":
    unittest.main()
