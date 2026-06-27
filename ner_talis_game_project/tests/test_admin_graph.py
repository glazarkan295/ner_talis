"""Единый граф админ-панели (ТЗ 12): сбор узлов/рёбер, режимы, ошибки, путь, API."""

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

from admin_graph_api import create_admin_graph_router
from services import admin_graph_service as graph
from services import admin_rbac as rbac
from services import item_constructor_service as items
from services import profile_layout_service as profile
from services import site_content_registry as site
from services import world_content_registry as wcr
from services.admin_panel_service import (
    consume_or_read_admin_session,
    create_admin_panel_activation_token,
)
from storage.json_storage import JsonStorage

# Все сторы, которые трогает граф — изолируем во временные файлы.
_STORE_ENVS = (
    "WORLD_CONTENT_PATH", "ITEM_CONSTRUCTOR_PATH", "RECIPE_CONSTRUCTOR_PATH",
    "EFFECT_CONSTRUCTOR_PATH", "TRAIT_CONSTRUCTOR_PATH", "BLESSING_CONSTRUCTOR_PATH",
    "PHASE_CONSTRUCTOR_PATH", "LEVEL_CONSTRUCTOR_PATH", "SKILL_CONSTRUCTOR_PATH",
    "RACE_CONSTRUCTOR_PATH", "FINE_CONSTRUCTOR_PATH", "CAMP_CONSTRUCTOR_PATH",
    "CITY_CONSTRUCTOR_PATH", "ACHIEVEMENTS_PATH", "ACHIEVEMENT_CATEGORIES_PATH",
    "WORLD_EVENTS_PATH", "GUILDS_PATH", "SITE_CONTENT_PATH", "PROFILE_LAYOUT_PATH",
)


class GraphTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        keys = _STORE_ENVS + ("ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self._saved = {k: os.environ.get(k) for k in keys}
        for env in _STORE_ENVS:
            os.environ[env] = str(base / f"{env.lower()}.json")
        os.environ["ADMIN_ROLES_PATH"] = str(base / "roles.json")
        os.environ["ADMIN_AUDIT_LOG_PATH"] = str(base / "audit.log")
        os.environ["TELEGRAM_ADMIN_USER_IDS"] = "999"
        self.addCleanup(self._restore)
        self.storage = JsonStorage(str(base / "players.json"))
        self._seed()

    def _restore(self):
        rbac.clear_role_overrides() if hasattr(rbac, "clear_role_overrides") else None
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _seed(self):
        # Локация + связанные узлы.
        wcr.create_content(wcr.KIND_LOCATION, "forest", {"name": "Лес", "type": "wild", "short_description": "Тёмный лес"})
        wcr.create_content(wcr.KIND_LOCATION, "cave", {"name": "Пещера", "type": "dungeon", "short_description": "Сырая пещера"})
        wcr.create_content(wcr.KIND_BUTTON, "b_go_cave", {"text": "В пещеру", "owner_location": "forest", "action": "goto_location", "target": "cave"})
        wcr.create_content(wcr.KIND_TRANSITION, "t_forest_cave", {"name": "Тропа", "from_location": "forest", "to_location": "cave"})
        wcr.create_content(wcr.KIND_MOB, "wolf", {"name": "Волк", "type": "beast"})
        wcr.create_content(wcr.KIND_LOCATION_MOB_SPAWN, "sp_wolf", {"location": "forest", "mob_id": "wolf"})
        # Предмет в конструкторе + событие с валидной и битой ссылкой на предмет.
        items.store().create("sword", {"name": "Меч"})
        wcr.create_content(wcr.KIND_EVENT, "ev_find", {"name": "Находка", "text": "Вы нашли предмет", "location": "forest", "given_item": "sword", "required_item": "ghost_item"})
        # Сайт (_kind) + профиль (_kind): страница/блок и вкладка/блок.
        site.store().create("home", {"_kind": "page", "title": "Главная"})
        site.store().create("blk_news", {"_kind": "page_block", "title": "Новости", "page_id": "home"})
        profile.store().create("char_tab", {"_kind": "profile_tab", "name": "Персонаж"})
        profile.store().create("hp_block", {"_kind": "profile_block", "name": "HP", "block_type": "stats", "tab": "char_tab"})


class GraphServiceTest(GraphTestBase):
    def test_full_graph_has_all_nodes(self):
        g = graph.full_graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("location:forest", ids)
        self.assertIn("mob:wolf", ids)
        self.assertIn("item:sword", ids)
        self.assertIn("event:ev_find", ids)

    def test_edges_built(self):
        g = graph.full_graph()
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("button:b_go_cave", "location:cave", "leads_to"), pairs)
        self.assertIn(("location_mob_spawn:sp_wolf", "mob:wolf", "spawns"), pairs)
        self.assertIn(("event:ev_find", "item:sword", "gives_item"), pairs)

    def test_broken_edge_detected(self):
        g = graph.full_graph()
        broken = [e for e in g["edges"] if e.get("broken")]
        self.assertTrue(any(e["to"] == "item:ghost_item" for e in broken))

    def test_type_filter(self):
        g = graph.full_graph(types=["location"])
        self.assertTrue(all(n["type"] == "location" for n in g["nodes"]))

    def test_around_depth(self):
        g = graph.graph_around("location:forest", depth=1)
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("location:forest", ids)
        self.assertIn("event:ev_find", ids)  # сосед через in_location
        self.assertIn("location_mob_spawn:sp_wolf", ids)

    def test_location_graph(self):
        g = graph.location_graph("forest")
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("button:b_go_cave", ids)

    def test_path_between(self):
        g = graph.path_graph("location:forest", "mob:wolf")
        self.assertTrue(g["found"])
        self.assertEqual(g["path"][0], "location:forest")
        self.assertEqual(g["path"][-1], "mob:wolf")

    def test_error_graph_includes_broken(self):
        g = graph.error_graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("event:ev_find", ids)

    def test_node_detail(self):
        d = graph.node_detail("location:forest")
        self.assertIsNotNone(d)
        incoming_from = {e["from"] for e in d["incoming"]}
        self.assertIn("event:ev_find", incoming_from)

    def test_validate_graph(self):
        v = graph.validate_graph()
        self.assertGreaterEqual(v["node_count"], 7)
        self.assertGreaterEqual(len(v["broken_edges"]), 1)

    def test_site_and_profile_nodes_and_edges(self):
        g = graph.full_graph()
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("site_page:home", ids)
        self.assertIn("site_page_block:blk_news", ids)
        self.assertIn("profile_tab:char_tab", ids)
        self.assertIn("profile_block:hp_block", ids)
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("site_page_block:blk_news", "site_page:home", "in_page"), pairs)
        self.assertIn(("profile_block:hp_block", "profile_tab:char_tab", "in_tab"), pairs)

    def test_export_markdown(self):
        g = graph.full_graph()
        md = graph.export_markdown(g)
        self.assertIn("# Схема Нер-Талис", md)
        self.assertIn("location:forest", md)

    def test_export_dispatch(self):
        js = graph.export("full", fmt="json")
        self.assertEqual(js["format"], "json")
        self.assertTrue(js["content"]["nodes"])
        md = graph.export("errors", fmt="md")
        self.assertEqual(md["format"], "md")
        self.assertIsInstance(md["content"], str)


class GraphApiTest(GraphTestBase):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(create_admin_graph_router(lambda: self.storage))
        self.client = TestClient(app)

    def _token(self, uid="999"):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id=uid)
        return consume_or_read_admin_session(self.storage, activation)["token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/admin/v2/graph").status_code, 401)

    def test_editable_edges_listed(self):
        token = self._token()
        r = self.client.get("/api/admin/v2/graph/editable-edges", headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        specs = r.json()["specs"]
        self.assertTrue(any(s["from_type"] == "recipe" and s["edge_type"] == "uses_profession" for s in specs))

    def test_edit_edge_requires_auth(self):
        r = self.client.post("/api/admin/v2/graph/edge", json={"from": "recipe:r1", "edge_type": "uses_profession", "to": "profession:p"})
        self.assertEqual(r.status_code, 401)

    def test_full_and_legend(self):
        token = self._token()
        full = self.client.get("/api/admin/v2/graph", headers=self._auth(token))
        self.assertEqual(full.status_code, 200, full.text)
        self.assertTrue(full.json()["nodes"])
        legend = self.client.get("/api/admin/v2/graph/legend", headers=self._auth(token))
        self.assertEqual(legend.status_code, 200)
        self.assertTrue(any(t["value"] == "location" for t in legend.json()["nodeTypes"]))

    def test_errors_and_validate(self):
        token = self._token()
        err = self.client.get("/api/admin/v2/graph/errors", headers=self._auth(token))
        self.assertEqual(err.status_code, 200, err.text)
        val = self.client.get("/api/admin/v2/graph/validate", headers=self._auth(token))
        self.assertGreaterEqual(len(val.json()["broken_edges"]), 1)

    def test_path_endpoint(self):
        token = self._token()
        r = self.client.get("/api/admin/v2/graph/path", params={"source": "location:forest", "target": "mob:wolf"}, headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["found"])

    def test_node_endpoint(self):
        token = self._token()
        r = self.client.get("/api/admin/v2/graph/node/location/forest", headers=self._auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["node"]["id"], "location:forest")

    def test_export_endpoint(self):
        token = self._token()
        j = self.client.get("/api/admin/v2/graph/export", params={"format": "json"}, headers=self._auth(token))
        self.assertEqual(j.status_code, 200, j.text)
        self.assertEqual(j.json()["format"], "json")
        m = self.client.get("/api/admin/v2/graph/export", params={"format": "md"}, headers=self._auth(token))
        self.assertEqual(m.status_code, 200, m.text)
        self.assertIn("Схема", m.json()["content"])


if __name__ == "__main__":
    unittest.main()
