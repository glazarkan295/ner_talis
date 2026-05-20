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
from services.web_profile import PROFILE_SCOPE, create_profile_site_link
from site_api import create_profile_api_router, equipment_modifier_totals, frontend_profile
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
        skill = next(skill for skill in profile["skills"]["active"] if skill["id"] == "legacy_focus")

        self.assertEqual(skill["resourceText"], "Расход: Мана: 2")
        self.assertNotIn("concentration_cost", skill)

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

        self.assertEqual(skills["basic_attack"]["damage"], 22)
        self.assertEqual(skills["magic_spark"]["damage"], 21)

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
        self.assertEqual(frontend_skills[0]["damage"], 17)
        self.assertEqual(frontend_skills[1]["damage"], 15)
        self.assertNotIn("base_damage_formula", frontend_skills[0])

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


if __name__ == "__main__":
    unittest.main()
