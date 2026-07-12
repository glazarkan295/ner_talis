import os
import random
import tempfile
import unittest
from pathlib import Path

from services import camp_constructor_service as camps
from services import camp_runtime


class CampRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved = os.environ.get("CAMP_CONSTRUCTOR_PATH")
        self.saved_world = os.environ.get("WORLD_CONTENT_PATH")
        self.saved_effects = os.environ.get("EFFECT_CONSTRUCTOR_PATH")
        os.environ["CAMP_CONSTRUCTOR_PATH"] = str(Path(self.tmp.name) / "camps.json")
        os.environ["WORLD_CONTENT_PATH"] = str(Path(self.tmp.name) / "world.json")
        os.environ["EFFECT_CONSTRUCTOR_PATH"] = str(Path(self.tmp.name) / "effects.json")
        self.addCleanup(self.restore)

    def restore(self):
        if self.saved is None:
            os.environ.pop("CAMP_CONSTRUCTOR_PATH", None)
        else:
            os.environ["CAMP_CONSTRUCTOR_PATH"] = self.saved
        if self.saved_world is None:
            os.environ.pop("WORLD_CONTENT_PATH", None)
        else:
            os.environ["WORLD_CONTENT_PATH"] = self.saved_world
        if self.saved_effects is None:
            os.environ.pop("EFFECT_CONSTRUCTOR_PATH", None)
        else:
            os.environ["EFFECT_CONSTRUCTOR_PATH"] = self.saved_effects

    def publish(self, camp_id, data):
        camps.store().create(camp_id, data)
        camps.store().set_status(camp_id, camps.STATUS_PUBLISHED, force=True)

    def test_selects_published_priority_camp_for_location(self):
        self.publish("low", {"name": "Низкий", "camp_type": "standard", "locations": ["forest"], "priority": 1})
        self.publish("death", {
            "name": "Возрождение", "camp_type": "safe", "locations": ["forest"],
            "priority": 5, "death_camp": True, "return_after_death": True,
        })
        self.assertEqual(camp_runtime.published_for_location("forest")["id"], "death")
        self.assertEqual(camp_runtime.death_camp("forest")["id"], "death")

    def test_rest_time_and_configured_recovery(self):
        camp = {
            "base_time": 30, "low_energy_time": 120, "zero_energy_time": 600,
            "min_time": 10, "max_time": 600,
            "recovery": [
                {"target": "hp", "percent": 50},
                {"target": "mana", "flat": 15, "max": 10},
                {"target": "energy", "full": True},
            ],
        }
        player = {"energy": 0, "max_energy": 100, "hp": 20, "max_hp": 100, "mana": 5, "max_mana": 50}
        self.assertEqual(camp_runtime.rest_seconds(player, camp, 30), 600)
        deltas = camp_runtime.apply_recovery(player, camp)
        self.assertEqual(player["hp"], 70)
        self.assertEqual(player["mana"], 15)
        self.assertEqual(player["energy"], 100)
        self.assertEqual(deltas, {"hp": 50, "mana": 10, "energy": 100})

    def test_unpublished_camp_never_enters_runtime(self):
        camps.store().create("draft", {"name": "Черновик", "locations": ["forest"]})
        self.assertIsNone(camp_runtime.published_for_location("forest"))

    def test_published_world_button_opens_specific_published_camp(self):
        from services import world_content_registry as world
        from services.external_location_service import handle_external_location_action, location_buttons

        self.publish("forest_refuge", {
            "name": "Убежище", "camp_type": "safe", "locations": ["ordinary_forest"],
            "can_rest": True, "base_time": 45, "min_time": 1, "max_time": 600,
            "entry_text": "Добро пожаловать в убежище", "recovery": [{"target": "hp", "flat": 10}],
        })
        world.create_content("button", "open_refuge", {
            "text": "В убежище", "owner_location": "ordinary_forest",
            "action": "open_camp", "target": "forest_refuge", "show_telegram": True, "show_vk": True,
        })
        world.set_status("button", "open_refuge", world.STATUS_PUBLISHED, force=True)

        self.assertIn(["В убежище"], location_buttons("ordinary_forest"))
        player = {
            "game_id": "p1", "current_location": "ordinary_forest",
            "current_zone": "ordinary_forest", "location_id": "ordinary_forest",
            "energy": 100, "max_energy": 100, "hp": 50, "max_hp": 100,
            "inventory": [],
        }

        class Storage:
            def update_player(self, _player):
                return None

        response = handle_external_location_action(Storage(), player, "В убежище")
        self.assertEqual(player["current_camp_id"], "forest_refuge")
        self.assertEqual(player["active_timer"]["camp_id"], "forest_refuge")
        self.assertIn("Добро пожаловать", response.text)

    def test_weekly_rest_limit_effect_and_event_execute(self):
        from services import effect_constructor_service as effects
        from services import world_content_registry as world

        effects.store().create("camp_blessing", {
            "name": "Благословение лагеря", "effect_type": "buff", "duration_seconds": 60,
        })
        effects.store().set_status("camp_blessing", effects.STATUS_PUBLISHED, force=True)
        world.create_content("event", "camp_story", {
            "name": "История", "text": "У костра рассказали древнюю историю.",
            "location": "forest", "chance": 100,
        })
        world.set_status("event", "camp_story", world.STATUS_PUBLISHED, force=True)
        camp = {
            "id": "refuge", "effect_links": [{"effect_id": "camp_blessing", "trigger": "on_rest"}],
            "camp_events": [{"event_id": "camp_story", "trigger": "on_rest", "chance": 100}],
            "weekly_limits": [{"id": "rest_once", "limit_type": "rest", "max_per_week": 1, "exhausted_text": "Отдых исчерпан"}],
        }
        player = {"active_effects": []}
        self.assertIsNone(camp_runtime.rest_limit_error(player, camp))
        camp_runtime.consume_rest_limit(player, camp)
        self.assertEqual(camp_runtime.rest_limit_error(player, camp), "Отдых исчерпан")
        applied = camp_runtime.apply_effects(player, camp, "on_rest", rng=random.Random(1))
        self.assertEqual(applied[0]["effect_id"], "camp_blessing")
        self.assertEqual(camp_runtime.roll_events(camp, "on_rest", rng=random.Random(1)), ["У костра рассказали древнюю историю."])

    def test_paid_rest_consumes_configured_money_and_item_atomically(self):
        camp = {
            "rest_price": 2, "rest_currency": "silver",
            "rest_item_id": "bedroll", "rest_item_amount": 2, "consume_rest_item": True,
            "missing_item_text": "Нужны спальники", "not_enough_money_text": "Нужно серебро",
        }
        insufficient = {"money_copper": 100, "inventory": [{"item_id": "bedroll", "amount": 2}]}
        self.assertEqual(camp_runtime.prepare_rest_payment(insufficient, camp), "Нужно серебро")
        self.assertEqual(insufficient["money_copper"], 100)
        self.assertEqual(insufficient["inventory"][0]["amount"], 2)

        player = {"money_copper": 500, "money": 500, "inventory": [{"item_id": "bedroll", "amount": 3}]}
        self.assertIsNone(camp_runtime.prepare_rest_payment(player, camp))
        self.assertEqual(player["money_copper"], 300)
        self.assertEqual(player["money"], 300)
        self.assertEqual(player["inventory"][0]["amount"], 1)

    def test_configured_service_button_charges_and_restores_resource(self):
        camp = {"id": "refuge", "services": [{
            "service_id": "healer", "name": "Лечение", "service_type": "healing",
            "cost": 25, "currency": "copper", "percent": 50,
            "success_text": "Лекарь перевязал раны.", "active": True,
        }]}
        player = {"money_copper": 100, "hp": 10, "max_hp": 100, "inventory": []}
        self.assertEqual(camp_runtime.service_buttons(camp), ["Лечение"])
        handled, text = camp_runtime.use_service(player, camp, "Лечение")
        self.assertTrue(handled)
        self.assertEqual(text, "Лекарь перевязал раны.")
        self.assertEqual(player["money_copper"], 75)
        self.assertEqual(player["hp"], 60)

    def test_access_conditions_cover_level_race_item_and_unlock(self):
        player = {"level": 5, "race_id": "elf", "inventory": [{"item_id": "pass", "amount": 2}], "unlocks": ["camp_known"]}
        camp = {"access_conditions": [
            {"type": "level", "operator": "gte", "value": 5},
            {"type": "race", "operator": "eq", "value": "elf"},
            {"type": "item", "object_id": "pass", "operator": "gte", "value": 2},
            {"type": "unlock", "object_id": "camp_known", "operator": "eq", "value": True},
        ]}
        self.assertIsNone(camp_runtime.access_error(player, camp))
        camp["access_conditions"][0]["value"] = 6
        camp["access_conditions"][0]["error_text"] = "Нужен шестой уровень."
        self.assertEqual(camp_runtime.access_error(player, camp), "Нужен шестой уровень.")

    def test_service_weekly_limit_blocks_before_payment(self):
        camp = {"id": "refuge", "services": [{
            "service_id": "healer", "name": "Лечение", "service_type": "healing", "cost": 25, "percent": 50,
        }], "weekly_limits": [{
            "id": "healer_once", "limit_type": "service", "object_id": "healer", "max_per_week": 1, "exhausted_text": "Лекарь уже помог.",
        }]}
        player = {"money_copper": 100, "hp": 10, "max_hp": 100, "inventory": []}
        self.assertTrue(camp_runtime.use_service(player, camp, "Лечение")[0])
        self.assertEqual(player["money_copper"], 75)
        handled, text = camp_runtime.use_service(player, camp, "Лечение")
        self.assertTrue(handled)
        self.assertEqual(text, "Лекарь уже помог.")
        self.assertEqual(player["money_copper"], 75)

    def test_published_camp_npc_is_visible_and_dialogue_opens(self):
        from services import world_content_registry as world
        from services.external_location_service import camp_buttons, handle_external_location_action

        world.create_content("npc", "healer_npc", {"name": "Лекарь", "first_message": "Раны нужно перевязать."})
        world.set_status("npc", "healer_npc", world.STATUS_PUBLISHED, force=True)
        self.publish("refuge", {"name": "Убежище", "locations": ["ordinary_forest"], "npc_ids": ["healer_npc"]})
        player = {"game_id": "p", "current_camp_id": "refuge", "current_zone": "ordinary_forest_camp", "location_id": "ordinary_forest_camp"}

        class Storage:
            def update_player(self, _player):
                return None

        label = "Поговорить: Лекарь"
        self.assertIn([label], camp_buttons(player))
        response = handle_external_location_action(Storage(), player, label)
        self.assertIn("Раны нужно перевязать", response.text)
        self.assertEqual(player["constructor_npc_id"], "healer_npc")
        response = handle_external_location_action(Storage(), player, "Завершить разговор")
        self.assertNotIn("constructor_npc_id", player)
        self.assertIn("лагер", response.text.lower())

    def test_rest_reward_item_role_is_issued(self):
        from services.item_registry import get_item_definition_by_id
        item_id = next(item for item in ("simple_sword", "healing_herb", "old_iron_sword") if get_item_definition_by_id(item))
        player = {"inventory": [], "inventory_capacity": 10, "inventory_overflow_capacity": 5}
        rows = camp_runtime.grant_rest_items(player, {"id": "refuge", "name": "Убежище", "items": [
            {"item_id": item_id, "role": "rest_reward", "amount": 1, "active": True},
        ]})
        self.assertEqual(rows[0]["added"], 1)
        self.assertTrue(any(str(row.get("item_id") or row.get("id")) == item_id for row in player["inventory"]))

    def test_rare_item_roles_effect_protection_event_limit_and_conditional_npc(self):
        from services import world_content_registry as world
        world.create_content("event","camp_once",{"name":"Разовый рассказ","text":"История у костра"});world.set_status("event","camp_once",world.STATUS_PUBLISHED,force=True)
        world.create_content("npc","camp_guide",{"name":"Проводник","dialogues":[{"id":"d","text":"Путь здесь."}]});world.set_status("npc","camp_guide",world.STATUS_PUBLISHED,force=True)
        camp={"id":"rare","missing_item_text":"Нужен пропуск","items":[{"item_id":"pass","role":"entry_required","amount":1},{"item_id":"food","role":"food","amount":2,"consumed":True}],"camp_events":[{"event_id":"camp_once","trigger":"on_rest","chance":100}],"weekly_limits":[{"id":"event_once","limit_type":"camp_event","object_id":"camp_once","max_per_week":1}],"camp_npcs":[{"npc_id":"camp_guide","appear_condition":"guide_open"}]}
        player={"game_id":"P","inventory":[],"unlocks":{}}
        self.assertEqual(camp_runtime.access_error(player,camp),"Нужен пропуск")
        player["inventory"]=[{"item_id":"pass","amount":1},{"item_id":"food","amount":2}];self.assertIsNone(camp_runtime.access_error(player,camp));self.assertIsNone(camp_runtime.prepare_rest_payment(player,camp));self.assertFalse(any(row.get("item_id")=="food" for row in player["inventory"]))
        self.assertEqual(camp_runtime.roll_events(camp,"on_rest",player=player,rng=random.Random(1)),["История у костра"]);self.assertEqual(camp_runtime.roll_events(camp,"on_rest",player=player,rng=random.Random(1)),[])
        self.assertEqual(camp_runtime.npc_rows(camp,player),[]);player["unlocks"]["guide_open"]=True;self.assertEqual(camp_runtime.npc_rows(camp,player)[0]["id"],"camp_guide")

    def test_special_service_routes_to_shared_runtime_after_atomic_payment(self):
        camp = {"id": "refuge", "services": [{
            "service_id": "trader", "name": "Торговец", "service_type": "trade",
            "cost": 10, "currency": "copper", "target_action": "Рынок", "success_text": "Торговец открыл прилавок.",
        }], "weekly_limits": [{"id": "trade_once", "limit_type": "service", "object_id": "trader", "max_per_week": 1, "exhausted_text": "Торговец закрылся."}]}
        player = {"money_copper": 25, "inventory": []}
        handled, action, text = camp_runtime.prepare_service_route(player, camp, "Торговец")
        self.assertTrue(handled)
        self.assertEqual(action, "Рынок")
        self.assertEqual(text, "Торговец открыл прилавок.")
        self.assertEqual(player["money_copper"], 15)
        handled, action, text = camp_runtime.prepare_service_route(player, camp, "Торговец")
        self.assertTrue(handled)
        self.assertIsNone(action)
        self.assertEqual(text, "Торговец закрылся.")
        self.assertEqual(player["money_copper"], 15)

    def test_camp_trade_service_opens_real_market_flow(self):
        from services.external_location_service import handle_external_location_action
        self.publish("refuge", {"name": "Убежище", "locations": ["ordinary_forest"], "services": [{
            "service_id": "trader", "name": "Торговец лагеря", "service_type": "trade", "cost": 0,
        }]})
        player = {"game_id": "p", "level": 1, "current_camp_id": "refuge", "current_zone": "ordinary_forest_camp", "location_id": "ordinary_forest_camp", "inventory": [], "money": 0}

        class Storage:
            def update_player(self, _player):
                return None

        response = handle_external_location_action(Storage(), player, "Торговец лагеря")
        self.assertIn("Рынок", response.text)
        self.assertTrue(any("Купить" in row for row in response.buttons))

    def test_camp_craft_and_fine_services_route_to_real_flows(self):
        from services.external_location_service import handle_external_location_action
        self.publish("refuge", {"name": "Убежище", "locations": ["ordinary_forest"], "services": [
            {"service_id": "smith", "name": "Ремесленник лагеря", "service_type": "craft", "cost": 0},
            {"service_id": "fines", "name": "Управляющий штрафами", "service_type": "pay_fines", "cost": 0},
        ]})
        player = {"game_id": "p", "level": 1, "current_camp_id": "refuge", "current_zone": "ordinary_forest_camp", "location_id": "ordinary_forest_camp", "inventory": [], "money": 0, "fines": []}

        class Storage:
            def update_player(self, _player):
                return None

        craft = handle_external_location_action(Storage(), player, "Ремесленник лагеря")
        self.assertIn("Ремесленный квартал", craft.text)
        player["current_camp_id"] = "refuge"
        player["current_zone"] = "ordinary_forest_camp"
        player["location_id"] = "ordinary_forest_camp"
        fines = handle_external_location_action(Storage(), player, "Управляющий штрафами")
        self.assertIn("штраф", fines.text.lower())


if __name__ == "__main__":
    unittest.main()
