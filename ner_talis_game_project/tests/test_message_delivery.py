import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import bot_message_queue as mq
from services import message_delivery as md
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class MessageDeliveryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in ("MESSAGE_QUEUE_PATH", "BOT_MESSAGE_DISPATCHER_ENABLED")}
        os.environ["MESSAGE_QUEUE_PATH"] = str(base / "queue.json")
        os.environ.pop("BOT_MESSAGE_DISPATCHER_ENABLED", None)
        self.addCleanup(self._restore)
        # Reset module + queue sender state between tests.
        mq.set_sender(None)
        md._platform_senders.clear()
        md._dispatcher_started = False
        self.addCleanup(lambda: (mq.set_sender(None), md._platform_senders.clear()))
        self.storage = JsonStorage(str(base / "players.json"))

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _player(self):
        races = load_races("data/races.json")
        gid = self.storage.generate_game_id()
        player = create_player(game_id=gid, platform="telegram", external_user_id="9001", name="Дел", race_id="human", races=races)
        self.storage.save_new_player(player, "telegram", "9001")
        return gid

    def test_flag_off_uses_pending_outbox(self):
        gid = self._player()
        status = md.notify_player(self.storage, gid, "привет", type="admin_message")
        self.assertEqual(status, "pending")
        # Nothing in the instant queue.
        self.assertEqual(mq.stats()["total"], 0)
        # It's in the per-player outbox.
        self.assertTrue(self.storage.dequeue_bot_messages(gid))

    def test_flag_on_uses_instant_queue(self):
        os.environ["BOT_MESSAGE_DISPATCHER_ENABLED"] = "1"
        gid = self._player()
        status = md.notify_player(self.storage, gid, "мгновенно", type="admin_message")
        self.assertEqual(status, "queued")
        msgs = mq.list_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["platform"], "telegram")
        self.assertEqual(msgs[0]["recipient"], "9001")

    def test_resolve_recipient(self):
        player = {"main_platform": "vk", "linked_accounts": {"vk": "555", "telegram": "111"}}
        self.assertEqual(md.resolve_recipient(player), ("vk", "555"))
        self.assertEqual(md.resolve_recipient({"linked_accounts": {"telegram": "111"}}), ("telegram", "111"))
        self.assertEqual(md.resolve_recipient({}), ("", ""))

    def test_combined_sender_delivers_registered_platform(self):
        os.environ["BOT_MESSAGE_DISPATCHER_ENABLED"] = "1"
        gid = self._player()
        md.notify_player(self.storage, gid, "тест", type="admin_message")
        seen = []
        md.register_platform_sender("telegram", lambda recipient, text: seen.append((recipient, text)))
        counts = mq.dispatch_once()  # uses the registered combined sender
        self.assertEqual(counts["sent"], 1)
        self.assertEqual(seen, [("9001", "тест")])

    def test_combined_sender_classifies_blocked(self):
        def boom(_r, _t):
            raise RuntimeError("Bot was blocked by the user")
        md.register_platform_sender("telegram", boom)
        result, _err = md._combined_sender({"platform": "telegram", "recipient": "1", "text": "x"})
        self.assertEqual(result, mq.RESULT_BLOCKED)

    def test_combined_sender_unknown_platform_and_no_recipient(self):
        self.assertEqual(md._combined_sender({"platform": "telegram", "recipient": "", "text": "x"})[0], mq.RESULT_FAILED_PERMANENT)
        self.assertEqual(md._combined_sender({"platform": "discord", "recipient": "1", "text": "x"})[0], mq.RESULT_FAILED_TEMPORARY)


if __name__ == "__main__":
    unittest.main()
