import os,sys,tempfile,unittest,random
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services import world_event_service as events
from services import world_event_runtime as runtime
from storage.json_storage import JsonStorage

class WorldEventRuntimeTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);base=Path(self.tmp.name);keys=("WORLD_EVENTS_PATH","WORLD_EVENT_LOOT_STATE_PATH","ECONOMY_CONSTRUCTOR_PATH","BOT_MESSAGE_DISPATCHER_ENABLED");self.old={k:os.environ.get(k) for k in keys};os.environ["WORLD_EVENTS_PATH"]=str(base/"events.json");os.environ["WORLD_EVENT_LOOT_STATE_PATH"]=str(base/"loot.json");os.environ["ECONOMY_CONSTRUCTOR_PATH"]=str(base/"economy.json");os.environ.pop("BOT_MESSAGE_DISPATCHER_ENABLED",None);self.addCleanup(self.restore);self.storage=JsonStorage(str(base/"players.json"))
 def restore(self):
  for k,v in self.old.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
 def activate(self):
  data={"name":"Ярмарка","type":"fair","start_date":"2026-01-01T00:00:00Z","end_date":"2027-01-01T00:00:00Z","exp_multiplier":2,"modifiers":[{"type":"buy_price","value":-20,"value_mode":"percent"},{"type":"craft_time","value":-50,"value_mode":"percent"},{"type":"craft_success_percent","value":10},{"type":"location_access","object_id":"small_plateau","value":-1},{"type":"player_effect","object_id":"festival"}],"special_loot":[{"item_id":"gift","source":"all_mobs","chance":100,"min_count":1,"max_count":1,"per_player_limit":1,"total_limit":2}],"start_message":"Началась ярмарка","end_message":"Ярмарка завершена"}
  env=events.store().create("fair",data);events.store().set_status("fair",events.STATUS_ACTIVE,force=True);return env
 def test_modifiers_access_effect_and_live_integrations(self):
  self.activate();mods=runtime.modifiers(context={"location_id":"small_plateau"},now=datetime(2026,7,1,tzinfo=timezone.utc));self.assertEqual(mods["exp_multiplier"],2);self.assertAlmostEqual(mods["buy_price_multiplier"],.8);self.assertEqual(mods["craft_success_percent"],10);self.assertFalse(runtime.access_allowed("location","small_plateau"))
  player={"game_id":"P"};self.assertEqual(runtime.apply_player_effects(player),["festival"]);self.assertEqual(runtime.apply_player_effects(player),[])
  from services.crafting_service import _recipe_craft_seconds
  self.assertEqual(_recipe_craft_seconds({"id":"r","workshop":"smeltery","craft_time_seconds":100}),50)
  from services.market_service import _discounted_buy_price
  self.assertEqual(_discounted_buy_price(player,100),80)
 def test_special_loot_limits_are_idempotent(self):
  self.activate();player={"game_id":"P"};self.assertEqual(runtime.roll_special_loot(player,"battle",location_id="x",object_id="wolf",rng=random.Random(1))[0]["item_id"],"gift");self.assertEqual(runtime.roll_special_loot(player,"battle",location_id="x",object_id="wolf",rng=random.Random(1)),[])
 def test_scheduled_repeat_and_notifications(self):
  data={"name":"Неделя","type":"seasonal","repeat_enabled":True,"repeat_type":"weekly","repeat_weekday":2,"repeat_start_hour":0,"repeat_duration_days":1,"start_message":"Старт","end_message":"Финиш"};env=events.store().create("weekly",data);events.store().set_status("weekly",events.STATUS_SCHEDULED,force=True)
  self.assertTrue(runtime.is_effectively_active(events.store().get("weekly"),datetime(2026,7,8,12,tzinfo=timezone.utc)));self.assertFalse(runtime.is_effectively_active(events.store().get("weekly"),datetime(2026,7,9,12,tzinfo=timezone.utc)))
 def test_start_and_end_notifications_use_outbox(self):
  self.activate();self.storage.save_new_player({"game_id":"P","name":"Игрок","level":1},"telegram","1");result=runtime.sync_and_notify(self.storage);self.assertIn("fair",result["started"]);self.assertIn("Началась",self.storage.dequeue_bot_messages("P")[0]["text"])
  events.store().set_status("fair",events.STATUS_FINISHED,force=True);result=runtime.sync_and_notify(self.storage);self.assertIn("fair",result["ended"]);self.assertIn("завершена",self.storage.dequeue_bot_messages("P")[0]["text"])
 def test_validation_accepts_full_modifiers(self):
  self.activate();result=events.validate(events.store().get("fair"));self.assertTrue(result["ok"],result["errors"])
 def test_daily_timezone_conditions_player_scope_endless_and_active_zone(self):
  data={"name":"Ночь","type":"weather","repeat_enabled":True,"repeat_type":"daily","repeat_start_hour":1,"repeat_duration_days":1,"timezone":"Europe/Moscow","scope_type":"players","player_ids":["P"],"start_by_condition":True,"start_condition":"weather=storm","end_by_condition":True,"end_condition":"cancelled=yes","modifiers":[{"type":"active_zone","object_id":"storm_port","enabled":True}]}
  events.store().create("night",data);events.store().set_status("night",events.STATUS_SCHEDULED,force=True);env=events.store().get("night")
  moment=datetime(2026,7,8,1,tzinfo=timezone.utc)
  self.assertTrue(runtime.is_effectively_active(env,moment))
  self.assertEqual([x["id"] for x in runtime.active_events(context={"game_id":"P","weather":"storm"},now=moment)],["night"])
  self.assertFalse(runtime.active_events(context={"game_id":"X","weather":"storm"},now=moment))
  self.assertFalse(runtime.active_events(context={"game_id":"P","weather":"storm","cancelled":"yes"},now=moment))
  self.assertTrue(runtime.zone_active("storm_port",context={"game_id":"P","weather":"storm"}))
  endless={"name":"Вечно","type":"system","start_date":"2020-01-01T00:00:00+00:00","end_date":"2021-01-01T00:00:00+00:00","endless":True}
  events.store().create("endless",endless);events.store().set_status("endless",events.STATUS_ACTIVE,force=True)
  self.assertTrue(runtime.is_effectively_active(events.store().get("endless"),moment))

if __name__=="__main__":unittest.main()
