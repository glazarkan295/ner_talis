"""Глубина поиска (ТЗ 09 §19): чистый слой счётчика + валидация полей локации."""

import os
import sys
import tempfile
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


class SearchDepthRuntimeGateTest(unittest.TestCase):
    """18-CODEX §3: cap глубины из V2-конструктора применяется только при включённом
    живом слое локаций; при выключенном — legacy-поиск его игнорирует."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("WORLD_CONTENT_PATH", "FEATURE_FLAGS_PATH", "WORLD_CONSTRUCTOR_LIVE")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["WORLD_CONTENT_PATH"] = str(base / "world.json")
        os.environ["FEATURE_FLAGS_PATH"] = str(base / "flags.json")
        os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None)
        self.addCleanup(self._restore)
        wcr.create_content(wcr.KIND_LOCATION, "hilly_meadows", {
            "name": "Луга", "type": "wild", "description": "x",
            "search_depth_enabled": True, "search_depth_max": 3,
        })
        wcr.set_status(wcr.KIND_LOCATION, "hilly_meadows", wcr.STATUS_PUBLISHED, force=True)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_cap_ignored_when_v2_off(self):
        from services import external_location_service as els
        self.assertEqual(els._search_depth_max("hilly_meadows"), 0)

    def test_cap_applied_when_v2_on(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        from services import external_location_service as els
        self.assertEqual(els._search_depth_max("hilly_meadows"), 3)


if __name__ == "__main__":
    unittest.main()
