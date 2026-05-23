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
    cook_buttons,
    eat_buttons,
    OUTSIDE_CITY,
    SEARCH_ENERGY_COST,
    START_SEARCH,
    BACK,
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

    def equip_basic_attack(self, storage, player):
        skills = player.setdefault("skills", {})
        active = skills.setdefault("active", [])
        equipped = skills.setdefault("equipped", [])
        basic = next(skill for skill in active if skill.get("id") == "basic_attack")
        active.remove(basic)
        equipped.append(basic)
        storage.update_player(player)
        return storage.get_player_by_platform("telegram", "111")

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

    def test_process_world_action_keeps_timer_schedule(self):
        storage, player = self.make_player_and_storage()
        handle_external_location_action(storage, player, OUTSIDE_CITY)
        player = storage.get_player_by_platform("telegram", "111")
        handle_external_location_action(storage, player, HILLY_MEADOWS)
        player = storage.get_player_by_platform("telegram", "111")
        player = self.equip_basic_attack(storage, player)

        response = process_world_action(storage, player, START_SEARCH, "telegram")

        self.assertIsNotNone(response.scheduled_timer)
        self.assertIn([BACK], response.buttons)

    def test_world_back_button_in_external_location_does_not_open_market(self):
        storage, player = self.make_player_and_storage()
        process_world_action(storage, player, OUTSIDE_CITY, "telegram")
        player = storage.get_player_by_platform("telegram", "111")
        process_world_action(storage, player, HILLY_MEADOWS, "telegram")
        player = storage.get_player_by_platform("telegram", "111")

        response = process_world_action(storage, player, BACK, "telegram")

        self.assertIn("Холмистые луга", response.text)
        updated = storage.get_player_by_platform("telegram", "111")
        self.assertEqual(updated.get("current_zone"), "hilly_meadows")
        self.assertFalse(str(updated.get("current_zone") or "").startswith("seldar_npc_market"))

    def test_search_spends_energy_and_creates_or_resolves_event(self):
        storage, player = self.make_player_and_storage()
        handle_external_location_action(storage, player, OUTSIDE_CITY)
        player = storage.get_player_by_platform("telegram", "111")
        handle_external_location_action(storage, player, HILLY_MEADOWS)
        player = storage.get_player_by_platform("telegram", "111")
        player = self.equip_basic_attack(storage, player)

        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(1))
        self.assertIn("Потрачено энергии", response.text)
        self.assertIn([BACK], response.buttons)
        self.assertNotIn(["Вернуться в город"], response.buttons)
        self.assertIsNotNone(response.scheduled_timer)

        player = storage.get_player_by_platform("telegram", "111")
        self.assertLess(player["energy"], 100)
        self.assertEqual(player["energy"], 100 - SEARCH_ENERGY_COST)
        self.assertEqual(player["current_energy"], player["energy"])

        back_response = handle_external_location_action(storage, player, BACK, rng=random.Random(2))
        self.assertIn("прекратили поиск", back_response.text)
        self.assertIn([START_SEARCH], back_response.buttons)
        player = storage.get_player_by_platform("telegram", "111")
        self.assertIsNone(player.get("active_timer"))
        self.assertEqual(player.get("current_zone"), "hilly_meadows")

    def test_zero_energy_search_uses_ten_minute_timer(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        player["energy"] = 0
        player["current_energy"] = 0
        storage.update_player(player)
        player = self.equip_basic_attack(storage, player)

        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(1))

        self.assertIn("Поиск начался", response.text)
        self.assertIn("10 мин", response.text)
        self.assertIsNotNone(response.scheduled_timer)
        self.assertEqual(response.scheduled_timer["seconds"], 600)
        player = storage.get_player_by_platform("telegram", "111")
        self.assertEqual(player["active_timer"]["seconds"], 600)
        self.assertEqual(player["energy"], 0)

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

    def test_trap_and_energy_warning_texts_are_current(self):
        from services.external_location_service import collect_energy_warning_messages, resolve_trap

        class FixedPitRandom(random.Random):
            def __init__(self):
                super().__init__(1)
                self.calls = 0

            def uniform(self, _a, _b):
                self.calls += 1
                return 50 if self.calls == 1 else 0.005

        player = {"hp": 100, "max_hp": 100, "energy": 50, "max_energy": 100}
        trap_text = resolve_trap(player, FixedPitRandom())
        self.assertIn("Ваши ноги запутались в высокой траве", trap_text)
        self.assertNotIn("проваливаетесь", trap_text)

        warnings = collect_energy_warning_messages(player)
        self.assertTrue(any("съешьте еду или вернитесь в город" in warning.casefold() for warning in warnings))
        self.assertFalse(any("вернуться в лагерь" in warning.casefold() for warning in warnings))

    def test_linked_platforms_cannot_duplicate_event_rewards(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        player["active_event"] = {
            "type": "stone_or_ore",
            "event_id": "event-no-double-1",
            "text": "камень",
        }
        storage.update_player(player)

        stale_copy = storage.get_player_by_platform("telegram", "111")
        fresh_copy = storage.get_player_by_platform("telegram", "111")

        first = handle_external_location_action(storage, fresh_copy, "Осмотреть и забрать", rng=random.Random(1))
        second = handle_external_location_action(storage, stale_copy, "Осмотреть и забрать", rng=random.Random(1))

        self.assertIn("Получено:", first.text)
        self.assertIn("повторно не выдаётся", second.text)
        player = storage.get_player_by_platform("telegram", "111")
        self.assertIsNone(player.get("active_event"))
        total_items = sum(int(item.get("amount", 1) or 1) for item in player.get("inventory", []))
        self.assertGreater(total_items, 0)
        self.assertLessEqual(total_items, 3)

    def test_linking_vk_to_telegram_profile_does_not_reapply_starter_pack(self):
        storage, player = self.make_player_and_storage()
        before_inventory = list(player.get("inventory", []))
        before_equipment_ids = sorted(
            str(item.get("id") or item.get("item_id"))
            for item in player.get("equipment", {}).values()
            if isinstance(item, dict)
        )

        code = storage.create_link_code(player["game_id"])
        ok, message, linked = storage.connect_platform_by_code(code, "vk", "222")

        self.assertTrue(ok, message)
        self.assertIsNotNone(linked)
        self.assertEqual(linked["game_id"], player["game_id"])
        self.assertEqual(storage.get_player_by_platform("vk", "222")["game_id"], player["game_id"])
        after = storage.get_player_by_game_id(player["game_id"])
        after_equipment_ids = sorted(
            str(item.get("id") or item.get("item_id"))
            for item in after.get("equipment", {}).values()
            if isinstance(item, dict)
        )
        self.assertEqual(after.get("inventory", []), before_inventory)
        self.assertEqual(after_equipment_ids, before_equipment_ids)



    def test_camp_food_buttons_are_short_and_numbered_for_mobile(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        add_item(player, "Сырое мясо", 10)
        storage.update_player(player)

        camp = handle_external_location_action(storage, player, "Разбить лагерь")
        self.assertIn(["Готовка", "Еда"], camp.buttons)
        self.assertNotIn(["Приготовить еду", "Съесть еду"], camp.buttons)

        player = storage.get_player_by_platform("telegram", "111")
        cooking = handle_external_location_action(storage, player, "Готовка")
        flat_cooking = [button for row in cooking.buttons for button in row]
        self.assertIn("1. ✅ Сушёное мясо", cooking.text)
        self.assertIn("Готовить 1 ×1", flat_cooking)
        self.assertIn("Готовить 1 ×10", flat_cooking)
        self.assertTrue(all(not button.startswith("Приготовить:") for button in flat_cooking))
        self.assertTrue(all(len(button) <= 14 or button == "⬅️ В лагерь" for button in flat_cooking))

        cooked = handle_external_location_action(storage, storage.get_player_by_platform("telegram", "111"), "Готовить 1 ×10")
        self.assertIn("Получено: Сушёное мясо ×10", cooked.text)

        player = storage.get_player_by_platform("telegram", "111")
        player["energy"] = 20
        player["current_energy"] = 20
        storage.update_player(player)
        eating = handle_external_location_action(storage, player, "Еда")
        flat_eating = [button for row in eating.buttons for button in row]
        self.assertIn("1. Сушёное мясо ×10", eating.text)
        self.assertIn("Есть 1 ×1", flat_eating)
        self.assertIn("Есть 1 ×10", flat_eating)
        self.assertTrue(all(not button.startswith("Съесть:") for button in flat_eating))
        self.assertTrue(all(len(button) <= 14 or button == "⬅️ В лагерь" for button in flat_eating))

        eaten = handle_external_location_action(storage, storage.get_player_by_platform("telegram", "111"), "Есть 1 ×10")
        self.assertIn("Энергия восстановлена", eaten.text)
        player = storage.get_player_by_platform("telegram", "111")
        self.assertEqual(player["energy"], 90)

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

        cooked = handle_external_location_action(storage, player, "Сушёное мясо")
        self.assertIn("Получено: Сушёное мясо", cooked.text)
        player = storage.get_player_by_platform("telegram", "111")

        eaten = handle_external_location_action(storage, player, "Съесть: Сушёное мясо")
        self.assertIn("Энергия восстановлена", eaten.text)
        player = storage.get_player_by_platform("telegram", "111")
        self.assertEqual(player["energy"], 27)

    def test_energy_time_formula_bounds(self):
        self.assertEqual(calculate_scaled_seconds(100, 100, 60, 600), 60)
        self.assertGreater(calculate_scaled_seconds(50, 100, 60, 600), 60)
        self.assertLessEqual(calculate_scaled_seconds(1, 100, 60, 600), 300)
        self.assertEqual(calculate_scaled_seconds(0, 100, 60, 600), 600)
        self.assertEqual(calculate_scaled_seconds(0, 100, 30, 600), 600)
        self.assertLessEqual(calculate_scaled_seconds(1, 100, 30, 600), 300)
        self.assertEqual(CAMP_DISHES["Сытная похлёбка"]["restore_energy"], 40)
        self.assertIn("Луговой корень", CAMP_DISHES["Сытная похлёбка"]["ingredients"])
        self.assertIn("Съедобный лесной гриб", CAMP_DISHES["Сытная похлёбка"]["ingredients"])
        self.assertNotIn("Съедобный гриб", CAMP_DISHES["Сытная похлёбка"]["ingredients"])
        self.assertNotIn("Съедобный корень", CAMP_DISHES["Сытная похлёбка"]["ingredients"])


if __name__ == "__main__":
    unittest.main()
