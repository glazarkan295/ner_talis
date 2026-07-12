"""Конструктор формул (ТЗ 13 §2): безопасный вычислитель, валидация, тест, API."""

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

from admin_formula_api import create_admin_formula_router
from services import formula_constructor_service as fx
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class EvaluatorTest(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(fx.evaluate_expression("2 + 3 * 4", {}), 14)

    def test_variables(self):
        self.assertEqual(fx.evaluate_expression("base_amount * multiplier", {"base_amount": 10, "multiplier": 2.5}), 25)

    def test_functions(self):
        self.assertEqual(fx.evaluate_expression("min(100, base_chance)", {"base_chance": 150}), 100)
        self.assertEqual(fx.evaluate_expression("floor(7 / 2)", {}), 3)

    def test_conditional(self):
        self.assertEqual(fx.evaluate_expression("100 if player_level > 10 else 50", {"player_level": 12}), 100)

    def test_division_by_zero(self):
        with self.assertRaises(fx.FormulaError):
            fx.evaluate_expression("5 / 0", {})

    def test_unknown_variable(self):
        with self.assertRaises(fx.FormulaError):
            fx.evaluate_expression("ghost + 1", {})

    def test_forbidden_construct(self):
        with self.assertRaises(fx.FormulaError):
            fx.evaluate_expression("__import__('os')", {})


class ValidateTest(unittest.TestCase):
    def _v(self, data):
        return fx.validate({"data": data})

    def test_valid(self):
        r = self._v({"name": "Опыт", "category": "exp", "expression": "base_amount * player_level",
                     "variables": [{"key": "base_amount"}, {"key": "player_level"}]})
        self.assertTrue(r["ok"], r["errors"])

    def test_empty_expression(self):
        self.assertFalse(self._v({"name": "X", "expression": ""})["ok"])

    def test_unknown_variable(self):
        r = self._v({"name": "X", "expression": "mystery * 2"})
        self.assertFalse(r["ok"])
        self.assertTrue(any("mystery" in e for e in r["errors"]))

    def test_catalog_variable_allowed(self):
        # player_level из стандартного каталога — без объявления.
        self.assertTrue(self._v({"name": "X", "expression": "player_level + 1"})["ok"])

    def test_min_gt_max(self):
        r = self._v({"name": "X", "expression": "base_amount", "variables": [{"key": "base_amount"}],
                     "min_result": 10, "max_result": 5})
        self.assertFalse(r["ok"])


class TestFormulaTest(unittest.TestCase):
    def test_constraints_floor_and_clamp(self):
        data = {"expression": "base_amount * multiplier", "rounding": "floor",
                "max_result": 50, "variables": [{"key": "base_amount", "default": 10}, {"key": "multiplier", "default": 1}]}
        res = fx.test_formula(data, {"base_amount": 9, "multiplier": 2.7})  # 24.3 → floor 24
        self.assertTrue(res["ok"])
        self.assertEqual(res["result"], 24)

    def test_percent_clamp(self):
        data = {"expression": "base_chance", "is_percent": True, "variables": [{"key": "base_chance", "default": 0}]}
        res = fx.test_formula(data, {"base_chance": 250})
        self.assertEqual(res["result"], 100)

    def test_defaults_used(self):
        data = {"expression": "base_amount + 5", "variables": [{"key": "base_amount", "default": 7}]}
        res = fx.test_formula(data, {})
        self.assertEqual(res["result"], 12)


class FormulaRuntimeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old = os.environ.get("FORMULA_CONSTRUCTOR_PATH")
        os.environ["FORMULA_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "formulas.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._old is None:
            os.environ.pop("FORMULA_CONSTRUCTOR_PATH", None)
        else:
            os.environ["FORMULA_CONSTRUCTOR_PATH"] = self._old

    def test_only_published_formula_is_live_and_constraints_apply(self):
        from services.formula_runtime import evaluate
        fx.store().create("live", {"name": "Live", "expression": "base_amount * multiplier",
                                     "rounding": "floor", "max_result": 20,
                                     "variables": [{"key": "base_amount", "default": 3},
                                                   {"key": "multiplier", "default": 2}]})
        self.assertEqual(evaluate("live", {"base_amount": 8}, default=99), 99)
        fx.store().set_status("live", fx.STATUS_PUBLISHED, force=True)
        self.assertEqual(evaluate("live", {"base_amount": 8, "multiplier": 2.9}), 20)

    def test_missing_variable_or_formula_falls_back(self):
        from services.formula_runtime import evaluate
        fx.store().create("bad", {"name": "Bad", "expression": "base_amount + player_level"})
        fx.store().set_status("bad", fx.STATUS_PUBLISHED, force=True)
        self.assertEqual(evaluate("bad", {"base_amount": 5}, default=7), 7)
        self.assertEqual(evaluate("absent", {}, default=11), 11)


class FormulaBindingTest(unittest.TestCase):
    """Привязка формул к механикам (ТЗ 13 §2.8): where_used + ребро в графе."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._keys = ("FORMULA_CONSTRUCTOR_PATH", "LEVEL_CONSTRUCTOR_PATH")
        self._saved = {k: os.environ.get(k) for k in self._keys}
        for k in self._keys:
            os.environ[k] = str(base / f"{k.lower()}.json")
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_where_used_and_graph_edge(self):
        from services import level_constructor_service as levels
        from services import admin_graph_service as graph
        fx.store().create("exp_curve", {"name": "Кривая опыта", "expression": "base_amount * 2",
                                        "variables": [{"key": "base_amount"}]})
        levels.store().create("lvl5", {"title": "Уровень 5", "level": 5, "exp_required": 100,
                                       "exp_formula_id": "exp_curve"})
        used = fx.where_used("exp_curve")
        self.assertTrue(any(r["id"] == "lvl5" for r in used), used)
        g = graph.full_graph()
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("level:lvl5", "formula:exp_curve", "uses_formula"), pairs)


class FormulaApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("FORMULA_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["FORMULA_CONSTRUCTOR_PATH"] = str(base / "formulas.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_formula_router(lambda: self.storage))
        self.client = TestClient(app)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _token(self):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id="999")
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_meta(self):
        token = self._token()
        r = self.client.get("/api/admin/v2/formulas/meta", headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(any(c["value"] == "exp" for c in r.json()["categories"]))
        self.assertIn("min", r.json()["functions"])

    def test_crud_and_publish(self):
        token = self._token()
        c = self.client.post("/api/admin/v2/formulas", headers=self._auth(token), json={
            "id": "mob_exp", "data": {"name": "Опыт за моба", "category": "exp",
                                      "expression": "base_amount * mob_level",
                                      "variables": [{"key": "base_amount"}, {"key": "mob_level"}]}})
        self.assertEqual(c.status_code, 200, c.text)
        pub = self.client.post("/api/admin/v2/formulas/mob_exp/publish", headers=self._auth(token), json={})
        self.assertEqual(pub.status_code, 200, pub.text)
        self.assertEqual(pub.json()["item"]["status"], "published")

    def test_test_endpoint(self):
        token = self._token()
        self.client.post("/api/admin/v2/formulas", headers=self._auth(token), json={
            "id": "f1", "data": {"name": "F1", "expression": "base_amount * 2", "rounding": "floor",
                                 "variables": [{"key": "base_amount", "default": 3}]}})
        r = self.client.post("/api/admin/v2/formulas/f1/test", headers=self._auth(token), json={"values": {"base_amount": 7}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["test"]["result"], 14)

    def test_evaluate_endpoint(self):
        token = self._token()
        r = self.client.post("/api/admin/v2/formulas/evaluate", headers=self._auth(token), json={
            "data": {"expression": "min(100, base_chance)", "variables": [{"key": "base_chance"}]},
            "values": {"base_chance": 250}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["test"]["result"], 100)

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/formulas/meta").status_code, 401)


if __name__ == "__main__":
    unittest.main()
