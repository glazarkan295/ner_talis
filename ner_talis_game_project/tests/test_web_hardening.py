"""Защита веб-приложения: OpenAPI закрыт в проде, favicon без 404, заголовки."""

import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Не поднимаем фоновые воркеры в тестах.
os.environ.setdefault("WEB_START_BACKGROUND_WORKERS", "false")

from fastapi.testclient import TestClient
import web_app
from services import bot_message_queue


class WebHardeningTest(unittest.TestCase):
    def tearDown(self):
        # create_app() глобально конфигурирует backend очереди под текущее
        # хранилище — возвращаем дефолтный JSON, чтобы не влиять на другие тесты.
        bot_message_queue.use_json_file_backend()

    def _client(self):
        return TestClient(web_app.create_app())

    def test_openapi_disabled_by_default(self):
        os.environ.pop("ENABLE_API_DOCS", None)
        client = self._client()
        self.assertEqual(client.get("/openapi.json").status_code, 404)
        self.assertEqual(client.get("/docs").status_code, 404)
        self.assertEqual(client.get("/redoc").status_code, 404)

    def test_openapi_enabled_with_flag(self):
        os.environ["ENABLE_API_DOCS"] = "true"
        try:
            client = self._client()
            self.assertEqual(client.get("/openapi.json").status_code, 200)
        finally:
            os.environ.pop("ENABLE_API_DOCS", None)

    def test_favicon_has_no_404(self):
        client = self._client()
        self.assertIn(client.get("/favicon.ico").status_code, (200, 204))
        self.assertIn(client.get("/favicon.svg").status_code, (200, 204))

    def test_security_headers_present(self):
        client = self._client()
        response = client.get("/health")
        self.assertEqual(response.text, "OK")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("Content-Security-Policy", response.headers)


if __name__ == "__main__":
    unittest.main()
