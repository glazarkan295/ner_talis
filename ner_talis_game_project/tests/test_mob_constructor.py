"""Расширенный конструктор мобов (ТЗ «Конструктор мобов»).

Покрывает новые под-объекты моба в world_content_registry (варианты/навыки/
пассивы/сопротивления/эффекты/привязки к событию и зоне/фазы босса), обогащённый
валидатор карточки моба (боевые параметры §8) и права RBAC §33.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class MobConstructorRegistryTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        self._tmp = tmp.name
        os.environ["WORLD_CONTENT_PATH"] = self._tmp
        import services.world_content_registry as wcr
        self.wcr = wcr
        wcr.create_content(wcr.KIND_LOCATION, "loc_forest", {
            "name": "Лес", "short_description": "тест", "type": "wild",
        })
        wcr.create_content(wcr.KIND_MOB, "mob_wolf", {
            "name": "Волк", "type": "beast", "hp": 50,
        })
        wcr.create_content(wcr.KIND_EVENT, "ev_tracks", {
            "name": "Следы", "text": "Следы в траве", "location": "loc_forest",
        })
        wcr.create_content(wcr.KIND_LOCATION_ZONE, "zone_cursed", {
            "name": "Проклятая зона", "type": "cursed", "location": "loc_forest",
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

    def _errors(self, result):
        return " ".join(result["errors"])

    def test_mob_card_combat_params(self):
        ok = self._check(self.wcr.KIND_MOB, "mob_bear", {
            "name": "Медведь", "type": "beast", "hp": 120,
            "attack_type": "physical", "behavior": "aggressive",
            "min_in_battle": 1, "max_in_battle": 3,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_MOB, "mob_x", {
            "name": "X", "type": "beast", "hp": 10,
            "attack_type": "telepathy", "min_in_battle": 5, "max_in_battle": 2,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("тип атаки", self._errors(bad))
        self.assertIn("больше максимума", self._errors(bad))

    def test_balance_warnings(self):
        # §30: большая группа в бою + частый дроп большими пачками → warning,
        # но не блокирует публикацию (это предупреждения, не ошибки).
        res = self._check(self.wcr.KIND_MOB, "mob_swarm", {
            "name": "Рой", "type": "beast", "hp": 30,
            "max_in_battle": 25, "min_in_battle": 1,
            "drop": [{"item_id": "money_copper", "chance": 80, "max_count": 50}],
        })
        self.assertTrue(res["ok"], res["errors"])
        joined = " ".join(res["warnings"])
        self.assertIn("Очень большая группа", joined)
        self.assertIn("фарм-петля", joined)

    def test_variant_multipliers(self):
        ok = self._check(self.wcr.KIND_MOB_VARIANT, "var_elite", {
            "name": "Элитный волк", "mob_id": "mob_wolf", "variant_type": "elite",
            "hp_mult": 2.0, "damage_mult": 1.5, "spawn_chance": 5,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_MOB_VARIANT, "var_bad", {
            "name": "Плохой", "mob_id": "mob_wolf", "variant_type": "godlike",
            "hp_mult": -1,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("тип варианта", self._errors(bad))

    def test_skill_types_and_conditions(self):
        ok = self._check(self.wcr.KIND_MOB_SKILL, "sk_bite", {
            "name": "Укус", "mob_id": "mob_wolf", "skill_type": "heavy_attack",
            "use_condition": "hp_below", "use_chance": 30, "cooldown": 2,
            "player_text": "Волк бросается вперёд.",
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_MOB_SKILL, "sk_bad", {
            "name": "X", "mob_id": "mob_wolf", "skill_type": "teleport_strike",
            "use_condition": "when_bored", "cooldown": -1,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("тип навыка", self._errors(bad))
        self.assertIn("условие использования", self._errors(bad))

    def test_resistance_type(self):
        ok = self._check(self.wcr.KIND_MOB_RESISTANCE, "res_fire", {
            "mob_id": "mob_wolf", "resist_type": "fire", "value": 25,
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_MOB_RESISTANCE, "res_bad", {
            "mob_id": "mob_wolf", "resist_type": "psychic",
        })
        self.assertFalse(bad["ok"])
        self.assertIn("тип сопротивления", self._errors(bad))

    def test_passive_and_phase(self):
        ok = self._check(self.wcr.KIND_MOB_PASSIVE, "pass_thick", {
            "name": "Толстая шкура", "mob_id": "mob_wolf",
            "player_description": "Снижает физический урон.",
        })
        self.assertTrue(ok["ok"], ok["errors"])
        phase = self._check(self.wcr.KIND_MOB_PHASE, "phase_2", {
            "name": "Фаза 2", "mob_id": "mob_wolf", "start_condition": "hp_below_70",
        })
        self.assertTrue(phase["ok"], phase["errors"])

    def test_effect_existence_optional(self):
        ok = self._check(self.wcr.KIND_MOB_EFFECT, "eff_poison", {
            "name": "Яд", "mob_id": "mob_wolf", "chance": 20, "duration": 3,
            "player_text": "Клыки источают яд.",
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_MOB_EFFECT, "eff_bad", {
            "name": "X", "mob_id": "mob_ghost", "chance": 150,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("Моб «mob_ghost» не существует", self._errors(bad))

    def test_event_link_refs(self):
        ok = self._check(self.wcr.KIND_MOB_EVENT_LINK, "link_tracks", {
            "mob_id": "mob_wolf", "event_id": "ev_tracks", "spawn_chance": 40,
            "count": 1, "variant_type": "normal",
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_MOB_EVENT_LINK, "link_bad", {
            "mob_id": "mob_wolf", "event_id": "ev_missing", "count": 0,
        })
        self.assertFalse(bad["ok"])
        self.assertIn("Событие «ev_missing» не существует", self._errors(bad))

    def test_zone_link_refs(self):
        ok = self._check(self.wcr.KIND_MOB_ZONE_LINK, "zlink_ok", {
            "mob_id": "mob_wolf", "zone_id": "zone_cursed",
            "spawn_chance_delta": 15, "variant_type": "cursed",
        })
        self.assertTrue(ok["ok"], ok["errors"])
        bad = self._check(self.wcr.KIND_MOB_ZONE_LINK, "zlink_bad", {
            "mob_id": "mob_wolf", "zone_id": "zone_missing",
        })
        self.assertFalse(bad["ok"])
        self.assertIn("Зона «zone_missing» не существует", self._errors(bad))


class MobConstructorRbacTest(unittest.TestCase):
    def test_permissions_registered_and_mapped(self):
        from services import admin_rbac as rbac
        self.assertIn(rbac.PERM_MOB_PUBLISH, rbac.ALL_PERMISSIONS)
        self.assertIn(rbac.PERM_MOB_CHANGE_LOOT, rbac.ALL_PERMISSIONS)
        # content ведёт черновики и характеристики, но не публикует/не правит лут.
        self.assertTrue(rbac.has_permission(rbac.CONTENT, "mob.create"))
        self.assertTrue(rbac.has_permission(rbac.CONTENT, "mob.change_stats"))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, "mob.publish"))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, "mob.change_loot"))
        # economy крутит баланс дропа/лимитов.
        self.assertTrue(rbac.has_permission(rbac.ECONOMY, "mob.change_loot"))
        # read_only только смотрит.
        self.assertTrue(rbac.has_permission(rbac.READ_ONLY, "mob.view"))
        self.assertFalse(rbac.has_permission(rbac.READ_ONLY, "mob.edit"))

    def test_dangerous_actions(self):
        from services import admin_rbac as rbac
        for action in ("mob.publish", "mob.disable", "mob.archive",
                       "mob.delete_soft", "mob.change_loot"):
            self.assertIn(action, rbac.DANGEROUS_ACTIONS)


if __name__ == "__main__":
    unittest.main()
