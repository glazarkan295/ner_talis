"""Runtime недельных лимитов/истощения/перераспределения локаций (ТЗ §16–§42)."""

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class LocationRuntimeStateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        self._tmp = tmp.name
        os.environ["LOCATION_RUNTIME_STATE_PATH"] = self._tmp
        import services.location_runtime as lr
        self.lr = lr
        self.limit = {"id": "lim_herb", "data": {
            "total_stock": 100, "base_chance": 30, "min_chance": 1,
            "depletion_trigger": "zero",
        }}

    def tearDown(self):
        os.environ.pop("LOCATION_RUNTIME_STATE_PATH", None)
        for suffix in ("", ".lock", ".tmp"):
            try:
                os.unlink(self._tmp + suffix)
            except OSError:
                pass

    def test_week_key_format(self):
        key = self.lr.current_week_key()
        self.assertRegex(key, r"^\d{4}-W\d{2}$")

    def test_remaining_defaults_to_total(self):
        self.assertEqual(self.lr.remaining("loc_forest", self.limit), 100)

    def test_consume_decrements_and_cannot_overdraw(self):
        taken, left = self.lr.consume("loc_forest", self.limit, 30)
        self.assertEqual((taken, left), (30, 70))
        # Запрошено больше остатка → списывается только остаток (§22/§23).
        taken, left = self.lr.consume("loc_forest", self.limit, 80)
        self.assertEqual((taken, left), (70, 0))
        self.assertEqual(self.lr.remaining("loc_forest", self.limit), 0)

    def test_force_set_remaining(self):
        self.lr.force_set_remaining("loc_forest", "lim_herb", 5)
        self.assertEqual(self.lr.remaining("loc_forest", self.limit), 5)

    def test_unlimited_when_no_total(self):
        limit = {"id": "lim_x", "data": {"base_chance": 10}}
        self.assertIsNone(self.lr.remaining("loc", limit))
        taken, left = self.lr.consume("loc", limit, 5)
        self.assertEqual((taken, left), (5, None))


class LocationRuntimeLogicTest(unittest.TestCase):
    def setUp(self):
        import services.location_runtime as lr
        self.lr = lr

    def test_is_depleted_triggers(self):
        lr = self.lr
        zero = {"data": {"depletion_trigger": "zero"}}
        self.assertTrue(lr.is_depleted(zero, 0, 100))
        self.assertFalse(lr.is_depleted(zero, 1, 100))
        pct = {"data": {"depletion_trigger": "below_10pct"}}
        self.assertTrue(lr.is_depleted(pct, 10, 100))
        self.assertFalse(lr.is_depleted(pct, 11, 100))
        cnt = {"data": {"depletion_trigger": "below_count", "depletion_count": 5}}
        self.assertTrue(lr.is_depleted(cnt, 5, 100))
        self.assertFalse(lr.is_depleted(cnt, 6, 100))
        man = {"data": {"depletion_trigger": "manual", "manual_depleted": True}}
        self.assertTrue(lr.is_depleted(man, 50, 100))

    def test_effective_chance(self):
        lr = self.lr
        limit = {"data": {"base_chance": 30, "min_chance": 1, "depletion_trigger": "zero"}}
        self.assertEqual(lr.effective_chance(limit, 50, 100), 30)
        self.assertEqual(lr.effective_chance(limit, 0, 100), 1)
        off = {"data": {"base_chance": 30, "min_chance": 1, "use_min_chance": False}}
        self.assertEqual(lr.effective_chance(off, 0, 100), 0)

    def test_resource_chances_do_not_boost_others(self):
        # §27: истощённый ресурс падает до min, остальные НЕ растут.
        rows = [
            {"id": "herb", "base_chance": 30, "min_chance": 1, "remaining": 0, "total": 70},
            {"id": "berry", "base_chance": 20, "min_chance": 1, "remaining": 50, "total": 70},
        ]
        out = {r["id"]: r["chance"] for r in self.lr.resource_chances(rows)}
        self.assertEqual(out["herb"], 1)
        self.assertEqual(out["berry"], 20)

    def test_events_no_redistribution(self):
        rows = [
            {"id": "herb", "base_chance": 30, "min_chance": 1, "depleted": True},
            {"id": "wolf", "base_chance": 25, "depleted": False},
        ]
        out = {r["id"]: r["chance"] for r in self.lr.redistribute_event_chances(rows)}
        self.assertEqual(out["herb"], 1)
        self.assertEqual(out["wolf"], 25)

    def test_events_redistribute_even(self):
        # §28: освобождённый шанс истощённого события перетекает живым.
        rows = [
            {"id": "herb", "base_chance": 30, "min_chance": 1, "depleted": True, "weight": 1},
            {"id": "wolf", "base_chance": 25, "depleted": False, "weight": 1},
            {"id": "chest", "base_chance": 10, "depleted": False, "weight": 1},
        ]
        out = {r["id"]: r["chance"] for r in self.lr.redistribute_event_chances(rows, redistribute=True, mode="even")}
        self.assertEqual(out["herb"], 1)
        self.assertAlmostEqual(out["wolf"], 25 + 14.5)
        self.assertAlmostEqual(out["chest"], 10 + 14.5)

    def test_events_redistribute_same_group(self):
        # §30: освобождённый шанс остаётся внутри группы истощённого события.
        rows = [
            {"id": "herb", "base_chance": 30, "min_chance": 1, "depleted": True, "group": "resource"},
            {"id": "berry", "base_chance": 20, "depleted": False, "group": "resource"},
            {"id": "wolf", "base_chance": 25, "depleted": False, "group": "mob"},
        ]
        out = {r["id"]: r["chance"] for r in self.lr.redistribute_event_chances(rows, redistribute=True, mode="same_group")}
        self.assertAlmostEqual(out["berry"], 20 + 29)
        self.assertEqual(out["wolf"], 25)
        self.assertEqual(out["herb"], 1)

    def test_empty_event_threshold(self):
        rows = [{"depleted": True}, {"depleted": True}, {"depleted": False}]
        self.assertTrue(self.lr.should_show_empty_event(rows))          # 66% ≥ 50
        self.assertFalse(self.lr.should_show_empty_event(rows, min_percent=70))

    def test_weighted_choice_excludes_zero_and_is_deterministic(self):
        options = [{"id": "a", "chance": 0}, {"id": "b", "chance": 10}]
        self.assertEqual(self.lr.weighted_choice(options, random.Random(1))["id"], "b")
        # Пустой/нулевой пул → None.
        self.assertIsNone(self.lr.weighted_choice([{"id": "x", "chance": 0}]))


if __name__ == "__main__":
    unittest.main()
