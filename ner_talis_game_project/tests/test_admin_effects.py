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

from admin_effect_api import create_admin_effect_router
from services import admin_rbac as rbac
from services import effect_constructor_service as effects
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class EffectServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("EFFECT_CONSTRUCTOR_PATH")
        os.environ["EFFECT_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "effects.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("EFFECT_CONSTRUCTOR_PATH", None)
        else:
            os.environ["EFFECT_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_stat_modifier(self):
        env = effects.store().create("str_buff", {
            "effect_name": "Бонус силы", "effect_type": "stat_modifier", "stat": "strength",
            "flat_bonus": 5, "show_to_player": True, "player_text": "Повышает силу.",
        })
        self.assertTrue(effects.validate(env)["ok"], effects.validate(env)["errors"])

    def test_type_specific_requirements(self):
        env = effects.store().create("bad", {
            "effect_name": "Глюк", "effect_type": "max_resource_modifier",  # no resource
            "control_kind": "", "apply_chance_percent": 250,
        })
        result = effects.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("resource", joined)
        self.assertIn("шанс", joined)

    def test_anti_chain_warning_for_periodic(self):
        env = effects.store().create("poison", {
            "effect_name": "Яд", "effect_type": "periodic_damage", "target": "enemy",
            "percent_max_hp_damage": 10, "can_trigger_effects": True,
        })
        result = effects.validate(env)
        # valid (warnings only): high damage + chain are warnings, not errors.
        self.assertTrue(result["ok"], result["errors"])
        joined = " ".join(result["warnings"]).lower()
        self.assertIn("цепоч", joined)
        self.assertTrue(any("6%" in w or "предел" in w.lower() for w in result["warnings"]))

    def test_unknown_type_is_error(self):
        env = effects.store().create("weird", {"effect_name": "X", "effect_type": "telepathy"})
        self.assertFalse(effects.validate(env)["ok"])


class EffectApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("EFFECT_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["EFFECT_CONSTRUCTOR_PATH"] = str(base / "effects.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_effect_router(lambda: self.storage))
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

    def _create(self, token, eid="regen", data=None):
        return self.client.post("/api/admin/v2/effects", headers=self._auth(token), json={"id": eid, "data": data or {
            "effect_name": "Регенерация", "effect_type": "resource_regeneration", "resource": "hp",
            "percent_max_hp_heal": 2, "show_to_player": True, "player_text": "Лечит каждый ход.",
        }})

    def test_meta_and_publish_flow(self):
        token = self._token("999")
        meta = self.client.get("/api/admin/v2/effects/meta", headers=self._auth(token)).json()
        self.assertIn("zone_effect", meta["effectTypes"])
        self.assertEqual(self._create(token).status_code, 200)
        publish = self.client.post("/api/admin/v2/effects/regen/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertIn("effect.publish", dangerous)

    def test_publish_blocked_when_invalid(self):
        token = self._token("999")
        self._create(token, eid="bad", data={"effect_name": "", "effect_type": "stat_modifier"})  # no name, no stat
        publish = self.client.post("/api/admin/v2/effects/bad/publish", headers=self._auth(token), json={})
        self.assertEqual(publish.status_code, 400, publish.text)
        self.assertEqual(self.client.get("/api/admin/v2/effects/bad", headers=self._auth(token)).json()["item"]["status"], "error")

    def test_delete_requires_confirm(self):
        token = self._token("999")
        self._create(token, eid="temp")
        self.assertEqual(self.client.request("DELETE", "/api/admin/v2/effects/temp", headers=self._auth(token), json={"confirm": "wrong"}).status_code, 400)
        ok = self.client.request("DELETE", "/api/admin/v2/effects/temp", headers=self._auth(token), json={"confirm": "temp", "reason": "уборка"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertIsNone(effects.store().get("temp"))

    def test_content_can_draft_but_not_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/effects/regen/publish", headers=self._auth(token), json={}).status_code, 403)

    def test_read_only_view_only(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token("999")
        self.assertEqual(self.client.get("/api/admin/v2/effects", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self._create(token).status_code, 403)

    def test_history_and_rollback_endpoints(self):
        # Этап 1: история версий + откат через общий помощник версионирования.
        token = self._token("999")
        self._create(token, eid="regen")  # effect_name «Регенерация»
        self.client.put("/api/admin/v2/effects/regen", headers=self._auth(token), json={"data": {"effect_name": "Изменено"}})
        hist = self.client.get("/api/admin/v2/effects/regen/history", headers=self._auth(token))
        self.assertEqual(hist.status_code, 200, hist.text)
        self.assertIn(1, [h["version"] for h in hist.json()["history"]])
        rb = self.client.post("/api/admin/v2/effects/regen/rollback", headers=self._auth(token), json={"version": 1})
        self.assertEqual(rb.status_code, 200, rb.text)
        got = self.client.get("/api/admin/v2/effects/regen", headers=self._auth(token)).json()["item"]
        self.assertEqual(got["data"]["effect_name"], "Регенерация")

    def test_rollback_published_requires_publish_right(self):
        owner = self._token("999")
        self._create(owner, eid="reg2")
        self.client.put("/api/admin/v2/effects/reg2", headers=self._auth(owner), json={"data": {"effect_name": "v2"}})
        self.client.post("/api/admin/v2/effects/reg2/publish", headers=self._auth(owner), json={})
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        content_token = self._token("999")
        rb = self.client.post("/api/admin/v2/effects/reg2/rollback", headers=self._auth(content_token), json={"version": 1})
        self.assertEqual(rb.status_code, 403, rb.text)


if __name__ == "__main__":
    unittest.main()
