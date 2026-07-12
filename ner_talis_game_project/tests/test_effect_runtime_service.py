import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services import effect_constructor_service as effects
from services import effect_runtime_service as runtime
from services import world_content_registry as world
from services.effect_formula_runtime import apply_to_player


class EffectRuntimeServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved = {key: os.environ.get(key) for key in ("EFFECT_CONSTRUCTOR_PATH", "WORLD_CONTENT_PATH")}
        os.environ["EFFECT_CONSTRUCTOR_PATH"] = str(Path(self.tmp.name) / "effects.json")
        os.environ["WORLD_CONTENT_PATH"] = str(Path(self.tmp.name) / "world.json")
        self.addCleanup(self.restore)

    def restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def publish_effect(self, effect_id, data):
        effects.store().create(effect_id, {"effect_name": effect_id, **data})
        effects.store().set_status(effect_id, effects.STATUS_PUBLISHED, force=True)

    def test_periodic_turn_effect_ticks_and_expires(self):
        self.publish_effect("poison", {
            "effect_type": "periodic_damage", "value": 7, "duration_mode": "turns",
            "duration_turns": 2, "tick_period_turns": 1,
        })
        player = {"hp": 50, "max_hp": 100}
        apply_to_player(player, "poison")
        first = runtime.advance_turn(player)
        self.assertEqual(player["hp"], 43)
        self.assertEqual(len(first["ticks"]), 1)
        second = runtime.advance_turn(player)
        self.assertEqual(player["hp"], 36)
        self.assertEqual(player["active_effects"], [])
        self.assertEqual(len(second["removed"]), 1)

    def test_curse_is_separate_and_seconds_effect_is_pruned(self):
        self.publish_effect("doom", {"effect_type": "curse_effect", "effect_category": "curse"})
        player = {}
        curse = apply_to_player(player, "doom")
        self.assertNotIn("active_effects", player)
        self.assertEqual(player["active_curses"][0]["effect_id"], "doom")
        curse["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        report = runtime.advance_time(player)
        self.assertEqual(player["active_curses"], [])
        self.assertEqual(len(report["removed"]), 1)

    def test_trauma_blocks_equipment_slot(self):
        self.publish_effect("broken_arm", {
            "effect_type": "slot_block", "effect_category": "trauma",
            "blocked_slots": ["weapon2"], "player_text": "Сломанная рука блокирует второй слот.",
        })
        player = {}
        apply_to_player(player, "broken_arm")
        self.assertIn("Сломанная рука", runtime.blocked_slots(player)["weapon2"])

    def test_zone_sync_adds_and_removes_published_effect(self):
        self.publish_effect("heat", {"effect_type": "zone_effect", "zone_element": "fire"})
        world.create_content("location_zone", "lava", {
            "name": "Жара", "type": "fire", "location": "volcano", "effects": [{"effect_id": "heat"}],
        })
        world.set_status("location_zone", "lava", world.STATUS_PUBLISHED, force=True)
        player = {}
        self.assertTrue(runtime.sync_zone_effects(player, "volcano"))
        self.assertEqual(player["active_effects"][0]["effect_id"], "heat")
        self.assertTrue(runtime.sync_zone_effects(player, "forest"))
        self.assertEqual(player["active_effects"], [])

    def test_item_accumulator_persists_value_on_instance(self):
        self.publish_effect("charge", {
            "effect_type": "item_charge_effect", "storage_field": "charges", "value": 2, "max_value": 5,
        })
        item = {"item_id": "orb", "charges": 4}
        result = runtime.apply_to_item(item, "charge")
        self.assertEqual(result["value"], 5)
        self.assertEqual(item["stored_effect_values"]["charge"], 5)

    def test_control_reflection_invulnerability_and_doomed_luck_flags(self):
        self.publish_effect("stun",{"effect_type":"control_effect","control_kind":"stun","trigger_text":"Ход потерян."})
        self.publish_effect("doom_luck",{"effect_type":"control_effect","control_kind":"doomed_luck"})
        self.publish_effect("mirror",{"effect_type":"damage_response","damage_type":"magic","reflect_percent":25})
        self.publish_effect("shield",{"effect_type":"invulnerability_effect","blocks_all_damage":True})
        player={}
        for effect_id in ("stun","doom_luck","mirror","shield"):apply_to_player(player,effect_id)
        flags=runtime.combat_flags(player)
        self.assertTrue(flags["skip_turn"]);self.assertTrue(flags["disable_critical"]);self.assertTrue(flags["invulnerable"]);self.assertEqual(flags["reflect_magic_percent"],25);self.assertEqual(flags["trigger_text"],"Ход потерян.")


if __name__ == "__main__":
    unittest.main()
