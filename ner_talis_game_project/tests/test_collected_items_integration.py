import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.city_service import process_world_action
from services.crafting_service import _crafted_output_item
from services.inventory_service import add_inventory_item
from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item
from services.registration_service import create_player, load_races
from storage.json_storage import JsonStorage


class CollectedItemsIntegrationTest(unittest.TestCase):
    def make_storage_player(self):
        tmp = tempfile.TemporaryDirectory()
        storage = JsonStorage(str(Path(tmp.name) / "players.json"))
        player = create_player(
            game_id="NT-COLLECTED",
            platform="telegram",
            external_user_id="222",
            name="Сборщик",
            race_id="human",
            races=load_races("data/races.json"),
        )
        player["inventory"] = []
        storage.save_new_player(player, "telegram", "222")
        return tmp, storage, storage.get_player_by_game_id("NT-COLLECTED")

    def add_item(self, player, item_id, amount):
        add_inventory_item(player, item_id, amount, item_id=item_id)

    def test_collected_items_are_registered_with_assets_and_effects(self):
        sword = get_item_definition_by_id("simple_sword")
        self.assertIsNotNone(sword)
        self.assertEqual(sword["weapon_type"], "sword")
        self.assertTrue(sword.get("quality_variants"))
        self.assertTrue(Path("web/public" + sword["icon"]).exists())

        energy_potion = get_item_definition_by_id("simple_energy_potion")
        self.assertEqual(energy_potion.get("energy_restore"), 20)
        self.assertTrue(Path("web/public" + energy_potion["icon"]).exists())

        arrow = get_item_definition_by_id("arrow_for_bow")
        self.assertEqual(arrow.get("loads_into"), "arrow_quiver")
        self.assertTrue(Path("web/public" + arrow["icon"]).exists())

    def test_new_forge_weapon_recipe_creates_equippable_simple_sword(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        self.add_item(player, "iron_ingot", 2)
        self.add_item(player, "leather_strip", 2)
        storage.update_player(player)

        result = process_world_action(storage, player, "Кузница", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-COLLECTED"), "Оружие", "telegram")
        player = storage.get_player_by_game_id("NT-COLLECTED")
        recipe_ids = player["crafting_context"]["recipe_ids"]
        sword_number = recipe_ids.index("forge_simple_sword") + 1
        result = process_world_action(storage, player, f"Крафт №{sword_number}", "telegram")
        self.assertIn("Простой меч", result.text)
        process_world_action(storage, storage.get_player_by_game_id("NT-COLLECTED"), "Создать", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-COLLECTED"), "1", "telegram")
        self.assertEqual(result.scheduled_timer["seconds"], 60)
        player = storage.get_player_by_game_id("NT-COLLECTED")
        player["active_timer"]["ends_at"] = 0
        storage.update_player(player)
        with patch("services.crafting_service.random.randint", return_value=1):
            result = process_world_action(storage, player, "Проверить таймер", "telegram")
        self.assertIn("Простой меч", result.text)
        restored = storage.get_player_by_game_id("NT-COLLECTED")
        created = next(item for item in restored["inventory"] if item.get("item_id") == "simple_sword")
        self.assertEqual(created.get("targetSlotKey"), "weapon1")
        self.assertEqual(created.get("weapon_type"), "sword")
        self.assertEqual(created.get("max_stack"), 1)


    def test_crafted_quality_variants_use_requested_chances_and_sell_prices(self):
        with patch("services.crafting_service.random.randint", return_value=10):
            rare = _crafted_output_item("simple_sword", "Простой меч", 1)
        self.assertEqual(rare.get("quality"), "редкий")
        self.assertEqual(rare.get("sell_price_copper"), 500)
        self.assertTrue(rare.get("can_sell"))

        with patch("services.crafting_service.random.randint", return_value=11):
            uncommon = _crafted_output_item("simple_sword", "Простой меч", 1)
        self.assertEqual(uncommon.get("quality"), "необычный")
        self.assertEqual(uncommon.get("sell_price_copper"), 300)
        self.assertTrue(uncommon.get("can_sell"))

        with patch("services.crafting_service.random.randint", return_value=50):
            uncommon_edge = _crafted_output_item("simple_sword", "Простой меч", 1)
        self.assertEqual(uncommon_edge.get("quality"), "необычный")

        with patch("services.crafting_service.random.randint", return_value=51):
            common = _crafted_output_item("simple_sword", "Простой меч", 1)
        self.assertEqual(common.get("quality"), "обычный")
        self.assertLess(common.get("sell_price_copper", 0), 300)

    def test_leatherwork_blanks_use_canonical_simple_hide_and_tendon(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        self.add_item(player, "simple_tendon", 3)
        self.add_item(player, "simple_hide", 1)
        storage.update_player(player)

        process_world_action(storage, player, "Кожевенная мастерская", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-COLLECTED"), "Заготовки", "telegram")
        self.assertIn("✅ Верёвка", result.text)
        self.assertIn("✅ Выделанная кожа", result.text)
        # Список раздела показывает только сами изделия; ингредиенты раскрываются
        # лишь по нажатию «Крафт №N», а не в общем списке.
        self.assertNotIn("Сухожилия ×3", result.text)
        self.assertIn("Крафт №1", result.text)

    def test_legacy_hide_and_tendon_ids_are_canonicalized_for_old_inventories(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)
        self.add_item(player, "strong_tendon", 3)
        self.add_item(player, "small_pelt", 1)
        storage.update_player(player)

        restored = storage.get_player_by_game_id("NT-COLLECTED")
        ids = {item.get("id") for item in restored["inventory"]}
        self.assertIn("simple_tendon", ids)
        self.assertIn("simple_hide", ids)

        process_world_action(storage, restored, "Кожевенная мастерская", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-COLLECTED"), "Заготовки", "telegram")
        self.assertIn("✅ Верёвка", result.text)
        self.assertIn("✅ Выделанная кожа", result.text)


    def test_forge_has_weapon_recipes_for_all_basic_combat_paths(self):
        tmp, storage, player = self.make_storage_player()
        self.addCleanup(tmp.cleanup)

        process_world_action(storage, player, "Кузница", "telegram")
        result = process_world_action(storage, storage.get_player_by_game_id("NT-COLLECTED"), "Оружие", "telegram")

        expected_items = {
            "simple_sword": "Простой меч",
            "simple_dagger": "Простой кинжал",
            "simple_axe": "Простой топор",
            "simple_hammer": "Простой молот",
            "simple_bow": "Простой лук",
            "simple_crossbow": "Простой арбалет",
            "simple_shield": "Простой щит",
            "simple_staff": "Простой посох",
            "simple_magic_book": "Простая книга",
        }
        for item_id, name in expected_items.items():
            definition = get_item_definition_by_id(item_id)
            self.assertIsNotNone(definition, item_id)
            self.assertEqual(definition.get("max_stack"), 1)
            self.assertTrue(definition.get("quality_variants"), item_id)
            self.assertTrue(Path("web/public" + definition["icon"]).exists(), definition["icon"])
            self.assertIn(name, result.text)

        recipe_ids = storage.get_player_by_game_id("NT-COLLECTED")["crafting_context"]["recipe_ids"]
        for recipe_id in (
            "forge_simple_sword",
            "forge_simple_dagger",
            "forge_simple_axe",
            "forge_simple_hammer",
            "forge_simple_bow",
            "forge_simple_crossbow",
            "forge_simple_shield",
            "forge_simple_staff",
            "forge_simple_magic_book",
        ):
            self.assertIn(recipe_id, recipe_ids)

    def test_ammo_aliases_stay_compatible_with_quiver_system(self):
        arrow = registry_item_to_inventory_item(get_item_definition_by_id("arrow_for_bow"), 5)
        bolt = registry_item_to_inventory_item(get_item_definition_by_id("bolt_for_crossbow"), 5)
        self.assertEqual(arrow.get("loads_into"), "arrow_quiver")
        self.assertEqual(bolt.get("loads_into"), "bolt_quiver")
        self.assertEqual(arrow.get("category"), "Расходники")
        self.assertEqual(bolt.get("category"), "Расходники")
        self.assertEqual(arrow.get("type"), "Стрела")
        self.assertEqual(bolt.get("type"), "Болт")


if __name__ == "__main__":
    unittest.main()
