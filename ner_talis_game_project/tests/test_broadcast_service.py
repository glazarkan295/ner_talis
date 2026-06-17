import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import broadcast_service
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage

TELEGRAM = "telegram"


class BroadcastServiceTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.storage = JsonStorage(str(Path(self._temp.name) / "players.json"))
        self.races = load_races("data/races.json")

    def _make_player(self, external_id, name, *, gender="male", level=1):
        player = create_player(
            game_id=self.storage.generate_game_id(),
            platform=TELEGRAM,
            external_user_id=external_id,
            name=name,
            race_id="human",
            races=self.races,
            gender_id=gender,
            gender_label="Муж." if gender == "male" else "Жен.",
        )
        player["level"] = level
        self.storage.save_new_player(player, TELEGRAM, external_id)
        return self.storage.get_player_by_game_id(player["game_id"])

    def _pending(self, game_id):
        player = self.storage.get_player_by_game_id(game_id)
        return list(player.get("pending_bot_messages", []))

    def test_select_by_gender(self):
        m = self._make_player("m1", "Муж1", gender="male")
        self._make_player("f1", "Жен1", gender="female")
        ids = broadcast_service.select_recipient_ids(self.storage, "male")
        self.assertEqual(ids, [m["game_id"]])

    def test_select_by_level_ranges(self):
        low = self._make_player("l1", "Низкий", level=10)
        mid = self._make_player("l2", "Средний", level=75)
        high = self._make_player("l3", "Высокий", level=1200)
        self.assertCountEqual(
            broadcast_service.select_recipient_ids(self.storage, "lvl_1_50"),
            [low["game_id"]],
        )
        self.assertCountEqual(
            broadcast_service.select_recipient_ids(self.storage, "lvl_50_100"),
            [mid["game_id"]],
        )
        self.assertCountEqual(
            broadcast_service.select_recipient_ids(self.storage, "lvl_1000_plus"),
            [high["game_id"]],
        )
        self.assertCountEqual(
            broadcast_service.select_recipient_ids(self.storage, "lvl_50_plus"),
            [mid["game_id"], high["game_id"]],
        )

    def test_select_all(self):
        a = self._make_player("a1", "Алиса")
        b = self._make_player("b1", "Боб")
        self.assertCountEqual(
            broadcast_service.select_recipient_ids(self.storage, "all"),
            [a["game_id"], b["game_id"]],
        )

    def test_specific_players_by_nick_and_id(self):
        a = self._make_player("a2", "Нэйм")
        b = self._make_player("b2", "Другой")
        ids = broadcast_service.select_recipient_ids(
            self.storage, "specific", ["Нэйм", b["game_id"]]
        )
        self.assertCountEqual(ids, [a["game_id"], b["game_id"]])

    def test_specific_unknown_raises(self):
        with self.assertRaises(broadcast_service.BroadcastError):
            broadcast_service.select_recipient_ids(self.storage, "specific", ["НетТакого"])

    def test_broadcast_queues_message(self):
        a = self._make_player("a3", "Получатель1")
        b = self._make_player("b3", "Получатель2")
        result = broadcast_service.broadcast_message(self.storage, "all", "Привет, мир!")
        self.assertEqual(result["delivered"], 2)
        self.assertEqual(result["recipients"], 2)
        self.assertIn("Привет, мир!", self._pending(a["game_id"]))
        self.assertIn("Привет, мир!", self._pending(b["game_id"]))

    def test_broadcast_empty_message_raises(self):
        self._make_player("a4", "Кто-то")
        with self.assertRaises(broadcast_service.BroadcastError):
            broadcast_service.broadcast_message(self.storage, "all", "   ")

    def test_broadcast_no_recipients_raises(self):
        self._make_player("a5", "Мужчина", gender="male")
        with self.assertRaises(broadcast_service.BroadcastError):
            broadcast_service.broadcast_message(self.storage, "female", "Только дамам")

    def test_unknown_audience_raises(self):
        self._make_player("a6", "Игрок")
        with self.assertRaises(broadcast_service.BroadcastError):
            broadcast_service.select_recipient_ids(self.storage, "nonsense")


if __name__ == "__main__":
    unittest.main()
