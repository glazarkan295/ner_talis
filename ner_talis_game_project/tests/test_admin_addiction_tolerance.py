"""Конструкторы зависимости (§4) и привыкания (§5): валидация, расчёты, граф, API."""

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

from admin_addiction_tolerance_api import (
    create_admin_addiction_router, create_admin_tolerance_router,
)
from services import addiction_constructor_service as addiction
from services import tolerance_constructor_service as tolerance
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class AddictionValidateTest(unittest.TestCase):
    def _v(self, data):
        return addiction.validate({"data": data})

    def test_valid(self):
        r = self._v({"name_admin": "Стимулятор", "addiction_value_max": 100,
                     "addiction_value_min": 0, "default_value": 0})
        self.assertTrue(r["ok"], r["errors"])

    def test_requires_max(self):
        self.assertFalse(self._v({"name_admin": "X"})["ok"])

    def test_overlapping_stages(self):
        bad = [{"stage_id": "a", "min_value": 0, "max_value": 40},
               {"stage_id": "b", "min_value": 30, "max_value": 60}]
        self.assertFalse(self._v({"name_admin": "X", "addiction_value_max": 100, "stages": bad})["ok"])

    def test_stage_for_value(self):
        data = {"stages": [{"stage_id": "tyaga", "min_value": 30, "max_value": 59}]}
        self.assertEqual(addiction.stage_for_value(data, 45)["stage_id"], "tyaga")


class ToleranceValidateTest(unittest.TestCase):
    def _v(self, data):
        return tolerance.validate({"data": data})

    def test_valid(self):
        r = self._v({"name_admin": "Зелья лечения", "min_effectiveness_percent": 50,
                     "value_min": 0, "value_max": 100})
        self.assertTrue(r["ok"], r["errors"])

    def test_requires_min_effectiveness(self):
        self.assertFalse(self._v({"name_admin": "X"})["ok"])

    def test_effectiveness_formula(self):
        data = {"min_effectiveness_percent": 50, "effectiveness_loss_per_value": 1}
        self.assertEqual(tolerance.effectiveness(data, 30), 70)
        self.assertEqual(tolerance.effectiveness(data, 90), 50)  # ограничено минимумом


class GraphTest(unittest.TestCase):
    ENVS = ("ADDICTION_CONSTRUCTOR_PATH", "TOLERANCE_CONSTRUCTOR_PATH")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in self.ENVS}
        for k in self.ENVS:
            os.environ[k] = str(base / f"{k.lower()}.json")
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_nodes_in_graph(self):
        from services import admin_graph_service as graph
        addiction.store().create("stim", {"name_admin": "Стимулятор", "addiction_value_max": 100})
        tolerance.store().create("heal_tol", {"name_admin": "Зелья", "min_effectiveness_percent": 50})
        ids = {n["id"] for n in graph.full_graph()["nodes"]}
        self.assertIn("addiction:stim", ids)
        self.assertIn("tolerance:heal_tol", ids)


class ApiTest(unittest.TestCase):
    ENVS = ("ADDICTION_CONSTRUCTOR_PATH", "TOLERANCE_CONSTRUCTOR_PATH")

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
        app = FastAPI()
        app.include_router(create_admin_addiction_router(lambda: self.storage))
        app.include_router(create_admin_tolerance_router(lambda: self.storage))
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

    def test_addiction_meta_create_stage(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/addictions/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        self.assertIn("player", meta.json()["scopes"])
        self.client.post("/api/admin/v2/addictions", headers=self._auth(token), json={
            "id": "stim", "data": {"name_admin": "Стимулятор", "addiction_value_max": 100,
                                   "stages": [{"stage_id": "tyaga", "min_value": 30, "max_value": 59}]}})
        st = self.client.post("/api/admin/v2/addictions/stim/stage", headers=self._auth(token), json={"value": 45})
        self.assertEqual(st.json()["stage"]["stage_id"], "tyaga")

    def test_tolerance_effectiveness_endpoint(self):
        token = self._token()
        self.client.post("/api/admin/v2/tolerances", headers=self._auth(token), json={
            "id": "heal", "data": {"name_admin": "Зелья", "min_effectiveness_percent": 50,
                                   "effectiveness_loss_per_value": 1}})
        r = self.client.post("/api/admin/v2/tolerances/heal/effectiveness", headers=self._auth(token), json={"value": 30})
        self.assertEqual(r.json()["effectiveness"], 70)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/tolerances/meta").status_code, 401)


if __name__ == "__main__":
    unittest.main()
