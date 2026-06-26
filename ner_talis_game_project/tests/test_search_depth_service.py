"""Глубина поиска (ТЗ 09 §19): чистый слой счётчика + валидация полей локации."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import search_depth_service as sd
from services import world_content_registry as wcr


class SearchDepthCounterTest(unittest.TestCase):
    def test_first_search_starts_at_one(self):
        player: dict = {}
        self.assertEqual(sd.current_depth(player, "loc_a"), 0)
        self.assertEqual(sd.record_search(player, "loc_a"), 1)
        self.assertEqual(sd.current_depth(player, "loc_a"), 1)

    def test_same_location_increments(self):
        player: dict = {}
        sd.record_search(player, "loc_a")
        sd.record_search(player, "loc_a")
        self.assertEqual(sd.record_search(player, "loc_a"), 3)

    def test_changing_location_resets_to_one(self):
        player: dict = {}
        sd.record_search(player, "loc_a")
        sd.record_search(player, "loc_a")
        # §19.4: первый поиск на другой локации сбрасывает к 1.
        self.assertEqual(sd.record_search(player, "loc_b"), 1)
        self.assertEqual(sd.current_depth(player, "loc_a"), 0)
        self.assertEqual(sd.current_depth(player, "loc_b"), 1)

    def test_max_depth_caps(self):
        player: dict = {}
        for _ in range(5):
            sd.record_search(player, "loc_a", max_depth=3)
        self.assertEqual(sd.current_depth(player, "loc_a"), 3)

    def test_explicit_reset(self):
        player: dict = {}
        sd.record_search(player, "loc_a")
        sd.reset_depth(player)
        self.assertEqual(sd.current_depth(player, "loc_a"), 0)

    def test_threshold_for_matches_range(self):
        thresholds = [
            {"min_depth": 1, "max_depth": 2, "tier": "low"},
            {"min_depth": 3, "max_depth": 0, "tier": "deep"},  # max<=0 = без верхней границы
        ]
        self.assertEqual(sd.threshold_for(thresholds, 1)["tier"], "low")
        self.assertEqual(sd.threshold_for(thresholds, 2)["tier"], "low")
        self.assertEqual(sd.threshold_for(thresholds, 3)["tier"], "deep")
        self.assertEqual(sd.threshold_for(thresholds, 99)["tier"], "deep")
        self.assertIsNone(sd.threshold_for([], 1))


class SearchDepthLocationValidationTest(unittest.TestCase):
    def _validate(self, data: dict):
        return wcr._validate_location({"id": "loc_card", "data": data})

    def test_disabled_skips_checks(self):
        errors, _ = self._validate({"name": "Холмы", "short_description": "x",
                                    "search_depth_start": -5})
        self.assertNotIn("Стартовая глубина поиска не может быть отрицательной.", errors)

    def test_negative_start_rejected(self):
        errors, _ = self._validate({"name": "Холмы", "short_description": "x",
                                    "search_depth_enabled": True, "search_depth_start": -1})
        self.assertTrue(any("Стартовая глубина" in e for e in errors))

    def test_start_greater_than_max_rejected(self):
        errors, _ = self._validate({"name": "Холмы", "short_description": "x",
                                    "search_depth_enabled": True,
                                    "search_depth_start": 5, "search_depth_max": 2})
        self.assertTrue(any("больше максимальной" in e for e in errors))

    def test_threshold_min_gt_max_rejected(self):
        errors, _ = self._validate({"name": "Холмы", "short_description": "x",
                                    "search_depth_enabled": True,
                                    "search_depth_thresholds": [{"min_depth": 5, "max_depth": 2}]})
        self.assertTrue(any("min_depth больше max_depth" in e for e in errors))

    def test_valid_config_passes(self):
        errors, _ = self._validate({"name": "Холмы", "short_description": "x", "type": "exploration",
                                    "search_depth_enabled": True,
                                    "search_depth_start": 1, "search_depth_max": 5,
                                    "search_depth_thresholds": [{"min_depth": 1, "max_depth": 3}]})
        self.assertEqual([e for e in errors if "глубин" in e.lower()], [])


if __name__ == "__main__":
    unittest.main()
