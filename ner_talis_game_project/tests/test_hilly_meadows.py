import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import CITY_BUTTONS, process_world_action
from services.external_location_service import (
    CAMP_DISHES,
    HILLY_MEADOWS,
    OUTSIDE_CITY,
    SEARCH_ENERGY_COST,
    START_SEARCH,
    add_item,
    calculate_scaled_seconds,
    create_search_event,
    handle_external_location_action,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class HillyMeadowsIntegrationTest(unittest.TestCase):
    def make_player_and_storage(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="111",
            name="Луговик",
            race_id="human",
            races=races,
        )
        storage.save_new_player(player, "telegram", "111")
        return storage, storage.get_player_by_platform("telegram", "111")

    def test_city_buttons_include_external_location_actions(self):
        self.assertIn(OUTSIDE_CITY, CITY_BUTTONS)
        self.assertIn(HILLY_MEADOWS, CITY_BUTTONS)
        self.assertIn(START_SEARCH, CITY_BUTTONS)
        self.assertIn("Посмотреть", CITY_BUTTONS)
        self.assertIn("Съесть: Сушёное мясо", CITY_BUTTONS)

    def test_gate_to_hilly_meadows_flow_updates_player(self):
        storage, player = self.make_player_and_storage()

        outside = process_world_action(storage, player, OUTSIDE_CITY, "telegram")
        self.assertIn("Выход из города", outside.text)
        self.assertIn([HILLY_MEADOWS], outside.buttons)

        player = storage.get_player_by_platform("telegram", "111")
        meadows = process_world_action(storage, player, HILLY_MEADOWS, "telegram")
        self.assertIn("Холмистые луга", meadows.text)

        player = storage.get_player_by_platform("telegram", "111")
        self.assertEqual(player["current_location"], "hilly_meadows")
        self.assertEqual(player["current_zone"], "hilly_meadows")

    def test_search_spends_energy_and_creates_or_resolves_event(self):
        storage, player = self.make_player_and_storage()
        handle_external_location_action(storage, player, OUTSIDE_CITY)
        player = storage.get_player_by_platform("telegram", "111")
        handle_external_location_action(storage, player, HILLY_MEADOWS)
        player = storage.get_player_by_platform("telegram", "111")

        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(1))
        self.assertIn("Потрачено энергии", response.text)

        player = storage.get_player_by_platform("telegram", "111")
        self.assertLess(player["energy"], 100)
        self.assertEqual(player["energy"], 100 - SEARCH_ENERGY_COST)
        self.assertEqual(player["current_energy"], player["energy"])

    def test_city_button_cannot_bypass_active_search_timer(self):
        storage, player = self.make_player_and_storage()
        handle_external_location_action(storage, player, OUTSIDE_CITY)
        player = storage.get_player_by_platform("telegram", "111")
        handle_external_location_action(storage, player, HILLY_MEADOWS)
        player = storage.get_player_by_platform("telegram", "111")

        handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(1))
        player = storage.get_player_by_platform("telegram", "111")
        response = process_world_action(storage, player, "В город", "telegram")

        self.assertIn("Сначала дождитесь окончания таймера", response.text)
        player = storage.get_player_by_platform("telegram", "111")
        self.assertIsInstance(player.get("active_timer"), dict)
        self.assertNotEqual(player.get("current_zone"), "seldar_central_square")

    def test_glint_event_can_be_resolved_with_look(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        player["active_event"] = create_search_event("glint", random.Random(5))
        storage.update_player(player)

        response = handle_external_location_action(storage, player, "Посмотреть", rng=random.Random(3))
        self.assertTrue(
            "Получено:" in response.text or "ничего не находите" in response.text,
            response.text,
        )
        player = storage.get_player_by_platform("telegram", "111")
        self.assertIsNone(player.get("active_event"))

    def test_camp_cooking_and_eating_restore_energy(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        player["energy"] = 20
        player["current_energy"] = 20
        add_item(player, "Сырое мясо", 1)
        storage.update_player(player)

        camp = handle_external_location_action(storage, player, "Разбить лагерь")
        self.assertIn("Лагерь", camp.text)
        player = storage.get_player_by_platform("telegram", "111")

        cooked = handle_external_location_action(storage, player, "Приготовить: Сушёное мясо ×1")
        self.assertIn("Получено: Сушёное мясо", cooked.text)
        player = storage.get_player_by_platform("telegram", "111")

        eaten = handle_external_location_action(storage, player, "Съесть: Сушёное мясо ×1")
        self.assertIn("Энергия восстановлена", eaten.text)
        player = storage.get_player_by_platform("telegram", "111")
        self.assertEqual(player["energy"], 27)

    def test_energy_time_formula_bounds(self):
        self.assertEqual(calculate_scaled_seconds(100, 100, 60, 600), 60)
        self.assertGreater(calculate_scaled_seconds(50, 100, 60, 600), 60)
        self.assertLessEqual(calculate_scaled_seconds(0, 100, 60, 600), 600)
        self.assertEqual(CAMP_DISHES["Сытная похлёбка"]["restore_energy"], 50)


if __name__ == "__main__":
    unittest.main()
