import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage

TELEGRAM = "telegram"


class BotOutboxAtomicityTest(unittest.TestCase):
    """Атомарный outbox pending_bot_messages: enqueue/dequeue + защита от
    lost-update при полном сохранении игрока."""

    def _make(self, StorageCls, path):
        storage = StorageCls(str(path))
        races = load_races("data/races.json")
        player = create_player(
            game_id=storage.generate_game_id(),
            platform=TELEGRAM,
            external_user_id="o1",
            name="Аутбокс",
            race_id="human",
            races=races,
        )
        storage.save_new_player(player, TELEGRAM, "o1")
        return storage, player["game_id"]

    def _both(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        yield self._make(JsonStorage, base / "players.json")
        yield self._make(SQLiteStorage, base / "players.sqlite3")

    def test_enqueue_and_dequeue_roundtrip(self):
        for storage, gid in self._both():
            self.assertTrue(storage.enqueue_bot_messages(gid, ["a", "b"]))
            self.assertEqual(storage.enqueue_bot_messages(gid, []), False)
            self.assertEqual(
                storage.get_player_by_game_id(gid)["pending_bot_messages"], ["a", "b"]
            )
            self.assertEqual(storage.dequeue_bot_messages(gid), ["a", "b"])
            self.assertEqual(
                storage.get_player_by_game_id(gid).get("pending_bot_messages"), []
            )
            self.assertEqual(storage.dequeue_bot_messages(gid), [])

    def test_update_player_preserves_pending_against_stale_save(self):
        # Воспроизводит lost-update: фон ставит сообщение, пока бот держит
        # устаревшую копию игрока с пустым outbox и потом её сохраняет.
        for storage, gid in self._both():
            storage.enqueue_bot_messages(gid, ["m1"])
            stale = storage.get_player_by_game_id(gid)
            stale["pending_bot_messages"] = []  # бот «вычитал» в память
            stale["money"] = 777
            storage.enqueue_bot_messages(gid, ["m2"])  # конкурентный фон
            storage.update_player(stale)  # устаревшее полное сохранение
            fresh = storage.get_player_by_game_id(gid)
            self.assertEqual(fresh["pending_bot_messages"], ["m1", "m2"])
            self.assertEqual(fresh["money"], 777)  # остальные поля сохранились

    def test_dequeue_clears_then_concurrent_enqueue_survives_save(self):
        for storage, gid in self._both():
            storage.enqueue_bot_messages(gid, ["m1"])
            self.assertEqual(storage.dequeue_bot_messages(gid), ["m1"])
            storage.enqueue_bot_messages(gid, ["m2"])  # пришло после вычитки
            player = storage.get_player_by_game_id(gid)
            storage.update_player(player)  # обычное сохранение действия
            self.assertEqual(storage.dequeue_bot_messages(gid), ["m2"])

    def test_enqueue_preserves_dict_items(self):
        for storage, gid in self._both():
            storage.enqueue_bot_messages(gid, [{"type": "gift", "text": "дар"}])
            pending = storage.get_player_by_game_id(gid)["pending_bot_messages"]
            self.assertEqual(pending[-1]["text"], "дар")

    def test_durable_delivery_requeues_unsent_on_failure(self):
        # Codex P2: сбой бот-API в середине отправки не теряет outbox —
        # несработавшие сообщения возвращаются в очередь на повтор.
        from services.chat_log_service import DurableOutboxDelivery
        for storage, gid in self._both():
            messages = ["m1", "m2", "m3"]
            delivery = DurableOutboxDelivery(storage, gid, messages)
            sent = []
            try:
                for m in messages:
                    if m == "m2":
                        raise RuntimeError("bot api down")
                    sent.append(m)
                    delivery.mark_sent()
            except RuntimeError:
                pass
            finally:
                delivery.requeue_unsent()
            self.assertEqual(sent, ["m1"])
            self.assertEqual(storage.dequeue_bot_messages(gid), ["m2", "m3"])

    def test_durable_delivery_no_requeue_on_success(self):
        from services.chat_log_service import DurableOutboxDelivery
        for storage, gid in self._both():
            messages = ["a", "b"]
            delivery = DurableOutboxDelivery(storage, gid, messages)
            try:
                for _m in messages:
                    delivery.mark_sent()
            finally:
                delivery.requeue_unsent()
            self.assertEqual(storage.dequeue_bot_messages(gid), [])


if __name__ == "__main__":
    unittest.main()
