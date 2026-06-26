"""Конструктор раскладки профиля (ТЗ §3): валидация + API + RBAC."""

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

from admin_profile_layout_api import create_admin_profile_layout_router
from services import admin_rbac as rbac
from services import profile_layout_service as layout
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class ProfileLayoutServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("PROFILE_LAYOUT_PATH")
        os.environ["PROFILE_LAYOUT_PATH"] = str(Path(self._tmp.name) / "layout.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("PROFILE_LAYOUT_PATH", None)
        else:
            os.environ["PROFILE_LAYOUT_PATH"] = self._saved

    def test_tab_requires_label(self):
        ok = layout.store().create("t_char", {"_kind": "profile_tab", "label": "Персонаж", "tab_key": "character", "visibility": "always"})
        self.assertTrue(layout.validate("profile_tab", ok)["ok"], layout.validate("profile_tab", ok)["errors"])
        bad = layout.store().create("t_bad", {"_kind": "profile_tab", "label": "", "visibility": "unknown"})
        res = layout.validate("profile_tab", bad)
        self.assertFalse(res["ok"])
        self.assertTrue(any("название" in e.lower() for e in res["errors"]))
        self.assertTrue(any("видимость" in e.lower() for e in res["errors"]))

    def test_overview_tab_warns(self):
        env = layout.store().create("t_ov", {"_kind": "profile_tab", "label": "Обзор"})
        res = layout.validate("profile_tab", env)
        self.assertTrue(res["ok"], res["errors"])  # предупреждение, не ошибка
        self.assertTrue(any("Обзор" in w for w in res["warnings"]))

    def test_block_type_enum(self):
        bad = layout.store().create("b_bad", {"_kind": "profile_block", "name": "Блок", "block_type": "teleporter"})
        self.assertFalse(layout.validate("profile_block", bad)["ok"])
        ok = layout.store().create("b_ok", {"_kind": "profile_block", "name": "Инвентарь", "block_type": "inventory", "tab": "inventory", "width": "full"})
        self.assertTrue(layout.validate("profile_block", ok)["ok"], layout.validate("profile_block", ok)["errors"])

    def test_theme_requires_title(self):
        self.assertFalse(layout.validate("profile_theme", layout.store().create("th_bad", {"_kind": "profile_theme", "title": ""}))["ok"])
        self.assertTrue(layout.validate("profile_theme", layout.store().create("th_ok", {"_kind": "profile_theme", "title": "Тёмная"}))["ok"])

    def test_published_layout_runtime(self):
        # Опубликованная раскладка: вкладки по порядку + их блоки + оформление.
        layout.store().create("t_inv", {"_kind": "profile_tab", "label": "Инвентарь", "tab_key": "inventory", "order": 2, "icon": "🎒"})
        layout.store().set_status("t_inv", layout.STATUS_PUBLISHED, force=True)
        layout.store().create("t_char", {"_kind": "profile_tab", "label": "Герой", "tab_key": "character", "order": 1})
        layout.store().set_status("t_char", layout.STATUS_PUBLISHED, force=True)
        layout.store().create("t_draft", {"_kind": "profile_tab", "label": "Черновик", "tab_key": "secret"})  # не опубликован
        layout.store().create("b_stats", {"_kind": "profile_block", "name": "Стат", "block_type": "stats", "tab": "character", "order": 1})
        layout.store().set_status("b_stats", layout.STATUS_PUBLISHED, force=True)
        layout.store().create("th", {"_kind": "profile_theme", "title": "Тёмная", "button_color": "#b58a4b"})
        layout.store().set_status("th", layout.STATUS_PUBLISHED, force=True)

        result = layout.published_layout()
        keys = [t["key"] for t in result["tabs"]]
        self.assertEqual(keys, ["character", "inventory"])  # по order, без черновика
        char_tab = result["tabs"][0]
        self.assertEqual([b["type"] for b in char_tab["blocks"]], ["stats"])
        self.assertEqual(result["theme"]["button_color"], "#b58a4b")

    def test_where_used_matches_tab_key(self):
        layout.store().create("tab_char", {"_kind": "profile_tab", "label": "Персонаж", "tab_key": "character"})
        layout.store().create("blk_stats", {"_kind": "profile_block", "name": "Характеристики", "block_type": "stats", "tab": "character"})
        layout.store().create("blk_inv", {"_kind": "profile_block", "name": "Инвентарь", "block_type": "inventory", "tab": "other"})
        ids = {u["id"] for u in layout.where_used("tab_char")}
        self.assertIn("blk_stats", ids)
        self.assertNotIn("blk_inv", ids)
        self.assertEqual(layout.where_used("nope"), [])


class ProfileLayoutApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("PROFILE_LAYOUT_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["PROFILE_LAYOUT_PATH"] = str(base / "layout.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_profile_layout_router(lambda: self.storage))
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

    def test_meta_and_tab_publish(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/profile-layout/meta", headers=self._auth(token)).json()
        self.assertIn("profile_tab", meta["kinds"])
        self.assertIn("inventory", meta["blockTypes"])
        create = self.client.post("/api/admin/v2/profile-layout/profile_tab", headers=self._auth(token), json={"id": "t_char", "data": {"label": "Персонаж", "tab_key": "character"}})
        self.assertEqual(create.status_code, 200, create.text)
        publish = self.client.post("/api/admin/v2/profile-layout/profile_tab/t_char/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertIn("profile_layout.publish", dangerous)

    def test_kind_filter_and_delete_confirm(self):
        token = self._token()
        self.client.post("/api/admin/v2/profile-layout/profile_tab", headers=self._auth(token), json={"id": "t1", "data": {"label": "Вкладка"}})
        self.client.post("/api/admin/v2/profile-layout/profile_block", headers=self._auth(token), json={"id": "b1", "data": {"name": "Блок", "block_type": "stats"}})
        tabs = self.client.get("/api/admin/v2/profile-layout/profile_tab", headers=self._auth(token)).json()["items"]
        self.assertEqual([i["id"] for i in tabs], ["t1"])
        self.assertEqual(self.client.request("DELETE", "/api/admin/v2/profile-layout/profile_block/b1", headers=self._auth(token), json={"confirm": "wrong"}).status_code, 400)
        ok = self.client.request("DELETE", "/api/admin/v2/profile-layout/profile_block/b1", headers=self._auth(token), json={"confirm": "b1", "reason": "уборка"})
        self.assertEqual(ok.status_code, 200, ok.text)

    def test_content_can_edit_but_not_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self.client.post("/api/admin/v2/profile-layout/profile_tab", headers=self._auth(token), json={"id": "t2", "data": {"label": "T"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/profile-layout/profile_tab/t2/publish", headers=self._auth(token), json={}).status_code, 403)

    def test_read_only_view_only(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/profile-layout/profile_tab", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/profile-layout/profile_tab", headers=self._auth(token), json={"id": "tx", "data": {"label": "T"}}).status_code, 403)

    def test_history_rollback_kinded(self):
        # Этап 1: история/откат для multi-kind конструктора (пути /{kind}/{id}/…).
        token = self._token()
        self.client.post("/api/admin/v2/profile-layout/profile_tab", headers=self._auth(token), json={"id": "t_h", "data": {"label": "Версия 1"}})
        self.client.put("/api/admin/v2/profile-layout/profile_tab/t_h", headers=self._auth(token), json={"data": {"label": "Версия 2"}})
        hist = self.client.get("/api/admin/v2/profile-layout/profile_tab/t_h/history", headers=self._auth(token))
        self.assertEqual(hist.status_code, 200, hist.text)
        self.assertIn(1, [h["version"] for h in hist.json()["history"]])
        rb = self.client.post("/api/admin/v2/profile-layout/profile_tab/t_h/rollback", headers=self._auth(token), json={"version": 1})
        self.assertEqual(rb.status_code, 200, rb.text)
        got = self.client.get("/api/admin/v2/profile-layout/profile_tab/t_h", headers=self._auth(token)).json()["item"]
        self.assertEqual(got["data"]["label"], "Версия 1")
        # Кросс-kind защита: история по чужому kind → 404.
        self.assertEqual(self.client.get("/api/admin/v2/profile-layout/profile_block/t_h/history", headers=self._auth(token)).status_code, 404)


if __name__ == "__main__":
    unittest.main()
