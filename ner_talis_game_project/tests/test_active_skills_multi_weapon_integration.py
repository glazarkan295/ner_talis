import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT_DIR.parent
for path in (ROOT_DIR, PROJECT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services.active_skill_service import (
    catalog_skill_by_id,
    choose_active_skill_branch,
    choose_main_path,
    load_active_skill_counts,
    load_active_skill_registry,
    normalize_starter_only_skills,
    path_level,
    resource_cost_with_modifiers,
    runtime_skill_from_catalog,
    player_branch,
    refresh_unlocked_active_skills,
    selected_main_path,
)
from services.city_service import (
    BACK_TO_BRANCH_CHOICE,
    CONFIRM_BRANCH,
    CONFIRM_SKILL,
    ORDER_STONE,
    PREVIEW_SPIRIT_BRANCH,
    process_world_action,
)
from services.derived_stats_service import calculate_player_skill_raw_damage
from services.progression_service import grant_experience
from services.pve_battle_service import create_location_battle, handle_battle_action
from services.registration_service import create_player, load_races
from site_api import frontend_profile


class MemoryStorage:
    def __init__(self):
        self.player = None

    def update_player(self, player):
        self.player = player


class ActiveSkillIntegrationTest(unittest.TestCase):
    def make_player(self):
        races = load_races("data/races.json")
        return create_player("NT-SKILLTEST", "telegram", "111", "Навык", "human", races)

    def test_active_skill_catalog_is_runtime_integrated(self):
        registry = load_active_skill_registry()
        counts = load_active_skill_counts()

        self.assertIsInstance(registry, dict)
        self.assertEqual(len(registry.get("skills", [])), 728)
        self.assertEqual(counts.get("total_skills"), 728)
        skill = catalog_skill_by_id("дух_меч_25_1_рубящий_выпад")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.get("path"), "Меч")

    def test_active_skill_json_catalogs_are_shipped(self):
        required_paths = [
            PROJECT_DIR / "data" / "active_skills_registry.json",
            PROJECT_DIR / "data" / "active_skills_counts.json",
            PROJECT_DIR / "data" / "branch_choice_messages.json",
        ]
        for path in required_paths:
            self.assertTrue(path.exists(), f"Каталог новой системы навыков должен быть в проекте: {path}")

    def test_level_10_sends_branch_hint_without_auto_granting_branch_skills(self):
        player = self.make_player()
        player["level"] = 9
        player["experience"] = 899

        result = grant_experience(player, 1)

        self.assertEqual(player["level"], 10)
        self.assertEqual(player.get("free_skill_points"), 2)
        self.assertTrue(player.get("branch_choice_hint_sent"))
        self.assertIsNotNone(result["branch_hint"])
        self.assertIn("распорядительному камню", result["branch_hint"].casefold())
        self.assertIsNone(player_branch(player))
        self.assertEqual({skill["id"] for skill in player["skills"]["active"]}, {"basic_attack", "magic_spark"})

    def test_order_stone_starts_branch_and_path_choice(self):
        storage = MemoryStorage()
        player = self.make_player()
        player["level"] = 10

        response = process_world_action(storage, player, "Ратуша", "telegram")
        self.assertIn(ORDER_STONE, sum(response.buttons, []))
        player = storage.player

        response = process_world_action(storage, player, ORDER_STONE, "telegram")
        buttons = sum(response.buttons, [])
        self.assertIn(PREVIEW_SPIRIT_BRANCH, buttons)
        self.assertIn("Ветка Маны", buttons)
        player = storage.player

        response = process_world_action(storage, player, PREVIEW_SPIRIT_BRANCH, "telegram")
        self.assertIn(CONFIRM_BRANCH, sum(response.buttons, []))
        player = storage.player

        response = process_world_action(storage, player, CONFIRM_BRANCH, "telegram")
        self.assertIn("Путь: Меч", sum(response.buttons, []))
        player = storage.player

        response = process_world_action(storage, player, "Путь: Меч", "telegram")
        self.assertIn("выбранный путь", response.text.casefold())
        self.assertEqual(player_branch(player), "Дух")
        self.assertEqual(selected_main_path(player), "Меч")
        self.assertTrue(any(skill.get("id") == "starter_spirit_меч_мощный_удар" for skill in player["skills"]["active"]))

    def test_path_threshold_choice_grants_one_skill(self):
        storage = MemoryStorage()
        player = self.make_player()
        player["level"] = 10
        player["current_city"] = "seldar"
        player["current_zone"] = "seldar_town_hall"
        player["location_id"] = "seldar_town_hall"
        choose_active_skill_branch(player, "Дух")
        choose_main_path(player, "Меч")
        starter = next(skill for skill in player["skills"]["active"] if skill.get("path") == "Меч")
        starter["modifiers"][0]["level"] = 24
        self.assertGreaterEqual(path_level(player, "Меч"), 25)

        response = process_world_action(storage, player, ORDER_STONE, "telegram")
        self.assertIn("Навык 1", sum(response.buttons, []))
        player = storage.player

        response = process_world_action(storage, player, "Навык 1", "telegram")
        self.assertIn(CONFIRM_SKILL, sum(response.buttons, []))
        player = storage.player

        response = process_world_action(storage, player, CONFIRM_SKILL, "telegram")
        self.assertIn("теперь ваш", response.text)
        self.assertIn("Меч_25", player.get("chosen_skill_groups", []))
        self.assertTrue(any(str(skill.get("choice_group")) == "Меч_25" for skill in player["skills"]["active"]))

    def test_legacy_concentration_skills_are_removed_but_valid_skills_remain(self):
        player = self.make_player()
        player["skill_branch"] = "Дух"
        player["branch"] = "Ветвь Духа"
        player["skills"]["active"].append({"id": "legacy_focus", "name": "Старый фокус", "concentration_cost": 1})
        player["skills"]["active"].append({"id": "дух_меч_25_1_рубящий_выпад", "name": "Рубящий выпад", "path": "Меч"})

        changed = normalize_starter_only_skills(player)

        self.assertTrue(changed)
        ids = {skill["id"] for skill in player["skills"]["active"]}
        self.assertNotIn("legacy_focus", ids)
        self.assertIn("дух_меч_25_1_рубящий_выпад", ids)
        self.assertEqual(player_branch(player), "Дух")


    def test_passive_skills_affect_damage_resource_cost_and_profile(self):
        player = self.make_player()
        player["level"] = 10
        player["equipment"]["weapon1"] = {
            "id": "test_sword",
            "name": "Учебный меч",
            "type": "Оружие",
            "weapon_type": "sword",
            "slotKey": "weapon1",
        }
        choose_active_skill_branch(player, "Дух")
        choose_main_path(player, "Меч")
        active = runtime_skill_from_catalog(catalog_skill_by_id("дух_меч_25_1_рубящий_выпад"))
        economy = runtime_skill_from_catalog(catalog_skill_by_id("passive_дух_меч_100_2"))
        economy["modifiers"][0]["level"] = 30
        damage_passive = runtime_skill_from_catalog(catalog_skill_by_id("passive_дух_меч_100_1"))
        damage_passive["modifiers"][0]["level"] = 30

        player["skills"]["passive"] = [economy, damage_passive]
        base_damage = calculate_player_skill_raw_damage({**player, "skills": {**player["skills"], "passive": []}}, active)["damage"]
        boosted_damage = calculate_player_skill_raw_damage(player, active)["damage"]
        base_spirit_cost, _ = resource_cost_with_modifiers(active, None)
        boosted_spirit_cost, _ = resource_cost_with_modifiers(active, player)
        profile = frontend_profile(player)

        self.assertGreater(boosted_damage, base_damage)
        self.assertLess(boosted_spirit_cost, base_spirit_cost)
        self.assertEqual(profile["player"]["skillBranch"], "Дух")
        self.assertEqual(profile["player"]["mainSkillPath"], "Меч")
        self.assertGreaterEqual(profile["player"]["mainSkillPathLevel"], 1)
        self.assertTrue(any(skill["id"] == "passive_дух_меч_100_2" for skill in profile["skills"]["passive"]))

    def test_catalog_active_skill_can_be_used_in_pve_battle(self):
        player = self.make_player()
        player["level"] = 10
        player["equipment"]["weapon1"] = {
            "id": "test_sword",
            "name": "Учебный меч",
            "type": "Оружие",
            "weapon_type": "sword",
            "slotKey": "weapon1",
        }
        player["spirit"] = 100
        choose_active_skill_branch(player, "Дух")
        choose_main_path(player, "Меч")
        active = runtime_skill_from_catalog(catalog_skill_by_id("дух_меч_25_1_рубящий_выпад"))
        player["skills"]["active"].append(active)
        player["skills"]["equipped"] = [active]
        create_location_battle(player, random.Random(1), "hilly_meadows")

        text, buttons = handle_battle_action(player, active["name"], random.Random(1))
        self.assertIn("Выберите противника", text)
        self.assertIn("Цель: 1", sum(buttons, []))

        text, buttons = handle_battle_action(player, "Цель: 1", random.Random(1))
        self.assertNotIn("нельзя применить", text)
        self.assertNotIn("Выберите действие боя кнопкой", text)
        self.assertLess(player["active_battle"]["player_state"].get("current_spirit", 100), 100)

    def test_starter_skill_damage_and_profile_preview_still_work(self):
        player = self.make_player()
        magic_spark = next(skill for skill in player["skills"]["active"] if skill["id"] == "magic_spark")
        damage = calculate_player_skill_raw_damage(player, magic_spark)
        self.assertGreater(damage["damage"], 0)
        self.assertEqual(damage["damage_type"], "magic")
        refresh_unlocked_active_skills(player)
        profile = frontend_profile(player)
        ids = {skill["id"] for skill in profile["skills"]["active"]}
        self.assertEqual(ids, {"basic_attack", "magic_spark"})
        profile_skill = next(skill for skill in profile["skills"]["active"] if skill["id"] == "magic_spark")
        self.assertEqual(profile_skill["damage"], damage["damage"])
        self.assertIn("Мана:", profile_skill["resourceText"])


if __name__ == "__main__":
    unittest.main()
