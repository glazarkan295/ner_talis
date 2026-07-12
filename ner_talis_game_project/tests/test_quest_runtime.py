import os,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services import quest_constructor_service as quests
from services import quest_runtime_service as runtime
from services import achievement_service as achievements
from services import achievement_engine

class QuestRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.saved={k:os.environ.get(k) for k in ("QUEST_CONSTRUCTOR_PATH","ACHIEVEMENTS_PATH","WORLD_CONTENT_PATH")};os.environ["QUEST_CONSTRUCTOR_PATH"]=str(Path(self.tmp.name)/"quests.json");os.environ["ACHIEVEMENTS_PATH"]=str(Path(self.tmp.name)/"achievements.json");os.environ["WORLD_CONTENT_PATH"]=str(Path(self.tmp.name)/"world.json");self.addCleanup(self.restore)
        quests.store().create("wolf_hunt",{"name":"Охота","quest_type":"pve","min_level":1,"completion_conditions":["all_tasks_done"],"stages":[{"stage_id":"hunt","name":"Охота","next_stage":"report"},{"stage_id":"report","name":"Доклад"}],"tasks":[{"task_id":"wolves","stage_id":"hunt","task_type":"kill_mob","target_id":"wolf","required_count":2},{"task_id":"talk","stage_id":"report","task_type":"talk_npc","target_id":"guard","required_count":1}],"rewards":[{"type":"currency","object_id":"copper","count":50},{"type":"exp","count":10}],"repeat_mode":"one_time","accept_text":"Начинайте охоту","complete_text":"Готово"})
        quests.store().set_status("wolf_hunt",quests.STATUS_PUBLISHED,force=True);self.player={"game_id":"P","level":2,"money":0,"experience":0,"total_experience":0}
    def restore(self):
        for key,value in self.saved.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    def test_accept_stage_progress_complete_and_rewards_once(self):
        accepted=runtime.accept(self.player,"wolf_hunt");self.assertEqual(accepted["state"]["stage_id"],"hunt")
        self.assertEqual(runtime.progress(self.player,"kill_mob","wolf")[0]["status"],"progress")
        moved=runtime.progress(self.player,"kill_mob","wolf")[0];self.assertEqual(moved["stage_id"],"report")
        done=runtime.progress(self.player,"talk_npc","guard")[0];self.assertEqual(done["status"],"completed")
        self.assertEqual(self.player["money"],50);self.assertEqual(self.player["experience"],10)
        with self.assertRaises(ValueError):runtime.accept(self.player,"wolf_hunt")
    def test_disabled_quest_cannot_start(self):
        quests.store().set_status("wolf_hunt",quests.STATUS_DISABLED,force=True)
        with self.assertRaises(ValueError):runtime.accept(self.player,"wolf_hunt")
    def test_quest_runtime_emits_achievement_events(self):
        achievements.store().create("quester",{"name":"Квестовик","conditions":[{"type":"complete_quest","target":"wolf_hunt","amount":1}]})
        achievements.store().set_status("quester",achievements.STATUS_PUBLISHED,force=True)
        runtime.accept(self.player,"wolf_hunt");runtime.progress(self.player,"kill_mob","wolf");runtime.progress(self.player,"kill_mob","wolf");runtime.progress(self.player,"talk_npc","guard")
        self.assertTrue(achievement_engine.is_earned(self.player,"quester"))
    def test_deadline_fails(self):
        env=quests.store().get("wolf_hunt");data=dict(env["data"]);data["deadline_seconds"]=1;quests.store().update("wolf_hunt",data);quests.store().set_status("wolf_hunt",quests.STATUS_PUBLISHED,force=True)
        start=datetime(2026,1,1,tzinfo=timezone.utc);runtime.accept(self.player,"wolf_hunt",now=start)
        result=runtime.progress(self.player,"kill_mob","wolf",now=datetime(2026,1,1,0,0,2,tzinfo=timezone.utc))[0]
        self.assertEqual(result["status"],"failed")

    def publish(self,qid,data):
        quests.store().create(qid,{"name":qid,"quest_type":"side","completion_conditions":["all_tasks_done"],**data});quests.store().set_status(qid,quests.STATUS_PUBLISHED,force=True)

    def test_accept_conditions_items_choices_and_branch(self):
        self.publish("branch",{"accept_conditions":[{"type":"item","object_id":"key","amount":1},{"type":"reputation","object_id":"guard","amount":5}],"stages":[{"stage_id":"start"},{"stage_id":"left"},{"stage_id":"right"}],"quest_items":[{"item_id":"letter","count":1,"give_on_accept":True,"take_on_complete":True,"bound":True,"cannot_drop":True}],"choices":[{"choice_id":"L","stage_id":"start","text":"Налево","next_stage":"left","reputation_id":"guard","reputation_change":2,"remember_choice":True}],"tasks":[{"task_id":"done","stage_id":"left","task_type":"talk_npc","target_id":"sage","required_count":1}]})
        with self.assertRaises(ValueError):runtime.accept(self.player,"branch")
        self.player["inventory"]=[{"item_id":"key","quantity":1}];self.player["reputations"]={"guard":5};runtime.accept(self.player,"branch")
        self.assertTrue(any(row.get("item_id")=="letter" and row.get("bound") for row in self.player["inventory"]))
        chosen=runtime.choose(self.player,"branch","L");self.assertEqual(chosen["stage_id"],"left");self.assertEqual(self.player["reputations"]["guard"],7);self.assertEqual(self.player["quest_choices"]["branch"],"L")
        result=runtime.progress(self.player,"talk_npc","sage")[0];self.assertEqual(result["status"],"completed");self.assertFalse(any(row.get("item_id")=="letter" for row in self.player["inventory"]))

    def test_alternative_failure_task_and_failure_consequences(self):
        self.publish("danger",{"stages":[{"stage_id":"main"}],"tasks":[{"task_id":"a","stage_id":"main","task_type":"visit_location","target_id":"a","alternative":True},{"task_id":"b","stage_id":"main","task_type":"visit_location","target_id":"b","alternative":True},{"task_id":"trap","stage_id":"main","task_type":"pass_event","target_id":"trap","failure_task":True}],"can_fail":True,"fail_consequences":[{"type":"reputation","object_id":"guard","amount":-3},{"type":"event","object_id":"after_fail"}],"repeat_after_fail":True})
        self.player["reputations"]={"guard":10};runtime.accept(self.player,"danger");failed=runtime.progress(self.player,"pass_event","trap")[0];self.assertEqual(failed["status"],"failed");self.assertEqual(self.player["reputations"]["guard"],7);self.assertEqual(self.player["constructor_event_id"],"after_fail")
        runtime.accept(self.player,"danger");done=runtime.progress(self.player,"visit_location","b")[0];self.assertEqual(done["status"],"completed")

    def test_daily_default_cooldown_and_item_event_sources(self):
        self.publish("daily",{"repeat_mode":"daily","stages":[{"stage_id":"main"}],"tasks":[{"stage_id":"main","task_type":"use_item","target_id":"token"}]})
        start=datetime(2026,1,1,tzinfo=timezone.utc);runtime.accept(self.player,"daily",now=start);runtime.progress(self.player,"use_item","token",now=start)
        self.assertFalse(runtime.can_accept(self.player,"daily",now=datetime(2026,1,1,12,tzinfo=timezone.utc))[0]);self.assertTrue(runtime.can_accept(self.player,"daily",now=datetime(2026,1,2,1,tzinfo=timezone.utc))[0])
        self.publish("from_item",{"source_type":"item","source_id":"scroll","stages":[{"stage_id":"main"}]});self.publish("from_event",{"source_type":"event","source_id":"festival","stages":[{"stage_id":"main"}]})
        self.assertEqual(runtime.trigger_source(self.player,"item","scroll")[0]["state"]["quest_id"],"from_item");self.assertEqual(runtime.trigger_source(self.player,"event","festival")[0]["state"]["quest_id"],"from_event")

    def test_shared_telegram_vk_quest_menu(self):
        from services.city_service import process_world_action
        class Storage:
            def update_player(_self,p):pass
        self.publish("local",{"source_type":"location","source_id":"town","stages":[{"stage_id":"main"}],"tasks":[{"stage_id":"main","task_type":"talk_npc","target_id":"sage"}]})
        self.player["constructor_location_id"]="town";storage=Storage();menu=process_world_action(storage,self.player,"Квесты и задания","telegram");self.assertIn("local",str(menu.buttons))
        accepted=process_world_action(storage,self.player,"Принять квест: local","vk");self.assertIn("Квест принят",accepted.text)

    def test_legacy_import_preserves_id_and_player_progress(self):
        from services import world_content_registry as world
        world.create_content(world.KIND_QUEST,"legacy_id",{"name":"Старый квест","description":"Текст","rewards":[]})
        self.player["quests"]={"active":{},"completed":{"legacy_id":{"count":4}},"failed":{}}
        report=quests.import_legacy(actor="test");self.assertEqual(report["created"],1);self.assertIsNotNone(quests.store().get("legacy_id"));self.assertEqual(self.player["quests"]["completed"]["legacy_id"]["count"],4)

    def test_configured_death_failure_blocks_repeat(self):
        self.publish("fatal",{"stages":[{"stage_id":"main"}],"tasks":[{"stage_id":"main","task_type":"survive_turns","required_count":3}],"can_fail":True,"fail_on_death":True,"repeat_after_fail":False})
        runtime.accept(self.player,"fatal");result=runtime.progress(self.player,"death","pve")[0];self.assertEqual(result["status"],"failed");self.assertFalse(runtime.can_accept(self.player,"fatal")[0])

    def test_reward_types_and_delivery_are_executed(self):
        rewards=[{"type":"item","object_id":"prize","count":2,"delivery_mode":"delivery"},{"type":"skill_points","count":2},{"type":"stat_points","count":3},{"type":"skill","object_id":"slash"},{"type":"achievement","object_id":"hero"},{"type":"reputation","object_id":"guards","count":4},{"type":"hidden_reputation","object_id":"thieves","count":5},{"type":"access_location","object_id":"vault"},{"type":"access_camp","object_id":"camp"},{"type":"access_npc","object_id":"sage"},{"type":"access_market","object_id":"bazaar"},{"type":"recipe","object_id":"soup"},{"type":"promo","object_id":"gift"},{"type":"system_flag","object_id":"flag"}]
        self.publish("rewards",{"stages":[{"stage_id":"main"}],"tasks":[{"stage_id":"main","task_type":"talk_npc","target_id":"king"}],"rewards":rewards})
        runtime.accept(self.player,"rewards");runtime.progress(self.player,"talk_npc","king")
        self.assertEqual(self.player["free_skill_points"],2);self.assertEqual(self.player["free_stat_points"],3);self.assertIn("slash",self.player["unlocked_skills"]);self.assertIn("hero",self.player["achievements"]);self.assertEqual(self.player["reputations"]["guards"],4);self.assertEqual(self.player["hidden_reputations"]["thieves"],5)
        for key in ("vault","camp","sage","bazaar","soup","flag"):self.assertTrue(self.player["unlocks"][key]);self.assertTrue(self.player["craft_delivery_inbox"]);self.assertIn("gift",self.player["promo_unlocks"])

if __name__=="__main__":unittest.main()
