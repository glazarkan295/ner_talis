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
        flat = sum(result.buttons, [])
        self.assertIn("Оружие", flat)
        self.assertIn("Броня", flat)
        self.assertIn("Заготовки", flat)
        self.assertIn("Рецепты", flat)

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Оружие", "telegram")
        self.assertIn("Что можно создать", result.text)
        for expected in (
            "Простой меч",
            "Простой кинжал",
            "Простой топор",
            "Простой молот",
            "Простой лук",
            "Простой арбалет",
            "Простой щит",
            "Простой посох",
            "Простая книга",
        ):
            self.assertIn(expected, result.text)
        self.assertIn("Крафт №9", sum(result.buttons, []))
        self.assertNotIn("Крафт №10", sum(result.buttons, []))

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Броня", "telegram")
        self.assertIn("Что можно создать", result.text)
        self.assertIn("Простой железный пояс", result.text)
        self.assertIn("Крафт №1", sum(result.buttons, []))

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Рецепты", "telegram")
        self.assertIn("В этом разделе пока нет доступных рецептов.", result.text)
        self.assertNotIn("Крафт №1", sum(result.buttons, []))

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Заготовки", "telegram")
        self.assertIn("Что можно создать", result.text)
        self.assertIn("Крафт №1", sum(result.buttons, []))
        self.assertNotIn("Медная пластина", sum(result.buttons, []))


    def test_leatherwork_blanks_use_tanned_leather_instead_of_simple_leather_sheet(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Кожевенная мастерская", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Заготовки", "telegram")

        self.assertIn("Выделанная кожа", result.text)
        self.assertNotIn("Простой лист кожи", result.text)

    def test_leatherwork_armor_section_has_simple_leather_armor_set_and_recipes_section_is_empty(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Кожевенная мастерская", "telegram")

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Броня", "telegram")
        flat = sum(result.buttons, [])
        for expected in (
            "Простой кожаный шлем",
            "Простой кожаный пояс",
            "Простой кожаный нагрудник",
            "Простые кожаные ботинки",
            "Простые кожаные штаны",
            "Простые кожаные перчатки",
        ):
            self.assertIn(expected, result.text)
        self.assertIn("Крафт №6", flat)
        self.assertNotIn("Крафт №7", flat)
        self.assertIn("Кожевенная мастерская", flat)

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT"), "Рецепты", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("В этом разделе пока нет доступных рецептов.", result.text)
        self.assertNotIn("Простой кожевенный рецепт", result.text)
        self.assertNotIn("Крафт №1", flat)
        self.assertIn("Кожевенная мастерская", flat)

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

class CraftingNavigationFixesTest(unittest.TestCase):
    def make_storage_player(self):
        tmp = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(tmp.name) / "players.json"))
        player = create_player(
            game_id="NT-CRAFT-NAV",
            platform="telegram",
            external_user_id="222",
            name="Навигатор",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["inventory"] = []
        storage.save_new_player(player, "telegram", "222")
        return tmp, storage, storage.get_player_by_game_id("NT-CRAFT-NAV")

    def test_alchemy_by_recipe_shows_only_unlocked_recipes_and_local_buttons(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Алхимическая мастерская", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Создать по рецепту", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("Открытых алхимических рецептов пока нет", result.text)
        self.assertNotIn("Крафт №1", flat)
        self.assertIn("Алхимическая мастерская", flat)
        self.assertNotIn("Вернуться к выбору", flat)
        self.assertNotIn("Ремесленный квартал", flat)

        player = storage.get_player_by_game_id("NT-CRAFT-NAV")
        player["unlocked_alchemy_recipes"] = ["alchemy_simple_healing_potion_legacy"]
        storage.update_player(player)
        result = process_world_action(storage, player, "Создать по рецепту", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("Простое зелье лечения", result.text)
        self.assertIn("Крафт №1", flat)
        self.assertIn("Алхимическая мастерская", flat)
        self.assertNotIn("Журнал рецептов", flat)

    def test_alchemy_experiment_cancel_and_back_buttons_return_to_alchemy(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        add_inventory_item(player, "clean_water", 1, item_id="clean_water")
        storage.update_player(player)

        process_world_action(storage, player, "Алхимическая мастерская", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Эксперимент", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("Алхимическая мастерская", flat)
        self.assertNotIn("Отмена", flat)
        self.assertNotIn("Назад", flat)

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Алхимическая мастерская", "telegram")
        self.assertIn("Создать по рецепту", sum(result.buttons, []))
        self.assertEqual(storage.get_player_by_game_id("NT-CRAFT-NAV").get("current_zone"), "seldar_alchemy_workshop")

    def test_forge_and_leatherwork_sections_use_workshop_back_buttons(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Кузница", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Оружие", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("Кузница", flat)
        self.assertNotIn("Вернуться к выбору", flat)

        process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Кожевенная мастерская", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Броня", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("Кожевенная мастерская", flat)
        self.assertNotIn("Вернуться к выбору", flat)

    def test_smeltery_entry_has_no_return_to_choice_button(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        result = process_world_action(storage, player, "Плавильня", "telegram")
        flat = sum(result.buttons, [])
        self.assertNotIn("Вернуться к выбору", flat)
        self.assertIn("Ремесленный квартал", flat)

    def test_blocked_workshops_and_central_square_navigation(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Ремесленный квартал", "telegram")
        # Jewelry workshop is now open: shows the department menu.
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Ювелирная мастерская", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("Выберите отдел", result.text)
        self.assertIn("Бижутерия", flat)
        self.assertIn("вставка камней", flat)
        self.assertEqual(storage.get_player_by_game_id("NT-CRAFT-NAV").get("current_zone"), "seldar_jewelry_workshop")
        # "вставка камней" is a maintenance stub.
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "вставка камней", "telegram")
        self.assertIn("технические работы", result.text)
        # "Бижутерия" opens the craft sections (Кольца/Ожерелья/Рецепты).
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Бижутерия", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("Кольца", flat)
        self.assertIn("Ожерелья", flat)
        # "Кольца" opens a metal sub-menu (iron / silver), not a recipe list.
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Кольца", "telegram")
        flat = sum(result.buttons, [])
        self.assertIn("Железные кольца", flat)
        self.assertIn("Серебряные кольца", flat)
        # Each metal sub-section lists its rings.
        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Железные кольца", "telegram")
        self.assertIn("Что можно создать", result.text)
        self.assertIn("Железное кольцо", result.text)
        self.assertIn("Крафт №1", sum(result.buttons, []))

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "Мастерская чародея", "telegram")
        self.assertIn("техническое обслуживание", result.text)
        self.assertEqual(storage.get_player_by_game_id("NT-CRAFT-NAV").get("current_zone"), "seldar_craft_district")

        result = process_world_action(storage, storage.get_player_by_game_id("NT-CRAFT-NAV"), "⬅️ Центральная площадь", "telegram")
        self.assertIn("Центральная площадь", result.text)
        self.assertEqual(storage.get_player_by_game_id("NT-CRAFT-NAV").get("current_zone"), "seldar_central_square")
