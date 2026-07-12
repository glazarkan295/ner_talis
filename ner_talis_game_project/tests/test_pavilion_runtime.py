import os,sys,tempfile,unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from storage.json_storage import JsonStorage
from services import economy_constructor_service as economy
from services import pavilion_runtime as pavilion
from pavilion_api import create_pavilion_router

class PavilionRuntimeTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);base=Path(self.tmp.name)
  self.saved={k:os.environ.get(k) for k in ("ECONOMY_CONSTRUCTOR_PATH","ECONOMY_TRANSACTION_LOG_PATH")};self.addCleanup(self.restore)
  os.environ["ECONOMY_CONSTRUCTOR_PATH"]=str(base/"economy.json");os.environ["ECONOMY_TRANSACTION_LOG_PATH"]=str(base/"transactions.jsonl")
  self.storage=JsonStorage(str(base/"players.json"));data=self.storage.empty_schema();data["players"]={
   "seller":{"game_id":"seller","id":"seller","name":"Продавец","money_copper":100,"money":100,"inventory":[{"item_id":"apple","name":"Яблоко","category":"food","amount":3}]},
   "buyer":{"game_id":"buyer","id":"buyer","name":"Покупатель","money_copper":1000,"money":1000,"inventory":[]}}
  self.storage.save(data)
  profile=economy.store().create("main",{"name":"Павильон","enabled":True,"currencies":[{"code":"copper","copper_rate":1}],"pavilion":[{"enabled":True,"player_available":True,"rent_seconds":3600,"rent_cost":50,"commission_percent":10,"item_limit":2,"price_limit":500,"allowed_categories":["food"],"rent_text":"Арендовано","purchase_text":"Куплено"}]})
  economy.store().set_status("main",economy.STATUS_PUBLISHED,force=True)
 def restore(self):
  for k,v in self.saved.items():os.environ.pop(k,None) if v is None else os.environ.__setitem__(k,v)
 def test_rent_list_buy_commission_and_history(self):
  seller=self.storage.get_player_by_game_id("seller");rent=pavilion.rent(self.storage,seller);self.assertEqual(rent["cost"],50)
  listing=pavilion.create_listing(self.storage,seller,"apple",2,200);self.assertEqual(self.storage.get_player_by_game_id("seller")["inventory"][0]["amount"],1)
  with self.assertRaises(ValueError):pavilion.buy(self.storage,seller,listing["listing_id"])
  buyer=self.storage.get_player_by_game_id("buyer");result=pavilion.buy(self.storage,buyer,listing["listing_id"]);self.assertEqual(result["commission"],20)
  seller=self.storage.get_player_by_game_id("seller");buyer=self.storage.get_player_by_game_id("buyer")
  self.assertEqual(seller["money_copper"],230);self.assertEqual(buyer["money_copper"],800);self.assertEqual(sum(x["amount"] for x in buyer["inventory"]),2)
  self.assertEqual(seller["pavilion"]["sales_history"][0]["status"],"sold");self.assertEqual(pavilion.listings(self.storage),[])
 def test_cancel_returns_escrow_and_limits_are_enforced(self):
  seller=self.storage.get_player_by_game_id("seller");pavilion.rent(self.storage,seller);listing=pavilion.create_listing(self.storage,seller,"apple",3,500)
  with self.assertRaises(ValueError):pavilion.create_listing(self.storage,seller,"apple",1,501)
  pavilion.cancel(self.storage,seller,listing["listing_id"]);self.assertEqual(sum(x["amount"] for x in self.storage.get_player_by_game_id("seller")["inventory"]),3)
 def test_authenticated_api_rejects_wrong_scope_and_exposes_listing(self):
  seller=self.storage.get_player_by_game_id("seller");token=self.storage.create_site_session("seller","pavilion","telegram")
  wrong=self.storage.create_site_session("seller","profile","telegram");app=FastAPI();app.include_router(create_pavilion_router(lambda:self.storage));client=TestClient(app)
  self.assertEqual(client.get("/api/pavilion",headers={"Authorization":f"Bearer {wrong}"}).status_code,401)
  rent=client.post(f"/api/pavilion/rent?token={token}");self.assertEqual(rent.status_code,200);active=rent.json()["sessionToken"]
  response=client.post("/api/pavilion/listings",headers={"Authorization":f"Bearer {active}"},json={"item_id":"apple","quantity":1,"price":100});self.assertEqual(response.status_code,200,response.text)
  self.assertEqual(len(client.get("/api/pavilion",headers={"Authorization":f"Bearer {active}"}).json()["items"]),1)

if __name__=="__main__":unittest.main()
