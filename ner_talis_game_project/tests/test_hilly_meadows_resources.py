import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import (
    HILLY_MEADOWS,
    INSPECT_AND_TAKE,
    COLLECT,
    resolve_active_event,
)
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage

DATA_DIR = ROOT_DIR.parent / "data"


class HillyMeadowsResourceTablesTest(unittest.TestCase):
    def make_player_and_storage(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="111",
            name="Луговик",
            race_id="human",
            races=races,
        )
        player["current_location"] = "hilly_meadows"
        player["current_zone"] = "hilly_meadows"
        storage.save_new_player(player, "telegram", "111")
        return storage, storage.get_player_by_platform("telegram", "111")

    def test_hilly_meadows_has_explicit_resource_tables_without_waterside(self):
        data = json.loads((DATA_DIR / "hilly_meadows.json").read_text(encoding="utf-8"))
        self.assertNotIn("waterside_loot", data.get("events", {}))
        tables = data.get("resource_find_tables")
        self.assertIsInstance(tables, dict)
        self.assertEqual({"alchemy_ingredient", "berries", "stone_or_ore", "glint_old_knife_up_slope", "glint_search_traces_down_slope"}, set(tables))
        self.assertEqual(["Обычный камень", "Кусок медной руды", "Кусок железной руды"], [entry["name_ru"] for entry in tables["stone_or_ore"]])
        self.assertEqual(["Сладкая луговая ягода", "Терпкая синяя ягода"], [entry["name_ru"] for entry in tables["berries"]])

    def test_stone_or_ore_reward_uses_configured_table(self):
        storage, player = self.make_player_and_storage()
        player["active_event"] = {"id": "test_event", "type": "stone_or_ore", "location_id": "hilly_meadows"}
        storage.update_player(player)
        response = resolve_active_event(storage, storage.get_player_by_platform("telegram", "111"), INSPECT_AND_TAKE, random.Random(1))
        self.assertRegex(response.text, r"Получено: (Обычный камень|Кусок медной руды|Кусок железной руды) ×")

    def test_alchemy_reward_uses_configured_table(self):
        storage, player = self.make_player_and_storage()
        player["active_event"] = {"id": "test_event", "type": "alchemy_ingredient", "location_id": "hilly_meadows"}
        storage.update_player(player)
        response = resolve_active_event(storage, storage.get_player_by_platform("telegram", "111"), COLLECT, random.Random(2))
        self.assertRegex(response.text, r"Получено: (Луговая мята|Серебристая ромашка|Жёлтый клевер|Горная полынь|Луговой корень) ×")


if __name__ == "__main__":
    unittest.main()
