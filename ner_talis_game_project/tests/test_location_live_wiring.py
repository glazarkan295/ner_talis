"""Живое подключение конструктора локаций (ТЗ §31–§34, §18–§24).

Проверяет overlay «пустой локации» и списание недельных лимитов через
location_runtime — строго за флагом WORLD_CONSTRUCTOR_LIVE (по умолчанию выкл →
игра не меняется).
"""

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class LocationLiveWiringTest(unittest.TestCase):
    def setUp(self):
        self._content = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._state = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        os.environ["WORLD_CONTENT_PATH"] = self._content
        os.environ["LOCATION_RUNTIME_STATE_PATH"] = self._state
        import services.world_content_registry as wcr
        import services.location_runtime as lr
        self.wcr = wcr
        self.lr = lr
        # Локация + недельный лимит ресурса + событие пустой локации, всё published.
        wcr.create_content(wcr.KIND_LOCATION, "loc_forest", {
            "name": "Лес", "short_description": "x", "type": "wild",
        })
        self._publish(wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_herb", {
            "location": "loc_forest", "limit_type": "resource",
            "linked_object": "money_copper", "total_stock": 70,
            "base_chance": 30, "min_chance": 1, "depletion_trigger": "zero",
        })
        self._publish(wcr.KIND_LOCATION_EMPTY_EVENT, "empty_forest", {
            "location": "loc_forest", "player_text": "Здесь уже всё забрали.",
            "min_percent_depleted": 50, "chance": 100,
        })

    def tearDown(self):
        for var in ("WORLD_CONTENT_PATH", "LOCATION_RUNTIME_STATE_PATH", "WORLD_CONSTRUCTOR_LIVE"):
            os.environ.pop(var, None)
        for base in (self._content, self._state):
            for suffix in ("", ".lock", ".tmp"):
                try:
                    os.unlink(base + suffix)
                except OSError:
                    pass

    def _publish(self, kind, cid, data):
        self.wcr.create_content(kind, cid, data)
        self.wcr.set_status(kind, cid, self.wcr.STATUS_PUBLISHED, force=True)

    # --- Флаг -------------------------------------------------------------
    def test_overlay_off_by_default(self):
        # Флаг не выставлен → overlay не срабатывает даже при истощении.
        self.lr.force_set_remaining("loc_forest", "lim_herb", 0)
        self.assertFalse(self.lr.live_enabled())
        self.assertIsNone(self.lr.roll_empty_overlay("loc_forest", rng=random.Random(1)))

    # --- Overlay пустой локации ------------------------------------------
    def test_overlay_when_depleted(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.lr.force_set_remaining("loc_forest", "lim_herb", 0)  # истощили
        text = self.lr.roll_empty_overlay("loc_forest", rng=random.Random(1))
        self.assertEqual(text, "Здесь уже всё забрали.")

    def test_no_overlay_when_not_depleted(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        # Остаток полный (по умолчанию total) → не истощено → overlay нет.
        self.assertIsNone(self.lr.roll_empty_overlay("loc_forest", rng=random.Random(1)))

    def test_no_overlay_without_empty_event(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.lr.force_set_remaining("loc_forest", "lim_herb", 0)
        self.assertIsNone(self.lr.roll_empty_overlay("loc_other", rng=random.Random(1)))

    # --- Списание лимитов ------------------------------------------------
    def test_consume_for_item_off_is_noop(self):
        self.assertIsNone(self.lr.consume_for_item("loc_forest", "money_copper", 10))

    def test_consume_for_item_decrements(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        taken = self.lr.consume_for_item("loc_forest", "money_copper", 10)
        self.assertEqual(taken, 10)
        limit = self.lr.published_limits("loc_forest")[0]
        self.assertEqual(self.lr.remaining("loc_forest", limit), 60)

    def test_consume_for_item_unknown_item(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.assertIsNone(self.lr.consume_for_item("loc_forest", "no_such_item", 5))

    def test_consume_for_mob_matches_limit(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.wcr.create_content(self.wcr.KIND_MOB, "mob_wolf", {"name": "Волк", "type": "beast", "hp": 10})
        self._publish(self.wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_wolf", {
            "location": "loc_forest", "limit_type": "mob",
            "linked_object": "mob_wolf", "total_stock": 100,
        })
        taken = self.lr.consume_for_mob("loc_forest", "mob_wolf", 3)
        self.assertEqual(taken, 3)


if __name__ == "__main__":
    unittest.main()
