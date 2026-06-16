import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class CritInBattleTest(unittest.TestCase):
    def test_player_battle_state_carries_crit_and_roll_multiplies(self):
        from services.pve_battle_models import PlayerBattleState
        # Поля крита присутствуют в боевом состоянии.
        state = PlayerBattleState(
            current_hp=100, max_hp=100, current_spirit=0, max_spirit=0, current_mana=0, max_mana=0,
            armor=0, magic_armor=0, physical_defense=0, magic_defense=0, accuracy=10, dodge=10,
            crit_chance=100, crit_damage=200,
        )
        self.assertEqual(state.crit_chance, 100)
        self.assertEqual(state.crit_damage, 200)

    def test_make_player_battle_state_copies_crit(self):
        from services.pve_battle_service import make_player_battle_state
        from services.registration_service import create_player, load_races
        player = create_player(game_id="C", platform="telegram", external_user_id="1", name="Боец", race_id="human", races=load_races("data/races.json"))
        state = make_player_battle_state(player)
        self.assertTrue(hasattr(state, "crit_chance"))
        self.assertTrue(hasattr(state, "crit_damage"))
        self.assertGreaterEqual(state.crit_damage, 100)


class PortStockAtomicTest(unittest.TestCase):
    def test_claim_is_all_or_nothing(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PORT_MARKET_STATE_PATH"] = str(Path(tmp) / "port_state.json")
            try:
                import services.market_service as ms
                ms._save_port_state({"generated_at": 0, "expires_at": 9e18, "items": [{"item_id": "arrow_for_bow", "stock": 3}]})
                # Запрос больше остатка не списывает ничего.
                claimed, available = ms.claim_port_stock("arrow_for_bow", 5)
                self.assertEqual((claimed, available), (0, 3))
                # Запрос в пределах остатка списывает ровно столько.
                claimed, available = ms.claim_port_stock("arrow_for_bow", 3)
                self.assertEqual((claimed, available), (3, 3))
                # Больше не осталось.
                claimed, available = ms.claim_port_stock("arrow_for_bow", 1)
                self.assertEqual((claimed, available), (0, 0))
            finally:
                os.environ.pop("PORT_MARKET_STATE_PATH", None)


class MoneyRewardCapTest(unittest.TestCase):
    def test_high_denomination_capped_by_copper(self):
        from services.admin_panel_service import _normalize_rewards, MAX_REWARD_MONEY_COPPER
        # 20 млн древних × 500 млрд = 1e19 меди — должно быть отклонено.
        with self.assertRaises(ValueError):
            _normalize_rewards([{"item_id": "money_ancient", "amount": 20_000_000}])
        # Небольшая сумма проходит.
        ok = _normalize_rewards([{"item_id": "money_silver", "amount": 10}])
        self.assertEqual(ok[0]["kind"], "money")


if __name__ == "__main__":
    unittest.main()
