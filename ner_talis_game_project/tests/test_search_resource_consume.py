"""Списание недельных лимитов при сборе ресурсов через поиск (ТЗ §23/§24).

Когда включён WORLD_CONSTRUCTOR_LIVE и для выдаваемого предмета есть
опубликованный конструкторный лимит локации, сбор в событии поиска уменьшает
его остаток. Флаг выкл / нет лимита → выдача как раньше.
"""

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import external_location_service as els
from services import location_runtime as lr
from services import world_content_registry as wcr
from services.registration_service import create_player, load_races

LOC = "ordinary_forest"


class _FakeStorage:
    def update_player(self, player):
        return player


class SearchResourceConsumeTest(unittest.TestCase):
    def setUp(self):
        self._content = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._state = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        os.environ["WORLD_CONTENT_PATH"] = self._content
        os.environ["LOCATION_RUNTIME_STATE_PATH"] = self._state
        # Конструкторный недельный лимит на «сухое бревно» в лесу.
        wcr.create_content(wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_log", {
            "location": LOC, "limit_type": "resource", "linked_object": "dry_log",
            "total_stock": 50,
        })
        wcr.set_status(wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_log", wcr.STATUS_PUBLISHED, force=True)

    def tearDown(self):
        for var in ("WORLD_CONTENT_PATH", "LOCATION_RUNTIME_STATE_PATH", "WORLD_CONSTRUCTOR_LIVE"):
            os.environ.pop(var, None)
        for base in (self._content, self._state):
            for suffix in ("", ".lock", ".tmp"):
                try:
                    os.unlink(base + suffix)
                except OSError:
                    pass

    def _player(self):
        races = load_races("data/races.json")
        player = create_player(game_id="NT-AAAA111122", platform="telegram", external_user_id="1", name="Тест", race_id="human", races=races)
        player["current_location"] = LOC
        player["current_zone"] = LOC
        player["location_id"] = LOC
        player["active_event"] = {"type": "dry_tree", "location_id": LOC, "event_id": "ev1"}
        return player

    def _remaining(self):
        limit = lr.published_limits(LOC)[0]
        return lr.remaining(LOC, limit)

    def test_collect_consumes_when_live(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        player = self._player()
        els.resolve_active_event(_FakeStorage(), player, els.COLLECT_TREE, random.Random(1))
        left = self._remaining()
        self.assertLess(left, 50)        # списано
        self.assertGreaterEqual(left, 47)  # за раз выдаётся 1–3 бревна

    def test_collect_noop_when_flag_off(self):
        player = self._player()
        els.resolve_active_event(_FakeStorage(), player, els.COLLECT_TREE, random.Random(1))
        self.assertEqual(self._remaining(), 50)  # флаг выкл → запас не тронут


if __name__ == "__main__":
    unittest.main()
