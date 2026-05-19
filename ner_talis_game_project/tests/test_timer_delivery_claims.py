import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.runtime_timer_scheduler import _deliver_timer_once, recover_saved_timers
from storage.json_storage import JsonStorage


class TimerDeliveryClaimTests(unittest.TestCase):
    def make_storage_with_timer(self) -> tuple[JsonStorage, str, str]:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        storage = JsonStorage(str(Path(tmpdir.name) / "players.json"))
        game_id = "NT-TIMERLOCK1"
        timer_id = "camp_rest_test"
        player = {
            "game_id": game_id,
            "id": game_id,
            "public_id": "pub-timer-lock",
            "name": "Таймер",
            "race_id": "human",
            "race_name": "Человек",
            "level": 1,
            "experience": 0,
            "money": 0,
            "energy": 100,
            "max_energy": 100,
            "hp": 10,
            "max_hp": 100,
            "mana": 1,
            "max_mana": 20,
            "spirit": 2,
            "max_spirit": 30,
            "stats": {},
            "inventory": [],
            "linked_accounts": {"telegram": "101"},
            "active_timer": {
                "id": timer_id,
                "type": "camp_rest",
                "seconds": 0,
                "ends_at": 0,
                "location_id": "hilly_meadows_camp",
                "notify": {"platform": "telegram", "chat_id": "101", "target_id": "101"},
            },
        }
        data = storage.empty_schema()
        data["players"][game_id] = player
        data["platform_links"]["telegram:101"] = game_id
        data["names"]["таймер"] = game_id
        storage.save(data)
        return storage, game_id, timer_id

    def test_json_storage_claims_timer_only_once(self):
        storage, game_id, timer_id = self.make_storage_with_timer()

        claimed = storage.claim_active_timer_for_delivery(
            game_id,
            timer_id,
            "worker-a",
            platform_filter="telegram",
        )
        self.assertIsNotNone(claimed)

        second = storage.claim_active_timer_for_delivery(
            game_id,
            timer_id,
            "worker-b",
            platform_filter="telegram",
        )
        self.assertIsNone(second)

    def test_claim_expires_and_can_be_retried(self):
        storage, game_id, timer_id = self.make_storage_with_timer()
        claimed = storage.claim_active_timer_for_delivery(
            game_id,
            timer_id,
            "worker-a",
            platform_filter="telegram",
        )
        self.assertIsNotNone(claimed)
        player = storage.get_player_by_game_id(game_id)
        player["active_timer"]["delivery_claim"]["claimed_until"] = time.time() - 1
        storage.update_player(player)

        retry = storage.claim_active_timer_for_delivery(
            game_id,
            timer_id,
            "worker-b",
            platform_filter="telegram",
        )
        self.assertIsNotNone(retry)
        self.assertEqual(retry["active_timer"]["delivery_claim"]["owner"], "worker-b")

    def test_deliver_timer_once_sends_only_once(self):
        storage, game_id, timer_id = self.make_storage_with_timer()
        sent = []

        def send(platform, target_id, response):
            sent.append((platform, target_id, response.text))

        self.assertTrue(_deliver_timer_once(storage, game_id, timer_id, send, platform_filter="telegram"))
        self.assertFalse(_deliver_timer_once(storage, game_id, timer_id, send, platform_filter="telegram"))
        self.assertEqual(len(sent), 1)
        self.assertIn("Отдых завершён", sent[0][2])

    def test_recovery_does_not_schedule_future_when_worker_mode(self):
        storage, game_id, timer_id = self.make_storage_with_timer()
        player = storage.get_player_by_game_id(game_id)
        player["active_timer"]["ends_at"] = time.time() + 60
        storage.update_player(player)
        sent = []

        count = recover_saved_timers(
            storage,
            lambda platform, target_id, response: sent.append(response.text),
            platform_filter="telegram",
            schedule_future=False,
        )
        self.assertEqual(count, 0)
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
