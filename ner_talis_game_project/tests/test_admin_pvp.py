"""Конструктор будущего PVP (ТЗ 4 §1): сервис, валидация, предпросмотр, API, RBAC."""

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

from admin_pvp_api import create_admin_pvp_router
from services import admin_rbac as rbac
from services import pvp_constructor_service as pvp
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class PvpServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("PVP_CONSTRUCTOR_PATH")
        os.environ["PVP_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "pvp.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("PVP_CONSTRUCTOR_PATH", None)
        else:
            os.environ["PVP_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_rule(self):
        env = pvp.store().create("duel", {
            "name": "Классическая дуэль", "pvp_type": "duel", "enabled": True,
            "min_level": 5, "max_level_diff": 10, "require_consent": True,
            "buttons": [{"action": "attack", "text": "Атаковать"}],
        })
        result = pvp.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = pvp.store().create("bad", {
            "name": "", "pvp_type": "bogus",
            "min_level": -1, "postdeath_curse_enabled": True, "postdeath_curse_chance": 150,
        })
        result = pvp.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("название", joined)
        self.assertIn("тип pvp", joined)
        self.assertIn("шанс посмертного", joined)

    def test_tz20_timer_and_sides(self):
        # ТЗ 20: предупреждение позже таймера — ошибка; командному PVP нужно 2 стороны.
        bad_timer = pvp.store().create("tt", {
            "name": "T", "pvp_type": "arena", "turn_seconds": 30, "warn_before_seconds": 60,
        })
        self.assertFalse(pvp.validate(bad_timer)["ok"])
        team = pvp.store().create("team", {
            "name": "Команды", "pvp_type": "team_vs_team",
            "sides": [{"name": "A", "players": "p1"}],  # только одна сторона
        })
        res = pvp.validate(team)
        self.assertTrue(res["ok"])  # это предупреждение, не ошибка
        self.assertTrue(any("сторон" in w.lower() for w in res["warnings"]))

    def test_tz20_side_without_participants_warns(self):
        env = pvp.store().create("sd", {
            "name": "Бой", "pvp_type": "team_vs_team",
            "sides": [{"name": "A", "players": "p1"}, {"name": "B"}],  # B пустая
        })
        res = pvp.validate(env)
        self.assertTrue(any("нет ни игроков" in w.lower() for w in res["warnings"]))

    def test_preview_steps(self):
        data = {
            "pvp_type": "duel", "enabled": True,
            "buttons": [{"action": "attack", "text": "Атаковать"}, {"action": "flee", "text": "Сбежать"}],
            "texts": [{"key": "invite", "text": "Вызов на дуэль!"}, {"key": "victory", "text": "Вы победили."}],
        }
        prev = pvp.preview(data)
        self.assertEqual(prev["pvp_type"], "Дуэль 1 на 1")
        self.assertIn("Атаковать", prev["buttons"])
        titles = {s["step"] for s in prev["steps"]}
        self.assertIn("Приглашение", titles)
        self.assertIn("Победа", titles)


class PvpApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("PVP_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["PVP_CONSTRUCTOR_PATH"] = str(base / "pvp.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_pvp_router(lambda: self.storage))
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

    def _create(self, token, pid="duel", data=None):
        body = {"id": pid, "data": data or {"name": "Дуэль", "pvp_type": "duel", "enabled": True}}
        return self.client.post("/api/admin/v2/pvp", headers=self._auth(token), json=body)

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/pvp/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        types = {t["value"] for t in meta.json()["pvpTypes"]}
        self.assertIn("duel", types)
        self.assertIn("arena", types)

    def test_create_validate_publish(self):
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        pub = self.client.post("/api/admin/v2/pvp/duel/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_publish_blocked_when_invalid(self):
        token = self._token()
        self._create(token, pid="bad", data={"name": "", "pvp_type": ""})
        pub = self.client.post("/api/admin/v2/pvp/bad/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 400, pub.text)

    def test_preview_endpoint(self):
        token = self._token()
        self._create(token, pid="dl", data={"name": "Д", "pvp_type": "duel", "texts": [{"key": "victory", "text": "Победа!"}]})
        pv = self.client.post("/api/admin/v2/pvp/dl/preview", headers=self._auth(token), json={})
        self.assertEqual(pv.status_code, 200, pv.text)
        self.assertEqual(pv.json()["preview"]["pvp_type"], "Дуэль 1 на 1")

    def test_content_cannot_publish_readonly_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)  # content создаёт черновик
        self.assertEqual(self.client.post("/api/admin/v2/pvp/duel/publish", headers=self._auth(token), json={}).status_code, 403)
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        ro = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/pvp", headers=self._auth(ro)).status_code, 200)
        self.assertEqual(self._create(ro, pid="nope").status_code, 403)


if __name__ == "__main__":
    unittest.main()
