import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import UNSTUCK_COOLDOWN_SECONDS, unstuck_player
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage

TELEGRAM = "telegram"


class UnstuckTest(unittest.TestCase):
    def _make(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        storage = JsonStorage(str(Path(tmp.name) / "players.json"))
        races = load_races("data/races.json")
        player = create_player(
            game_id=storage.generate_game_id(),
            platform=TELEGRAM,
            external_user_id="u1",
            name="Застрявший",
            race_id="human",
            races=races,
        )
        storage.save_new_player(player, TELEGRAM, "u1")
        return storage, storage.get_player_by_game_id(player["game_id"])

    def test_unstuck_resets_action_and_moves_to_central_square(self):
        storage, player = self._make()
        player["active_timer"] = {"id": "t1", "type": "search", "ends_at": 10**12}
        player["active_event"] = {"type": "berries"}
        player["in_battle"] = True
        player["active_battle"] = {"enemy": "wolf"}
        player["current_zone"] = "small_plateau"
        player["location_id"] = "small_plateau"
        player["current_city"] = "outside_seldar"
        storage.update_player(player)

        response = unstuck_player(storage, player, now=1000.0)
        self.assertIn("сброшено", response.text.lower())
        self.assertEqual(response.zone_id, "seldar_central_square")

        fresh = storage.get_player_by_game_id(player["game_id"])
        self.assertIsNone(fresh.get("active_timer"))
        self.assertIsNone(fresh.get("active_event"))
        self.assertFalse(fresh.get("in_battle"))
        self.assertIsNone(fresh.get("active_battle"))
        self.assertEqual(fresh.get("current_zone"), "seldar_central_square")
        self.assertEqual(fresh.get("current_city"), "seldar")
        self.assertEqual(fresh.get("last_unstuck_at"), 1000.0)

    def test_unstuck_is_rate_limited_to_30_minutes(self):
        storage, player = self._make()
        unstuck_player(storage, player, now=1000.0)

        # Within cooldown → blocked, no state change.
        player["active_timer"] = {"id": "t2", "type": "search", "ends_at": 10**12}
        blocked = unstuck_player(storage, player, now=1000.0 + 600)  # +10 min
        self.assertIn("раз в 30 минут", blocked.text)
        self.assertIsNotNone(player.get("active_timer"))  # not reset while on cooldown

        # After cooldown → allowed again.
        ok = unstuck_player(storage, player, now=1000.0 + UNSTUCK_COOLDOWN_SECONDS + 1)
        self.assertIn("сброшено", ok.text.lower())
        self.assertIsNone(storage.get_player_by_game_id(player["game_id"]).get("active_timer"))

    def test_unstuck_preserves_effects_and_inventory(self):
        storage, player = self._make()
        player["active_effects"] = [{"id": "ancient_curse", "active": True}]
        player["inventory"] = [{"id": "potion", "item_id": "potion", "name": "Зелье", "amount": 2}]
        player["active_timer"] = {"id": "t3", "type": "search", "ends_at": 10**12}
        storage.update_player(player)

        unstuck_player(storage, player, now=2000.0)
        fresh = storage.get_player_by_game_id(player["game_id"])
        self.assertEqual(fresh.get("active_effects"), [{"id": "ancient_curse", "active": True}])
        self.assertEqual(len(fresh.get("inventory")), 1)


if __name__ == "__main__":
    unittest.main()
