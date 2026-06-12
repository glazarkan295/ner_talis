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
    CHECK_TIMER,
    INSPECT_ARCH,
    PAY_100_SILVER,
    RETURN_SMALL_PLATEAU,
    SET_CAMP,
    SMALL_PLATEAU,
    START_SEARCH,
    TAKE_CURSED_COINS,
    APPROACH_ARCH,
    handle_external_location_action,
    location_text,
)
from services.small_plateau_service import (
    ANCIENT_CURSE_ID,
    AMULET_BURN_ID,
    add_effect,
    cleanse_ancient_curse_at_hidden_place,
    handle_cursed_coin_choice,
    register_ancient_curse_active_day,
    resolve_small_plateau_search,
)
from services.item_registry import get_item_definition_by_id
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class SmallPlateauIntegrationTest(unittest.TestCase):
    def make_player_and_storage(self, *, energy: int = 100):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="sp1",
            name="Искатель плато",
            race_id="human",
            races=races,
        )
        player["energy"] = energy
        player["current_energy"] = energy
        player["max_energy"] = 100
        storage.save_new_player(player, "telegram", "sp1")
        return storage, storage.get_player_by_platform("telegram", "sp1")

    def test_small_plateau_is_enterable_and_has_arch_actions(self):
        storage, player = self.make_player_and_storage()
        response = handle_external_location_action(storage, player, SMALL_PLATEAU, rng=random.Random(1))
        self.assertIn("Малое плато", response.text)
        self.assertIn([START_SEARCH], response.buttons)
        self.assertIn([APPROACH_ARCH], response.buttons)

        player = storage.get_player_by_platform("telegram", "sp1")
        arch = handle_external_location_action(storage, player, APPROACH_ARCH, rng=random.Random(2))
        self.assertIn("Древняя арка", arch.text)
        self.assertIn([INSPECT_ARCH], arch.buttons)

        player = storage.get_player_by_platform("telegram", "sp1")
        inspected = handle_external_location_action(storage, player, INSPECT_ARCH, rng=random.Random(3))
        self.assertIn("полустёртые", inspected.text)
        self.assertIn([RETURN_SMALL_PLATEAU], inspected.buttons)

    def test_small_plateau_search_timer_uses_standard_energy_and_resolves(self):
        storage, player = self.make_player_and_storage(energy=100)
        handle_external_location_action(storage, player, SMALL_PLATEAU, rng=random.Random(1))
        player = storage.get_player_by_platform("telegram", "sp1")
        started = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(2))
        self.assertIn("Время поиска: 30 сек", started.text)
        self.assertIn("Потрачено энергии: 2", started.text)
        player = storage.get_player_by_platform("telegram", "sp1")
        player["active_timer"]["ends_at"] = time.time() - 1
        storage.update_player(player)
        completed = handle_external_location_action(storage, player, CHECK_TIMER, rng=random.Random(3))
        self.assertIn("Поиск завершён", completed.text)
        updated = storage.get_player_by_platform("telegram", "sp1")
        self.assertEqual("small_plateau", updated.get("current_location"))
        self.assertEqual(1, updated.get("small_plateau", {}).get("search_count"))

    def test_cursed_coins_first_take_never_curses_and_adds_silver_value(self):
        player = {"hp": 100, "max_hp": 100, "money_copper": 0, "money": 0}
        result = handle_cursed_coin_choice(player, take_coins=True, rng=random.Random(1))
        self.assertEqual(0.0, result["curse_chance"])
        self.assertFalse(result["curse_applied"])
        self.assertIn(player.get("money_copper"), (1000, 2000))

    def test_curse_cleanse_spends_100_silver_and_deals_damage(self):
        player = {"hp": 100, "max_hp": 100, "money_copper": 100000, "money": 100000}
        add_effect(player, ANCIENT_CURSE_ID, {"id": ANCIENT_CURSE_ID, "effect_id": ANCIENT_CURSE_ID, "active": True})
        result = cleanse_ancient_curse_at_hidden_place(player)
        self.assertTrue(result["success"])
        self.assertEqual(0, player["money_copper"])
        self.assertEqual(60, player["hp"])

    def test_search_milestone_adds_amulet_burn(self):
        player = {"hp": 100, "max_hp": 100, "small_plateau": {"search_count": 399}}
        resolve_small_plateau_search(player, random.Random(4))
        self.assertTrue(any((effect.get("id") == AMULET_BURN_ID or effect.get("effect_id") == AMULET_BURN_ID) for effect in player.get("active_effects", [])))

    def test_curse_achievement_after_60_active_days(self):
        player = {}
        add_effect(player, ANCIENT_CURSE_ID, {"id": ANCIENT_CURSE_ID, "effect_id": ANCIENT_CURSE_ID, "active": True})
        result = None
        for _ in range(60):
            result = register_ancient_curse_active_day(player, 30)
        self.assertIsNotNone(result)
        self.assertTrue(any(value == "curse_what_curse" or (isinstance(value, dict) and value.get("achievement_id") == "curse_what_curse") for value in player.get("achievements", [])))

    def test_small_plateau_items_are_in_registry(self):
        self.assertIsNotNone(get_item_definition_by_id("old_brooch"))
        self.assertIsNotNone(get_item_definition_by_id("old_medallion"))
        self.assertIn("2 энергии", location_text("small_plateau"))


if __name__ == "__main__":
    unittest.main()
