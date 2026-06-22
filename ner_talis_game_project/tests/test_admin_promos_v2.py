"""Промокоды + рассылки в V2 (ТЗ §9): эндпоинты, RBAC и аудит."""

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

from admin_promos_api import create_admin_promos_router
from services import admin_rbac as rbac
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class AdminPromosV2Test(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("PROMO_CODES_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["PROMO_CODES_PATH"] = str(base / "promo.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_promos_router(lambda: self.storage))
        self.client = TestClient(app)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _token(self, uid="999"):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id=uid)
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _make_player(self, ext_id):
        races = load_races("data/races.json")
        game_id = self.storage.generate_game_id()
        player = create_player(
            game_id=game_id, platform="telegram", external_user_id=str(ext_id),
            name=f"Игрок{ext_id}", race_id="human", races=races,
        )
        player["level"] = 10
        self.storage.save_new_player(player, "telegram", str(ext_id))
        return game_id

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/promos/meta", headers=self._auth(token)).json()
        self.assertTrue(any(d["value"] == "never" for d in meta["durations"]))
        self.assertTrue(any(a["value"] == "all" for a in meta["audiences"]))

    def test_create_list_delete_promo(self):
        token = self._token()
        create = self.client.post("/api/admin/v2/promos", headers=self._auth(token), json={
            "code": "START100", "uses_left": 5, "duration": "7d",
            "rewards": [{"item_id": "money_copper", "amount": 1000}], "reason": "акция",
        })
        self.assertEqual(create.status_code, 200, create.text)
        listed = self.client.get("/api/admin/v2/promos", headers=self._auth(token)).json()
        self.assertTrue(any(p["code"] == "START100" for p in listed["promos"]))
        deleted = self.client.request("DELETE", "/api/admin/v2/promos?code=START100", headers=self._auth(token))
        self.assertEqual(deleted.status_code, 200, deleted.text)
        listed2 = self.client.get("/api/admin/v2/promos", headers=self._auth(token)).json()
        self.assertFalse(any(p["code"] == "START100" for p in listed2["promos"]))
        actions = {r["action"] for r in read_admin_audit_records()}
        self.assertIn("promo.create", actions)
        self.assertIn("promo.delete", actions)

    def test_unknown_duration_rejected(self):
        token = self._token()
        bad = self.client.post("/api/admin/v2/promos", headers=self._auth(token), json={
            "code": "X", "uses_left": 1, "duration": "forever_and_ever",
            "rewards": [{"item_id": "money_copper", "amount": 1}],
        })
        self.assertEqual(bad.status_code, 400, bad.text)

    def test_broadcast_preview_and_send(self):
        token = self._token()
        for i in range(3):
            self._make_player(500 + i)
        preview = self.client.post("/api/admin/v2/broadcast/preview", headers=self._auth(token), json={"audience": "all"})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertGreaterEqual(preview.json()["recipients"], 3)
        send = self.client.post("/api/admin/v2/broadcast", headers=self._auth(token), json={
            "audience": "all", "message": "Привет, мир! 🎉", "reason": "новость",
        })
        self.assertEqual(send.status_code, 200, send.text)
        self.assertGreaterEqual(send.json()["delivered"], 3)
        self.assertIn("broadcast.send", {r["action"] for r in read_admin_audit_records()})

    def test_rbac_read_only_cannot_manage(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token()
        # read_only видит промокоды, но не создаёт и не рассылает.
        self.assertEqual(self.client.get("/api/admin/v2/promos", headers=self._auth(token)).status_code, 200)
        create = self.client.post("/api/admin/v2/promos", headers=self._auth(token), json={
            "code": "NO", "uses_left": 1, "duration": "never", "rewards": [{"item_id": "money_copper", "amount": 1}],
        })
        self.assertEqual(create.status_code, 403, create.text)
        send = self.client.post("/api/admin/v2/broadcast", headers=self._auth(token), json={"audience": "all", "message": "x"})
        self.assertEqual(send.status_code, 403, send.text)


if __name__ == "__main__":
    unittest.main()
