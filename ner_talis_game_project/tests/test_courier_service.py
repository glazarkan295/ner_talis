import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import courier_service
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage

TELEGRAM = "telegram"


class FakeRng:
    """Deterministic RNG: controls outcome roll, delivery delay and choice."""

    def __init__(self, random_value=0.5, randint_value=12, choice_index=0):
        self._random = random_value
        self._randint = randint_value
        self._choice_index = choice_index

    def random(self):
        return self._random

    def randint(self, a, b):
        return self._randint

    def choice(self, seq):
        return seq[self._choice_index]


def _make_item(item_id="test_potion", name="Зелье", amount=5):
    return {
        "id": item_id,
        "item_id": item_id,
        "name": name,
        "amount": amount,
        "category": "Расходники",
        "stackable": True,
        "max_stack": 99,
    }


class CourierServiceTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        base = Path(self._temp.name)
        self.storage = JsonStorage(str(base / "players.json"))
        self._prev_env = os.environ.get("COURIER_TRANSFERS_PATH")
        os.environ["COURIER_TRANSFERS_PATH"] = str(base / "courier_transfers.json")
        self.addCleanup(self._restore_env)
        self.races = load_races("data/races.json")
        self.now = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)

    def _restore_env(self):
        if self._prev_env is None:
            os.environ.pop("COURIER_TRANSFERS_PATH", None)
        else:
            os.environ["COURIER_TRANSFERS_PATH"] = self._prev_env

    def _make_player(self, external_id, name, *, level=1, money=0, inventory=None):
        player = create_player(
            game_id=self.storage.generate_game_id(),
            platform=TELEGRAM,
            external_user_id=external_id,
            name=name,
            race_id="human",
            races=self.races,
        )
        player["level"] = level
        player["money"] = money
        player["inventory"] = list(inventory or [])
        self.storage.save_new_player(player, TELEGRAM, external_id)
        return self.storage.get_player_by_game_id(player["game_id"])

    # --- cost --------------------------------------------------------------
    def test_delivery_cost_is_thirteen_per_level(self):
        self.assertEqual(courier_service.delivery_cost_copper(1), 13)
        self.assertEqual(courier_service.delivery_cost_copper(100), 1300)
        self.assertEqual(courier_service.delivery_cost_copper(0), 13)

    # --- creation ----------------------------------------------------------
    def test_create_transfer_deducts_items_money_and_queues(self):
        sender = self._make_player("s1", "Отправитель", level=10, money=1000, inventory=[_make_item(amount=5)])
        self._make_player("r1", "Получатель")

        result = courier_service.create_courier_transfer(
            self.storage, sender, "Получатель",
            [{"item_id": "test_potion", "inventory_index": 0, "amount": 3}],
            coins=100, letter="Привет", now=self.now, rng=FakeRng(),
        )

        # 3 sent, 2 left in sender stack
        self.assertEqual(sender["inventory"][0]["amount"], 2)
        # cost = 13*10 = 130, coins=100 → money 1000-130-100 = 770
        self.assertEqual(sender["money"], 770)
        self.assertIn("Посылка передана гонцу", result["message"])
        self.assertIn("Получатель", result["message"])

        queue = courier_service._load_transfers()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["coins"], 100)
        self.assertEqual(queue[0]["letter"], "Привет")
        self.assertEqual(queue[0]["items"][0]["amount"], 3)

    def test_create_rejects_unknown_receiver(self):
        sender = self._make_player("s2", "Отпр2", money=1000, inventory=[_make_item()])
        with self.assertRaises(courier_service.CourierError):
            courier_service.create_courier_transfer(
                self.storage, sender, "НетТакого",
                [{"item_id": "test_potion", "inventory_index": 0, "amount": 1}],
                now=self.now, rng=FakeRng(),
            )

    def test_create_rejects_self_transfer(self):
        sender = self._make_player("s3", "СамСебе", money=1000, inventory=[_make_item()])
        with self.assertRaises(courier_service.CourierError):
            courier_service.create_courier_transfer(
                self.storage, sender, "СамСебе",
                [{"item_id": "test_potion", "inventory_index": 0, "amount": 1}],
                now=self.now, rng=FakeRng(),
            )

    def test_create_rejects_insufficient_money(self):
        sender = self._make_player("s4", "Бедняк", level=100, money=10, inventory=[_make_item()])
        self._make_player("r4", "Богач")
        with self.assertRaises(courier_service.CourierError):
            courier_service.create_courier_transfer(
                self.storage, sender, "Богач",
                [{"item_id": "test_potion", "inventory_index": 0, "amount": 1}],
                now=self.now, rng=FakeRng(),
            )

    def test_create_rejects_long_letter(self):
        sender = self._make_player("s5", "Писатель", money=1000, inventory=[_make_item()])
        self._make_player("r5", "Читатель")
        with self.assertRaises(courier_service.CourierError):
            courier_service.create_courier_transfer(
                self.storage, sender, "Читатель",
                [{"item_id": "test_potion", "inventory_index": 0, "amount": 1}],
                letter="x" * 31, now=self.now, rng=FakeRng(),
            )

    def test_create_rejects_empty_payload(self):
        sender = self._make_player("s6", "Пустой", money=1000, inventory=[_make_item()])
        self._make_player("r6", "Кто-то")
        with self.assertRaises(courier_service.CourierError):
            courier_service.create_courier_transfer(
                self.storage, sender, "Кто-то", [], coins=0,
                now=self.now, rng=FakeRng(),
            )

    # --- delivery outcomes -------------------------------------------------
    def _enqueue(self, sender, receiver_name, **kwargs):
        return courier_service.create_courier_transfer(
            self.storage, sender, receiver_name,
            [{"item_id": "test_potion", "inventory_index": 0, "amount": 2}],
            now=self.now, rng=FakeRng(randint_value=12), **kwargs,
        )

    def test_successful_delivery_gives_items_to_receiver(self):
        sender = self._make_player("s7", "Курьеротправ", money=1000, inventory=[_make_item(amount=5)])
        receiver = self._make_player("r7", "Адресат")
        self._enqueue(sender, "Адресат", coins=50, letter="Спасибо")
        self.storage.update_player(sender)

        # success roll (50%) and time past deliver_at
        processed = courier_service.process_due_transfers(
            self.storage, now=self.now + timedelta(minutes=20), rng=FakeRng(random_value=0.5),
        )
        self.assertEqual(processed, 1)

        fresh = self.storage.get_player_by_game_id(receiver["game_id"])
        stack = next((it for it in fresh["inventory"] if it.get("item_id") == "test_potion"), None)
        self.assertIsNotNone(stack)
        self.assertEqual(stack["amount"], 2)
        self.assertEqual(fresh["money"], 50)
        pending = "\n".join(fresh.get("pending_bot_messages", []))
        self.assertIn("Гонец останавливается рядом", pending)
        self.assertIn("Вы получили посылку от игрока Курьеротправ", pending)
        self.assertIn("Спасибо", pending)
        # queue drained
        self.assertEqual(courier_service._load_transfers(), [])

    def test_stolen_delivery_notifies_sender_only(self):
        sender = self._make_player("s8", "Невезучий", money=1000, inventory=[_make_item(amount=5)])
        receiver = self._make_player("r8", "Жертва")
        self._enqueue(sender, "Жертва")
        self.storage.update_player(sender)

        processed = courier_service.process_due_transfers(
            self.storage, now=self.now + timedelta(minutes=20),
            rng=FakeRng(random_value=0.00005),  # *100 = 0.005 < 0.01 → stolen
        )
        self.assertEqual(processed, 1)

        fresh_receiver = self.storage.get_player_by_game_id(receiver["game_id"])
        self.assertEqual(fresh_receiver["inventory"], [])
        fresh_sender = self.storage.get_player_by_game_id(sender["game_id"])
        pending = "\n".join(fresh_sender.get("pending_bot_messages", []))
        self.assertIn("Посылка не была доставлена", pending)
        self.assertIn("украдена", pending)

    def test_misdelivery_routes_to_random_player(self):
        sender = self._make_player("s9", "Отпр9", money=1000, inventory=[_make_item(amount=5)])
        receiver = self._make_player("r9", "Адр9")
        bystander = self._make_player("b9", "Случайный")
        self._enqueue(sender, "Адр9")
        self.storage.update_player(sender)

        processed = courier_service.process_due_transfers(
            self.storage, now=self.now + timedelta(minutes=20),
            rng=FakeRng(random_value=0.0005),  # *100 = 0.05 → misdelivery
        )
        self.assertEqual(processed, 1)

        fresh_intended = self.storage.get_player_by_game_id(receiver["game_id"])
        self.assertEqual(fresh_intended["inventory"], [])
        fresh_random = self.storage.get_player_by_game_id(bystander["game_id"])
        stack = next((it for it in fresh_random["inventory"] if it.get("item_id") == "test_potion"), None)
        self.assertIsNotNone(stack)
        random_pending = "\n".join(fresh_random.get("pending_bot_messages", []))
        self.assertIn("Вы получили чужую посылку", random_pending)
        sender_pending = "\n".join(
            self.storage.get_player_by_game_id(sender["game_id"]).get("pending_bot_messages", [])
        )
        self.assertIn("доставлена не тому получателю", sender_pending)

    def test_transfer_not_due_is_not_processed(self):
        sender = self._make_player("s10", "Ранний", money=1000, inventory=[_make_item(amount=5)])
        self._make_player("r10", "Ждущий")
        self._enqueue(sender, "Ждущий")
        self.storage.update_player(sender)

        processed = courier_service.process_due_transfers(
            self.storage, now=self.now + timedelta(minutes=5), rng=FakeRng(random_value=0.5),
        )
        self.assertEqual(processed, 0)
        self.assertEqual(len(courier_service._load_transfers()), 1)

    def test_search_players_matches_name_and_id(self):
        self._make_player("s11", "ИскомыйНик")
        results = courier_service.search_players(self.storage, "Искомый")
        self.assertTrue(any(r["name"] == "ИскомыйНик" for r in results))


if __name__ == "__main__":
    unittest.main()
