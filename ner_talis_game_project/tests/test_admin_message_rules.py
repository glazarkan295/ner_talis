"""Конструктор правил очереди сообщений (ТЗ 2.0 файл 18): валидация, API, RBAC."""

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

from admin_message_queue_api import create_admin_message_queue_router
from services import admin_rbac as rbac
from services import message_queue_rule_service as mq
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


def _v(data):
    return mq.validate({"id":"test_rule","data": data})


class MessageRuleServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("MESSAGE_QUEUE_RULES_PATH")
        os.environ["MESSAGE_QUEUE_RULES_PATH"] = str(Path(self._tmp.name) / "rules.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("MESSAGE_QUEUE_RULES_PATH", None)
        else:
            os.environ["MESSAGE_QUEUE_RULES_PATH"] = self._saved

    def test_valid_rule(self):
        r = _v({"name": "Боевые", "message_type": "combat", "source": "battle",
                "priority": 1, "send_mode": "after_battle", "platform": "both"})
        self.assertTrue(r["ok"], r["errors"])

    def test_errors(self):
        r = _v({"name": "", "message_type": "bogus", "priority": -3,
                "platform": "icq", "repeat_on_error": True})
        self.assertFalse(r["ok"])
        joined = " ".join(r["errors"]).lower()
        self.assertIn("название правила", joined)
        self.assertIn("тип сообщения", joined)
        self.assertIn("приоритет", joined)
        self.assertIn("платформа", joined)
        self.assertIn("лимит попыток", joined)

    def test_broadcast_high_priority_warns(self):
        r = _v({"name": "Рассылка", "message_type": "broadcast", "priority": 1})
        self.assertTrue(r["ok"])
        self.assertTrue(any("рассылка" in w.lower() and "высокий приоритет" in w.lower() for w in r["warnings"]))

    def test_combat_without_priority_warns(self):
        r = _v({"name": "Бой", "message_type": "combat"})
        self.assertTrue(any("без приоритета" in w.lower() for w in r["warnings"]))

    def test_priority_zero_allowed(self):
        r = _v({"name": "Ждущее", "message_type": "system", "priority": 0})
        self.assertTrue(r["ok"], r["errors"])

    def test_id_source_template_and_button_validation(self):
        r=mq.validate({"data":{"name":"X","message_type":"system","source":"missing","message_template":"{{unknown}}","buttons":[{"action":"teleport"}]}})
        self.assertFalse(r["ok"]);joined=" ".join(r["errors"])
        self.assertIn("ID правила",joined);self.assertIn("не существует",joined);self.assertIn("неизвестные переменные",joined);self.assertIn("Кнопка",joined)

    def test_preview_priority_labels(self):
        self.assertEqual(mq.preview({"message_type": "combat"})["priority"], "после таймера")
        self.assertEqual(mq.preview({"message_type": "system", "priority": 0})["priority"], "ждать сообщения")
        self.assertEqual(mq.preview({"message_type": "combat", "priority": 1})["priority"], "1")


class MessageRuleApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("MESSAGE_QUEUE_RULES_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["MESSAGE_QUEUE_RULES_PATH"] = str(base / "rules.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_message_queue_router(lambda: self.storage))
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

    def _create(self, token, rid="r1", data=None):
        body = {"id": rid, "data": data or {"name": "Правило", "message_type": "combat", "priority": 1}}
        return self.client.post("/api/admin/v2/message-rules", headers=self._auth(token), json=body)

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/message-rules/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        self.assertIn("combat", meta.json()["messageTypes"])
        self.assertIn("both", meta.json()["platforms"])

    def test_create_validate_publish(self):
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        pub = self.client.post("/api/admin/v2/message-rules/r1/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_content_cannot_publish_readonly_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/message-rules/r1/publish", headers=self._auth(token), json={}).status_code, 403)
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        ro = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/message-rules", headers=self._auth(ro)).status_code, 200)
        self.assertEqual(self._create(ro, rid="nope").status_code, 403)


if __name__ == "__main__":
    unittest.main()
