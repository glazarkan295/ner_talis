"""Улучшение/зачарование/разборка (ТЗ 13 §5.10–§5.11): валидаторы, граф, API."""

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

from admin_item_action_api import (
    create_admin_disassemble_router, create_admin_enchant_router, create_admin_upgrade_router,
)
from services import disassemble_constructor_service as disassemble
from services import enchant_constructor_service as enchant
from services import upgrade_constructor_service as upgrade
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class _Base(unittest.TestCase):
    ENVS = ("UPGRADE_CONSTRUCTOR_PATH", "ENCHANT_CONSTRUCTOR_PATH",
            "DISASSEMBLE_CONSTRUCTOR_PATH", "EFFECT_CONSTRUCTOR_PATH")

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
    def test_upgrade_valid_and_bad(self):
        ok = upgrade.store().create("u1", {"name": "Заточка", "upgrade_type": "raise_level", "success_chance": 80})
        self.assertTrue(upgrade.validate(ok)["ok"], upgrade.validate(ok)["errors"])
        bad = upgrade.store().create("u2", {"name": "X", "upgrade_type": "weird", "success_chance": 150})
        self.assertFalse(upgrade.validate(bad)["ok"])

    def test_enchant_missing_effect_warns(self):
        env = enchant.store().create("e1", {"name": "Огонь"})
        self.assertTrue(any("эффект" in w.lower() for w in enchant.validate(env)["warnings"]))

    def test_disassemble_requires_source(self):
        env = disassemble.store().create("d1", {"name": "Разбор"})
        self.assertFalse(disassemble.validate(env)["ok"])


class GraphTest(_Base):
    def test_edges(self):
        from services import admin_graph_service as graph
        disassemble.store().create("d_sword", {"name": "Разбор меча", "source_item_id": "iron_sword",
                                               "outputs": [{"item_id": "iron_scrap"}]})
        enchant.store().create("ench_fire", {"name": "Огонь", "enchant_effect": "burn"})
        g = graph.full_graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("item_disassemble:d_sword", ids)
        self.assertIn("item_enchant:ench_fire", ids)
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("item_disassemble:d_sword", "item:iron_sword", "disassembles"), pairs)
        self.assertIn(("item_disassemble:d_sword", "item:iron_scrap", "produces"), pairs)
        self.assertIn(("item_enchant:ench_fire", "effect:burn", "applies_effect"), pairs)


class ApiTest(_Base):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(create_admin_upgrade_router(lambda: self.storage))
        app.include_router(create_admin_enchant_router(lambda: self.storage))
        app.include_router(create_admin_disassemble_router(lambda: self.storage))
        self.client = TestClient(app)

    def _token(self):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id="999")
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_upgrade_meta_and_publish(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/upgrades/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        self.assertTrue(any(t["value"] == "raise_level" for t in meta.json()["upgradeTypes"]))
        self.client.post("/api/admin/v2/upgrades", headers=self._auth(token), json={"id": "sharp", "data": {"name": "Заточка", "upgrade_type": "raise_level"}})
        pub = self.client.post("/api/admin/v2/upgrades/sharp/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 200, pub.text)

    def test_disassemble_create(self):
        token = self._token()
        c = self.client.post("/api/admin/v2/disassembles", headers=self._auth(token), json={"id": "dis1", "data": {"name": "Разбор", "source_item_id": "iron_sword"}})
        self.assertEqual(c.status_code, 200, c.text)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/enchants/meta").status_code, 401)


if __name__ == "__main__":
    unittest.main()
