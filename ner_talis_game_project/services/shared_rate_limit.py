"""Общий rate-limit с переключаемым backend'ом (16-TZ §3/§6).

Зачем: процесс-локальные лимитеры не синхронизируются между несколькими
процессами/контейнерами — пользователь может обойти лимит через разные воркеры.
Этот слой даёт единый лимитер, который МОЖЕТ работать через Redis (общий для всех
процессов), а в dev/без Redis откатывается на in-memory.

Выбор backend'а (по окружению):
* RATE_LIMIT_BACKEND=memory  → всегда in-memory;
* RATE_LIMIT_BACKEND=redis   → Redis (REDIS_URL), при недоступности — in-memory;
* RATE_LIMIT_BACKEND=auto|"" → Redis, если задан REDIS_URL и он отвечает, иначе in-memory.

Секреты (REDIS_URL/пароль) читаются ТОЛЬКО из окружения и нигде не логируются и
не коммитятся.

API: ``allow(key, limit, window_seconds) -> bool`` (True — запрос разрешён).
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any

# Короткие таймауты: лимитер не должен подвешивать запрос, если Redis тормозит.
_REDIS_TIMEOUT = float(os.getenv("RATE_LIMIT_REDIS_TIMEOUT", "0.5") or "0.5")


class InMemoryRateLimiter:
    """Скользящее окно в памяти процесса (dev / fallback)."""

    backend = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int, window_seconds: float, *, now: float | None = None) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic() if now is None else now
        cutoff = now - window_seconds
        with self._lock:
            q = self._hits.setdefault(str(key), deque())
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 8192:  # не даём словарю расти бесконечно
                for k in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
                    self._hits.pop(k, None)
            return True


class RedisRateLimiter:
    """Фиксированное окно через INCR+EXPIRE — общий лимит для всех процессов.

    При любой ошибке Redis молча откатывается на внутренний in-memory лимитер,
    чтобы сбой Redis не ронял обработку запросов."""

    backend = "redis"

    def __init__(self, client: Any) -> None:
        self._client = client
        self._fallback = InMemoryRateLimiter()

    def allow(self, key: str, limit: int, window_seconds: float, *, now: float | None = None) -> bool:
        if limit <= 0:
            return True
        rk = f"rl:{key}"
        try:
            count = self._client.incr(rk)
            if int(count) == 1:
                self._client.expire(rk, max(1, int(window_seconds)))
            return int(count) <= int(limit)
        except Exception:
            # Redis недоступен на этом запросе → деградируем на in-memory.
            return self._fallback.allow(key, limit, window_seconds, now=now)


def _build_redis_client(url: str) -> Any | None:
    if not url:
        return None
    try:
        import redis  # опциональная зависимость

        client = redis.Redis.from_url(
            url, socket_timeout=_REDIS_TIMEOUT, socket_connect_timeout=_REDIS_TIMEOUT
        )
        client.ping()
        return client
    except Exception:
        return None


def build_limiter() -> Any:
    """Собрать лимитер по текущему окружению (без кэша)."""
    backend = str(os.getenv("RATE_LIMIT_BACKEND", "auto") or "auto").strip().lower()
    url = str(os.getenv("REDIS_URL", "") or "").strip()
    if backend in ("memory", "inmemory", "local"):
        return InMemoryRateLimiter()
    if backend == "redis" or (backend in ("auto", "") and url):
        client = _build_redis_client(url)
        if client is not None:
            return RedisRateLimiter(client)
    return InMemoryRateLimiter()


_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()


def get_limiter() -> Any:
    """Кэшированный лимитер процесса (переиспользует Redis-подключение)."""
    limiter = _CACHE.get("limiter")
    if limiter is None:
        with _CACHE_LOCK:
            limiter = _CACHE.get("limiter") or build_limiter()
            _CACHE["limiter"] = limiter
    return limiter


def reset() -> None:
    """Сбросить кэш (для тестов/смены окружения)."""
    _CACHE.pop("limiter", None)


def backend_name() -> str:
    return getattr(get_limiter(), "backend", "memory")


def shared_active() -> bool:
    """True, если активен общий (не процесс-локальный) backend — например Redis."""
    return backend_name() != "memory"


def allow(key: str, limit: int, window_seconds: float, *, now: float | None = None) -> bool:
    return get_limiter().allow(key, limit, window_seconds, now=now)
