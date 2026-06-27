"""Конструктор жилого района / дома (ТЗ 21 §6): валидация, предпросмотр, API, RBAC."""

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

from admin_housing_api import create_admin_housing_router
from services import admin_rbac as rbac
from services import housing_constructor_service as housing
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class HousingServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("HOUSING_CONSTRUCTOR_PATH")
        os.environ["HOUSING_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "housing.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("HOUSING_CONSTRUCTOR_PATH", None)
        else:
            os.environ["HOUSING_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_plan(self):
        env = housing.store().create("large_estate", {
            "name": "Большой дом", "plot_type": "large", "house_type": "large",
            "cooking_tier": "special", "full_rest_minutes": 40, "extra_building_slots": 5,
            "special_rooms": [{"room_type": "gym", "stats": ["strength", "endurance"], "time_minutes": 30, "chance_percent": 40, "daily_limit": 1}],
            "fixed_buildings": [{"building_type": "trophy_room"}, {"building_type": "mailbox"}],
            "upgradable_buildings": [{"building_type": "altar", "level": 1, "max_level": 3, "upgrade_cost": 1000}],
            "dishes": [{"name": "Особый пирог", "dish_type": "special", "success_chance": 80, "cook_time_seconds": 300}],
            "restore_hp_percent": 100, "restore_energy_percent": 100,
        })
        result = housing.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = housing.store().create("bad", {
            "name": "", "full_rest_minutes": -5,
            "special_rooms": [{"room_type": "gym", "chance_percent": 150}],
            "dishes": [{"dish_type": "special", "success_chance": 200}],
            "restore_hp_percent": 120,
        })
        result = housing.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("название плана жилья", joined)
        self.assertIn("время отдыха", joined)
        self.assertIn("шанс должен быть 0–100", joined)
        self.assertIn("блюдо #1: не заполнено название", joined)
        self.assertIn("восстановление hp", joined)

    def test_upgradable_level_warning(self):
        env = housing.store().create("warn", {
            "name": "Дом", "upgradable_buildings": [{"building_type": "warehouse", "level": 5, "max_level": 3}],
        })
        res = housing.validate(env)
        self.assertTrue(res["ok"])
        self.assertTrue(any("больше максимального" in w.lower() for w in res["warnings"]))

    def test_preview(self):
        prev = housing.preview({
            "name": "Дом", "plot_type": "large", "cooking_tier": "special",
            "special_rooms": [{"room_type": "meditation_room", "stats": ["intelligence", "wisdom"]}],
            "dishes": [{"name": "Суп", "dish_type": "common"}],
        })
        self.assertEqual(prev["plot_type"], "Большой участок")
        self.assertEqual(prev["cooking_tier"], "Блюда с особыми эффектами")
        self.assertEqual(prev["special_rooms"][0]["room"], "Комната медитации и знаний")
        self.assertIn("Интеллект", prev["special_rooms"][0]["stats"])


class HousingApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("HOUSING_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["HOUSING_CONSTRUCTOR_PATH"] = str(base / "housing.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_housing_router(lambda: self.storage))
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

    def _create(self, token, hid="estate", data=None):
        body = {"id": hid, "data": data or {"name": "Дом", "plot_type": "small"}}
        return self.client.post("/api/admin/v2/housing", headers=self._auth(token), json=body)

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/housing/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        body = meta.json()
        plots = {p["value"] for p in body["plotTypes"]}
        self.assertEqual(plots, {"small", "medium", "large"})
        self.assertEqual(body["plotPresets"]["large"]["full_rest_minutes"], 40)
        self.assertEqual(body["roomPresets"]["gym"]["chance_percent"], 40)

    def test_create_validate_publish(self):
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        pub = self.client.post("/api/admin/v2/housing/estate/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_preview_endpoint(self):
        token = self._token()
        self._create(token, hid="e2", data={"name": "Дом", "plot_type": "medium"})
        pv = self.client.post("/api/admin/v2/housing/e2/preview", headers=self._auth(token), json={})
        self.assertEqual(pv.status_code, 200, pv.text)
        self.assertEqual(pv.json()["preview"]["plot_type"], "Средний участок")

    def test_content_cannot_publish_readonly_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/housing/estate/publish", headers=self._auth(token), json={}).status_code, 403)
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        ro = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/housing", headers=self._auth(ro)).status_code, 200)
        self.assertEqual(self._create(ro, hid="nope").status_code, 403)


if __name__ == "__main__":
    unittest.main()
