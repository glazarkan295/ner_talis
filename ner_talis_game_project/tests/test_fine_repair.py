"""Снятие/починка штрафов (ТЗ «исправить неснимаемый штраф»).

Корень бага: активность штрафа проверялась как «status != paid», поэтому штраф
с любым иным терминальным/повреждённым статусом висел навсегда. Здесь — что
терминальные статусы больше не активны, а forgive_all_fines/repair_player_fines
снимают штрафы и чинят зависшие данные.
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import fine_service as fs


def _fine(fid="fine_1", status=fs.FINE_STATUS_VOLUNTARY, amount=500):
    return {
        "id": fid, "status": status, "current_amount": amount, "current_day": 1,
        "source": "black_market", "source_name": "Чёрный рынок", "created_at_ts": 0,
        "movement_restricted": status == fs.FINE_STATUS_FORCED,
    }


class FineActiveFilterTest(unittest.TestCase):
    def test_terminal_statuses_are_inactive(self):
        for status in (fs.FINE_STATUS_PAID, fs.FINE_STATUS_REMOVED,
                       fs.FINE_STATUS_EXPIRED, fs.FINE_STATUS_CANCELLED):
            self.assertFalse(fs.is_fine_active(_fine(status=status)), status)
        self.assertTrue(fs.is_fine_active(_fine(status=fs.FINE_STATUS_VOLUNTARY)))
        self.assertTrue(fs.is_fine_active(_fine(status=fs.FINE_STATUS_FORCED)))
        # Неизвестный/пустой статус считаем активным (безопасно).
        self.assertTrue(fs.is_fine_active(_fine(status="")))

    def test_removed_fine_no_longer_counts_as_active(self):
        # Раньше «removed_by_admin» (≠ paid) висел как активный навсегда.
        player = {"active_fines": [_fine(status=fs.FINE_STATUS_REMOVED)]}
        self.assertEqual(fs.active_fines(player), [])
        self.assertFalse(fs.has_active_fine(player))

    def test_paid_fine_filtered(self):
        player = {"active_fines": [_fine(status=fs.FINE_STATUS_PAID), _fine("fine_2")]}
        active = fs.active_fines(player)
        self.assertEqual([f["id"] for f in active], ["fine_2"])


class ForgiveAllFinesTest(unittest.TestCase):
    def test_forgive_clears_active_and_restrictions(self):
        player = {"active_fines": [_fine("f1", fs.FINE_STATUS_FORCED), _fine("f2")]}
        self.assertTrue(fs.is_forced_collection(player))
        report = fs.forgive_all_fines(player, by="telegram:1", reason="тест")
        self.assertEqual(report["removed"], 2)
        self.assertTrue(report["was_forced"])
        self.assertEqual(fs.active_fines(player), [])
        self.assertFalse(fs.has_active_fine(player))
        self.assertFalse(fs.is_forced_collection(player))   # ограничение снято (§5)
        self.assertNotIn("active_fine", player)
        # Снятые штрафы уходят в историю/архив (§8).
        self.assertEqual(len(player.get("removed_fines") or []), 2)
        self.assertTrue(player.get("fine_history"))

    def test_forgive_empty_is_safe(self):
        player = {}
        report = fs.forgive_all_fines(player)
        self.assertEqual(report["removed"], 0)
        self.assertFalse(report["was_forced"])


class RepairFinesTest(unittest.TestCase):
    def test_repair_drops_stuck_terminal_fine(self):
        # «штраф снят, но висит»: терминальный статус остался в active_fines.
        player = {"active_fines": [_fine("f1", fs.FINE_STATUS_REMOVED), _fine("f2")]}
        report = fs.repair_player_fines(player)
        self.assertTrue(report["fixed"])
        self.assertEqual(report["active_count"], 1)
        self.assertIn("dropped_inactive_or_invalid_fines", report["issues"])
        self.assertEqual([f["id"] for f in fs.active_fines(player)], ["f2"])

    def test_repair_drops_stale_legacy_alias(self):
        player = {"active_fines": [], "active_fine": _fine("old", fs.FINE_STATUS_PAID)}
        report = fs.repair_player_fines(player)
        self.assertNotIn("active_fine", player)
        self.assertEqual(report["state"], "no_active_fines")
        self.assertTrue(report["fixed"])

    def test_repair_clean_state_no_changes(self):
        player = {"active_fines": [_fine("f1")]}
        report = fs.repair_player_fines(player)
        self.assertFalse(report["fixed"])
        self.assertEqual(report["state"], "active_ok")
        self.assertEqual(report["active_count"], 1)


if __name__ == "__main__":
    unittest.main()
