import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.registration_service import create_player, load_races
from site_api import frontend_profile


class ProfileV2BlocksTest(unittest.TestCase):
    def _player(self, **overrides):
        races = load_races("data/races.json")
        player = create_player(game_id="NT-AAAA111122", platform="telegram", external_user_id="1", name="Тест", race_id="human", races=races)
        player.update(overrides)
        return player

    def test_schema_and_core_blocks_present(self):
        prof = frontend_profile(self._player())
        for key in ("profileSchemaVersion", "status", "warnings", "ratingPlaces", "services", "guild"):
            self.assertIn(key, prof)
        self.assertGreaterEqual(prof["profileSchemaVersion"], 2)
        # Services drive the «Сервисы» tab — transfer + promo available.
        self.assertEqual({s["id"] for s in prof["services"]}, {"transfer", "promo"})
        # No guild system yet → tab hidden.
        self.assertIsNone(prof["guild"])
        # Eight personal rating places, default «—».
        self.assertEqual(len(prof["ratingPlaces"]), 8)
        self.assertTrue(all("place" in p and "label" in p for p in prof["ratingPlaces"]))

    def test_status_free_for_idle_player(self):
        status = frontend_profile(self._player())["status"]
        self.assertEqual(status["state"], "free")
        self.assertTrue(status["canUseInventory"])
        self.assertTrue(status["canMove"])
        self.assertFalse(status["hasActiveTimer"])

    def test_status_in_battle_blocks_inventory(self):
        status = frontend_profile(self._player(in_battle=True))["status"]
        self.assertEqual(status["state"], "in_battle")
        self.assertFalse(status["canUseInventory"])

    def test_warnings_for_free_points(self):
        prof = frontend_profile(self._player(free_stat_points=3, free_skill_points=2))
        types = {w["type"] for w in prof["warnings"]}
        self.assertIn("attr_points", types)
        self.assertIn("skill_points", types)

    def test_rating_places_use_player_values(self):
        prof = frontend_profile(self._player(rating={"globalPlace": 15, "pvePlace": 21}))
        by_key = {p["key"]: p["place"] for p in prof["ratingPlaces"]}
        self.assertEqual(by_key["globalPlace"], 15)
        self.assertEqual(by_key["pvePlace"], 21)
        self.assertEqual(by_key["pvpPlace"], "—")  # not set → placeholder

    def test_guild_block_present_when_player_in_guild(self):
        prof = frontend_profile(self._player(guild={"id": "g1", "name": "Волки", "rank": "member"}))
        self.assertIsInstance(prof["guild"], dict)
        self.assertEqual(prof["guild"]["name"], "Волки")

    def test_race_info_served_from_catalog(self):
        # Раса берётся из data/races.json — фронту больше не нужен свой список.
        info = frontend_profile(self._player())["player"]["raceInfo"]
        self.assertEqual(info["name"], "Человек")
        self.assertTrue(info["description"])
        self.assertIn("Сила", info["statsText"])
        self.assertTrue(len(info["bonuses"]) >= 1)


if __name__ == "__main__":
    unittest.main()
