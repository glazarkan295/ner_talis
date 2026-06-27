"""Конструктор «Подпольное казино» (ТЗ 21 §4): баланс, колесо §4.8, API, RBAC."""

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

from admin_casino_api import create_admin_casino_router
from services import admin_rbac as rbac
from services import casino_constructor_service as casino
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


def _wheel(n):
    return [{"prize_type": "coins", "name": f"p{i}", "chance": 5} for i in range(n)]


class CasinoServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("CASINO_CONSTRUCTOR_PATH")
        os.environ["CASINO_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "casino.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("CASINO_CONSTRUCTOR_PATH", None)
        else:
            os.environ["CASINO_CONSTRUCTOR_PATH"] = self._saved

    def test_valid_casino(self):
        env = casino.store().create("den", {
            "name": "Логово удачи", "location_id": "slums", "enabled": True,
            "min_bet": 10, "max_bet": 1000,
            "games": [
                {"game_type": "dice", "win_chance": 45, "loss_chance": 55, "coefficient": 2},
                {"game_type": "thimbles", "win_chance": 30, "loss_chance": 70, "coefficient": 3},
            ],
            "wheel_enabled": True, "wheel_prizes": _wheel(6), "wheel_empty_chance": 70,
        })
        result = casino.validate(env)
        self.assertTrue(result["ok"], result["errors"])

    def test_loss_must_exceed_win(self):
        env = casino.store().create("bad", {
            "name": "Казино", "games": [{"game_type": "dice", "win_chance": 60, "loss_chance": 40, "coefficient": 2}],
        })
        result = casino.validate(env)
        self.assertFalse(result["ok"])
        self.assertTrue(any("проигрыша должен быть выше" in e.lower() for e in result["errors"]), result["errors"])

    def test_higher_coef_lower_win_warning(self):
        env = casino.store().create("coefcheck", {
            "name": "Казино",
            "games": [
                {"game_type": "dice", "win_chance": 40, "loss_chance": 60, "coefficient": 2},
                {"game_type": "thimbles", "win_chance": 45, "loss_chance": 55, "coefficient": 5},  # выше коэф и выше шанс
            ],
        })
        result = casino.validate(env)
        self.assertTrue(any("выше коэффициент" in w.lower() for w in result["warnings"]), result["warnings"])

    def test_wheel_prize_count_bounds(self):
        too_few = casino.store().create("wf", {"name": "К", "wheel_enabled": True, "wheel_prizes": _wheel(4)})
        self.assertFalse(casino.validate(too_few)["ok"])
        too_many = casino.store().create("wm", {"name": "К", "wheel_enabled": True, "wheel_prizes": _wheel(11)})
        self.assertFalse(casino.validate(too_many)["ok"])

    def test_wheel_chance_sum_over_100(self):
        prizes = [{"prize_type": "coins", "chance": 30} for _ in range(5)]  # сумма 150
        env = casino.store().create("ws", {"name": "К", "wheel_enabled": True, "wheel_prizes": prizes})
        result = casino.validate(env)
        self.assertTrue(any("больше 100" in e.lower() for e in result["errors"]), result["errors"])

    def test_wheel_redistribute_rule(self):
        # §4.8: шанс выпавшего приза уходит в пустой результат, остальные не меняются.
        prizes = [{"name": "a", "chance": 10}, {"name": "b", "chance": 20}, {"name": "c", "chance": 30}]
        res = casino.wheel_redistribute(prizes, 40, 1)  # выпал приз b (20%)
        self.assertEqual(res["empty_chance"], 60)  # 40 + 20
        self.assertEqual(res["prizes"][1]["chance"], 0)
        self.assertEqual(res["prizes"][0]["chance"], 10)  # не изменился
        self.assertEqual(res["prizes"][2]["chance"], 30)  # не изменился

    def test_preview_hides_chances_when_off(self):
        prev = casino.preview({
            "name": "К", "wheel_prizes": _wheel(5), "wheel_show_prizes": True, "wheel_show_chances": False,
        })
        self.assertEqual(prev["name"], "К")
        self.assertIsNone(prev["wheel_prizes"][0]["chance"])


class CasinoApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("CASINO_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["CASINO_CONSTRUCTOR_PATH"] = str(base / "casino.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_casino_router(lambda: self.storage))
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

    def _create(self, token, cid="den", data=None):
        body = {"id": cid, "data": data or {"name": "Казино", "location_id": "slums"}}
        return self.client.post("/api/admin/v2/casino", headers=self._auth(token), json=body)

    def test_meta(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/casino/meta", headers=self._auth(token))
        self.assertEqual(meta.status_code, 200, meta.text)
        body = meta.json()
        games = {g["value"] for g in body["gameTypes"]}
        self.assertIn("wheel", games)
        self.assertEqual(body["wheelMinPrizes"], 5)
        self.assertEqual(body["wheelMaxPrizes"], 10)

    def test_create_validate_publish(self):
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        pub = self.client.post("/api/admin/v2/casino/den/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_wheel_redistribute_endpoint(self):
        token = self._token()
        resp = self.client.post("/api/admin/v2/casino/wheel-redistribute", headers=self._auth(token),
                                json={"prizes": [{"name": "a", "chance": 10}, {"name": "b", "chance": 20}],
                                      "empty_chance": 50, "won_index": 0})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["result"]["empty_chance"], 60)

    def test_content_cannot_publish_readonly_cannot_create(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self._create(token).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/casino/den/publish", headers=self._auth(token), json={}).status_code, 403)
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        ro = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/casino", headers=self._auth(ro)).status_code, 200)
        self.assertEqual(self._create(ro, cid="nope").status_code, 403)


if __name__ == "__main__":
    unittest.main()
