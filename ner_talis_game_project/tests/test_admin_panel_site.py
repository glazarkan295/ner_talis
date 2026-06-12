import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from admin_panel_api import create_admin_panel_router
from services.admin_command_service import execute_admin_command
from services.admin_panel_service import create_admin_panel_activation_token, build_admin_panel_url
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class AdminPanelSiteTest(unittest.TestCase):
    def _make_player(self, storage, *, name="АдминПанель", platform="telegram", external_user_id="111"):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform=platform,
            external_user_id=external_user_id,
            name=name,
            race_id="human",
            races=races,
        )
        player["money"] = 10
        player["money_copper"] = 10
        storage.save_new_player(player, platform, external_user_id)
        return game_id

    def _client(self, storage):
        app = FastAPI()
        app.include_router(create_admin_panel_router(lambda: storage))
        return TestClient(app)

    def test_admin_panel_token_is_one_time_and_unlocks_catalog(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["SITE_BASE_URL"] = "https://example.test"
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            token = create_admin_panel_activation_token(storage, platform="telegram", admin_user_id="999", chat_id="-100")
            self.assertIn("/admin_panel?token=", build_admin_panel_url(token))
            client = self._client(storage)

            activated = client.get(f"/api/admin/session/{token}")
            self.assertEqual(activated.status_code, 200, activated.text)
            session_token = activated.json()["sessionToken"]
            self.assertNotEqual(session_token, token)

            reused = client.get(f"/api/admin/session/{token}")
            self.assertEqual(reused.status_code, 401)

            catalog = client.get(f"/api/admin/catalog?token={session_token}")
            self.assertEqual(catalog.status_code, 200, catalog.text)
            item_ids = {item["item_id"] for item in catalog.json()["items"]}
            self.assertIn("money_copper", item_ids)
            self.assertIn("experience_shards", item_ids)

    def test_admin_panel_delivery_routes_special_rewards_to_balance_and_items_to_inventory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(tmp_dir) / "audit.log")
            os.environ["ADMIN_BACKUP_DIR"] = str(Path(tmp_dir) / "backups")
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)
            token = create_admin_panel_activation_token(storage, platform="telegram", admin_user_id="999")
            client = self._client(storage)
            session_token = client.get(f"/api/admin/session/{token}").json()["sessionToken"]

            response = client.post("/api/admin/delivery/send", json={
                "token": session_token,
                "target_game_id": game_id,
                "rewards": [
                    {"item_id": "money_copper", "amount": 25},
                    {"item_id": "free_skill_points", "amount": 2},
                    {"item_id": "free_stat_points", "amount": 3},
                    {"item_id": "experience_shards", "amount": 100},
                    {"item_id": "dried_meat", "amount": 1},
                ],
            })
            self.assertEqual(response.status_code, 200, response.text)
            player = storage.get_player_by_game_id(game_id)
            self.assertEqual(player["money"], 35)
            self.assertEqual(player["free_skill_points"], 4)  # +2 reward, +2 for level-up
            self.assertEqual(player["free_stat_points"], 8)   # +3 reward, +5 for level-up
            self.assertEqual(player["level"], 2)
            self.assertTrue(any(item.get("item_id") == "dried_meat" for item in player["inventory"]))
            self.assertIn("Дар свыше", player["pending_bot_messages"][-1]["text"])

    def test_admin_panel_promo_create_and_player_view_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage, name="Просмотр")
            token = create_admin_panel_activation_token(storage, platform="vk", admin_user_id="555")
            client = self._client(storage)
            session_token = client.get(f"/api/admin/session/{token}").json()["sessionToken"]

            promo = client.post("/api/admin/promos", json={
                "token": session_token,
                "code": "PANEL100",
                "uses_left": 5,
                "duration": "1h",
                "rewards": [{"item_id": "money_copper", "amount": 100}],
            })
            self.assertEqual(promo.status_code, 200, promo.text)
            self.assertEqual(promo.json()["promo"]["reward"]["money"], 100)
            self.assertIsNotNone(promo.json()["promo"]["expires_at"])

            view = client.post(f"/api/admin/players/{game_id}/view-token", json={"token": session_token})
            self.assertEqual(view.status_code, 200, view.text)
            profile = client.get(f"/api/admin/player-view/{view.json()['token']}")
            self.assertEqual(profile.status_code, 200, profile.text)
            self.assertTrue(profile.json()["profile"]["readOnly"])
            self.assertEqual(profile.json()["session"]["target_game_id"], game_id)

    def test_sqlite_persists_admin_sessions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "players.sqlite3"
            storage = SQLiteStorage(str(path))
            token = create_admin_panel_activation_token(storage, platform="telegram", admin_user_id="999")
            storage2 = SQLiteStorage(str(path))
            client = self._client(storage2)
            response = client.get(f"/api/admin/session/{token}")
            self.assertEqual(response.status_code, 200, response.text)

    def test_admin_panel_command_returns_link(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["SITE_BASE_URL"] = "https://example.test"
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            result = execute_admin_command(text="/admin_panel", storage=storage, platform="telegram", admin_user_id="999")
            self.assertTrue(result.handled)
            self.assertIn("Админ-панель", result.text)
            self.assertIn("https://example.test/admin_panel?token=", result.text)


if __name__ == "__main__":
    unittest.main()
