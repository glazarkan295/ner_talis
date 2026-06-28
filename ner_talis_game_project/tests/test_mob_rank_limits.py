"""Лимиты рангов мобов (ТЗ «черты/благословения/фазы» §2.1–§2.2, §11.5)."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.mob_rank_limits import recommended_limits, validate_mob_rank_limits


class MobRankLimitsTest(unittest.TestCase):
    def test_recommended_limits_known_and_unknown(self):
        boss = recommended_limits("boss")
        self.assertEqual(boss["active"], (8, 10))
        self.assertEqual(boss["world"], (0, 0))
        self.assertIsNone(recommended_limits("dragonlord"))

    def test_within_limits_ok(self):
        data = {
            "mob_rank": "special",
            "active_skills": ["a", "b", "c"],
            "passive_skills": ["p"],
            "special_traits": ["t1"],
        }
        res = validate_mob_rank_limits(data)
        self.assertTrue(res["ok"], res)
        self.assertFalse(res["errors"])
        self.assertFalse(res["warnings"])

    def test_too_many_traits_warns_by_default(self):
        data = {"mob_rank": "special", "active_skills": ["a", "b", "c"],
                "passive_skills": ["p"], "special_traits": ["t1", "t2"]}  # лимит 1
        res = validate_mob_rank_limits(data)
        self.assertTrue(res["ok"])  # warning_only → не ошибка
        self.assertTrue(any("особых черт" in w for w in res["warnings"]))

    def test_strict_mode_blocks(self):
        data = {"mob_rank": "special", "active_skills": ["a", "b", "c"],
                "passive_skills": ["p"], "special_traits": ["t1", "t2"]}
        res = validate_mob_rank_limits(data, mode="strict")
        self.assertFalse(res["ok"])
        self.assertTrue(res["errors"])

    def test_world_trait_only_for_world_boss(self):
        data = {"mob_rank": "boss", "active_skills": ["a"] * 8, "passive_skills": ["p"] * 6,
                "world_traits": ["w1"]}
        res = validate_mob_rank_limits(data, mode="strict")
        self.assertFalse(res["ok"])
        self.assertTrue(any("мировых черт" in e for e in res["errors"]))

    def test_per_turn_limit(self):
        data = {"mob_rank": "boss", "active_skills": ["a"] * 8, "passive_skills": ["p"] * 6,
                "active_skills_per_turn_max": 5}  # лимит 2
        res = validate_mob_rank_limits(data, mode="strict")
        self.assertTrue(any("за ход" in e for e in res["errors"]))

    def test_unknown_rank_is_safe(self):
        res = validate_mob_rank_limits({"mob_rank": "wyrm"})
        self.assertTrue(res["ok"])
        self.assertTrue(any("Неизвестный ранг" in w for w in res["warnings"]))


if __name__ == "__main__":
    unittest.main()
