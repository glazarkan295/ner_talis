"""Конструкторы черт/благословений/фаз (ТЗ «черты/благословения/фазы»):
сервис-валидация, API, импорт-сид, версионирование, RBAC."""

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

from admin_trait_api import create_admin_trait_router
from admin_blessing_api import create_admin_blessing_router
from admin_phase_api import create_admin_phase_router
from services import admin_rbac as rbac
from services import trait_constructor_service as traits
from services import blessing_constructor_service as blessings
from services import phase_constructor_service as phases
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage

_PATHS = ("TRAIT_CONSTRUCTOR_PATH", "BLESSING_CONSTRUCTOR_PATH", "PHASE_CONSTRUCTOR_PATH")


class _Base(unittest.TestCase):
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
        app.include_router(create_admin_trait_router(lambda: self.storage))
        app.include_router(create_admin_blessing_router(lambda: self.storage))
        app.include_router(create_admin_phase_router(lambda: self.storage))
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


class TraitConstructorTest(_Base):
    def test_validate_rank_and_categories(self):
        ok = traits.store().create("t_ok", {"trait_name": "Крепкая шкура", "trait_rank": "special", "trigger": "passive"})
        self.assertTrue(traits.validate(ok)["ok"], traits.validate(ok)["errors"])
        bad = traits.store().create("t_bad", {"trait_name": "", "trait_rank": "godlike"})
        self.assertFalse(traits.validate(bad)["ok"])

    def test_import_seeds_50_and_publish_flow(self):
        token = self._token()
        imp = self.client.post("/api/admin/v2/traits/import", headers=self._auth(token), json={})
        self.assertEqual(imp.status_code, 200, imp.text)
        self.assertGreaterEqual(imp.json()["report"]["created"], 50)
        items = self.client.get("/api/admin/v2/traits", headers=self._auth(token)).json()["items"]
        self.assertTrue(any(i["id"] == "tough_hide" and i["status"] == "published" for i in items))

    def test_history_and_content_cannot_publish(self):
        token = self._token()
        self.client.post("/api/admin/v2/traits", headers=self._auth(token), json={"id": "tt", "data": {"trait_name": "T", "trait_rank": "elite"}})
        self.client.put("/api/admin/v2/traits/tt", headers=self._auth(token), json={"data": {"trait_name": "T2"}})
        hist = self.client.get("/api/admin/v2/traits/tt/history", headers=self._auth(token))
        self.assertIn(1, [h["version"] for h in hist.json()["history"]])
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        ct = self._token()
        self.assertEqual(self.client.post("/api/admin/v2/traits/tt/publish", headers=self._auth(ct), json={}).status_code, 403)

    def test_published_edit_requires_publish(self):
        # 18-CODEX §2: published черту нельзя править без trait.publish; черновик — можно.
        token = self._token()  # owner
        self.client.post("/api/admin/v2/traits/import", headers=self._auth(token), json={})
        # owner (есть publish) правит published — можно.
        self.assertEqual(self.client.put("/api/admin/v2/traits/tough_hide", headers=self._auth(token), json={"data": {"trait_name": "Крепкая шкура+"}}).status_code, 200)
        self.client.post("/api/admin/v2/traits", headers=self._auth(token), json={"id": "drft", "data": {"trait_name": "D", "trait_rank": "special", "trigger": "passive"}})
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        ct = self._token()
        # content правит ЧЕРНОВИК — можно.
        self.assertEqual(self.client.put("/api/admin/v2/traits/drft", headers=self._auth(ct), json={"data": {"trait_name": "D2"}}).status_code, 200)
        # content правит PUBLISHED — 403.
        self.assertEqual(self.client.put("/api/admin/v2/traits/tough_hide", headers=self._auth(ct), json={"data": {"trait_name": "X"}}).status_code, 403)


class BlessingConstructorTest(_Base):
    def test_published_edit_requires_publish(self):
        # 18-CODEX §2: published благословение нельзя править без blessing.publish.
        token = self._token()
        self.client.post("/api/admin/v2/blessings/import", headers=self._auth(token), json={})
        self.client.post("/api/admin/v2/blessings", headers=self._auth(token), json={"id": "bdrft", "data": {"blessing_name": "B", "source_type": "item", "allowed_targets": ["player"], "player_text": "x"}})
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        ct = self._token()
        self.assertEqual(self.client.put("/api/admin/v2/blessings/bdrft", headers=self._auth(ct), json={"data": {"player_text": "y"}}).status_code, 200)
        self.assertEqual(self.client.put("/api/admin/v2/blessings/blessing_strength", headers=self._auth(ct), json={"data": {"player_text": "z"}}).status_code, 403)

    def test_import_seeds_and_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/blessings/meta", headers=self._auth(token)).json()
        self.assertTrue(any(s["value"] == "boss_phase" for s in meta["sourceTypes"]))
        imp = self.client.post("/api/admin/v2/blessings/import", headers=self._auth(token), json={})
        self.assertGreaterEqual(imp.json()["report"]["created"], 19)
        self.assertEqual(self.client.get("/api/admin/v2/blessings/blessing_strength", headers=self._auth(token)).json()["item"]["status"], "published")


class PhaseConstructorTest(_Base):
    def test_validate_hp_trigger_range(self):
        bad = phases.store().create("p_bad", {"phase_name": "X", "trigger_type": "hp_percent", "trigger_value": 250})
        self.assertFalse(phases.validate(bad)["ok"])

    def test_published_edit_requires_publish(self):
        # 18-CODEX §2: published фазу нельзя править без phase.publish.
        token = self._token()
        self.client.post("/api/admin/v2/phases/import", headers=self._auth(token), json={})
        self.client.post("/api/admin/v2/phases", headers=self._auth(token), json={"id": "pdrft", "data": {"phase_name": "P", "trigger_type": "manual", "trigger_value": 0}})
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        ct = self._token()
        self.assertEqual(self.client.put("/api/admin/v2/phases/pdrft", headers=self._auth(ct), json={"data": {"phase_name": "P2"}}).status_code, 200)
        self.assertEqual(self.client.put("/api/admin/v2/phases/phase_rage", headers=self._auth(ct), json={"data": {"phase_name": "X"}}).status_code, 403)

    def test_import_seeds_and_rollback(self):
        token = self._token()
        imp = self.client.post("/api/admin/v2/phases/import", headers=self._auth(token), json={})
        self.assertGreaterEqual(imp.json()["report"]["created"], 20)
        self.client.put("/api/admin/v2/phases/phase_rage", headers=self._auth(token), json={"data": {"phase_name": "Изм"}})
        rb = self.client.post("/api/admin/v2/phases/phase_rage/rollback", headers=self._auth(token), json={"version": 1})
        self.assertEqual(rb.status_code, 200, rb.text)
        self.assertEqual(self.client.get("/api/admin/v2/phases/phase_rage", headers=self._auth(token)).json()["item"]["data"]["phase_name"], "Фаза ярости")


if __name__ == "__main__":
    unittest.main()
