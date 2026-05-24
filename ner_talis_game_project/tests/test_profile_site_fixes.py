import sys
import types
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


if "vk_api" not in sys.modules:
    vk_api_stub = types.ModuleType("vk_api")
    vk_api_stub.VkApi = lambda *args, **kwargs: None
    bot_longpoll_stub = types.ModuleType("vk_api.bot_longpoll")
    bot_longpoll_stub.VkBotEventType = types.SimpleNamespace(MESSAGE_NEW="message_new")
    bot_longpoll_stub.VkBotLongPoll = lambda *args, **kwargs: None
    utils_stub = types.ModuleType("vk_api.utils")
    utils_stub.get_random_id = lambda: 1
    keyboard_stub = types.ModuleType("vk_api.keyboard")

    class _FakeKeyboard:
        def __init__(self, *args, **kwargs):
            self.buttons = []

        def add_line(self):
            self.buttons.append("line")

        def add_button(self, label, color=None):
            self.buttons.append(label)

        def get_keyboard(self):
            return "{}"

    keyboard_stub.VkKeyboard = _FakeKeyboard
    keyboard_stub.VkKeyboardColor = types.SimpleNamespace(PRIMARY="primary")
    sys.modules["vk_api"] = vk_api_stub
    sys.modules["vk_api.bot_longpoll"] = bot_longpoll_stub
    sys.modules["vk_api.utils"] = utils_stub
    sys.modules["vk_api.keyboard"] = keyboard_stub

from services.registration_service import create_player, load_races
from services.inventory_service import add_inventory_item
from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item
from services.web_profile import PROFILE_SCOPE, create_profile_site_link
from site_api import create_profile_api_router, equipment_modifier_totals, frontend_profile, is_inventory_item_usable
from storage.json_storage import JsonStorage
from handlers.vk_registration import VK_PLATFORM, VkRegistrationBot


class ProfileSiteFixesTest(unittest.TestCase):
    def _new_player(self):
        races = load_races("data/races.json")
        return create_player(
            game_id="NT-PROFILEFIX",
            platform="telegram",
            external_user_id="111",
            name="Профиль",
            race_id="human",
            races=races,
        )

    def test_frontend_profile_handles_empty_runtime_resources(self):
        player = self._new_player()
        player["hp"] = None
        player["spirit"] = None
        player["mana"] = None

        profile = frontend_profile(player)

        values = {row["label"]: row["value"] for row in profile["parameters"]}
        self.assertRegex(values["HP"], r"^\d+ / \d+$")
        self.assertRegex(values["Дух"], r"^\d+ / \d+$")
        self.assertRegex(values["Мана"], r"^\d+ / \d+$")
        self.assertNotIn("Концентрация", values)

    def test_frontend_profile_filters_legacy_concentration_skill_costs(self):
        player = self._new_player()
        player["skills"]["active"].append(
            {
                "id": "legacy_focus",
                "name": "Старый фокус",
                "resource_text": "Cost: Concentration: 1",
                "concentration_cost": 1,
                "mana_cost": 2,
                "spirit_cost": 0,
            }
        )

        profile = frontend_profile(player)
        skill_ids = {skill["id"] for skill in profile["skills"]["active"]}

        self.assertNotIn("legacy_focus", skill_ids)
        self.assertEqual(skill_ids, {"basic_attack", "magic_spark"})

    def test_frontend_profile_exposes_free_skill_points(self):
        player = self._new_player()
        player["free_skill_points"] = 7

        profile = frontend_profile(player)

        self.assertEqual(profile["player"]["freeSkillPoints"], 7)

    def test_equipped_items_change_final_parameters(self):
        player = self._new_player()

        with_equipment = frontend_profile(player)
        player["equipment"].pop("weapon1")
        without_staff = frontend_profile(player)

        def parameter(profile, label):
            value = next(row["value"] for row in profile["parameters"] if row["label"] == label)
            if isinstance(value, str) and "/" in value:
                return int(value.split("/")[-1].strip())
            return int(str(value).rstrip("%"))

        self.assertGreater(parameter(with_equipment, "Мана"), parameter(without_staff, "Мана"))
        self.assertGreater(parameter(with_equipment, "Точность"), parameter(without_staff, "Точность"))

    def test_equipment_text_modifiers_are_summed(self):
        player = self._new_player()
        player["equipment"] = {
            "ring1": {"stats": ["Точность: +1"]},
            "ring2": {"stats": ["+2 к точность"]},
        }

        modifiers = equipment_modifier_totals(player)

        self.assertEqual(modifiers["bonus_accuracy"], 3)

    def test_structured_equipment_modifiers_are_not_double_counted_by_display_stats(self):
        player = self._new_player()
        player["equipment"] = {
            "ring1": {
                "stat_modifiers": {"bonus_accuracy": 2},
                "stats": ["Точность: +2"],
            }
        }

        modifiers = equipment_modifier_totals(player)

        self.assertEqual(modifiers["bonus_accuracy"], 2)

    def test_active_effect_modifiers_are_used_in_profile_formulas(self):
        player = self._new_player()
        player["energy"] = 150
        base_profile = frontend_profile(player)
        player["active_effects"] = [
            {
                "name": "Сосредоточенность",
                "stat_modifiers": {
                    "bonus_accuracy": 10,
                    "max_energy": 15,
                    "bonus_crit_damage_percent": 25,
                },
            }
        ]

        boosted_profile = frontend_profile(player)
        base_values = {row["label"]: row["value"] for row in base_profile["parameters"]}
        boosted_values = {row["label"]: row["value"] for row in boosted_profile["parameters"]}

        self.assertGreater(int(boosted_values["Точность"]), int(base_values["Точность"]))
        self.assertEqual(boosted_values["Энергия"], "115 / 115")
        self.assertEqual(boosted_values["Урон крита"], "125%")

    def test_damage_modifiers_are_used_in_frontend_skill_damage(self):
        player = self._new_player()
        player["level"] = 10
        player["active_effects"] = [
            {
                "name": "Боевой импульс",
                "stat_modifiers": {
                    "bonus_damage": 2,
                    "bonus_physical_damage": 3,
                    "magic_damage": 4,
                },
            }
        ]

        profile = frontend_profile(player)
        skills = {skill["id"]: skill for skill in profile["skills"]["active"]}

        self.assertEqual(skills["basic_attack"]["damage"], 25)
        self.assertEqual(skills["magic_spark"]["damage"], 24)

    def test_inventory_actions_are_based_on_current_location(self):
        player = self._new_player()
        item = player["equipment"].pop("weapon1")
        item["targetSlotKey"] = "weapon1"
        item.pop("slotKey", None)
        item["actions"] = ["Снять"]
        player["inventory"].append(item)

        profile = frontend_profile(player)
        weapon = next(item for item in profile["inventory"] if item["id"] == "starter_wooden_staff")

        self.assertEqual(weapon["actions"], ["Надеть"])


    def test_overflow_inventory_penalty_is_visible_and_affects_profile_stats(self):
        player = self._new_player()
        player["inventory_capacity"] = 40
        player["inventory"] = [
            {"id": f"regular_{index}", "name": f"Обычный предмет {index}", "amount": 1, "max_stack": 1}
            for index in range(40)
        ]
        base_profile = frontend_profile(player)
        base_dodge = int(next(row["value"] for row in base_profile["parameters"] if row["label"] == "Уклонение"))

        for index in range(4):
            add_inventory_item(
                player,
                {"id": f"overflow_{index}", "name": f"Лишний предмет {index}", "amount": 1, "max_stack": 1},
                1,
                item_id=f"overflow_{index}",
                max_stack=1,
            )

        profile = frontend_profile(player)
        dodge = int(next(row["value"] for row in profile["parameters"] if row["label"] == "Уклонение"))
        overflow_items = [item for item in profile["inventory"] if item.get("overflowSlot")]
        effect_names = [effect["name"] for effect in profile["effects"]]

        self.assertEqual(len(overflow_items), 4)
        self.assertTrue(profile["player"]["inventoryNoEscape"])
        self.assertIn("Перегруз инвентаря", effect_names)
        self.assertTrue(any(effect.get("kind") == "negative" for effect in profile["effects"]))
        self.assertLess(dodge, base_dodge)

    def test_profile_button_link_uses_short_lived_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            races = load_races("data/races.json")
            player = create_player(
                game_id=storage.generate_game_id(),
                platform="telegram",
                external_user_id="111",
                name="Ссылка",
                race_id="human",
                races=races,
            )
            storage.save_new_player(player, "telegram", "111")

            link = create_profile_site_link(storage, player, "telegram")

            self.assertIn("/profile?token=", link)


    def test_vk_profile_button_uses_short_lived_token_link(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            races = load_races("data/races.json")
            player = create_player(
                game_id=storage.generate_game_id(),
                platform=VK_PLATFORM,
                external_user_id="222",
                name="ВКСсылка",
                race_id="human",
                races=races,
            )
            storage.save_new_player(player, VK_PLATFORM, "222")

            sent_messages = []
            bot = object.__new__(VkRegistrationBot)
            bot.storage = storage
            bot.send = lambda peer_id, text, keyboard=None: sent_messages.append(text)

            bot.send_profile("222", 123)

            self.assertTrue(sent_messages)
            self.assertIn("/profile?token=", sent_messages[0])
            self.assertNotIn(player["public_id"], sent_messages[0])

    def test_starter_skills_are_level_zero_and_show_damage(self):
        player = self._new_player()
        skills = player["skills"]["active"]

        self.assertEqual(skills[0]["level"], 0)
        self.assertEqual(skills[1]["level"], 0)
        self.assertIn("уровня персонажа", skills[0]["description"])
        self.assertIn("уровень персонажа", skills[0]["damage"])
        self.assertIn("уровень персонажа", skills[1]["damage"])

        player["level"] = 10
        profile = frontend_profile(player)
        frontend_skills = profile["skills"]["active"]
        self.assertEqual(frontend_skills[0]["damage"], 20)
        self.assertEqual(frontend_skills[1]["damage"], 18)
        self.assertNotIn("base_damage_formula", frontend_skills[0])


    def test_attribute_points_can_be_confirmed_in_batch_through_private_profile_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["free_stat_points"] = 5
            player["invested_stats"] = {"strength": 0, "endurance": 0}
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/attributes/confirm",
                json={"allocations": {"strength": 2, "endurance": 3}},
            )

            self.assertEqual(response.status_code, 200, response.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["free_stat_points"], 0)
            self.assertEqual(restored["invested_stats"]["strength"], 2)
            self.assertEqual(restored["invested_stats"]["endurance"], 3)

    def test_attribute_batch_confirm_rejects_more_points_than_available(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["free_stat_points"] = 1
            player["invested_stats"] = {"strength": 0}
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/attributes/confirm",
                json={"allocations": {"strength": 2}},
            )

            self.assertEqual(response.status_code, 400)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["free_stat_points"], 1)
            self.assertEqual(restored["invested_stats"].get("strength"), 0)

    def test_skill_points_can_be_spent_through_private_profile_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["free_skill_points"] = 3
            player["skills"]["passive"].append(
                {
                    "id": "focus",
                    "name": "Фокус",
                    "level": 1,
                    "upgradeable": True,
                    "modifiers": [{"id": "clarity", "name": "Ясность", "level": 0}],
                }
            )
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/skills/spend",
                json={"skill_id": "focus", "modifier_id": "clarity", "amount": 2},
            )

            self.assertEqual(response.status_code, 200, response.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["free_skill_points"], 1)
            self.assertEqual(restored["skills"]["passive"][0]["level"], 3)
            self.assertEqual(restored["skills"]["passive"][0]["modifiers"][0]["level"], 2)

    def test_consumable_with_explicit_modifiers_adds_active_effect(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["inventory"] = [
                {
                    "id": "focus_food",
                    "name": "Питательная похлебка",
                    "category": "Еда",
                    "amount": 2,
                    "use_effect": {"stat_modifiers": {"bonus_max_energy": 20}},
                }
            ]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/inventory/use",
                json={"item_id": "focus_food"},
            )

            self.assertEqual(response.status_code, 200, response.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["inventory"][0]["amount"], 1)
            self.assertEqual(restored["active_effects"][0]["stat_modifiers"]["bonus_max_energy"], 20)
            values = {row["label"]: row["value"] for row in response.json()["profile"]["parameters"]}
            self.assertEqual(values["Энергия"], "100 / 120")


    def test_direct_use_rejects_non_consumable_without_spending_item(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["inventory"] = [{"id": "plain_stone", "name": "Обычный камень", "category": "Ресурсы", "amount": 3}]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/inventory/use",
                json={"item_id": "plain_stone"},
            )

            self.assertEqual(response.status_code, 400)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["inventory"][0]["amount"], 3)

    def test_market_sell_mode_adds_profile_sell_action_and_exit_removes_it(self):
        player = self._new_player()
        player["current_zone"] = "seldar_npc_market_sell"
        player["location_id"] = "seldar_npc_market_sell"
        player["market_context"] = {"mode": "sell_list"}
        player["inventory"] = [{"id": "clean_water", "name": "Чистая вода", "amount": 3, "can_sell": True, "sell_price_copper": 5}]

        profile = frontend_profile(player)
        water = next(item for item in profile["inventory"] if item["id"] == "clean_water")
        self.assertTrue(profile["market"]["sellFromProfile"])
        self.assertIn("Продать", water.get("actions", []))

        player["current_zone"] = "seldar_trade_district"
        player["location_id"] = "seldar_trade_district"
        player.pop("market_context", None)
        profile = frontend_profile(player)
        water = next(item for item in profile["inventory"] if item["id"] == "clean_water")
        self.assertFalse(profile["market"]["sellFromProfile"])
        self.assertNotIn("Продать", water.get("actions", []))

    def test_market_sell_endpoint_sells_profile_item_quantity(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["money"] = 100
            player["money_copper"] = 100
            player["current_zone"] = "seldar_npc_market_sell"
            player["location_id"] = "seldar_npc_market_sell"
            player["market_context"] = {"mode": "sell_list"}
            player["inventory"] = [{"id": "clean_water", "name": "Чистая вода", "amount": 3, "can_sell": True, "sell_price_copper": 5}]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/inventory/sell",
                json={"item_id": "clean_water", "amount": 2},
            )

            self.assertEqual(response.status_code, 200, response.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["money_copper"], 110)
            self.assertEqual(restored["inventory"][0]["amount"], 1)
            payload = response.json()
            self.assertIn("Продано: Чистая вода ×2", payload["message"])
            water = next(item for item in payload["profile"]["inventory"] if item["id"] == "clean_water")
            self.assertIn("Продать", water.get("actions", []))

    def test_market_sell_profile_action_is_per_stack_not_item_id(self):
        player = self._new_player()
        player["current_zone"] = "seldar_npc_market_sell"
        player["location_id"] = "seldar_npc_market_sell"
        player["market_context"] = {"mode": "sell_list"}
        player["inventory"] = [
            {"id": "clean_water", "item_id": "clean_water", "name": "Чистая вода", "amount": 1, "protected": True, "can_sell": True, "sell_price_copper": 5},
            {"id": "clean_water", "item_id": "clean_water", "name": "Чистая вода", "amount": 3, "can_sell": True, "sell_price_copper": 5},
        ]

        profile = frontend_profile(player)
        water_stacks = [item for item in profile["inventory"] if item["id"] == "clean_water"]

        self.assertEqual([item["inventoryIndex"] for item in water_stacks], [0, 1])
        self.assertNotIn("Продать", water_stacks[0].get("actions", []))
        self.assertFalse(water_stacks[0].get("marketSellAvailable", False))
        self.assertIn("Продать", water_stacks[1].get("actions", []))
        self.assertTrue(water_stacks[1].get("marketSellAvailable"))

    def test_market_sell_endpoint_rejects_protected_stack_index(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["money"] = 100
            player["money_copper"] = 100
            player["current_zone"] = "seldar_npc_market_sell"
            player["location_id"] = "seldar_npc_market_sell"
            player["market_context"] = {"mode": "sell_list"}
            player["inventory"] = [
                {"id": "clean_water", "item_id": "clean_water", "name": "Чистая вода", "amount": 1, "protected": True, "can_sell": True, "sell_price_copper": 5},
                {"id": "clean_water", "item_id": "clean_water", "name": "Чистая вода", "amount": 3, "can_sell": True, "sell_price_copper": 5},
            ]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/inventory/sell",
                json={"item_id": "clean_water", "amount": 1, "inventory_index": 0},
            )

            self.assertEqual(response.status_code, 400)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["money_copper"], 100)
            self.assertEqual([item["amount"] for item in restored["inventory"]], [1, 3])

    def test_market_sell_endpoint_sells_selected_stack_index_only(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["money"] = 100
            player["money_copper"] = 100
            player["race_id"] = "elf"
            player["current_zone"] = "seldar_npc_market_sell"
            player["location_id"] = "seldar_npc_market_sell"
            player["market_context"] = {"mode": "sell_list"}
            player["inventory"] = [
                {"id": "clean_water", "item_id": "clean_water", "name": "Чистая вода", "amount": 2, "can_sell": True, "sell_price_copper": 2},
                {"id": "clean_water", "item_id": "clean_water", "name": "Чистая вода", "amount": 4, "can_sell": True, "sell_price_copper": 5},
            ]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/inventory/sell",
                json={"item_id": "clean_water", "amount": 3, "inventory_index": 1},
            )

            self.assertEqual(response.status_code, 200, response.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["money_copper"], 115)
            self.assertEqual(sum(item["amount"] for item in restored["inventory"]), 3)

    def test_market_sell_endpoint_rejects_outside_market_sell_mode(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["inventory"] = [{"id": "clean_water", "name": "Чистая вода", "amount": 3, "can_sell": True, "sell_price_copper": 5}]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/inventory/sell",
                json={"item_id": "clean_water", "amount": 1},
            )

            self.assertEqual(response.status_code, 400)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["inventory"][0]["amount"], 3)

    def test_consumable_category_items_remain_directly_usable(self):
        self.assertTrue(is_inventory_item_usable({"id": "legacy_consumable", "name": "Старый расходник", "category": "Расходники"}))

    def test_direct_use_false_hides_profile_use_action(self):
        player = self._new_player()
        item_ids = ["mining_pickaxe", "woodcutters_axe"]
        player["inventory"] = [
            registry_item_to_inventory_item(get_item_definition_by_id(item_id), 1)
            for item_id in item_ids
        ]

        profile = frontend_profile(player)
        actions_by_id = {item["id"]: item.get("actions", []) for item in profile["inventory"]}

        for item_id in item_ids:
            self.assertNotIn("Использовать", actions_by_id[item_id])
            self.assertFalse(is_inventory_item_usable(player["inventory"][item_ids.index(item_id)]))

    def test_alchemy_ingredients_are_not_direct_profile_use_items(self):
        player = self._new_player()
        ingredient_ids = [
            "meadow_mint",
            "meadow_root",
            "mountain_wormwood",
            "silver_chamomile",
            "yellow_clover",
        ]
        player["inventory"] = [
            registry_item_to_inventory_item(get_item_definition_by_id(item_id), 1)
            for item_id in ingredient_ids
        ]

        profile = frontend_profile(player)
        actions_by_id = {item["id"]: item.get("actions", []) for item in profile["inventory"]}

        for item_id in ingredient_ids:
            self.assertNotIn("Использовать", actions_by_id[item_id])
            self.assertFalse(is_inventory_item_usable(player["inventory"][ingredient_ids.index(item_id)]))

    def test_forest_equipment_is_equippable_not_directly_usable(self):
        player = self._new_player()
        equipment_ids = ["old_gloves", "decent_belt"]
        player["inventory"] = [
            registry_item_to_inventory_item(get_item_definition_by_id(item_id), 1)
            for item_id in equipment_ids
        ]

        profile = frontend_profile(player)
        actions_by_id = {item["id"]: item.get("actions", []) for item in profile["inventory"]}

        for item_id in equipment_ids:
            self.assertIn("Надеть", actions_by_id[item_id])
            self.assertNotIn("Использовать", actions_by_id[item_id])
            self.assertFalse(is_inventory_item_usable(player["inventory"][equipment_ids.index(item_id)]))

    def test_energy_bonus_does_not_stack_into_saved_max_energy_when_food_used_twice(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["energy"] = 50
            player["current_energy"] = 50
            player["max_energy"] = 100
            player["equipment"] = {"ring1": {"stat_modifiers": {"bonus_max_energy": 20}}}
            player["inventory"] = [{"id": "food", "name": "Еда", "category": "Еда", "amount": 2, "energy_restore": 10}]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)
            first = client.post(f"/api/profile/{token}/inventory/use", json={"item_id": "food"})
            second = client.post(f"/api/profile/{token}/inventory/use", json={"item_id": "food"})

            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(second.status_code, 200, second.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["max_energy"], 100)
            values = {row["label"]: row["value"] for row in second.json()["profile"]["parameters"]}
            self.assertEqual(values["Энергия"], "70 / 120")

    def test_profile_inventory_categories_split_consumables_resources_and_mob_loot(self):
        player = self._new_player()
        player["inventory"] = [
            {"id": "tea", "name": "Травяной чай", "category": "Еда", "amount": 1, "energy_restore": 20},
            {"id": "ore", "name": "Кусок медной руды", "category": "resources", "subtype": "ore", "amount": 1},
            {"id": "fang", "name": "Клык шакала", "category": "Трофеи", "source": "mob", "amount": 1},
        ]

        profile = frontend_profile(player)
        categories = {item["name"]: item["category"] for item in profile["inventory"]}

        self.assertEqual(categories["Травяной чай"], "Расходники")
        self.assertEqual(categories["Кусок медной руды"], "Ресурсы")
        self.assertEqual(categories["Клык шакала"], "Добыча")


    def test_skills_can_be_equipped_and_unequipped_through_private_profile_token(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)

            equip_response = client.post(
                f"/api/profile/{token}/skills/equip",
                json={"skill_id": "basic_attack"},
            )
            self.assertEqual(equip_response.status_code, 200, equip_response.text)
            equipped_names = [skill["id"] for skill in equip_response.json()["profile"]["skills"]["equipped"]]
            active_names = [skill["id"] for skill in equip_response.json()["profile"]["skills"]["active"]]
            self.assertIn("basic_attack", equipped_names)
            self.assertNotIn("basic_attack", active_names)

            unequip_response = client.post(
                f"/api/profile/{token}/skills/unequip",
                json={"skill_id": "basic_attack"},
            )
            self.assertEqual(unequip_response.status_code, 200, unequip_response.text)
            equipped_names = [skill["id"] for skill in unequip_response.json()["profile"]["skills"]["equipped"]]
            active_names = [skill["id"] for skill in unequip_response.json()["profile"]["skills"]["active"]]
            self.assertNotIn("basic_attack", equipped_names)
            self.assertIn("basic_attack", active_names)

    def test_passive_skills_without_explicit_type_are_not_equippable(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["skills"]["passive"].append({"id": "focus", "name": "Фокус", "level": 1})
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)

            profile_response = client.get(f"/api/profile/{token}")
            self.assertEqual(profile_response.status_code, 200, profile_response.text)
            passive_skill = next(skill for skill in profile_response.json()["skills"]["passive"] if skill["id"] == "focus")
            self.assertFalse(passive_skill["equippable"])

            equip_response = client.post(
                f"/api/profile/{token}/skills/equip",
                json={"skill_id": "focus"},
            )
            self.assertEqual(equip_response.status_code, 400)

    def test_skill_points_cannot_be_spent_through_public_profile_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["free_skill_points"] = 1
            player["skills"]["passive"].append(
                {"id": "focus", "name": "Фокус", "level": 1, "upgradeable": True}
            )
            storage.save_new_player(player, "telegram", "111")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{player['public_id']}/skills/spend",
                json={"skill_id": "focus", "modifier_id": "main", "amount": 1},
            )

            self.assertEqual(response.status_code, 401)

    def test_two_handed_weapon_blocks_second_weapon_slot_in_profile(self):
        player = self._new_player()

        profile = frontend_profile(player)
        slot_by_key = {slot["key"]: slot for slot in profile["equipmentSlots"]}

        self.assertTrue(slot_by_key["weapon2"].get("blocked"))
        self.assertIn("заблокирован", slot_by_key["weapon2"].get("blockedReason", ""))

    def test_api_rejects_weapon2_when_two_handed_weapon_is_equipped(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["inventory"].append(
                {
                    "id": "training_dagger",
                    "name": "Учебный кинжал",
                    "category": "Оружие",
                    "type": "Оружие",
                    "subtype": "Кинжал",
                    "slot": "weapon",
                    "amount": 1,
                }
            )
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/equipment/equip",
                json={"item_id": "training_dagger", "slot_key": "weapon2"},
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn("заблокирован", response.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertIn("starter_wooden_staff", restored["equipment"]["weapon1"]["id"])
            self.assertTrue(any(item.get("id") == "training_dagger" for item in restored["inventory"]))

    def test_equipping_two_handed_weapon_moves_second_weapon_to_inventory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["equipment"] = {
                "weapon1": {"id": "iron_sword", "name": "Железный меч", "category": "Оружие", "type": "Оружие", "subtype": "Меч", "slotKey": "weapon1", "amount": 1},
                "weapon2": {"id": "old_shield", "name": "Старый щит", "category": "Оружие", "type": "Оружие", "subtype": "Щит", "slotKey": "weapon2", "amount": 1},
            }
            player["inventory"] = [
                {
                    "id": "forest_staff",
                    "name": "Лесной двуручный посох",
                    "category": "Оружие",
                    "type": "Оружие",
                    "subtype": "Посох",
                    "slot": "weapon",
                    "combat": {"two_handed": True},
                    "amount": 1,
                }
            ]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")

            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            response = TestClient(app).post(
                f"/api/profile/{token}/equipment/equip",
                json={"item_id": "forest_staff", "slot_key": "weapon1"},
            )

            self.assertEqual(response.status_code, 200, response.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(restored["equipment"]["weapon1"]["id"], "forest_staff")
            self.assertNotIn("weapon2", restored["equipment"])
            self.assertTrue(any(item.get("id") == "old_shield" and item.get("targetSlotKey") == "weapon2" for item in restored["inventory"]))
            profile = response.json()["profile"]
            slot_by_key = {slot["key"]: slot for slot in profile["equipmentSlots"]}
            self.assertTrue(slot_by_key["weapon2"].get("blocked"))


if __name__ == "__main__":
    unittest.main()

class PromoAndEffectFixesTest(unittest.TestCase):
    def _new_player(self):
        races = load_races("data/races.json")
        return create_player(
            game_id="NT-PROMOFIX",
            platform="telegram",
            external_user_id="111",
            name="Промо",
            race_id="human",
            races=races,
        )

    def test_consumable_buff_refreshes_instead_of_stacking_forever(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
            player = self._new_player()
            player["inventory"] = [
                {
                    "id": "focus_food",
                    "name": "Пища концентрации",
                    "category": "Еда",
                    "amount": 2,
                    "use_effect": {"stat_modifiers": {"bonus_accuracy": 10}, "duration_seconds": 60},
                }
            ]
            storage.save_new_player(player, "telegram", "111")
            token = storage.create_site_session(player["game_id"], PROFILE_SCOPE, "telegram")
            app = FastAPI()
            app.include_router(create_profile_api_router(lambda: storage))
            client = TestClient(app)
            base_values = {row["label"]: row["value"] for row in client.get(f"/api/profile/{token}").json()["parameters"]}

            first = client.post(f"/api/profile/{token}/inventory/use", json={"item_id": "focus_food"})
            second = client.post(f"/api/profile/{token}/inventory/use", json={"item_id": "focus_food"})

            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(second.status_code, 200, second.text)
            restored = storage.get_player_by_game_id(player["game_id"])
            self.assertEqual(len(restored.get("active_effects", [])), 1)
            self.assertIn("expires_at", restored["active_effects"][0])
            values = {row["label"]: row["value"] for row in second.json()["profile"]["parameters"]}
            self.assertEqual(int(values["Точность"]), int(base_values["Точность"]) + 10)

    def test_promo_rewards_update_canonical_money_and_energy_fields(self):
        import os
        from datetime import datetime, timedelta, timezone
        from services.promo_service import add_promo_code, redeem_promo_code

        with tempfile.TemporaryDirectory() as tmp_dir:
            promo_path = Path(tmp_dir) / "promo.json"
            old_path = os.environ.get("PROMO_CODES_PATH")
            os.environ["PROMO_CODES_PATH"] = str(promo_path)
            try:
                storage = JsonStorage(str(Path(tmp_dir) / "players.json"))
                player = self._new_player()
                player["money"] = 10
                player["money_copper"] = 10
                player["energy"] = 20
                player["current_energy"] = 20
                player["max_energy"] = 100
                storage.save_new_player(player, "telegram", "111")
                add_promo_code(
                    code="SYNC100",
                    uses_left=1,
                    reward={"money": 50, "energy": 30},
                    expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None).isoformat(),
                )

                ok, message = redeem_promo_code(storage, player["game_id"], "SYNC100")

                self.assertTrue(ok, message)
                restored = storage.get_player_by_game_id(player["game_id"])
                self.assertEqual(restored["money"], 60)
                self.assertEqual(restored["money_copper"], 60)
                self.assertEqual(restored["energy"], 50)
                self.assertEqual(restored["current_energy"], 50)
            finally:
                if old_path is None:
                    os.environ.pop("PROMO_CODES_PATH", None)
                else:
                    os.environ["PROMO_CODES_PATH"] = old_path
