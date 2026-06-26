"""Блок «Используется в ремесле» (ТЗ 13 §6): сервис ролей/цепочки + API предмета."""

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
from services import item_constructor_service as items
from services import recipe_constructor_service as recipes
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class CraftUsageBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("ITEM_CONSTRUCTOR_PATH", "RECIPE_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH",
                "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["ITEM_CONSTRUCTOR_PATH"] = str(base / "items.json")
        os.environ["RECIPE_CONSTRUCTOR_PATH"] = str(base / "recipes.json")
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

    def _seed(self):
        items.store().create("iron_ore", {"name": "Железная руда"})
        items.store().create("iron_ingot", {"name": "Железный слиток"})
        items.store().create("iron_sword", {"name": "Железный меч"})
        items.store().create("sword_blueprint", {"name": "Чертёж меча"})
        # Слиток выплавляется из руды.
        recipes.store().create("smelt_ingot", {"name": "Плавка слитка", "workshop": "smeltery",
                                               "output_item_id": "iron_ingot",
                                               "ingredients": [{"item_id": "iron_ore", "amount": 2}]})
        # Меч куётся из слитка по чертежу.
        recipes.store().create("forge_sword", {"name": "Ковка меча", "workshop": "forge",
                                              "output_item_id": "iron_sword", "blueprint_id": "sword_blueprint",
                                              "ingredients": [{"item_id": "iron_ingot", "amount": 3}]})


class CraftUsageServiceTest(CraftUsageBase):
    def test_ingot_roles_and_chain(self):
        self._seed()
        u = recipes.item_craft_usage("iron_ingot")
        self.assertEqual({r["id"] for r in u["as_result"]}, {"smelt_ingot"})
        self.assertEqual({r["id"] for r in u["as_material"]}, {"forge_sword"})
        self.assertIn("iron_ore", u["chain"]["made_from"])   # слиток из руды
        self.assertIn("iron_sword", u["chain"]["makes"])     # из слитка — меч

    def test_blueprint_role(self):
        self._seed()
        u = recipes.item_craft_usage("sword_blueprint")
        self.assertEqual({r["id"] for r in u["as_blueprint"]}, {"forge_sword"})

    def test_material_without_recipe_warns(self):
        self._seed()
        u = recipes.item_craft_usage("iron_ore")  # руда нигде не создаётся
        self.assertTrue(any("ни один рецепт его не создаёт" in w for w in u["warnings"]))

    def test_disabled_recipe_warns(self):
        self._seed()
        recipes.store().set_status("smelt_ingot", recipes.STATUS_DISABLED, force=True)
        u = recipes.item_craft_usage("iron_ingot")
        self.assertTrue(any("отключён" in w for w in u["warnings"]))


class CraftUsageApiTest(CraftUsageBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(create_admin_item_router(lambda: self.storage))
        self.client = TestClient(app)

    def _token(self):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id="999")
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_craft_usage_endpoint(self):
        self._seed()
        token = self._token()
        r = self.client.get("/api/admin/v2/items/iron_ingot/craft-usage", headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        craft = r.json()["craft"]
        self.assertEqual(len(craft["as_result"]), 1)
        self.assertEqual(len(craft["as_material"]), 1)

    def test_unknown_item_404(self):
        token = self._token()
        r = self.client.get("/api/admin/v2/items/ghost/craft-usage", headers=self._auth(token))
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
