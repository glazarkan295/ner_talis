"""Feature flags V2 (full-import ТЗ §14, AC#12): сервис + API."""

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

from admin_feature_flags_api import create_admin_feature_flags_router
from services import admin_rbac as rbac
from services import feature_flags_service as ff
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class FeatureFlagServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("FEATURE_FLAGS_PATH")
        os.environ["FEATURE_FLAGS_PATH"] = str(Path(self._tmp.name) / "flags.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("FEATURE_FLAGS_PATH", None)
        else:
            os.environ["FEATURE_FLAGS_PATH"] = self._saved

    def test_defaults_all_false(self):
        flags = ff.all_flags()
        self.assertEqual(set(flags.keys()), set(ff.FLAGS))
        self.assertTrue(all(v is False for v in flags.values()))
        self.assertFalse(ff.is_enabled("use_v2_items"))

    def test_set_and_persist(self):
        ff.set_flag("use_v2_items", True)
        self.assertTrue(ff.is_enabled("use_v2_items"))
        # Прочитано из файла заново.
        self.assertTrue(ff.all_flags()["use_v2_items"])
        ff.set_flag("use_v2_items", False)
        self.assertFalse(ff.is_enabled("use_v2_items"))

    def test_unknown_flag_rejected(self):
        with self.assertRaises(ValueError):
            ff.set_flag("use_v2_bogus", True)
        self.assertFalse(ff.is_enabled("use_v2_bogus"))


class FeatureFlagApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("FEATURE_FLAGS_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["FEATURE_FLAGS_PATH"] = str(base / "flags.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_feature_flags_router(lambda: self.storage))
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

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/feature-flags").status_code, 401)

    def test_list_and_toggle(self):
        token = self._token()
        lst = self.client.get("/api/admin/v2/feature-flags", headers=self._auth(token))
        self.assertEqual(lst.status_code, 200, lst.text)
        self.assertIn("use_v2_items", lst.json()["flags"])
        self.assertFalse(lst.json()["flags"]["use_v2_items"])
        put = self.client.put("/api/admin/v2/feature-flags", headers=self._auth(token), json={"name": "use_v2_items", "enabled": True, "reason": "переход"})
        self.assertEqual(put.status_code, 200, put.text)
        self.assertTrue(put.json()["flags"]["use_v2_items"])
        # Изменение флага — опасное действие, попадает в аудит.
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertIn("system.feature_flag", dangerous)

    def test_unknown_flag_400(self):
        token = self._token()
        put = self.client.put("/api/admin/v2/feature-flags", headers=self._auth(token), json={"name": "use_v2_bogus", "enabled": True})
        self.assertEqual(put.status_code, 400, put.text)

    def test_read_only_cannot_toggle(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token()
        put = self.client.put("/api/admin/v2/feature-flags", headers=self._auth(token), json={"name": "use_v2_items", "enabled": True})
        self.assertEqual(put.status_code, 403, put.text)


if __name__ == "__main__":
    unittest.main()
