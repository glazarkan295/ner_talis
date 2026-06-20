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

from admin_item_api import create_admin_item_router
from services import admin_rbac as rbac
from services import item_constructor_service as items
from services import world_content_registry as world
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class ItemServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("ITEM_CONSTRUCTOR_PATH")
        os.environ["ITEM_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "items.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("ITEM_CONSTRUCTOR_PATH", None)
        else:
            os.environ["ITEM_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_item(self):
        env = items.store().create("iron_sword", {
            "name": "Железный меч", "description": "Простой меч", "category": "Оружие",
            "item_type": "equippable", "quality": "common", "equippable": True,
            "equip_slot": "main_hand", "stackable": False, "price_sell": 50,
        })
        result = items.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = items.store().create("broken_item", {
            "category": "", "quality": "ultra", "item_type": "weird",
            "stackable": False, "max_stack": 9, "equippable": True,
            "price_sell": -5,
        })
        result = items.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("название", joined)
        self.assertIn("категория", joined)
        self.assertIn("стак", joined)
        self.assertIn("слот", joined)
        self.assertIn("цена", joined)

    def test_version_history_snapshot(self):
        items.store().create("potion", {"name": "Зелье", "description": "x", "category": "Зелье", "stackable": True, "max_stack": 10})
        items.record_version("potion", by="t:1", reason="до правки")
        env = items.store().get("potion")
        self.assertEqual(len(env["data"]["version_history"]), 1)

    def test_where_used_finds_mob_drop(self):
        os.environ["WORLD_CONTENT_PATH"] = str(Path(self._tmp.name) / "world.json")
        self.addCleanup(lambda: os.environ.pop("WORLD_CONTENT_PATH", None))
        world.create_content("mob", "wolf", {"name": "Волк", "type": "beast", "hp": 10, "drop": [{"item_id": "fang", "chance": 50}]})
        items.store().create("fang", {"name": "Клык", "description": "x", "category": "Трофей"})
        usage = items.where_used("fang")
        self.assertEqual(usage["total"], 1)
        self.assertTrue(any(m["id"] == "wolf" for m in usage["mob_drops"]))


class ItemApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("ITEM_CONSTRUCTOR_PATH", "WORLD_CONTENT_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["ITEM_CONSTRUCTOR_PATH"] = str(base / "items.json")
        os.environ["WORLD_CONTENT_PATH"] = str(base / "world.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_item_router(lambda: self.storage))
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

    def _create(self, token, iid="sword", data=None):
        return self.client.post("/api/admin/v2/items", headers=self._auth(token), json={"id": iid, "data": data or {"name": "Меч", "description": "x", "category": "Оружие", "stackable": False}})

    def test_create_validate_publish_flow(self):
        token = self._token("999")
        self.assertEqual(self._create(token).status_code, 200)
        publish = self.client.post("/api/admin/v2/items/sword/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertIn("item.publish", dangerous)

    def test_edit_published_makes_draft_with_version(self):
        token = self._token("999")
        self._create(token)
        self.client.post("/api/admin/v2/items/sword/publish", headers=self._auth(token), json={})
        upd = self.client.put("/api/admin/v2/items/sword", headers=self._auth(token), json={"data": {"name": "Меч 2"}, "reason": "правка"})
        self.assertEqual(upd.status_code, 200, upd.text)
        self.assertEqual(upd.json()["item"]["status"], "draft")  # back to draft until republish
        env = self.client.get("/api/admin/v2/items/sword", headers=self._auth(token)).json()["item"]
        self.assertTrue(env["data"].get("version_history"))

    def test_publish_blocked_when_invalid(self):
        token = self._token("999")
        self._create(token, iid="bad", data={"name": "", "category": "", "stackable": False})
        publish = self.client.post("/api/admin/v2/items/bad/publish", headers=self._auth(token), json={})
        self.assertEqual(publish.status_code, 400, publish.text)
        self.assertEqual(self.client.get("/api/admin/v2/items/bad", headers=self._auth(token)).json()["item"]["status"], "error")

    def test_hard_delete_owner_only_and_blocked_when_used(self):
        token = self._token("999")  # 999 is owner via ENV bootstrap
        # Item referenced by a mob drop cannot be hard-deleted.
        world.create_content("mob", "wolf", {"name": "Волк", "type": "beast", "hp": 10, "drop": [{"item_id": "fang", "chance": 50}]})
        self._create(token, iid="fang", data={"name": "Клык", "description": "x", "category": "Трофей"})
        used = self.client.request("DELETE", "/api/admin/v2/items/fang", headers=self._auth(token), json={"confirm": "fang", "reason": "x"})
        self.assertEqual(used.status_code, 409, used.text)
        # Unused item, wrong confirm -> 400; correct confirm -> deleted.
        self._create(token, iid="lonely", data={"name": "Одинокий", "description": "x", "category": "Трофей"})
        self.assertEqual(self.client.request("DELETE", "/api/admin/v2/items/lonely", headers=self._auth(token), json={"confirm": "wrong"}).status_code, 400)
        ok = self.client.request("DELETE", "/api/admin/v2/items/lonely", headers=self._auth(token), json={"confirm": "lonely", "reason": "уборка"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertIsNone(items.store().get("lonely"))

    def test_content_can_draft_but_not_publish_or_hard_delete(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/items/sword/publish", headers=self._auth(token), json={}).status_code, 403)
        self.assertEqual(self.client.request("DELETE", "/api/admin/v2/items/sword", headers=self._auth(token), json={"confirm": "sword"}).status_code, 403)

    def test_read_only_view_only(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token("999")
        self.assertEqual(self.client.get("/api/admin/v2/items", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self._create(token).status_code, 403)


if __name__ == "__main__":
    unittest.main()
