"""Конструктор сообщений мастерских (ТЗ 14): валидация, рендер-предпросмотр, API, граф."""

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

from admin_workshop_message_api import create_admin_workshop_message_router
from services import workshop_message_service as wm
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class ValidateTest(unittest.TestCase):
    def _v(self, data):
        return wm.validate({"data": data})

    def test_valid(self):
        self.assertTrue(self._v({"name": "Кузница", "scope": "global"})["ok"])

    def test_bad_scope(self):
        self.assertFalse(self._v({"name": "X", "scope": "weird"})["ok"])

    def test_unknown_block(self):
        r = self._v({"name": "X", "block_order": ["header", "nonsense"]})
        self.assertFalse(r["ok"])

    def test_pagination_requires_positive(self):
        r = self._v({"name": "X", "use_pagination": True, "items_per_page": 0})
        self.assertFalse(r["ok"])

    def test_too_many_buttons_warns(self):
        r = self._v({"name": "X", "buttons": [{"text": f"b{i}"} for i in range(15)]})
        self.assertTrue(any("кнопок" in w for w in r["warnings"]))

    def test_unknown_placeholder_warns(self):
        r = self._v({"name": "X", "header": "Привет {ghost}"})
        self.assertTrue(any("ghost" in w for w in r["warnings"]))


class PreviewTest(unittest.TestCase):
    def test_default_preview(self):
        p = wm.render_preview({"name": "X"}, None)
        self.assertIn("Доступные рецепты", p["text"])
        self.assertGreater(p["length"], 0)

    def test_hide_unavailable(self):
        p = wm.render_preview({"name": "X", "unavailable_display": "hide"}, None)
        self.assertNotIn("Недоступные рецепты", p["text"])

    def test_queue_never(self):
        p = wm.render_preview({"name": "X", "show_queue": "never"}, None)
        self.assertNotIn("Очередь", p["text"])

    def test_custom_state(self):
        state = {"recipes": [{"name": "Зелье", "available": True}], "materials": [], "requirements": [], "queue": []}
        p = wm.render_preview({"name": "X"}, state)
        self.assertIn("Зелье", p["text"])


class GraphTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._keys = ("WORKSHOP_MESSAGE_CONSTRUCTOR_PATH", "WORKSHOP_CONSTRUCTOR_PATH")
        self._saved = {k: os.environ.get(k) for k in self._keys}
        for k in self._keys:
            os.environ[k] = str(base / f"{k.lower()}.json")
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_template_workshop_edge(self):
        from services import workshop_constructor_service as workshops
        from services import admin_graph_service as graph
        workshops.store().create("forge1", {"name": "Кузница", "type": "forge"})
        wm.store().create("tpl1", {"name": "Шаблон", "scope": "by_workshop", "workshop_id": "forge1"})
        g = graph.full_graph()
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("workshop_message:tpl1", "workshop:forge1", "in_workshop"), pairs)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("WORKSHOP_MESSAGE_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["WORKSHOP_MESSAGE_CONSTRUCTOR_PATH"] = str(base / "wm.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_workshop_message_router(lambda: self.storage))
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
        meta = self.client.get("/api/admin/v2/workshop-messages/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        self.assertTrue(any(b["value"] == "available_recipes" for b in meta.json()["blockTypes"]))
        self.client.post("/api/admin/v2/workshop-messages", headers=self._auth(token), json={"id": "t1", "data": {"name": "Шаблон", "scope": "global"}})
        pub = self.client.post("/api/admin/v2/workshop-messages/t1/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 200, pub.text)
        prev = self.client.post("/api/admin/v2/workshop-messages/preview", headers=self._auth(token), json={"data": {"name": "X"}})
        self.assertEqual(prev.status_code, 200, prev.text)
        self.assertIn("text", prev.json()["preview"])

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/workshop-messages/meta").status_code, 401)


if __name__ == "__main__":
    unittest.main()
