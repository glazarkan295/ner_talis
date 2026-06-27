"""Конструктор текстов бота (full-import ТЗ §5.18): сервис, API, рантайм."""

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

from admin_text_api import create_admin_text_router
from services import admin_rbac as rbac
from services import text_constructor_service as tcs
from services import text_runtime
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class TextServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("TEXT_CONSTRUCTOR_PATH")
        os.environ["TEXT_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "texts.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("TEXT_CONSTRUCTOR_PATH", None)
        else:
            os.environ["TEXT_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_text(self):
        env = tcs.store().create("greet", {
            "text_key": "system.welcome", "text_value": "Привет, {name}!",
            "platform": "both", "parse_mode": "none", "variables": ["name"],
        })
        result = tcs.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = tcs.store().create("bad", {
            "text_key": "", "text_value": "", "platform": "signal",
            "parse_mode": "weird",
        })
        result = tcs.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("ключ", joined)
        self.assertIn("платформа", joined)
        self.assertIn("разметк", joined)

    def test_undeclared_placeholder_warns(self):
        env = tcs.store().create("ww", {
            "text_key": "x.y", "text_value": "Привет, {name}!",
            "platform": "both", "variables": [],
        })
        result = tcs.validate(env)
        self.assertTrue(result["ok"])  # это предупреждение, не ошибка
        self.assertTrue(any("name" in w for w in result["warnings"]))

    def test_render_substitutes(self):
        data = {"text_value": "Дар: {items}", "fallback_text": "Дар."}
        self.assertEqual(tcs.render(data, {"items": "меч"}), "Дар: меч")
        # Неизвестный плейсхолдер остаётся как есть.
        self.assertEqual(tcs.render(data, {}), "Дар: {items}")
        # Пустой text_value → fallback.
        self.assertEqual(tcs.render({"text_value": "", "fallback_text": "Запас"}, None), "Запас")


class TextRuntimeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in ("TEXT_CONSTRUCTOR_PATH", "FEATURE_FLAGS_PATH")}
        os.environ["TEXT_CONSTRUCTOR_PATH"] = str(base / "texts.json")
        os.environ["FEATURE_FLAGS_PATH"] = str(base / "flags.json")
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _publish(self, sid, data):
        tcs.store().create(sid, data)
        tcs.store().set_status(sid, tcs.STATUS_PUBLISHED, actor="t", force=True)

    def test_flag_off_returns_default(self):
        from services import feature_flags_service as ff

        self._publish("gg", {"text_key": "hello", "text_value": "Из V2", "platform": "both"})
        self.assertFalse(ff.is_enabled("use_v2_texts"))
        self.assertEqual(text_runtime.get_text("hello", default="старый"), "старый")

    def test_flag_on_reads_published(self):
        from services import feature_flags_service as ff

        self._publish("gg", {"text_key": "hello", "text_value": "Привет, {name}", "platform": "both"})
        ff.set_flag("use_v2_texts", True)
        self.assertEqual(text_runtime.get_text("hello", variables={"name": "Ал"}, default="d"), "Привет, Ал")
        # Несуществующий ключ → default.
        self.assertEqual(text_runtime.get_text("missing", default="d"), "d")

    def test_unpublished_not_used(self):
        from services import feature_flags_service as ff

        tcs.store().create("draft", {"text_key": "k", "text_value": "черновик", "platform": "both"})
        ff.set_flag("use_v2_texts", True)
        self.assertEqual(text_runtime.get_text("k", default="d"), "d")


class TextApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("TEXT_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["TEXT_CONSTRUCTOR_PATH"] = str(base / "texts.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_text_router(lambda: self.storage))
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

    def _create(self, token, tid="t1", data=None):
        body = {"id": tid, "data": data or {"text_key": "system.welcome", "text_value": "Привет!", "platform": "both"}}
        return self.client.post("/api/admin/v2/texts", headers=self._auth(token), json=body)

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/texts/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        body = meta.json()
        self.assertTrue(body["platforms"])
        self.assertIn("none", body["parseModes"])
        self.assertTrue(body["contexts"])

    def test_create_validate_publish(self):
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        pub = self.client.post("/api/admin/v2/texts/t1/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_publish_blocked_when_invalid(self):
        token = self._token()
        self._create(token, tid="bad", data={"text_key": "", "text_value": "", "platform": "both"})
        pub = self.client.post("/api/admin/v2/texts/bad/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 400, pub.text)

    def test_preview_endpoint(self):
        token = self._token()
        self._create(token, tid="gg", data={"text_key": "k", "text_value": "Дар: {items}", "platform": "both", "variables": ["items"]})
        pv = self.client.post("/api/admin/v2/texts/gg/preview", headers=self._auth(token), json={"variables": {"items": "щит"}})
        self.assertEqual(pv.status_code, 200, pv.text)
        self.assertEqual(pv.json()["preview"], "Дар: щит")

    def test_import_endpoint(self):
        token = self._token()
        r = self.client.post("/api/admin/v2/texts/import", headers=self._auth(token), json={"mode": "new"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreater(r.json()["report"]["created"], 0)
        # Якорный текст §5.10 импортирован.
        keys = {(i.get("data") or {}).get("text_key") for i in tcs.store().list()}
        self.assertIn("search.nothing_found", keys)

    def test_read_only_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/texts", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self._create(token).status_code, 403)

    def test_content_cannot_edit_published(self):
        # 15-CODEX §3: content (edit, без publish) не может править live-объект.
        token = self._token()  # owner
        self._create(token, tid="pub")
        self.assertEqual(self.client.post("/api/admin/v2/texts/pub/publish", headers=self._auth(token), json={}).status_code, 200)
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        upd = self.client.put("/api/admin/v2/texts/pub", headers=self._auth(token), json={"data": {"text_value": "правка"}})
        self.assertEqual(upd.status_code, 403, upd.text)
        # Черновик content править может.
        self.assertEqual(self._create(token, tid="drf").status_code, 200)
        ok = self.client.put("/api/admin/v2/texts/drf", headers=self._auth(token), json={"data": {"text_value": "ок"}})
        self.assertEqual(ok.status_code, 200, ok.text)


if __name__ == "__main__":
    unittest.main()
