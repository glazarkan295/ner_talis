import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import world_content_registry as registry
from services import world_runtime as rt


class WorldRuntimeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("WORLD_CONTENT_PATH")
        os.environ["WORLD_CONTENT_PATH"] = str(Path(self._tmp.name) / "world.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("WORLD_CONTENT_PATH", None)
        else:
            os.environ["WORLD_CONTENT_PATH"] = self._saved

    def _publish(self, kind, cid, data):
        registry.create_content(kind, cid, data)
        registry.set_status(kind, cid, registry.STATUS_PUBLISHED, force=True)

    def test_only_published_content_is_served(self):
        self._publish("location", "hub", {"name": "Узел", "type": "wild", "description": "Перекрёсток"})
        # A draft button must NOT appear in runtime.
        registry.create_content("button", "draft_btn", {"text": "Черновик", "owner_location": "hub", "action": "show_message", "show_telegram": True})
        self._publish("button", "go_tg", {"text": "В путь", "owner_location": "hub", "action": "go_back", "order": 1, "show_telegram": True, "show_vk": False})
        self._publish("button", "go_vk", {"text": "VK кнопка", "owner_location": "hub", "action": "go_back", "order": 2, "show_telegram": False, "show_vk": True})

        scene = rt.location_scene("hub", platform="telegram")
        self.assertEqual(scene["title"], "Узел")
        self.assertIn("В путь", scene["buttons"])
        self.assertNotIn("VK кнопка", scene["buttons"])  # platform filter
        self.assertNotIn("Черновик", scene["buttons"])  # draft excluded

        # Unpublished location -> None.
        registry.create_content("location", "secret", {"name": "Тайна", "type": "wild", "description": "x"})
        self.assertIsNone(rt.location("secret"))

    def test_roll_drop_is_deterministic_with_seed_and_respects_flags(self):
        self._publish("mob", "wolf", {
            "name": "Волк", "type": "beast", "hp": 50,
            "drop": [
                {"item_id": "money_copper", "chance": 100, "min_count": 5, "max_count": 5},
                {"item_id": "rare_fang", "chance": 0.0001, "min_count": 1, "max_count": 1},
                {"item_id": "event_token", "chance": 100, "min_count": 1, "max_count": 1, "only_event": True},
            ],
        })
        drops = rt.roll_drop("wolf", rng=random.Random(1))
        ids = {d["item_id"] for d in drops}
        self.assertIn("money_copper", ids)   # 100% always
        self.assertNotIn("rare_fang", ids)   # ~0% basically never
        self.assertNotIn("event_token", ids)  # event-only, not an event run
        # Event run includes the event-only drop.
        event_drops = {d["item_id"] for d in rt.roll_drop("wolf", rng=random.Random(1), event=True)}
        self.assertIn("event_token", event_drops)

    def test_mobs_in_location(self):
        self._publish("mob", "bat", {"name": "Мышь", "type": "beast", "hp": 10, "locations": "cave, hub"})
        self.assertTrue(any(m["id"] == "bat" for m in rt.mobs_in_location("cave")))
        self.assertFalse(rt.mobs_in_location("nowhere"))

    def test_published_locations_enter_and_transition_in_bot_flow(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "moon_road", {"name": "Лунная дорога", "type": "wild", "description": "Серебристая тропа."})
        self._publish("location", "old_tower", {"name": "Старая башня", "type": "story", "description": "Башня у горизонта."})
        self._publish("transition", "road_to_tower", {
            "name": "К башне", "from_location": "moon_road", "to_location": "old_tower",
        })

        from services.city_service import process_world_action

        class Storage:
            def update_player(self, _player):
                return None

        player = {
            "game_id": "NT-WORLD", "level": 1, "inventory": [], "equipment": {},
            "current_city": "seldar", "current_zone": "central_square",
            "location_id": "central_square", "current_location": "",
        }
        entered = process_world_action(Storage(), player, "Лунная дорога", "telegram")
        self.assertIn("Серебристая тропа", entered.text)
        self.assertIn(["К башне"], entered.buttons)
        self.assertEqual(player["constructor_location_id"], "moon_road")

        moved = process_world_action(Storage(), player, "К башне", "vk")
        self.assertIn("Башня у горизонта", moved.text)
        self.assertEqual(player["constructor_location_id"], "old_tower")

    def test_published_sublocation_opens_and_navigates_by_button(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "forest", {"name": "Лес", "type": "wild", "description": "Тёмный лес."})
        self._publish("sublocation", "old_cave", {
            "name": "Старая пещера", "type": "cave", "parent_location": "forest",
            "description": "Вход в пещеру.", "can_leave": True,
        })
        self._publish("sublocation_node", "cave_entry", {
            "name": "Вход", "player_text": "Вы у входа.", "node_type": "entry", "sublocation_id": "old_cave",
        })
        self._publish("sublocation_node", "cave_hall", {
            "name": "Зал", "player_text": "Вы в каменном зале.", "node_type": "hall", "sublocation_id": "old_cave",
        })
        self._publish("sublocation_transition", "into_hall", {
            "sublocation_id": "old_cave", "from_node": "cave_entry", "to_node": "cave_hall", "button_text": "В глубину",
        })
        self._publish("button", "open_cave", {
            "text": "В пещеру", "owner_location": "forest", "action": "open_sublocation",
            "target": "old_cave", "show_telegram": True, "show_vk": True,
        })
        self._publish("button", "inspect_cave", {
            "text": "Осмотреть стены", "owner_sublocation": "old_cave", "action": "show_message",
            "message": "На стенах древние руны.", "show_telegram": True, "show_vk": True,
        })

        from services.city_service import process_world_action

        class Storage:
            def update_player(self, _player):
                return None

        player = {"game_id": "NT-SUB", "level": 3, "energy": 10, "inventory": [], "equipment": {}}
        process_world_action(Storage(), player, "Лес", "telegram")
        entered = process_world_action(Storage(), player, "В пещеру", "telegram")
        self.assertIn("Вы у входа", entered.text)
        self.assertIn(["Осмотреть стены"], entered.buttons)
        self.assertEqual(player["constructor_sublocation_id"], "old_cave")
        inspected = process_world_action(Storage(), player, "Осмотреть стены", "telegram")
        self.assertIn("древние руны", inspected.text)
        moved = process_world_action(Storage(), player, "В глубину", "vk")
        self.assertIn("каменном зале", moved.text)
        self.assertEqual(player["constructor_sublocation_node_id"], "cave_hall")

    def test_sublocation_authored_access_services_refs_and_texts_are_live(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"]="1";self.addCleanup(lambda:os.environ.pop("WORLD_CONSTRUCTOR_LIVE",None))
        self._publish("location","harbor",{"name":"Порт","type":"port","description":"Порт"})
        self._publish("event","dock_event",{"name":"Чайка","text":"Чайка принесла письмо.","location_id":"harbor"})
        self._publish("npc","dockmaster",{"name":"Начальник порта","dialogue":[{"id":"start","text":"Добро пожаловать."}]})
        self._publish("sublocation","dock",{"name":"Пристань","player_name":"Пристань","type":"market","parent_location":"harbor","description":"Причалы","entry_text":"Вы вышли на пристань.","exit_text":"Вы вернулись в порт.","denied_text":"Страж не пропускает.","min_level":3,"required_item":"dock_pass","npc_ids":["dockmaster"],"event_ids":["dock_event"],"service_types":["port_market","delivery"],"can_leave":True})
        self._publish("sublocation_node","dock_entry",{"name":"Вход","node_type":"entry","sublocation_id":"dock"})
        denied=rt.render_sublocation("dock",player={"level":2,"inventory":[]},platform="telegram")
        self.assertEqual(denied["kind"],"sublocation_denied");self.assertIn("не пропускает",denied["text"])
        player={"level":3,"inventory":[{"item_id":"dock_pass"}],"constructor_sublocation_id":"dock","constructor_sublocation_node_id":"dock_entry"}
        view=rt.render_sublocation("dock",player=player,platform="vk")
        self.assertIn("вышли на пристань",view["text"]);self.assertIn(["Портовый рынок"],view["buttons"]);self.assertIn(["Доставка"],view["buttons"]);self.assertTrue(any("Начальник" in row[0] for row in view["buttons"]));self.assertTrue(any("Чайка" in row[0] for row in view["buttons"]))
        service=rt.try_handle_sublocation_action(player,"Доставка",platform="telegram");self.assertEqual(service["route_action"],"Доставка")
        left=rt.try_handle_sublocation_action(player,"Покинуть подлокацию",platform="vk");self.assertIn("вернулись",left["text"])

    def test_published_sublocation_event_starts_obeys_limit_and_returns_to_node(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "forest", {"name": "Лес", "type": "wild", "description": "Лес"})
        self._publish("sublocation", "glade", {"name": "Поляна", "parent_location": "forest", "type": "event_zone", "can_leave": True})
        self._publish("sublocation_node", "glade_entry", {"name": "Центр", "player_text": "Тихая поляна.", "node_type": "entry", "sublocation_id": "glade"})
        self._publish("event", "campfire_story", {
            "name": "История у костра", "text": "Старик начинает рассказ.", "location": "forest",
            "sublocation_id": "glade", "node_id": "glade_entry", "button_text": "Послушать историю", "chance": 100, "limit": 1,
            "rewards": [{"type": "item", "object_id": "simple_sword", "amount": 1, "chance": 100, "text": "Получен старый подарок."}, {"type": "skill_points", "amount": 2}],
            "losses": [{"type": "energy", "amount": 3}],
        })
        self._publish("button", "open_glade", {"text": "На поляну", "owner_location": "forest", "action": "open_sublocation", "target": "glade", "show_telegram": True, "show_vk": True})
        player = {"game_id": "p", "level": 1, "constructor_location_id": "forest", "inventory": []}

        class Storage:
            def update_player(self, _player):
                return None

        from services.city_service import process_world_action
        scene = process_world_action(Storage(), player, "На поляну", "telegram")
        self.assertIn(["Послушать историю"], scene.buttons)
        event = process_world_action(Storage(), player, "Послушать историю", "telegram")
        self.assertIn("Старик начинает рассказ", event.text)
        self.assertEqual(player["constructor_event_id"], "campfire_story")
        returned = process_world_action(Storage(), player, "Завершить событие", "telegram")
        self.assertIn("Тихая поляна", returned.text)
        self.assertIn("Получен старый подарок", returned.text)
        self.assertTrue(any(str(row.get("item_id") or row.get("id")) == "simple_sword" for row in player["inventory"]))
        self.assertEqual(player["free_skill_points"], 2)
        self.assertEqual(player["constructor_sublocation_node_id"], "glade_entry")
        self.assertNotIn(["Послушать историю"], returned.buttons)
        vk_player = {"game_id": "vk", "level": 1, "constructor_location_id": "forest", "inventory": []}
        vk_scene = process_world_action(Storage(), vk_player, "На поляну", "vk")
        self.assertIn(["Послушать историю"], vk_scene.buttons)
        self.assertIn("Старик начинает рассказ", process_world_action(Storage(), vk_player, "Послушать историю", "vk").text)

    def test_constructor_event_completion_can_start_explicit_mob_battle(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"; self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "ruins", {"name": "Руины", "type": "wild", "description": "Камни"})
        self._publish("mob", "guardian", {"name": "Страж", "type": "construct", "hp": 30, "min_level": 1, "max_level": 1, "min_damage": 1, "max_damage": 2})
        self._publish("event", "guardian_event", {"name": "Пробуждение", "text": "Статуя оживает.", "location": "ruins", "battle_mob": "guardian"})
        self._publish("button", "wake", {"text": "Коснуться статуи", "owner_location": "ruins", "action": "start_event", "target": "guardian_event", "show_telegram": True, "show_vk": True})
        player = {"game_id": "p", "name": "Искатель", "level": 1, "constructor_location_id": "ruins", "inventory": [], "attributes": {}}

        class Storage:
            def update_player(self, _player): return None

        from services.city_service import process_world_action
        self.assertIn("Статуя оживает", process_world_action(Storage(), player, "Коснуться статуи", "telegram").text)
        battle = process_world_action(Storage(), player, "Завершить событие", "telegram")
        self.assertTrue(player["in_battle"])
        self.assertEqual(player["active_battle"]["enemies"][0]["source_mob_id"], "guardian")
        self.assertTrue(battle.buttons)

    def test_event_access_gate_is_shared_by_location_and_sublocation(self):
        from datetime import datetime
        player = {
            "level": 5, "energy": 10, "race_id": "elf", "inventory": [{"item_id": "key", "amount": 1}],
            "equipment": {"ring1": {"item_id": "seal"}}, "active_effects": [{"effect_id": "blessing"}],
            "reputations": {"seekers": 20}, "hidden_reputations": {"shadows": 3}, "completed_quests": ["intro"],
            "achievements": [{"id": "first_step"}], "fines": [], "active_world_events": ["festival"],
        }
        event = {
            "min_level": 5, "min_energy": 10, "required_race": "elf", "required_item_id": "key",
            "required_equipped_item_id": "seal", "required_effect_id": "blessing", "forbidden_effect_id": "curse",
            "required_reputation_id": "seekers", "min_reputation": 20, "required_hidden_reputation_id": "shadows",
            "min_hidden_reputation": 3, "required_quest_id": "intro", "required_achievement_id": "first_step",
            "required_world_event_id": "festival", "requires_no_fine": True, "weekdays": [0], "time_start": "10:00", "time_end": "12:00",
            "access_denied_text": "Проход закрыт.",
        }
        self.assertIsNone(rt.event_access_error(player, event, now=datetime(2026, 7, 6, 11, 0)))
        player["energy"] = 9
        self.assertEqual(rt.event_access_error(player, event, now=datetime(2026, 7, 6, 11, 0)), "Проход закрыт.")

    def test_event_consequence_chains_to_next_published_event_once(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"; self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "road", {"name": "Дорога", "type": "wild", "description": "Пыльная дорога"})
        self._publish("event", "second", {"name": "Продолжение", "text": "Следы ведут к башне.", "location": "road"})
        self._publish("event", "first", {"name": "Следы", "text": "На земле видны следы.", "location": "road", "rewards": [{"type": "skill_points", "amount": 1}], "consequences": [{"type": "next_event", "object_id": "second", "chance": 100}]})
        self._publish("button", "tracks", {"text": "Осмотреть следы", "owner_location": "road", "action": "start_event", "target": "first", "show_telegram": True, "show_vk": True})
        player = {"game_id": "p", "level": 1, "constructor_location_id": "road", "inventory": []}

        class Storage:
            def update_player(self, _player): return None

        from services.city_service import process_world_action
        process_world_action(Storage(), player, "Осмотреть следы", "telegram")
        second = process_world_action(Storage(), player, "Завершить событие", "telegram")
        self.assertIn("Следы ведут к башне", second.text)
        self.assertEqual(player["constructor_event_id"], "second")
        self.assertEqual(player["free_skill_points"], 1)
        process_world_action(Storage(), player, "Завершить событие", "telegram")
        self.assertEqual(player["free_skill_points"], 1)

    def test_event_group_redistributes_exhausted_chance_and_button_starts_pick(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"; self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "field", {"name": "Поле", "type": "wild", "description": "Поле"})
        self._publish("event", "depleted", {"name": "Исчерпано", "text": "Не должно выпасть", "location": "field", "event_group": "finds", "chance": 80, "weight": 1, "limit": 1, "chance_after_limit": 0, "redistribution_mode": "by_weight"})
        self._publish("event", "live", {"name": "Находка", "text": "Вы нашли тайник.", "location": "field", "event_group": "finds", "chance": 10, "weight": 2, "max_chance": 100, "redistribution_mode": "by_weight"})
        self._publish("button", "search_group", {"text": "Искать находки", "owner_location": "field", "action": "start_event_group", "target": "finds", "show_telegram": True, "show_vk": True})
        player = {"game_id": "p", "level": 1, "constructor_location_id": "field", "constructor_event_occurrences": {"depleted": 1}, "inventory": []}
        picked = rt.pick_event_group(player, "finds", location_id="field", rng=random.Random(1))
        self.assertEqual(picked["id"], "live")

        class Storage:
            def update_player(self, _player): return None

        from unittest.mock import patch
        from services.city_service import process_world_action
        with patch("services.world_runtime.random.Random", return_value=random.Random(1)):
            response = process_world_action(Storage(), player, "Искать находки", "telegram")
        self.assertIn("Вы нашли тайник", response.text)
        self.assertEqual(player["constructor_event_id"], "live")

    def test_event_can_issue_fine_and_queue_external_message_once(self):
        from services.constructor_event_runtime import complete
        player = {"game_id": "p", "level": 3, "inventory": [], "constructor_event_occurrences": {"raid_notice": 1}}
        event = {"id": "raid_notice", "name": "Облава", "rewards": [{"type": "fine", "object_id": "event_raid", "text": "Стража выписала штраф."}], "consequences": [{"type": "chat_message", "text": "Облава завершена.", "deliver": True}]}
        first = complete(player, event, rng=random.Random(1))
        self.assertIn("Стража выписала штраф.", first["lines"])
        self.assertTrue(player.get("active_fines"))
        self.assertEqual(player["pending_bot_messages"][0]["text"], "Облава завершена.")
        second = complete(player, event, rng=random.Random(1))
        self.assertTrue(second["already_claimed"])
        self.assertEqual(len(player["active_fines"]), 1)
        self.assertEqual(len(player["pending_bot_messages"]), 1)

    def test_published_npc_dialogue_branch_and_unlock_work_in_bot_flow(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "square", {"name": "Тихая площадь", "type": "city", "description": "Пустая площадь."})
        self._publish("npc", "sage", {
            "name": "Мудрец", "npc_kind": "informant", "location": "square",
            "dialogues": [
                {"id": "hello", "dialogue_type": "greeting", "npc_text": "Приветствую, путник."},
                {"id": "identity", "parent_id": "hello", "player_button": "Кто ты?", "npc_text": "Я хранитель старой башни.", "open_access": "old_tower", "ends_dialogue": True},
            ],
        })

        from services.city_service import process_world_action

        class Storage:
            def update_player(self, _player):
                return None

        player = {"game_id": "NT-NPC", "level": 2, "inventory": [], "equipment": {}}
        scene = process_world_action(Storage(), player, "Тихая площадь", "telegram")
        self.assertIn(["Поговорить: Мудрец"], scene.buttons)
        opened = process_world_action(Storage(), player, "Поговорить: Мудрец", "telegram")
        self.assertIn("Приветствую", opened.text)
        self.assertIn(["Кто ты?"], opened.buttons)
        answered = process_world_action(Storage(), player, "Кто ты?", "vk")
        self.assertIn("хранитель старой башни", answered.text)
        self.assertIn("old_tower", player["unlocks"])
        self.assertEqual(player["constructor_npc_dialogue_id"], "identity")

    def test_npc_services_dialogue_losses_quest_and_combat_are_live(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"]="1";self.addCleanup(lambda:os.environ.pop("WORLD_CONSTRUCTOR_LIVE",None))
        self._publish("location","npc_hall",{"name":"Зал наёмников","type":"city","description":"Шумный зал."})
        self._publish("mob","duelist",{"name":"Дуэлянт","type":"human","hp":20,"phys_damage":1,"min_level":1,"max_level":1})
        self._publish("quest","npc_task",{"name":"Поручение","description":"Найти знак.","npc_giver":"captain","goal_type":"collect_item","goal_target":"sign"})
        self._publish("npc","captain",{"name":"Капитан","npc_kind":"mercenary","location":"npc_hall","combat_mob_id":"duelist","kill_fine_id":"underground_casino","kill_consequences":[{"type":"reputation","object_id":"guards","amount":-5}],"combat_reward":[{"type":"currency","amount":4}],"quest_ids":["npc_task"],"trade":{"sells":[{"item_id":"dried_meat","price":2,"stock":1}]},"services":[{"service_id":"heal","name":"Лечение","service_type":"healing","cost":5,"amount":20,"success_text":"Раны перевязаны."},{"service_id":"shop","name":"Личный магазин","service_type":"shop","cost":0}],"dialogues":[{"id":"hello","dialogue_type":"greeting","npc_text":"Плата вперёд."},{"id":"pay","parent_id":"hello","player_button":"Отдать знак","npc_text":"Принято.","loss_item_id":"sign","loss_amount":1,"reputation_id":"guards","reputation_delta":3,"ends_dialogue":True}]})
        from services.city_service import process_world_action
        class Storage:
            def update_player(self,_player):return None
        player={"game_id":"NT-SVC","level":1,"hp":10,"max_hp":30,"money":10,"inventory":[{"item_id":"sign","amount":1}],"equipment":{}}
        process_world_action(Storage(),player,"Зал наёмников","telegram");opened=process_world_action(Storage(),player,"Поговорить: Капитан","telegram");self.assertIn(["Лечение"],opened.buttons);self.assertIn(["Принять квест: npc_task"],opened.buttons);self.assertIn(["Сразиться"],opened.buttons)
        healed=process_world_action(Storage(),player,"Лечение","vk");self.assertIn("перевязаны",healed.text);self.assertEqual(player["hp"],30);self.assertEqual(player["money"],5)
        shop=process_world_action(Storage(),player,"Личный магазин","telegram");self.assertIn(["Купить у NPC: dried_meat"],shop.buttons);bought=process_world_action(Storage(),player,"Купить у NPC: dried_meat","telegram");self.assertIn("Куплено",bought.text);self.assertEqual(player["money"],3);self.assertTrue(any(row.get("item_id")=="dried_meat" for row in player["inventory"]))
        process_world_action(Storage(),player,"Отдать знак","telegram");self.assertFalse(any(row.get("item_id")=="sign" for row in player["inventory"]));self.assertEqual(player["reputations"]["guards"],3)
        accepted=process_world_action(Storage(),player,"Принять квест: npc_task","telegram");self.assertIn("Найти знак",accepted.text);self.assertIn("npc_task",player["active_world_quests"])
        battle=process_world_action(Storage(),player,"Сразиться","vk");self.assertTrue(player["in_battle"]);self.assertIn("Начинается бой",battle.text)
        from services.pve_battle_service import grant_battle_rewards
        grant_battle_rewards(player,player["active_battle"],random.Random(1));self.assertTrue(player.get("active_fines"));self.assertEqual(player["reputations"]["guards"],-2);self.assertGreaterEqual(player["money"],7)

    def test_button_conditions_and_atomic_consequences_are_live(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "vault", {"name": "Хранилище", "type": "story", "description": "Каменная дверь."})
        self._publish("button", "open_seal", {
            "text": "Сломать печать", "owner_location": "vault", "action": "take_item",
            "target": "money_copper", "min_level": 3, "show_required_item_id": "money_copper",
            "take_item_id": "money_copper", "take_item_amount": 2, "energy_cost": 4,
            "open_access": "sealed_room", "one_time": True, "message": "Печать разрушена.",
            "show_telegram": True, "show_vk": True,
        })

        player = {"level": 2, "energy": 10, "inventory": [{"item_id": "money_copper", "amount": 3}]}
        hidden = rt.render_location("vault", platform="telegram", player=player)
        self.assertNotIn(["Сломать печать"], hidden["buttons"])
        player["level"] = 3
        shown = rt.render_location("vault", platform="vk", player=player)
        self.assertIn(["Сломать печать"], shown["buttons"])
        player["constructor_location_id"] = "vault"
        result = rt.try_handle_location_action(player, "Сломать печать", platform="vk")
        self.assertIn("Печать разрушена", result["text"])
        self.assertEqual(player["energy"], 6)
        self.assertEqual(player["inventory"][0]["amount"], 1)
        self.assertIn("sealed_room", player["unlocks"])
        self.assertIn("open_seal", player.get("used_world_buttons", []), player)
        self.assertNotIn(["Сломать печать"], result["buttons"])

    def test_special_button_routes_and_battle_are_not_noops(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"]="1";self.addCleanup(lambda:os.environ.pop("WORLD_CONSTRUCTOR_LIVE",None))
        self._publish("location","hub_buttons",{"name":"Узел кнопок","type":"city","description":"Пульт."});self._publish("mob","button_mob",{"name":"Манекен","type":"mechanism","hp":5,"phys_damage":1,"min_level":1,"max_level":1})
        for bid,text,action,target in (("market_btn","Открыть торговлю","open_market",""),("profile_btn","Открыть профиль","open_profile",""),("fight_btn","Начать испытание","start_battle","button_mob"),("hide_btn","Скрыть меню","hide_menu","")):
            self._publish("button",bid,{"text":text,"owner_location":"hub_buttons","action":action,"target":target,"show_telegram":True,"show_vk":True})
        from services.city_service import process_world_action
        class Storage:
            def update_player(self,_player):return None
        player={"game_id":"NT-BTN","level":1,"inventory":[],"equipment":{}}
        process_world_action(Storage(),player,"Узел кнопок","telegram")
        market=process_world_action(Storage(),player,"Открыть торговлю","telegram");self.assertIn(["Рынок"],market.buttons)
        profile=process_world_action(Storage(),player,"Открыть профиль","vk");self.assertIn(["👤 Профиль"],profile.buttons)
        hidden=process_world_action(Storage(),player,"Скрыть меню","telegram");self.assertIn("скрыто",hidden.text.lower())
        fight=process_world_action(Storage(),player,"Начать испытание","vk");self.assertTrue(player["in_battle"]);self.assertIn("Начинается бой",fight.text)

    def test_event_owned_button_runs_inside_event_scene(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self.addCleanup(lambda: os.environ.pop("WORLD_CONSTRUCTOR_LIVE", None))
        self._publish("location", "shore", {"name": "Берег", "type": "wild", "description": "Волны."})
        self._publish("event", "bottle", {"name": "Бутылка", "text": "В песке лежит бутылка.", "location": "shore"})
        self._publish("button", "start_bottle", {"text": "Осмотреть бутылку", "owner_location": "shore", "action": "start_event", "target": "bottle", "show_telegram": True, "show_vk": True})
        self._publish("button", "read_note", {"text": "Прочитать записку", "owner_event": "bottle", "action": "show_message", "message": "Записка указывает на север.", "show_telegram": True, "show_vk": True})
        from services.city_service import process_world_action

        class Storage:
            def update_player(self, _player): return None

        player = {"level": 1, "inventory": [], "equipment": {}}
        process_world_action(Storage(), player, "Берег", "telegram")
        event = process_world_action(Storage(), player, "Осмотреть бутылку", "telegram")
        self.assertIn(["Прочитать записку"], event.buttons)
        note = process_world_action(Storage(), player, "Прочитать записку", "vk")
        self.assertIn("указывает на север", note.text)


if __name__ == "__main__":
    unittest.main()
