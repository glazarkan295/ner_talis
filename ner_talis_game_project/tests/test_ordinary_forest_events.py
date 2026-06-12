import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import START_SEARCH, create_search_event, handle_external_location_action
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage

DATA_DIR = ROOT_DIR.parent / "data"


class OrdinaryForestEventsRebuildTest(unittest.TestCase):
    def make_player_and_storage(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="444",
            name="Лесной путник",
            race_id="human",
            races=races,
        )
        player["current_location"] = "ordinary_forest"
        player["current_zone"] = "ordinary_forest"
        skills = player.setdefault("skills", {})
        active = skills.setdefault("active", [])
        equipped = skills.setdefault("equipped", [])
        basic = next((skill for skill in active if skill.get("id") == "basic_attack"), None)
        if basic:
            active.remove(basic)
            equipped.append(basic)
        storage.save_new_player(player, "telegram", "444")
        return storage, storage.get_player_by_platform("telegram", "444")

    def test_ordinary_forest_event_table_is_rebuilt_to_100_without_waterside(self):
        data = json.loads((DATA_DIR / "ordinary_forest.json").read_text(encoding="utf-8"))
        events = data.get("events") or {}
        self.assertEqual("ordinary_forest_events_v2", data.get("event_list_version"))
        self.assertEqual(100, sum(int(value) for value in events.values()))
        self.assertEqual(
            {"dry_tree", "mushrooms", "river", "small_burrow", "forest_trap", "battle"},
            set(events),
        )
        self.assertNotIn("waterside_loot", events)
        self.assertEqual("ordinary_forest_events_v2", data.get("event_flow", {}).get("version"))
        self.assertIn("waterside_loot", data.get("event_flow", {}).get("excluded_events", []))

    def test_create_search_event_uses_configured_discovery_texts(self):
        data = json.loads((DATA_DIR / "ordinary_forest.json").read_text(encoding="utf-8"))
        for event_type in ("dry_tree", "mushrooms", "river", "small_burrow"):
            configured = set(data["event_texts"][event_type]["discovery"])
            seen = {
                create_search_event(event_type, random.Random(seed), "ordinary_forest")["text"]
                for seed in range(20)
            }
            self.assertTrue(seen <= configured)
            self.assertGreaterEqual(len(seen), 2)

    def test_start_search_only_rolls_rebuilt_event_types(self):
        allowed = {"dry_tree", "mushrooms", "river", "small_burrow", "forest_trap", "battle"}
        for seed in range(50):
            storage, player = self.make_player_and_storage()
            response = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(seed))
            self.assertIn("Поиск начался", response.text)
            updated = storage.get_player_by_platform("telegram", "444")
            event_type = updated["active_timer"]["event"].get("type")
            self.assertIn(event_type, allowed)
            self.assertNotEqual("waterside_loot", event_type)


if __name__ == "__main__":
    unittest.main()
