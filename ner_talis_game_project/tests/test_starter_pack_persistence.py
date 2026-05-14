import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.registration_service import create_player, load_races


class StarterPackPersistenceTest(unittest.TestCase):
    def test_create_player_has_starter_equipment_and_skills_marker(self):
        races = load_races("data/races.json")
        player = create_player(
            game_id="NT-TESTSTART",
            platform="telegram",
            external_user_id="111",
            name="Новичок",
            race_id="human",
            races=races,
        )

        self.assertIn("weapon1", player["equipment"])
        self.assertEqual(player["equipment"]["weapon1"]["name"], "Деревянный посох")
        self.assertEqual(len(player["skills"]["active"]), 2)
        self.assertEqual(player["skills"]["active"][0]["name"], "Обычный удар")
        self.assertFalse(player["skills"]["active"][0]["upgradeable"])
        self.assertTrue(player["starter_pack_applied"])

    def test_postgres_runtime_packs_starter_fields_into_extra_json(self):
        try:
            from storage.postgres_storage import PostgresStorage
            from storage.starter_pack_runtime import patch_postgres_starter_pack
        except ModuleNotFoundError as exc:
            self.skipTest(f"PostgreSQL dependencies are not installed: {exc}")

        patch_postgres_starter_pack(PostgresStorage)
        races = load_races("data/races.json")
        player = create_player(
            game_id="NT-POSTGRES",
            platform="telegram",
            external_user_id="111",
            name="Постгрес",
            race_id="human",
            races=races,
        )

        storage = PostgresStorage.__new__(PostgresStorage)
        extra = storage._build_extra_payload(player)

        self.assertIn("equipment", extra)
        self.assertIn("skills", extra)
        self.assertTrue(extra["starter_pack_applied"])
        self.assertIn("weapon1", extra["equipment"])
        self.assertEqual(extra["skills"]["active"][1]["name"], "Магический сгусток")

        row = {
            "game_id": player["game_id"],
            "public_id": player["public_id"],
            "name": player["name"],
            "race_id": player["race_id"],
            "race_name": player["race_name"],
            "level": player["level"],
            "experience": player["experience"],
            "money": player["money"],
            "debt": player["debt"],
            "energy": player["energy"],
            "max_energy": player["max_energy"],
            "current_city": player["current_city"],
            "current_zone": player["current_zone"],
            "stats": player["stats"],
            "inventory": player["inventory"],
            "crafting_levels": player["crafting_levels"],
            "housing": player["housing"],
            "extra": extra,
        }

        with patch.object(storage, "get_links_for_game_id", return_value={"telegram": "111"}):
            restored = storage._row_to_player(row)

        self.assertIsNotNone(restored)
        self.assertIn("weapon1", restored["equipment"])
        self.assertEqual(restored["skills"]["active"][0]["id"], "basic_attack")
        self.assertEqual(restored["linked_accounts"], {"telegram": "111"})


if __name__ == "__main__":
    unittest.main()
