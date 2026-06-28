"""Аудит изображений импортированного контента (full-import ТЗ §6)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import image_audit_service as ias
from services import item_constructor_service as ics


class ImageAuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._uploads = base / "uploads"
        keys = ("ITEM_CONSTRUCTOR_PATH", "WORLD_CONTENT_PATH", "CITY_CONSTRUCTOR_PATH",
                "RACE_CONSTRUCTOR_PATH", "PUBLIC_UPLOADS_ASSETS_DIR")
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ["ITEM_CONSTRUCTOR_PATH"] = str(base / "items.json")
        os.environ["WORLD_CONTENT_PATH"] = str(base / "world.json")
        os.environ["CITY_CONSTRUCTOR_PATH"] = str(base / "city.json")
        os.environ["RACE_CONSTRUCTOR_PATH"] = str(base / "race.json")
        os.environ["PUBLIC_UPLOADS_ASSETS_DIR"] = str(self._uploads)
        self.addCleanup(self._restore)
        # Реальный файл в рантайм-хранилище загрузок.
        good = self._uploads / "admin_uploads" / "items"
        good.mkdir(parents=True, exist_ok=True)
        (good / "good.png").write_bytes(b"\x89PNG\r\n")

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_classify(self):
        self.assertEqual(ias.classify(""), "empty")
        self.assertEqual(ias.classify("http://example.com/a.png"), "external")
        self.assertEqual(ias.classify("//cdn/x.png"), "external")
        self.assertEqual(ias.classify("data:image/png;base64,AAAA"), "external")
        self.assertEqual(ias.classify("/assets/admin_uploads/items/good.png"), "ok")
        self.assertEqual(ias.classify("/assets/admin_uploads/items/none.png"), "missing")

    def test_audit_counts_and_problems(self):
        ics.store().create("okitem", {"name": "OK", "category": "Оружие", "icon": "/assets/admin_uploads/items/good.png"})
        ics.store().create("missitem", {"name": "M", "category": "Оружие", "icon": "/assets/admin_uploads/items/missing.png"})
        ics.store().create("exturl", {"name": "E", "category": "Оружие", "icon": "http://example.com/x.png"})
        report = ias.audit()
        self.assertGreaterEqual(report["ok"], 1)
        self.assertGreaterEqual(report["missing"], 1)
        self.assertGreaterEqual(report["external"], 1)
        problem_ids = {(p["id"], p["status"]) for p in report["problems"]}
        self.assertIn(("missitem", "missing"), problem_ids)
        self.assertIn(("exturl", "external"), problem_ids)
        # «Хороший» предмет в проблемы не попал.
        self.assertNotIn("okitem", {p["id"] for p in report["problems"]})

    def test_audit_scans_world_mob(self):
        from services import world_content_registry as wcr

        wcr.create_content(wcr.KIND_MOB, "wolf", {"name": "Волк", "type": "beast", "hp": 10, "image": "/assets/mobs/ghost.png"})
        report = ias.audit()
        self.assertTrue(any(p["kind"] == "mob" and p["id"] == "wolf" for p in report["problems"]))


if __name__ == "__main__":
    unittest.main()
