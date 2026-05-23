import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import CITY_ACTIONS, ORDER_STONE, process_world_action
from services.external_location_service import OUTSIDE_CITY, HILLY_MEADOWS, COMMON_FOREST, FORTRESS_IN_GORGE
from services.market_service import MARKET_ENTRY
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


BAD_TEXT_MARKERS = (
    "Неизвестное городское действие",
    "Неизвестное действие внешней локации",
)
GLOBAL_BUTTONS_HANDLED_BEFORE_WORLD_ROUTER = {"Профиль"}


def flat_buttons(buttons):
    return [button for row in buttons for button in row]


class ButtonRoutingIntegrityTest(unittest.TestCase):
    def make_storage_player(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        storage = JsonStorage(str(Path(tmp.name) / "players.json"))
        player = create_player(
            game_id="NT-BUTTONS",
            platform="telegram",
            external_user_id="111",
            name="Проверяющий",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["level"] = 10
        storage.save_new_player(player, "telegram", "111")
        return storage, storage.get_player_by_game_id("NT-BUTTONS")

    def assert_known_response(self, result):
        for marker in BAD_TEXT_MARKERS:
            self.assertNotIn(marker, result.text)
        self.assertIsInstance(result.buttons, list)
        for row in result.buttons:
            self.assertIsInstance(row, list)
            for button in row:
                self.assertIsInstance(button, str)
                self.assertTrue(button.strip())

    def test_city_screen_buttons_have_registered_routes(self):
        for screen_action, response in CITY_ACTIONS.items():
            for button in flat_buttons(response.buttons):
                if button in GLOBAL_BUTTONS_HANDLED_BEFORE_WORLD_ROUTER:
                    continue
                with self.subTest(screen=screen_action, button=button):
                    storage, player = self.make_storage_player()
                    process_world_action(storage, player, screen_action, "telegram")
                    player = storage.get_player_by_game_id("NT-BUTTONS")
                    result = process_world_action(storage, player, button, "telegram")
                    self.assert_known_response(result)

    def test_trade_district_buttons_break_stale_market_context(self):
        expected_zones = {
            "⬅️ Центральная площадь": "seldar_central_square",
            "Центральная площадь": "seldar_central_square",
            "Торговый квартал": "seldar_trade_district",
            "Торговая гильдия": "seldar_trade_guild",
            "Аукцион": "seldar_auction",
            "Торговый представитель": "seldar_trade_representative",
            "Торговый павильон": "seldar_trade_pavilion",
        }
        for action, expected_zone in expected_zones.items():
            with self.subTest(action=action):
                storage, player = self.make_storage_player()
                player["current_city"] = "seldar"
                player["current_zone"] = "seldar_npc_market"
                player["location_id"] = "seldar_npc_market"
                player["market_context"] = {"mode": "main"}
                storage.update_player(player)

                result = process_world_action(storage, player, action, "telegram")

                self.assert_known_response(result)
                updated = storage.get_player_by_game_id("NT-BUTTONS")
                self.assertEqual(updated.get("current_zone"), expected_zone)
                self.assertNotIn("market_context", updated)

    def test_external_location_buttons_are_not_intercepted_by_city_or_market_routes(self):
        storage, player = self.make_storage_player()

        outside = process_world_action(storage, player, OUTSIDE_CITY, "telegram")
        self.assert_known_response(outside)
        self.assertIn(HILLY_MEADOWS, flat_buttons(outside.buttons))
        self.assertIn(COMMON_FOREST, flat_buttons(outside.buttons))
        self.assertIn(FORTRESS_IN_GORGE, flat_buttons(outside.buttons))

        for action, expected_zone in {
            HILLY_MEADOWS: "hilly_meadows",
            COMMON_FOREST: "ordinary_forest",
            FORTRESS_IN_GORGE: "fortress_in_gorge_courtyard",
        }.items():
            with self.subTest(action=action):
                storage, player = self.make_storage_player()
                process_world_action(storage, player, OUTSIDE_CITY, "telegram")
                player = storage.get_player_by_game_id("NT-BUTTONS")
                result = process_world_action(storage, player, action, "telegram")
                self.assert_known_response(result)
                updated = storage.get_player_by_game_id("NT-BUTTONS")
                self.assertEqual(updated.get("current_zone"), expected_zone)
                self.assertNotIn("market_context", updated)

    def test_external_and_order_stone_buttons_break_stale_market_context(self):
        storage, player = self.make_storage_player()
        player["current_city"] = "seldar"
        player["current_zone"] = "seldar_city_gates"
        player["location_id"] = "seldar_city_gates"
        player["market_context"] = {"mode": "main"}
        storage.update_player(player)

        result = process_world_action(storage, player, OUTSIDE_CITY, "telegram")

        self.assert_known_response(result)
        self.assertIn(HILLY_MEADOWS, flat_buttons(result.buttons))
        updated = storage.get_player_by_game_id("NT-BUTTONS")
        self.assertEqual(updated.get("current_zone"), "outside_city_crossroads")
        self.assertNotIn("market_context", updated)

        storage, player = self.make_storage_player()
        player["level"] = 9
        player["current_city"] = "seldar"
        player["current_zone"] = "seldar_town_hall"
        player["location_id"] = "seldar_town_hall"
        player["market_context"] = {"mode": "main"}
        storage.update_player(player)

        result = process_world_action(storage, player, ORDER_STONE, "telegram")

        self.assert_known_response(result)
        self.assertIn("Вы пришли рано", result.text)
        updated = storage.get_player_by_game_id("NT-BUTTONS")
        self.assertEqual(updated.get("current_zone"), "seldar_town_hall")
        self.assertNotIn("market_context", updated)

    def test_market_buy_sell_buttons_work_through_vk_route(self):
        storage, player = self.make_storage_player()

        process_world_action(storage, player, MARKET_ENTRY, "vk")
        player = storage.get_player_by_game_id("NT-BUTTONS")
        buy_result = process_world_action(storage, player, "Купить", "vk")
        self.assert_known_response(buy_result)
        self.assertIn("Покупка у NPC", buy_result.text)
        self.assertIn("Назад на рынок", flat_buttons(buy_result.buttons))
        updated = storage.get_player_by_game_id("NT-BUTTONS")
        self.assertEqual(updated.get("market_context", {}).get("mode"), "buy_list")

        process_world_action(storage, updated, MARKET_ENTRY, "vk")
        player = storage.get_player_by_game_id("NT-BUTTONS")
        sell_result = process_world_action(storage, player, "Продать", "vk")
        self.assert_known_response(sell_result)
        self.assertIn("Продажа NPC", sell_result.text)
        self.assertIn("Назад на рынок", flat_buttons(sell_result.buttons))
        updated = storage.get_player_by_game_id("NT-BUTTONS")
        self.assertEqual(updated.get("market_context", {}).get("mode"), "sell_list")

    def test_market_entry_still_opens_market_from_city(self):
        storage, player = self.make_storage_player()

        result = process_world_action(storage, player, MARKET_ENTRY, "telegram")

        self.assert_known_response(result)
        updated = storage.get_player_by_game_id("NT-BUTTONS")
        self.assertEqual(updated.get("current_zone"), "seldar_npc_market")
        self.assertEqual(updated.get("market_context", {}).get("mode"), "main")


if __name__ == "__main__":
    unittest.main()
