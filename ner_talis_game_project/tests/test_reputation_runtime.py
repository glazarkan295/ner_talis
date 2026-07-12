import os
import sys
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import reputation_constructor_service as definitions
from services import reputation_runtime_service as runtime


class ReputationRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.old = os.environ.get("REPUTATION_CONSTRUCTOR_PATH");self.old_formula=os.environ.get("FORMULA_CONSTRUCTOR_PATH")
        os.environ["REPUTATION_CONSTRUCTOR_PATH"] = str(Path(self.tmp.name) / "reputation.json")
        os.environ["FORMULA_CONSTRUCTOR_PATH"] = str(Path(self.tmp.name) / "formulas.json")
        self.addCleanup(self.restore)

    def restore(self):
        if self.old is None: os.environ.pop("REPUTATION_CONSTRUCTOR_PATH", None)
        else: os.environ["REPUTATION_CONSTRUCTOR_PATH"] = self.old
        if self.old_formula is None:os.environ.pop("FORMULA_CONSTRUCTOR_PATH",None)
        else:os.environ["FORMULA_CONSTRUCTOR_PATH"]=self.old_formula

    def publish(self, object_id="city", **extra):
        data = {"name_ru": "Селдар", "visibility": "visible", "min_value": -100,
                "max_value": 100, "default_value": 0, "show_to_player": True,
                "show_exact_value": True, **extra}
        definitions.store().create(object_id, data)
        definitions.store().set_status(object_id, definitions.STATUS_PUBLISHED, force=True)

    def test_trigger_clamps_logs_and_changes_stage(self):
        self.publish(change_rules=[{"trigger": "mob_kill", "source_id": "wolf", "change_value": 30}],
                     stages=[{"stage_id": "neutral", "name_ru": "Нейтрально", "min_value": -100, "max_value": 29},
                             {"stage_id": "friend", "name_ru": "Дружба", "min_value": 30, "max_value": 100}])
        player = {}; rows = runtime.apply_trigger(player, "mob_kill", "wolf")
        self.assertEqual(rows[0]["new_value"], 30); self.assertTrue(rows[0]["stage_changed"])
        runtime.change(player, "city", 999, source="admin", admin="telegram:1")
        self.assertEqual(runtime.value(player, "city"), 100)
        self.assertEqual(player["reputation_history"][-1]["admin"], "telegram:1")

    def test_hidden_reputation_does_not_leak_but_affects_economy(self):
        self.publish("secret", visibility="hidden", show_to_player=False,
                     buy_discount_percent=5, trade_blocked=True)
        player = {"reputations": {"secret": 50}}
        self.assertEqual(runtime.player_view(player), [])
        modifiers = runtime.economic_modifiers(player)
        self.assertEqual(modifiers["buy_discount_percent"], 5); self.assertTrue(modifiers["trade_blocked"])
        from services import market_service
        self.assertEqual(market_service._discounted_buy_price(player, 100), 95)
        self.assertTrue(market_service._reputation_blocks_trade(player))

    def test_unpublished_definition_is_not_applied(self):
        definitions.store().create("draft", {"name_ru": "Черновик", "change_rules": [{"trigger": "mob_kill", "change_value": 5}]})
        player = {}; self.assertEqual(runtime.apply_trigger(player, "mob_kill", "wolf"), [])
        with self.assertRaises(ValueError): runtime.change(player, "draft", 1, source="admin")

    def test_hidden_bucket_daily_limit_and_stage_rewards_accesses(self):
        self.publish("secret",visibility="hidden",show_to_player=False,allow_negative=False,
                     change_rules=[{"rule_id":"help","trigger":"help_npc","source_id":"elder","change_value":30,"daily_limit":1}],
                     stages=[{"stage_id":"neutral","min_value":0,"max_value":29},{"stage_id":"trusted","min_value":30,"max_value":100,"rewards":[{"type":"item","object_id":"token","amount":2}],"accesses":[{"type":"location","object_id":"vault"}]}])
        player={};first=runtime.apply_trigger(player,"help_npc","elder");second=runtime.apply_trigger(player,"help_npc","elder")
        self.assertEqual(first[0]["new_value"],30);self.assertEqual(second,[]);self.assertNotIn("secret",player.get("reputations",{}));self.assertEqual(player["hidden_reputations"]["secret"],30)
        self.assertTrue(player["unlocks"]["location:vault"]);self.assertEqual(sum(x.get("amount",0) for x in player["inventory"] if x.get("item_id")=="token"),2)
        runtime.change(player,"secret",-999,source="admin");self.assertEqual(runtime.value(player,"secret"),0)

    def test_bad_reputation_markup_and_service_price(self):
        self.publish("trade",bad_reputation_markup_percent=25,service_price_percent=20,delivery_commission_percent=10)
        player={"reputations":{"trade":1}}
        from services.market_service import _discounted_buy_price
        from services.economy_runtime import service_price,commission_adjusted
        self.assertEqual(_discounted_buy_price(player,100),125)
        self.assertEqual(service_price("repair",100,player),120)
        self.assertEqual(commission_adjusted(100,"delivery",player),110)

    def test_decay_moves_value_toward_default_and_logs(self):
        self.publish("decay",default_value=10,decay_enabled=True,decay_direction="toward_default",decay_amount=5,decay_interval_seconds=60)
        now=datetime(2026,1,1,tzinfo=timezone.utc);player={"reputations":{"decay":30},"reputation_decay_state":{"decay":(now-timedelta(seconds=120)).isoformat()}}
        rows=runtime.apply_decay(player,now=now);self.assertEqual(runtime.value(player,"decay"),20);self.assertEqual(rows[0]["source"],"decay")

    def test_reputation_price_formula_is_live(self):
        from services import formula_constructor_service as formulas
        formulas.store().create("rep_price",{"name":"Цена","expression":"base_amount * 0.5"});formulas.store().set_status("rep_price",formulas.STATUS_PUBLISHED,force=True)
        self.publish("formula_rep",price_formula_id="rep_price");self.assertEqual(runtime.price_by_reputation({"reputations":{"formula_rep":1}},200),100)


if __name__ == "__main__": unittest.main()
