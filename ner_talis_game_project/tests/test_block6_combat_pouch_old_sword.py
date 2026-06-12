import random
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT_DIR.parent
for path in (ROOT_DIR, PROJECT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services.pve_battle_service import (
    BATTLE_ESCAPE,
    BATTLE_POUCH,
    BATTLE_POUCH_ITEM_PREFIX,
    BATTLE_WAIT,
    create_location_battle,
    handle_battle_action,
    old_iron_sword_scaling,
)
from services.registration_service import create_player, load_races
from site_api import apply_battle_stimulant_inventory_effect, is_inventory_item_usable


class Block6CombatPouchOldSwordTest(unittest.TestCase):
    def make_player(self):
        races = load_races("data/races.json")
        player = create_player("NT-BLOCK6", "telegram", "111", "Боец", "human", races)
        player["level"] = 100
        return player

    def make_battle(self, player):
        battle, _text = create_location_battle(player, random.Random(1), "hilly_meadows")
        for enemy in battle["enemies"]:
            enemy["accuracy"] = 0
            enemy["current_hp"] = max(enemy.get("current_hp", 1), 200)
            enemy["max_hp"] = max(enemy.get("max_hp", 1), 200)
        player["active_battle"] = battle
        player["in_battle"] = True
        return battle

    def test_throwing_knife_requires_target_and_damages_target_without_ending_turn(self):
        player = self.make_player()
        player["inventory"] = [{
            "id": "old_throwing_knife",
            "item_id": "old_throwing_knife",
            "name": "Старый метательный нож",
            "category": "Расходники",
            "amount": 1,
            "combat_effect": {"type": "throw_damage", "bonus_player_level_percent": 0},
        }]
        battle = self.make_battle(player)
        initial_round = battle["round_number"]
        initial_hp = battle["enemies"][0]["current_hp"]

        pouch_text, _buttons = handle_battle_action(player, BATTLE_POUCH, random.Random(1))
        self.assertIn("выберите цель", pouch_text.casefold())
        target_text, target_buttons = handle_battle_action(player, f"{BATTLE_POUCH_ITEM_PREFIX}1", random.Random(1))
        self.assertIn("Выберите противника", target_text)
        self.assertTrue(any("Цель: 1" in row for row in target_buttons))

        status_text, _buttons = handle_battle_action(player, "Цель: 1", random.Random(1))
        self.assertIn("Старый метательный нож", status_text)
        self.assertEqual(player["active_battle"]["round_number"], initial_round)
        self.assertEqual(player["active_battle"]["enemies"][0]["current_hp"], initial_hp - 100)
        self.assertEqual(player["inventory"], [])

    def test_smoke_bomb_adds_escape_bonus_for_two_turns(self):
        player = self.make_player()
        player["inventory"] = [{
            "id": "homemade_smoke_bomb",
            "item_id": "homemade_smoke_bomb",
            "name": "Самодельная дымовая бомбочка",
            "category": "Расходники",
            "amount": 1,
            "combat_effect": {"type": "escape_bonus", "escape_bonus_percent": 20, "duration_turns": 2},
        }]
        self.make_battle(player)
        handle_battle_action(player, BATTLE_POUCH, random.Random(1))
        text, _buttons = handle_battle_action(player, f"{BATTLE_POUCH_ITEM_PREFIX}1", random.Random(1))
        self.assertIn("шанс сбежать", text.casefold())
        self.assertEqual(player["active_battle"]["player_state"]["escape_bonus_chance_percent"], 20)

        handle_battle_action(player, BATTLE_WAIT, random.Random(1))
        self.assertEqual(player["active_battle"]["player_state"]["escape_bonus_turns"], 1)

    def test_regeneration_and_cleansing_potions_work_from_pouch(self):
        player = self.make_player()
        player["inventory"] = [
            {
                "id": "minor_regeneration_potion",
                "item_id": "minor_regeneration_potion",
                "name": "Малое зелье регенерации",
                "category": "Расходники",
                "amount": 1,
                "combat_effect": {"type": "battle_regeneration", "regen_flat": 30, "regen_max_hp_percent": 2, "duration_turns": 2},
            },
            {
                "id": "common_cleansing_potion",
                "item_id": "common_cleansing_potion",
                "name": "Обычное зелье очищения",
                "category": "Расходники",
                "amount": 1,
                "combat_effect": {"type": "cleanse_debuffs"},
            },
        ]
        battle = self.make_battle(player)
        battle["player_state"]["current_hp"] = battle["player_state"]["max_hp"] - 80
        battle["player_state"]["debuffs"] = [{"id": "slow"}, {"id": "blind"}]

        handle_battle_action(player, BATTLE_POUCH, random.Random(1))
        handle_battle_action(player, f"{BATTLE_POUCH_ITEM_PREFIX}1", random.Random(1))
        before_wait_hp = player["active_battle"]["player_state"]["current_hp"]
        handle_battle_action(player, BATTLE_WAIT, random.Random(1))
        after_wait_hp = player["active_battle"]["player_state"]["current_hp"]
        self.assertGreater(after_wait_hp, before_wait_hp)

        handle_battle_action(player, BATTLE_POUCH, random.Random(1))
        handle_battle_action(player, f"{BATTLE_POUCH_ITEM_PREFIX}1", random.Random(2))
        self.assertEqual(len(player["active_battle"]["player_state"]["debuffs"]), 1)


    def test_battle_stimulant_is_inventory_only_and_applies_to_next_battle(self):
        player = self.make_player()
        item = {
            "id": "battle_stimulant",
            "item_id": "battle_stimulant",
            "name": "Боевой стимулятор",
            "category": "Расходники",
            "type": "potion",
            "amount": 1,
            "pouch_excluded": True,
            "use_effect": {"type": "battle_stimulant", "duration_seconds": 1800, "damage_bonus_percent": 30, "resource_max_bonus_percent": 20},
            "combat_effect": {"type": "battle_stimulant", "damage_bonus_percent": 30, "resource_max_bonus_percent": 20, "inventory_only": True},
        }
        player["inventory"] = [dict(item)]

        self.assertTrue(is_inventory_item_usable(item))
        battle = self.make_battle(player)
        pouch_text, _buttons = handle_battle_action(player, BATTLE_POUCH, random.Random(1))
        self.assertNotIn("Боевой стимулятор", pouch_text)

        # Принятие из инвентаря создаёт активный эффект. Новый бой подхватывает его.
        player.pop("active_battle", None)
        player["in_battle"] = False
        player["inventory"] = [dict(item)]
        apply_battle_stimulant_inventory_effect(player, item)
        boosted_battle = self.make_battle(player)
        player_state = boosted_battle["player_state"]
        self.assertTrue(player_state.get("battle_stimulant_active"))
        self.assertEqual(player_state.get("combat_damage_bonus_percent"), 30)
        self.assertGreater(player_state.get("max_spirit"), 0)
        self.assertGreater(player_state.get("max_mana"), 0)

    def test_old_iron_sword_poverty_damage_never_makes_money_negative_and_penalizes_xp(self):
        player = self.make_player()
        player["money"] = 10
        player["money_copper"] = 10
        player["equipment"] = {
            "weapon1": {"id": "old_iron_sword", "item_id": "old_iron_sword", "name": "Старый железный меч", "category": "weapon"}
        }
        battle = self.make_battle(player)
        for enemy in battle["enemies"]:
            enemy["dodge"] = 0
            enemy["physical_defense"] = 0
        player["skills"]["equipped"] = []

        text, _buttons = handle_battle_action(player, BATTLE_WAIT, random.Random(1))
        # wait does not hit, so use internal fallback normal attack by direct action for regression coverage
        player["active_battle"] = battle
        player["in_battle"] = True
        text, _buttons = handle_battle_action(player, "Обычная атака", random.Random(1))
        self.assertIn("Бедность", text)
        self.assertEqual(player["money_copper"], 0)
        self.assertEqual(player["money"], 0)
        scaling = old_iron_sword_scaling(100)
        self.assertGreater(scaling["bonus_damage"], 0)
        self.assertGreater(scaling["mob_xp_penalty_percent"], 0)


if __name__ == "__main__":
    unittest.main()
