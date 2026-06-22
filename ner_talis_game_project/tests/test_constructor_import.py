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
        os.environ["ITEM_CONSTRUCTOR_PATH"] = self._items
        os.environ["WORLD_CONTENT_PATH"] = self._world
        os.environ["EFFECT_CONSTRUCTOR_PATH"] = self._effects

    def tearDown(self):
        os.environ.pop("ITEM_CONSTRUCTOR_PATH", None)
        os.environ.pop("WORLD_CONTENT_PATH", None)
        os.environ.pop("EFFECT_CONSTRUCTOR_PATH", None)
        for base in (self._items, self._world, self._effects):
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


if __name__ == "__main__":
    unittest.main()
