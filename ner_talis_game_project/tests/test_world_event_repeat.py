"""Повтор мировых событий (ТЗ §4.1/§4.2) — валидация типов и параметров."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import world_event_service as wes


def _val(data):
    return wes.validate({"data": data})


class WorldEventRepeatTest(unittest.TestCase):
    def test_repeat_types_exposed(self):
        self.assertEqual(wes.REPEAT_TYPES, ("none", "weekly", "monthly", "yearly"))

    def test_weekly_requires_valid_weekday(self):
        bad = _val({"name": "X", "repeat_enabled": True, "repeat_type": "weekly", "repeat_weekday": 9})
        self.assertFalse(bad["ok"])
        self.assertTrue(any("День недели" in e for e in bad["errors"]))
        ok = _val({"name": "X", "repeat_enabled": True, "repeat_type": "weekly", "repeat_weekday": 0})
        self.assertTrue(ok["ok"], ok["errors"])

    def test_monthly_and_yearly_bounds(self):
        self.assertFalse(_val({"name": "X", "repeat_enabled": True, "repeat_type": "monthly", "repeat_day_of_month": 40})["ok"])
        self.assertFalse(_val({"name": "X", "repeat_enabled": True, "repeat_type": "yearly", "repeat_month": 13})["ok"])
        self.assertTrue(_val({"name": "X", "repeat_enabled": True, "repeat_type": "yearly", "repeat_month": 12})["ok"])

    def test_unknown_repeat_type(self):
        bad = _val({"name": "X", "repeat_enabled": True, "repeat_type": "hourly"})
        self.assertFalse(bad["ok"])
        self.assertTrue(any("тип повтора" in e.lower() for e in bad["errors"]))

    def test_hours_bounds(self):
        bad = _val({"name": "X", "repeat_enabled": True, "repeat_type": "none", "repeat_start_hour": 25})
        self.assertFalse(bad["ok"])

    def test_repeat_disabled_ignores_params(self):
        ok = _val({"name": "X", "repeat_enabled": False, "repeat_type": "weekly", "repeat_weekday": 99})
        self.assertTrue(ok["ok"], ok["errors"])


if __name__ == "__main__":
    unittest.main()
