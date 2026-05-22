import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import HILLY_MEADOWS, OUTSIDE_CITY, START_SEARCH, add_item, complete_active_timer, handle_external_location_action
from services.item_registry import get_item_definition_by_name, load_item_definitions
from services.pve_battle_service import (
    BATTLE_ATTACK,
    BATTLE_ESCAPE,
    BATTLE_MAGIC_SPARK,
    BATTLE_POUCH,
    battle_buttons,
    calculate_player_derived_stats,
    create_hilly_meadows_battle,
    grant_battle_rewards,
    handle_battle_action,
    target_buttons,
)
from services.progression_service import apply_death_experience_penalty, grant_experience
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class AssetsAndPveIntegrationTest(unittest.TestCase):
    def make_player_and_storage(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(game_id, "telegram", "111", "Боец", "human", races)
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

    def test_hilly_meadows_item_registry_is_loaded(self):
        items = load_item_definitions()
        self.assertEqual(len(items), 35)
        mint = get_item_definition_by_name("Луговая мята")
        self.assertIsNotNone(mint)
        self.assertEqual(mint["id"], "meadow_mint")

    def test_add_item_enriches_inventory_with_icon_and_stable_id(self):
        player = {"inventory": []}
        add_item(player, "Луговая мята", 2)
        self.assertEqual(player["inventory"][0]["id"], "meadow_mint")
        self.assertEqual(player["inventory"][0]["amount"], 2)
        self.assertTrue(player["inventory"][0]["icon"].startswith("/assets/items/hilly_meadows/"))

    def test_equipment_magic_armor_is_not_double_counted(self):
        player = {
            "level": 1,
            "stats": {},
            "equipment": {
                "cloak": {
                    "stat_modifiers": {
                        "magic_armor": 7,
                    },
                },
            },
        }

        stats = calculate_player_derived_stats(player)

        self.assertEqual(stats["magic_armor"], 7)

    def test_search_battle_starts_real_pve_battle(self):
        storage, player = self.make_player_and_storage()
        handle_external_location_action(storage, player, OUTSIDE_CITY)
        player = storage.get_player_by_platform("telegram", "111")
        handle_external_location_action(storage, player, HILLY_MEADOWS)
        player = storage.get_player_by_platform("telegram", "111")
        player = self.equip_basic_attack(storage, player)

        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(0))
        self.assertIn("Поиск начался", response.text)
        player = storage.get_player_by_platform("telegram", "111")
        player["active_timer"]["ends_at"] = 0
        storage.update_player(player)
        response = complete_active_timer(storage, player, player["active_timer"]["id"], rng=random.Random(0))
        self.assertIn("Бой начался", response.text)
        player = storage.get_player_by_platform("telegram", "111")
        self.assertEqual(response.buttons, battle_buttons(player))
        self.assertTrue(player["in_battle"])
        self.assertIsInstance(player.get("active_battle"), dict)
        self.assertGreaterEqual(len(player["active_battle"]["enemies"]), 1)

    def test_search_requires_equipped_attack_skill(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"

        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(0))

        self.assertIn("экипируйте", response.text.casefold())
        self.assertIsNone(player.get("active_timer"))

    def test_battle_action_updates_or_ends_battle(self):
        storage, player = self.make_player_and_storage()
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        player = self.equip_basic_attack(storage, player)
        response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(0))
        self.assertIn("Поиск начался", response.text)
        player = storage.get_player_by_platform("telegram", "111")
        player["active_timer"]["ends_at"] = 0
        storage.update_player(player)
        response = complete_active_timer(storage, player, player["active_timer"]["id"], rng=random.Random(0))
        self.assertIn("Бой начался", response.text)
        player = storage.get_player_by_platform("telegram", "111")

        escape = handle_external_location_action(storage, player, BATTLE_ESCAPE, rng=random.Random(3))
        self.assertIn("отступ", escape.text.casefold())
        player = storage.get_player_by_platform("telegram", "111")
        self.assertFalse(player.get("in_battle"))

    def test_food_is_not_usable_in_battle(self):
        _storage, player = self.make_player_and_storage()
        add_item(player, "Сушёное мясо", 1)
        battle, _text = create_hilly_meadows_battle(player, rng=random.Random(1))
        player["in_battle"] = True
        player["active_battle"] = battle

        pouch_text, _buttons = handle_battle_action(player, BATTLE_POUCH, rng=random.Random(1))
        self.assertNotIn("Сушёное мясо", pouch_text)

        use_text, _buttons = handle_battle_action(player, "Использовать: Сушёное мясо", rng=random.Random(1))
        self.assertIn("нельзя использовать", use_text)
        self.assertEqual(player["inventory"][0]["name"], "Сушёное мясо")
        self.assertEqual(player["inventory"][0]["amount"], 1)

    def test_battle_text_uses_player_name_and_splits_last_turn(self):
        _storage, player = self.make_player_and_storage()
        player = self.equip_basic_attack(_storage, player)
        basic = player["skills"]["equipped"][0]
        battle, start_text = create_hilly_meadows_battle(player, rng=random.Random(0))
        player["active_battle"] = battle
        player["in_battle"] = True

        self.assertIn("🧍 Боец:", start_text)
        self.assertNotIn("🧍 Вы:", start_text)
        self.assertNotIn("Тип урона: физический/магический по выбранному действию", start_text)

        handle_battle_action(player, basic["name"], rng=random.Random(1))
        status_text, _buttons = handle_battle_action(player, "Цель: 1", rng=random.Random(1))

        self.assertIn("📜 Действия прошлого хода", status_text)
        self.assertIn("🧍 Боец:", status_text)
        self.assertIn("👹 Противники:", status_text)
        self.assertIn("Боец бьёт", status_text)
        self.assertNotIn("🧍 Вы:", status_text)
        self.assertNotIn("Тип урона: зависит от выбранного действия", status_text)


    def test_target_buttons_keep_original_enemy_numbers_after_kill(self):
        _storage, player = self.make_player_and_storage()
        player = self.equip_basic_attack(_storage, player)
        basic = player["skills"]["equipped"][0]
        battle, _start_text = create_hilly_meadows_battle(player, rng=random.Random(9))
        enemy_template = dict(battle["enemies"][0])
        battle["enemies"] = [dict(enemy_template), dict(enemy_template), dict(enemy_template)]
        battle["enemies"][0]["current_hp"] = 0
        battle["enemies"][1]["current_hp"] = 50
        battle["enemies"][2]["current_hp"] = 50
        battle["pending_skill"] = basic
        player["active_battle"] = battle
        player["in_battle"] = True

        buttons = target_buttons(battle, player)
        flat_buttons = [button for row in buttons for button in row]

        self.assertNotIn("Цель: 1", flat_buttons)
        self.assertIn("Цель: 2", flat_buttons)
        self.assertIn("Цель: 3", flat_buttons)

        before_second_hp = battle["enemies"][1]["current_hp"]
        status_text, _buttons = handle_battle_action(player, "Цель: 2", rng=random.Random(1))

        self.assertLess(player["active_battle"]["enemies"][1]["current_hp"], before_second_hp)
        self.assertIn("2. ", status_text)

    def test_dead_target_number_is_rejected_without_shift_to_next_enemy(self):
        _storage, player = self.make_player_and_storage()
        player = self.equip_basic_attack(_storage, player)
        basic = player["skills"]["equipped"][0]
        battle, _start_text = create_hilly_meadows_battle(player, rng=random.Random(9))
        enemy_template = dict(battle["enemies"][0])
        battle["enemies"] = [dict(enemy_template), dict(enemy_template)]
        battle["enemies"][0]["current_hp"] = 0
        battle["enemies"][1]["current_hp"] = 50
        battle["pending_skill"] = basic
        player["active_battle"] = battle
        player["in_battle"] = True

        response_text, buttons = handle_battle_action(player, "Цель: 1", rng=random.Random(1))
        flat_buttons = [button for row in buttons for button in row]

        self.assertIn("цель уже побеждена", response_text.casefold())
        self.assertEqual(player["active_battle"]["enemies"][1]["current_hp"], 50)
        self.assertNotIn("Цель: 1", flat_buttons)
        self.assertIn("Цель: 2", flat_buttons)


    def test_mob_kill_experience_is_reduced_by_twenty_percent(self):
        _storage, player = self.make_player_and_storage()
        battle = {
            "enemies": [
                {
                    "name": "Тестовый моб",
                    "level": 1,
                    "rank": "normal",
                    "current_hp": 0,
                    "max_hp": 1,
                }
            ]
        }

        rewards = grant_battle_rewards(player, battle, rng=random.Random(1))

        # Base reward for one level-1 normal mob is 32 XP.
        # After the 20% kill-XP reduction it becomes 25, then the human +2% bonus makes it 26.
        self.assertIn("Опыт: +26", rewards)
        self.assertEqual(player["experience"], 26)

    def test_grant_experience_applies_human_bonus_and_level_up(self):
        _storage, player = self.make_player_and_storage()
        result = grant_experience(player, 100)

        self.assertEqual(result["gained"], 102)
        self.assertEqual(result["level_ups"], 1)
        self.assertEqual(player["level"], 2)
        self.assertEqual(player["free_stat_points"], 5)
        self.assertEqual(player["free_skill_points"], 2)
        self.assertEqual(player["experience"], 2)

    def test_death_experience_penalty_removes_ten_percent_current_experience(self):
        _storage, player = self.make_player_and_storage()
        player["experience"] = 137
        player["total_experience"] = 500

        result = apply_death_experience_penalty(player, 10)

        self.assertEqual(result["lost"], 14)
        self.assertEqual(player["experience"], 123)
        self.assertEqual(player["total_experience"], 500)
        self.assertEqual(player["experience_to_next"], 100)

    def test_player_defeat_applies_death_experience_penalty_message(self):
        _storage, player = self.make_player_and_storage()
        player["experience"] = 50
        battle, _start_text = create_hilly_meadows_battle(player, rng=random.Random(0))
        battle["player_state"]["current_hp"] = 1
        battle["enemies"] = [
            {
                "name": "Тестовый противник",
                "level": 1,
                "rank": "normal",
                "current_hp": 10,
                "max_hp": 10,
                "accuracy": 999,
                "dodge": 0,
                "physical_defense": 0,
                "magic_defense": 0,
                "damage_min": 999,
                "damage_max": 999,
                "damage_type": "physical",
                "skills": [],
            }
        ]
        player["active_battle"] = battle
        player["in_battle"] = True

        text, buttons = handle_battle_action(player, BATTLE_ATTACK, rng=random.Random(1))

        self.assertIn("Штраф смерти: -5 опыта (-10%).", text)
        self.assertEqual(player["experience"], 45)
        self.assertFalse(player.get("in_battle"))
        self.assertEqual(buttons, [])

    def test_race_bonuses_affect_combat_stats(self):
        _storage, player = self.make_player_and_storage()
        human_stats = calculate_player_derived_stats(player)
        player["race_id"] = "undead"
        undead_stats = calculate_player_derived_stats(player)

        self.assertGreater(undead_stats["max_hp"], human_stats["max_hp"])


if __name__ == "__main__":
    unittest.main()

class PveCooldownAndDamageFixesTest(unittest.TestCase):
    def make_player(self):
        races = load_races("data/races.json")
        player = create_player("NT-COOLDOWN", "telegram", "111", "КД", "human", races)
        skills = player.setdefault("skills", {})
        active = skills.setdefault("active", [])
        equipped = skills.setdefault("equipped", [])
        basic = next(skill for skill in active if skill.get("id") == "basic_attack")
        active.remove(basic)
        basic["cooldown_turns"] = 1
        equipped.append(basic)
        return player, basic

    def test_skill_damage_preview_matches_pve_raw_damage(self):
        from site_api import frontend_profile
        from services.pve_battle_service import player_skill_raw_damage

        player, basic = self.make_player()
        player["level"] = 10
        profile = frontend_profile(player)
        preview_damage = next(skill["damage"] for skill in profile["skills"]["equipped"] if skill["id"] == "basic_attack")
        battle_damage, _damage_type, _name = player_skill_raw_damage(player, basic)

        self.assertEqual(preview_damage, battle_damage)

    def test_cooldown_blocks_one_following_player_action(self):
        player, basic = self.make_player()
        battle, _text = create_hilly_meadows_battle(player, rng=random.Random(9))
        enemy_template = dict(battle["enemies"][0])
        enemy_template["current_hp"] = 999
        enemy_template["max_hp"] = 999
        enemy_template["accuracy"] = 0
        battle["enemies"] = [enemy_template]
        player["active_battle"] = battle
        player["in_battle"] = True

        handle_battle_action(player, basic["name"], rng=random.Random(1))
        handle_battle_action(player, "Цель: 1", rng=random.Random(1))
        text, _buttons = handle_battle_action(player, basic["name"], rng=random.Random(1))

        self.assertIn("откате", text)

        handle_battle_action(player, BATTLE_ATTACK, rng=random.Random(1))
        text, _buttons = handle_battle_action(player, basic["name"], rng=random.Random(1))

        self.assertIn("Выберите противника", text)
