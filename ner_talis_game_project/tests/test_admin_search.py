"""Глобальный поиск по админ-панели (ТЗ 11 §4.2): сервис + API."""

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

from admin_search_api import create_admin_search_router
from services import admin_search_service as search_svc
from services import item_constructor_service as items
from services import world_content_registry as wcr
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage

_ENVS = ("WORLD_CONTENT_PATH", "ITEM_CONSTRUCTOR_PATH")


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = _ENVS + ("ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        for k in _ENVS:
            os.environ[k] = str(base / f"{k.lower()}.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        self._seed()

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _seed(self):
        items.store().create("iron_sword", {"name": "Железный меч"})
        items.store().create("iron_ore", {"name": "Железная руда"})
        wcr.create_content(wcr.KIND_MOB, "iron_golem", {"name": "Железный голем"})
        wcr.create_content(wcr.KIND_LOCATION, "green_hills", {"name": "Зелёные холмы", "short_description": "x"})


class SearchServiceTest(_Base):
    def test_finds_grouped(self):
        res = search_svc.search("желез")
        types = {g["type"] for g in res["groups"]}
        self.assertIn("item", types)
        self.assertIn("mob", types)
        item_group = next(g for g in res["groups"] if g["type"] == "item")
        ids = {i["entity_id"] for i in item_group["items"]}
        self.assertEqual(ids, {"iron_sword", "iron_ore"})

    def test_by_id(self):
        res = search_svc.search("green_hills")
        self.assertTrue(any(g["type"] == "location" for g in res["groups"]))

    def test_short_query_empty(self):
        self.assertEqual(search_svc.search("ж")["groups"], [])

    def test_no_match(self):
        self.assertEqual(search_svc.search("zzzznothing")["total"], 0)

    def test_limit_truncates(self):
        for i in range(5):
            items.store().create(f"steel_{i}", {"name": f"Стальной предмет {i}"})
        res = search_svc.search("стальн", limit=2)
        g = next(x for x in res["groups"] if x["type"] == "item")
        self.assertEqual(len(g["items"]), 2)
        self.assertTrue(g["truncated"])


class SearchApiTest(_Base):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(create_admin_search_router(lambda: self.storage))
        self.client = TestClient(app)

    def _token(self):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id="999")
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_search_endpoint(self):
        token = self._token()
        r = self.client.get("/api/admin/v2/search", params={"q": "желез"}, headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreaterEqual(r.json()["total"], 3)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/search", params={"q": "x"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
