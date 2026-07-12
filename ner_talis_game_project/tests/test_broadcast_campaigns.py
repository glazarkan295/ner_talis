import os,sys,tempfile,unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services import broadcast_constructor_service as svc
from services import broadcast_campaign_runtime as runtime
from admin_broadcast_campaign_api import create_admin_broadcast_campaign_router
from services.admin_panel_service import create_admin_panel_activation_token,consume_or_read_admin_session
from storage.json_storage import JsonStorage
from services.admin_audit import read_admin_audit_records

class BroadcastCampaignTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);base=Path(self.tmp.name)
  keys=("BROADCAST_CONSTRUCTOR_PATH","BROADCAST_RUNTIME_PATH","ADMIN_ROLES_PATH","ADMIN_AUDIT_LOG_PATH","TELEGRAM_ADMIN_USER_IDS","BOT_MESSAGE_DISPATCHER_ENABLED");self.old={k:os.environ.get(k) for k in keys}
  os.environ["BROADCAST_CONSTRUCTOR_PATH"]=str(base/"broadcasts.json");os.environ["BROADCAST_RUNTIME_PATH"]=str(base/"runs.json");os.environ["ADMIN_ROLES_PATH"]=str(base/"roles.json");os.environ["ADMIN_AUDIT_LOG_PATH"]=str(base/"audit.log");os.environ["TELEGRAM_ADMIN_USER_IDS"]="999";os.environ.pop("BOT_MESSAGE_DISPATCHER_ENABLED",None);self.addCleanup(self.restore)
  self.storage=JsonStorage(str(base/"players.json"))
  for i in (1,2):self.storage.save_new_player({"game_id":f"P{i}","name":f"Игрок {i}","level":i,"money":0,"main_platform":"telegram","linked_accounts":{"telegram":str(i)}},"telegram",str(i))
 def restore(self):
  for k,v in self.old.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
 def data(self):return {"name":"Компенсация","system_name":"comp","broadcast_type":"compensation","audience_mode":"all","title":"Подарок","text":"Спасибо за ожидание","send_mode":"reward_message","format":"plain","rewards":[{"type":"currency","object_id":"copper","amount":25}],"buttons":[{"button_id":"profile","text":"Профиль","action":"open_profile","target":""}],"send_in_batches":True,"batch_size":1,"batch_delay_seconds":0,"double_confirmation_required":True}
 def publish(self):svc.store().create("comp",self.data());svc.store().set_status("comp",svc.STATUS_PUBLISHED,force=True)
 def test_validation_batch_rewards_logs_and_idempotency(self):
  self.publish();self.assertTrue(svc.validate(svc.store().get("comp"))["ok"]);self.assertEqual(runtime.preview_recipients(self.storage,"comp")["recipients"],2)
  with self.assertRaises(ValueError):runtime.start(self.storage,"comp",confirm=True,confirm_rewards=False)
  run=runtime.start(self.storage,"comp",confirm=True,confirm_rewards=True);self.assertEqual(run["cursor"],1);self.assertEqual(run["status"],"running")
  run=runtime.run_batch(self.storage,"comp");self.assertEqual(run["status"],"sent");self.assertEqual(run["sent"],2);self.assertEqual(len(run["logs"]),2)
  self.assertEqual(self.storage.get_player_by_game_id("P1")["money"],25);self.assertEqual(self.storage.get_player_by_game_id("P2")["money"],25)
  self.assertTrue(self.storage.dequeue_bot_messages("P1"));self.assertEqual(runtime.run_batch(self.storage,"comp")["sent"],2)
 def test_required_test_send_is_separate_from_main_and_preserves_history(self):
  data=self.data();data.update({"test_before_main":True,"test_player_ids":["P1"],"send_in_batches":False})
  svc.store().create("comp",data);svc.store().set_status("comp",svc.STATUS_PUBLISHED,force=True)
  with self.assertRaisesRegex(ValueError,"тестовую"):
   runtime.start(self.storage,"comp",confirm=True,confirm_rewards=True)
  tested=runtime.start(self.storage,"comp",confirm=True,confirm_rewards=True,test_only=True)
  self.assertEqual(tested["status"],"sent");self.assertEqual(tested["recipients"],["P1"])
  main=runtime.start(self.storage,"comp",confirm=True,confirm_rewards=True)
  self.assertEqual(main["status"],"sent");self.assertEqual(main["sent"],2)
  self.assertEqual(self.storage.get_player_by_game_id("P1")["money"],50)
  again=runtime.start(self.storage,"comp",confirm=True,confirm_rewards=True)
  self.assertEqual(len(again["history"]),1)
 def test_item_delivery_binding_gift_text_and_button_condition(self):
  data=self.data();data["rewards"]=[{"type":"item","object_id":"broadcast_gem","amount":2,"bind_on_receive":True,"delivery_mode":"delivery","receive_text":"Самоцвет"}]
  data["buttons"]=[{"button_id":"only_high","text":"Для второго","action":"open_profile","condition":{"audience_mode":"level","min_level":2}}];data["send_in_batches"]=False
  svc.store().create("comp",data);svc.store().set_status("comp",svc.STATUS_PUBLISHED,force=True)
  runtime.start(self.storage,"comp",confirm=True,confirm_rewards=True)
  p1=self.storage.get_player_by_game_id("P1");gift=p1["broadcast_delivery_inbox"][0]
  self.assertTrue(gift["item"]["bound_on_receive"]);self.assertEqual(gift["amount"],2)
  m1=self.storage.dequeue_bot_messages("P1")[0];m2=self.storage.dequeue_bot_messages("P2")[0]
  self.assertIn("Вы получили в дар от высших сил",m1["text"]);self.assertNotIn("Для второго",m1["text"]);self.assertIn("Для второго",m2["text"])
 def test_admin_crud_publish_start_and_stop(self):
  app=FastAPI();app.include_router(create_admin_broadcast_campaign_router(lambda:self.storage));client=TestClient(app)
  activation=create_admin_panel_activation_token(self.storage,platform="telegram",admin_user_id="999");token=consume_or_read_admin_session(self.storage,activation)["token"];headers={"Authorization":f"Bearer {token}"}
  self.assertIn("compensation",client.get("/api/admin/v2/broadcast-campaigns/meta",headers=headers).json()["broadcastTypes"])
  self.assertEqual(client.post("/api/admin/v2/broadcast-campaigns",headers=headers,json={"id":"comp","data":self.data()}).status_code,200)
  self.assertEqual(client.post("/api/admin/v2/broadcast-campaigns/comp/publish",headers=headers,json={"reason":"готово"}).status_code,200)
  preview=client.post("/api/admin/v2/broadcast-campaigns/comp/recipient-preview",headers=headers,json={});self.assertEqual(preview.json()["recipients"],2)
  started=client.post("/api/admin/v2/broadcast-campaigns/comp/start",headers=headers,json={"confirm":True,"confirm_rewards":True});self.assertEqual(started.status_code,200,started.text)
  stopped=client.post("/api/admin/v2/broadcast-campaigns/comp/stop",headers=headers,json={});self.assertEqual(stopped.json()["run"]["status"],"stopped")
  actions={row["action"] for row in read_admin_audit_records()};self.assertIn("broadcast_campaign.start",actions);self.assertIn("broadcast_campaign.stop",actions)

if __name__=="__main__":unittest.main()
