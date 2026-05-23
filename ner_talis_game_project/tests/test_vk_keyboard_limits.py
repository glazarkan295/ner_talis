import sys
import types
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class FakeVkKeyboard:
    def __init__(self, one_time=False, inline=False):
        self.rows = [[]]

    def add_line(self):
        self.rows.append([])

    def add_button(self, label, color=None):
        self.rows[-1].append(label)

    def get_keyboard(self):
        return str(self.rows)


class FakeVkKeyboardColor:
    PRIMARY = "primary"


fake_vk_api = types.ModuleType("vk_api")
fake_vk_keyboard = types.ModuleType("vk_api.keyboard")
fake_vk_keyboard.VkKeyboard = FakeVkKeyboard
fake_vk_keyboard.VkKeyboardColor = FakeVkKeyboardColor
sys.modules.setdefault("vk_api", fake_vk_api)
sys.modules.setdefault("vk_api.keyboard", fake_vk_keyboard)

from keyboards.vk_keyboards import VK_MAX_BUTTONS_PER_ROW, VK_MAX_ROWS, _fit_vk_button_rows, make_keyboard
from services.market_service import market_buy_buttons


class VkKeyboardLimitsTest(unittest.TestCase):
    def test_market_buy_keyboard_uses_short_readable_number_buttons(self):
        shared_buttons = market_buy_buttons()
        self.assertLessEqual(len(shared_buttons), VK_MAX_ROWS)

        fitted = _fit_vk_button_rows(shared_buttons)

        self.assertLessEqual(len(fitted), VK_MAX_ROWS)
        self.assertTrue(all(len(row) <= 2 for row in fitted[:-1]))
        flat = [button for row in fitted for button in row]
        self.assertIn("Купить 1", flat)
        self.assertIn("Купить 16", flat)
        self.assertIn("Покупка далее", flat)
        self.assertIn("Назад на рынок", flat)
        self.assertNotIn("Простое зелье лечения", flat)
        make_keyboard(shared_buttons)


if __name__ == "__main__":
    unittest.main()
