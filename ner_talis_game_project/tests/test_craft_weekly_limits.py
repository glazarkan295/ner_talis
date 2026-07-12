import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.craft_weekly_limit_runtime import admin_view, check, consume, week_key
from services import crafting_service as crafting
from unittest.mock import patch


class CraftWeeklyLimitTest(unittest.TestCase):
    def test_limit_consumes_quantity_and_blocks_overflow(self):
        player = {}
        recipe = {"weekly_limits": [{"id": "weekly_swords", "limit_type": "recipe_count", "max_per_week": 3, "exhausted_text": "Мечи закончились"}]}
        self.assertEqual(check(player, recipe, quantity=2), (True, ""))
        consume(player, recipe, quantity=2)
        self.assertEqual(check(player, recipe, quantity=2), (False, "Мечи закончились"))
        row = admin_view(player, recipe)[0]
        self.assertEqual((row["used"], row["remaining"]), (2, 1))

    def test_result_limit_scales_by_output_amount(self):
        player = {}
        recipe = {"weekly_limits": [{"id": "potions", "limit_type": "result_count", "max_per_week": 6}]}
        consume(player, recipe, quantity=2, result_amount=3)
        self.assertFalse(check(player, recipe, quantity=1, result_amount=1)[0])

    def test_iso_week_key(self):
        self.assertEqual(week_key(datetime(2026, 1, 1, tzinfo=timezone.utc)), "2026-W01")

    def test_cancel_timer_refunds_resources_money_energy_and_limit(self):
        recipe = {"id": "sword", "output_item_id": "sword", "output_amount": 1, "can_cancel": True,
                  "weekly_limits": [{"id": "weekly", "limit_type": "recipe_count", "max_per_week": 2}]}
        player = {"inventory": [], "money": 5, "energy": 2, "craft_weekly_usage": {week_key(): {"weekly": 1}},
                  "active_timer": {"type": "craft", "location_id": "forge", "craft": {"recipe_id": "sword", "quantity": 1,
                    "charged_cost": 10, "charged_energy": 3, "consumed_items": [{"item_id": "ore", "amount": 2}]}}}
        class Storage:
            def update_player(self, value): self.saved = value
        storage = Storage()
        with patch.object(crafting, "recipe_by_id", return_value={"sword": recipe}):
            response = crafting.cancel_craft_timer(storage, player)
        self.assertIn("отменено", response.text.lower())
        self.assertEqual((player["money"], player["energy"]), (15, 5))
        self.assertEqual(player["craft_weekly_usage"][week_key()]["weekly"], 0)
        self.assertEqual(next(row for row in player["inventory"] if row.get("item_id") == "ore")["amount"], 2)
        self.assertIsNone(player["active_timer"])

    def test_queue_reserves_resources_and_starts_next_after_completion(self):
        recipe = {"id": "queued", "name": "Слиток", "workshop": "smeltery", "output_item_id": "ingot", "output_amount": 1,
                  "output": {"item_id": "ingot", "amount": 1}, "ingredients": [{"item_id": "ore", "amount": 1}],
                  "craft_time_seconds": 1, "success_chance": 100, "can_queue": True, "free": True}
        player = {"inventory": [{"item_id": "ore", "name": "Руда", "amount": 1}], "money": 0, "energy": 10,
                  "active_timer": {"id": "first", "type": "craft", "ends_at": 9999999999, "location_id": "seldar_smeltery", "craft": {"recipe_id": "queued", "quantity": 1, "workshop_id": "smeltery"}}}
        class Storage:
            def update_player(self, value): self.saved = value
        storage = Storage()
        with patch.object(crafting, "recipe_by_id", return_value={"queued": recipe}):
            queued = crafting.enqueue_same_craft(storage, player)
            self.assertIn("добавлен в очередь", queued.text)
            self.assertEqual(len(player["craft_queue"]), 1)
            self.assertEqual(player["active_timer"]["id"], "first")
            player["active_timer"]["ends_at"] = 0
            done = crafting.complete_craft_timer(storage, player, "first")
        self.assertIn("Следующая позиция очереди запущена", done.text)
        self.assertIsNotNone(done.scheduled_timer)
        self.assertEqual(player["craft_queue"], [])
        self.assertEqual(player["active_timer"]["craft"]["recipe_id"], "queued")

    def test_partial_success_reduces_output_and_uses_own_text(self):
        recipe = {"id": "partial", "workshop": "smeltery", "output": {"item_id": "ingot", "amount": 4},
                  "output_item_id": "ingot", "output_amount": 4, "partial_result_percent": 50, "text_partial_success": "Частичный результат"}
        player = {"inventory": [], "active_timer": {"id": "partial_timer", "type": "craft", "ends_at": 0, "location_id": "seldar_smeltery",
                  "craft": {"recipe_id": "partial", "quantity": 1, "workshop_id": "smeltery", "partial_success": True}}}
        class Storage:
            def update_player(self, value): self.saved = value
        with patch.object(crafting, "recipe_by_id", return_value={"partial": recipe}):
            response = crafting.complete_craft_timer(Storage(), player, "partial_timer")
        self.assertIn("Частичный результат", response.text)
        self.assertEqual(next(row for row in player["inventory"] if row.get("item_id") == "ingot")["amount"], 2)

    def test_failure_returns_configured_material_share_and_grants_failure_byproduct(self):
        recipe = {"id": "failed", "workshop": "smeltery", "output": {"item_id": "ingot", "amount": 1},
                  "failure_material_policy": "return_percent", "failure_return_percent": 50,
                  "byproducts": [{"item_id": "slag", "amount": 1, "chance": 100, "when": "failure"}]}
        player = {"inventory": [], "active_timer": {"id": "fail_timer", "type": "craft", "ends_at": 0, "location_id": "seldar_smeltery",
                  "craft": {"recipe_id": "failed", "quantity": 1, "workshop_id": "smeltery", "craft_failure": True,
                            "consumed_items": [{"item_id": "ore", "amount": 4}]}}}
        class Storage:
            def update_player(self, value): self.saved = value
        with patch.object(crafting, "recipe_by_id", return_value={"failed": recipe}), patch("services.crafting_service.random.randint", return_value=1):
            crafting.complete_craft_timer(Storage(), player, "fail_timer")
        self.assertEqual(next(row for row in player["inventory"] if row.get("item_id") == "ore")["amount"], 2)
        self.assertEqual(next(row for row in player["inventory"] if row.get("item_id") == "slag")["amount"], 1)

    def test_failure_can_open_event_or_start_explicit_mob_battle(self):
        base = {"id": "consequence", "workshop": "smeltery", "output": {"item_id": "ingot", "amount": 1}}
        class Storage:
            def update_player(self, value): self.saved = value
        event_player = {"inventory": [], "current_location": "forge", "active_timer": {"id": "event_timer", "type": "craft", "ends_at": 0,
                        "location_id": "forge", "craft": {"recipe_id": "consequence", "quantity": 1, "workshop_id": "smeltery", "craft_failure": True}}}
        event_recipe = {**base, "failure_event_id": "smoke_event"}
        with patch.object(crafting, "recipe_by_id", return_value={"consequence": event_recipe}), patch("services.world_runtime.render_event", return_value={"text": "Мастерскую заволокло дымом", "buttons": [["Осмотреться"]]}):
            response = crafting.complete_craft_timer(Storage(), event_player, "event_timer")
        self.assertEqual(event_player["constructor_event_id"], "smoke_event")
        self.assertIn("заволокло дымом", response.text)
        self.assertEqual(response.buttons, [["Осмотреться"]])

        battle_player = {"inventory": [], "current_location": "forge", "active_timer": {"id": "battle_timer", "type": "craft", "ends_at": 0,
                         "location_id": "forge", "craft": {"recipe_id": "consequence", "quantity": 1, "workshop_id": "smeltery", "craft_failure": True}}}
        battle_recipe = {**base, "failure_battle_mob_id": "fire_elemental"}
        def start_battle(player, mob_id, **_kwargs):
            player["in_battle"] = True
            return {"enemies": [{"source_mob_id": mob_id}]}, "Появился огненный элементаль"
        with patch.object(crafting, "recipe_by_id", return_value={"consequence": battle_recipe}), patch("services.pve_battle_service.create_battle_for_constructor_mob", side_effect=start_battle):
            response = crafting.complete_craft_timer(Storage(), battle_player, "battle_timer")
        self.assertTrue(battle_player["in_battle"])
        self.assertIn("огненный элементаль", response.text)
        self.assertIn("Атаковать", sum(response.buttons, []))


if __name__ == "__main__":
    unittest.main()
