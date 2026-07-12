import os,sys,tempfile,unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services import event_campaign_service as svc
from services import event_campaign_runtime as runtime
from admin_event_campaign_api import create_admin_event_campaign_router
from services.admin_panel_service import create_admin_panel_activation_token,consume_or_read_admin_session
from storage.json_storage import JsonStorage

class EventCampaignTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);base=Path(self.tmp.name)
  keys=("EVENT_CAMPAIGNS_PATH","WORLD_CONTENT_PATH","BROADCAST_CONSTRUCTOR_PATH","BROADCAST_RUNTIME_PATH","ADMIN_ROLES_PATH","ADMIN_AUDIT_LOG_PATH","TELEGRAM_ADMIN_USER_IDS");self.old={k:os.environ.get(k) for k in keys}
  os.environ["EVENT_CAMPAIGNS_PATH"]=str(base/"events.json");os.environ["WORLD_CONTENT_PATH"]=str(base/"world.json");os.environ["BROADCAST_CONSTRUCTOR_PATH"]=str(base/"broadcasts.json");os.environ["BROADCAST_RUNTIME_PATH"]=str(base/"broadcast_runtime.json");os.environ["ADMIN_ROLES_PATH"]=str(base/"roles.json");os.environ["ADMIN_AUDIT_LOG_PATH"]=str(base/"audit.log");os.environ["TELEGRAM_ADMIN_USER_IDS"]="999";self.addCleanup(self.restore)
  self.storage=JsonStorage(str(base/"players.json"))
 def restore(self):
  for k,v in self.old.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
 def data(self):return {"name":"Охота","player_name":"Большая охота","event_type":"pve","min_level":2,"registration_required":True,"stages":[{"stage_id":"hunt","name":"Охота"},{"stage_id":"report","name":"Итоги"}],"tasks":[{"task_id":"wolves","stage_id":"hunt","task_type":"kill_mob","target_id":"wolf","required_count":2,"points":5},{"task_id":"visit","stage_id":"report","task_type":"visit_location","target_id":"city","required_count":1}],"rewards":[{"type":"currency","object_id":"copper","amount":10,"scope":"final"}],"rating_enabled":True,"rating_type":"points"}
 def publish(self):svc.store().create("hunt",self.data());svc.store().set_status("hunt",svc.STATUS_PUBLISHED,force=True)
 def test_validation_runtime_stages_rewards_and_ranking(self):
  env=svc.store().create("draft",self.data());self.assertTrue(svc.validate(env)["ok"]);svc.store().delete("draft")
  self.publish();player={"game_id":"P1","name":"Игрок","level":2,"money":0};self.storage.save_new_player(player,"telegram","1")
  state=runtime.join(player,"hunt");self.assertEqual(state["stage_id"],"hunt")
  runtime.progress(player,"kill_mob","wolf");result=runtime.progress(player,"kill_mob","wolf")[0];self.assertEqual(result["status"],"stage")
  result=runtime.progress(player,"visit_location","city")[0];self.assertEqual(result["status"],"completed");self.assertEqual(player["money"],10);self.assertEqual(state["points"],6)
  self.storage.update_player(player);self.assertEqual(runtime.ranking(self.storage,"hunt")[0]["game_id"],"P1")
 def test_eligibility(self):
  self.publish();ok,error=runtime.eligible({"game_id":"P","level":1},"hunt");self.assertFalse(ok);self.assertIn("уровень",error.lower())
 def test_admin_api_crud_and_meta(self):
  app=FastAPI();app.include_router(create_admin_event_campaign_router(lambda:self.storage));client=TestClient(app)
  activation=create_admin_panel_activation_token(self.storage,platform="telegram",admin_user_id="999");token=consume_or_read_admin_session(self.storage,activation)["token"];headers={"Authorization":f"Bearer {token}"}
  meta=client.get("/api/admin/v2/event-campaigns/meta",headers=headers);self.assertEqual(meta.status_code,200);self.assertIn("pve",meta.json()["eventTypes"])
  created=client.post("/api/admin/v2/event-campaigns",headers=headers,json={"id":"hunt","data":self.data()});self.assertEqual(created.status_code,200,created.text)
  published=client.post("/api/admin/v2/event-campaigns/hunt/publish",headers=headers,json={"reason":"старт"});self.assertEqual(published.status_code,200,published.text)
  finalized=client.post("/api/admin/v2/event-campaigns/hunt/finalize-ranking",headers=headers,json={"reason":"итоги"});self.assertEqual(finalized.status_code,200,finalized.text)
 def test_shared_bot_city_action_lists_and_joins_event(self):
  self.publish();player={"game_id":"P2","name":"Бот","level":2};self.storage.save_new_player(player,"telegram","22")
  from services.city_service import process_world_action
  listed=process_world_action(self.storage,player,"Эвенты","telegram");self.assertIn("Большая охота",listed.text);self.assertIn(["Эвент: hunt"],listed.buttons)
  joined=process_world_action(self.storage,player,"Эвент: hunt","vk");self.assertIn("участвуете",joined.text.lower());self.assertIn("hunt",player["event_campaigns"])
 def test_item_registration_is_checked_and_consumed(self):
  data=self.data();data.update({"registration_via_button":False,"registration_via_item":True,"registration_item_id":"event_pass","consume_registration_item":True})
  svc.store().create("item_event",data);svc.store().set_status("item_event",svc.STATUS_PUBLISHED,force=True)
  player={"game_id":"P3","level":2,"inventory":[]}
  with self.assertRaisesRegex(ValueError,"предмет"):runtime.join(player,"item_event",method="item")
  player["inventory"]=[{"item_id":"event_pass","amount":1}]
  runtime.join(player,"item_event",method="item");self.assertEqual(player["inventory"],[])
 def test_ranking_rewards_are_finalized_once(self):
  data=self.data();data["rewards"]=[
   {"type":"currency","object_id":"copper","amount":100,"scope":"rating","place":1},
   {"type":"currency","object_id":"copper","amount":25,"scope":"rating","place_from":2,"place_to":3},
  ]
  svc.store().create("ranked",data);svc.store().set_status("ranked",svc.STATUS_PUBLISHED,force=True)
  for gid,points in (("A",20),("B",10)):
   player={"game_id":gid,"name":gid,"level":2,"money":0,"event_campaigns":{"ranked":{"event_id":"ranked","status":"completed","points":points,"claimed":[]}}}
   self.storage.save_new_player(player,"telegram",gid)
  result=runtime.finalize_ranking(self.storage,"ranked");self.assertEqual(result["issued"],["A","B"])
  self.assertEqual(self.storage.get_player_by_game_id("A")["money"],100);self.assertEqual(self.storage.get_player_by_game_id("B")["money"],25)
  again=runtime.finalize_ranking(self.storage,"ranked");self.assertEqual(again["issued"],[])
  self.assertEqual(self.storage.get_player_by_game_id("A")["money"],100)
 def test_temporary_location_is_visible_only_to_active_participant(self):
  from services import world_content_registry as world
  from services import world_runtime
  world.create_content("location","event_island",{"name":"Остров эвента","type":"event","description":"Временный остров"});world.set_status("location","event_island",world.STATUS_PUBLISHED,force=True)
  data=self.data();data["locations"]=["event_island"];svc.store().create("island_event",data);svc.store().set_status("island_event",svc.STATUS_PUBLISHED,force=True)
  player={"game_id":"P4","level":2,"inventory":[]}
  self.assertIsNone(world_runtime.render_location("event_island",player=player))
  state=runtime.join(player,"island_event");self.assertIsNotNone(world_runtime.render_location("event_island",player=player))
  state["status"]="completed";self.assertIsNone(world_runtime.render_location("event_island",player=player))
 def test_linked_participation_broadcast_is_delivered_once(self):
  from services import broadcast_constructor_service as broadcasts
  broadcasts.store().create("welcome",{"name":"Приветствие","broadcast_type":"event","audience_mode":"all","text":"Добро пожаловать в эвент"});broadcasts.store().set_status("welcome",broadcasts.STATUS_PUBLISHED,force=True)
  data=self.data();data["broadcast_ids"]=[{"broadcast_id":"welcome","scope":"participation"}];svc.store().create("with_mail",data);svc.store().set_status("with_mail",svc.STATUS_PUBLISHED,force=True)
  player={"game_id":"MAIL","name":"Почта","level":2};self.storage.save_new_player(player,"telegram","mail")
  runtime.join(player,"with_mail",storage=self.storage);stored=self.storage.get_player_by_game_id("MAIL")
  self.assertIn("welcome",stored.get("broadcast_delivery_claims") or [])
  runtime._linked_broadcasts(stored,data,"participation",self.storage);stored=self.storage.get_player_by_game_id("MAIL")
  self.assertEqual((stored.get("broadcast_delivery_claims") or []).count("welcome"),1)

if __name__=="__main__":unittest.main()
