"""Конструктор лагеря (доп. ТЗ §4): валидация + API + RBAC + версионирование."""

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

from admin_camp_api import create_admin_camp_router
from services import admin_rbac as rbac
from services import camp_constructor_service as camps
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class CampServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("CAMP_CONSTRUCTOR_PATH")
        os.environ["CAMP_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "camps.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("CAMP_CONSTRUCTOR_PATH", None)
        else:
            os.environ["CAMP_CONSTRUCTOR_PATH"] = self._saved

    def test_validate_requires_name_and_type(self):
        ok = camps.store().create("safe_glade", {"name": "Поляна", "camp_type": "safe"})
        self.assertTrue(camps.validate(ok)["ok"], camps.validate(ok)["errors"])
        bad = camps.store().create("bad", {"name": "", "camp_type": "teleport"})
        res = camps.validate(bad)
        self.assertFalse(res["ok"])

    def test_published_for_location(self):
        camps.store().create("c1", {"name": "Лагерь у реки", "camp_type": "standard", "locations": ["hilly_meadows"]})
        camps.store().set_status("c1", camps.STATUS_PUBLISHED, force=True)
        found = camps.published_for_location("hilly_meadows")
        self.assertTrue(any(c["id"] == "c1" for c in found))
        self.assertEqual(camps.published_for_location("nowhere"), [])


class CampApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("CAMP_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["CAMP_CONSTRUCTOR_PATH"] = str(base / "camps.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_camp_router(lambda: self.storage))
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

    def _create(self, token, cid="safe_glade", data=None):
        return self.client.post("/api/admin/v2/camps", headers=self._auth(token), json={"id": cid, "data": data or {"name": "Поляна", "camp_type": "safe"}})

    def test_meta_and_publish_flow(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/camps/meta", headers=self._auth(token)).json()
        self.assertIn("safe", meta["campTypes"])
        self.assertEqual(self._create(token).status_code, 200)
        publish = self.client.post("/api/admin/v2/camps/safe_glade/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")

    def test_import_reports_needs_check(self):
        token = self._token()
        resp = self.client.post("/api/admin/v2/camps/import", headers=self._auth(token), json={})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["report"]["needs_check"])

    def test_history_and_rollback(self):
        token = self._token()
        self._create(token)
        self.client.put("/api/admin/v2/camps/safe_glade", headers=self._auth(token), json={"data": {"name": "Новая поляна"}})
        hist = self.client.get("/api/admin/v2/camps/safe_glade/history", headers=self._auth(token))
        self.assertEqual(hist.status_code, 200, hist.text)
        self.assertIn(1, [h["version"] for h in hist.json()["history"]])
        rb = self.client.post("/api/admin/v2/camps/safe_glade/rollback", headers=self._auth(token), json={"version": 1})
        self.assertEqual(rb.status_code, 200, rb.text)
        self.assertEqual(self.client.get("/api/admin/v2/camps/safe_glade", headers=self._auth(token)).json()["item"]["data"]["name"], "Поляна")

    def test_content_can_draft_but_not_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/camps/safe_glade/publish", headers=self._auth(token), json={}).status_code, 403)

    def test_published_edit_requires_publish(self):
        # 18-CODEX §2: published лагерь нельзя править без camp.publish; черновик — можно.
        token = self._token()  # owner
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/camps/safe_glade/publish", headers=self._auth(token), json={}).status_code, 200)
        self._create(token, cid="cdrft")  # черновик
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        ct = self._token()
        self.assertEqual(self.client.put("/api/admin/v2/camps/cdrft", headers=self._auth(ct), json={"data": {"name": "Черновик 2"}}).status_code, 200)
        self.assertEqual(self.client.put("/api/admin/v2/camps/safe_glade", headers=self._auth(ct), json={"data": {"name": "X"}}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
