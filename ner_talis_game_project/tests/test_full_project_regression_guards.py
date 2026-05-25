import random
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Lightweight VK stubs for keyboard-only tests when vk_api is not installed.
if "vk_api" not in sys.modules:
    vk_api_stub = types.ModuleType("vk_api")
    vk_api_stub.__path__ = []
    vk_api_stub.VkApi = lambda *args, **kwargs: None
    sys.modules["vk_api"] = vk_api_stub

if "vk_api.bot_longpoll" not in sys.modules:
    bot_longpoll_stub = types.ModuleType("vk_api.bot_longpoll")
    bot_longpoll_stub.VkBotEventType = types.SimpleNamespace(MESSAGE_NEW="message_new")
    bot_longpoll_stub.VkBotLongPoll = lambda *args, **kwargs: None
    sys.modules["vk_api.bot_longpoll"] = bot_longpoll_stub

if "vk_api.utils" not in sys.modules:
    utils_stub = types.ModuleType("vk_api.utils")
    utils_stub.get_random_id = lambda: 1
    sys.modules["vk_api.utils"] = utils_stub

if "vk_api.keyboard" not in sys.modules:
    keyboard_stub = types.ModuleType("vk_api.keyboard")

    class _FakeKeyboard:
        def __init__(self, one_time=False, inline=False):
            self.rows = [[]]

        def add_line(self):
            self.rows.append([])

        def add_button(self, label, color=None):
            self.rows[-1].append(label)

        def get_keyboard(self):
            return str(self.rows)

    keyboard_stub.VkKeyboard = _FakeKeyboard
    keyboard_stub.VkKeyboardColor = types.SimpleNamespace(PRIMARY="primary")
    sys.modules["vk_api.keyboard"] = keyboard_stub

from keyboards.vk_keyboards import VK_MAX_BUTTONS_PER_ROW, VK_MAX_ROWS, _fit_vk_button_rows
from services.city_service import process_world_action
from services.derived_stats_service import calculate_player_derived_stats
from services.pve_battle_service import BATTLE_ESCAPE, BATTLE_POUCH, create_location_battle, format_battle_started_text, grant_battle_rewards, handle_battle_action
from site_api import frontend_profile


class AlwaysLootRandom(random.Random):
    def uniform(self, a, b):
        return 0

    def randint(self, a, b):
        return a


class DummyStorage:
    def __init__(self):
        self.updated = []
        self.sessions = []

    def update_player(self, player):
        self.updated.append(dict(player))
        return player

    def create_site_session(self, game_id, scope, platform, lifetime_minutes=1440):
        self.sessions.append((game_id, scope, platform))
        return "profile-token"


class FullProjectRegressionGuardsTest(unittest.TestCase):
    def test_profile_attributes_use_unified_derived_stats(self):
        player = {
            "game_id": "NT-TEST",
            "name": "Тестовый герой",
            "level": 25,
            "stats": {"strength": 120, "endurance": 80, "dexterity": 60, "perception": 45, "intelligence": 30, "wisdom": 20},
            "invested_stats": {"strength": 50, "endurance": 10},
            "stat_bonuses": {"strength": 2},
            "equipment": {
                "weapon1": {
                    "id": "test_sword",
                    "name": "Тестовый меч",
                    "type": "Оружие",
                    "stat_modifiers": {"bonus_strength": 5, "bonus_accuracy": 3},
                }
            },
            "inventory": [],
        }
        derived = calculate_player_derived_stats(player)
        profile = frontend_profile(player)
        by_key = {item["key"]: item["value"] for item in profile["attributes"]}

        self.assertEqual(by_key["strength"], derived["strength"])
        self.assertEqual(by_key["endurance"], derived["endurance"])
        self.assertEqual(profile["parameters"][0]["value"], f"{derived['max_hp']} / {derived['max_hp']}")

    def test_pending_skill_is_cleared_when_player_opens_pouch(self):
        player = {
            "game_id": "NT-BATTLE",
            "name": "Боец",
            "level": 10,
            "stats": {"strength": 20, "endurance": 20, "dexterity": 20, "perception": 20, "intelligence": 10, "wisdom": 10},
            "inventory": [],
            "equipment": {},
        }
        battle, _ = create_location_battle(player, random.Random(2), "hilly_meadows")
        battle["pending_skill"] = {"id": "test_skill", "name": "Старый выбранный навык"}
        player["active_battle"] = battle

        handle_battle_action(player, BATTLE_POUCH, random.Random(3))

        self.assertNotIn("pending_skill", player["active_battle"])


    def test_battle_start_text_uses_plain_magic_defense_icon(self):
        battle = {
            "battle_log": ["Тестовая стычка."],
            "round_number": 1,
            "player_name": "Боец",
            "player_state": {
                "current_hp": 100,
                "max_hp": 100,
                "current_spirit": 30,
                "max_spirit": 30,
                "current_mana": 20,
                "max_mana": 20,
                "accuracy": 10,
                "dodge": 5,
                "physical_defense": 7,
                "magic_defense": 9,
            },
            "enemies": [],
        }

        text = format_battle_started_text(battle)

        self.assertIn("🛡 7 · ✨ 9", text)
        self.assertNotIn("✨🛡 9", text)

    def test_pve_escape_succeeds_with_forty_percent_chance(self):
        player = {
            "game_id": "NT-ESCAPE",
            "name": "Беглец",
            "level": 10,
            "stats": {"strength": 20, "endurance": 20, "dexterity": 20, "perception": 20, "intelligence": 10, "wisdom": 10},
            "inventory": [],
            "equipment": {},
            "in_battle": True,
        }
        battle, _ = create_location_battle(player, random.Random(2), "hilly_meadows")
        player["active_battle"] = battle

        text, buttons = handle_battle_action(player, BATTLE_ESCAPE, random.Random(3))

        self.assertIn("сбегает", text.casefold())
        self.assertFalse(player.get("in_battle"))
        self.assertIsNone(player.get("active_battle"))
        self.assertEqual(buttons, [])

    def test_pve_escape_failure_skips_player_turn_and_enemies_act(self):
        player = {
            "game_id": "NT-ESCAPE-FAIL",
            "name": "Беглец",
            "level": 10,
            "stats": {"strength": 20, "endurance": 20, "dexterity": 20, "perception": 20, "intelligence": 10, "wisdom": 10},
            "inventory": [],
            "equipment": {},
            "in_battle": True,
        }
        battle, _ = create_location_battle(player, random.Random(2), "hilly_meadows")
        start_round = battle.get("round_number", 1)
        player["active_battle"] = battle

        text, buttons = handle_battle_action(player, BATTLE_ESCAPE, random.Random(0))

        self.assertIn("Ход пропущен", text)
        self.assertTrue(player.get("in_battle"))
        self.assertIsInstance(player.get("active_battle"), dict)
        self.assertEqual(player["active_battle"].get("round_number"), start_round + 1)
        self.assertTrue(buttons)

    def test_battle_duplicate_loot_names_are_granted_by_location_item_id(self):
        hilly_player = {"game_id": "NT-HILLY", "level": 1, "inventory": [], "equipment": {}}
        hilly_battle = {"return_location": "hilly_meadows", "enemies": [{"name": "Бык", "level": 1, "rank": "normal"}]}
        grant_battle_rewards(hilly_player, hilly_battle, AlwaysLootRandom())
        hilly_ids = {item.get("id") for item in hilly_player["inventory"]}
        self.assertIn("strong_tendon", hilly_ids)
        self.assertNotIn("strong_sinew", hilly_ids)

        forest_player = {"game_id": "NT-FOREST", "level": 10, "inventory": [], "equipment": {}}
        forest_battle = {"return_location": "ordinary_forest", "enemies": [{"name": "Разъярённый олень", "level": 10, "rank": "normal"}]}
        grant_battle_rewards(forest_player, forest_battle, AlwaysLootRandom())
        forest_ids = {item.get("id") for item in forest_player["inventory"]}
        self.assertIn("strong_sinew", forest_ids)
        self.assertNotIn("strong_tendon", forest_ids)

    def test_vk_keyboard_keeps_priority_navigation_and_battle_buttons(self):
        buttons = [[f"Предмет рынка {index}"] for index in range(50)]
        buttons.extend([
            ["Назад на рынок"],
            ["Вернуться в город"],
            ["Вернуться к воротам"],
            ["Подсумок"],
            ["Сбежать"],
            ["Свернуть лагерь"],
            ["Профиль"],
        ])

        fitted = _fit_vk_button_rows(buttons)
        flat = [button for row in fitted for button in row]

        self.assertLessEqual(len(fitted), VK_MAX_ROWS)
        self.assertTrue(all(len(row) <= VK_MAX_BUTTONS_PER_ROW for row in fitted))
        for label in ["Назад на рынок", "Вернуться в город", "Вернуться к воротам", "Подсумок", "Сбежать", "Свернуть лагерь", "Профиль"]:
            self.assertIn(label, flat)

    def test_common_world_router_handles_profile_button_safely(self):
        storage = DummyStorage()
        player = {"game_id": "NT-PROFILE", "current_zone": "seldar_central_square", "inventory": [], "equipment": {}}

        result = process_world_action(storage, player, "Профиль", "telegram")

        self.assertIn("Профиль на сайте готов", result.text)
        self.assertIn("profile-token", result.text)
        self.assertEqual(storage.sessions, [("NT-PROFILE", "profile", "telegram")])

    def test_main_can_disable_vk_without_requiring_vk_env(self):
        import main as combined_main

        events = []

        class _FakeApp:
            bot_data = {"storage": None}

        env = {
            "ENABLE_VK": "false",
            "ENABLE_TELEGRAM": "true",
            "TELEGRAM_BOT_TOKEN": "telegram-test-token",
        }

        with patch.dict("os.environ", env, clear=True), \
             patch.object(combined_main, "load_project_env", lambda: None), \
             patch.object(combined_main, "build_application", lambda: _FakeApp()), \
             patch.object(combined_main, "recover_runtime_timers", lambda _app: None), \
             patch.object(combined_main, "run_application", lambda _app: events.append("telegram")), \
             patch.object(combined_main, "start_vk_thread", lambda: events.append("vk")):
            combined_main.main()

        self.assertEqual(events, ["telegram"])


    def test_crafting_service_has_no_duplicate_alchemy_menu_guard(self):
        source = (Path(__file__).resolve().parents[1] / "services" / "crafting_service.py").read_text(encoding="utf-8")
        self.assertNotIn('if workshop_id == "alchemy":\n    if workshop_id == "alchemy":', source)

    def test_main_vk_thread_sets_daemon_once(self):
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        start = source.index("def start_vk_thread")
        end = source.index("def build_telegram_bot_application")
        self.assertEqual(source[start:end].count("daemon=True"), 1)

    def test_profile_skills_tab_uses_active_skills_title_without_start_available_row(self):
        component = (Path(__file__).resolve().parents[2] / "web" / "src" / "components" / "player-profile" / "PlayerProfile.jsx").read_text(encoding="utf-8")

        self.assertIn('Panel title="Активные навыки"', component)
        self.assertNotIn('Panel title="Стартовые навыки"', component)
        self.assertNotIn('label="Доступно" value="стартовые навыки"', component)
        self.assertNotIn('Стартовых навыков пока нет.', component)


if __name__ == "__main__":
    unittest.main()
