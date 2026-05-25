import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import CITY_BUTTONS, process_world_action
from services.inventory_service import add_inventory_item
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class CraftingWorkshopsAndAlchemyTest(unittest.TestCase):
    def make_storage_player(self):
        tmp = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(tmp.name) / "players.json"))
        player = create_player(
            game_id="NT-CRAFT",
            platform="telegram",
            external_user_id="111",
            name="Ремесленник",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["inventory"] = []
        storage.save_new_player(player, "telegram", "111")
        return tmp, storage, storage.get_player_by_game_id("NT-CRAFT")

    def add_item(self, player, item_id, amount):
        add_inventory_item(player, item_id, amount, item_id=item_id)

    def test_smeltery_uses_numbered_buttons_timer_and_outputs_ingot(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        self.add_item(player, "copper_ore_chunk", 3)
        storage.update_player(player)

        result = process_world_action(storage, player, "Плавильня", "telegram")
        self.assertIn("1. ✅ Медный слиток", result.text)
        self.assertIn("Крафт №1", sum(result.buttons, []))

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Крафт №1", "telegram")
        self.assertIn("Предмет: Медный слиток", result.text)
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Создать", "telegram")
        self.assertIn("Сколько создать", result.text)
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "1", "telegram")
        self.assertIn("Создание началось", result.text)
        self.assertIn("Время: 1 мин", result.text)
        self.assertIsNotNone(result.scheduled_timer)
        self.assertEqual(result.scheduled_timer["seconds"], 60)

        player = storage.get_player_by_game_id("NT-CRAFT")
        player["active_timer"]["ends_at"] = 0
        storage.update_player(player)
        result = process_world_action(storage, player, "Проверить таймер", "telegram")

        self.assertIn("Получено: Медный слиток ×1", result.text)
        updated = storage.get_player_by_game_id("NT-CRAFT")
        self.assertTrue(any(item.get("item_id") == "copper_ingot" and item.get("amount") == 1 for item in updated["inventory"]))
        self.assertFalse(any(item.get("item_id") == "copper_ore_chunk" for item in updated["inventory"]))

    def test_crafting_time_scales_with_requested_quantity(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        self.add_item(player, "copper_ore_chunk", 15)
        storage.update_player(player)

        for action in ["Плавильня", "Крафт №1", "Создать"]:
            result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), action, "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "5", "telegram")

        self.assertIn("Создание началось", result.text)
        self.assertIn("Время: 5 мин", result.text)
        self.assertEqual(result.scheduled_timer["seconds"], 300)
        player = storage.get_player_by_game_id("NT-CRAFT")
        self.assertEqual(player["active_timer"]["seconds"], 300)

    def test_forge_sections_show_short_numbered_recipe_buttons(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        result = process_world_action(storage, player, "Кузница", "telegram")
        self.assertIn("Выберите раздел создания", result.text)
        self.assertIn("Оружие", sum(result.buttons, []))

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Заготовки", "telegram")
        self.assertIn("Что можно создать", result.text)
        self.assertIn("Крафт №1", sum(result.buttons, []))
        self.assertNotIn("Медная пластина", sum(result.buttons, []))

    def test_alchemy_experiment_uses_number_input_and_exact_error_text(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        self.add_item(player, "clean_water", 1)
        self.add_item(player, "silver_chamomile", 2)
        storage.update_player(player)

        for action in ["Алхимическая мастерская", "Эксперимент", "1", "1", "1", "2", "Нет", "Нет", "Нет"]:
            result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), action, "telegram")
        self.assertIn("Выберите порядок действий", result.text)

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "1 2 3", "telegram")
        self.assertIn("Вы выбрали слишком много действий для выбранных ингредиентов.", result.text)

    def test_alchemy_exact_experiment_can_create_healing_potion(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        self.add_item(player, "clean_water", 1)
        self.add_item(player, "silver_chamomile", 2)
        storage.update_player(player)

        for action in ["Алхимическая мастерская", "Эксперимент", "1", "1", "1", "2", "Нет", "Нет", "Нет", "1 8"]:
            result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), action, "telegram")
        self.assertIn("Проверьте состав опыта", result.text)
        self.assertIn("Общий риск: низкий", result.text)

        with patch("services.crafting_service.random.randint", return_value=1):
            result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Провести опыт", "telegram")
        self.assertIn("Вы начали Простое зелье лечения", result.text)

        player = storage.get_player_by_game_id("NT-CRAFT")
        player["active_timer"]["ends_at"] = 0
        storage.update_player(player)
        result = process_world_action(storage, player, "Проверить таймер", "telegram")

        self.assertIn("Получено: Простое зелье лечения ×1", result.text)
        updated = storage.get_player_by_game_id("NT-CRAFT")
        self.assertTrue(any(item.get("item_id") == "simple_healing_potion" for item in updated["inventory"]))

    def test_crafting_vk_routes_contextual_numbers(self):
        self.assertIn("Плавильня", CITY_BUTTONS)
        self.assertIn("Крафт №1", CITY_BUTTONS)
        self.assertIn("Да", CITY_BUTTONS)
        self.assertIn("Нет", CITY_BUTTONS)


if __name__ == "__main__":
    unittest.main()
