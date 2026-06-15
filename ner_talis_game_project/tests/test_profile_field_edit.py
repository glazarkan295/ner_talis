import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.registration_service import create_player, load_races
from site_api import (
    apply_profile_field_edit,
    frontend_profile,
    gender_label_ru,
    profile_field_edit_availability,
)


class ProfileFieldEditTest(unittest.TestCase):
    def _player(self):
        return create_player(
            game_id="NT-EDIT",
            platform="telegram",
            external_user_id="1",
            name="Старое имя",
            race_id="human",
            races=load_races("data/races.json"),
        )

    def test_payload_exposes_gender_and_edit_availability(self):
        player = self._player()
        payload = frontend_profile(player)["player"]
        self.assertEqual(payload["genderLabel"], "Не выбран")
        self.assertEqual(payload["profileFieldEdits"], {"name": True, "race": True, "gender": True})

    def test_one_free_edit_per_field_then_blocked(self):
        player = self._player()
        self.assertEqual(apply_profile_field_edit(player, "name", "Новое имя"), "Новое имя")
        self.assertEqual(player["name"], "Новое имя")
        self.assertEqual(apply_profile_field_edit(player, "gender", "Жен."), "Жен.")
        self.assertEqual(player["gender"], "female")
        self.assertEqual(player["gender_label"], "Жен.")
        self.assertEqual(apply_profile_field_edit(player, "race", "elf"), "Эльф")
        self.assertEqual(player["race_id"], "elf")
        self.assertEqual(player["race_name"], "Эльф")

        availability = profile_field_edit_availability(player)
        self.assertEqual(availability, {"name": False, "race": False, "gender": False})

        for field, value in (("name", "Третье"), ("gender", "Муж."), ("race", "dwarf")):
            with self.assertRaises(HTTPException) as ctx:
                apply_profile_field_edit(player, field, value)
            self.assertEqual(ctx.exception.status_code, 409)

    def test_race_change_swaps_base_stats(self):
        player = self._player()
        races = load_races("data/races.json")
        apply_profile_field_edit(player, "race", "dwarf")
        self.assertEqual(player["stats"], dict(races["dwarf"]["stats"]))

    def test_invalid_values_rejected(self):
        player = self._player()
        with self.assertRaises(HTTPException):
            apply_profile_field_edit(player, "gender", "нечто")
        player2 = self._player()
        with self.assertRaises(HTTPException):
            apply_profile_field_edit(player2, "race", "ork")
        player3 = self._player()
        with self.assertRaises(HTTPException):
            apply_profile_field_edit(player3, "name", "")

    def test_gender_label_helper(self):
        self.assertEqual(gender_label_ru("male"), "Муж.")
        self.assertEqual(gender_label_ru("female"), "Жен.")
        self.assertEqual(gender_label_ru(None, "Не выбран"), "Не выбран")


if __name__ == "__main__":
    unittest.main()
