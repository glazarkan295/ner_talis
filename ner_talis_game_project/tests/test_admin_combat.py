"""Конструктор боевых настроек (ТЗ 20 §1–§4, §10): сервис, валидация, API, RBAC."""

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

from admin_combat_api import create_admin_combat_router
from services import admin_rbac as rbac
from services import combat_constructor_service as combat
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class CombatServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("COMBAT_CONSTRUCTOR_PATH")
        os.environ["COMBAT_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "combat.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("COMBAT_CONSTRUCTOR_PATH", None)
        else:
            os.environ["COMBAT_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_group_timer(self):
        env = combat.store().create("grp", {
            "name": "Групповой бой", "scope": "global", "timer_enabled": True,
            "turn_seconds": 100, "only_group_battles": True, "on_timeout": "skip",
            "warn_before_seconds": 15, "ally_order_type": "by_initiative",
        })
        result = combat.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = combat.store().create("bad", {
            "name": "", "scope": "bogus", "timer_enabled": True, "turn_seconds": 0,
            "on_timeout": "explode",
        })
        result = combat.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("название", joined)
        self.assertIn("область", joined)
        self.assertIn("время на ход", joined)

    def test_warn_after_timer_is_error(self):
        env = combat.store().create("warn1", {
            "name": "X", "scope": "pvp", "timer_enabled": True,
            "turn_seconds": 30, "warn_before_seconds": 60,
        })
        self.assertFalse(combat.validate(env)["ok"])

    def test_group_without_timer_warns(self):
        env = combat.store().create("g2", {"name": "G", "scope": "global", "only_group_battles": True})
        res = combat.validate(env)
        self.assertTrue(res["ok"])
        self.assertTrue(any("групповых" in w for w in res["warnings"]))


class CombatApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("COMBAT_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["COMBAT_CONSTRUCTOR_PATH"] = str(base / "combat.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_combat_router(lambda: self.storage))
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

    def test_meta_defaults(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/combat/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        body = meta.json()
        self.assertEqual(body["defaultTurnSeconds"], 100)
        self.assertIn("global", {s["value"] for s in body["scopes"]})

    def test_create_publish_flow(self):
        token = self._token()
        create = self.client.post("/api/admin/v2/combat", headers=self._auth(token), json={"id": "grp", "data": {"name": "Группа", "scope": "global", "timer_enabled": True, "turn_seconds": 100}})
        self.assertEqual(create.status_code, 200, create.text)
        pub = self.client.post("/api/admin/v2/combat/grp/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_content_cannot_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self.client.post("/api/admin/v2/combat", headers=self._auth(token), json={"id": "c1", "data": {"name": "C", "scope": "pve"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/combat/c1/publish", headers=self._auth(token), json={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
