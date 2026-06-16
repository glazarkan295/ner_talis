import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import process_world_action
from services.external_location_service import COLLECT, START_SEARCH
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class EventResolutionPersistsTest(unittest.TestCase):
    """Regression: the bot handler re-saves the same player object after the
    action (handlers/city.py). resolve_active_event claims an atomic reload, so
    the resolution must land on the SAME object — otherwise the stale original
    overwrites the cleared event and granted loot, leaving the player stuck on
    the event ("Сначала завершите активное событие") with no reward.
    """

    def _setup(self, storage):
        player = create_player(
            game_id="NT-EVT",
            platform="telegram",
            external_user_id="1",
            name="E",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["current_city"] = "outside_seldar"
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        player["location_id"] = "hilly_meadows"
        player["active_event"] = {"type": "berries", "location_id": "hilly_meadows", "event_id": "evt1"}
        player["inventory"] = []
        storage.save_new_player(player, "telegram", "1")

    def _assert_resolves(self, storage):
        # Mirror the bot handler: load, act, then re-save the SAME object.
        player = storage.get_player_by_platform("telegram", "1")
        process_world_action(storage=storage, player=player, action=COLLECT, platform="telegram")
        storage.update_player(player)

        updated = storage.get_player_by_game_id("NT-EVT")
        self.assertIsNone(updated.get("active_event"))  # событие завершено
        self.assertTrue(updated.get("inventory"))       # ресурс собран

        # Any next button must not be blocked by a phantom active event.
        player2 = storage.get_player_by_platform("telegram", "1")
        result = process_world_action(storage=storage, player=player2, action=START_SEARCH, platform="telegram")
        storage.update_player(player2)
        self.assertNotIn("завершите активное событие", result.text)
        self.assertNotIn("завершите текущее событие", result.text)

    def test_event_resolution_persists_json_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = JsonStorage(str(Path(tmp) / "players.json"))
            self._setup(storage)
            self._assert_resolves(storage)

    def test_event_resolution_persists_sqlite_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = SQLiteStorage(str(Path(tmp) / "players.sqlite3"))
            self._setup(storage)
            self._assert_resolves(storage)


if __name__ == "__main__":
    unittest.main()
