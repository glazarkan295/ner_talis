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

from admin_achievement_api import create_admin_achievement_router
from services import achievement_engine as engine
from services import achievement_service as ach
from services import admin_rbac as rbac
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class AchievementServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in ("ACHIEVEMENTS_PATH", "ACHIEVEMENT_CATEGORIES_PATH")}
        os.environ["ACHIEVEMENTS_PATH"] = str(base / "ach.json")
        os.environ["ACHIEVEMENT_CATEGORIES_PATH"] = str(base / "cat.json")
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_valid_achievement_with_existing_category(self):
        ach.categories().create("combat", {"name": "Бой"})
        env = ach.store().create("hunter_1", {
            "name": "Охотник I", "description": "Победить мобов", "category": "combat",
            "type": "combat", "rarity": "common", "visibility": "open",
            "condition_logic": "all",
            "conditions": [{"type": "kill_mob", "amount": 10}],
            "rewards": [{"type": "experience", "amount": 500}, {"type": "item", "item_id": "money_copper", "amount": 100}],
        })
        result = ach.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_validation_catches_problems(self):
        env = ach.store().create("broken", {
            "type": "weird", "rarity": "ultra", "visibility": "ghost",
            "category": "missing_cat",
            "conditions": [{"type": "nope", "amount": -5}],
            "rewards": [{"type": "item", "item_id": "not_a_real_item_zzz"}],
        })
        result = ach.validate(env)
        self.assertFalse(result["ok"])
        joined = " ".join(result["errors"]).lower()
        self.assertIn("название", joined)
        self.assertIn("категория", joined)
        self.assertIn("тип", joined)
        self.assertIn("не существует", joined)

    def test_n_of_requires_n(self):
        ach.categories().create("misc", {"name": "Разное"})
        env = ach.store().create("multi", {
            "name": "Мульти", "description": "x", "category": "misc",
            "condition_logic": "n_of", "conditions": [{"type": "kill_mob"}, {"type": "catch_fish"}],
        })
        self.assertFalse(ach.validate(env)["ok"])


class AchievementEngineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in ("ACHIEVEMENTS_PATH", "ACHIEVEMENT_CATEGORIES_PATH")}
        os.environ["ACHIEVEMENTS_PATH"] = str(base / "ach.json")
        os.environ["ACHIEVEMENT_CATEGORIES_PATH"] = str(base / "cat.json")
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        ach.categories().create("combat", {"name": "Бой"})
        ach.store().create("hunter", {
            "name": "Охотник", "description": "Победить 3 мобов", "category": "combat",
            "condition_logic": "all", "conditions": [{"type": "kill_mob", "amount": 3}],
            "rewards": [{"type": "coins", "amount": 100}],
        })
        ach.store().set_status("hunter", ach.STATUS_PUBLISHED, force=True)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _player(self):
        races = load_races("data/races.json")
        gid = self.storage.generate_game_id()
        player = create_player(game_id=gid, platform="telegram", external_user_id="55", name="Гер", race_id="human", races=races)
        self.storage.save_new_player(player, "telegram", "55")
        return self.storage.get_player_by_game_id(gid)

    def test_progress_grants_on_completion_and_pays_reward(self):
        player = self._player()
        money_before = int(player.get("money_copper", player.get("money", 0)) or 0)
        self.assertEqual(engine.record_progress(self.storage, player, "kill_mob", 2), [])
        self.assertFalse(engine.is_earned(player, "hunter"))
        newly = engine.record_progress(self.storage, player, "kill_mob", 1)
        self.assertEqual(newly, ["hunter"])
        self.assertTrue(engine.is_earned(player, "hunter"))
        self.assertEqual(int(player.get("money_copper", 0)), money_before + 100)
        # Idempotent: not granted twice.
        self.assertEqual(engine.record_progress(self.storage, player, "kill_mob", 5), [])

    def test_state_event_and_condition_operator(self):
        ach.store().create("veteran", {"name": "Ветеран", "category": "combat", "conditions": [{"type": "reach_level", "operator": "gte", "amount": 10}]})
        ach.store().set_status("veteran", ach.STATUS_PUBLISHED, force=True)
        player = self._player()
        self.assertEqual(engine.record_game_event(player, "reach_level", 9, storage=self.storage), [])
        self.assertEqual(engine.record_game_event(player, "reach_level", 10, storage=self.storage), ["veteran"])

    def test_runtime_unlock_and_effect_rewards_are_applied(self):
        player = self._player()
        lines, errors = engine.apply_rewards(player, [
            {"type": "unlock_location", "object_id": "small_plateau"},
            {"type": "temp_buff", "effect_id": "blessing", "duration_seconds": 60},
            {"type": "event_currency", "currency_id": "summer", "amount": 3},
        ])
        self.assertFalse(errors); self.assertTrue(lines)
        self.assertTrue(player["unlocks"]["small_plateau"])
        self.assertEqual(player["active_effects"][-1]["effect_id"], "blessing")
        self.assertEqual(player["event_currencies"]["summer"], 3)

    def test_ordered_and_repeatable_progress_semantics(self):
        ach.store().create("sequence", {"name": "По порядку", "category": "combat", "condition_logic": "ordered", "conditions": [{"type": "visit_location", "target": "a", "amount": 1}, {"type": "visit_location", "target": "b", "amount": 1}]})
        ach.store().set_status("sequence", ach.STATUS_PUBLISHED, force=True)
        ach.store().create("repeat", {"name": "Повтор", "category": "combat", "repeatable": True, "conditions": [{"type": "kill_mob", "amount": 2}], "rewards": [{"type": "coins", "amount": 1}]})
        ach.store().set_status("repeat", ach.STATUS_PUBLISHED, force=True)
        player = self._player()
        self.assertEqual(engine.record_game_event(player, "visit_location", target="b", storage=self.storage), [])
        engine.record_game_event(player, "visit_location", target="a", storage=self.storage)
        self.assertEqual(engine.record_game_event(player, "visit_location", target="b", storage=self.storage), ["sequence"])
        self.assertNotIn("repeat", engine.record_game_event(player, "kill_mob", storage=self.storage))
        self.assertIn("repeat", engine.record_game_event(player, "kill_mob", storage=self.storage))
        self.assertNotIn("repeat", engine.record_game_event(player, "kill_mob", storage=self.storage))
        self.assertIn("repeat", engine.record_game_event(player, "kill_mob", storage=self.storage))

    def test_manual_grant_and_revoke(self):
        player = self._player()
        self.assertTrue(engine.grant(self.storage, player, "hunter", source="manual", by="t:1", reason="приз"))
        self.assertFalse(engine.grant(self.storage, player, "hunter", source="manual"))  # already
        self.assertTrue(engine.revoke(self.storage, player, "hunter", by="t:1", reason="ошибка"))
        self.assertFalse(engine.is_earned(player, "hunter"))

    def test_hidden_achievement_masked_in_player_view(self):
        ach.store().create("secret", {
            "name": "Секрет", "description": "?", "category": "combat", "visibility": "hidden_until_earned",
            "conditions": [{"type": "find_pearl", "amount": 1}],
        })
        ach.store().set_status("secret", ach.STATUS_PUBLISHED, force=True)
        player = self._player()
        view = engine.player_view(player)
        names = [a["name"] for a in view["inProgress"]]
        self.assertIn("???", names)
        self.assertNotIn("Секрет", names)
    def test_stage_rewards_resets_reveal_and_extended_rewards_are_live(self):
        ach.store().create("staged",{"name":"Ступени","category":"combat","type":"multi_stage","conditions":[{"type":"kill_mob","amount":3}],"reset_on_death":True,"reveal_after_first_progress":True,"stages":[{"stage_id":"first","name":"Первая","required_progress":2,"title_id":"slayer","achievement_points":5,"receive_text":"Первая ступень!"}]})
        ach.store().set_status("staged",ach.STATUS_PUBLISHED,force=True);player=self._player()
        engine.record_game_event(player,"kill_mob",1,storage=self.storage);self.assertTrue(player["achievements"]["progress"]["staged"]["revealed"])
        engine.record_game_event(player,"kill_mob",1,storage=self.storage);self.assertEqual(player["achievement_points"],5);self.assertEqual(player["titles"][-1]["id"],"slayer");self.assertFalse(engine.is_earned(player,"staged"))
        engine.record_game_event(player,"death",1,storage=self.storage);self.assertEqual(player["achievements"]["progress"]["staged"]["counts"],{})
        lines,errors=engine.apply_rewards(player,[{"type":"reputation","object_id":"guards","amount":3},{"type":"unlock_market","object_id":"black"},{"type":"discount","object_id":"tavern","amount":10},{"type":"system_flag","object_id":"hero","value":True},{"type":"special_button","object_id":"portal","label":"Портал"}])
        self.assertFalse(errors);self.assertTrue(lines);self.assertEqual(player["reputations"]["guards"],3);self.assertTrue(player["unlocks"]["black"]);self.assertEqual(player["achievement_economy_bonuses"]["discount"]["tavern"]["value"],10);self.assertTrue(player["system_flags"]["hero"]);self.assertEqual(player["achievement_buttons"][-1]["id"],"portal")


class AchievementApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("ACHIEVEMENTS_PATH", "ACHIEVEMENT_CATEGORIES_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["ACHIEVEMENTS_PATH"] = str(base / "ach.json")
        os.environ["ACHIEVEMENT_CATEGORIES_PATH"] = str(base / "cat.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_achievement_router(lambda: self.storage))
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

    def _make_category(self, token, cid="combat"):
        return self.client.post("/api/admin/v2/achievements/categories", headers=self._auth(token), json={"id": cid, "data": {"name": "Бой"}})

    def test_meta_and_create_publish_flow(self):
        token = self._token("999")
        self.assertEqual(self._make_category(token).status_code, 200)
        meta = self.client.get("/api/admin/v2/achievements/meta", headers=self._auth(token)).json()
        self.assertIn("kill_mob", meta["conditionTypes"])
        self.assertTrue(any(c["id"] == "combat" for c in meta["categories"]))

        created = self.client.post("/api/admin/v2/achievements", headers=self._auth(token), json={"id": "hunter_1", "data": {
            "name": "Охотник I", "description": "x", "category": "combat",
            "conditions": [{"type": "kill_mob", "amount": 10}],
        }})
        self.assertEqual(created.status_code, 200, created.text)
        publish = self.client.post("/api/admin/v2/achievements/hunter_1/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        self.assertEqual(publish.json()["item"]["status"], "published")
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertIn("achievement.publish", dangerous)

    def test_publish_blocked_without_conditions(self):
        token = self._token("999")
        self._make_category(token)
        self.client.post("/api/admin/v2/achievements", headers=self._auth(token), json={"id": "bad", "data": {"name": "Плохое", "category": "combat"}})
        publish = self.client.post("/api/admin/v2/achievements/bad/publish", headers=self._auth(token), json={})
        self.assertEqual(publish.status_code, 400, publish.text)
        got = self.client.get("/api/admin/v2/achievements/bad", headers=self._auth(token)).json()["item"]
        self.assertEqual(got["status"], "error")

    def test_content_can_draft_but_not_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token("999")
        self.assertEqual(self._make_category(token).status_code, 200)  # content manages categories
        self.assertEqual(self.client.post("/api/admin/v2/achievements", headers=self._auth(token), json={"id": "a1", "data": {"name": "A", "category": "combat", "conditions": [{"type": "kill_mob"}]}}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/achievements/a1/publish", headers=self._auth(token), json={}).status_code, 403)

    def test_read_only_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token("999")
        self.assertEqual(self.client.post("/api/admin/v2/achievements", headers=self._auth(token), json={"id": "ach_x", "data": {"name": "x"}}).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/v2/achievements", headers=self._auth(token)).status_code, 200)

    def test_content_cannot_edit_published_achievement(self):
        # Codex P2: правка опубликованного достижения уходит в игру немедленно
        # (рантайм читает published), поэтому требует прав публикации.
        owner = self._token("999")
        self._published_achievement(owner, aid="hero")
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        content_token = self._token("999")
        edit_published = self.client.put(
            "/api/admin/v2/achievements/hero",
            headers=self._auth(content_token), json={"data": {"name": "Изменено"}},
        )
        self.assertEqual(edit_published.status_code, 403, edit_published.text)
        # Черновик content править может (edit).
        self.client.post("/api/admin/v2/achievements", headers=self._auth(content_token), json={
            "id": "draft_ach",
            "data": {"name": "D", "category": "combat", "conditions": [{"type": "kill_mob"}]},
        })
        edit_draft = self.client.put(
            "/api/admin/v2/achievements/draft_ach",
            headers=self._auth(content_token), json={"data": {"name": "D2"}},
        )
        self.assertEqual(edit_draft.status_code, 200, edit_draft.text)

    def _make_player(self):
        races = load_races("data/races.json")
        gid = self.storage.generate_game_id()
        player = create_player(game_id=gid, platform="telegram", external_user_id="77", name="Игр", race_id="human", races=races)
        self.storage.save_new_player(player, "telegram", "77")
        return gid

    def _published_achievement(self, token, aid="hero"):
        self._make_category(token)
        self.client.post("/api/admin/v2/achievements", headers=self._auth(token), json={"id": aid, "data": {"name": "Герой", "description": "x", "category": "combat", "conditions": [{"type": "reach_level", "amount": 1}]}})
        self.client.post(f"/api/admin/v2/achievements/{aid}/publish", headers=self._auth(token), json={})

    def test_manual_grant_revoke_and_progress_api(self):
        token = self._token("999")
        self._published_achievement(token)
        gid = self._make_player()
        grant = self.client.post("/api/admin/v2/achievements/hero/grant", headers=self._auth(token), json={"game_id": gid, "reason": "приз"})
        self.assertEqual(grant.status_code, 200, grant.text)
        self.assertTrue(grant.json()["granted"])
        progress = self.client.get(f"/api/admin/v2/achievements/players/{gid}", headers=self._auth(token)).json()["progress"]
        self.assertTrue(any(a["id"] == "hero" and a["earned"] for a in progress["achievements"]))
        revoke = self.client.post("/api/admin/v2/achievements/hero/revoke", headers=self._auth(token), json={"game_id": gid, "reason": "откат"})
        self.assertTrue(revoke.json()["revoked"])
        # Audited as dangerous manual actions.
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertTrue({"achievement.grant_manual", "achievement.revoke_manual"} <= dangerous)

    def test_support_cannot_grant_manual(self):
        rbac.set_role_override("telegram", "999", rbac.SUPPORT)
        token = self._token("999")
        gid = self._make_player()
        # support has view_player_progress but not grant_manual.
        self.assertEqual(self.client.get(f"/api/admin/v2/achievements/players/{gid}", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/achievements/hero/grant", headers=self._auth(token), json={"game_id": gid}).status_code, 403)

    def test_usage_lists_players_and_delete_is_blocked_by_saved_progress(self):
        token=self._token("999");self._published_achievement(token,"protected");gid=self._make_player();player=self.storage.get_player_by_game_id(gid);player["achievements"]={"earned":{},"progress":{"protected":{"counts":{"0":1}}},"history":[]};self.storage.update_player(player)
        usage=self.client.get("/api/admin/v2/achievements/protected/usage",headers=self._auth(token));self.assertEqual(usage.status_code,200,usage.text);self.assertIn(gid,usage.json()["usage"]["players_progress"])
        deleted=self.client.request("DELETE","/api/admin/v2/achievements/protected",headers=self._auth(token),json={"confirm":"protected","reason":"cleanup"});self.assertEqual(deleted.status_code,409,deleted.text);self.assertIn("прогресс",deleted.text.lower())


if __name__ == "__main__":
    unittest.main()
