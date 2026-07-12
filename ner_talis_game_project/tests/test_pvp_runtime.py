import os, random, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from services import pvp_constructor_service as rules
from services import pvp_runtime_service as runtime
from services import combat_constructor_service as combat

class Storage:
    def __init__(self,*players): self.p={x["game_id"]:x for x in players}
    def get_player_by_game_id(self,gid): return self.p.get(gid)
    def update_player(self,p): self.p[p["game_id"]]=p

class PvpRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); base=Path(self.tmp.name)
        self.saved={k:os.environ.get(k) for k in ("PVP_CONSTRUCTOR_PATH","PVP_SESSIONS_PATH","COMBAT_CONSTRUCTOR_PATH")}
        os.environ["PVP_CONSTRUCTOR_PATH"]=str(base/"rules.json"); os.environ["PVP_SESSIONS_PATH"]=str(base/"sessions.json"); os.environ["COMBAT_CONSTRUCTOR_PATH"]=str(base/"combat.json")
        self.addCleanup(self.restore)
        rules.store().create("duel",{"name":"Дуэль","pvp_type":"duel","enabled":True,"min_level":1,"require_consent":True,"base_damage":100,"postdeath_curse_enabled":True,"postdeath_curse_chance":100,"postdeath_curses":["pvp_curse"]})
        rules.store().set_status("duel",rules.STATUS_PUBLISHED,force=True)
        self.a={"game_id":"A","level":5,"hp":50}; self.b={"game_id":"B","level":5,"hp":50}
    def restore(self):
        for k,v in self.saved.items(): os.environ.pop(k,None) if v is None else os.environ.__setitem__(k,v)
    def test_challenge_accept_attack_death_curse_and_idempotent_apply(self):
        s=runtime.create_challenge(self.a,self.b); self.assertEqual(s["state"],"pending")
        s=runtime.respond(s["id"],"B",True); self.assertEqual(s["turn"],"A")
        s=runtime.act(s["id"],"A","attack",rng=random.Random(1)); self.assertEqual(s["state"],"finished")
        self.assertEqual(s["winner"],"A"); self.assertEqual(s["postdeath_curse"]["source"],"pvp_player_death")
        storage=Storage(self.a,self.b); runtime.apply_result_to_players(storage,s["id"]); runtime.apply_result_to_players(storage,s["id"])
        self.assertEqual(storage.p["A"]["pvp_wins"],1); self.assertEqual(storage.p["B"]["pvp_deaths"],1)
        self.assertEqual(storage.p["B"]["active_effects"][0]["effect_id"],"pvp_curse")
    def test_only_opponent_can_accept_and_turn_is_enforced(self):
        s=runtime.create_challenge(self.a,self.b)
        with self.assertRaises(PermissionError): runtime.respond(s["id"],"A",True)
        runtime.respond(s["id"],"B",True)
        with self.assertRaises(PermissionError): runtime.act(s["id"],"B","attack")
    def test_decline_and_location_filter(self):
        s=runtime.create_challenge(self.a,self.b); self.assertEqual(runtime.respond(s["id"],"B",False)["state"],"declined")
    def test_group_pvp_has_player_and_npc_allies_on_both_sides(self):
        participants=[
            {"participant_id":"a","participant_type":"player","side":"pvp_initiator"},
            {"participant_id":"npc_a","participant_type":"npc_ally","side":"pvp_initiator","source_id":"guard_a","name":"Страж A","hp":30,"damage":60,"can_attack":True},
            {"participant_id":"b","participant_type":"player_enemy","side":"pvp_defender"},
            {"participant_id":"npc_b","participant_type":"enemy_npc_ally","side":"pvp_defender","source_id":"guard_b","name":"Страж B","hp":30,"damage":5,"can_attack":True},
        ]
        combat.store().create("pvp_party",{"name":"Групповой PVP","scope":"pvp","scope_id":"duel","max_players":3,"participants":participants})
        combat.store().set_status("pvp_party",combat.STATUS_PUBLISHED,force=True)
        ally_a={"game_id":"A2","name":"Друг A","hp":40,"pvp_damage":20}
        ally_b={"game_id":"B2","name":"Друг B","hp":40,"pvp_damage":10}
        opponent={**self.b,"hp":200}
        session=runtime.create_challenge(self.a,opponent,challenger_allies=[ally_a],opponent_allies=[ally_b])
        self.assertEqual({row["type"] for row in session["allies"]["A"]},{"npc_ally","player_ally"})
        self.assertEqual({row["type"] for row in session["allies"]["B"]},{"enemy_npc_ally","player_ally"})
        runtime.respond(session["id"],"B",True)
        acted=runtime.act(session["id"],"A","attack",rng=random.Random(1))
        self.assertLess(acted["participants"]["B"]["hp"],100)
        self.assertIn("Союзник",acted["log"][-1]["text"])

    def update_rule(self, **values):
        data=dict(rules.store().get("duel")["data"]);data.update(values);rules.store().update("duel",data);rules.store().set_status("duel",rules.STATUS_PUBLISHED,force=True)

    def test_configurable_flee_surrender_and_afk(self):
        self.update_rule(flee_allowed=True,flee_chance=0,surrender_allowed=False,max_skips=1,afk_technical_defeat=True,texts=[{"key":"flee_fail","text":"{player}: путь закрыт"},{"key":"afk","text":"AFK {player}"}])
        s=runtime.create_challenge(self.a,self.b);runtime.respond(s["id"],"B",True)
        s=runtime.act(s["id"],"A","flee",rng=random.Random(1));self.assertEqual(s["state"],"active");self.assertIn("путь закрыт",s["log"][-1]["text"])
        with self.assertRaises(ValueError):runtime.act(s["id"],"B","surrender")
        s=runtime.handle_timeout(s["id"]);self.assertEqual(s["state"],"finished");self.assertEqual(s["finish_reason"],"afk")

    def test_rewards_losses_crime_proof_and_message_layout(self):
        self.a.update({"money":10,"inventory":[]});self.b.update({"money":50,"inventory":[{"item_id":"proof","quantity":2}]})
        self.update_rule(base_damage=100,victory_rewards=[{"type":"coins","amount":20},{"type":"pvp_points","amount":3}],defeat_consequences=[{"type":"coins","amount":7},{"type":"item","object_id":"proof","amount":1}],criminal=True,criminal_reputation_id="crime",criminal_reputation_amount=5,city_reputation_id="city",city_reputation_amount=-2,city_ban_id="capital",ban_start_locations=True,create_proof_bag=True,proof_item_id="proof",message_layout="Раунд {round}: {player}={hp}; {opponent}={enemy_hp}")
        s=runtime.create_challenge(self.a,self.b);runtime.respond(s["id"],"B",True)
        self.assertIn("Раунд 1",runtime.render_session(runtime.get_session(s["id"]),"A"))
        runtime.act(s["id"],"A","attack",rng=random.Random(1));storage=Storage(self.a,self.b);runtime.apply_result_to_players(storage,s["id"])
        self.assertEqual(storage.p["A"]["money"],30);self.assertEqual(storage.p["A"]["pvp_points"],3)
        self.assertEqual(storage.p["B"]["money"],43);self.assertEqual(storage.p["B"]["inventory"][0]["quantity"],1)
        self.assertEqual(storage.p["A"]["reputations"],{"crime":5,"city":-2});self.assertTrue(storage.p["A"]["city_bans"]["capital"]);self.assertTrue(storage.p["A"]["start_locations_banned"])
        self.assertTrue(any(row.get("item_id")=="proof" for row in storage.p["A"].get("inventory") or []))

    def test_postdeath_curse_can_require_achievement(self):
        self.update_rule(curse_requires_achievement=True,curse_achievement_id="curse_master")
        s=runtime.create_challenge(self.a,self.b);runtime.respond(s["id"],"B",True);s=runtime.act(s["id"],"A","attack",rng=random.Random(1));self.assertIsNone(s["postdeath_curse"])
        self.b["achievements"]={"curse_master":{}}
        s=runtime.create_challenge(self.a,self.b);runtime.respond(s["id"],"B",True);s=runtime.act(s["id"],"A","attack",rng=random.Random(1));self.assertEqual(s["postdeath_curse"]["source"],"pvp_player_death")

    def test_order_is_authored_and_whole_enemy_side_must_fall(self):
        self.a["initiative"]=1;self.b["initiative"]=20;self.update_rule(action_order="by_initiative",base_damage=100,allow_player_allies=True,max_player_allies=2)
        ally={"game_id":"B2","name":"Щит","hp":30,"pvp_damage":1}
        s=runtime.create_challenge(self.a,self.b,opponent_allies=[ally]);s=runtime.respond(s["id"],"B",True);self.assertEqual(s["turn"],"B")
        s=runtime.act(s["id"],"B","defend");s=runtime.act(s["id"],"A","attack",rng=random.Random(1));self.assertEqual(s["state"],"active")
        runtime.act(s["id"],"B","defend");s=runtime.act(s["id"],"A","attack",rng=random.Random(1));self.assertEqual(s["participants"]["B"]["hp"],0);self.assertEqual(s["state"],"active")
        runtime.act(s["id"],"B","defend");s=runtime.act(s["id"],"A","attack",rng=random.Random(1));self.assertEqual(s["state"],"finished")

    def test_shared_telegram_vk_world_flow(self):
        from services.city_service import process_world_action
        storage=Storage(self.a,self.b)
        sent=process_world_action(storage,self.a,"PVP вызов B","telegram");self.assertIn("Вызов отправлен",sent.text)
        session_id=storage.p["B"]["pvp_invites"][0]
        accepted=process_world_action(storage,self.b,f"PVP принять {session_id}","vk");self.assertIn("PVP",accepted.text)
        acted=process_world_action(storage,self.a,f"PVP {session_id} атака","telegram");self.assertIn("побеждает",acted.text)

    def test_rule_authored_npc_allies_are_on_both_sides(self):
        self.update_rule(npc_allies=[{"side":"challenger","npc_id":"guard_a","level":2,"behavior":"protect"},{"side":"opponent","npc_id":"guard_b","level":3,"behavior":"attack"}])
        s=runtime.create_challenge(self.a,self.b)
        self.assertEqual(s["allies"]["A"][0]["source_id"],"guard_a");self.assertEqual(s["allies"]["B"][0]["source_id"],"guard_b")

if __name__=="__main__": unittest.main()
