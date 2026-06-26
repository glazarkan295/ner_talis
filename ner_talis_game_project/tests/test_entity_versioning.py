"""Этап 1: версионирование/история/откат на общем EntityStore."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.admin_entity_store import HISTORY_LIMIT, EntityError, EntityStore


class EntityVersioningTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["TEST_ENTITY_PATH"] = str(Path(self._tmp.name) / "e.json")
        self.addCleanup(lambda: os.environ.pop("TEST_ENTITY_PATH", None))
        self.store = EntityStore(
            env_var="TEST_ENTITY_PATH", default_rel="x/e.json",
            statuses=("draft", "published"),
            transitions={"draft": {"published"}, "published": {"draft"}},
            initial_status="draft",
        )

    def test_history_records_previous_versions_on_update(self):
        self.store.create("obj", {"name": "v1"})
        self.store.update("obj", {"name": "v2"})
        self.store.update("obj", {"name": "v3"})
        hist = self.store.history("obj")
        self.assertEqual([h["version"] for h in hist], [1, 2])
        self.assertEqual(hist[0]["data"]["name"], "v1")
        self.assertEqual(hist[1]["data"]["name"], "v2")
        self.assertEqual(self.store.get("obj")["version"], 3)

    def test_rollback_restores_snapshot_and_is_reversible(self):
        self.store.create("obj", {"name": "v1", "hp": 10})
        self.store.update("obj", {"name": "v2"})
        env = self.store.rollback("obj", 1)
        self.assertEqual(env["data"]["name"], "v1")
        self.assertEqual(env["data"]["hp"], 10)
        self.assertEqual(env["version"], 3)
        # Текущее состояние тоже ушло в историю → откат обратим.
        self.assertIn(2, [h["version"] for h in self.store.history("obj")])

    def test_rollback_unknown_version_raises(self):
        self.store.create("obj", {"name": "v1"})
        with self.assertRaises(EntityError):
            self.store.rollback("obj", 99)

    def test_history_is_bounded(self):
        self.store.create("obj", {"n": 0})
        for i in range(1, HISTORY_LIMIT + 12):
            self.store.update("obj", {"n": i})
        self.assertLessEqual(len(self.store.history("obj")), HISTORY_LIMIT)

    def test_history_empty_for_unknown(self):
        self.assertEqual(self.store.history("missing"), [])


if __name__ == "__main__":
    unittest.main()
