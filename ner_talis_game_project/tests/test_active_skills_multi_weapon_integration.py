import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT_DIR.parent
for path in (ROOT_DIR, PROJECT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services.active_skill_service import (
    load_active_skill_counts,
    load_active_skill_registry,
    is_skill_weapon_compatible,
)
from services.city_service import (
    APPLY_ID_AMULET,
    CHOOSE_MANA_BRANCH,
    CHOOSE_SPIRIT_BRANCH,
    ORDER_STONE,
    process_world_action,
)
from services.derived_stats_service import calculate_player_skill_raw_damage
from services.progression_service import grant_experience
from services.registration_service import create_player, load_races
from site_api import frontend_profile


class MemoryStorage:
    def __init__(self):
        self.player = None

    def update_player(self, player):
        self.player = player


class ActiveSkillsMultiWeaponIntegrationTest(unittest.TestCase):
    def make_player(self):
        races = load_races("data/races.json")
        return create_player("NT-SKILLTEST", "telegram", "111", "Навык", "human", races)

    def test_registry_and_multi_weapon_report_are_integrated(self):
        registry = load_active_skill_registry()
        counts = load_active_skill_counts()
        self.assertEqual(counts["total_skills"], 94)
        self.assertEqual(len(registry["skills"]), 94)
        self.assertEqual(counts["direct_player_level_unlocks"], 0)
        self.assertEqual(counts["multi_weapon_skills"], 28)
        self.assertEqual(counts["weapon_requirement_mode"], "any_of")
        self.assertEqual((counts.get("weapon_sync") or {}).get("invalid_weapon_tokens"), 0)

    def test_level_10_sends_branch_choice_hint_but_does_not_open_branch_skills(self):
        player = self.make_player()
        player["level"] = 9
        player["experience"] = 899
        result = grant_experience(player, 1)
        self.assertEqual(player["level"], 10)
        self.assertTrue(player["branch_choice_hint_sent"])
        self.assertIn("Распорядительного камня", result["branch_hint"])
        self.assertIsNone(player.get("skill_branch"))
        self.assertEqual(len(player["skills"]["active"]), 2)

    def test_order_stone_selects_branch_and_grants_branch_starter_skills(self):
        storage = MemoryStorage()
        player = self.make_player()
        player["level"] = 10

        response = process_world_action(storage, player, "Ратуша", "telegram")
        self.assertIn(ORDER_STONE, response.buttons[0])
        player = storage.player

        response = process_world_action(storage, player, ORDER_STONE, "telegram")
        self.assertIn(APPLY_ID_AMULET, response.buttons[0])
        player = storage.player

        response = process_world_action(storage, player, APPLY_ID_AMULET, "telegram")
        self.assertIn(CHOOSE_SPIRIT_BRANCH, response.buttons[0])
        self.assertIn(CHOOSE_MANA_BRANCH, response.buttons[1])
        player = storage.player

        response = process_world_action(storage, player, CHOOSE_SPIRIT_BRANCH, "telegram")
        self.assertIn("Вы выбрали Ветвь Духа", response.text)
        self.assertEqual(player["skill_branch"], "spirit")
        self.assertEqual(player["branch"], "Ветвь Духа")
        skill_names = {skill["name"] for skill in player["skills"]["active"]}
        self.assertIn("Сильный удар", skill_names)
        self.assertIn("Прицельный выстрел", skill_names)

    def test_weapon_requirements_use_any_of_with_project_weapon_types(self):
        player = self.make_player()
        registry = load_active_skill_registry()
        power_strike = next(skill for skill in registry["skills"] if skill["id"] == "spirit_power_strike")
        aimed_shot = next(skill for skill in registry["skills"] if skill["id"] == "spirit_aimed_shot")
        self.assertIn("staff", power_strike["weapon_requirements"])
        self.assertTrue(is_skill_weapon_compatible(player, power_strike))
        self.assertFalse(is_skill_weapon_compatible(player, aimed_shot))

    def test_profile_and_damage_preview_use_integrated_branch_skill_formula(self):
        storage = MemoryStorage()
        player = self.make_player()
        player["level"] = 10
        process_world_action(storage, player, ORDER_STONE, "telegram")
        player = storage.player
        process_world_action(storage, player, CHOOSE_MANA_BRANCH, "telegram")
        player = storage.player
        mana_spark = next(skill for skill in player["skills"]["active"] if skill["id"] == "mana_spark")
        damage = calculate_player_skill_raw_damage(player, mana_spark)
        self.assertGreater(damage["damage"], 0)
        self.assertEqual(damage["damage_type"], "magic")
        profile = frontend_profile(player)
        profile_skill = next(skill for skill in profile["skills"]["active"] if skill["id"] == "mana_spark")
        self.assertEqual(profile_skill["damage"], damage["damage"])
        self.assertIn("Мана:", profile_skill["resourceText"])


if __name__ == "__main__":
    unittest.main()
