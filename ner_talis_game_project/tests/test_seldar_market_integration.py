import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import process_world_action
from services.market_service import load_market_items
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class SeldarMarketIntegrationTest(unittest.TestCase):
    def make_storage_player(self):
        tmp = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(tmp.name) / "players.json"))
        player = create_player(
            game_id="NT-MARKET",
            platform="telegram",
            external_user_id="111",
            name="Торговец",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["money"] = 1000
        player["money_copper"] = 1000
        player["inventory"] = []
        storage.save_new_player(player, "telegram", "111")
        return tmp, storage, storage.get_player_by_game_id("NT-MARKET")

    def test_market_catalog_contains_updated_assortment(self):
        names = [item.display_name for item in load_market_items()]
        self.assertIn("Простое зелье лечения", names)
        self.assertIn("Пустой колчан для стрел лука", names)
        self.assertIn("Обычный кожаный нагрудник", names)
        self.assertIn("Стекляшки: Алмаз", names)

    def test_buy_item_charges_money_and_uses_inventory_helper(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        result = process_world_action(storage, player, "Рынок", "telegram")
        self.assertIn("Рынок", result.text)
        result = process_world_action(storage, player, "Купить", "telegram")
        self.assertIn("Выберите товар", result.text)
        result = process_world_action(storage, player, "Чистая вода", "telegram")
        self.assertIn("Цена покупки", result.text)
        result = process_world_action(storage, player, "Купить", "telegram")
        self.assertIn("Введите количество", result.text)
        with patch("services.market_service.npc_purchase_refund_amount", return_value=0):
            result = process_world_action(storage, player, "2", "telegram")

        self.assertIn("Куплено: Чистая вода ×2", result.text)
        self.assertIn("Чистая вода", sum(result.buttons, []))
        updated = storage.get_player_by_game_id("NT-MARKET")
        self.assertEqual(updated["money_copper"], 970)
        self.assertEqual(updated.get("current_zone"), "seldar_npc_market_buy")
        self.assertEqual(updated.get("market_context", {}).get("mode"), "buy_list")
        self.assertTrue(any(item.get("id") == "clean_water" and item.get("amount") == 2 for item in updated["inventory"]))

    def test_pavilion_button_from_market_main_exits_to_pavilion(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Рынок", "telegram")
        result = process_world_action(storage, player, "Торговый павильон", "telegram")

        self.assertIn("Торговый павильон", result.text)
        self.assertNotIn("Рынок Торгового квартала", result.text)
        updated = storage.get_player_by_game_id("NT-MARKET")
        self.assertEqual(updated.get("current_zone"), "seldar_trade_pavilion")
        self.assertNotIn("market_context", updated)

    def test_legacy_back_from_market_main_exits_to_pavilion(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Рынок", "telegram")
        result = process_world_action(storage, player, "Назад", "telegram")

        self.assertIn("Торговый павильон", result.text)
        self.assertNotIn("Рынок Торгового квартала", result.text)
        updated = storage.get_player_by_game_id("NT-MARKET")
        self.assertEqual(updated.get("current_zone"), "seldar_trade_pavilion")
        self.assertNotIn("market_context", updated)

    def test_back_to_market_from_buy_list_returns_market_main(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Рынок", "telegram")
        process_world_action(storage, player, "Купить", "telegram")
        result = process_world_action(storage, player, "Назад на рынок", "telegram")

        self.assertIn("Рынок Торгового квартала", result.text)
        updated = storage.get_player_by_game_id("NT-MARKET")
        self.assertEqual(updated.get("current_zone"), "seldar_npc_market")
        self.assertEqual(updated.get("market_context", {}).get("mode"), "main")

    def test_sell_inventory_item_does_not_add_to_market_assortment(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        player["inventory"] = [{"id": "clean_water", "name": "Чистая вода", "amount": 3, "can_sell": True, "sell_price_copper": 5}]
        storage.update_player(player)

        process_world_action(storage, player, "Рынок", "telegram")
        process_world_action(storage, player, "Продать", "telegram")
        result = process_world_action(storage, player, "Чистая вода ×3", "telegram")
        self.assertIn("Цена продажи", result.text)
        process_world_action(storage, player, "Продать", "telegram")
        result = process_world_action(storage, player, "2", "telegram")

        self.assertIn("Продано: Чистая вода ×2", result.text)
        self.assertIn("Чистая вода ×1", sum(result.buttons, []))
        updated = storage.get_player_by_game_id("NT-MARKET")
        self.assertEqual(updated["money_copper"], 1010)
        self.assertEqual(updated.get("current_zone"), "seldar_npc_market_sell")
        self.assertEqual(updated.get("market_context", {}).get("mode"), "sell_list")
        self.assertEqual(updated["inventory"][0]["amount"], 1)
        names = [item.display_name for item in load_market_items()]
        self.assertEqual(names.count("Чистая вода"), 1)

    def test_buy_rejects_when_inventory_and_overflow_cannot_fit_full_quantity(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        player["inventory_capacity"] = 1
        player["inventory"] = [{"id": "occupied", "name": "Занято", "amount": 1, "max_stack": 1}]
        storage.update_player(player)

        process_world_action(storage, player, "Рынок", "telegram")
        process_world_action(storage, player, "Купить", "telegram")
        process_world_action(storage, player, "Обычный кожаный шлем", "telegram")
        process_world_action(storage, player, "Купить", "telegram")
        result = process_world_action(storage, player, "1", "telegram")

        self.assertIn("не хватает места", result.text)
        updated = storage.get_player_by_game_id("NT-MARKET")
        self.assertEqual(updated["money_copper"], 1000)
        self.assertEqual(len(updated["inventory"]), 1)


if __name__ == "__main__":
    unittest.main()
