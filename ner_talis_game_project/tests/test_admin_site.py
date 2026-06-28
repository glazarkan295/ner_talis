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


class SiteExtendedKindsServiceTest(unittest.TestCase):
    """Расширенные типы конструктора сайта (§2): страницы/блоки/меню/рейтинги/лор/что-где/оформление."""

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

    def test_page_requires_title(self):
        ok = site.store().create("p_home", {"_kind": "page", "title": "Главная", "slug": "home", "visibility": "public"})
        self.assertTrue(site.validate("page", ok)["ok"], site.validate("page", ok)["errors"])
        bad = site.store().create("p_bad", {"_kind": "page", "title": "", "visibility": "unknown"})
        res = site.validate("page", bad)
        self.assertFalse(res["ok"])
        self.assertTrue(any("видимость" in e.lower() for e in res["errors"]))

    def test_page_block_type_enum(self):
        bad = site.store().create("b_bad", {"_kind": "page_block", "title": "Блок", "block_type": "rocket"})
        self.assertFalse(site.validate("page_block", bad)["ok"])
        ok = site.store().create("b_ok", {"_kind": "page_block", "title": "Блок", "block_type": "text", "width": "half", "align": "center"})
        self.assertTrue(site.validate("page_block", ok)["ok"], site.validate("page_block", ok)["errors"])

    def test_menu_item_requires_label(self):
        bad = site.store().create("m_bad", {"_kind": "menu_item", "label": ""})
        self.assertFalse(site.validate("menu_item", bad)["ok"])
        ok = site.store().create("m_ok", {"_kind": "menu_item", "label": "Главная", "link": "/"})
        self.assertTrue(site.validate("menu_item", ok)["ok"], site.validate("menu_item", ok)["errors"])

    def test_rating_enums(self):
        bad = site.store().create("r_bad", {"_kind": "rating", "title": "Топ", "rating_type": "karma", "period": "forever"})
        res = site.validate("rating", bad)
        self.assertFalse(res["ok"])
        joined = " ".join(res["errors"])
        self.assertIn("тип рейтинга", joined)
        self.assertIn("период", joined)
        ok = site.store().create("r_ok", {"_kind": "rating", "title": "Топ по уровню", "rating_type": "level", "period": "weekly"})
        self.assertTrue(site.validate("rating", ok)["ok"], site.validate("rating", ok)["errors"])

    def test_lore_and_where_is(self):
        lore = site.store().create("l1", {"_kind": "lore", "title": "Древние", "text": "История", "lore_type": "history"})
        self.assertTrue(site.validate("lore", lore)["ok"], site.validate("lore", lore)["errors"])
        wi = site.store().create("w1", {"_kind": "where_is", "title": "Где рынок", "place": "Селдар"})
        self.assertTrue(site.validate("where_is", wi)["ok"], site.validate("where_is", wi)["errors"])

    def test_theme_opacity_bounds(self):
        bad = site.store().create("t_bad", {"_kind": "site_theme", "title": "Тёмная", "block_opacity": 250})
        self.assertFalse(site.validate("site_theme", bad)["ok"])
        ok = site.store().create("t_ok", {"_kind": "site_theme", "title": "Тёмная", "block_opacity": 80})
        self.assertTrue(site.validate("site_theme", ok)["ok"], site.validate("site_theme", ok)["errors"])

    def test_where_used(self):
        site.store().create("home", {"_kind": "page", "title": "Главная"})
        site.store().create("hero", {"_kind": "page_block", "title": "Шапка", "block_type": "heading", "page_id": "home"})
        site.store().create("nav_home", {"_kind": "menu_item", "label": "Главная", "page_id": "home"})
        ids = {u["id"] for u in site.where_used("home")}
        self.assertIn("hero", ids)
        self.assertIn("nav_home", ids)
        self.assertEqual(site.where_used("nonexistent"), [])


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

    def test_meta_lists_new_kinds_and_vocab(self):
        token = self._token("999")
        meta = self.client.get("/api/admin/v2/site/meta", headers=self._auth(token)).json()
        for k in ("page", "page_block", "menu_item", "post", "rating", "lore", "where_is", "site_theme"):
            self.assertIn(k, meta["kinds"])
        self.assertIn("text", meta["blockTypes"])
        self.assertIn("level", meta["ratingTypes"])
        self.assertIn("history", meta["loreTypes"])

    def test_page_create_publish_owner(self):
        token = self._token("999")
        create = self.client.post("/api/admin/v2/site/page", headers=self._auth(token), json={"id": "p_home", "data": {"title": "Главная", "slug": "home", "visibility": "public"}})
        self.assertEqual(create.status_code, 200, create.text)
        publish = self.client.post("/api/admin/v2/site/page/p_home/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")
        # Фильтр по типу: страница в /page, не в /news.
        pages = self.client.get("/api/admin/v2/site/page", headers=self._auth(token)).json()["items"]
        self.assertEqual([i["id"] for i in pages], ["p_home"])

    def test_menu_item_gated_by_menu_edit(self):
        # content не имеет site.menu_edit -> не создаёт пункты меню, но видит их.
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        self.assertEqual(self.client.get("/api/admin/v2/site/menu_item", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/site/menu_item", headers=self._auth(token), json={"id": "m1", "data": {"label": "Главная"}}).status_code, 403)

    def test_cross_kind_update_rejected(self):
        # Codex P1: правка материала под чужим kind должна давать 404, а не
        # конвертировать/затирать его и обходить per-kind RBAC.
        token = self._token()
        self.client.post("/api/admin/v2/site/page", headers=self._auth(token), json={"id": "p_secret", "data": {"title": "Стр", "slug": "s"}})
        bad = self.client.put("/api/admin/v2/site/news/p_secret", headers=self._auth(token), json={"data": {"title": "Взлом"}})
        self.assertEqual(bad.status_code, 404, bad.text)
        # Тип записи не изменился.
        self.assertEqual(self.client.get("/api/admin/v2/site/page/p_secret", headers=self._auth(token)).json()["item"]["data"]["_kind"], "page")

    def test_content_can_draft_lore_and_rating(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        self.assertEqual(self.client.post("/api/admin/v2/site/lore", headers=self._auth(token), json={"id": "l1", "data": {"title": "Лор", "text": "История", "lore_type": "history"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/site/rating", headers=self._auth(token), json={"id": "r1", "data": {"title": "Топ", "rating_type": "level", "period": "weekly"}}).status_code, 200)

    def test_history_rollback_kinded(self):
        # Этап 1: история/откат для multi-kind сайта + кросс-kind защита.
        token = self._token()
        self.client.post("/api/admin/v2/site/news", headers=self._auth(token), json={"id": "n_h", "data": {"title": "Заголовок 1", "body": "B"}})
        self.client.put("/api/admin/v2/site/news/n_h", headers=self._auth(token), json={"data": {"title": "Заголовок 2"}})
        hist = self.client.get("/api/admin/v2/site/news/n_h/history", headers=self._auth(token))
        self.assertEqual(hist.status_code, 200, hist.text)
        self.assertIn(1, [h["version"] for h in hist.json()["history"]])
        rb = self.client.post("/api/admin/v2/site/news/n_h/rollback", headers=self._auth(token), json={"version": 1})
        self.assertEqual(rb.status_code, 200, rb.text)
        got = self.client.get("/api/admin/v2/site/news/n_h", headers=self._auth(token)).json()["item"]
        self.assertEqual(got["data"]["title"], "Заголовок 1")
        # Кросс-kind: история по чужому kind → 404.
        self.assertEqual(self.client.get("/api/admin/v2/site/page/n_h/history", headers=self._auth(token)).status_code, 404)


if __name__ == "__main__":
    unittest.main()
