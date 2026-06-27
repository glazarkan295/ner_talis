"""Расширение конструктора эффектов (ТЗ эффектов §2): новые поля и проверки."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import effect_constructor_service as fx


def _v(data):
    return fx.validate({"data": data})


class EffectExpansionTest(unittest.TestCase):
    def test_new_effect_type_allowed(self):
        r = _v({"effect_name": "Метка", "effect_type": "mark_effect",
                "linked_hidden_reputation_id": "guard_suspicion"})
        self.assertTrue(r["ok"], r["errors"])

    def test_mark_without_link_warns(self):
        r = _v({"effect_name": "Метка", "effect_type": "mark_effect"})
        self.assertTrue(any("linked_hidden_reputation_id" in w for w in r["warnings"]))

    def test_unknown_category_warns(self):
        r = _v({"effect_name": "X", "effect_type": "stat_modifier", "stat": "strength",
                "effect_category": "nonsense"})
        self.assertTrue(any("Категория" in w for w in r["warnings"]))

    def test_unknown_trigger_and_duration_warn(self):
        r = _v({"effect_name": "X", "effect_type": "notification_effect",
                "trigger_type": "weird", "duration_mode": "weird2"})
        self.assertTrue(any("Триггер" in w for w in r["warnings"]))
        self.assertTrue(any("длительности" in w for w in r["warnings"]))

    def test_priority_must_be_number(self):
        r = _v({"effect_name": "X", "effect_type": "notification_effect", "priority": "high"})
        self.assertFalse(r["ok"])

    def test_permanent_without_removal_warns(self):
        r = _v({"effect_name": "X", "effect_type": "stat_modifier", "stat": "strength",
                "duration_mode": "permanent"})
        self.assertTrue(any("Постоянный эффект" in w for w in r["warnings"]))

    def test_permanent_with_recalc_ok(self):
        r = _v({"effect_name": "X", "effect_type": "stat_modifier", "stat": "strength",
                "duration_mode": "permanent", "recalculate_on_hidden_reputation_change": True})
        self.assertFalse(any("Постоянный эффект" in w for w in r["warnings"]))

    def test_visibility_and_target_type(self):
        r = _v({"effect_name": "X", "effect_type": "stat_modifier", "stat": "strength",
                "visibility_mode": "stage_only", "target_type": "player"})
        self.assertEqual([w for w in r["warnings"] if "видимост" in w.lower() or "Цель" in w], [])


if __name__ == "__main__":
    unittest.main()
