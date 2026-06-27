"""Защита входящих ботов (ТЗ 08 §7): антифлуд, дедуп, лимит длины."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import bot_flood_guard as guard


class BotFloodGuardTest(unittest.TestCase):
    def setUp(self):
        guard.reset()
        self.addCleanup(guard.reset)

    def test_clamp_incoming_text(self):
        self.assertEqual(guard.clamp_incoming_text("привет"), "привет")
        long = "x" * 5000
        self.assertEqual(len(guard.clamp_incoming_text(long)), guard.MAX_INCOMING_TEXT)
        self.assertEqual(guard.clamp_incoming_text(None), "")

    def test_duplicate_event_detected_in_window(self):
        self.assertFalse(guard.is_duplicate_event("telegram", 555, now=0.0))
        self.assertTrue(guard.is_duplicate_event("telegram", 555, now=1.0))
        # Пустой id никогда не дубликат.
        self.assertFalse(guard.is_duplicate_event("telegram", "", now=2.0))
        # После окна — снова не дубликат.
        self.assertFalse(guard.is_duplicate_event("telegram", 555, now=guard.DEDUP_TTL + 5))

    def test_per_user_rate_limit(self):
        now = 100.0
        allowed = sum(1 for _ in range(20) if guard.allow_message("telegram", "u1", now=now))
        self.assertEqual(allowed, guard.PER_USER_LIMIT)  # сверх лимита — отказ
        # Другой пользователь не затронут.
        self.assertTrue(guard.allow_message("telegram", "u2", now=now))
        # После окна лимит сбрасывается.
        self.assertTrue(guard.allow_message("telegram", "u1", now=now + guard.PER_USER_WINDOW + 1))

    def test_guard_incoming_reasons(self):
        now = 0.0
        self.assertEqual(guard.guard_incoming("vk", "a", 1, now=now)["reason"], None)
        # Повтор того же события → duplicate.
        self.assertEqual(guard.guard_incoming("vk", "a", 1, now=now + 0.1)["reason"], "duplicate")
        # Новые события подряд → в итоге flood.
        reasons = [guard.guard_incoming("vk", "a", 100 + i, now=now)["reason"] for i in range(20)]
        self.assertIn("flood", reasons)

    def test_dedup_scoped_by_peer(self):
        # 15-CODEX §2: разные VK-пользователи с одинаковым conversation_message_id
        # не должны конфликтовать.
        guard.reset()
        now = 0.0
        self.assertFalse(guard.is_duplicate_event("vk", 5, scope="peerA", now=now))
        # Тот же id события, но другой peer — НЕ дубль.
        self.assertFalse(guard.is_duplicate_event("vk", 5, scope="peerB", now=now))
        # Повтор у того же peer — дубль.
        self.assertTrue(guard.is_duplicate_event("vk", 5, scope="peerA", now=now + 0.1))
        # guard_incoming скоупит по user_id: одинаковый event_id у разных пользователей — оба проходят.
        guard.reset()
        self.assertEqual(guard.guard_incoming("vk", "userA", 7, now=now)["reason"], None)
        self.assertEqual(guard.guard_incoming("vk", "userB", 7, now=now)["reason"], None)


if __name__ == "__main__":
    unittest.main()
