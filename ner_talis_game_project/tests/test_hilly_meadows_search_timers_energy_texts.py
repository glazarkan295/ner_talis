import json
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import (
    BACK,
    CHECK_TIMER,
    HILLY_MEADOWS_TEXT,
    START_SEARCH,
    calculate_scaled_seconds,
    handle_external_location_action,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage

DATA_DIR = ROOT_DIR.parent / "data"


class HillyMeadowsSearchTimersEnergyTextsTest(unittest.TestCase):
    def make_player_and_storage(self, *, energy: int = 100):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="777",
            name="Проверяющий",
            race_id="human",
            races=races,
        )
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        player["location_id"] = "hilly_meadows"
        player["energy"] = energy
        player["current_energy"] = energy
        player["max_energy"] = 100
        skills = player.setdefault("skills", {})
        active = skills.setdefault("active", [])
        equipped = skills.setdefault("equipped", [])
        basic = next(skill for skill in active if skill.get("id") == "basic_attack")
        active.remove(basic)
        equipped.append(basic)
        storage.save_new_player(player, "telegram", "777")
        return storage, storage.get_player_by_platform("telegram", "777")

    def test_hilly_meadows_search_rules_are_explicit_in_config_and_location_text(self):
        data = json.loads((DATA_DIR / "hilly_meadows.json").read_text(encoding="utf-8"))
        self.assertEqual(2, data.get("base_search_energy_cost"))
        self.assertEqual(30, data.get("base_search_time_seconds"))
        self.assertEqual(600, data.get("max_search_time_seconds"))
        self.assertEqual("hilly_meadows_search_timing_v1", data.get("search_rules", {}).get("version"))
        self.assertIn("2 энергии", HILLY_MEADOWS_TEXT)
        self.assertIn("30 сек", HILLY_MEADOWS_TEXT)
        self.assertIn("5 минут", HILLY_MEADOWS_TEXT)
        self.assertIn("10 минут", HILLY_MEADOWS_TEXT)

    def test_full_energy_search_spends_two_energy_and_uses_thirty_second_timer(self):
        storage, player = self.make_player_and_storage(energy=100)
        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(1))
        updated = storage.get_player_by_platform("telegram", "777")
        timer = updated.get("active_timer") or {}
        self.assertIn("Поиск начался", response.text)
        self.assertIn("Локация: Холмистые луга", response.text)
        self.assertIn("Время поиска: 30 сек", response.text)
        self.assertIn("Потрачено энергии: 2", response.text)
        self.assertIn("Осталось энергии: 98/100", response.text)
        self.assertEqual(98, updated.get("energy"))
        self.assertEqual(98, updated.get("current_energy"))
        self.assertEqual(30, timer.get("seconds"))
        self.assertEqual(30, response.scheduled_timer.get("seconds"))
        self.assertEqual("hilly_meadows", timer.get("location_id"))

    def test_low_positive_energy_caps_search_time_at_five_minutes(self):
        storage, player = self.make_player_and_storage(energy=1)
        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(2))
        updated = storage.get_player_by_platform("telegram", "777")
        seconds = int(updated["active_timer"]["seconds"])
        self.assertGreaterEqual(seconds, 30)
        self.assertLessEqual(seconds, 300)
        self.assertEqual(0, updated.get("energy"))
        self.assertIn("Потрачено энергии: 1", response.text)

    def test_zero_energy_search_uses_ten_minutes_and_spends_no_energy(self):
        storage, player = self.make_player_and_storage(energy=0)
        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(3))
        updated = storage.get_player_by_platform("telegram", "777")
        self.assertIn("Время поиска: 10 мин", response.text)
        self.assertIn("Потрачено энергии: 0", response.text)
        self.assertEqual(600, updated["active_timer"]["seconds"])
        self.assertEqual(600, response.scheduled_timer["seconds"])
        self.assertEqual(0, updated.get("energy"))

    def test_timer_check_and_completion_keep_search_text_and_location(self):
        storage, player = self.make_player_and_storage(energy=100)
        handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(4))
        player = storage.get_player_by_platform("telegram", "777")
        player["active_timer"]["ends_at"] = time.time() - 1
        storage.update_player(player)
        completed = handle_external_location_action(storage, player, CHECK_TIMER, rng=random.Random(5))
        self.assertIn("Поиск завершён", completed.text)
        self.assertIn("Локация: Холмистые луга", completed.text)
        self.assertNotIn("waterside", completed.text.casefold())
        updated = storage.get_player_by_platform("telegram", "777")
        self.assertIsNone(updated.get("active_timer"))

    def test_back_cancels_active_search_without_returning_city_buttons(self):
        storage, player = self.make_player_and_storage(energy=100)
        handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(6))
        player = storage.get_player_by_platform("telegram", "777")
        cancelled = handle_external_location_action(storage, player, BACK, rng=random.Random(7))
        self.assertIn("прекратили поиск", cancelled.text)
        self.assertIn([START_SEARCH], cancelled.buttons)
        updated = storage.get_player_by_platform("telegram", "777")
        self.assertIsNone(updated.get("active_timer"))
        self.assertEqual("hilly_meadows", updated.get("current_zone"))

    def test_search_time_formula_bounds_remain_stable(self):
        self.assertEqual(30, calculate_scaled_seconds(100, 100, 30, 600))
        self.assertLessEqual(calculate_scaled_seconds(1, 100, 30, 600), 300)
        self.assertEqual(600, calculate_scaled_seconds(0, 100, 30, 600))


if __name__ == "__main__":
    unittest.main()
