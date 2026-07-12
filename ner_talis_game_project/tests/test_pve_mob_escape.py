import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.pve_battle_service import process_mob_escape


def enemy(mob_id="wolf", hp=20, maximum=100, **extra):
    return {"name": mob_id, "source_mob_id": mob_id, "current_hp": hp, "max_hp": maximum, "level": 1, **extra}


class MobEscapeRuntimeTest(unittest.TestCase):
    def battle(self, rules, enemies=None, allies=None):
        return {"round_number": 2, "enemies": enemies or [enemy()], "allies": allies or [], "combat_profile": {"mob_escape_rules": rules}}

    def test_individual_escape_by_hp_and_authored_text(self):
        battle = self.battle([{"enabled": True, "mob_id": "wolf", "mode": "individual", "condition_type": "hp_percent", "operator": "<=", "value": 25, "chance": 100, "success_text": "Волк скрылся!", "xp_factor": .5, "coin_factor": 0, "drop_factor": 0}])
        log = []
        result = process_mob_escape({"level": 2}, battle, random.Random(1), log)
        self.assertTrue(result["all_gone"])
        self.assertTrue(battle["enemies"][0]["escaped"])
        self.assertEqual(battle["enemies"][0]["escape_reward_policy"]["xp_factor"], .5)
        self.assertIn("Волк скрылся!", log)

    def test_failed_chance_and_player_can_stop(self):
        failed = self.battle([{"enabled": True, "condition_type": "scenario", "chance": 0, "fail_text": "Не вышло"}])
        log = []
        process_mob_escape({}, failed, random.Random(1), log)
        self.assertFalse(failed["enemies"][0].get("escaped"))
        self.assertIn("Не вышло", log)
        stopped = self.battle([{"enabled": True, "condition_type": "scenario", "chance": 100, "player_can_stop": True, "stop_chance": 100, "stop_text": "Перехвачен"}])
        log = []
        process_mob_escape({}, stopped, random.Random(2), log)
        self.assertFalse(stopped["enemies"][0].get("escaped"))
        self.assertIn("Перехвачен", log)

    def test_group_escape_event_future_and_draw(self):
        battle = self.battle([{"enabled": True, "mode": "group", "condition_type": "scenario", "chance": 100, "event_id": "after_flee", "future_encounter_id": "revenge", "all_escaped_result": "draw"}], [enemy("a"), enemy("b")])
        player = {}
        result = process_mob_escape(player, battle, random.Random(3), [])
        self.assertEqual(result["result"], "draw")
        self.assertTrue(result["all_gone"])
        self.assertEqual(battle["post_escape_event_id"], "after_flee")
        self.assertTrue(player["future_encounters"]["revenge"])

    def test_npc_ally_can_stop_boss_retreat(self):
        battle = self.battle([{"enabled": True, "mode": "boss_retreat", "condition_type": "scenario", "chance": 100, "npc_can_stop": True, "stop_chance": 100}], [enemy("boss")], [{"name": "guard", "current_hp": 10}])
        result = process_mob_escape({}, battle, random.Random(4), [])
        self.assertFalse(result["all_gone"])


if __name__ == "__main__":
    unittest.main()
