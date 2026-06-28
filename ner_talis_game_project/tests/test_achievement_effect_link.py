"""Связь достижение→эффект (ТЗ 09 §16–§17): источник в эффекте + ребро в графе."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import achievement_service
from services import admin_graph_service as graph
from services import effect_constructor_service as effects


class AchievementEffectLinkTest(unittest.TestCase):
    ENVS = ("ACHIEVEMENTS_PATH", "ACHIEVEMENT_CATEGORIES_PATH", "EFFECT_CONSTRUCTOR_PATH")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in self.ENVS}
        for k in self.ENVS:
            os.environ[k] = str(base / f"{k.lower()}.json")
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_effect_where_used_includes_achievement(self):
        effects.store().create("exp_boost", {"effect_name": "Бонус опыта", "effect_type": "buff"})
        achievement_service.store().create("hunter", {"name": "Охотник", "effects": ["exp_boost"]})
        used = effects.where_used("exp_boost")
        self.assertTrue(any(u["kind"] == "achievement" and u["id"] == "hunter" for u in used), used)

    def test_graph_edge_from_effects_list(self):
        effects.store().create("exp_boost", {"effect_name": "Бонус опыта"})
        achievement_service.store().create("hunter", {"name": "Охотник", "effects": ["exp_boost"]})
        g = graph.full_graph()
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("achievement:hunter", "effect:exp_boost", "applies_effect"), pairs)

    def test_graph_edge_from_reward_effect(self):
        effects.store().create("shield", {"effect_name": "Щит"})
        achievement_service.store().create("guard", {"name": "Страж", "rewards": [{"type": "effect", "effect_id": "shield"}]})
        g = graph.full_graph()
        pairs = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        self.assertIn(("achievement:guard", "effect:shield", "applies_effect"), pairs)


if __name__ == "__main__":
    unittest.main()
