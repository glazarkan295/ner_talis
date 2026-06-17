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
from site_api import create_profile_api_router
from services.admin_panel_service import (
    admin_player_detail,
    create_admin_panel_activation_token,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage

TELEGRAM = "telegram"


class AdminProfileEditTest(unittest.TestCase):
    def _make_player(self, storage, *, name="Подопечный", external_user_id="111"):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform=TELEGRAM,
            external_user_id=external_user_id,
            name=name,
            race_id="human",
            races=races,
        )
        player["inventory"] = [{
            "id": "dried_meat",
            "item_id": "dried_meat",
            "name": "Сушёное мясо",
            "amount": 4,
            "category": "Расходники",
            "stackable": True,
            "max_stack": 99,
        }]
        storage.save_new_player(player, TELEGRAM, external_user_id)
        return game_id

    def _client(self, storage):
        app = FastAPI()
        app.include_router(create_admin_panel_router(lambda: storage))
        app.include_router(create_profile_api_router(lambda: storage))
        return TestClient(app)

    def test_admin_view_returns_edit_token_and_allows_item_removal(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage)
            token = create_admin_panel_activation_token(storage, platform=TELEGRAM, admin_user_id="999")
            client = self._client(storage)
            session_token = client.get(f"/api/admin/session/{token}").json()["sessionToken"]

            view = client.post(f"/api/admin/players/{game_id}/view-token", json={"token": session_token})
            self.assertEqual(view.status_code, 200, view.text)
            profile = client.get(f"/api/admin/player-view/{view.json()['token']}")
            self.assertEqual(profile.status_code, 200, profile.text)
            edit_token = profile.json()["editToken"]
            self.assertTrue(edit_token)
            self.assertTrue(profile.json()["profile"]["adminEdit"])

            # Admin removes the whole stack from the player's profile via the
            # normal profile drop endpoint, authorized by the edit token.
            removed = client.post(
                "/api/profile/me/inventory/drop",
                headers={"Authorization": f"Bearer {edit_token}"},
                json={"item_id": "dried_meat", "amount": 4, "inventory_index": 0},
            )
            self.assertEqual(removed.status_code, 200, removed.text)
            updated = storage.get_player_by_game_id(game_id)
            self.assertFalse(any(item.get("item_id") == "dried_meat" for item in updated.get("inventory", [])))

    def test_admin_edit_token_can_change_profile_field(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage, name="СтароеИмя", external_user_id="222")
            token = create_admin_panel_activation_token(storage, platform=TELEGRAM, admin_user_id="999")
            client = self._client(storage)
            session_token = client.get(f"/api/admin/session/{token}").json()["sessionToken"]
            view = client.post(f"/api/admin/players/{game_id}/view-token", json={"token": session_token})
            edit_token = client.get(f"/api/admin/player-view/{view.json()['token']}").json()["editToken"]

            edited = client.post(
                "/api/profile/me/profile/edit-field",
                headers={"Authorization": f"Bearer {edit_token}"},
                json={"field": "name", "value": "НовоеИмя"},
            )
            self.assertEqual(edited.status_code, 200, edited.text)
            self.assertEqual(storage.get_player_by_game_id(game_id)["name"], "НовоеИмя")

    def test_player_detail_includes_last_activity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage, external_user_id="333")
            player = storage.get_player_by_game_id(game_id)
            player["last_activity_at"] = "2026-06-15T08:30:00+00:00"
            storage.update_player(player)

            detail = admin_player_detail(storage, game_id)
            self.assertEqual(detail["last_activity"], "15.06.26")

    def test_player_detail_last_activity_dash_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            game_id = self._make_player(storage, external_user_id="444")
            detail = admin_player_detail(storage, game_id)
            self.assertEqual(detail["last_activity"], "—")


if __name__ == "__main__":
    unittest.main()
