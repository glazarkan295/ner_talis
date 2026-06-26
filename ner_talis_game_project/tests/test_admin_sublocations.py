"""Конструктор подлокаций (ТЗ 09 §2–§14): валидаторы, проверка схемы, граф, API."""

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

from admin_sublocation_api import create_admin_sublocation_router
from services import admin_graph_service as graph
from services import world_content_registry as wcr
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage

K_SUB = wcr.KIND_SUBLOCATION
K_NODE = wcr.KIND_SUBLOCATION_NODE
K_TR = wcr.KIND_SUBLOCATION_TRANSITION


class SubBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("WORLD_CONTENT_PATH", "ITEM_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH",
                "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["WORLD_CONTENT_PATH"] = str(base / "world.json")
        os.environ["ITEM_CONSTRUCTOR_PATH"] = str(base / "items.json")
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

    def _seed_cave(self):
        wcr.create_content(wcr.KIND_LOCATION, "forest", {"name": "Лес", "short_description": "лес"})
        wcr.create_content(K_SUB, "old_cave", {"name": "Старая пещера", "type": "cave", "parent_location": "forest", "short_description": "сыро"})
        wcr.create_content(K_NODE, "n_entry", {"name": "Вход", "node_type": "entry", "sublocation_id": "old_cave"})
        wcr.create_content(K_NODE, "n_room", {"name": "Комната", "node_type": "room", "sublocation_id": "old_cave"})
        wcr.create_content(K_NODE, "n_exit", {"name": "Выход", "node_type": "exit", "sublocation_id": "old_cave"})
        wcr.create_content(K_TR, "t1", {"sublocation_id": "old_cave", "from_node": "n_entry", "to_node": "n_room", "button_text": "Вперёд"})
        wcr.create_content(K_TR, "t2", {"sublocation_id": "old_cave", "from_node": "n_room", "to_node": "n_exit", "button_text": "Наружу"})


class SubValidationTest(SubBase):
    def test_card_valid(self):
        self._seed_cave()
        env = wcr.get_content(K_SUB, "old_cave")
        self.assertTrue(wcr.validate_envelope(env)["ok"], wcr.validate_envelope(env)["errors"])

    def test_card_bad_type(self):
        wcr.create_content(K_SUB, "weird", {"name": "X", "type": "nonsense", "parent_location": "forest", "short_description": "y"})
        env = wcr.get_content(K_SUB, "weird")
        self.assertFalse(wcr.validate_envelope(env)["ok"])

    def test_card_missing_parent_warns(self):
        wcr.create_content(K_SUB, "np", {"name": "X", "type": "cave", "short_description": "y"})
        env = wcr.get_content(K_SUB, "np")
        res = wcr.validate_envelope(env)
        self.assertFalse(res["ok"])  # parent required → error
        self.assertTrue(any("родительск" in e.lower() for e in res["errors"]))

    def test_node_requires_sublocation(self):
        wcr.create_content(K_NODE, "orphan", {"name": "Узел", "node_type": "room", "sublocation_id": "ghost"})
        env = wcr.get_content(K_NODE, "orphan")
        self.assertFalse(wcr.validate_envelope(env)["ok"])

    def test_transition_same_node_rejected(self):
        self._seed_cave()
        wcr.create_content(K_TR, "loop", {"sublocation_id": "old_cave", "from_node": "n_room", "to_node": "n_room"})
        env = wcr.get_content(K_TR, "loop")
        self.assertFalse(wcr.validate_envelope(env)["ok"])

    def test_hidden_transition_without_condition_warns(self):
        self._seed_cave()
        wcr.create_content(K_TR, "secret", {"sublocation_id": "old_cave", "from_node": "n_entry", "to_node": "n_exit", "hidden": True})
        env = wcr.get_content(K_TR, "secret")
        res = wcr.validate_envelope(env)
        self.assertTrue(any("скрыт" in w.lower() for w in res["warnings"]))


class SubSchemaTest(SubBase):
    def test_schema_ok(self):
        self._seed_cave()
        s = wcr.validate_sublocation_schema("old_cave")
        self.assertTrue(s["ok"], s["errors"])
        self.assertEqual(s["node_count"], 3)
        self.assertEqual(s["transition_count"], 2)

    def test_schema_no_entry(self):
        wcr.create_content(K_SUB, "c2", {"name": "C2", "type": "cave", "parent_location": "forest", "short_description": "x"})
        wcr.create_content(K_NODE, "c2_room", {"name": "Комната", "node_type": "room", "sublocation_id": "c2"})
        s = wcr.validate_sublocation_schema("c2")
        self.assertFalse(s["ok"])
        self.assertTrue(any("нет входа" in e.lower() for e in s["errors"]))

    def test_schema_unreachable(self):
        self._seed_cave()
        wcr.create_content(K_NODE, "n_island", {"name": "Остров", "node_type": "room", "sublocation_id": "old_cave"})
        s = wcr.validate_sublocation_schema("old_cave")
        self.assertTrue(any("недостижим" in w.lower() for w in s["warnings"]))


class SubGraphTest(SubBase):
    def test_sublocation_in_graph(self):
        self._seed_cave()
        g = graph.full_graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("sublocation:old_cave", ids)
        self.assertIn("sublocation_node:n_entry", ids)
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("sublocation:old_cave", "location:forest", "in_location"), pairs)
        self.assertIn(("sublocation_node:n_entry", "sublocation:old_cave", "in_location"), pairs)
        self.assertIn(("sublocation_transition:t1", "sublocation_node:n_room", "to_location"), pairs)


class SubApiTest(SubBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(create_admin_sublocation_router(lambda: self.storage))
        self.client = TestClient(app)

    def _token(self):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id="999")
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_meta(self):
        token = self._token()
        r = self.client.get("/api/admin/v2/sublocations/meta", headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("cave", r.json()["sublocationTypes"])
        self.assertIn("entry", r.json()["nodeTypes"])

    def test_schema_and_nodes_endpoints(self):
        self._seed_cave()
        token = self._token()
        s = self.client.get("/api/admin/v2/sublocations/old_cave/schema", headers=self._auth(token))
        self.assertEqual(s.status_code, 200, s.text)
        self.assertTrue(s.json()["schema"]["ok"])
        n = self.client.get("/api/admin/v2/sublocations/old_cave/nodes", headers=self._auth(token))
        self.assertEqual(len(n.json()["nodes"]), 3)
        self.assertEqual(len(n.json()["transitions"]), 2)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/sublocations/meta").status_code, 401)


if __name__ == "__main__":
    unittest.main()
