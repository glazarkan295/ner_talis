import random
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.external_location_service import (
    CHECK_TIMER,
    INSPECT_ARCH,
    PAY_100_SILVER,
    RETURN_SMALL_PLATEAU,
    SET_CAMP,
    SMALL_PLATEAU,
    START_SEARCH,
    TAKE_CURSED_COINS,
    APPROACH_ARCH,
    handle_external_location_action,
    location_text,
)
from services.small_plateau_service import (
    ANCIENT_CURSE_ID,
    AMULET_BURN_ID,
    CURSE_ACHIEVEMENT_ID,
    CURSE_BEARER_EFFECT_ID,
    SEEKER_ACHIEVEMENT_ID,
    add_achievement,
    add_effect,
    apply_pvp_kill_postmortem_curse,
    cleanse_ancient_curse_at_hidden_place,
    filter_seeker_only,
    handle_cursed_coin_choice,
    has_effect,
    player_has_seeker,
    register_ancient_curse_active_day,
    roll_ancient_curse_trigger,
    resolve_small_plateau_search,
)
from services.player_time_service import advance_all_players_time, advance_player_time, HOUR_SECONDS
from services.item_registry import get_item_definition_by_id
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class SmallPlateauIntegrationTest(unittest.TestCase):
    def make_player_and_storage(self, *, energy: int = 100):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        storage = JsonStorage(str(Path(tmp_dir.name) / "players.json"))
        races = load_races("data/races.json")
        game_id = storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform="telegram",
            external_user_id="sp1",
            name="Искатель плато",
            race_id="human",
            races=races,
        )
        player["energy"] = energy
        player["current_energy"] = energy
        player["max_energy"] = 100
        storage.save_new_player(player, "telegram", "sp1")
        return storage, storage.get_player_by_platform("telegram", "sp1")

    def test_small_plateau_is_enterable_and_has_arch_actions(self):
        storage, player = self.make_player_and_storage()
        response = handle_external_location_action(storage, player, SMALL_PLATEAU, rng=random.Random(1))
        self.assertIn("Малое плато", response.text)
        self.assertIn([START_SEARCH], response.buttons)
        self.assertIn([APPROACH_ARCH], response.buttons)

        player = storage.get_player_by_platform("telegram", "sp1")
        arch = handle_external_location_action(storage, player, APPROACH_ARCH, rng=random.Random(2))
        self.assertIn("Древняя арка", arch.text)
        self.assertIn([INSPECT_ARCH], arch.buttons)

        player = storage.get_player_by_platform("telegram", "sp1")
        inspected = handle_external_location_action(storage, player, INSPECT_ARCH, rng=random.Random(3))
        self.assertIn("полустёртые", inspected.text)
        self.assertIn([RETURN_SMALL_PLATEAU], inspected.buttons)

    def test_small_plateau_search_timer_uses_standard_energy_and_resolves(self):
        storage, player = self.make_player_and_storage(energy=100)
        handle_external_location_action(storage, player, SMALL_PLATEAU, rng=random.Random(1))
        player = storage.get_player_by_platform("telegram", "sp1")
        started = handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(2))
        self.assertIn("Время поиска: 30 сек", started.text)
        self.assertIn("Потрачено энергии: 2", started.text)
        player = storage.get_player_by_platform("telegram", "sp1")
        player["active_timer"]["ends_at"] = time.time() - 1
        storage.update_player(player)
        completed = handle_external_location_action(storage, player, CHECK_TIMER, rng=random.Random(3))
        self.assertIn("Поиск завершён", completed.text)
        updated = storage.get_player_by_platform("telegram", "sp1")
        self.assertEqual("small_plateau", updated.get("current_location"))
        self.assertEqual(1, updated.get("small_plateau", {}).get("search_count"))

    def test_search_completion_survives_bot_resave_of_original_player(self):
        # Воспроизводит баг «застревания» на локации: бот после действия
        # пересохраняет ИСХОДНЫЙ объект игрока (handlers/city.py). Если завершение
        # таймера применилось к атомарно перезагруженной копии, стейл-оригинал
        # затирал снятый таймер и награды → бесконечный повтор поиска.
        storage, player = self.make_player_and_storage(energy=100)
        handle_external_location_action(storage, player, SMALL_PLATEAU, rng=random.Random(1))
        storage.update_player(player)

        player = storage.get_player_by_platform("telegram", "sp1")
        handle_external_location_action(storage, player, START_SEARCH, rng=random.Random(2))
        storage.update_player(player)  # бот пересохраняет исходный объект

        player = storage.get_player_by_platform("telegram", "sp1")
        player["active_timer"]["ends_at"] = time.time() - 1
        storage.update_player(player)

        # Бот: загрузка → действие → пересохранение ТОГО ЖЕ объекта.
        player = storage.get_player_by_platform("telegram", "sp1")
        completed = handle_external_location_action(storage, player, CHECK_TIMER, rng=random.Random(3))
        storage.update_player(player)

        self.assertIn("Поиск завершён", completed.text)
        updated = storage.get_player_by_game_id(player["game_id"])
        self.assertIsNone(updated.get("active_timer"))  # таймер снят, не застрял
        self.assertEqual(1, updated.get("small_plateau", {}).get("search_count"))

    def test_cursed_coins_first_take_never_curses_and_adds_silver_value(self):
        player = {"hp": 100, "max_hp": 100, "money_copper": 0, "money": 0}
        result = handle_cursed_coin_choice(player, take_coins=True, rng=random.Random(1))
        self.assertEqual(0.0, result["curse_chance"])
        self.assertFalse(result["curse_applied"])
        self.assertIn(player.get("money_copper"), (1000, 2000))

    def test_curse_cleanse_spends_100_silver_and_deals_damage(self):
        player = {"hp": 100, "max_hp": 100, "money_copper": 100000, "money": 100000}
        add_effect(player, ANCIENT_CURSE_ID, {"id": ANCIENT_CURSE_ID, "effect_id": ANCIENT_CURSE_ID, "active": True})
        result = cleanse_ancient_curse_at_hidden_place(player)
        self.assertTrue(result["success"])
        self.assertEqual(0, player["money_copper"])
        self.assertEqual(60, player["hp"])

    def test_search_milestone_adds_amulet_burn(self):
        player = {"hp": 100, "max_hp": 100, "small_plateau": {"search_count": 399}}
        resolve_small_plateau_search(player, random.Random(4))
        self.assertTrue(any((effect.get("id") == AMULET_BURN_ID or effect.get("effect_id") == AMULET_BURN_ID) for effect in player.get("active_effects", [])))

    def test_curse_achievement_after_60_active_days(self):
        player = {}
        add_effect(player, ANCIENT_CURSE_ID, {"id": ANCIENT_CURSE_ID, "effect_id": ANCIENT_CURSE_ID, "active": True})
        # Спека: «больше 60 дней» — достижение выдаётся строго после 60-го дня.
        result = None
        for _ in range(60):
            result = register_ancient_curse_active_day(player, 30)
        self.assertIsNone(result)
        result = register_ancient_curse_active_day(player, 30)  # 61-й день
        self.assertIsNotNone(result)
        self.assertTrue(any(value == "curse_what_curse" or (isinstance(value, dict) and value.get("achievement_id") == "curse_what_curse") for value in player.get("achievements", [])))
        self.assertTrue(has_effect(player, CURSE_BEARER_EFFECT_ID))
        self.assertIn("Носитель проклятья", result["text"])

    def test_curse_achievement_grants_bearer_effect_for_legacy_achievement(self):
        player = {"achievements": [CURSE_ACHIEVEMENT_ID]}
        add_achievement(player, CURSE_ACHIEVEMENT_ID)
        self.assertTrue(has_effect(player, CURSE_BEARER_EFFECT_ID))

    def test_curse_achievement_no_longer_weakens_ancient_curse(self):
        class FixedRandom:
            def random(self):
                return 0.15

        player = {"hp": 100, "max_hp": 100, "money_copper": 100000, "money": 100000}
        add_effect(player, ANCIENT_CURSE_ID, {"id": ANCIENT_CURSE_ID, "effect_id": ANCIENT_CURSE_ID, "active": True})
        add_achievement(player, CURSE_ACHIEVEMENT_ID)

        trigger = roll_ancient_curse_trigger(player, "location_search", rng=FixedRandom())
        self.assertTrue(trigger["triggered"])  # 15% still triggers because chance remains 20%.

        result = cleanse_ancient_curse_at_hidden_place(player)
        self.assertTrue(result["success"])
        self.assertEqual(60, player["hp"])  # −40% HP, not the old reduced −20%.

    def test_pvp_kill_applies_postmortem_curse_to_killer(self):
        killer = {"game_id": "NT-KILLER", "name": "Убийца"}
        victim = {"game_id": "NT-VICTIM", "name": "Носитель"}
        add_achievement(victim, CURSE_ACHIEVEMENT_ID)

        result = apply_pvp_kill_postmortem_curse(killer, victim, rng=random.Random(1), now_ts=4_000_000_000)

        self.assertTrue(result["applied"])
        effect = result["effect"]
        self.assertEqual("curse_bearer_pvp_death", effect["source"])
        self.assertEqual("curse", effect["type"])
        self.assertEqual(3600, effect["duration_seconds"])
        self.assertEqual("NT-VICTIM", effect["pvp_victim_id"])
        self.assertTrue(has_effect(killer, effect["effect_id"]))

    def test_pvp_kill_without_curse_bearer_does_not_affect_killer(self):
        killer = {"game_id": "NT-KILLER"}
        victim = {"game_id": "NT-VICTIM"}

        result = apply_pvp_kill_postmortem_curse(killer, victim, rng=random.Random(1), now_ts=1_700_000_000)

        self.assertFalse(result["applied"])
        self.assertEqual([], killer.get("active_effects", []))

    def test_amulet_burn_ticks_hourly_via_player_time(self):
        player = {"hp": 100, "max_hp": 100}
        add_effect(player, AMULET_BURN_ID, {"id": AMULET_BURN_ID, "effect_id": AMULET_BURN_ID, "active": True})
        now = 1_000_000
        # Первый вызов лишь ставит метку времени, без урона.
        self.assertEqual([], advance_player_time(player, now))
        self.assertEqual(100, player["hp"])
        # Через 3 часа — 3 тика по 5 HP и 3 сообщения.
        messages = advance_player_time(player, now + 3 * HOUR_SECONDS)
        self.assertEqual(3, len(messages))
        self.assertEqual(85, player["hp"])
        self.assertTrue(all("5 HP" in m for m in messages))

    def test_seeker_only_events_hidden_until_achievement(self):
        events = [
            {"id": "common", "weight": 5},
            {"id": "secret", "weight": 5, "seeker_only": True},
        ]
        player = {}
        self.assertFalse(player_has_seeker(player))
        visible = filter_seeker_only(player, events)
        self.assertEqual([e["id"] for e in visible], ["common"])  # обычный игрок не видит секрет

        add_achievement(player, SEEKER_ACHIEVEMENT_ID)
        self.assertTrue(player_has_seeker(player))
        visible_seeker = filter_seeker_only(player, events)
        self.assertEqual({e["id"] for e in visible_seeker}, {"common", "secret"})

    def test_scheduler_ticks_amulet_burn_for_all_players(self):
        storage, player = self.make_player_and_storage()
        player["hp"] = 100
        player["max_hp"] = 100
        add_effect(player, AMULET_BURN_ID, {"id": AMULET_BURN_ID, "effect_id": AMULET_BURN_ID, "active": True})
        player["amulet_burn_last_tick_ts"] = 1_000_000
        game_id = str(player.get("game_id"))
        storage.update_player(player)

        updated = advance_all_players_time(storage, now_ts=1_000_000 + 3 * HOUR_SECONDS)
        self.assertGreaterEqual(updated, 1)
        after = storage.get_player_by_game_id(game_id)
        self.assertEqual(after["hp"], 85)  # 3 часа × 5 HP
        self.assertEqual(len(after.get("pending_bot_messages", [])), 3)

    def test_background_tick_does_not_inflate_curse_activity(self):
        # count_activity=False: фоновый тик не должен копить «активные секунды».
        from services.player_time_service import _advance
        player = {"curse_day_tracker": {"date": "2999-01-01", "active_seconds": 0, "last_action_ts": 0}}
        import datetime as _dt
        now = int(_dt.datetime(2999, 1, 1, 12, tzinfo=_dt.timezone.utc).timestamp())
        _advance(player, now, count_activity=False)
        self.assertEqual(player["curse_day_tracker"]["active_seconds"], 0)

    def test_small_plateau_items_are_in_registry(self):
        self.assertIsNotNone(get_item_definition_by_id("old_brooch"))
        self.assertIsNotNone(get_item_definition_by_id("old_medallion"))
        # Описание локации стало атмосферным; стоимость поиска показывается
        # игроку в момент начала поиска, а не в тексте локации.
        self.assertIn("Малое плато", location_text("small_plateau"))


class LegacyEffectFlagTest(unittest.TestCase):
    def test_has_effect_accepts_legacy_key_flag(self):
        # Codex P2: старые сейвы хранят эффект как ключ-флаг {"ancient_curse":
        # True}; has_effect должен признавать это активностью, иначе теряется
        # проклятие/амулет.
        player = {"effects": {ANCIENT_CURSE_ID: True}}
        self.assertTrue(has_effect(player, ANCIENT_CURSE_ID))

    def test_has_effect_false_for_falsy_legacy_flag(self):
        player = {"effects": {ANCIENT_CURSE_ID: False}}
        self.assertFalse(has_effect(player, ANCIENT_CURSE_ID))

    def test_has_effect_dict_form_still_works(self):
        player = {"effects": {ANCIENT_CURSE_ID: {"id": ANCIENT_CURSE_ID}}}
        self.assertTrue(has_effect(player, ANCIENT_CURSE_ID))


if __name__ == "__main__":
    unittest.main()
