"""Публичный сайт (рантайм конструктора сайта, ТЗ §2): только опубликованное."""

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

from public_site_api import create_public_site_router
from services import site_content_registry as site


class PublicSiteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("SITE_CONTENT_PATH")
        os.environ["SITE_CONTENT_PATH"] = str(Path(self._tmp.name) / "site.json")
        self.addCleanup(self._restore)
        app = FastAPI()
        app.include_router(create_public_site_router())
        self.client = TestClient(app)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("SITE_CONTENT_PATH", None)
        else:
            os.environ["SITE_CONTENT_PATH"] = self._saved

    def _publish(self, kind, cid, data):
        site.store().create(cid, {**data, "_kind": kind})
        site.store().set_status(cid, site.STATUS_PUBLISHED, force=True)

    def test_only_published_pages_served(self):
        self._publish("page", "home", {"title": "Главная", "slug": "home", "menu_order": 1})
        site.store().create("draft_page", {"_kind": "page", "title": "Черновик", "slug": "secret"})  # draft, not published
        pages = self.client.get("/api/public/site/pages").json()["pages"]
        slugs = {p["slug"] for p in pages}
        self.assertIn("home", slugs)
        self.assertNotIn("secret", slugs)

    def test_page_with_blocks_by_slug(self):
        self._publish("page", "about", {"title": "О мире", "slug": "about"})
        self._publish("page_block", "b1", {"title": "Заголовок", "block_type": "heading", "page_id": "about", "order": 1})
        self._publish("page_block", "b2", {"title": "Текст", "block_type": "text", "page_id": "about", "order": 2})
        resp = self.client.get("/api/public/site/page/about")
        self.assertEqual(resp.status_code, 200, resp.text)
        page = resp.json()["page"]
        self.assertEqual(page["title"], "О мире")
        self.assertEqual([b["id"] for b in page["blocks"]], ["b1", "b2"])
        # Технического поля _kind в публичной выдаче нет.
        self.assertNotIn("_kind", page)
        self.assertEqual(self.client.get("/api/public/site/page/missing").status_code, 404)

    def test_menu_tree(self):
        self._publish("menu_item", "m_main", {"label": "Главная", "order": 1})
        self._publish("menu_item", "m_lore", {"label": "Лор", "order": 2})
        self._publish("menu_item", "m_lore_ancients", {"label": "Древние", "parent_id": "m_lore", "order": 1})
        menu = self.client.get("/api/public/site/menu").json()["menu"]
        labels = [m["label"] for m in menu]
        self.assertEqual(labels, ["Главная", "Лор"])
        lore = next(m for m in menu if m["id"] == "m_lore")
        self.assertEqual([c["id"] for c in lore["children"]], ["m_lore_ancients"])

    def test_news_guides_faq_lore_ratings(self):
        self._publish("news", "n1", {"title": "Обновление", "body": "Текст"})
        self._publish("guide", "g1", {"title": "Гайд", "body": "Как играть"})
        self._publish("faq", "f1", {"question": "Как?", "answer": "Так."})
        self._publish("lore", "l1", {"title": "Древние", "text": "История", "lore_type": "history"})
        self._publish("rating", "r1", {"title": "Топ уровня", "rating_type": "level", "period": "weekly"})
        self.assertEqual(self.client.get("/api/public/site/news").json()["news"][0]["id"], "n1")
        self.assertEqual(self.client.get("/api/public/site/guides").json()["guides"][0]["id"], "g1")
        self.assertEqual(self.client.get("/api/public/site/faq").json()["faq"][0]["id"], "f1")
        self.assertEqual(self.client.get("/api/public/site/lore").json()["lore"][0]["id"], "l1")
        self.assertEqual(self.client.get("/api/public/site/ratings").json()["ratings"][0]["id"], "r1")


if __name__ == "__main__":
    unittest.main()
