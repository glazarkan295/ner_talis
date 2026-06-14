import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.admin_panel_service import create_admin_promo
from services.promo_service import redeem_promo_code
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage
from storage.sqlite_storage import SQLiteStorage


class PromoAdminToBotTest(unittest.TestCase):
    """Promo codes created in the admin panel must redeem in the bot."""

    def _make_player(self, storage, ext_id):
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id, platform="telegram", external_user_id=str(ext_id),
            name=f"ПромоБот{ext_id}", race_id="human", races=races,
        )
        player["money"] = 0
        player["money_copper"] = 0
        storage.save_new_player(player, "telegram", str(ext_id))
        return game_id

    def _admin_session(self):
        return {"platform": "telegram", "admin_user_id": "1", "admin_key": "telegram:1"}

    def _check(self, storage):
        # Admin panel creates a promo; admin may type a leading slash.
        create_admin_promo(
            storage, code="/START100", uses_left=3, duration="never",
            rewards=[{"item_id": "money_copper", "amount": 1000}],
            admin_session=self._admin_session(),
        )
        # Different players redeem with different spellings (case / slash / spaces).
        for i, spelling in enumerate(("start100", "/START100", " Start100 ")):
            game_id = self._make_player(storage, 600 + i)
            ok, message = redeem_promo_code(storage, game_id, spelling)
            self.assertTrue(ok, f"redeem failed for {spelling!r}: {message}")
            refreshed = storage.get_player_by_game_id(game_id)
            self.assertEqual(int(refreshed.get("money_copper", 0)), 1000)
        # 3 uses spent -> the 4th player gets the exhausted message.
        last = self._make_player(storage, 999)
        ok, message = redeem_promo_code(storage, last, "START100")
        self.assertFalse(ok)
        self.assertIn("Лимит", message)

    def test_sqlite_admin_promo_redeems_in_bot(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = SQLiteStorage(str(Path(tmp) / "p.sqlite3"))
            self._check(storage)

    def test_json_admin_promo_redeems_in_bot(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PROMO_CODES_PATH"] = str(Path(tmp) / "promo.json")
            storage = JsonStorage(str(Path(tmp) / "p.json"))
            self._check(storage)

    def test_one_use_per_player_blocks_second_redeem(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = SQLiteStorage(str(Path(tmp) / "p.sqlite3"))
            game_id = self._make_player(storage, 700)
            create_admin_promo(
                storage, code="ONCE", uses_left=10, duration="never",
                rewards=[{"item_id": "money_copper", "amount": 500}],
                admin_session=self._admin_session(),
            )
            ok, _ = redeem_promo_code(storage, game_id, "once")
            self.assertTrue(ok)
            ok, message = redeem_promo_code(storage, game_id, "ONCE")
            self.assertFalse(ok)
            self.assertIn("уже использован", message)


if __name__ == "__main__":
    unittest.main()
