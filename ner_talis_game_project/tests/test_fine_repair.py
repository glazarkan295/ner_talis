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

    def test_repair_preserves_active_legacy_only_fine(self):
        # Codex P2: legacy-форма — активный штраф ТОЛЬКО в active_fine, списка
        # нет. Repair не должен тихо снять долг, а перенести его в active_fines.
        player = {"active_fine": _fine("legacy1", fs.FINE_STATUS_FORCED)}
        report = fs.repair_player_fines(player)
        self.assertEqual(report["state"], "forced_active")
        self.assertEqual(report["active_count"], 1)
        self.assertIn("migrated_legacy_fine", report["issues"])
        self.assertEqual([f["id"] for f in fs.active_fines(player)], ["legacy1"])
        self.assertEqual(player["active_fine"]["id"], "legacy1")

    def test_repair_normalizes_all_aliases_restores_fields_and_deduplicates(self):
        aliases=[("seldar_npc_market_black","black_market"),("Крот","informer_krot"),("casino_raid","underground_casino")]
        for alias,canonical in aliases:
            broken={"id":"same","source":alias,"source_name":alias,"current_amount":None}
            player={"level":10,"active_fines":[broken,dict(broken)]}
            report=fs.repair_player_fines(player,now=1000)
            self.assertTrue(report["fixed"]);self.assertEqual(len(player["active_fines"]),1)
            fine=player["active_fines"][0];self.assertEqual(fine["source"],canonical);self.assertGreater(fine["current_amount"],0)
            for key in ("status","currency","created_at_ts","updated_at_ts","due_day","overdue_day","forced_collection_day","daily_interest_percent","can_pay_in_city_hall","can_pay_in_fortress_hall"):self.assertIn(key,fine)
            actions={row.get("action") for row in player.get("fine_history") or []};self.assertIn("fine_duplicate_removed",actions);self.assertIn("fine_repaired",actions)

    def test_create_pay_remove_delete_write_unified_history(self):
        player={"level":1,"money":1000,"money_copper":1000}
        first=fs.create_raid_fine(player,"black_market_raid",now=100)
        self.assertEqual(first["source"],"black_market");self.assertEqual(player["fine_history"][-1]["action"],"fine_created")
        fs.pay_fine(player,place="city",now=100);self.assertIn("fine_paid",{row["action"] for row in player["fine_history"]})
        second=fs.create_raid_fine(player,"krot",now=200);fs.remove_player_fine(player,second["id"],reason="test");self.assertEqual(player["fine_history"][-1]["action"],"fine_removed_by_admin")
        third=fs.create_raid_fine(player,"casino",now=300);fs.remove_player_fine(player,third["id"],reason="broken",delete=True);self.assertEqual(player["fine_history"][-1]["action"],"fine_invalid_dropped")

    def test_authored_stages_restrictions_text_and_partial_payment_are_live(self):
        fine=_fine("staged",amount=100);fine.update({"created_at_ts":1_000_000,"stages":[{"stage":"first","duration_days":1},{"stage":"second","duration_days":1,"percent_increase":50,"text":"Вторая стадия"},{"stage":"permanent","permanent":True,"force_fortress":True,"block_city":True}],"restrictions":[{"code":"block_market"}],"messages":{"on_block":"Запрещено: {restriction}"},"partial_payment_allowed":True,"payment_places":["profile"]})
        player={"money":100,"money_copper":100,"current_city":"seldar","current_zone":"seldar_central_square","active_fines":[fine]};result=fs.advance_fine_state(player,now=1_000_000+fs.SECONDS_PER_FINE_DAY)
        self.assertIn("Вторая стадия",result.messages);self.assertEqual(fine["current_amount"],150);self.assertEqual(fine["status"],fs.FINE_STATUS_OVERDUE)
        self.assertIn("block_market",fs.fine_restrictions(player));self.assertIn("Запрещено",fs.fine_action_block_text(player,"Чёрный рынок"))
        paid=fs.pay_fine_amount(player,"staged",40,place="profile",now=1_000_100);self.assertEqual(paid["remaining"],110);self.assertEqual(player["money"],60)
        result=fs.advance_fine_state(player,now=1_000_000+2*fs.SECONDS_PER_FINE_DAY);self.assertTrue(result.moved_to_fortress);self.assertIn("block_city",fs.fine_restrictions(player))


if __name__ == "__main__":
    unittest.main()
