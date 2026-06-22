"""Расширенный конструктор локаций (ТЗ «Конструктор локаций»).

Покрывает новые под-объекты локации в world_content_registry (зоны/ресурсы/
добыча/мобы локации/недельные лимиты/ротации/правила истощения/пустая
локация/скрытые события/варианты ответа) и права RBAC §60.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class LocationConstructorRegistryTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        self._tmp = tmp.name
        os.environ["WORLD_CONTENT_PATH"] = self._tmp
        import services.world_content_registry as wcr
        self.wcr = wcr
        wcr.create_content(wcr.KIND_LOCATION, "loc_forest", {
            "name": "Обыкновенный лес", "short_description": "тест", "type": "wild",
        })
        wcr.create_content(wcr.KIND_MOB, "mob_wolf", {
            "name": "Волк", "type": "beast", "hp": 50,
        })

    def tearDown(self):
        os.environ.pop("WORLD_CONTENT_PATH", None)
        for suffix in ("", ".lock", ".tmp"):
            try:
                os.unlink(self._tmp + suffix)
            except OSError:
                pass

    def _check(self, kind, cid, data):
        env = self.wcr.create_content(kind, cid, data)
        return self.wcr.validate_envelope(env)

    def _errors_text(self, result):
        return " ".join(result["errors"])

    def test_zone_ok_and_bad_type(self):
        ok = self._check(self.wcr.KIND_LOCATION_ZONE, "z_ok", {
            "name": "Огненная зона", "type": "fire", "location": "loc_forest",
            "trigger_chance": 20,
            "protections": [{"item_id": "money_copper", "percent": 50}],
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_ZONE, "z_bad", {
            "name": "X", "type": "plasma", "location": "loc_forest",
        })
        self.assertFalse(bad["ok"])
        self.assertIn("тип зоны", self._errors_text(bad))

    def test_resource_chance_window(self):
        ok = self._check(self.wcr.KIND_LOCATION_RESOURCE, "res_ok", {
            "location": "loc_forest", "item_id": "money_copper", "category": "herb",
            "base_chance": 30, "min_chance": 1, "min_count": 1, "max_count": 5,
            "weekly_limit": 70,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_RESOURCE, "res_bad", {
            "location": "loc_forest", "item_id": "money_copper",
            "base_chance": 10, "min_chance": 20,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("Минимальный шанс", self._errors_text(bad))

    def test_loot_source_validation(self):
        ok = self._check(self.wcr.KIND_LOCATION_LOOT, "loot_ok", {
            "location": "loc_forest", "item_id": "money_copper",
            "source": "search", "chance": 15, "min_chance": 1,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_LOOT, "loot_bad", {
            "location": "loc_forest", "item_id": "money_copper",
            "source": "telepathy", "chance": 10,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("источник добычи", self._errors_text(bad))

    def test_mob_spawn_refs_and_battle_counts(self):
        ok = self._check(self.wcr.KIND_LOCATION_MOB_SPAWN, "spawn_ok", {
            "location": "loc_forest", "mob_id": "mob_wolf", "spawn_chance": 25,
            "min_chance": 2, "min_in_battle": 1, "max_in_battle": 5,
            "weekly_stock": 100,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_MOB_SPAWN, "spawn_bad", {
            "location": "loc_forest", "mob_id": "mob_ghost", "spawn_chance": 10,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("не существует", self._errors_text(bad))

    def test_weekly_limit_linked_object(self):
        ok_mob = self._check(self.wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_mob", {
            "location": "loc_forest", "limit_type": "mob", "linked_object": "mob_wolf",
            "total_stock": 100, "min_per_event": 1, "max_per_event": 5,
        })
        self.assertTrue(ok_mob["ok"], ok_mob["errors"])
        ok_res = self._check(self.wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_res", {
            "location": "loc_forest", "limit_type": "resource",
            "linked_object": "money_copper", "total_stock": 70,
        })
        self.assertTrue(ok_res["ok"], ok_res["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_bad", {
            "location": "loc_forest", "limit_type": "mob",
            "linked_object": "mob_ghost", "total_stock": 10,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("Связанный моб", self._errors_text(bad))

    def test_rotation_modes(self):
        ok = self._check(self.wcr.KIND_LOCATION_WEEKLY_ROTATION, "rot_ok", {
            "location": "loc_forest", "name": "Обычная неделя",
            "periodicity": "weekly", "selection_mode": "random",
            "active_resources": 3, "active_mobs": 2, "active_events": 4,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_WEEKLY_ROTATION, "rot_bad", {
            "location": "loc_forest", "periodicity": "weekly",
            "selection_mode": "telepathic",
        })
        self.assertFalse(bad["ok"])
        self.assertIn("режим выбора", self._errors_text(bad))

    def test_depletion_rule(self):
        ok = self._check(self.wcr.KIND_LOCATION_DEPLETION_RULE, "dep_ok", {
            "location": "loc_forest", "base_chance": 30, "min_chance": 1,
            "trigger": "zero", "redistribution_mode": "by_weight",
            "event_group": "resource",
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_DEPLETION_RULE, "dep_bad", {
            "base_chance": 10, "min_chance": 1, "redistribution_mode": "chaos",
        })
        self.assertFalse(bad["ok"])
        self.assertIn("перераспределения", self._errors_text(bad))

    def test_empty_event_requires_text(self):
        ok = self._check(self.wcr.KIND_LOCATION_EMPTY_EVENT, "empty_ok", {
            "location": "loc_forest", "player_text": "Вы ничего не нашли.",
            "min_percent_depleted": 50, "chance": 100,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_EMPTY_EVENT, "empty_bad", {
            "location": "loc_forest", "min_percent_depleted": 50,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("текст события пустой локации", self._errors_text(bad))

    def test_hidden_event_requires_conditions(self):
        ok = self._check(self.wcr.KIND_LOCATION_HIDDEN_EVENT, "hid_ok", {
            "admin_name": "Шёпот Древних", "player_text": "Вы слышите шёпот.",
            "location": "loc_forest", "conditions": [{"type": "has_item"}],
            "open_chance": 1,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_HIDDEN_EVENT, "hid_bad", {
            "admin_name": "X", "player_text": "Y", "location": "loc_forest",
        })
        self.assertFalse(bad["ok"])
        self.assertIn("условия открытия", self._errors_text(bad))

    def test_event_outcome_type_and_npc_kind(self):
        # Тип исхода события и вид NPC валидируются по справочникам (доп.§3/§5).
        ok = self._check(self.wcr.KIND_EVENT, "ev_out", {
            "name": "Развилка", "text": "Выбор", "location": "loc_forest",
            "type": "story", "outcome_type": "battle_or_nothing",
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_EVENT, "ev_bad", {
            "name": "X", "text": "Y", "location": "loc_forest", "outcome_type": "teleport_tax",
        })
        self.assertFalse(bad["ok"])
        self.assertIn("тип исхода", self._errors_text(bad).lower())
        npc_ok = self._check(self.wcr.KIND_NPC, "npc_q", {
            "name": "Загадочник", "location": "loc_forest", "npc_kind": "questioner",
        })
        self.assertTrue(npc_ok["ok"], npc_ok["errors"])
        npc_bad = self._check(self.wcr.KIND_NPC, "npc_bad", {
            "name": "X", "location": "loc_forest", "npc_kind": "wizardish",
        })
        self.assertFalse(npc_bad["ok"])
        self.assertIn("вид npc", self._errors_text(npc_bad).lower())

    def test_npc_trade_validation(self):
        # NPC-торговец: ассортимент ссылается на существующие предметы (§12).
        ok = self._check(self.wcr.KIND_NPC, "npc_trader", {
            "name": "Купец", "location": "loc_forest", "npc_kind": "trader",
            "trade": {"sells": [{"item_id": "money_copper", "price": 10, "currency": "copper"}], "buys": []},
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_NPC, "npc_trader_bad", {
            "name": "X", "location": "loc_forest", "npc_kind": "trader",
            "trade": {"sells": [{"item_id": "ghost_item", "price": -5}]},
        })
        self.assertFalse(bad["ok"])
        joined = self._errors_text(bad)
        self.assertIn("не существует", joined)
        self.assertIn("отрицательной", joined)

    def test_location_external_image_rejected(self):
        bad = self._check(self.wcr.KIND_LOCATION, "loc_ext", {
            "name": "Локация", "short_description": "тест", "type": "wild",
            "image": "http://evil.example/bg.png",
        })
        self.assertFalse(bad["ok"])
        self.assertIn("внешние url", self._errors_text(bad).lower())

    def test_item_constructor_external_image_rejected(self):
        from services import item_constructor_service as ics
        bad = ics.validate({"data": {
            "name": "Меч", "description": "острый", "category": "Оружие",
            "image": "https://cdn.example/sword.png",
        }})
        self.assertFalse(bad["ok"])
        self.assertTrue(any("внешние url" in e.lower() for e in bad["errors"]))
        ok_img = ics.validate({"data": {
            "name": "Меч", "description": "острый", "category": "Оружие",
            "image": "/assets/items/equipment/sword.png",
        }})
        self.assertFalse(any("внешние url" in e.lower() for e in ok_img["errors"]))

    def test_event_answer_hidden_requires_conditions(self):
        ok = self._check(self.wcr.KIND_LOCATION_EVENT_ANSWER, "ans_ok", {
            "button_text": "Осмотреть сундук", "result": "show_text",
            "result_text": "Сундук пуст.",
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_LOCATION_EVENT_ANSWER, "ans_bad", {
            "button_text": "Положить 100 монет", "result": "give_item",
            "hidden": True,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("условия показа", self._errors_text(bad))


class LocationConstructorRbacTest(unittest.TestCase):
    def test_new_permissions_registered_and_mapped(self):
        from services import admin_rbac as rbac
        self.assertIn(rbac.PERM_LOCATION_RESOURCES_EDIT, rbac.ALL_PERMISSIONS)
        self.assertIn(rbac.PERM_LOCATION_LIMITS_FORCE_RESTORE, rbac.ALL_PERMISSIONS)
        # content/economy ведут под-системы локации.
        self.assertTrue(rbac.has_permission(rbac.CONTENT, "location_resources.edit"))
        self.assertTrue(rbac.has_permission(rbac.ECONOMY, "location_limits.edit"))
        # read_only только смотрит.
        self.assertTrue(rbac.has_permission(rbac.READ_ONLY, "location_resources.view"))
        self.assertFalse(rbac.has_permission(rbac.READ_ONLY, "location_resources.edit"))

    def test_force_actions_dangerous_and_restricted(self):
        from services import admin_rbac as rbac
        self.assertIn("location_limits.force_restore", rbac.DANGEROUS_ACTIONS)
        self.assertIn("location_rotation.force_update", rbac.DANGEROUS_ACTIONS)
        # force-вмешательство — admin/owner, не content.
        self.assertFalse(rbac.has_permission(rbac.CONTENT, "location_limits.force_restore"))
        self.assertTrue(rbac.has_permission(rbac.ADMIN, "location_limits.force_restore"))
        self.assertTrue(rbac.has_permission(rbac.OWNER, "location_rotation.force_update"))


if __name__ == "__main__":
    unittest.main()
