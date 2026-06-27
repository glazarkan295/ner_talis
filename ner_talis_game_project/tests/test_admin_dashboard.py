"""Dashboard админ-панели (ТЗ 11 §16): сервис + API."""

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

from admin_dashboard_api import create_admin_dashboard_router
from services import admin_dashboard_service as dash
from services import item_constructor_service as ics
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage

_STORE_ENVS = (
    "ITEM_CONSTRUCTOR_PATH", "WORLD_CONTENT_PATH", "EFFECT_CONSTRUCTOR_PATH",
    "ACHIEVEMENTS_PATH", "RECIPE_CONSTRUCTOR_PATH", "REPUTATION_CONSTRUCTOR_PATH",
    "TEXT_CONSTRUCTOR_PATH", "WORLD_EVENTS_PATH", "ADMIN_AUDIT_LOG_PATH",
)


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = _STORE_ENVS + ("ADMIN_ROLES_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        for env in _STORE_ENVS:
            os.environ[env] = str(base / f"{env.lower()}.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_dashboard_router(lambda: self.storage))
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

    def test_summary_counts_constructors(self):
        ics.store().create("sword", {"name": "Меч", "category": "Оружие"})
        report = dash.summary(self.storage)
        self.assertIn("totals", report)
        self.assertIn("constructors", report)
        item_stat = next((c for c in report["constructors"] if c["key"] == "item"), None)
        self.assertIsNotNone(item_stat)
        self.assertGreaterEqual(item_stat["total"], 1)
        self.assertGreaterEqual(report["totals"]["objects"], 1)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/dashboard").status_code, 401)

    def test_endpoint_returns_summary(self):
        token = self._token()
        r = self.client.get("/api/admin/v2/dashboard", headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        for key in ("totals", "constructors", "recent_changes"):
            self.assertIn(key, body)


if __name__ == "__main__":
    unittest.main()
