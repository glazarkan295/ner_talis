"""Конструктор таверны (ТЗ таверны): валидация, цена, предпросмотр, граф, API."""

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

from admin_tavern_api import create_admin_tavern_router
from services import tavern_constructor_service as tav
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


def _v(data):
    return tav.validate({"data": data})


class ValidateTest(unittest.TestCase):
    def test_valid(self):
        r = _v({"name": "Таверна Селдара", "tavern_type": "city_tavern",
                "location_id": "seldar", "player_entry_text": "Вы входите в таверну."})
        self.assertTrue(r["ok"], r["errors"])

    def test_bad_type(self):
        self.assertFalse(_v({"name": "X", "tavern_type": "nonsense"})["ok"])

    def test_no_location_warns(self):
        r = _v({"name": "X", "player_entry_text": "вход"})
        self.assertTrue(any("локации или городу" in w for w in r["warnings"]))

    def test_negative_price_error(self):
        r = _v({"name": "X", "location_id": "l", "services": [{"name": "Эль", "price": -5}]})
        self.assertFalse(r["ok"])

    def test_paid_service_without_currency_warns(self):
        r = _v({"name": "X", "location_id": "l", "services": [{"name": "Эль", "price": 5}]})
        self.assertTrue(any("без валюты" in w for w in r["warnings"]))

    def test_rumor_without_text_error(self):
        r = _v({"name": "X", "location_id": "l", "rumors": [{"rumor_id": "r1"}]})
        self.assertFalse(r["ok"])

    def test_http_image_rejected(self):
        r = _v({"name": "X", "location_id": "l", "image_path": "https://evil/x.png"})
        self.assertFalse(r["ok"])

    def test_job_valid(self):
        r = _v({"name": "T", "location_id": "l", "jobs": [{
            "name": "Грузчик", "trains_stat": "strength", "work_level": 1, "max_level": 10,
            "base_duration_seconds": 600, "base_cooldown_seconds": 1200, "reward": 50,
            "stat_raise_chance": 30, "time_reduction_percent": 40, "cooldown_reduction_percent": 40,
        }]})
        self.assertTrue(r["ok"], r["errors"])

    def test_job_reduction_cap_40(self):
        # §5.2: снижение времени/отката от прокачки не может превышать 40%.
        r = _v({"name": "T", "location_id": "l", "jobs": [{
            "name": "Грузчик", "time_reduction_percent": 50,
        }]})
        self.assertFalse(r["ok"])
        self.assertTrue(any("40" in e and "снижение времени" in e.lower() for e in r["errors"]), r["errors"])

    def test_job_without_name_error(self):
        r = _v({"name": "T", "location_id": "l", "jobs": [{"trains_stat": "strength"}]})
        self.assertFalse(r["ok"])

    def test_capped_work_reduction_helper(self):
        self.assertEqual(tav.capped_work_reduction(80), 40.0)
        self.assertEqual(tav.capped_work_reduction(25), 25.0)
        self.assertEqual(tav.capped_work_reduction(-5), 0.0)

    def test_food_type_and_name(self):
        bad = _v({"name": "T", "location_id": "l", "food": [{"food_type": "common", "price": 5}]})
        self.assertFalse(bad["ok"])  # нет названия
        ok = _v({"name": "T", "location_id": "l", "food": [{"food_type": "festive", "name": "Праздничный пирог", "price": 5, "currency": "gold"}]})
        self.assertTrue(ok["ok"], ok["errors"])

    def test_preview_includes_jobs(self):
        p = tav.preview({"name": "T", "jobs": [{"name": "Грузчик", "trains_stat": "strength", "work_level": 2}]})
        self.assertEqual(p["jobs"][0]["name"], "Грузчик")
        self.assertEqual(p["jobs"][0]["trains_stat"], "Сила")


class PriceTest(unittest.TestCase):
    def test_final_price(self):
        self.assertEqual(tav.final_price(100, reputation_discount_percent=10), 90)
        self.assertEqual(tav.final_price(100, event_modifier_percent=20), 120)
        self.assertEqual(tav.final_price(10, min_price=15), 15)


class PreviewTest(unittest.TestCase):
    def test_preview(self):
        data = {"name": "T", "player_entry_text": "Привет",
                "services": [{"name": "Эль", "price": 10, "currency": "copper"}],
                "rumors": [{"rumor_text": "Говорят, в лесу завелись волки."}]}
        p = tav.preview(data, {"reputation_discount_percent": 50})
        self.assertEqual(p["entry_text"], "Привет")
        self.assertEqual(p["services"][0]["price"], 5)  # скидка 50%
        self.assertIn("волки", p["rumor"])

    def test_preview_no_rumor(self):
        p = tav.preview({"name": "T"}, None)
        self.assertIn("ничего полезного", p["rumor"])


class GraphTest(unittest.TestCase):
    ENVS = ("TAVERN_CONSTRUCTOR_PATH", "WORLD_CONTENT_PATH")

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

    def test_tavern_to_location_edge(self):
        from services import world_content_registry as wcr
        from services import admin_graph_service as graph
        wcr.create_content(wcr.KIND_LOCATION, "seldar", {"name": "Селдар", "short_description": "город"})
        tav.store().create("seldar_tav", {"name": "Таверна", "location_id": "seldar"})
        g = graph.full_graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("tavern:seldar_tav", ids)
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("tavern:seldar_tav", "location:seldar", "in_location"), pairs)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("TAVERN_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["TAVERN_CONSTRUCTOR_PATH"] = str(base / "tav.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_tavern_router(lambda: self.storage))
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

    def test_meta_create_publish_preview(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/taverns/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        self.assertTrue(any(t["value"] == "city_tavern" for t in meta.json()["tavernTypes"]))
        self.client.post("/api/admin/v2/taverns", headers=self._auth(token), json={
            "id": "t1", "data": {"name": "Таверна", "location_id": "seldar",
                                 "player_entry_text": "вход", "tavern_type": "city_tavern"}})
        pub = self.client.post("/api/admin/v2/taverns/t1/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 200, pub.text)
        prev = self.client.post("/api/admin/v2/taverns/t1/preview", headers=self._auth(token), json={})
        self.assertEqual(prev.status_code, 200, prev.text)
        self.assertEqual(prev.json()["preview"]["entry_text"], "вход")

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/taverns/meta").status_code, 401)


if __name__ == "__main__":
    unittest.main()
