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
from services.registration_service import create_player, load_races
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

    def _make_player(self, *, name="Странник", external_user_id="111"):
        races = load_races("data/races.json")
        game_id = self.storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id=external_user_id,
            name=name,
            race_id="human",
            races=races,
        )
        self.storage.save_new_player(player, "telegram", external_user_id)
        return game_id

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

    def test_view_token_requires_edit_right(self):
        # Codex P1: read-only/просмотровая роль не должна получать редактируемый
        # токен профиля (даёт правки инвентаря/имени/очков/курьера).
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._session_token("999")
        resp = self.client.post("/api/admin/v2/players/ANYID/view-token", headers=self._auth(token), json={})
        self.assertEqual(resp.status_code, 403, resp.text)

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

    # ---- Player control-center ------------------------------------------

    def test_owner_lists_and_opens_player_card(self):
        gid = self._make_player(name="Карточкин")
        token = self._session_token("999")
        listing = self.client.get("/api/admin/v2/players", headers=self._auth(token))
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertTrue(any(p["game_id"] == gid for p in listing.json()["players"]))
        card = self.client.get(f"/api/admin/v2/players/{gid}", headers=self._auth(token))
        self.assertEqual(card.status_code, 200, card.text)
        body = card.json()["player"]
        self.assertEqual(body["game_id"], gid)
        self.assertEqual(body["level"], 1)
        self.assertIn("fines", body)

    def test_owner_can_unstuck_message_and_grant_audited(self):
        gid = self._make_player()
        token = self._session_token("999")
        self.assertEqual(
            self.client.post(f"/api/admin/v2/players/{gid}/unstuck", headers=self._auth(token), json={"reason": "застрял"}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(f"/api/admin/v2/players/{gid}/message", headers=self._auth(token), json={"text": "привет"}).status_code,
            200,
        )
        grant = self.client.post(
            f"/api/admin/v2/players/{gid}/rewards",
            headers=self._auth(token),
            json={"rewards": [{"item_id": "money_copper", "amount": 100}], "reason": "компенсация"},
        )
        self.assertEqual(grant.status_code, 200, grant.text)
        # Player got the coins.
        card = self.client.get(f"/api/admin/v2/players/{gid}", headers=self._auth(token)).json()["player"]
        self.assertGreaterEqual(card["money"], 100)
        # All three actions are in the audit.
        audit = self.client.get("/api/admin/v2/audit", headers=self._auth(token)).json()["records"]
        actions = {r["action"] for r in audit}
        self.assertTrue({"player.unstuck", "player.message", "rewards.grant"} <= actions)

    def test_owner_can_reset_and_delete_player(self):
        gid = self._make_player()
        token = self._session_token("999")
        reset = self.client.post(f"/api/admin/v2/players/{gid}/reset", headers=self._auth(token), json={"reason": "по просьбе"})
        self.assertEqual(reset.status_code, 200, reset.text)
        delete = self.client.request(
            "DELETE",
            f"/api/admin/v2/players/{gid}",
            headers=self._auth(token),
            json={"reason": "бан", "confirm": "CONFIRM_DELETE"},
        )
        self.assertEqual(delete.status_code, 200, delete.text)
        # Gone now.
        self.assertEqual(self.client.get(f"/api/admin/v2/players/{gid}", headers=self._auth(token)).status_code, 404)
        audit = {r["action"] for r in self.client.get("/api/admin/v2/audit?dangerous_only=true", headers=self._auth(token)).json()["records"]}
        self.assertIn("player.reset", audit)
        self.assertIn("player.delete", audit)

    def test_forgive_fine_clears_active_fines(self):
        gid = self._make_player()
        player = self.storage.get_player_by_game_id(gid)
        player["active_fines"] = [{"id": "fine_test_1", "status": "voluntary", "current_amount": 500, "current_day": 1, "source_name": "Налёт"}]
        player["active_fine"] = player["active_fines"][0]
        self.storage.update_player(player)
        token = self._session_token("999")
        card = self.client.get(f"/api/admin/v2/players/{gid}", headers=self._auth(token)).json()["player"]
        self.assertEqual(len(card["fines"]), 1)
        res = self.client.post(f"/api/admin/v2/players/{gid}/forgive-fine", headers=self._auth(token), json={"reason": "прощено"})
        self.assertEqual(res.status_code, 200, res.text)
        card2 = self.client.get(f"/api/admin/v2/players/{gid}", headers=self._auth(token)).json()["player"]
        self.assertEqual(card2["fines"], [])

    def test_support_can_unstuck_but_not_reset_or_delete(self):
        gid = self._make_player()
        rbac.set_role_override("telegram", "999", rbac.SUPPORT)
        token = self._session_token("999")
        self.assertEqual(self.client.post(f"/api/admin/v2/players/{gid}/unstuck", headers=self._auth(token), json={}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/admin/v2/players/{gid}/reset", headers=self._auth(token), json={}).status_code, 403)
        self.assertEqual(
            self.client.request("DELETE", f"/api/admin/v2/players/{gid}", headers=self._auth(token), json={"reason": "x"}).status_code,
            403,
        )

    def test_readonly_can_view_but_not_act(self):
        gid = self._make_player()
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._session_token("999")
        self.assertEqual(self.client.get(f"/api/admin/v2/players/{gid}", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self.client.post(f"/api/admin/v2/players/{gid}/message", headers=self._auth(token), json={"text": "x"}).status_code, 403)
        self.assertEqual(
            self.client.post(f"/api/admin/v2/players/{gid}/rewards", headers=self._auth(token), json={"rewards": [{"item_id": "money_copper", "amount": 1}]}).status_code,
            403,
        )


    # ---- V1 panel mutations now flow through the structured audit --------

    def test_v1_panel_mutations_emit_structured_operation_records(self):
        from services.admin_audit import read_admin_audit_records
        from services.admin_panel_service import (
            create_admin_promo,
            delete_admin_promo,
            deliver_rewards_to_player,
        )

        # A V1 admin session is just a dict with platform + admin_user_id.
        sess = {"platform": "telegram", "admin_user_id": "999"}
        gid = self._make_player(name="Аудитов")

        deliver_rewards_to_player(
            self.storage,
            target_game_id=gid,
            rewards=[{"item_id": "money_copper", "amount": 50}],
            admin_session=sess,
            reason="компенсация",
        )
        create_admin_promo(
            self.storage, code="AUD10", uses_left=3, duration="never",
            rewards=[{"item_id": "money_copper", "amount": 10}], admin_session=sess,
        )
        delete_admin_promo(self.storage, code="AUD10", admin_session=sess)

        grant = read_admin_audit_records(action="rewards.grant")
        self.assertTrue(grant)
        self.assertEqual(grant[0]["admin_role"], rbac.OWNER)
        self.assertEqual(grant[0]["reason"], "компенсация")
        self.assertEqual(grant[0]["target_id"], gid)

        self.assertTrue(read_admin_audit_records(action="promo.create"))

        deleted = read_admin_audit_records(
            action="promo.delete", dangerous_actions=rbac.DANGEROUS_ACTIONS
        )
        self.assertTrue(deleted)
        self.assertTrue(deleted[0]["dangerous"])

        # And they show up in the "dangerous only" view used by the audit page.
        dangerous = read_admin_audit_records(
            dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS
        )
        self.assertIn("promo.delete", {r["action"] for r in dangerous})


if __name__ == "__main__":
    unittest.main()
