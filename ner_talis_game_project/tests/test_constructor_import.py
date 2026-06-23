"""Импорт-миграция существующего контента в конструкторы (ТЗ §3).

Идемпотентность, публикация, маркировка imported и защита рукотворных записей.
Сторы изолируются через ENV (ITEM_CONSTRUCTOR_PATH / WORLD_CONTENT_PATH).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import constructor_import as ci


class ConstructorImportTest(unittest.TestCase):
    def setUp(self):
        self._items = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._world = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._effects = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._city = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._ach = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._achcat = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._fines = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._recipes = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        os.environ["FINE_CONSTRUCTOR_PATH"] = self._fines
        os.environ["RECIPE_CONSTRUCTOR_PATH"] = self._recipes
        os.environ["ITEM_CONSTRUCTOR_PATH"] = self._items
        os.environ["WORLD_CONTENT_PATH"] = self._world
        os.environ["EFFECT_CONSTRUCTOR_PATH"] = self._effects
        os.environ["CITY_CONSTRUCTOR_PATH"] = self._city
        os.environ["ACHIEVEMENTS_PATH"] = self._ach
        os.environ["ACHIEVEMENT_CATEGORIES_PATH"] = self._achcat

    def tearDown(self):
        os.environ.pop("ITEM_CONSTRUCTOR_PATH", None)
        os.environ.pop("WORLD_CONTENT_PATH", None)
        os.environ.pop("EFFECT_CONSTRUCTOR_PATH", None)
        os.environ.pop("CITY_CONSTRUCTOR_PATH", None)
        os.environ.pop("ACHIEVEMENTS_PATH", None)
        os.environ.pop("ACHIEVEMENT_CATEGORIES_PATH", None)
        os.environ.pop("FINE_CONSTRUCTOR_PATH", None)
        os.environ.pop("RECIPE_CONSTRUCTOR_PATH", None)
        for base in (self._items, self._world, self._effects, self._city, self._ach, self._achcat, self._fines, self._recipes):
            for suffix in ("", ".lock", ".tmp"):
                try:
                    os.unlink(base + suffix)
                except OSError:
                    pass

    def test_safe_id(self):
        self.assertEqual(ci.safe_constructor_id("Wolf Fang!"), "wolf_fang")
        self.assertEqual(ci.safe_constructor_id("dried_meat"), "dried_meat")
        self.assertEqual(ci.safe_constructor_id("!!"), "")

    def test_import_items_published_marked_idempotent(self):
        from services import item_constructor_service as ics

        r1 = ci.import_items()
        self.assertGreater(r1["created"], 0)
        items = ics.store().list()
        self.assertTrue(items)
        self.assertTrue(any(i["status"] == "published" for i in items))
        self.assertTrue(any((i.get("data") or {}).get("imported") for i in items))
        # Повторный запуск ничего не создаёт (идемпотентно).
        r2 = ci.import_items()
        self.assertEqual(r2["created"], 0)
        self.assertEqual(r2["skipped"], r1["created"])

    def test_import_mobs_published_idempotent(self):
        from services import world_content_registry as wcr

        r1 = ci.import_mobs()
        self.assertGreater(r1["created"], 0)
        mobs = wcr.list_content(wcr.KIND_MOB)
        self.assertTrue(mobs)
        self.assertTrue(any(m["status"] == "published" for m in mobs))
        self.assertTrue(any((m.get("data") or {}).get("imported") for m in mobs))
        r2 = ci.import_mobs()
        self.assertEqual(r2["created"], 0)

    def test_overwrite_does_not_touch_manual_entries(self):
        from services.pve_battle_service import BATTLE_MOB_CATALOGS
        from services import world_content_registry as wcr

        key = ""
        for catalog in BATTLE_MOB_CATALOGS.values():
            for mob_key in catalog:
                key = ci.safe_constructor_id(mob_key)
                if key:
                    break
            if key:
                break
        self.assertTrue(key)
        # Рукотворная запись (без imported) с тем же id — импорт её не трогает.
        wcr.create_content(wcr.KIND_MOB, key, {"name": "АДМИН-МОБ", "type": "beast", "hp": 999})
        report = ci.import_mobs(overwrite=True)
        self.assertGreaterEqual(report["skipped"], 1)
        got = wcr.get_content(wcr.KIND_MOB, key)
        self.assertEqual(got["data"]["name"], "АДМИН-МОБ")

    def test_import_all_selects_kinds(self):
        result = ci.import_all(["mob"])
        kinds = [r["kind"] for r in result["reports"]]
        self.assertEqual(kinds, ["mob"])

    def test_import_effects_published_idempotent(self):
        from services import effect_constructor_service as ecs

        r1 = ci.import_effects()
        self.assertGreater(r1["created"], 0)
        items = ecs.store().list()
        self.assertTrue(any(i["status"] == "published" for i in items))
        self.assertTrue(any((i.get("data") or {}).get("imported") for i in items))
        # Известные проклятия в сиде.
        self.assertIsNotNone(ecs.store().get("ancient_curse"))
        r2 = ci.import_effects()
        self.assertEqual(r2["created"], 0)

    def test_effect_where_used(self):
        from services import effect_constructor_service as ecs
        from services import world_content_registry as wcr

        wcr.create_content(wcr.KIND_MOB, "mob_x", {"name": "X", "type": "beast", "hp": 10})
        wcr.create_content(wcr.KIND_MOB_EFFECT, "me_poison", {
            "name": "Яд волка", "mob_id": "mob_x", "effect_id": "poison", "chance": 20,
        })
        used = ecs.where_used("poison")
        self.assertTrue(any(u["id"] == "me_poison" for u in used))
        self.assertEqual(ecs.where_used("nonexistent_effect"), [])


    def test_import_locations_published(self):
        from services import world_content_registry as wcr

        report = ci.import_locations()
        self.assertGreaterEqual(report["found"], 4)
        self.assertGreater(report["created"], 0)
        locs = wcr.list_content(wcr.KIND_LOCATION)
        self.assertTrue(any(loc["status"] == "published" for loc in locs))
        self.assertTrue(any((loc.get("data") or {}).get("imported") for loc in locs))
        # Идемпотентность: повтор в режиме «new» ничего не создаёт.
        r2 = ci.import_locations(mode="new")
        self.assertEqual(r2["created"], 0)
        self.assertEqual(r2["skipped"], r2["found"])

    def test_import_events_link_location(self):
        from services import world_content_registry as wcr

        ci.import_locations()
        report = ci.import_events()
        self.assertGreater(report["created"], 0)
        evs = wcr.list_content(wcr.KIND_EVENT)
        self.assertTrue(all((e.get("data") or {}).get("location") for e in evs))
        self.assertTrue(report["needs_check"])  # текст-заглушка помечен на проверку

    def test_import_city_nodes(self):
        from services import city_constructor_service as ccs

        report = ci.import_city_nodes()
        self.assertGreater(report["created"], 0)
        nodes = [i for i in ccs.store().list() if (i.get("data") or {}).get("_kind") == "city_node"]
        self.assertTrue(any(n["id"] == "seldar" for n in nodes))
        self.assertTrue(any((n.get("data") or {}).get("parent_id") == "seldar" for n in nodes))

    def test_mode_copy(self):
        from services import world_content_registry as wcr

        ci.import_locations()
        rc = ci.import_locations(mode="copy")
        self.assertGreater(rc["created"], 0)
        self.assertTrue(wcr.get_content(wcr.KIND_LOCATION, "hilly_meadows_copy") is not None)

    def test_manual_protection(self):
        from services import world_content_registry as wcr

        # Рукотворная запись по id, который импортёр тоже создаёт (без imported).
        wcr.create_content(wcr.KIND_LOCATION, "hilly_meadows", {"name": "Правка админа", "type": "wild", "description": "x"})
        report = ci.import_locations(mode="update")
        # Ручная запись не перезаписана — помечена на проверку (ТЗ §9).
        self.assertTrue(any(n.get("id") == "hilly_meadows" for n in report["needs_check"]))
        # Содержимое не затёрто импортом.
        kept = wcr.get_content(wcr.KIND_LOCATION, "hilly_meadows")
        self.assertEqual((kept.get("data") or {}).get("name"), "Правка админа")

    def test_check_import_finds_orphans(self):
        from services import world_content_registry as wcr

        ci.import_locations()
        ci.import_events()
        clean = ci.check_import()
        self.assertTrue(clean["ok"], clean["issues"])
        # Событие на несуществующую локацию → проблема.
        wcr.create_content(wcr.KIND_EVENT, "orphan_ev", {"name": "Сирота", "type": "trap", "text": "t", "location": "ghost_loc"})
        bad = ci.check_import()
        self.assertFalse(bad["ok"])
        self.assertTrue(any(i["id"] == "orphan_ev" for i in bad["issues"]))

    def test_import_achievements(self):
        from services import achievement_service as ach

        report = ci.import_achievements()
        self.assertGreaterEqual(report["created"], 2)
        ids = {a["id"] for a in ach.store().list()}
        self.assertIn("seeker", ids)
        self.assertIn("curse_what_curse", ids)
        # Категория создана, достижения опубликованы и помечены imported.
        self.assertIsNotNone(ach.categories().get("small_plateau"))
        self.assertTrue(all(a["status"] == "published" for a in ach.store().list()))
        # §5: у curse_what_curse — пометка про только PVP-посмертное проклятье.
        self.assertTrue(any(n["id"] == "curse_what_curse" and "PVP" in n["reason"] for n in report["needs_check"]))
        # Идемпотентность.
        r2 = ci.import_achievements(mode="new")
        self.assertEqual(r2["created"], 0)

    def test_import_fines(self):
        from services import fine_constructor_service as fc

        report = ci.import_fines()
        self.assertGreaterEqual(report["created"], 5)
        items = fc.store().list()
        ids = {i["id"] for i in items}
        self.assertIn("black_market_raid_fine", ids)
        self.assertTrue(all(i["status"] == "published" for i in items))
        # Импортированные типы проходят валидацию конструктора штрафов.
        for it in items:
            res = fc.validate(it)
            self.assertTrue(res["ok"], (it["id"], res["errors"]))
        self.assertEqual(ci.import_fines(mode="new")["created"], 0)

    def test_import_recipes(self):
        from services import recipe_constructor_service as rcs

        report = ci.import_recipes()
        self.assertGreater(report["created"], 0)
        items = rcs.store().list()
        self.assertTrue(items)
        self.assertTrue(all(i["status"] == "published" for i in items))
        # У импортированных рецептов есть мастерская/результат/ингредиенты.
        sample = next(i for i in items if (i.get("data") or {}).get("ingredients"))
        d = sample["data"]
        self.assertIn(d["workshop"], rcs.WORKSHOPS)
        self.assertTrue(d["output_item_id"])
        # where_used находит рецепт по результату.
        self.assertTrue(rcs.where_used(d["output_item_id"]))
        self.assertEqual(ci.import_recipes(mode="new")["created"], 0)

    def test_import_all_summary(self):
        result = ci.import_all(["location", "event"])
        self.assertIn("summary", result)
        self.assertEqual({r["kind"] for r in result["reports"]}, {"location", "event"})
        self.assertGreaterEqual(result["summary"]["created"], 1)


if __name__ == "__main__":
    unittest.main()
