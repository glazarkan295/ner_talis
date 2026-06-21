import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from admin_messages_api import create_admin_messages_router
from services import admin_rbac as rbac
from services import bot_message_queue as mq
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class MessageQueueTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("MESSAGE_QUEUE_PATH")
        os.environ["MESSAGE_QUEUE_PATH"] = str(Path(self._tmp.name) / "queue.json")
        self.addCleanup(self._restore)
        # Тест опирается на JSON-файловый backend (через MESSAGE_QUEUE_PATH);
        # сбрасываем глобальный backend, если предыдущий тест переключил его на БД.
        mq.use_json_file_backend()
        self.addCleanup(mq.use_json_file_backend)
        mq.set_sender(None)
        self.addCleanup(lambda: mq.set_sender(None))

    def _restore(self):
        if self._saved is None:
            os.environ.pop("MESSAGE_QUEUE_PATH", None)
        else:
            os.environ["MESSAGE_QUEUE_PATH"] = self._saved

    def _msg(self, **kw):
        base = dict(game_id="NT-1", platform="telegram", recipient="111", text="hi")
        base.update(kw)
        return mq.enqueue(**base)

    def test_dedupe_by_delivery_key(self):
        a, created_a = self._msg(delivery_key="reward:op1:NT-1")
        b, created_b = self._msg(delivery_key="reward:op1:NT-1")
        self.assertTrue(created_a)
        self.assertFalse(created_b)
        self.assertEqual(a["id"], b["id"])

    def test_dispatch_sends_with_sender(self):
        self._msg()
        counts = mq.dispatch_once(lambda m: (mq.RESULT_SENT, ""))
        self.assertEqual(counts["sent"], 1)
        self.assertEqual(mq.stats()["by_status"]["sent"], 1)

    def test_temporary_failure_retries_then_fails(self):
        msg, _ = self._msg(max_attempts=2)
        # 1st temporary failure -> retry_wait.
        mq.dispatch_once(lambda m: (mq.RESULT_FAILED_TEMPORARY, "net"))
        self.assertEqual(mq.get(msg["id"])["status"], "retry_wait")
        # Make it due, 2nd failure hits max -> failed.
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        mq.dispatch_once(lambda m: (mq.RESULT_FAILED_TEMPORARY, "net"), now=future)
        self.assertEqual(mq.get(msg["id"])["status"], "failed")

    def test_blocked_is_terminal(self):
        msg, _ = self._msg()
        mq.dispatch_once(lambda m: (mq.RESULT_BLOCKED, "blocked bot"))
        got = mq.get(msg["id"])
        self.assertEqual(got["status"], "blocked")

    def test_retry_and_cancel(self):
        msg, _ = self._msg()
        mq.dispatch_once(lambda m: (mq.RESULT_FAILED_PERMANENT, "bad"))
        self.assertEqual(mq.get(msg["id"])["status"], "failed")
        mq.retry(msg["id"])
        self.assertEqual(mq.get(msg["id"])["status"], "queued")
        mq.cancel(msg["id"])
        self.assertEqual(mq.get(msg["id"])["status"], "cancelled")

    def test_priority_order_in_dispatch(self):
        self._msg(priority="low", text="low")
        self._msg(priority="critical", text="crit")
        order = []
        mq.dispatch_once(lambda m: (order.append(m["text"]) or (mq.RESULT_SENT, "")))
        self.assertEqual(order[0], "crit")


class MessagesApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("MESSAGE_QUEUE_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["MESSAGE_QUEUE_PATH"] = str(base / "queue.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        mq.set_sender(None)
        self.addCleanup(lambda: mq.set_sender(None))
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_messages_router(lambda: self.storage))
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

    def _make_player(self):
        races = load_races("data/races.json")
        gid = self.storage.generate_game_id()
        player = create_player(game_id=gid, platform="telegram", external_user_id="424242", name="Игр", race_id="human", races=races)
        self.storage.save_new_player(player, "telegram", "424242")
        return gid

    def test_send_direct_enqueues_and_is_audited(self):
        token = self._token("999")
        gid = self._make_player()
        res = self.client.post("/api/admin/v2/messages/send", headers=self._auth(token), json={"game_id": gid, "text": "Привет!", "reason": "тест"})
        self.assertEqual(res.status_code, 200, res.text)
        msg = res.json()["message"]
        self.assertEqual(msg["platform"], "telegram")
        self.assertEqual(msg["recipient"], "424242")
        # Visible in the queue + player view.
        listing = self.client.get("/api/admin/v2/messages", headers=self._auth(token)).json()["messages"]
        self.assertTrue(listing)
        actions = {r["action"] for r in read_admin_audit_records()}
        self.assertIn("messages.send_direct", actions)

    def test_send_direct_requires_linked_account(self):
        token = self._token("999")
        # Player with no linked account.
        self.assertEqual(self.client.post("/api/admin/v2/messages/send", headers=self._auth(token), json={"game_id": "NT-NOPE", "text": "x"}).status_code, 404)

    def test_retry_and_cancel_endpoints(self):
        token = self._token("999")
        gid = self._make_player()
        msg_id = self.client.post("/api/admin/v2/messages/send", headers=self._auth(token), json={"game_id": gid, "text": "x"}).json()["message"]["id"]
        # default sender => failed_temporary => retry_wait; retry then cancel.
        self.assertEqual(self.client.post(f"/api/admin/v2/messages/{msg_id}/retry", headers=self._auth(token), json={}).status_code, 200)
        cancel = self.client.post(f"/api/admin/v2/messages/{msg_id}/cancel", headers=self._auth(token), json={})
        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertEqual(cancel.json()["message"]["status"], "cancelled")

    def test_read_only_can_view_but_not_send(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token("999")
        gid = self._make_player()
        self.assertEqual(self.client.get("/api/admin/v2/messages/stats", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/messages/send", headers=self._auth(token), json={"game_id": gid, "text": "x"}).status_code, 403)


class SqliteQueueBackendTest(unittest.TestCase):
    """Та же логика очереди поверх БД-хранилища (row-per-message)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.storage = SQLiteStorage(str(Path(self._tmp.name) / "players.sqlite3"))
        self.assertTrue(mq.configure_queue(self.storage))
        mq.set_sender(None)
        self.addCleanup(mq.use_json_file_backend)
        self.addCleanup(lambda: mq.set_sender(None))

    def test_enqueue_dedupe_and_dispatch_on_db(self):
        a, created_a = mq.enqueue(game_id="NT-1", platform="telegram", recipient="111", text="hi", delivery_key="k1")
        b, created_b = mq.enqueue(game_id="NT-1", platform="telegram", recipient="111", text="hi2", delivery_key="k1")
        self.assertTrue(created_a)
        self.assertFalse(created_b)
        self.assertEqual(a["id"], b["id"])
        # Dispatch with a fake sender marks it sent in the DB.
        counts = mq.dispatch_once(lambda m: (mq.RESULT_SENT, ""))
        self.assertEqual(counts["sent"], 1)
        self.assertEqual(mq.get(a["id"])["status"], "sent")
        self.assertEqual(mq.stats()["by_status"]["sent"], 1)

    def test_priority_and_retry_backoff_on_db(self):
        mq.enqueue(game_id="NT-1", platform="telegram", recipient="1", text="low", priority="low")
        crit, _ = mq.enqueue(game_id="NT-1", platform="telegram", recipient="1", text="crit", priority="critical")
        order = []
        mq.dispatch_once(lambda m: (order.append(m["text"]) or (mq.RESULT_FAILED_TEMPORARY, "net")))
        self.assertEqual(order[0], "crit")  # critical claimed first
        self.assertEqual(mq.get(crit["id"])["status"], "retry_wait")

    def test_list_and_player_filter_on_db(self):
        mq.enqueue(game_id="NT-A", platform="telegram", recipient="1", text="a")
        mq.enqueue(game_id="NT-B", platform="vk", recipient="2", text="b")
        self.assertEqual(len(mq.list_messages(game_id="NT-A")), 1)
        self.assertEqual(len(mq.list_messages()), 2)

    def test_meta_persists_on_db(self):
        mq.enqueue(game_id="NT-1", platform="telegram", recipient="1", text="x")
        mq.dispatch_once(lambda m: (mq.RESULT_SENT, ""))
        self.assertIsNotNone(mq.dispatcher_status()["last_run"])


if __name__ == "__main__":
    unittest.main()
