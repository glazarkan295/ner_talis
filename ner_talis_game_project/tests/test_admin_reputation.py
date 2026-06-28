"""Конструктор репутации (item-reputation §3, эффекты §3): валидация, стадии,
предпросмотр, граф, API."""

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

from admin_reputation_api import create_admin_reputation_router
from services import reputation_constructor_service as rep
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


def _v(data):
    return rep.validate({"data": data})


_STAGES = [
    {"stage_id": "calm", "name_ru": "Спокойно", "min_value": 0, "max_value": 20},
    {"stage_id": "watch", "name_ru": "Наблюдение", "min_value": 21, "max_value": 50},
    {"stage_id": "danger", "name_ru": "Опасность", "min_value": 51, "max_value": 100},
]


class ValidateTest(unittest.TestCase):
    def test_valid(self):
        r = _v({"name_ru": "Подозрение стражи", "visibility": "hidden", "min_value": 0,
                "max_value": 100, "default_value": 0, "stages": _STAGES, "show_to_player": False})
        self.assertTrue(r["ok"], r["errors"])

    def test_default_out_of_range(self):
        self.assertFalse(_v({"name_ru": "X", "min_value": 0, "max_value": 10, "default_value": 50})["ok"])

    def test_overlapping_stages(self):
        bad = [{"stage_id": "a", "min_value": 0, "max_value": 30},
               {"stage_id": "b", "min_value": 20, "max_value": 50}]
        self.assertFalse(_v({"name_ru": "X", "min_value": 0, "max_value": 50, "stages": bad})["ok"])

    def test_gap_warns(self):
        gap = [{"stage_id": "a", "min_value": 0, "max_value": 10},
               {"stage_id": "b", "min_value": 30, "max_value": 50}]
        r = _v({"name_ru": "X", "min_value": 0, "max_value": 50, "stages": gap})
        self.assertTrue(any("пустой диапазон" in w for w in r["warnings"]))

    def test_visible_but_hidden_warns(self):
        r = _v({"name_ru": "X", "visibility": "visible", "show_to_player": False})
        self.assertTrue(any("скрыта от игрока" in w for w in r["warnings"]))

    def test_hidden_shows_exact_warns(self):
        r = _v({"name_ru": "X", "visibility": "hidden", "show_exact_value": True})
        self.assertTrue(any("точное значение" in w for w in r["warnings"]))

    def test_decay_requires_interval(self):
        self.assertFalse(_v({"name_ru": "X", "decay_enabled": True})["ok"])


class StagePreviewTest(unittest.TestCase):
    def _data(self):
        return {"name_ru": "S", "min_value": 0, "max_value": 100, "default_value": 0,
                "stages": _STAGES,
                "marks": [{"mark_id": "watched", "name_ru": "Под наблюдением",
                           "required_min_value": 21, "required_max_value": 100}]}

    def test_stage_for_value(self):
        self.assertEqual(rep.stage_for_value(self._data(), 25)["stage_id"], "watch")
        self.assertIsNone(rep.stage_for_value(self._data(), 999))

    def test_active_marks(self):
        marks = rep.active_marks(self._data(), 40)
        self.assertEqual([m["mark_id"] for m in marks], ["watched"])
        self.assertEqual(rep.active_marks(self._data(), 5), [])

    def test_preview_stage_change(self):
        p = rep.preview(self._data(), 10, 40)  # 10 (calm) → 50 (watch)
        self.assertEqual(p["next_value"], 50)
        self.assertTrue(p["stage_changed"])
        self.assertIn("Под наблюдением", p["next_marks"])

    def test_preview_clamps(self):
        p = rep.preview(self._data(), 90, 100)
        self.assertEqual(p["next_value"], 100)


class GraphTest(unittest.TestCase):
    ENVS = ("REPUTATION_CONSTRUCTOR_PATH", "EFFECT_CONSTRUCTOR_PATH")

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

    def test_effect_to_reputation_edge(self):
        from services import effect_constructor_service as fx
        from services import admin_graph_service as graph
        rep.store().create("guard_susp", {"name_ru": "Подозрение"})
        fx.store().create("mark_susp", {"effect_name": "Метка", "effect_type": "mark_effect",
                                        "linked_hidden_reputation_id": "guard_susp"})
        g = graph.full_graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("reputation:guard_susp", ids)
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("effect:mark_susp", "reputation:guard_susp", "depends_on_reputation"), pairs)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("REPUTATION_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["REPUTATION_CONSTRUCTOR_PATH"] = str(base / "rep.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_reputation_router(lambda: self.storage))
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

    def test_meta_create_preview(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/reputations/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        self.assertTrue(any(v["value"] == "hidden" for v in meta.json()["visibility"]))
        self.client.post("/api/admin/v2/reputations", headers=self._auth(token), json={
            "id": "city_rep", "data": {"name_ru": "Город", "min_value": -100, "max_value": 100,
                                       "default_value": 0, "stages": _STAGES}})
        pub = self.client.post("/api/admin/v2/reputations/city_rep/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 200, pub.text)
        prev = self.client.post("/api/admin/v2/reputations/city_rep/preview", headers=self._auth(token), json={"value": 10, "delta": 40})
        self.assertEqual(prev.status_code, 200, prev.text)
        self.assertEqual(prev.json()["preview"]["next_value"], 50)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/reputations/meta").status_code, 401)


if __name__ == "__main__":
    unittest.main()
