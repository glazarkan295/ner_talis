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

from admin_panel_v2_api import create_admin_panel_v2_router
from services import admin_rbac as rbac
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class AdminPanelV2Test(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in
                       ("ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")}
        os.environ["ADMIN_ROLES_PATH"] = str(base / "admin_roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"  # session admin -> owner via bootstrap
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_panel_v2_router(lambda: self.storage))
        self.client = TestClient(app)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _session_token(self, admin_user_id="999"):
        activation = create_admin_panel_activation_token(
            self.storage, platform="telegram", admin_user_id=admin_user_id
        )
        session = consume_or_read_admin_session(self.storage, activation)
        return session["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_me_returns_owner_role_and_permissions(self):
        token = self._session_token("999")
        res = self.client.get("/api/admin/v2/me", headers=self._auth(token))
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["role"], rbac.OWNER)
        self.assertTrue(body["isOwner"])
        self.assertIn(rbac.PERM_ROLES_MANAGE, body["permissions"])

    def test_owner_can_assign_role_and_it_is_audited(self):
        token = self._session_token("999")
        res = self.client.post("/api/admin/v2/roles", headers=self._auth(token), json={
            "platform": "telegram", "admin_user_id": "555", "role": "support", "reason": "новый саппорт",
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["role"], "support")
        # override persisted
        self.assertEqual(rbac.resolve_admin_role("telegram", "555"), "support")
        # audit recorded
        audit = self.client.get("/api/admin/v2/audit?action=roles.change", headers=self._auth(token)).json()
        self.assertTrue(audit["records"])
        rec = audit["records"][0]
        self.assertEqual(rec["after"]["role"], "support")
        self.assertEqual(rec["reason"], "новый саппорт")

    def test_owner_cannot_demote_self(self):
        token = self._session_token("999")
        res = self.client.post("/api/admin/v2/roles", headers=self._auth(token), json={
            "platform": "telegram", "admin_user_id": "999", "role": "support",
        })
        self.assertEqual(res.status_code, 400, res.text)
        self.assertIn("owner", res.json()["detail"].lower())

    def test_support_session_cannot_manage_roles_but_can_view_audit(self):
        # Downgrade the session admin to support.
        rbac.set_role_override("telegram", "999", rbac.SUPPORT)
        token = self._session_token("999")
        self.assertEqual(self.client.get("/api/admin/v2/me", headers=self._auth(token)).json()["role"], "support")
        self.assertEqual(self.client.get("/api/admin/v2/roles", headers=self._auth(token)).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/v2/audit", headers=self._auth(token)).status_code, 200)

    def test_moderator_session_cannot_view_audit(self):
        rbac.set_role_override("telegram", "999", rbac.MODERATOR)
        token = self._session_token("999")
        self.assertEqual(self.client.get("/api/admin/v2/audit", headers=self._auth(token)).status_code, 403)

    def test_missing_session_is_401(self):
        self.assertEqual(self.client.get("/api/admin/v2/me").status_code, 401)

    def test_owner_lists_sessions_with_masked_ids(self):
        token = self._session_token("999")
        res = self.client.get("/api/admin/v2/sessions", headers=self._auth(token))
        self.assertEqual(res.status_code, 200, res.text)
        sessions = res.json()["sessions"]
        self.assertTrue(sessions)
        current = next(s for s in sessions if s["isCurrent"])
        self.assertEqual(current["adminUserId"], "999")
        self.assertEqual(current["role"], rbac.OWNER)
        # Token never leaks; only a short hashed id is exposed.
        self.assertEqual(len(current["id"]), 16)
        self.assertNotIn("token", current)

    def test_owner_can_revoke_another_session(self):
        owner_token = self._session_token("999")
        # Second admin session to revoke.
        rbac.set_role_override("telegram", "555", rbac.SUPPORT)
        victim_token = self._session_token("555")
        sessions = self.client.get(
            "/api/admin/v2/sessions", headers=self._auth(owner_token)
        ).json()["sessions"]
        victim = next(s for s in sessions if s["adminUserId"] == "555")
        res = self.client.post(
            "/api/admin/v2/sessions/revoke",
            headers=self._auth(owner_token),
            json={"id": victim["id"], "reason": "подозрительная активность"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["removed"])
        # Revoked session no longer authenticates.
        self.assertEqual(
            self.client.get("/api/admin/v2/me", headers=self._auth(victim_token)).status_code,
            403,
        )
        # And it is audited.
        audit = self.client.get(
            "/api/admin/v2/audit?action=session.revoke", headers=self._auth(owner_token)
        ).json()
        self.assertTrue(audit["records"])

    def test_revoke_unknown_session_is_404(self):
        token = self._session_token("999")
        res = self.client.post(
            "/api/admin/v2/sessions/revoke",
            headers=self._auth(token),
            json={"id": "deadbeefdeadbeef"},
        )
        self.assertEqual(res.status_code, 404, res.text)

    def test_support_cannot_revoke_sessions(self):
        rbac.set_role_override("telegram", "999", rbac.SUPPORT)
        token = self._session_token("999")
        # Support can view sessions? PERM_SYSTEM_VIEW is not in support set -> 403.
        self.assertEqual(
            self.client.get("/api/admin/v2/sessions", headers=self._auth(token)).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/admin/v2/sessions/revoke",
                headers=self._auth(token),
                json={"id": "deadbeefdeadbeef"},
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
