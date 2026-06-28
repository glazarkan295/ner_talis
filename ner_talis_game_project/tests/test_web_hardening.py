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

    def test_force_https_ignores_spoofed_forwarded_proto(self):
        # Codex P2: прямой HTTP-клиент не должен обходить FORCE_HTTPS подделкой
        # X-Forwarded-Proto: https — заголовок не доверенный без TRUST_PROXY_HEADERS.
        os.environ["FORCE_HTTPS"] = "true"
        os.environ.pop("TRUST_PROXY_HEADERS", None)
        try:
            client = self._client()
            resp = client.get("/", headers={"X-Forwarded-Proto": "https"})
            self.assertEqual(resp.status_code, 426, resp.text)
        finally:
            os.environ.pop("FORCE_HTTPS", None)

    def test_force_https_allows_real_https(self):
        os.environ["FORCE_HTTPS"] = "true"
        try:
            client = TestClient(web_app.create_app(), base_url="https://testserver")
            resp = client.get("/")
            self.assertNotEqual(resp.status_code, 426)
        finally:
            os.environ.pop("FORCE_HTTPS", None)

    # --- ТЗ 23: HTTPS за reverse proxy ------------------------------------
    def test_http_without_proxy_is_blocked(self):
        # §7.1: FORCE_HTTPS=true, TRUST_PROXY_HEADERS=false → /profile блокируется.
        os.environ["FORCE_HTTPS"] = "true"
        os.environ.pop("TRUST_PROXY_HEADERS", None)
        try:
            client = self._client()
            resp = client.get("/profile?token=TEST_TOKEN")
            self.assertEqual(resp.status_code, 426, resp.text)
            self.assertEqual(resp.json().get("detail"), "HTTPS required")
        finally:
            os.environ.pop("FORCE_HTTPS", None)

    def test_https_via_trusted_proxy_header(self):
        # §7.2: доверенный proxy + X-Forwarded-Proto: https → не блокируется.
        os.environ.update({"FORCE_HTTPS": "true", "TRUST_PROXY_HEADERS": "true", "TRUSTED_PROXY_IPS": "*"})
        try:
            client = self._client()
            for headers in ({"X-Forwarded-Proto": "https"}, {"X-Forwarded-Ssl": "on"}, {"Forwarded": "proto=https"}):
                resp = client.get("/profile?token=TEST_TOKEN", headers=headers)
                self.assertNotEqual(resp.status_code, 426, f"{headers} → {resp.status_code}")
        finally:
            for k in ("FORCE_HTTPS", "TRUST_PROXY_HEADERS", "TRUSTED_PROXY_IPS"):
                os.environ.pop(k, None)

    def test_https_header_from_untrusted_proxy_ignored(self):
        # §7.3: TRUST включён, но IP клиента (testclient) не в TRUSTED_PROXY_IPS →
        # X-Forwarded-Proto игнорируется, запрос блокируется.
        os.environ.update({"FORCE_HTTPS": "true", "TRUST_PROXY_HEADERS": "true", "TRUSTED_PROXY_IPS": "127.0.0.1"})
        try:
            client = self._client()
            resp = client.get("/profile?token=TEST_TOKEN", headers={"X-Forwarded-Proto": "https"})
            self.assertEqual(resp.status_code, 426, resp.text)
        finally:
            for k in ("FORCE_HTTPS", "TRUST_PROXY_HEADERS", "TRUSTED_PROXY_IPS"):
                os.environ.pop(k, None)

    def test_trusted_proxy_ip_helper_cidr(self):
        # §7.4: helper поддерживает *, точные IP и CIDR-сети.
        self.assertTrue(web_app._proxy_ip_trusted("8.8.8.8", ["*"]))
        self.assertTrue(web_app._proxy_ip_trusted("10.1.2.3", ["10.0.0.0/8"]))
        self.assertTrue(web_app._proxy_ip_trusted("172.16.5.5", ["172.16.0.0/12"]))
        self.assertTrue(web_app._proxy_ip_trusted("192.168.0.7", ["192.168.0.0/16"]))
        self.assertTrue(web_app._proxy_ip_trusted("127.0.0.1", ["127.0.0.1", "::1"]))
        self.assertFalse(web_app._proxy_ip_trusted("8.8.8.8", ["10.0.0.0/8"]))
        self.assertFalse(web_app._proxy_ip_trusted("8.8.8.8", []))
        self.assertFalse(web_app._proxy_ip_trusted("not-an-ip", ["10.0.0.0/8"]))


if __name__ == "__main__":
    unittest.main()
