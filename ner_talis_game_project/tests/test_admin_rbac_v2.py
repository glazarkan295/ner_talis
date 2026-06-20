import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import admin_rbac as rbac
from services.admin_audit import read_admin_audit_records
from services.admin_operation import (
    DANGEROUS_ACTIONS,
    record_admin_operation,
    run_admin_operation,
)


class RbacMatrixTest(unittest.TestCase):
    def test_owner_has_every_permission(self):
        for perm in rbac.ALL_PERMISSIONS:
            self.assertTrue(rbac.has_permission(rbac.OWNER, perm), perm)

    def test_support_scope(self):
        self.assertTrue(rbac.has_permission(rbac.SUPPORT, rbac.PERM_PLAYERS_VIEW))
        self.assertTrue(rbac.has_permission(rbac.SUPPORT, rbac.PERM_PLAYERS_UNSTUCK))
        self.assertTrue(rbac.has_permission(rbac.SUPPORT, rbac.PERM_REWARDS_GRANT))
        # Не может: удалять, менять валюту произвольно, массово выдавать.
        self.assertFalse(rbac.has_permission(rbac.SUPPORT, rbac.PERM_PLAYERS_DELETE))
        self.assertFalse(rbac.has_permission(rbac.SUPPORT, rbac.PERM_CURRENCY_CHANGE))
        self.assertFalse(rbac.has_permission(rbac.SUPPORT, rbac.PERM_REWARDS_BULK))

    def test_moderator_scope(self):
        self.assertTrue(rbac.has_permission(rbac.MODERATOR, rbac.PERM_MOD_WARN))
        self.assertTrue(rbac.has_permission(rbac.MODERATOR, rbac.PERM_MOD_MUTE))
        # Не может выдавать награды/валюту/удалять.
        self.assertFalse(rbac.has_permission(rbac.MODERATOR, rbac.PERM_REWARDS_GRANT))
        self.assertFalse(rbac.has_permission(rbac.MODERATOR, rbac.PERM_CURRENCY_CHANGE))
        self.assertFalse(rbac.has_permission(rbac.MODERATOR, rbac.PERM_PLAYERS_DELETE))

    def test_content_scope(self):
        self.assertTrue(rbac.has_permission(rbac.CONTENT, rbac.PERM_CONTENT_EDIT))
        self.assertTrue(rbac.has_permission(rbac.CONTENT, rbac.PERM_ASSETS_MANAGE))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, rbac.PERM_REWARDS_GRANT))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, rbac.PERM_PLAYERS_DELETE))

    def test_economy_scope(self):
        self.assertTrue(rbac.has_permission(rbac.ECONOMY, rbac.PERM_ECONOMY_MANAGE))
        self.assertFalse(rbac.has_permission(rbac.ECONOMY, rbac.PERM_MOD_WARN))
        self.assertFalse(rbac.has_permission(rbac.ECONOMY, rbac.PERM_PLAYERS_DELETE))

    def test_admin_has_all_but_roles_manage(self):
        self.assertTrue(rbac.has_permission(rbac.ADMIN, rbac.PERM_PLAYERS_DELETE))
        self.assertTrue(rbac.has_permission(rbac.ADMIN, rbac.PERM_REWARDS_BULK))
        self.assertFalse(rbac.has_permission(rbac.ADMIN, rbac.PERM_ROLES_MANAGE))
        self.assertTrue(rbac.has_permission(rbac.OWNER, rbac.PERM_ROLES_MANAGE))

    def test_read_only_has_no_mutations(self):
        for perm in (rbac.PERM_PLAYERS_DELETE, rbac.PERM_REWARDS_GRANT,
                     rbac.PERM_CURRENCY_CHANGE, rbac.PERM_MOD_WARN,
                     rbac.PERM_PROMOS_MANAGE, rbac.PERM_BROADCAST_SEND,
                     rbac.PERM_WORLD_PUBLISH, rbac.PERM_WORLD_CREATE_DRAFT,
                     rbac.PERM_WORLD_EVENT_START, rbac.PERM_GUILD_CREATE):
            self.assertFalse(rbac.has_permission(rbac.READ_ONLY, perm), perm)
        self.assertTrue(rbac.has_permission(rbac.READ_ONLY, rbac.PERM_PLAYERS_VIEW))
        # read_only всё же видит мир/события/гильдии (view-роль).
        self.assertTrue(rbac.has_permission(rbac.READ_ONLY, rbac.PERM_WORLD_VIEW))
        self.assertTrue(rbac.has_permission(rbac.READ_ONLY, rbac.PERM_WORLD_EVENT_VIEW))

    def test_world_constructor_scope(self):
        # content делает черновики и проверки, но не публикует/не отключает.
        self.assertTrue(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_CREATE_DRAFT))
        self.assertTrue(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_EDIT_DRAFT))
        self.assertTrue(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_VALIDATE))
        self.assertTrue(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_TEST_RUN))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_PUBLISH))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_DISABLE))
        # publish/launch — у admin и owner.
        self.assertTrue(rbac.has_permission(rbac.ADMIN, rbac.PERM_WORLD_PUBLISH))
        self.assertTrue(rbac.has_permission(rbac.OWNER, rbac.PERM_WORLD_PUBLISH))

    def test_guild_and_world_event_scope(self):
        # content создаёт черновики событий, но не запускает и не выдаёт награды.
        self.assertTrue(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_EVENT_CREATE))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_EVENT_START))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, rbac.PERM_WORLD_EVENT_REWARD))
        # economy подтверждает награды событий.
        self.assertTrue(rbac.has_permission(rbac.ECONOMY, rbac.PERM_WORLD_EVENT_REWARD))
        # moderator модерирует состав гильдий.
        self.assertTrue(rbac.has_permission(rbac.MODERATOR, rbac.PERM_GUILD_MANAGE_MEMBERS))
        self.assertFalse(rbac.has_permission(rbac.MODERATOR, rbac.PERM_GUILD_DISABLE))

    def test_new_dangerous_actions_flagged(self):
        for action in ("world.publish", "world_event.start", "world_event.reward",
                       "guild.disable"):
            self.assertIn(action, rbac.DANGEROUS_ACTIONS, action)


class RoleResolutionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = {k: os.environ.get(k) for k in
                       ("ADMIN_ROLES_PATH", "TELEGRAM_ADMIN_USER_IDS", "VK_ADMIN_USER_IDS")}
        os.environ["ADMIN_ROLES_PATH"] = str(Path(self._tmp.name) / "admin_roles.json")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "111,222"
        os.environ["VK_ADMIN_USER_IDS"] = "900"
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_env_admin_is_owner_by_default(self):
        self.assertEqual(rbac.resolve_admin_role("telegram", "111"), rbac.OWNER)
        self.assertEqual(rbac.resolve_admin_role("vk", "900"), rbac.OWNER)

    def test_non_admin_defaults_to_read_only(self):
        self.assertEqual(rbac.resolve_admin_role("telegram", "555"), rbac.READ_ONLY)

    def test_storage_override_wins_over_env(self):
        rbac.set_role_override("telegram", "222", rbac.SUPPORT)
        self.assertEqual(rbac.resolve_admin_role("telegram", "222"), rbac.SUPPORT)
        # Override persists and can be removed -> back to ENV owner.
        self.assertTrue(rbac.remove_role_override("telegram", "222"))
        self.assertEqual(rbac.resolve_admin_role("telegram", "222"), rbac.OWNER)

    def test_override_can_promote_non_env_user(self):
        rbac.set_role_override("telegram", "777", rbac.MODERATOR)
        self.assertEqual(rbac.resolve_admin_role("telegram", "777"), rbac.MODERATOR)

    def test_require_permission(self):
        owner_session = {"platform": "telegram", "admin_user_id": "111"}
        rbac.set_role_override("telegram", "333", rbac.SUPPORT)
        support_session = {"platform": "telegram", "admin_user_id": "333"}
        self.assertEqual(rbac.require_permission(owner_session, rbac.PERM_PLAYERS_DELETE), rbac.OWNER)
        with self.assertRaises(PermissionError):
            rbac.require_permission(support_session, rbac.PERM_PLAYERS_DELETE)


class AdminOperationAuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = {k: os.environ.get(k) for k in
                       ("ADMIN_AUDIT_LOG_PATH", "ADMIN_ROLES_PATH", "TELEGRAM_ADMIN_USER_IDS")}
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(Path(self._tmp.name) / "audit.log")
        os.environ["ADMIN_ROLES_PATH"] = str(Path(self._tmp.name) / "admin_roles.json")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "111"
        self.addCleanup(self._restore)
        self.session = {"platform": "telegram", "admin_user_id": "111", "token": "sess-abc"}

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_record_writes_structured_audit_with_before_after(self):
        record_admin_operation(
            session=self.session, action="player.money_change",
            target_type="player", target_id="NT-1", target_name="Иван",
            before={"money": 100}, after={"money": 50}, reason="возврат",
        )
        rows = read_admin_audit_records()
        self.assertEqual(len(rows), 1)
        rec = rows[0]
        self.assertEqual(rec["action"], "player.money_change")
        self.assertEqual(rec["admin_role"], rbac.OWNER)
        self.assertEqual(rec["target_id"], "NT-1")
        self.assertEqual(rec["before"], {"money": 100})
        self.assertEqual(rec["after"], {"money": 50})
        self.assertEqual(rec["reason"], "возврат")
        self.assertEqual(rec["status"], "ok")

    def test_audit_filters(self):
        record_admin_operation(session=self.session, action="player.reward_grant", target_id="NT-1")
        record_admin_operation(session=self.session, action="promo.delete", target_id="CODE1")
        record_admin_operation(session=self.session, action="player.money_change", target_id="NT-2", status="error", error="boom")

        self.assertEqual(len(read_admin_audit_records(action="promo.delete")), 1)
        self.assertEqual(len(read_admin_audit_records(target_id="NT-1")), 1)
        self.assertEqual(len(read_admin_audit_records(errors_only=True)), 1)
        dangerous = read_admin_audit_records(dangerous_only=True, dangerous_actions=DANGEROUS_ACTIONS)
        self.assertEqual([r["action"] for r in dangerous], ["promo.delete"])

    def test_run_admin_operation_records_success_and_error(self):
        result = run_admin_operation(
            session=self.session, action="player.reward_grant", target_id="NT-1",
            func=lambda: 42, after_func=lambda r: {"granted": r},
        )
        self.assertEqual(result, 42)
        ok_rows = read_admin_audit_records(action="player.reward_grant")
        self.assertEqual(ok_rows[0]["after"], {"granted": 42})

        with self.assertRaises(ValueError):
            run_admin_operation(
                session=self.session, action="player.delete", target_id="NT-9",
                func=lambda: (_ for _ in ()).throw(ValueError("nope")),
            )
        err_rows = read_admin_audit_records(action="player.delete")
        self.assertEqual(err_rows[0]["status"], "error")
        self.assertIn("nope", err_rows[0]["error"])


if __name__ == "__main__":
    unittest.main()
