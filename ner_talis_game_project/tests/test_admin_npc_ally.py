"""Конструктор NPC-союзников (ТЗ 21 §2): сервис, валидация, предпросмотр, API, RBAC."""

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

from admin_npc_ally_api import create_admin_npc_ally_router
from services import admin_rbac as rbac
from services import npc_ally_constructor_service as allies
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class NpcAllyServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("NPC_ALLY_CONSTRUCTOR_PATH")
        os.environ["NPC_ALLY_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "allies.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("NPC_ALLY_CONSTRUCTOR_PATH", None)
        else:
            os.environ["NPC_ALLY_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_ally(self):
        env = allies.store().create("squire", {
            "name": "Оруженосец", "ally_type": "combat", "acquire_method": "hire",
            "cost": 100, "currency": "gold", "level": 5, "hp": 120,
            "crit_chance": 15, "loot_share_percent": 10,
            "combat_turn_mode": "after_player", "target_mode": "player",
            "abilities": ["attack", "protect_owner"], "can_die": True, "can_revive": True,
        })
        result = allies.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = allies.store().create("bad", {
            "name": "", "ally_type": "bogus",
            "hp": -5, "crit_chance": 150,
        })
        result = allies.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("имя", joined)
        self.assertIn("тип союзника", joined)
        self.assertIn("здоровье", joined)
        self.assertIn("критический шанс", joined)

    def test_revive_without_death_warns(self):
        env = allies.store().create("ghost", {
            "name": "Дух", "ally_type": "summon", "can_revive": True, "can_die": False,
        })
        res = allies.validate(env)
        self.assertTrue(res["ok"])  # это предупреждение, не ошибка
        self.assertTrue(any("воскресить" in w.lower() for w in res["warnings"]))

    def test_cost_without_currency_warns(self):
        env = allies.store().create("merc", {
            "name": "Наёмник", "ally_type": "mercenary", "cost": 50,
        })
        res = allies.validate(env)
        self.assertTrue(any("валюта" in w.lower() for w in res["warnings"]))

    def test_preview_card(self):
        prev = allies.preview({
            "name": "Лекарь", "ally_type": "healer", "level": 7,
            "hp": 90, "abilities": ["heal", "cleanse"], "combat_turn_mode": "auto",
        })
        self.assertEqual(prev["name"], "Лекарь")
        self.assertEqual(prev["ally_type"], "Лекарь")
        self.assertIn("heal", prev["abilities"])
        self.assertEqual(prev["combat_turn"], "Ходит автоматически")


class NpcAllyApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("NPC_ALLY_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["NPC_ALLY_CONSTRUCTOR_PATH"] = str(base / "allies.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_npc_ally_router(lambda: self.storage))
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

    def _create(self, token, aid="squire", data=None):
        body = {"id": aid, "data": data or {"name": "Оруженосец", "ally_type": "combat"}}
        return self.client.post("/api/admin/v2/npc-allies", headers=self._auth(token), json=body)

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/npc-allies/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        types = {t["value"] for t in meta.json()["allyTypes"]}
        self.assertIn("combat", types)
        self.assertIn("healer", types)

    def test_create_validate_publish(self):
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        pub = self.client.post("/api/admin/v2/npc-allies/squire/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_publish_blocked_when_invalid(self):
        token = self._token()
        self._create(token, aid="bad", data={"name": "", "ally_type": ""})
        pub = self.client.post("/api/admin/v2/npc-allies/bad/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 400, pub.text)

    def test_preview_endpoint(self):
        token = self._token()
        self._create(token, aid="hl", data={"name": "Лекарь", "ally_type": "healer"})
        pv = self.client.post("/api/admin/v2/npc-allies/hl/preview", headers=self._auth(token), json={})
        self.assertEqual(pv.status_code, 200, pv.text)
        self.assertEqual(pv.json()["preview"]["ally_type"], "Лекарь")

    def test_content_cannot_publish_readonly_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/npc-allies/squire/publish", headers=self._auth(token), json={}).status_code, 403)
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        ro = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/npc-allies", headers=self._auth(ro)).status_code, 200)
        self.assertEqual(self._create(ro, aid="nope").status_code, 403)


if __name__ == "__main__":
    unittest.main()
