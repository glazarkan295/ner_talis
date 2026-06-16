import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import process_world_action
from services.currency import format_price
from services.fine_service import (
    SECONDS_PER_FINE_DAY,
    advance_fine_state,
    create_raid_fine,
    fine_entries_for_profile,
    pay_fine,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class BlackMarketRaidFineTest(unittest.TestCase):
    def make_storage_player(self, level=100, money=1000):
        tmp = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(tmp.name) / "players.json"))
        player = create_player(
            game_id="NT-RAID",
            platform="telegram",
            external_user_id="999",
            name="Контрабандист",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["level"] = level
        player["money"] = money
        player["money_copper"] = money
        storage.save_new_player(player, "telegram", "999")
        return tmp, storage, storage.get_player_by_game_id("NT-RAID")

    def test_black_market_action_can_create_raid_fine(self):
        tmp, storage, player = self.make_storage_player(level=100, money=1000)
        self.addCleanup(tmp.cleanup)

        with patch("services.fine_service.should_trigger_raid", return_value=True):
            result = process_world_action(storage, player, "Чёрный рынок", "telegram")

        self.assertIn("штраф", result.text.casefold())
        updated = storage.get_player_by_game_id("NT-RAID")
        self.assertEqual(updated.get("current_zone"), "seldar_central_square")
        self.assertEqual(updated["active_fine"]["source"], "black_market")
        self.assertEqual(updated["active_fine"]["current_amount"], 110)
        self.assertEqual(updated["active_fine"]["status"], "voluntary")

    def test_fine_reaches_forced_collection_and_moves_city_player_to_fortress(self):
        _tmp, _storage, player = self.make_storage_player(level=100, money=1000)
        create_raid_fine(player, "underground_casino", now=1)
        player["current_city"] = "seldar"
        player["current_zone"] = "seldar_central_square"
        player["location_id"] = "seldar_central_square"

        result = advance_fine_state(player, now=1 + 23 * SECONDS_PER_FINE_DAY)

        self.assertTrue(result.moved_to_fortress)
        self.assertEqual(player["active_fine"]["status"], "forced_collection")
        self.assertTrue(player["active_fine"]["movement_restricted"])
        self.assertEqual(player["current_location"], "fortress_in_gorge")
        self.assertEqual(player["current_zone"], "fortress_in_gorge_courtyard")

    def test_city_hall_payment_before_third_stage_clears_fine(self):
        _tmp, _storage, player = self.make_storage_player(level=100, money=1000)
        create_raid_fine(player, "informer_krot", now=0)

        result = pay_fine(player, place="city", now=0)

        self.assertIn("Долг перед городом погашен", result.text)
        self.assertNotIn("active_fine", player)
        self.assertEqual(player["money_copper"], 890)
        self.assertTrue(player.get("paid_fines"))

    def test_forced_collection_blocks_return_to_city_from_fortress(self):
        tmp, storage, player = self.make_storage_player(level=100, money=1000)
        self.addCleanup(tmp.cleanup)
        create_raid_fine(player, "black_market", now=1)
        advance_fine_state(player, now=1 + 23 * SECONDS_PER_FINE_DAY)
        storage.update_player(player)

        result = process_world_action(storage, player, "Вернуться к воротам Селдара", "telegram")

        self.assertIn("Дальше нельзя", result.text)
        updated = storage.get_player_by_game_id("NT-RAID")
        self.assertEqual(updated.get("current_location"), "fortress_in_gorge")
        self.assertEqual(updated.get("current_zone"), "fortress_in_gorge_courtyard")

    def test_fine_entries_for_profile_expose_number_amount_and_term(self):
        _tmp, _storage, player = self.make_storage_player(level=25, money=0)
        create_raid_fine(player, "black_market", now=0)
        create_raid_fine(player, "underground_casino", now=0)

        entries = fine_entries_for_profile(player, now=0)

        self.assertEqual([e["number"] for e in entries], [1, 2])
        for entry in entries:
            self.assertEqual(entry["amount"], format_price(entry["amountCopper"]))
            self.assertIn("дн.", entry["term"])
            self.assertTrue(entry["source"])
        self.assertEqual(fine_entries_for_profile({"level": 1}), [])


if __name__ == "__main__":
    unittest.main()
