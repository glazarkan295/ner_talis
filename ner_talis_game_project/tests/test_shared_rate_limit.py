"""Общий rate-limit (16-TZ §3/§6): in-memory всегда; Redis — если доступен."""

import os
import sys
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import shared_rate_limit as srl


def _redis_available() -> bool:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return False
    try:
        import redis

        c = redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)
        return bool(c.ping())
    except Exception:
        return False


class InMemoryLimiterTest(unittest.TestCase):
    def test_sliding_window_allow_then_deny(self):
        lim = srl.InMemoryRateLimiter()
        now = 100.0
        self.assertTrue(lim.allow("k", 3, 10, now=now))
        self.assertTrue(lim.allow("k", 3, 10, now=now))
        self.assertTrue(lim.allow("k", 3, 10, now=now))
        self.assertFalse(lim.allow("k", 3, 10, now=now))  # 4-й сверх лимита
        # После окна — снова можно.
        self.assertTrue(lim.allow("k", 3, 10, now=now + 11))

    def test_keys_isolated(self):
        lim = srl.InMemoryRateLimiter()
        now = 0.0
        self.assertTrue(lim.allow("a", 1, 10, now=now))
        self.assertFalse(lim.allow("a", 1, 10, now=now))
        self.assertTrue(lim.allow("b", 1, 10, now=now))  # другой ключ независим

    def test_zero_limit_always_allows(self):
        lim = srl.InMemoryRateLimiter()
        self.assertTrue(lim.allow("k", 0, 10))


class BuildLimiterTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("RATE_LIMIT_BACKEND",)}
        self.addCleanup(self._restore)
        srl.reset()
        self.addCleanup(srl.reset)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_memory_backend_forced(self):
        os.environ["RATE_LIMIT_BACKEND"] = "memory"
        srl.reset()
        self.assertEqual(srl.backend_name(), "memory")
        self.assertFalse(srl.shared_active())


@unittest.skipUnless(_redis_available(), "REDIS_URL не задан или Redis недоступен")
class RedisLimiterTest(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("RATE_LIMIT_BACKEND")
        os.environ["RATE_LIMIT_BACKEND"] = "redis"
        srl.reset()
        self.addCleanup(self._restore)
        self.addCleanup(srl.reset)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("RATE_LIMIT_BACKEND", None)
        else:
            os.environ["RATE_LIMIT_BACKEND"] = self._saved

    def test_redis_backend_selected_and_limits(self):
        self.assertEqual(srl.backend_name(), "redis")
        self.assertTrue(srl.shared_active())
        key = f"test:{os.getpid()}:{time.time()}"
        self.assertTrue(srl.allow(key, 3, 30))
        self.assertTrue(srl.allow(key, 3, 30))
        self.assertTrue(srl.allow(key, 3, 30))
        self.assertFalse(srl.allow(key, 3, 30))  # 4-й сверх лимита (общий счётчик)


if __name__ == "__main__":
    unittest.main()
