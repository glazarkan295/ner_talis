import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.gathering_tools import player_has_tool, spend_tool_use, tool_uses_left

ROD = "fishing_rod"
NAMES = ("удочка рыбака",)


def _player(amount):
    return {"inventory": [{"id": ROD, "item_id": ROD, "name": "Удочка рыбака", "amount": amount}]}


class GatheringToolsDurabilityTest(unittest.TestCase):
    def test_total_uses_is_count_times_ten(self):
        self.assertEqual(tool_uses_left(_player(1), ROD, NAMES), 10)
        self.assertEqual(tool_uses_left(_player(3), ROD, NAMES), 30)
        self.assertEqual(tool_uses_left(_player(14), ROD, NAMES), 140)

    def test_one_tool_consumed_per_ten_uses(self):
        player = _player(3)
        for i in range(1, 31):
            self.assertTrue(spend_tool_use(player, ROD, NAMES))
            self.assertEqual(tool_uses_left(player, ROD, NAMES), 30 - i)
            # Один инструмент расходуется ровно на 10-м, 20-м, 30-м использовании.
            if i < 30:
                self.assertTrue(player_has_tool(player, ROD, NAMES))
        # После 30 использований инструментов не осталось.
        self.assertFalse(player_has_tool(player, ROD, NAMES))
        self.assertFalse(spend_tool_use(player, ROD, NAMES))

    def test_single_tool_lasts_exactly_ten_uses(self):
        player = _player(1)
        for _ in range(10):
            self.assertTrue(spend_tool_use(player, ROD, NAMES))
        self.assertFalse(player_has_tool(player, ROD, NAMES))

    def test_no_tool_returns_false(self):
        self.assertFalse(spend_tool_use({"inventory": []}, ROD, NAMES))
        self.assertEqual(tool_uses_left({"inventory": []}, ROD, NAMES), 0)


if __name__ == "__main__":
    unittest.main()
