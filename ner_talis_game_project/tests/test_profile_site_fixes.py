import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.registration_service import create_player, load_races
from services.web_profile import PROFILE_SCOPE, create_profile_site_link
from site_api import create_profile_api_router, frontend_profile
from storage.json_storage import JsonStorage


class ProfileSiteFixesTest(unittest.TestCase):
    def _new_player(self):
        races = load_races("data/races.json")
        return create_player(
            game_id="NT-PROFILEFIX",
            platform="telegram",
            external_user_id="111",
            name="Профиль",
            race_id="human",
            races=races,
        )

    def test_frontend_profile_handles_empty_runtime_resources(self):
        player = self._new_player()
        player["hp"] = None
        player["spirit"] = None
        player["mana"] = None
        player["concentration"] = None

        profile = frontend_profile(player)

        values = {row["label"]: row["value"] for row in profile["parameters"]}
        self.assertRegex(values["HP"], r"^\d+ / \d+$")
        self.assertRegex(values["Дух"], r"^\d+ / \d+$")
        self.assertRegex(values["Мана"], r"^\d+ / \d+$")
        self.assertRegex(values["Концентрация"], r"^\d+ / \d+$")

    def test_inventory_actions_are_based_on_current_location(self):
        player = self._new_player()
        item = player["equipment"].pop("weapon1")
        item["targetSlotKey"] = "weapon1"
        item.pop("slotKey", None)
        item["actions"] = ["Снять"]
        player["inventory"].append(item)

        profile = frontend_profile(player)
        weapon = next(item for item in profile["inventory"] if item["id"] == "starter_wooden_staff")

        self.assertEqual(weapon["actions"], ["Надеть"])

    def test_profile_button_link_uses_short_lived_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            races = load_races("data/races.json")
            player = create_player(
                game_id=storage.generate_game_id(),
                platform="telegram",
                external_user_id="111",
                name="Ссылка",
                race_id="human",
                races=races,
            )
            storage.save_new_player(player, "telegram", "111")

            link = create_profile_site_link(storage, player, "telegram")

            self.assertIn("/profile?token=", link)

    def test_starter_skills_are_level_zero_and_show_damage(self):
        player = self._new_player()
        skills = player["skills"]["active"]

        self.assertEqual(skills[0]["level"], 0)
        self.assertEqual(skills[1]["level"], 0)
        self.assertIn("уровня персонажа", skills[0]["description"])
        self.assertIn("уровень персонажа", skills[0]["damage"])
        self.assertIn("уровень персонажа", skills[1]["damage"])

        player["level"] = 10
        profile = frontend_profile(player)
        frontend_skills = profile["skills"]["active"]
        self.assertEqual(frontend_skills[0]["damage"], "17 (5 + уровень × 1.2)")
        self.assertEqual(frontend_skills[1]["damage"], "15 (4 + уровень × 1.1)")

    def test_skill_points_can_be_spent_through_private_profile_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["free_skill_points"] = 3
            player["skills"]["passive"].append(
                {
                    "id": "focus",
                    "name": "Фокус",
                    "level": 1,
                    "upgradeable": True,
                    "modifiers": [{"id": "clarity", "name": "Ясность", "level": 0}],
                }
            )
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/skills/spend",
                json={"skill_id": "focus", "modifier_id": "clarity", "amount": 2},
            )

            self.assertEqual(response.status_code, 200, response.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["free_skill_points"], 1)
            self.assertEqual(restored["skills"]["passive"][0]["level"], 3)
            self.assertEqual(restored["skills"]["passive"][0]["modifiers"][0]["level"], 2)

    def test_skill_points_cannot_be_spent_through_public_profile_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["free_skill_points"] = 1
            player["skills"]["passive"].append(
                {"id": "focus", "name": "Фокус", "level": 1, "upgradeable": True}
            )
            storage.save_new_player(player, "telegram", "111")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{player['public_id']}/skills/spend",
                json={"skill_id": "focus", "modifier_id": "main", "amount": 1},
            )

            self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
