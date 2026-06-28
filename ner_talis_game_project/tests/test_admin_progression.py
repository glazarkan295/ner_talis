"""Конструкторы прогрессии (чат-ТЗ «уровни/опыт/регистрация/расы»):
валидация, API через общую фабрику, импорт рас, версионирование, RBAC."""

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

from admin_progression_api import (
    create_admin_exp_router,
    create_admin_levels_router,
    create_admin_races_router,
    create_admin_registration_router,
)
from services import admin_rbac as rbac
from services import level_constructor_service as level_svc
from services import race_constructor_service as race_svc
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage

_PATHS = ("LEVEL_CONSTRUCTOR_PATH", "EXP_CONSTRUCTOR_PATH", "REGISTRATION_CONSTRUCTOR_PATH", "RACE_CONSTRUCTOR_PATH")


class ProgressionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = (*_PATHS, "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        for p in _PATHS:
            os.environ[p] = str(base / f"{p.lower()}.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        for factory in (create_admin_levels_router, create_admin_exp_router,
                        create_admin_registration_router, create_admin_races_router):
            app.include_router(factory(lambda: self.storage))
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

    def test_level_validation(self):
        ok = level_svc.store().create("lvl5", {"title": "Уровень 5", "level": 5, "exp_required": 1000})
        self.assertTrue(level_svc.validate(ok)["ok"], level_svc.validate(ok)["errors"])
        bad = level_svc.store().create("bad", {"level": 0, "exp_required": -1})
        self.assertFalse(level_svc.validate(bad)["ok"])

    def test_level_crud_and_publish(self):
        token = self._token()
        c = self.client.post("/api/admin/v2/levels", headers=self._auth(token), json={"id": "lvl1", "data": {"title": "Уровень 1", "level": 1, "exp_required": 0}})
        self.assertEqual(c.status_code, 200, c.text)
        pub = self.client.post("/api/admin/v2/levels/lvl1/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_exp_meta_and_create(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/exp/meta", headers=self._auth(token)).json()
        self.assertTrue(any(s["value"] == "mob_kill" for s in meta["sourceTypes"]))
        c = self.client.post("/api/admin/v2/exp", headers=self._auth(token), json={"id": "from_mobs", "data": {"name": "Опыт с мобов", "source_type": "mob_kill", "base_exp": 10}})
        self.assertEqual(c.status_code, 200, c.text)

    def test_registration_history_rollback(self):
        token = self._token()
        self.client.post("/api/admin/v2/registration", headers=self._auth(token), json={"id": "step_name", "data": {"label": "Имя", "step_type": "name"}})
        self.client.put("/api/admin/v2/registration/step_name", headers=self._auth(token), json={"data": {"label": "Ввод имени"}})
        hist = self.client.get("/api/admin/v2/registration/step_name/history", headers=self._auth(token))
        self.assertIn(1, [h["version"] for h in hist.json()["history"]])
        rb = self.client.post("/api/admin/v2/registration/step_name/rollback", headers=self._auth(token), json={"version": 1})
        self.assertEqual(rb.status_code, 200, rb.text)
        self.assertEqual(self.client.get("/api/admin/v2/registration/step_name", headers=self._auth(token)).json()["item"]["data"]["label"], "Имя")

    def test_race_import_from_data(self):
        token = self._token()
        imp = self.client.post("/api/admin/v2/races/import", headers=self._auth(token), json={})
        self.assertEqual(imp.status_code, 200, imp.text)
        self.assertGreaterEqual(imp.json()["report"]["created"], 3)
        human = self.client.get("/api/admin/v2/races/human", headers=self._auth(token))
        self.assertEqual(human.status_code, 200, human.text)
        self.assertEqual(human.json()["item"]["status"], "published")

    def test_external_url_image_rejected(self):
        env = race_svc.store().create("orc", {"race_name": "Орк", "model_image": "https://evil.example/x.png"})
        self.assertFalse(race_svc.validate(env)["ok"])

    def test_content_cannot_publish_level(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.client.post("/api/admin/v2/levels", headers=self._auth(token), json={"id": "lvl9", "data": {"title": "L9", "level": 9, "exp_required": 1}})
        self.assertEqual(self.client.post("/api/admin/v2/levels/lvl9/publish", headers=self._auth(token), json={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
