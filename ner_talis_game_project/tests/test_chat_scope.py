"""Поведение бота в личных vs общих чатах (ТЗ): классификация сообщений."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import chat_scope_service as cs


class NormalizeCommandTest(unittest.TestCase):
    def test_plain_text_is_not_command(self):
        self.assertEqual(cs.normalize_command("привет всем"), "")
        self.assertEqual(cs.normalize_command(""), "")
        self.assertEqual(cs.normalize_command(None), "")

    def test_strips_bot_mention_and_args(self):
        self.assertEqual(cs.normalize_command("/profile@NerTalisBot"), "profile")
        self.assertEqual(cs.normalize_command("/PROMO start100"), "promo")
        self.assertEqual(cs.normalize_command("/admin_add_money 5 1000"), "admin_add_money")


class ClassifyGroupMessageTest(unittest.TestCase):
    def test_plain_text_ignored(self):
        self.assertEqual(cs.classify_group_message("всем привет"), cs.ACTION_IGNORE)

    def test_game_command_flagged(self):
        for cmd in ("/profile", "/city", "/promo CODE", "/start", "/inventory"):
            self.assertEqual(cs.classify_group_message(cmd), cs.ACTION_GAME, cmd)

    def test_admin_and_help_allowed(self):
        for cmd in ("/admin_help", "/admin_add_money 1 1", "/help", "/rules", "/admin_id"):
            self.assertEqual(cs.classify_group_message(cmd), cs.ACTION_ALLOWED, cmd)

    def test_unknown_command_ignored(self):
        self.assertEqual(cs.classify_group_message("/weather"), cs.ACTION_IGNORE)


class ChatTypeHelpersTest(unittest.TestCase):
    def test_telegram_types(self):
        self.assertTrue(cs.telegram_chat_is_private("private"))
        self.assertFalse(cs.telegram_chat_is_group("private"))
        self.assertTrue(cs.telegram_chat_is_group("group"))
        self.assertTrue(cs.telegram_chat_is_group("supergroup"))
        self.assertFalse(cs.telegram_chat_is_private("supergroup"))

    def test_vk_peer(self):
        self.assertTrue(cs.vk_peer_is_private(12345))
        self.assertFalse(cs.vk_peer_is_group(12345))
        self.assertTrue(cs.vk_peer_is_group(2_000_000_001))
        self.assertFalse(cs.vk_peer_is_private(2_000_000_001))
        self.assertFalse(cs.vk_peer_is_group("not-a-number"))

    def test_notices_have_no_buttons_text(self):
        self.assertIn("личном чате", cs.GROUP_GAME_NOTICE)
        self.assertIn("прав", cs.NO_PERMISSION_NOTICE)


if __name__ == "__main__":
    unittest.main()
