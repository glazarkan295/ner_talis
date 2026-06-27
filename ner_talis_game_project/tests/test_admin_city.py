"""Конструктор города и крепости (ТЗ §4–§6): валидация + дерево + API + RBAC."""

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

from admin_city_api import create_admin_city_router
from services import admin_rbac as rbac
from services import city_constructor_service as city
from services.admin_audit import read_admin_audit_records
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage


class CityServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("CITY_CONSTRUCTOR_PATH")
        os.environ["CITY_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "city.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("CITY_CONSTRUCTOR_PATH", None)
        else:
            os.environ["CITY_CONSTRUCTOR_PATH"] = self._saved

    def test_node_type_enum(self):
        bad = city.store().create("n_bad", {"_kind": "city_node", "name": "X", "node_type": "spaceport"})
        self.assertFalse(city.validate("city_node", bad)["ok"])
        ok = city.store().create("seldar", {"_kind": "city_node", "name": "Селдар", "node_type": "city"})
        self.assertTrue(city.validate("city_node", ok)["ok"], city.validate("city_node", ok)["errors"])

    def test_button_action_and_target(self):
        bad = city.store().create("b_bad", {"_kind": "city_button", "label": "Идти", "action": "goto_node"})  # no target
        res = city.validate("city_button", bad)
        self.assertFalse(res["ok"])
        self.assertTrue(any("целевой узел" in e.lower() for e in res["errors"]))
        ok = city.store().create("b_ok", {"_kind": "city_button", "label": "Идти", "action": "goto_node", "node_id": "seldar", "target_node_id": "market"})
        self.assertTrue(city.validate("city_button", ok)["ok"], city.validate("city_button", ok)["errors"])

    def test_shop_item_bounds(self):
        bad = city.store().create("s_bad", {"_kind": "city_shop_item", "item_id": "sword", "price_buy": -5, "appear_chance": 250, "currency": "doubloon"})
        res = city.validate("city_shop_item", bad)
        self.assertFalse(res["ok"])
        joined = " ".join(res["errors"])
        self.assertIn("price_buy", joined)
        self.assertIn("Шанс появления", joined)
        self.assertIn("валюта", joined.lower())

    def test_service_and_criminal(self):
        srv = city.store().create("forge1", {"_kind": "city_service", "name": "Кузница", "service_kind": "forge", "success_chance": 90})
        self.assertTrue(city.validate("city_service", srv)["ok"], city.validate("city_service", srv)["errors"])
        crim = city.store().create("bm", {"_kind": "criminal_zone", "name": "Чёрный рынок", "raid_chance": 15, "fine_amount": 500})
        self.assertTrue(city.validate("criminal_zone", crim)["ok"], city.validate("criminal_zone", crim)["errors"])
        crim_bad = city.store().create("bm_bad", {"_kind": "criminal_zone", "name": "X", "raid_chance": 150})
        self.assertFalse(city.validate("criminal_zone", crim_bad)["ok"])

    def test_runtime_node_view_published_only(self):
        from services import city_runtime
        city.store().create("seldar", {"_kind": "city_node", "name": "Селдар", "node_type": "city"})
        city.store().set_status("seldar", city.STATUS_PUBLISHED, force=True)
        city.store().create("market", {"_kind": "city_node", "name": "Рынок", "node_type": "market", "parent_id": "seldar", "order": 1})
        city.store().set_status("market", city.STATUS_PUBLISHED, force=True)
        city.store().create("draft_q", {"_kind": "city_node", "name": "Черновик", "node_type": "quarter", "parent_id": "seldar"})  # не опубликован
        city.store().create("to_market", {"_kind": "city_button", "label": "В рынок", "action": "goto_node", "node_id": "seldar", "target_node_id": "market"})
        city.store().set_status("to_market", city.STATUS_PUBLISHED, force=True)
        city.store().create("sword", {"_kind": "city_shop_item", "item_id": "iron_sword", "node_id": "market"})
        city.store().set_status("sword", city.STATUS_PUBLISHED, force=True)

        view = city_runtime.node_runtime_view("seldar")
        self.assertEqual(view["name"], "Селдар")
        self.assertEqual([b["label"] for b in view["buttons"]], ["В рынок"])
        # Только опубликованные дети: market есть, черновик — нет.
        self.assertEqual([c["id"] for c in view["children"]], ["market"])
        market_view = city_runtime.node_runtime_view("market")
        self.assertEqual([s["item_id"] for s in market_view["shop_items"]], ["iron_sword"])
        # Неопубликованный/несуществующий узел → None.
        self.assertIsNone(city_runtime.node_runtime_view("draft_q"))
        self.assertIsNone(city_runtime.node_runtime_view("nope"))
        # Корневые узлы — опубликованный город.
        self.assertIn("seldar", [r["id"] for r in city_runtime.root_nodes()])

    def test_runtime_flag_default_off(self):
        from services import city_runtime
        self.assertFalse(city_runtime.live_enabled())

    def test_looks_like_game_action(self):
        # 16-TZ §4: короткие однострочные подписи кнопок — игровые действия,
        # длинный/многострочный свободный текст — нет (не грузит city runtime).
        from services import city_service
        self.assertTrue(city_service.looks_like_game_action("В город"))
        self.assertTrue(city_service.looks_like_game_action("🏪 На рынок"))
        self.assertFalse(city_service.looks_like_game_action(""))
        self.assertFalse(city_service.looks_like_game_action("строка\nещё строка"))
        self.assertFalse(city_service.looks_like_game_action("привет " * 30))

    def test_try_handle_button_scoped_by_node(self):
        # Codex P2: одинаковая подпись «Назад» на разных узлах ведёт в разные места.
        from services import city_runtime
        for nid in ("hub", "market", "tavern"):
            city.store().create(nid, {"_kind": "city_node", "name": nid.title(), "node_type": "quarter"})
            city.store().set_status(nid, city.STATUS_PUBLISHED, force=True)
        city.store().create("b_market_back", {"_kind": "city_button", "label": "Назад", "action": "goto_node", "node_id": "market", "target_node_id": "hub"})
        city.store().set_status("b_market_back", city.STATUS_PUBLISHED, force=True)
        city.store().create("b_tavern_back", {"_kind": "city_button", "label": "Назад", "action": "goto_node", "node_id": "tavern", "target_node_id": "market"})
        city.store().set_status("b_tavern_back", city.STATUS_PUBLISHED, force=True)
        saved = os.environ.get("CITY_CONSTRUCTOR_LIVE")
        try:
            os.environ["CITY_CONSTRUCTOR_LIVE"] = "1"
            # «Назад» на рынке → hub; «Назад» в таверне → market (разные цели).
            back_market = city_runtime.try_handle("Назад", current_node_id="market")
            back_tavern = city_runtime.try_handle("Назад", current_node_id="tavern")
            self.assertIn("Hub", back_market["text"])
            self.assertIn("Market", back_tavern["text"])
            # 15-CODEX §1: возвращается node_id целевого узла (для сохранения контекста).
            self.assertEqual(back_market["node_id"], "hub")
            self.assertEqual(back_tavern["node_id"], "market")
        finally:
            if saved is None:
                os.environ.pop("CITY_CONSTRUCTOR_LIVE", None)
            else:
                os.environ["CITY_CONSTRUCTOR_LIVE"] = saved

    def test_try_handle_respects_flag_and_matches_published(self):
        from services import city_runtime
        city.store().create("seldar", {"_kind": "city_node", "name": "Селдар", "node_type": "city", "description": "Столица."})
        city.store().set_status("seldar", city.STATUS_PUBLISHED, force=True)
        city.store().create("market", {"_kind": "city_node", "name": "Рынок", "node_type": "market", "parent_id": "seldar"})
        city.store().set_status("market", city.STATUS_PUBLISHED, force=True)
        city.store().create("to_market", {"_kind": "city_button", "label": "На рынок", "action": "goto_node", "node_id": "seldar", "target_node_id": "market"})
        city.store().set_status("to_market", city.STATUS_PUBLISHED, force=True)

        saved = os.environ.get("CITY_CONSTRUCTOR_LIVE")
        try:
            os.environ["CITY_CONSTRUCTOR_LIVE"] = ""
            self.assertIsNone(city_runtime.try_handle("Селдар"))  # флаг выкл → легаси
            os.environ["CITY_CONSTRUCTOR_LIVE"] = "1"
            self.assertTrue(city_runtime.live_enabled())
            by_name = city_runtime.try_handle("Селдар")
            self.assertIsNotNone(by_name)
            self.assertIn("Селдар", by_name["text"])
            self.assertIn(["В город"], by_name["buttons"])
            # Переход по подписи кнопки ведёт к целевому узлу «Рынок».
            by_button = city_runtime.try_handle("На рынок")
            self.assertIsNotNone(by_button)
            self.assertIn("Рынок", by_button["text"])
            # Неизвестное действие → None (легаси-навигация).
            self.assertIsNone(city_runtime.try_handle("абракадабра"))
        finally:
            if saved is None:
                os.environ.pop("CITY_CONSTRUCTOR_LIVE", None)
            else:
                os.environ["CITY_CONSTRUCTOR_LIVE"] = saved

    def test_where_used(self):
        city.store().create("seldar", {"_kind": "city_node", "name": "Селдар", "node_type": "city"})
        city.store().create("market", {"_kind": "city_node", "name": "Рынок", "node_type": "market", "parent_id": "seldar"})
        city.store().create("to_market", {"_kind": "city_button", "name": "В рынок", "label": "Рынок", "action": "goto_node", "node_id": "seldar", "target_node_id": "market"})
        city.store().create("sword", {"_kind": "city_shop_item", "item_id": "iron_sword", "node_id": "market"})
        used = city.where_used("market")
        ids = {u["id"] for u in used}
        self.assertIn("to_market", ids)   # переход ведёт сюда
        self.assertIn("sword", ids)       # товар привязан к узлу
        # «market» сам — дочерний у seldar: where_used(seldar) включает market.
        self.assertIn("market", {u["id"] for u in city.where_used("seldar")})
        self.assertEqual(city.where_used("nonexistent"), [])

    def test_build_tree_nesting(self):
        city.store().create("seldar", {"_kind": "city_node", "name": "Селдар", "node_type": "city"})
        city.store().create("port", {"_kind": "city_node", "name": "Портовый квартал", "node_type": "quarter", "parent_id": "seldar", "order": 2})
        city.store().create("center", {"_kind": "city_node", "name": "Центральная площадь", "node_type": "square", "parent_id": "seldar", "order": 1})
        city.store().create("pier", {"_kind": "city_node", "name": "Причал", "node_type": "pier", "parent_id": "port"})
        tree = city.build_tree()
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]["id"], "seldar")
        # Дети отсортированы по order: center(1) перед port(2).
        self.assertEqual([c["id"] for c in tree[0]["children"]], ["center", "port"])
        port = next(c for c in tree[0]["children"] if c["id"] == "port")
        self.assertEqual([c["id"] for c in port["children"]], ["pier"])


class CityApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = ("CITY_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["CITY_CONSTRUCTOR_PATH"] = str(base / "city.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        app = FastAPI()
        app.include_router(create_admin_city_router(lambda: self.storage))
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

    def test_meta_and_node_publish_and_tree(self):
        token = self._token()
        meta = self.client.get("/api/admin/v2/city/meta", headers=self._auth(token)).json()
        self.assertIn("city_node", meta["kinds"])
        self.assertIn("townhall", meta["nodeTypes"])
        create = self.client.post("/api/admin/v2/city/city_node", headers=self._auth(token), json={"id": "seldar", "data": {"name": "Селдар", "node_type": "city"}})
        self.assertEqual(create.status_code, 200, create.text)
        publish = self.client.post("/api/admin/v2/city/city_node/seldar/publish", headers=self._auth(token), json={"reason": "релиз"})
        self.assertEqual(publish.status_code, 200, publish.text)
        tree = self.client.get("/api/admin/v2/city/tree", headers=self._auth(token)).json()["tree"]
        self.assertEqual(tree[0]["id"], "seldar")
        dangerous = {r["action"] for r in read_admin_audit_records(dangerous_only=True, dangerous_actions=rbac.DANGEROUS_ACTIONS)}
        self.assertIn("city.publish", dangerous)

    def test_kind_filter_and_delete_confirm(self):
        token = self._token()
        self.client.post("/api/admin/v2/city/city_node", headers=self._auth(token), json={"id": "node1", "data": {"name": "Узел", "node_type": "quarter"}})
        self.client.post("/api/admin/v2/city/city_button", headers=self._auth(token), json={"id": "btn1", "data": {"label": "Кнопка", "action": "go_back", "node_id": "node1"}})
        nodes = self.client.get("/api/admin/v2/city/city_node", headers=self._auth(token)).json()["items"]
        self.assertEqual([i["id"] for i in nodes], ["node1"])
        self.assertEqual(self.client.request("DELETE", "/api/admin/v2/city/city_button/btn1", headers=self._auth(token), json={"confirm": "no"}).status_code, 400)
        ok = self.client.request("DELETE", "/api/admin/v2/city/city_button/btn1", headers=self._auth(token), json={"confirm": "btn1", "reason": "уборка"})
        self.assertEqual(ok.status_code, 200, ok.text)

    def test_content_drafts_but_not_publish(self):
        rbac.set_role_override("telegram", "999", rbac.CONTENT)
        token = self._token()
        self.assertEqual(self.client.post("/api/admin/v2/city/city_node", headers=self._auth(token), json={"id": "n2", "data": {"name": "Узел", "node_type": "quarter"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/city/city_node/n2/publish", headers=self._auth(token), json={}).status_code, 403)

    def test_read_only_view_only(self):
        rbac.set_role_override("telegram", "999", rbac.READ_ONLY)
        token = self._token()
        self.assertEqual(self.client.get("/api/admin/v2/city/city_node", headers=self._auth(token)).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/v2/city/city_node", headers=self._auth(token), json={"id": "nx", "data": {"name": "X", "node_type": "city"}}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
