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

from admin_site_api import create_admin_site_router
from services import admin_rbac as rbac
from services import site_content_registry as site
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class SiteContentServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("SITE_CONTENT_PATH")
        os.environ["SITE_CONTENT_PATH"] = str(Path(self._tmp.name) / "site.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("SITE_CONTENT_PATH", None)
        else:
            os.environ["SITE_CONTENT_PATH"] = self._saved

    def test_valid_news(self):
        env = site.store().create("update_1", {"_kind": "news", "title": "Обновление", "body": "Текст новости", "category": "Обновления"})
        self.assertTrue(site.validate("news", env)["ok"], site.validate("news", env)["errors"])

    def test_validation_rejects_html_and_empty(self):
        env = site.store().create("bad", {"_kind": "news", "title": "", "body": "<script>alert(1)</script>"})
        result = site.validate("news", env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("заголовок", joined)
        self.assertIn("html", joined)

    def test_faq_uses_question_answer(self):
        env = site.store().create("faq_energy", {"_kind": "faq", "question": "Как работает энергия?", "answer": "Энергия тратится на действия."})
        self.assertTrue(site.validate("faq", env)["ok"], site.validate("faq", env)["errors"])
        bad = site.store().create("faq_bad", {"_kind": "faq", "question": "Вопрос?"})  # no answer
        self.assertFalse(site.validate("faq", bad)["ok"])

    def test_date_order(self):
        env = site.store().create("ev", {"_kind": "news", "title": "T", "body": "B", "publish_at": "2026-12-10", "end_at": "2026-12-01"})
        self.assertFalse(site.validate("news", env)["ok"])


class SiteApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("SITE_CONTENT_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["SITE_CONTENT_PATH"] = str(base / "site.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_site_router(lambda: self.storage))
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

    def test_news_create_publish_and_kind_filter(self):
        token = self._token("999")
        self.client.post("/api/admin/v2/site/news", headers=self._auth(token), json={"id": "n1", "data": {"title": "Новость", "body": "Текст"}})
        self.client.post("/api/admin/v2/site/guide", headers=self._auth(token), json={"id": "g1", "data": {"title": "Гайд", "body": "Как играть"}})
        # Kind filter: /news returns only news.
        news = self.client.get("/api/admin/v2/site/news", headers=self._auth(token)).json()["items"]
        self.assertEqual([i["id"] for i in news], ["n1"])
        publish = self.client.post("/api/admin/v2/site/news/n1/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertIn("news.publish", dangerous)

    def test_publish_blocked_when_invalid(self):
        token = self._token("999")
        self.client.post("/api/admin/v2/site/news", headers=self._auth(token), json={"id": "bad", "data": {"title": "", "body": ""}})
        publish = self.client.post("/api/admin/v2/site/news/bad/publish", headers=self._auth(token), json={})
        self.assertEqual(publish.status_code, 400, publish.text)
        self.assertEqual(self.client.get("/api/admin/v2/site/news/bad", headers=self._auth(token)).json()["item"]["status"], "error")

    def test_content_can_draft_news_but_not_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        self.assertEqual(self.client.post("/api/admin/v2/site/news", headers=self._auth(token), json={"id": "n2", "data": {"title": "T", "body": "B"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/site/news/n2/publish", headers=self._auth(token), json={}).status_code, 403)

    def test_read_only_view_only(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token("999")
        self.assertEqual(self.client.get("/api/admin/v2/site/news", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/site/news", headers=self._auth(token), json={"id": "news_x", "data": {"title": "T", "body": "B"}}).status_code, 403)

    def test_banner_gated_by_homepage_edit(self):
        # content lacks site.homepage_edit -> can't create banners.
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        self.assertEqual(self.client.post("/api/admin/v2/site/banner", headers=self._auth(token), json={"id": "b1", "data": {"title": "B", "text": "T"}}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
