"""Тестовый бой и баланс-проверка моба (ТЗ §28–§30)."""

import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import mob_balance_service as mbs


class MobBalanceTest(unittest.TestCase):
    def test_report_shape(self):
        rep = mbs.simulate_battle({"hp": 50, "phys_damage": 8, "accuracy": 20}, count=50, rng=random.Random(1))
        for key in ("winRate", "deathRate", "avgTurns", "avgMobDamagePerTurn",
                    "avgPlayerDamagePerTurn", "avgExp", "avgCoins", "warnings", "simulations"):
            self.assertIn(key, rep)
        self.assertEqual(rep["simulations"], 50)
        self.assertTrue(0.0 <= rep["winRate"] <= 1.0)

    def test_weak_mob_warns_underpowered(self):
        rep = mbs.simulate_battle(
            {"hp": 1, "phys_damage": 0, "accuracy": 1, "experience": 500, "coins": 100},
            count=100, rng=random.Random(2),
        )
        self.assertGreater(rep["winRate"], 0.98)
        self.assertTrue(any("слабый" in w for w in rep["warnings"]))

    def test_strong_mob_warns_overpowered_and_one_shot(self):
        rep = mbs.simulate_battle(
            {"hp": 100000, "phys_damage": 99999, "accuracy": 9999, "max_level": 50},
            count=50, rng=random.Random(3),
        )
        self.assertLess(rep["winRate"], 0.2)
        joined = " ".join(rep["warnings"])
        self.assertIn("сильный", joined)
        self.assertIn("один ход", joined)

    def test_deterministic_with_seed(self):
        mob = {"hp": 60, "phys_damage": 10, "accuracy": 25, "evasion": 10}
        a = mbs.simulate_battle(mob, count=80, rng=random.Random(7))
        b = mbs.simulate_battle(mob, count=80, rng=random.Random(7))
        self.assertEqual(a["winRate"], b["winRate"])
        self.assertEqual(a["avgTurns"], b["avgTurns"])

    def test_player_override(self):
        # Сильный игрок-переопределение выигрывает у среднего моба чаще.
        mob = {"hp": 200, "phys_damage": 15, "accuracy": 30, "phys_defense": 20}
        weak = mbs.simulate_battle(mob, {"level": 1}, count=80, rng=random.Random(5))
        strong = mbs.simulate_battle(mob, {"level": 1, "hp": 5000, "damage": 500, "accuracy": 999}, count=80, rng=random.Random(5))
        self.assertGreaterEqual(strong["winRate"], weak["winRate"])


if __name__ == "__main__":
    unittest.main()
