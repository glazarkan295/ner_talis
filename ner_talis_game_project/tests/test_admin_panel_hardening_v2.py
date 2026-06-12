import base64
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
from services.admin_panel_service import create_admin_panel_activation_token
import services.admin_panel_service as admin_panel_service
from services.registration_service import create_player, load_races
from services.web_profile import PROFILE_SCOPE
from storage.json_storage import JsonStorage


def _one_pixel_png_base64() -> str:
    from io import BytesIO
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class AdminPanelHardeningV2Test(unittest.TestCase):
    def _make_player(self, storage, *, name="Игрок"):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="111",
            name=name,
            race_id="human",
            races=races,
        )
        storage.save_new_player(player, "telegram", "111")
        return player

    def test_profile_session_token_works_through_bearer_header(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._make_player(storage)
            activation = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")
            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)

            activated = client.get(f"/api/profile/session/{activation}")
            self.assertEqual(activated.status_code, 200, activated.text)
            session_token = activated.json()["sessionToken"]

            old_url = client.get(f"/api/profile/{activation}")
            self.assertEqual(old_url.status_code, 401)

            current = client.get("/api/profile/me", headers={"Authorization": f"Bearer {session_token}"})
            self.assertEqual(current.status_code, 200, current.text)
            self.assertEqual(current.json()["player"]["userGlobalId"], player["game_id"])

    def test_admin_panel_accepts_bearer_and_rejects_fake_image_upload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            token = create_admin_panel_activation_token(storage, platform="telegram", admin_user_id="999")
            app = FastAPI()
            app.include_router(create_admin_panel_router(lambda: storage))
            client = TestClient(app)
            session_token = client.get(f"/api/admin/session/{token}").json()["sessionToken"]

            catalog = client.get("/api/admin/catalog", headers={"Authorization": f"Bearer {session_token}"})
            self.assertEqual(catalog.status_code, 200, catalog.text)

            fake = base64.b64encode(b"not really a png").decode("ascii")
            response = client.post(
                "/api/admin/catalog/dried_meat/image",
                headers={"Authorization": f"Bearer {session_token}"},
                json={"filename": "bad.png", "content_base64": fake, "content_type": "image/png"},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("PNG", response.text)

    def test_admin_upload_is_saved_to_runtime_public_uploads(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_uploads_dir = admin_panel_service.PUBLIC_UPLOADS_ASSETS_DIR
            project_root = ROOT_DIR.parent
            snapshots = {path: path.read_bytes() for path in (project_root / "data").glob("*.json")}
            audit_path = project_root / "data" / "admin_audit.log"
            audit_snapshot = audit_path.read_bytes() if audit_path.exists() else None
            admin_panel_service.PUBLIC_UPLOADS_ASSETS_DIR = str(Path(tmp_dir) / "public_uploads" / "assets")
            try:
                storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
                token = create_admin_panel_activation_token(storage, platform="telegram", admin_user_id="999")
                app = FastAPI()
                app.include_router(create_admin_panel_router(lambda: storage))
                client = TestClient(app)
                session_token = client.get(f"/api/admin/session/{token}").json()["sessionToken"]

                response = client.post(
                    "/api/admin/catalog/dried_meat/image",
                    headers={"Authorization": f"Bearer {session_token}"},
                    json={"filename": "new.png", "content_base64": _one_pixel_png_base64(), "content_type": "image/png"},
                )
                self.assertEqual(response.status_code, 200, response.text)
                asset_path = response.json()["asset_path"]
                self.assertTrue(asset_path.startswith("/assets/admin_uploads/items/dried_meat"))
                saved = Path(admin_panel_service.PUBLIC_UPLOADS_ASSETS_DIR) / asset_path.removeprefix("/assets/")
                self.assertTrue(saved.exists(), saved)
                self.assertFalse(str(saved).endswith("web/public/assets/admin_uploads/items/dried_meat.png"))
            finally:
                admin_panel_service.PUBLIC_UPLOADS_ASSETS_DIR = old_uploads_dir
                for path, content in snapshots.items():
                    path.write_bytes(content)
                if audit_snapshot is None:
                    try:
                        audit_path.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    audit_path.write_bytes(audit_snapshot)
                try:
                    from services.item_registry import load_all_item_definitions, load_item_definitions, _indexes
                    load_all_item_definitions.cache_clear(); load_item_definitions.cache_clear(); _indexes.cache_clear()
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
