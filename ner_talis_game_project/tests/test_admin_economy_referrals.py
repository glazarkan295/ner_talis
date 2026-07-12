import os, sys, tempfile, unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from admin_economy_api import create_admin_economy_router
from admin_referral_api import create_admin_referral_router
from services import economy_constructor_service as economy
from services import referral_constructor_service as referrals
from services import market_service
from services import economy_runtime
from services.admin_panel_service import create_admin_panel_activation_token, consume_or_read_admin_session
from storage.json_storage import JsonStorage

class EconomyReferralApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); base = Path(self.tmp.name)
        keys = ("ECONOMY_CONSTRUCTOR_PATH", "ECONOMY_TRANSACTION_LOG_PATH", "REFERRAL_CONSTRUCTOR_PATH", "ADMIN_ROLES_PATH", "ADMIN_AUDIT_LOG_PATH", "TELEGRAM_ADMIN_USER_IDS")
        self.saved = {k: os.environ.get(k) for k in keys}; self.addCleanup(self.restore)
        os.environ.update({"ECONOMY_CONSTRUCTOR_PATH": str(base/"economy.json"), "REFERRAL_CONSTRUCTOR_PATH": str(base/"referrals.json"),
                           "ECONOMY_TRANSACTION_LOG_PATH": str(base/"transactions.jsonl"), "ADMIN_ROLES_PATH": str(base/"roles.json"), "ADMIN_AUDIT_LOG_PATH": str(base/"audit.log"), "TELEGRAM_ADMIN_USER_IDS": "999"})
        self.storage = JsonStorage(str(base/"players.json")); app = FastAPI()
        app.include_router(create_admin_economy_router(lambda: self.storage)); app.include_router(create_admin_referral_router(lambda: self.storage))
        self.client = TestClient(app)
    def restore(self):
        for k,v in self.saved.items(): os.environ.pop(k, None) if v is None else os.environ.__setitem__(k,v)
    def auth(self):
        activation = create_admin_panel_activation_token(self.storage, platform="telegram", admin_user_id="999")
        token = consume_or_read_admin_session(self.storage, activation)["token"]
        return {"Authorization": f"Bearer {token}"}
    def test_economy_publish_is_runtime_profile(self):
        h=self.auth(); data={"name":"Основная экономика","enabled":True,"priority":10,"currencies":[{"code":"copper","name":"Медь","copper_rate":1}],"global_buy_multiplier":1,"global_sell_multiplier":.5,"market_commission_percent":5}
        self.assertEqual(self.client.post("/api/admin/v2/economy",headers=h,json={"id":"main","data":data}).status_code,200)
        p=self.client.post("/api/admin/v2/economy/main/publish",headers=h,json={"reason":"live"}); self.assertEqual(p.status_code,200,p.text)
        self.assertEqual(economy.active_profile()["name"],"Основная экономика")
        self.assertEqual(market_service.item_sell_price({"id":"test","sell_price_copper":100}), 50)
    def test_referral_publish_is_runtime_rule(self):
        h=self.auth(); data={"name":"За регистрацию","enabled":True,"platform":"telegram","trigger":"registration_complete","referrer_rewards":[{"type":"currency","object_id":"copper","amount":100}],"referred_rewards":[{"type":"exp","amount":10}],"prevent_self_referral":True}
        self.assertEqual(self.client.post("/api/admin/v2/referrals",headers=h,json={"id":"welcome","data":data}).status_code,200)
        p=self.client.post("/api/admin/v2/referrals/welcome/publish",headers=h,json={}); self.assertEqual(p.status_code,200,p.text)
        self.assertEqual(referrals.active_rules("telegram")[0]["id"],"welcome")
        stats=self.client.get("/api/admin/v2/referrals/operations/statistics",headers=h)
        self.assertEqual(stats.status_code,200,stats.text);self.assertEqual(stats.json()["total"],0)
    def test_wallet_exchange_dynamic_rules_and_operation_log(self):
        h=self.auth(); data={"name":"Расширенная экономика","enabled":True,"currencies":[{"code":"copper","name":"Медь","copper_rate":1,"min_value":0},{"code":"silver","name":"Серебро","copper_rate":100,"min_value":0}],"exchange_rates":[{"rate_id":"c2s","source_currency":"copper","target_currency":"silver","rate":.01,"commission_percent":10,"active":True}],"dynamic_rules":[{"context_key":"market_type","value":"black","multiplier":1.5,"active":True}]}
        self.assertEqual(self.client.post("/api/admin/v2/economy",headers=h,json={"id":"extended","data":data}).status_code,200)
        self.assertEqual(self.client.post("/api/admin/v2/economy/extended/publish",headers=h,json={}).status_code,200)
        player={"game_id":"p1","money_copper":1000,"currencies":{"silver":0}}
        result=economy_runtime.exchange(player,"copper","silver",1000,rate_id="c2s")
        self.assertEqual(result["received"],9); self.assertEqual(player["money_copper"],0); self.assertEqual(player["currencies"]["silver"],9)
        self.assertEqual(economy_runtime.dynamic_multiplier({"market_type":"black"}),1.5)
        with self.assertRaises(ValueError): economy_runtime.change(player,"copper",-1,operation="purchase")
        logs=self.client.get("/api/admin/v2/economy/operations/logs?game_id=p1",headers=h)
        self.assertEqual(logs.status_code,200,logs.text); self.assertEqual(len(logs.json()["items"]),3)
        self.assertEqual(logs.json()["items"][0]["status"],"error")
    def test_published_assortments_replace_all_three_legacy_markets(self):
        h=self.auth(); data={"name":"Авторские рынки","enabled":True,"currencies":[{"code":"copper","copper_rate":1}],"markets":[
            {"market_id":"regular","market_type":"ordinary","active":True,"items":[{"item_id":"bread","name":"Хлеб админа","buy_price":17,"stock":9}]},
            {"market_id":"harbor","market_type":"port","active":True,"items":[{"item_id":"rope","name":"Канат","buy_price":33}]},
            {"market_id":"shadow","market_type":"black","active":True,"items":"[{\"item_id\":\"lockpick\",\"name\":\"Отмычка\",\"buy_price\":71}]"}]}
        self.assertEqual(self.client.post("/api/admin/v2/economy",headers=h,json={"id":"markets","data":data}).status_code,200)
        self.assertEqual(self.client.post("/api/admin/v2/economy/markets/publish",headers=h,json={}).status_code,200)
        expected=((market_service.MARKET_KIND_NPC,"bread",17),(market_service.MARKET_KIND_PORT,"rope",33),(market_service.MARKET_KIND_BLACK,"lockpick",71))
        for kind,item_id,price in expected:
            rows=market_service.load_market_items(kind); self.assertEqual([(x.item_id,x.buy_price_copper) for x in rows],[(item_id,price)])
            self.assertTrue(rows[0].authored_market_id)
    def test_market_charges_and_source_reward_rule(self):
        h=self.auth(); data={"name":"Заряды и награды","enabled":True,"reward_multiplier":2,"currencies":[{"code":"copper","copper_rate":1}],"rewards":[{"reward_id":"quest","source_type":"quest","fixed":5,"multiplier":1.5,"enabled":True}],"services":[{"service_id":"rest","service_type":"camp_rest","price":200,"enabled":True}],"commissions":[{"commission_id":"rest_tax","applies_to":"camp_rest","percent":10,"enabled":True}],"economic_effects":[{"effect_id":"lucky","applies_to":"camp_rest","influence_type":"discount","percent":25}],"markets":[{"market_id":"limited","market_type":"ordinary","active":True,"use_charges":True,"max_charges":2,"current_charges":2,"buy_charge_cost":1,"no_charges_text":"Рынок отдыхает","items":[]}]}
        self.assertEqual(self.client.post("/api/admin/v2/economy",headers=h,json={"id":"rules","data":data}).status_code,200)
        self.assertEqual(self.client.post("/api/admin/v2/economy/rules/publish",headers=h,json={}).status_code,200)
        player={}; self.assertEqual(market_service._charge_error(player,market_service.MARKET_KIND_NPC,"buy"),"")
        market_service._consume_charge(player,market_service.MARKET_KIND_NPC,"buy"); market_service._consume_charge(player,market_service.MARKET_KIND_NPC,"buy")
        self.assertEqual(market_service._charge_error(player,market_service.MARKET_KIND_NPC,"buy"),"Рынок отдыхает")
        self.assertEqual(economy_runtime.reward_amount("quest",10),45)
        self.assertEqual(economy_runtime.service_price("camp_rest",999,{"active_effects":[{"effect_id":"lucky"}]}),165)
        self.assertEqual(economy_runtime.service_price("camp_rest",999,{}),220)
    def test_published_nested_economy_object_cannot_be_silently_removed(self):
        h=self.auth(); data={"name":"Защищённый профиль","enabled":True,"currencies":[{"code":"copper","copper_rate":1},{"code":"silver","copper_rate":100}],"markets":[{"market_id":"main","market_type":"ordinary","active":True,"items":[]}]}
        self.assertEqual(self.client.post("/api/admin/v2/economy",headers=h,json={"id":"protected","data":data}).status_code,200)
        self.assertEqual(self.client.post("/api/admin/v2/economy/protected/publish",headers=h,json={}).status_code,200)
        removed={**data,"currencies":[data["currencies"][0]],"markets":[]}
        response=self.client.put("/api/admin/v2/economy/protected",headers=h,json={"data":removed})
        self.assertEqual(response.status_code,409,response.text); self.assertIn("silver",response.text)
        disabled={**data,"markets":[{**data["markets"][0],"active":False}]}
        self.assertEqual(self.client.put("/api/admin/v2/economy/protected",headers=h,json={"data":disabled}).status_code,200)
    def test_period_money_mass_cap_clamps_then_rejects_emission(self):
        h=self.auth();data={"name":"Лимит эмиссии","enabled":True,"currencies":[{"code":"copper","copper_rate":1}],"money_caps":[{"scope":"player","currency":"copper","amount":100,"period":"day","enabled":True}]}
        self.assertEqual(self.client.post("/api/admin/v2/economy",headers=h,json={"id":"caps","data":data}).status_code,200)
        self.assertEqual(self.client.post("/api/admin/v2/economy/caps/publish",headers=h,json={}).status_code,200)
        player={"game_id":"cap-player","money":0};self.assertEqual(economy_runtime.change(player,"copper",70,operation="reward")["amount"],70)
        self.assertEqual(economy_runtime.change(player,"copper",70,operation="reward")["amount"],30);self.assertEqual(player["money"],100)
        with self.assertRaisesRegex(ValueError,"лимит"):economy_runtime.change(player,"copper",1,operation="reward")
    def test_validation_rejects_invalid_values(self):
        bad_e=economy.store().create("bad",{"name":"x","currencies":[{"code":"copper","copper_rate":0}],"market_commission_percent":120})
        self.assertFalse(economy.validate(bad_e)["ok"])
        bad_r=referrals.store().create("bad",{"name":"x","platform":"mail","trigger":"level_reached","trigger_value":0,"referrer_rewards":[{"type":"???","amount":0}]})
        self.assertFalse(referrals.validate(bad_r)["ok"])

if __name__ == "__main__": unittest.main()
