"""Генерация боя из конструктора (ТЗ §15/§18/§22).

Когда включён WORLD_CONSTRUCTOR_LIVE и у локации есть опубликованные спауны,
бой строится из них: враги из карточек мобов, число ограничено недельным
запасом, при победе запас списывается. Флаг выкл → старая логика.
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

from services import location_runtime as lr
from services import pve_battle_service as pbs
from services import world_content_registry as wcr
from services.pve_battle_models import DamageType
from services.registration_service import create_player, load_races

LOC = "hilly_meadows"  # легаси-id (normalize_battle_location его сохраняет)


class ConstructorBattleTest(unittest.TestCase):
    def setUp(self):
        self._content = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        self._state = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        os.environ["WORLD_CONTENT_PATH"] = self._content
        os.environ["LOCATION_RUNTIME_STATE_PATH"] = self._state
        self._publish(wcr.KIND_MOB, "mob_wolf", {
            "name": "Волк", "type": "beast", "hp": 80,
            "phys_damage": 12, "accuracy": 25, "evasion": 8, "phys_defense": 5,
            "min_level": 3, "max_level": 6, "experience": 40, "coins": 10,
        })
        self._publish(wcr.KIND_LOCATION_MOB_SPAWN, "spawn_wolf", {
            "location": LOC, "mob_id": "mob_wolf", "spawn_chance": 100,
            "min_in_battle": 2, "max_in_battle": 2,
        })

    def tearDown(self):
        for var in ("WORLD_CONTENT_PATH", "LOCATION_RUNTIME_STATE_PATH", "WORLD_CONSTRUCTOR_LIVE"):
            os.environ.pop(var, None)
        for base in (self._content, self._state):
            for suffix in ("", ".lock", ".tmp"):
                try:
                    os.unlink(base + suffix)
                except OSError:
                    pass

    def _publish(self, kind, cid, data):
        wcr.create_content(kind, cid, data)
        wcr.set_status(kind, cid, wcr.STATUS_PUBLISHED, force=True)

    def _player(self):
        races = load_races("data/races.json")
        return create_player(game_id="NT-AAAA111122", platform="telegram", external_user_id="1", name="Тест", race_id="human", races=races)

    # --- Выбор спауна ----------------------------------------------------
    def test_pick_spawn_and_exclude_depleted(self):
        spawn = lr.pick_mob_spawn(LOC, 5, rng=random.Random(1))
        self.assertIsNotNone(spawn)
        self.assertEqual(spawn["mob_id"], "mob_wolf")
        # Добавляем лимит и истощаем — спаун исключается.
        self._publish(wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_wolf", {
            "location": LOC, "limit_type": "mob", "linked_object": "mob_wolf",
            "total_stock": 100,
        })
        lr.force_set_remaining(LOC, "lim_wolf", 0)
        self.assertIsNone(lr.pick_mob_spawn(LOC, 5, rng=random.Random(1)))

    # --- Сборка врага из карточки ----------------------------------------
    def test_build_constructor_enemy(self):
        mob = wcr.get_content(wcr.KIND_MOB, "mob_wolf")["data"]
        enemy = pbs.build_constructor_enemy(mob, 5, 1)
        self.assertEqual(enemy.max_hp, 80)
        self.assertEqual(enemy.physical_defense, 5)
        self.assertEqual(enemy.accuracy, 25)
        self.assertEqual(enemy.damage_type, DamageType.PHYSICAL)

    def test_enemy_raw_damage_honors_base_damage(self):
        dmg = pbs.enemy_raw_damage({"base_damage": 30, "rank": "normal", "level": 1})
        self.assertEqual(dmg, 30)

    # --- Создание боя ----------------------------------------------------
    def test_flag_off_no_constructor_battle(self):
        self.assertIsNone(pbs.create_constructor_battle({}, random.Random(1), LOC))

    def test_happy_path_tags_enemies(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        result = pbs.create_constructor_battle(self._player(), random.Random(1), LOC)
        self.assertIsNotNone(result)
        battle, _text = result
        enemies = battle["enemies"]
        self.assertEqual(len(enemies), 2)
        for e in enemies:
            self.assertEqual(e["source_mob_id"], "mob_wolf")
            self.assertEqual(e["base_damage"], 12)

    def test_count_capped_by_weekly_stock(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self._publish(wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_wolf", {
            "location": LOC, "limit_type": "mob", "linked_object": "mob_wolf",
            "total_stock": 100,
        })
        lr.force_set_remaining(LOC, "lim_wolf", 1)  # осталось 1
        battle, _ = pbs.create_constructor_battle(self._player(), random.Random(1), LOC)
        self.assertEqual(len(battle["enemies"]), 1)

    def test_victory_consumes_weekly_stock(self):
        os.environ["WORLD_CONSTRUCTOR_LIVE"] = "1"
        self._publish(wcr.KIND_LOCATION_WEEKLY_LIMIT, "lim_wolf", {
            "location": LOC, "limit_type": "mob", "linked_object": "mob_wolf",
            "total_stock": 100,
        })
        player = self._player()
        battle, _ = pbs.create_constructor_battle(player, random.Random(1), LOC)
        count = len(battle["enemies"])
        pbs.grant_battle_rewards(player, battle, random.Random(1))
        limit = lr.published_limits(LOC)[0]
        self.assertEqual(lr.remaining(LOC, limit), 100 - count)


if __name__ == "__main__":
    unittest.main()
