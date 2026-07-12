import os
import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from services import npc_ally_constructor_service as constructor
from services import npc_ally_runtime as runtime


class NpcAllyRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.saved = os.environ.get("NPC_ALLY_CONSTRUCTOR_PATH")
        os.environ["NPC_ALLY_CONSTRUCTOR_PATH"] = str(Path(self.tmp.name) / "helpers.json")
        self.addCleanup(self.restore)
        constructor.store().create("fox", {
            "name": "Лис", "ally_type": "scout", "role": "scout", "permanent": True,
            "active_on_receive": False, "pve_enabled": True, "pvp_allow_mode": "allowed",
            "hp": 30, "phys_damage": 8, "accuracy": 100, "abilities": ["attack"],
            "out_of_battle_actions": ["find_resources", "open_sublocation"],
            "own_actions": [{"id": "fox_bite", "name": "Укус", "type": "attack", "power": 50, "success_chance": 100, "success_text": "Лис кусает врага."}],
            "outside_target_id": "secret_cave", "outside_action_chance": 100,
            "has_levels": True, "dev_level": 1, "dev_max_level": 3, "dev_exp_per_battle": 100, "exp_per_level": 100,
            "loyalty_enabled": True, "loyalty_min": 0, "loyalty_max": 100, "loyalty_start": 50,
            "loyalty_on_victory": 2, "can_die": True, "permanent_death": False, "revival_seconds": 10,
            "summon_text": "Лис выходит из тени.", "outside_success_text": "Лис находит путь.",
        })
        constructor.store().set_status("fox", constructor.STATUS_PUBLISHED, force=True)

    def restore(self):
        if self.saved is None: os.environ.pop("NPC_ALLY_CONSTRUCTOR_PATH", None)
        else: os.environ["NPC_ALLY_CONSTRUCTOR_PATH"] = self.saved

    def test_grant_activate_outside_battle_progress_death_and_recovery(self):
        player = {"game_id": "P", "level": 5}
        state = runtime.grant(player, "fox", source="quest:q1")
        self.assertTrue(state["permanent"]); self.assertEqual(state["status"], "available")
        runtime.activate(player, "fox")
        self.assertEqual(runtime.outside_action(player, "fox", "open_sublocation", rng=random.Random(1)), "Лис находит путь.")
        self.assertTrue(player["unlocks"]["secret_cave"])
        snapshots = runtime.battle_snapshots(player)
        self.assertEqual(snapshots[0]["damage"], 8)
        from services.combat_group_runtime import attach_participants, apply_ally_phase
        live_battle = {"combat_profile": {}, "player_state": {"current_hp": 10, "max_hp": 10}, "enemies": [{"name": "Крыса", "current_hp": 40}]}
        attach_participants(live_battle, player); log = []; apply_ally_phase(live_battle, random.Random(1), log)
        self.assertEqual(live_battle["enemies"][0]["current_hp"], 0)
        self.assertIn("Лис кусает", log[0])
        battle = {"allies": [{"participant_id": "fox", "current_hp": 0}]}
        runtime.record_battle(player, battle, victory=True)
        state = player["npc_helpers"]["owned"]["fox"]
        self.assertEqual(state["level"], 2); self.assertEqual(state["loyalty"], 52)
        self.assertEqual(state["status"], "recovering")
        runtime.refresh(player, now=datetime.now(timezone.utc) + timedelta(seconds=11))
        self.assertEqual(state["status"], "available")

    def test_grants_from_quest_event_and_achievement_are_idempotent(self):
        from services.quest_runtime_service import _grant
        from services.constructor_event_runtime import complete
        from services.achievement_engine import apply_rewards
        q = {}; _grant(q, {"type": "npc_helper", "object_id": "fox"})
        self.assertEqual(q["npc_helpers"]["owned"]["fox"]["source"], "quest")
        e = {}; complete(e, {"id": "meet_fox", "rewards": [{"type": "npc_ally", "object_id": "fox"}]}, rng=random.Random(1))
        self.assertEqual(e["npc_helpers"]["owned"]["fox"]["source"], "event:meet_fox")
        a = {}; lines, errors = apply_rewards(a, [{"type": "npc_helper", "object_id": "fox"}])
        self.assertFalse(errors); self.assertTrue(any("fox" in line for line in lines))
        runtime.grant(a, "fox", source="duplicate")
        self.assertEqual(len(a["npc_helpers"]["owned"]), 1)


if __name__ == "__main__": unittest.main()
