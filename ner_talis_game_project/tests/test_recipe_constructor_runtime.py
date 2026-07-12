import os,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from services import crafting_service as runtime
from services import recipe_constructor_service as recipes
from services import workshop_constructor_service as workshops

class RecipeConstructorRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.saved=os.environ.get("RECIPE_CONSTRUCTOR_PATH"); os.environ["RECIPE_CONSTRUCTOR_PATH"]=str(Path(self.tmp.name)/"recipes.json"); self.addCleanup(self.restore)
        self.saved_workshop=os.environ.get("WORKSHOP_CONSTRUCTOR_PATH"); os.environ["WORKSHOP_CONSTRUCTOR_PATH"]=str(Path(self.tmp.name)/"workshops.json")
        runtime.invalidate_crafting_recipe_cache()
    def restore(self):
        if self.saved is None: os.environ.pop("RECIPE_CONSTRUCTOR_PATH",None)
        else: os.environ["RECIPE_CONSTRUCTOR_PATH"]=self.saved
        if self.saved_workshop is None: os.environ.pop("WORKSHOP_CONSTRUCTOR_PATH",None)
        else: os.environ["WORKSHOP_CONSTRUCTOR_PATH"]=self.saved_workshop
        runtime.invalidate_crafting_recipe_cache()
    def test_published_recipe_is_live_and_disabled_recipe_disappears(self):
        recipes.store().create("live_recipe",{"name":"Live","workshop":"forge","output_item_id":"sword","output_amount":1,"ingredients":[{"item_id":"iron","amount":2}],"craft_time":10,"success_chance":100})
        recipes.store().set_status("live_recipe",recipes.STATUS_PUBLISHED,force=True); runtime.invalidate_crafting_recipe_cache()
        live=runtime.recipe_by_id()["live_recipe"]; self.assertTrue(live["constructor_live"]); self.assertEqual(live["result"]["item_id"],"sword"); self.assertEqual(live["output"]["item_id"],"sword")
        recipes.store().set_status("live_recipe",recipes.STATUS_DISABLED,force=True); runtime.invalidate_crafting_recipe_cache()
        self.assertNotIn("live_recipe",runtime.recipe_by_id())

    def test_alternative_ingredient_tool_and_durability_are_live(self):
        player={"inventory":[
            {"item_id":"silver_ingot","name":"Silver","amount":2},
            {"item_id":"hammer","name":"Hammer","amount":1,"durability":8,"max_durability":10},
        ]}
        recipe={"ingredients":[{"item_id":"iron_ingot","alternatives":["silver_ingot"],"amount":2}],
                "tools":[{"item_id":"hammer","required":True,"min_durability":5,"durability_loss":3}]}
        self.assertTrue(runtime._has_ingredients(player,recipe,1))
        self.assertTrue(runtime._consume_recipe_ingredients(player,recipe,1))
        self.assertFalse(any(row.get("item_id")=="silver_ingot" for row in player["inventory"]))
        self.assertEqual(next(row for row in player["inventory"] if row.get("item_id")=="hammer")["durability"],5)

    def test_recipe_usage_lists_dependencies_and_extended_item_roles(self):
        recipes.store().create("linked",{"name":"Linked","workshop":"forge","workshop_id":"forge_main",
            "output_item_id":"sword","ingredients":[{"item_id":"iron","amount":1,"alternatives":["silver"]}],
            "tools":[{"item_id":"hammer"}],"results":[{"item_id":"scrap"}],"effect_ids":["blessing"]})
        usage=recipes.recipe_usage("linked")
        self.assertTrue(any(row["kind"]=="workshop" and row["id"]=="forge_main" for row in usage))
        self.assertTrue(any(row["kind"]=="effect" and row["id"]=="blessing" for row in usage))
        self.assertIn("инструмент", recipes.where_used("hammer")[0]["fields"])
        self.assertIn("дополнительный/побочный результат", recipes.where_used("scrap")[0]["fields"])

    def test_published_workshop_button_opens_only_its_published_recipes(self):
        workshops.store().create("village_forge", {"name":"Деревенская кузница","button_text":"Открыть деревенскую кузницу","type":"forge","location":"village"})
        workshops.store().set_status("village_forge","published",force=True)
        recipes.store().create("village_sword",{"name":"Деревенский меч","workshop":"forge","workshop_id":"village_forge","output_item_id":"sword","ingredients":[]})
        recipes.store().set_status("village_sword","published",force=True); runtime.invalidate_crafting_recipe_cache()
        class Storage:
            def update_player(self,value): self.saved=value
        player={"current_location":"village","current_zone":"village","inventory":[]}
        self.assertTrue(runtime.should_handle_crafting_action(player,"Открыть деревенскую кузницу"))
        response=runtime.handle_crafting_action(Storage(),player,"Открыть деревенскую кузницу")
        self.assertIn("sword",response.text)
        self.assertEqual(player["crafting_context"]["constructor_workshop_id"],"village_forge")

    def test_start_checks_level_blueprint_materials_and_tools_with_admin_texts(self):
        recipe={"id":"guarded","workshop":"forge","output_item_id":"sword","output":{"item_id":"sword","amount":1},
                "player_level":5,"blueprint_required":True,"blueprint_id":"plan","ingredients":[{"item_id":"ore","amount":1}],
                "tools":[{"item_id":"hammer","required":True}],"text_not_enough_level":"Нужен пятый уровень",
                "text_unavailable":"Нужен чертёж","text_not_enough_ingredients":"Нет руды","text_not_enough_tool":"Нет молота"}
        class Storage:
            def update_player(self,value): self.saved=value
        player={"level":1,"energy":10,"money":0,"inventory":[],"crafting_context":{"selected_recipe_id":"guarded","workshop":"forge","step":"quantity"}}
        with patch.object(runtime,"recipe_by_id",return_value={"guarded":recipe}):
            self.assertIn("Нужен пятый уровень",runtime._start_craft(Storage(),player,"1").text)
            player["level"]=5
            self.assertIn("Нужен чертёж",runtime._start_craft(Storage(),player,"1").text)
            player["inventory"]=[{"item_id":"plan","amount":1}]
            self.assertIn("Нет руды",runtime._start_craft(Storage(),player,"1").text)
            player["inventory"].append({"item_id":"ore","amount":1})
            self.assertIn("Нет молота",runtime._start_craft(Storage(),player,"1").text)

if __name__=="__main__":unittest.main()
