"""Конструктор боевых настроек (ТЗ 20 §1–§4, §10): сервис, валидация, API, RBAC."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from admin_combat_api import create_admin_combat_router
from services import admin_rbac as rbac
from services import combat_constructor_service as combat
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class CombatServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("COMBAT_CONSTRUCTOR_PATH")
        os.environ["COMBAT_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "combat.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("COMBAT_CONSTRUCTOR_PATH", None)
        else:
            os.environ["COMBAT_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_group_timer(self):
        env = combat.store().create("grp", {
            "name": "Групповой бой", "scope": "global", "timer_enabled": True,
            "turn_seconds": 100, "only_group_battles": True, "on_timeout": "skip",
            "warn_before_seconds": 15, "ally_order_type": "by_initiative",
        })
        result = combat.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = combat.store().create("bad", {
            "name": "", "scope": "bogus", "timer_enabled": True, "turn_seconds": 0,
            "on_timeout": "explode",
        })
        result = combat.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("название", joined)
        self.assertIn("область", joined)
        self.assertIn("время на ход", joined)

    def test_warn_after_timer_is_error(self):
        env = combat.store().create("warn1", {
            "name": "X", "scope": "pvp", "timer_enabled": True,
            "turn_seconds": 30, "warn_before_seconds": 60,
        })
        self.assertFalse(combat.validate(env)["ok"])

    def test_group_without_timer_warns(self):
        env = combat.store().create("g2", {"name": "G", "scope": "global", "only_group_battles": True})
        res = combat.validate(env)
        self.assertTrue(res["ok"])
        self.assertTrue(any("групповых" in w for w in res["warnings"]))

    def test_published_profile_is_resolved_by_runtime_specificity(self):
        combat.store().create("global", {"name": "G", "scope": "global", "timer_enabled": True, "turn_seconds": 100, "priority": 1})
        combat.store().set_status("global", combat.STATUS_PUBLISHED, force=True)
        combat.store().create("wolf", {"name": "W", "scope": "mob", "scope_id": "wolf", "timer_enabled": True, "turn_seconds": 30})
        combat.store().set_status("wolf", combat.STATUS_PUBLISHED, force=True)
        self.assertEqual(combat.resolve_profile("mob", object_id="wolf")["turn_seconds"], 30)
        self.assertEqual(combat.resolve_profile("pve", object_id="forest")["turn_seconds"], 100)

    def test_combat_group_participants_validate_and_allies_fight(self):
        from services.combat_group_runtime import attach_participants, apply_ally_phase, choose_enemy_target, damage_ally
        import random
        participants = [
            {"participant_id": "hero", "participant_type": "player", "side": "player"},
            {"participant_id": "friend", "participant_type": "player_ally", "side": "player_allies",
             "name": "Союзник", "hp": 40, "damage": 12, "accuracy": 100,
             "behavior": "weakest", "order": 5, "can_attack": True, "can_die": True,
             "death_consequence": "remove_from_group"},
            {"participant_id": "wolf", "participant_type": "mob", "side": "enemy"},
        ]
        env = combat.store().create("party", {"name": "Отряд", "scope": "pve", "participants": participants})
        self.assertTrue(combat.validate(env)["ok"], combat.validate(env)["errors"])
        battle = {
            "combat_profile": env["data"], "player_state": {"current_hp": 50, "max_hp": 50},
            "enemies": [{"name": "Сильный", "current_hp": 30}, {"name": "Слабый", "current_hp": 10}],
        }
        allies = attach_participants(battle)
        self.assertEqual(allies[0]["name"], "Союзник")
        log = []
        apply_ally_phase(battle, random.Random(1), log)
        self.assertEqual(battle["enemies"][1]["current_hp"], 0)
        self.assertTrue(any("Союзник" in line for line in log))
        allies[0]["behavior"] = "protect_player"
        target = choose_enemy_target(battle, random.Random(2))
        self.assertIs(target, allies[0])
        damage_ally(target, 99, log, "Волк")
        self.assertEqual(target["current_hp"], 0)
        self.assertTrue(any("remove_from_group" in line for line in log))

    def test_combat_group_rejects_invalid_participant(self):
        env = combat.store().create("bad_party", {"name": "X", "scope": "pve", "participants": [
            {"participant_id": "x", "participant_type": "dragon", "side": "nowhere", "hp": -1},
        ]})
        result = combat.validate(env)
        self.assertFalse(result["ok"])
        self.assertIn("неизвестный тип", " ".join(result["errors"]).lower())

    def test_full_pve_profile_and_mob_escape_validate(self):
        env = combat.store().create("pve_full", {"name": "Рейд", "scope": "pve", "pve_type": "raid_boss", "battle_source": "event_campaign", "turn_order": "initiative", "mob_escape_rules": [{"enabled": True, "mode": "boss_retreat", "condition_type": "hp_percent", "value": 10, "chance": 75, "success_text": "Босс отступает"}]})
        self.assertTrue(combat.validate(env)["ok"], combat.validate(env)["errors"])
        bad = combat.store().create("pve_bad", {"name": "Bad", "scope": "pve", "pve_type": "unknown", "mob_escape_rules": [{"enabled": True, "mode": "teleport", "condition_type": "unknown"}]})
        errors = " ".join(combat.validate(bad)["errors"])
        self.assertIn("тип PVE", errors)
        self.assertIn("Побег моба", errors)


class CombatApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("COMBAT_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["COMBAT_CONSTRUCTOR_PATH"] = str(base / "combat.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_combat_router(lambda: self.storage))
        self.client = TestClient(app)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _token(self, uid="999"):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id=uid)
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_meta_defaults(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/combat/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        body = meta.json()
        self.assertEqual(body["defaultTurnSeconds"], 100)
        self.assertIn("global", {s["value"] for s in body["scopes"]})
        self.assertIn("npc_ally", body["participantTypes"])
        self.assertIn("player_allies", body["participantSides"])
        self.assertIn("raid_boss", body["pveTypes"])
        self.assertIn("hp_percent", body["mobEscapeConditions"])

    def test_create_publish_flow(self):
        token = self._token()
        create = self.client.post("/api/admin/v2/combat", headers=self._auth(token), json={"id": "grp", "data": {"name": "Группа", "scope": "global", "timer_enabled": True, "turn_seconds": 100}})
        self.assertEqual(create.status_code, 200, create.text)
        pub = self.client.post("/api/admin/v2/combat/grp/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_content_cannot_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self.client.post("/api/admin/v2/combat", headers=self._auth(token), json={"id": "c1", "data": {"name": "C", "scope": "pve"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/combat/c1/publish", headers=self._auth(token), json={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
