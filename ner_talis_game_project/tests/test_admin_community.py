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

from admin_community_api import create_admin_community_router
from services import admin_rbac as rbac
from services import guild_service, world_event_service
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class GuildServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("GUILDS_PATH")
        os.environ["GUILDS_PATH"] = str(Path(self._tmp.name) / "guilds.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("GUILDS_PATH", None)
        else:
            os.environ["GUILDS_PATH"] = self._saved

    def test_validation_and_members(self):
        env = guild_service.store().create("iron_wolves", {"name": "Железные волки", "guild_type": "player", "max_members": 2})
        self.assertEqual(env["status"], "draft")
        self.assertTrue(guild_service.validate(env)["ok"])
        guild_service.add_member("iron_wolves", "NT-1", "leader")
        guild_service.add_member("iron_wolves", "NT-2", "member")
        with self.assertRaises(Exception):
            guild_service.add_member("iron_wolves", "NT-1")  # duplicate
        env = guild_service.set_member_role("iron_wolves", "NT-2", "officer")
        members = (env["data"] or {}).get("members")
        self.assertEqual(len(members), 2)
        # Over max_members -> validation error.
        guild_service.add_member("iron_wolves", "NT-3")
        self.assertFalse(guild_service.validate(guild_service.store().get("iron_wolves"))["ok"])

    def test_status_transition_guard(self):
        guild_service.store().create("g1", {"name": "G"})
        with self.assertRaises(Exception):
            guild_service.store().set_status("g1", "disbanded")  # draft can't disband directly


class WorldEventServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("WORLD_EVENTS_PATH")
        os.environ["WORLD_EVENTS_PATH"] = str(Path(self._tmp.name) / "events.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("WORLD_EVENTS_PATH", None)
        else:
            os.environ["WORLD_EVENTS_PATH"] = self._saved

    def test_validation_dates_and_multipliers(self):
        env = world_event_service.store().create("ny", {
            "name": "Новый год", "type": "festive",
            "start_date": "2026-12-31", "end_date": "2027-01-10", "exp_multiplier": 2,
        })
        self.assertTrue(world_event_service.validate(env)["ok"])
        bad = world_event_service.store().create("bad", {
            "name": "Плохое", "type": "weird",
            "start_date": "2026-05-10", "end_date": "2026-05-01", "drop_multiplier": 99,
        })
        result = world_event_service.validate(bad)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("позже", joined)
        self.assertIn("множитель", joined)

    def test_rewards_are_real_and_idempotent(self):
        class Storage:
            def __init__(self): self.players = {"P1": {"game_id": "P1", "money": 0, "experience": 0, "total_experience": 0}}
            def list_player_audience_rows(self): return [{"game_id": "P1"}]
            def get_player_by_game_id(self, gid): return self.players.get(gid)
            def update_player(self, player): self.players[player["game_id"]] = player
            def enqueue_bot_messages(self, game_id, messages): return None
        world_event_service.store().create("wave", {"name": "Волна", "type": "mob_invasion", "rewards": [
            {"type": "coins", "currency": "copper", "amount": 50}, {"type": "experience", "amount": 10}
        ]})
        storage = Storage()
        first = world_event_service.distribute_rewards(storage, "wave")
        second = world_event_service.distribute_rewards(storage, "wave")
        self.assertEqual(first["granted"], 1)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(storage.players["P1"]["money"], 50)
        self.assertEqual(storage.players["P1"]["experience"], 10)


class CommunityApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("GUILDS_PATH", "WORLD_EVENTS_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["GUILDS_PATH"] = str(base / "guilds.json")
        os.environ["WORLD_EVENTS_PATH"] = str(base / "events.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_community_router(lambda: self.storage))
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

    def test_guild_lifecycle_and_members_audited(self):
        token = self._token("999")
        created = self.client.post("/api/admin/v2/guilds", headers=self._auth(token), json={"id": "g1", "data": {"name": "Гильдия", "guild_type": "player"}})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(self.client.post("/api/admin/v2/guilds/g1/activate", headers=self._auth(token), json={}).json()["item"]["status"], "active")
        member = self.client.post("/api/admin/v2/guilds/g1/members", headers=self._auth(token), json={"user_id": "NT-7", "role": "leader"})
        self.assertEqual(member.status_code, 200, member.text)
        disband = self.client.post("/api/admin/v2/guilds/g1/disband", headers=self._auth(token), json={"reason": "нарушения"})
        self.assertEqual(disband.json()["item"]["status"], "disbanded")
        actions = {r["action"] for r in read_admin_audit_records()}
        self.assertTrue({"guild.create", "guild.activate", "guild.member_add"} <= actions)
        # disband is the dangerous guild.disable action.
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertIn("guild.disable", dangerous)

    def test_event_start_blocked_until_valid(self):
        token = self._token("999")
        # Missing name/dates -> start fails validation.
        self.client.post("/api/admin/v2/events", headers=self._auth(token), json={"id": "ev1", "data": {"type": "festive"}})
        blocked = self.client.post("/api/admin/v2/events/ev1/start", headers=self._auth(token), json={})
        self.assertEqual(blocked.status_code, 400, blocked.text)
        # Fix it, then schedule + start.
        self.client.put("/api/admin/v2/events/ev1", headers=self._auth(token), json={"data": {"name": "Праздник", "start_date": "2026-12-01", "end_date": "2026-12-09"}})
        started = self.client.post("/api/admin/v2/events/ev1/start", headers=self._auth(token), json={"reason": "запуск"})
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["item"]["status"], "active")

    def test_content_can_draft_event_but_not_start(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        self.assertEqual(self.client.post("/api/admin/v2/events", headers=self._auth(token), json={"id": "ev2", "data": {"name": "x"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/events/ev2/start", headers=self._auth(token), json={}).status_code, 403)

    def test_read_only_cannot_create_guild(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token("999")
        self.assertEqual(self.client.post("/api/admin/v2/guilds", headers=self._auth(token), json={"id": "g9", "data": {"name": "x"}}).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/v2/guilds", headers=self._auth(token)).status_code, 200)


if __name__ == "__main__":
    unittest.main()
