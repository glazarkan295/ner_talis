"""Конструктор квестов (ТЗ 2.0, файл 10): валидация, циклы этапов, API, RBAC."""

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

from admin_quest_api import create_admin_quest_router
from services import admin_rbac as rbac
from services import quest_constructor_service as quests
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class QuestServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("QUEST_CONSTRUCTOR_PATH")
        os.environ["QUEST_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "quests.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("QUEST_CONSTRUCTOR_PATH", None)
        else:
            os.environ["QUEST_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_quest(self):
        env = quests.store().create("herb_hunt", {
            "name": "Сбор трав", "quest_type": "side", "source_type": "npc",
            "source_npc_id": "herbalist", "min_level": 1, "max_level": 10,
            "completion_conditions": ["all_tasks_done"],
            "stages": [{"stage_id": "s1", "name": "Начало", "next_stage": "s2"},
                       {"stage_id": "s2", "name": "Конец"}],
            "tasks": [{"task_type": "gather_resource", "target_id": "herb", "required_count": 5, "stage_id": "s1"}],
            "rewards": [{"type": "currency", "object_id": "gold", "count": 100}],
        })
        result = quests.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = quests.store().create("bad", {
            "name": "", "quest_type": "bogus", "min_level": 20, "max_level": 5,
            "completion_conditions": [],
            "stages": [{"stage_id": "s1", "next_stage": "s404"}],
        })
        result = quests.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("название квеста", joined)
        self.assertIn("тип квеста", joined)
        self.assertIn("больше максимального", joined)
        self.assertIn("условия завершения", joined)
        self.assertIn("не существует", joined)

    def test_stage_cycle_detected(self):
        # Этапы образуют цикл s1 -> s2 -> s1.
        env = quests.store().create("loop", {
            "name": "Петля", "quest_type": "story", "completion_conditions": ["x"],
            "stages": [{"stage_id": "s1", "next_stage": "s2"},
                       {"stage_id": "s2", "next_stage": "s1"}],
        })
        result = quests.validate(env)
        self.assertFalse(result["ok"])
        self.assertTrue(any("бесконечный цикл" in e.lower() for e in result["errors"]), result["errors"])

    def test_no_cycle_helper(self):
        self.assertFalse(quests.has_stage_cycle([{"stage_id": "a", "next_stage": "b"}, {"stage_id": "b"}]))
        self.assertTrue(quests.has_stage_cycle([{"stage_id": "a", "next_stage": "a"}]))

    def test_repeatable_without_cooldown_warns(self):
        env = quests.store().create("daily", {
            "name": "Ежедневка", "quest_type": "daily", "repeat_mode": "daily",
            "completion_conditions": ["x"],
        })
        res = quests.validate(env)
        self.assertTrue(res["ok"])  # предупреждение, не ошибка
        self.assertTrue(any("кулдаун повтора" in w.lower() for w in res["warnings"]))

    def test_preview(self):
        prev = quests.preview({
            "name": "Сбор трав", "quest_type": "side",
            "stages": [{"stage_id": "s1", "name": "Начало"}],
            "rewards": [{"type": "exp", "count": 50}],
        })
        self.assertEqual(prev["name"], "Сбор трав")
        self.assertEqual(prev["quest_type"], "Побочный")
        self.assertEqual(len(prev["stages"]), 1)


class QuestApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("QUEST_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["QUEST_CONSTRUCTOR_PATH"] = str(base / "quests.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_quest_router(lambda: self.storage))
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

    def _create(self, token, qid="q1", data=None):
        body = {"id": qid, "data": data or {"name": "Квест", "quest_type": "side", "completion_conditions": ["x"]}}
        return self.client.post("/api/admin/v2/quests", headers=self._auth(token), json=body)

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/quests/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        types = {t["value"] for t in meta.json()["questTypes"]}
        self.assertIn("story", types)
        self.assertIn("daily", types)

    def test_create_validate_publish(self):
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        pub = self.client.post("/api/admin/v2/quests/q1/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_publish_blocked_when_invalid(self):
        token = self._token()
        self._create(token, qid="bad", data={"name": "", "quest_type": ""})
        pub = self.client.post("/api/admin/v2/quests/bad/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 400, pub.text)

    def test_preview_endpoint(self):
        token = self._token()
        self._create(token, qid="q2", data={"name": "Сюжет", "quest_type": "story", "completion_conditions": ["x"]})
        pv = self.client.post("/api/admin/v2/quests/q2/preview", headers=self._auth(token), json={})
        self.assertEqual(pv.status_code, 200, pv.text)
        self.assertEqual(pv.json()["preview"]["quest_type"], "Сюжетный")

    def test_content_cannot_publish_readonly_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/quests/q1/publish", headers=self._auth(token), json={}).status_code, 403)
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        ro = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/quests", headers=self._auth(ro)).status_code, 200)
        self.assertEqual(self._create(ro, qid="nope").status_code, 403)


if __name__ == "__main__":
    unittest.main()
