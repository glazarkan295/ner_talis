"""Конструктор «Информатор Крот» (ТЗ 21 §3): сервис, запреты заказа, API, RBAC."""

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

from admin_mole_api import create_admin_mole_router
from services import admin_rbac as rbac
from services import mole_constructor_service as mole
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class MoleServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("MOLE_CONSTRUCTOR_PATH")
        os.environ["MOLE_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "mole.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("MOLE_CONSTRUCTOR_PATH", None)
        else:
            os.environ["MOLE_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_service(self):
        env = mole.store().create("mole_city", {
            "name": "Крот трущоб", "location_id": "slums",
            "info_search_modes": ["by_nick", "exact"], "info_cost": 100,
            "info_error_chance": 10, "info_stale_chance": 5,
            "compass_enabled": True, "compass_mode": "teleport", "compass_cost": 5000,
            "order_attempts": 3, "order_refund_policy": "partial",
            "assassin_categories": [{"category": "cheap", "price": 200, "success_chance": 40, "count": 1}],
            "price_min": 100, "price_max": 9999, "price_base": 200,
        })
        result = mole.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = mole.store().create("bad", {
            "name": "", "info_error_chance": 150,
            "ban_weaker_ratio": 0.5,
            "assassin_categories": [{"category": "elite", "price": -5, "success_chance": 200}],
            "price_min": 1000, "price_max": 100,
        })
        result = mole.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("название", joined)
        self.assertIn("шанс ошибки", joined)
        self.assertIn("слабее", joined)
        self.assertIn("минимальная цена", joined)

    def test_order_ban_level_diff(self):
        # Разница уровней больше 400 — заказ запрещён.
        res = mole.check_order_allowed(900, 100)
        self.assertFalse(res["allowed"])
        self.assertIn("разница уровней", res["reason"].lower())
        # В пределах 400 и не слабее ×2 — разрешено.
        ok = mole.check_order_allowed(150, 100)
        self.assertTrue(ok["allowed"], ok["reason"])

    def test_order_ban_weaker_ratio(self):
        # Цель слабее заказчика более чем в 2 раза по уровню — заказ запрещён.
        res = mole.check_order_allowed(300, 100)
        self.assertFalse(res["allowed"])
        self.assertIn("раза", res["reason"].lower())
        # Ровно ×2 — допустимо (не «более чем»).
        ok = mole.check_order_allowed(200, 100)
        self.assertTrue(ok["allowed"], ok["reason"])

    def test_order_custom_thresholds(self):
        # Пороги можно переопределить настройками сервиса.
        res = mole.check_order_allowed(50, 10, max_level_diff=30)
        self.assertFalse(res["allowed"])

    def test_preview(self):
        prev = mole.preview({
            "name": "Крот", "info_search_modes": ["by_nick"],
            "assassin_categories": [{"category": "elite", "price": 5000, "success_chance": 80}],
        })
        self.assertEqual(prev["name"], "Крот")
        self.assertEqual(prev["ban_max_level_diff"], 400)
        self.assertEqual(prev["assassin_categories"][0]["category"], "Элитный убийца")


class MoleApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("MOLE_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["MOLE_CONSTRUCTOR_PATH"] = str(base / "mole.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_mole_router(lambda: self.storage))
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

    def _create(self, token, mid="mole_city", data=None):
        body = {"id": mid, "data": data or {"name": "Крот", "location_id": "slums"}}
        return self.client.post("/api/admin/v2/mole", headers=self._auth(token), json=body)

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/mole/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        body = meta.json()
        cats = {c["value"] for c in body["assassinCategories"]}
        self.assertIn("elite", cats)
        self.assertEqual(body["defaultMaxLevelDiff"], 400)

    def test_create_validate_publish(self):
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        pub = self.client.post("/api/admin/v2/mole/mole_city/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_order_check_endpoint(self):
        token = self._token()
        resp = self.client.post("/api/admin/v2/mole/order-check", headers=self._auth(token),
                                json={"orderer_level": 900, "target_level": 100})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["result"]["allowed"])

    def test_content_cannot_publish_readonly_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/mole/mole_city/publish", headers=self._auth(token), json={}).status_code, 403)
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        ro = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/mole", headers=self._auth(ro)).status_code, 200)
        self.assertEqual(self._create(ro, mid="nope").status_code, 403)


if __name__ == "__main__":
    unittest.main()
