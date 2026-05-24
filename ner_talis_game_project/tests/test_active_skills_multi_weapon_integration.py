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
    load_active_skill_counts,
    load_active_skill_registry,
    normalize_starter_only_skills,
    refresh_unlocked_active_skills,
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


class ActiveSkillBranchesRemovedTest(unittest.TestCase):
    def make_player(self):
        races = load_races("data/races.json")
        return create_player("NT-SKILLTEST", "telegram", "111", "Навык", "human", races)

    def test_external_active_skill_catalog_is_not_runtime_integrated(self):
        registry = load_active_skill_registry()
        counts = load_active_skill_counts()
        self.assertIsInstance(registry, dict)
        self.assertIsInstance(counts, dict)
        self.assertIsNone(catalog_skill_by_id("spirit_power_strike"))


    def test_removed_branch_json_catalogs_are_not_shipped(self):
        removed_paths = [
            PROJECT_DIR / "data" / "active_skills_registry.json",
            PROJECT_DIR / "data" / "active_skills_counts.json",
            PROJECT_DIR / "data" / "branch_choice_messages.json",
            PROJECT_DIR / "ner_talis_game_project" / "docs" / "active_skills",
        ]
        for path in removed_paths:
            self.assertFalse(path.exists(), f"Старый каталог веток навыков не должен попадать в проект: {path}")

        json_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in PROJECT_DIR.rglob("*.json")
            if "node_modules" not in path.parts and "dist" not in path.parts
        )
        forbidden_markers = (
            "active_skills_registry",
            "active_skills_counts",
            "branch_choice_messages",
            "spirit_power_strike",
            "spirit_arrow_rain",
        )
        for marker in forbidden_markers:
            self.assertNotIn(marker, json_text)

    def test_level_10_does_not_send_branch_hint_or_grant_branch_skills(self):
        player = self.make_player()
        player["level"] = 9
        player["experience"] = 899
        result = grant_experience(player, 1)
        self.assertEqual(player["level"], 10)
        self.assertEqual(player.get("free_skill_points"), 2)
        self.assertFalse(player.get("branch_choice_hint_sent"))
        self.assertIsNone(result["branch_hint"])
        self.assertIsNone(player.get("skill_branch"))
        self.assertEqual({skill["id"] for skill in player["skills"]["active"]}, {"basic_attack", "magic_spark"})

    def test_order_stone_no_longer_starts_spirit_mana_branch_choice(self):
        storage = MemoryStorage()
        player = self.make_player()
        player["level"] = 10

        response = process_world_action(storage, player, "Ратуша", "telegram")
        self.assertIn(ORDER_STONE, response.buttons[0])
        player = storage.player

        response = process_world_action(storage, player, ORDER_STONE, "telegram")
        self.assertIn("отключена", response.text)
        self.assertNotIn(APPLY_ID_AMULET, sum(response.buttons, []))
        player = storage.player

        response = process_world_action(storage, player, APPLY_ID_AMULET, "telegram")
        self.assertIn("отключена", response.text)
        self.assertNotIn(CHOOSE_SPIRIT_BRANCH, sum(response.buttons, []))
        self.assertNotIn(CHOOSE_MANA_BRANCH, sum(response.buttons, []))

        response = process_world_action(storage, player, CHOOSE_SPIRIT_BRANCH, "telegram")
        self.assertIn("отключена", response.text)
        self.assertIsNone(player.get("skill_branch"))
        self.assertEqual({skill["id"] for skill in player["skills"]["active"]}, {"basic_attack", "magic_spark"})

    def test_old_branch_skills_are_removed_but_starter_skills_remain(self):
        player = self.make_player()
        player["skill_branch"] = "spirit"
        player["branch"] = "Ветвь Духа"
        player["branch_choice_hint_sent"] = True
        player["skills"]["active"].append({"id": "spirit_power_strike", "name": "Сильный удар"})
        player["skills"]["equipped"] = [
            {"id": "spirit_power_strike", "name": "Сильный удар"},
            {"id": "magic_spark", "name": "Магический сгусток"},
        ]

        changed = normalize_starter_only_skills(player)
        self.assertTrue(changed)
        self.assertIsNone(player.get("skill_branch"))
        self.assertEqual(player.get("branch"), "Без ветви")
        self.assertFalse(player.get("branch_choice_hint_sent"))
        self.assertEqual({skill["id"] for skill in player["skills"]["active"]}, {"basic_attack", "magic_spark"})
        self.assertEqual([skill["id"] for skill in player["skills"]["equipped"]], ["magic_spark"])

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
