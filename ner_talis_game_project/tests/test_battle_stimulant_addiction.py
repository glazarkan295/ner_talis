import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import battle_stimulant_service as bss
from services.derived_stats_service import calculate_player_derived_stats


def _base_player():
    return {
        "level": 20,
        "stats": {"strength": 30, "endurance": 30, "dexterity": 30, "perception": 30, "intelligence": 30, "wisdom": 30},
        "inventory": [],
        "equipment": {},
    }


def _stats(player):
    s = calculate_player_derived_stats(copy.deepcopy(player))
    keys = ("max_hp", "max_spirit", "max_mana", "max_energy", "accuracy", "dodge", "crit_chance_percent", "crit_damage_percent")
    return {k: s[k] for k in keys}


class BattleStimulantAddictionTest(unittest.TestCase):
    def test_use_sets_active_phase_and_grows_addiction_without_debuffs(self):
        player = _base_player()
        clean = _stats(player)
        bss.register_battle_stimulant_use(player)
        self.assertEqual(bss.battle_stimulant_phase(player), "active")
        self.assertEqual(bss.addiction_level(player), 1)
        # Active phase blocks addiction and does not change derived stats here.
        self.assertEqual(_stats(player), clean)

    def test_withdrawal_phase_applies_minus_ten_percent(self):
        player = _base_player()
        clean = _stats(player)
        now = datetime.now(timezone.utc)
        player["battle_stimulant_active_until"] = (now - timedelta(minutes=1)).isoformat()
        player["battle_stimulant_withdrawal_until"] = (now + timedelta(hours=1)).isoformat()
        withdrawn = _stats(player)
        for key in ("accuracy", "dodge", "max_spirit", "max_mana", "max_energy"):
            self.assertLess(withdrawn[key], clean[key], key)
        self.assertEqual(withdrawn["max_hp"], clean["max_hp"])

    def test_addiction_threshold_and_scaling(self):
        clean = _stats(_base_player())

        below = _base_player()
        below["battle_stimulant_addiction"] = {"level": 49}
        self.assertEqual(_stats(below), clean)

        at_50 = _base_player()
        at_50["battle_stimulant_addiction"] = {"level": 50}
        s50 = _stats(at_50)
        self.assertLess(s50["dodge"], clean["dodge"])
        self.assertLess(s50["accuracy"], clean["accuracy"])
        self.assertLess(s50["max_hp"], clean["max_hp"])
        self.assertGreaterEqual(s50["crit_damage_percent"], clean["crit_damage_percent"])

        at_100 = _base_player()
        at_100["battle_stimulant_addiction"] = {"level": 100}
        self.assertLess(_stats(at_100)["dodge"], s50["dodge"])

    def test_active_blocks_addiction_debuffs(self):
        player = _base_player()
        player["battle_stimulant_addiction"] = {"level": 100}
        clean = _stats(_base_player())
        bss.register_battle_stimulant_use(player)  # now active
        self.assertEqual(_stats(player), clean)

    def test_skill_damage_multiplier(self):
        addicted = _base_player()
        addicted["battle_stimulant_addiction"] = {"level": 50}
        self.assertGreater(bss.skill_damage_multiplier(addicted), 1.0)
        active = _base_player()
        active["battle_stimulant_addiction"] = {"level": 100}
        bss.register_battle_stimulant_use(active)
        self.assertAlmostEqual(bss.skill_damage_multiplier(active), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
