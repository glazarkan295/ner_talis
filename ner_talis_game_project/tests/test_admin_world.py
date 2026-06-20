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

from admin_world_api import create_admin_world_router
from services import admin_rbac as rbac
from services import world_content_registry as registry
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class WorldRegistryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("WORLD_CONTENT_PATH")
        os.environ["WORLD_CONTENT_PATH"] = str(Path(self._tmp.name) / "world.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("WORLD_CONTENT_PATH", None)
        else:
            os.environ["WORLD_CONTENT_PATH"] = self._saved

    def test_create_requires_valid_id(self):
        with self.assertRaises(registry.ContentError):
            registry.create_content("location", "Bad ID!", {"name": "x"})

    def test_create_rejects_unknown_kind(self):
        with self.assertRaises(registry.ContentError):
            registry.create_content("dragon", "x", {})

    def test_lifecycle_and_duplicate_guard(self):
        env = registry.create_content("location", "small_plateau", {"name": "Малое плато"})
        self.assertEqual(env["status"], registry.STATUS_DRAFT)
        with self.assertRaises(registry.ContentError):
            registry.create_content("location", "small_plateau", {})
        # Update bumps version and clears validation.
        env2 = registry.update_content("location", "small_plateau", {"type": "wild"})
        self.assertEqual(env2["version"], 2)
        self.assertEqual(env2["data"]["type"], "wild")

    def test_invalid_status_transition_blocked(self):
        registry.create_content("location", "loc1", {"name": "L"})
        with self.assertRaises(registry.ContentError):
            registry.set_status("location", "loc1", registry.STATUS_PUBLISHED)

    def test_validation_flags_errors(self):
        env = registry.create_content("location", "loc2", {"type": "nope"})
        result = registry.validate_envelope(env)
        self.assertFalse(result["ok"])
        # Missing name, missing description, bad type.
        self.assertTrue(any("название" in e.lower() for e in result["errors"]))
        self.assertTrue(any("тип" in e.lower() for e in result["errors"]))

    def test_validation_blocks_markup(self):
        env = registry.create_content("location", "loc3", {
            "name": "Город", "short_description": "<script>x</script>", "type": "city",
        })
        result = registry.validate_envelope(env)
        self.assertFalse(result["ok"])

    def test_mob_validation_ok_with_currency_drop(self):
        env = registry.create_content("mob", "wolf", {
            "name": "Волк", "type": "beast", "min_level": 1, "max_level": 5,
            "hp": 50, "experience": 20, "coins": 10,
            "drop": [{"item_id": "money_copper", "chance": 60, "min_count": 5, "max_count": 20}],
        })
        result = registry.validate_envelope(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_button_requires_existing_locations(self):
        # Button pointing at a missing location fails; once the locations exist it passes.
        env = registry.create_content("button", "btn_go", {
            "text": "В город", "owner_location": "wild1", "action": "goto_location", "target": "city1",
            "show_telegram": True,
        })
        bad = registry.validate_envelope(env)
        self.assertFalse(bad["ok"])
        registry.create_content("location", "wild1", {"name": "Дичь", "type": "wild", "short_description": "x"})
        registry.create_content("location", "city1", {"name": "Город", "type": "city", "short_description": "x"})
        good = registry.validate_envelope(registry.get_content("button", "btn_go"))
        self.assertTrue(good["ok"], good["errors"])

    def test_transition_validation(self):
        registry.create_content("location", "loc_a", {"name": "A", "type": "wild", "short_description": "x"})
        registry.create_content("location", "loc_b", {"name": "B", "type": "city", "short_description": "x"})
        ok = registry.validate_envelope(registry.create_content("transition", "a_to_b", {
            "from_location": "loc_a", "to_location": "loc_b", "access_condition": "always", "cost": 5,
        }))
        self.assertTrue(ok["ok"], ok["errors"])
        # Self-loop + unknown target + bad condition + negative cost are errors.
        bad = registry.validate_envelope(registry.create_content("transition", "bad_one", {
            "from_location": "loc_a", "to_location": "loc_a", "access_condition": "nope", "cost": -3,
        }))
        self.assertFalse(bad["ok"])
        joined = " ".join(bad["errors"]).lower()
        self.assertIn("ту же локацию", joined)
        self.assertIn("условие", joined)

    def test_location_dead_end_warning_clears_with_exit(self):
        registry.create_content("location", "lonely", {"name": "Тупик", "type": "wild", "short_description": "x"})
        before = registry.validate_envelope(registry.get_content("location", "lonely"))
        self.assertTrue(any("тупик" in w.lower() for w in before["warnings"]))
        # Add an outgoing transition -> warning clears, still valid.
        registry.create_content("location", "exitloc", {"name": "Выход", "type": "city", "short_description": "x"})
        registry.create_content("transition", "out", {"from_location": "lonely", "to_location": "exitloc"})
        after = registry.validate_envelope(registry.get_content("location", "lonely"))
        self.assertFalse(any("тупик" in w.lower() for w in after["warnings"]))

    def test_mob_validation_catches_bad_drop_and_stats(self):
        env = registry.create_content("mob", "broken_mob", {
            "name": "Глюк", "type": "beast", "hp": 0,
            "drop": [
                {"item_id": "definitely_not_real_item_zzz", "chance": 150, "min_count": 9, "max_count": 2},
            ],
        })
        result = registry.validate_envelope(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("hp", joined)
        self.assertIn("не существует", joined)
        self.assertIn("шанс", joined)


class WorldApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("WORLD_CONTENT_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["WORLD_CONTENT_PATH"] = str(base / "world.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_world_router(lambda: self.storage))
        self.client = TestClient(app)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _token(self, uid="999"):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id=uid)
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _create_location(self, token, cid="small_plateau", data=None):
        return self.client.post(
            "/api/admin/v2/world/location",
            headers=self._auth(token),
            json={"id": cid, "data": data or {"name": "Малое плато", "type": "wild", "short_description": "Дикая земля"}},
        )

    def test_owner_full_lifecycle(self):
        token = self._token("999")
        created = self._create_location(token)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["item"]["status"], "draft")

        validate = self.client.post("/api/admin/v2/world/location/small_plateau/validate", headers=self._auth(token), json={})
        self.assertEqual(validate.status_code, 200, validate.text)
        self.assertTrue(validate.json()["validation"]["ok"])

        publish = self.client.post("/api/admin/v2/world/location/small_plateau/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")

        disable = self.client.post("/api/admin/v2/world/location/small_plateau/disable", headers=self._auth(token), json={})
        self.assertEqual(disable.status_code, 200, disable.text)
        self.assertEqual(disable.json()["item"]["status"], "disabled")

        # Audited with role + dangerous flag for publish.
        audit = {r["action"]: r for r in read_admin_audit_records()}
        self.assertIn("world.create_draft", audit)
        self.assertEqual(audit["world.publish"]["admin_role"], rbac.OWNER)
        self.assertTrue(audit["world.publish"]["dangerous"])

    def test_publish_blocked_when_validation_fails(self):
        token = self._token("999")
        # Missing name/description/type -> validation errors.
        self._create_location(token, cid="broken", data={"type": "nope"})
        publish = self.client.post("/api/admin/v2/world/location/broken/publish", headers=self._auth(token), json={})
        self.assertEqual(publish.status_code, 400, publish.text)
        # Object is flagged as error, not published.
        got = self.client.get("/api/admin/v2/world/location/broken", headers=self._auth(token)).json()["item"]
        self.assertEqual(got["status"], "error")

    def test_content_can_draft_but_not_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        created = self._create_location(token)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(
            self.client.post("/api/admin/v2/world/location/small_plateau/validate", headers=self._auth(token), json={}).status_code,
            200,
        )
        blocked = self.client.post("/api/admin/v2/world/location/small_plateau/publish", headers=self._auth(token), json={})
        self.assertEqual(blocked.status_code, 403)

    def test_read_only_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token("999")
        self.assertEqual(self._create_location(token).status_code, 403)
        # But can list.
        self.assertEqual(self.client.get("/api/admin/v2/world/location", headers=self._auth(token)).status_code, 200)

    def test_unknown_kind_is_404(self):
        token = self._token("999")
        self.assertEqual(self.client.get("/api/admin/v2/world/dragon", headers=self._auth(token)).status_code, 404)

    def test_meta_exposes_mob_kind_and_types(self):
        token = self._token("999")
        meta = self.client.get("/api/admin/v2/world/kinds", headers=self._auth(token)).json()
        self.assertIn("mob", meta["kinds"])
        self.assertIn("beast", meta["mobTypes"])

    def test_mob_create_validate_publish(self):
        token = self._token("999")
        created = self.client.post(
            "/api/admin/v2/world/mob",
            headers=self._auth(token),
            json={"id": "wolf", "data": {
                "name": "Волк", "type": "beast", "min_level": 1, "max_level": 5,
                "hp": 50, "experience": 20, "coins": 10,
                "drop": [{"item_id": "money_copper", "chance": 60, "min_count": 5, "max_count": 20}],
            }},
        )
        self.assertEqual(created.status_code, 200, created.text)
        publish = self.client.post("/api/admin/v2/world/mob/wolf/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")


if __name__ == "__main__":
    unittest.main()
