import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import world_content_registry as registry
from services import world_runtime as rt


class WorldRuntimeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("WORLD_CONTENT_PATH")
        os.environ["WORLD_CONTENT_PATH"] = str(Path(self._tmp.name) / "world.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("WORLD_CONTENT_PATH", None)
        else:
            os.environ["WORLD_CONTENT_PATH"] = self._saved

    def _publish(self, kind, cid, data):
        registry.create_content(kind, cid, data)
        registry.set_status(kind, cid, registry.STATUS_PUBLISHED, force=True)

    def test_only_published_content_is_served(self):
        self._publish("location", "hub", {"name": "Узел", "type": "wild", "description": "Перекрёсток"})
        # A draft button must NOT appear in runtime.
        registry.create_content("button", "draft_btn", {"text": "Черновик", "owner_location": "hub", "action": "show_message", "show_telegram": True})
        self._publish("button", "go_tg", {"text": "В путь", "owner_location": "hub", "action": "go_back", "order": 1, "show_telegram": True, "show_vk": False})
        self._publish("button", "go_vk", {"text": "VK кнопка", "owner_location": "hub", "action": "go_back", "order": 2, "show_telegram": False, "show_vk": True})

        scene = rt.location_scene("hub", platform="telegram")
        self.assertEqual(scene["title"], "Узел")
        self.assertIn("В путь", scene["buttons"])
        self.assertNotIn("VK кнопка", scene["buttons"])  # platform filter
        self.assertNotIn("Черновик", scene["buttons"])  # draft excluded

        # Unpublished location -> None.
        registry.create_content("location", "secret", {"name": "Тайна", "type": "wild", "description": "x"})
        self.assertIsNone(rt.location("secret"))

    def test_roll_drop_is_deterministic_with_seed_and_respects_flags(self):
        self._publish("mob", "wolf", {
            "name": "Волк", "type": "beast", "hp": 50,
            "drop": [
                {"item_id": "money_copper", "chance": 100, "min_count": 5, "max_count": 5},
                {"item_id": "rare_fang", "chance": 0.0001, "min_count": 1, "max_count": 1},
                {"item_id": "event_token", "chance": 100, "min_count": 1, "max_count": 1, "only_event": True},
            ],
        })
        drops = rt.roll_drop("wolf", rng=random.Random(1))
        ids = {d["item_id"] for d in drops}
        self.assertIn("money_copper", ids)   # 100% always
        self.assertNotIn("rare_fang", ids)   # ~0% basically never
        self.assertNotIn("event_token", ids)  # event-only, not an event run
        # Event run includes the event-only drop.
        event_drops = {d["item_id"] for d in rt.roll_drop("wolf", rng=random.Random(1), event=True)}
        self.assertIn("event_token", event_drops)

    def test_mobs_in_location(self):
        self._publish("mob", "bat", {"name": "Мышь", "type": "beast", "hp": 10, "locations": "cave, hub"})
        self.assertTrue(any(m["id"] == "bat" for m in rt.mobs_in_location("cave")))
        self.assertFalse(rt.mobs_in_location("nowhere"))


if __name__ == "__main__":
    unittest.main()
