"""Конструкторы прогрессии (чат-ТЗ «уровни/опыт/регистрация/расы»):
валидация, API через общую фабрику, импорт рас, версионирование, RBAC."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from admin_progression_api import (
    create_admin_exp_router,
    create_admin_levels_router,
    create_admin_races_router,
    create_admin_registration_router,
)
from services import admin_rbac as rbac
from services import level_constructor_service as level_svc
from services import race_constructor_service as race_svc
from services import registration_constructor_service as reg_svc
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage

_PATHS = ("LEVEL_CONSTRUCTOR_PATH", "EXP_CONSTRUCTOR_PATH", "REGISTRATION_CONSTRUCTOR_PATH", "RACE_CONSTRUCTOR_PATH")


class ProgressionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = (*_PATHS, "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        for p in _PATHS:
            os.environ[p] = str(base / f"{p.lower()}.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        for factory in (create_admin_levels_router, create_admin_exp_router,
                        create_admin_registration_router, create_admin_races_router):
            app.include_router(factory(lambda: self.storage))
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

    def test_level_validation(self):
        ok = level_svc.store().create("lvl5", {"title": "Уровень 5", "level": 5, "exp_required": 1000})
        self.assertTrue(level_svc.validate(ok)["ok"], level_svc.validate(ok)["errors"])
        bad = level_svc.store().create("bad", {"level": 0, "exp_required": -1})
        self.assertFalse(level_svc.validate(bad)["ok"])

    def test_level_crud_and_publish(self):
        token = self._token()
        c = self.client.post("/api/admin/v2/levels", headers=self._auth(token), json={"id": "lvl1", "data": {"title": "Уровень 1", "level": 1, "exp_required": 0}})
        self.assertEqual(c.status_code, 200, c.text)
        pub = self.client.post("/api/admin/v2/levels/lvl1/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_published_progression_rule_drives_cap_rewards_source_penalty_and_death(self):
        from services.progression_service import grant_experience, apply_death_experience_penalty
        from services import exp_constructor_service as exp_svc
        rule={"entity_type":"rule","title":"Основная прогрессия","active_rule":True,"start_level":1,"max_level":3,"stat_points_per_level":1,"skill_points_per_level":4,"death_exp_loss_enabled":True,"death_loss_percent":20,"death_loss_from_current":True,"death_loss_max":15,"migration_required":True}
        env=level_svc.store().create("main_rule",rule);self.assertTrue(level_svc.validate(env)["ok"],level_svc.validate(env)["errors"]);level_svc.store().set_status("main_rule",level_svc.STATUS_PUBLISHED,force=True)
        for level,required in ((1,100),(2,200),(3,300)):
            level_svc.store().create(f"level_{level}",{"entity_type":"level","title":f"Уровень {level}","level":level,"exp_required":required,"skill_points":4,"stat_points":1,"level_up_text":f"Новый уровень {level}","migration_required":True})
            level_svc.store().set_status(f"level_{level}",level_svc.STATUS_PUBLISHED,force=True)
        exp_svc.store().create("mob_rule",{"name":"Мобы","source_type":"mob_kill","base_exp":100,"penalty_after_level":2,"penalty_percent":50,"min_exp":10,"max_exp":60,"show_player":True})
        exp_svc.store().set_status("mob_rule",exp_svc.STATUS_PUBLISHED,force=True)
        player={"level":1,"experience":0,"total_experience":0,"free_skill_points":0,"free_stat_points":0}
        first=grant_experience(player,100,source_type="mob_kill");self.assertEqual(first["level"],1);self.assertEqual(first["gained"],60)
        grant_experience(player,40);self.assertEqual(player["level"],2);self.assertEqual(player["free_skill_points"],4)
        player["experience"]=80;loss=apply_death_experience_penalty(player);self.assertEqual(loss["lost"],15);self.assertEqual(player["experience"],65)

    def test_exp_meta_and_create(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/exp/meta", headers=self._auth(token)).json()
        self.assertTrue(any(s["value"] == "mob_kill" for s in meta["sourceTypes"]))
        c = self.client.post("/api/admin/v2/exp", headers=self._auth(token), json={"id": "from_mobs", "data": {"name": "Опыт с мобов", "source_type": "mob_kill", "base_exp": 10}})
        self.assertEqual(c.status_code, 200, c.text)

    def test_registration_history_rollback(self):
        token = self._token()
        self.client.post("/api/admin/v2/registration", headers=self._auth(token), json={"id": "step_name", "data": {"label": "Имя", "step_type": "name"}})
        self.client.put("/api/admin/v2/registration/step_name", headers=self._auth(token), json={"data": {"label": "Ввод имени"}})
        hist = self.client.get("/api/admin/v2/registration/step_name/history", headers=self._auth(token))
        self.assertIn(1, [h["version"] for h in hist.json()["history"]])
        rb = self.client.post("/api/admin/v2/registration/step_name/rollback", headers=self._auth(token), json={"version": 1})
        self.assertEqual(rb.status_code, 200, rb.text)
        self.assertEqual(self.client.get("/api/admin/v2/registration/step_name", headers=self._auth(token)).json()["item"]["data"]["label"], "Имя")

    def test_published_registration_scenario_drives_both_platforms_and_start_setup(self):
        from services.registration_service import create_player, registration_access, registration_text, validate_name
        scenario = {"entity_type":"scenario","name":"Основная регистрация","system_name":"main_v2","active":True,
                    "telegram_enabled":True,"vk_enabled":True,"registration_enabled":True,"priority":10,
                    "name_min_length":4,"name_max_length":12,"forbidden_names":["Злодей"],
                    "welcome_text":"Добро пожаловать в конструктор.","complete_text":"Готово, {player_name}!",
                    "steps":[{"id":"name","label":"Имя","step_type":"name","order":1,"required":True},
                             {"id":"race","label":"Раса","step_type":"race","order":2,"required":True}],
                    "starting_skills":[{"skill_id":"constructor_strike","all_players":True,"permanent":True}],
                    "start_city_id":"new_city","start_location_id":"new_road","start_sublocation_id":"new_gate"}
        env=reg_svc.store().create("main",scenario);self.assertTrue(reg_svc.validate(env)["ok"],reg_svc.validate(env)["errors"])
        reg_svc.store().set_status("main",reg_svc.STATUS_PUBLISHED,force=True)
        self.assertTrue(registration_access("telegram")[0]);self.assertEqual(registration_text("vk","welcome_text","x"),"Добро пожаловать в конструктор.")
        self.assertFalse(validate_name("abc","telegram")[0]);self.assertFalse(validate_name("Злодей","vk")[0])
        races={"human":{"name":"Человек","stats":{"strength":1,"dexterity":1,"endurance":1,"intelligence":1,"wisdom":1,"perception":1},"bonuses":[]}}
        player=create_player("P","telegram","1","Герой","human",races)
        self.assertEqual(player["registration_scenario_id"],"main_v2");self.assertEqual(player["current_city"],"new_city");self.assertEqual(player["current_zone"],"new_gate")
        self.assertTrue(any(row.get("id")=="constructor_strike" for row in player["skills"]["active"]))
        preview=reg_svc.preview(scenario);self.assertEqual([row["id"] for row in preview["steps"]],["name","race"])

    def test_race_import_from_data(self):
        token = self._token()
        imp = self.client.post("/api/admin/v2/races/import", headers=self._auth(token), json={})
        self.assertEqual(imp.status_code, 200, imp.text)
        self.assertGreaterEqual(imp.json()["report"]["created"], 3)
        human = self.client.get("/api/admin/v2/races/human", headers=self._auth(token))
        self.assertEqual(human.status_code, 200, human.text)
        self.assertEqual(human.json()["item"]["status"], "published")

    def test_external_url_image_rejected(self):
        env = race_svc.store().create("orc", {"race_name": "Орк", "model_image": "https://evil.example/x.png"})
        self.assertFalse(race_svc.validate(env)["ok"])

    def test_published_custom_race_drives_registration_bonuses_and_confirmed_change(self):
        from services.registration_service import load_races, create_player
        from services.race_bonus_service import experience_multiplier, outgoing_damage_multiplier
        from services.race_runtime import request_change, confirm_change, restriction_error
        stats = {"strength": 7, "agility": 8, "endurance": 9, "intelligence": 10, "wisdom": 11, "perception": 12}
        data = {"race_name": "Орк", "player_name": "Орк", "registration_enabled": True,
                "starting_stats": stats, "start_hp": 140, "start_energy": 80,
                "bonuses": [{"id": "learn", "name": "Обучаемость", "type": "experience_percent", "target": "experience", "value": 7},
                            {"id": "rage", "name": "Ярость", "type": "formula", "target": "physical", "formula_id": "race_damage"}],
                "forbidden_locations": ["elf_grove"], "change_allowed": True, "change_via_service": True,
                "change_cost": 10, "change_warning_text": "⚠️ Бонусы персонажа будут полностью заменены.",
                "change_requires_confirmation": True, "preserve_progress": True, "change_success_text": "Вы стали орком."}
        env = race_svc.store().create("orc", data); self.assertTrue(race_svc.validate(env)["ok"], race_svc.validate(env)["errors"])
        race_svc.store().set_status("orc", race_svc.STATUS_PUBLISHED, force=True)
        races = load_races(); self.assertEqual(set(races), {"orc"}); self.assertEqual(races["orc"]["stats"]["dexterity"], 8)
        player = create_player("P", "telegram", "1", "Воин", "orc", races); self.assertEqual(player["hp"], 140)
        self.assertAlmostEqual(experience_multiplier(player), 1.07)
        with patch("services.formula_runtime.evaluate", return_value=9): self.assertAlmostEqual(outgoing_damage_multiplier(player, "physical"), 1.09)
        self.assertIsNotNone(restriction_error(player, "location", "elf_grove"))
        # Для проверки смены сначала возвращаем игроку другую расу.
        player.update({"race_id": "human", "race_name": "Человек", "money": 20})
        preview = request_change(player, "orc"); self.assertIn("⚠️", preview["warning"])
        changed = confirm_change(player, preview["confirmation_token"])
        self.assertEqual(changed["race_id"], "orc"); self.assertEqual(player["money"], 10)
        with self.assertRaises(ValueError): confirm_change(player, preview["confirmation_token"])

    def test_race_change_without_warning_is_invalid(self):
        env = race_svc.store().create("unsafe", {"race_name": "X", "change_allowed": True, "change_requires_confirmation": False})
        result = race_svc.validate(env); self.assertFalse(result["ok"])
        self.assertIn("предупреждения", " ".join(result["errors"]).lower())

    def test_content_cannot_publish_level(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.client.post("/api/admin/v2/levels", headers=self._auth(token), json={"id": "lvl9", "data": {"title": "L9", "level": 9, "exp_required": 1}})
        self.assertEqual(self.client.post("/api/admin/v2/levels/lvl9/publish", headers=self._auth(token), json={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
