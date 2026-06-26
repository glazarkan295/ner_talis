"""Расширенное ремесло (ТЗ 13 §5): профессии и мастерские — валидаторы, API, граф."""

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

from admin_craft_api import create_admin_profession_router, create_admin_workshop_router
from services import profession_constructor_service as professions
from services import workshop_constructor_service as workshops
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class _Base(unittest.TestCase):
    ENVS = ("PROFESSION_CONSTRUCTOR_PATH", "WORKSHOP_CONSTRUCTOR_PATH",
            "WORLD_CONTENT_PATH", "FORMULA_CONSTRUCTOR_PATH")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = self.ENVS + ("ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        for k in self.ENVS:
            os.environ[k] = str(base / f"{k.lower()}.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class ValidateTest(_Base):
    def test_profession_valid(self):
        env = professions.store().create("smithing", {"name": "Кузнечное дело", "profession_type": "smithing", "max_level": 50, "start_level": 1})
        self.assertTrue(professions.validate(env)["ok"], professions.validate(env)["errors"])

    def test_profession_start_gt_max(self):
        env = professions.store().create("bad", {"name": "X", "max_level": 5, "start_level": 9})
        self.assertFalse(professions.validate(env)["ok"])

    def test_workshop_valid(self):
        env = workshops.store().create("forge1", {"name": "Городская кузница", "type": "forge", "location": "seldar"})
        self.assertTrue(workshops.validate(env)["ok"], workshops.validate(env)["errors"])

    def test_workshop_bad_type(self):
        env = workshops.store().create("w2", {"name": "X", "type": "nonsense"})
        self.assertFalse(workshops.validate(env)["ok"])

    def test_workshop_http_image_rejected(self):
        env = workshops.store().create("w3", {"name": "X", "type": "forge", "image": "https://evil/x.png"})
        self.assertFalse(workshops.validate(env)["ok"])


class GraphTest(_Base):
    def test_workshop_and_profession_in_graph(self):
        from services import world_content_registry as wcr
        from services import formula_constructor_service as fx
        from services import admin_graph_service as graph
        wcr.create_content(wcr.KIND_LOCATION, "seldar", {"name": "Селдар", "short_description": "город"})
        fx.store().create("prof_exp", {"name": "Опыт профессии", "expression": "base_amount * 2", "variables": [{"key": "base_amount"}]})
        workshops.store().create("forge1", {"name": "Кузница", "type": "forge", "location": "seldar"})
        professions.store().create("smithing", {"name": "Кузнечное", "max_level": 50, "exp_formula_id": "prof_exp"})
        g = graph.full_graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("workshop:forge1", ids)
        self.assertIn("profession:smithing", ids)
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("workshop:forge1", "location:seldar", "in_location"), pairs)
        self.assertIn(("profession:smithing", "formula:prof_exp", "uses_formula"), pairs)


class ApiTest(_Base):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(create_admin_profession_router(lambda: self.storage))
        app.include_router(create_admin_workshop_router(lambda: self.storage))
        self.client = TestClient(app)

    def _token(self):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id="999")
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_profession_meta_and_publish(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/professions/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        self.assertTrue(any(p["value"] == "smithing" for p in meta.json()["professionTypes"]))
        self.client.post("/api/admin/v2/professions", headers=self._auth(token), json={"id": "alch", "data": {"name": "Алхимия", "profession_type": "alchemy", "max_level": 30}})
        pub = self.client.post("/api/admin/v2/professions/alch/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_workshop_meta_and_create(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/workshops/meta", headers=self._auth(token))
        self.assertTrue(any(w["value"] == "forge" for w in meta.json()["workshopTypes"]))
        c = self.client.post("/api/admin/v2/workshops", headers=self._auth(token), json={"id": "smelt1", "data": {"name": "Плавильня", "type": "smeltery"}})
        self.assertEqual(c.status_code, 200, c.text)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/professions/meta").status_code, 401)


if __name__ == "__main__":
    unittest.main()
