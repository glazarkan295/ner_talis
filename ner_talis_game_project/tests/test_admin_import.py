"""Единый импорт-эндпоинт V2: режимы, защита от импорта-всего, проверка."""

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

from admin_import_api import create_admin_import_router
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage

_STORE_ENVS = (
    "ITEM_CONSTRUCTOR_PATH", "WORLD_CONTENT_PATH", "EFFECT_CONSTRUCTOR_PATH",
    "CITY_CONSTRUCTOR_PATH", "ACHIEVEMENTS_PATH", "ACHIEVEMENT_CATEGORIES_PATH",
    "FINE_CONSTRUCTOR_PATH", "SKILL_CONSTRUCTOR_PATH",
)


class AdminImportApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = _STORE_ENVS + ("ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        for env in _STORE_ENVS:
            os.environ[env] = str(base / f"{env.lower()}.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_import_router(lambda: self.storage))
        self.client = TestClient(app)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _token(self):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id="999")
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_only_unknown_kinds_rejected(self):
        # Codex P1: список только из неизвестных типов → 400, а не «импортировать всё».
        token = self._token()
        resp = self.client.post("/api/admin/v2/import/run", headers=self._auth(token), json={"kinds": ["bogus", "typo"], "mode": "new"})
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_valid_kind_imports_only_that(self):
        token = self._token()
        resp = self.client.post("/api/admin/v2/import/run", headers=self._auth(token), json={"kinds": ["fine_def"], "mode": "new"})
        self.assertEqual(resp.status_code, 200, resp.text)
        kinds = {r["kind"] for r in resp.json()["reports"]}
        self.assertEqual(kinds, {"fine_def"})

    def test_check_endpoint(self):
        token = self._token()
        resp = self.client.post("/api/admin/v2/import/check", headers=self._auth(token), json={})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("report", resp.json())


if __name__ == "__main__":
    unittest.main()
