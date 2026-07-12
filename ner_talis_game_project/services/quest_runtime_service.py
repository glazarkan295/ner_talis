"""Data-driven runtime опубликованных квестов конструктора."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from services.quest_constructor_service import published_definition

_RATES={"copper":1,"silver":1000,"gold":1_000_000,"magic_gold":1_000_000_000,"ancient_coin":500_000_000_000}
def _now()->datetime:return datetime.now(timezone.utc)
def _iso(dt:datetime)->str:return dt.isoformat()
def _bucket(player:dict[str,Any])->dict[str,Any]:
    q=player.get("quests"); q=q if isinstance(q,dict) else {}; q.setdefault("active",{}); q.setdefault("completed",{}); q.setdefault("failed",{}); player["quests"]=q; return q
def _first_stage(data:dict[str,Any])->str:
    stages=[s for s in data.get("stages") or [] if isinstance(s,dict)]
    return str((stages[0] if stages else {}).get("stage_id") or "main")
def _stage(data:dict[str,Any],sid:str)->dict[str,Any]:return next((s for s in data.get("stages") or [] if isinstance(s,dict) and str(s.get("stage_id") or "")==sid),{})
def _tasks(data:dict[str,Any],sid:str)->list[dict[str,Any]]:
    return [dict(t) for t in data.get("tasks") or [] if isinstance(t,dict) and t.get("enabled",True) and str(t.get("stage_id") or _first_stage(data))==sid]
def _item_count(player:dict[str,Any],item_id:str)->int:return sum(int(row.get("quantity") or row.get("count") or 1) for row in player.get("inventory") or [] if isinstance(row,dict) and str(row.get("item_id") or row.get("id") or "")==item_id)
def _remove_item(player:dict[str,Any],item_id:str,count:int)->bool:
    if _item_count(player,item_id)<count:return False
    left=count
    for row in player.get("inventory") or []:
        if left<=0:break
        if isinstance(row,dict) and str(row.get("item_id") or row.get("id") or "")==item_id:
            qty=int(row.get("quantity") or row.get("count") or 1);take=min(qty,left);row["quantity"]=qty-take;left-=take
    player["inventory"]=[row for row in player.get("inventory") or [] if not isinstance(row,dict) or int(row.get("quantity") or row.get("count") or 0)>0];return True
def _condition_error(player:dict[str,Any],data:dict[str,Any])->str:
    if data.get("required_race") and str(player.get("race_id") or player.get("race") or "")!=str(data["required_race"]):return str(data.get("unavailable_text") or "Требуется другая раса.")
    conditions=data.get("accept_conditions") or []
    for raw in conditions:
        if isinstance(raw,str):
            kind,_,value=raw.partition(":");row={"type":kind,"object_id":value}
        elif isinstance(raw,dict):row=raw
        else:continue
        kind=str(row.get("type") or "");oid=str(row.get("object_id") or row.get("value") or "");amount=int(row.get("amount") or row.get("min_value") or 1)
        if kind in {"item","has_item"} and _item_count(player,oid)<amount:return str(data.get("missing_item_text") or "Не хватает требуемого предмета.")
        if kind=="achievement" and oid not in (player.get("achievements") or {}):return str(data.get("unavailable_text") or "Требуется достижение.")
        if kind in {"previous_quest","completed_quest"} and oid not in _bucket(player)["completed"]:return str(data.get("unavailable_text") or "Сначала завершите предыдущий квест.")
        if kind=="failed_quest" and oid not in _bucket(player)["failed"]:return str(data.get("unavailable_text") or "Требуется провал другого квеста.")
        if kind in {"reputation","hidden_reputation"}:
            bucket=player.get("hidden_reputations" if kind=="hidden_reputation" else "reputations") or {}
            if int(bucket.get(oid) or 0)<amount:return str(data.get("unavailable_text") or "Недостаточная репутация.")
        if kind in {"location","sublocation"} and str(player.get("constructor_sublocation_id" if kind=="sublocation" else "constructor_location_id") or player.get("location_id") or "")!=oid:return str(data.get("wrong_location_text") or "Квест недоступен в этой локации.")
        if kind=="npc" and str(player.get("current_npc_id") or player.get("constructor_npc_id") or "")!=oid:return str(data.get("wrong_npc_text") or "Нужен другой NPC.")
        if kind=="effect" and oid not in {str(x.get("effect_id") or x.get("id") or "") for x in player.get("active_effects") or [] if isinstance(x,dict)}:return str(data.get("unavailable_text") or "Требуется эффект.")
        if kind=="no_fine" and (player.get("active_fines") or player.get("active_fine")):return str(data.get("unavailable_text") or "Квест недоступен при штрафе.")
        if kind=="has_fine" and not (player.get("active_fines") or player.get("active_fine")):return str(data.get("unavailable_text") or "Требуется активный штраф.")
        if kind in {"event_campaign","world_event"} and oid not in (player.get("event_campaigns") or player.get("active_world_events") or {}):return str(data.get("unavailable_text") or "Требуется активное событие.")
        if kind=="weekday" and (datetime.now().weekday()+1)!=int(row.get("value") or amount):return str(data.get("unavailable_text") or "Квест недоступен сегодня.")
    return ""

def can_accept(player:dict[str,Any],quest_id:str,*,now:datetime|None=None)->tuple[bool,str]:
    data=published_definition(quest_id)
    if not data:return False,"Квест не опубликован или отключён."
    level=int(player.get("level") or 1); lo=int(data.get("min_level") or 0); hi=int(data.get("max_level") or 0)
    if level<lo or (hi and level>hi):return False,"Уровень игрока не подходит."
    denied=_condition_error(player,data)
    if denied:return False,denied
    q=_bucket(player)
    if quest_id in q["active"]:return False,"Квест уже активен."
    completed=q["completed"].get(quest_id) or {}; repeat=str(data.get("repeat_mode") or "one_time")
    if q["failed"].get(quest_id) and not data.get("repeat_after_fail"):return False,"Квест уже провален и не допускает повтор."
    if completed and repeat in ("","one_time"):return False,"Одноразовый квест уже завершён."
    cooldown=int(data.get("repeat_cooldown_seconds") or 0)
    if not cooldown:cooldown={"daily":86400,"weekly":604800,"monthly":2592000}.get(repeat,0)
    if completed and cooldown:
        try:last=datetime.fromisoformat(str(completed.get("at")).replace("Z","+00:00"))
        except (TypeError,ValueError):last=None
        if last and (now or _now())<last+timedelta(seconds=cooldown):return False,"Квест ещё на перезарядке."
    if int(data.get("repeat_count") or 0) and int(completed.get("count") or 0)>=int(data["repeat_count"]):return False,"Лимит повторов квеста исчерпан."
    moment=now or _now()
    for key,op in (("start_at","before"),("end_at","after")):
        if data.get(key):
            try:boundary=datetime.fromisoformat(str(data[key]).replace("Z","+00:00"))
            except ValueError:boundary=None
            if boundary and ((op=="before" and moment<boundary) or (op=="after" and moment>boundary)):return False,"Квест сейчас недоступен."
    return True,""

def accept(player:dict[str,Any],quest_id:str,*,now:datetime|None=None)->dict[str,Any]:
    from services.race_runtime import restriction_error
    denied=restriction_error(player,"quest",quest_id)
    if denied:raise ValueError(denied)
    ok,error=can_accept(player,quest_id,now=now)
    if not ok:raise ValueError(error)
    data=published_definition(quest_id) or {}; sid=_first_stage(data); moment=now or _now()
    state={"quest_id":quest_id,"name":data.get("name"),"stage_id":sid,"accepted_at":_iso(moment),"deadline_at":_iso(moment+timedelta(seconds=int(data.get("deadline_seconds") or 0))) if data.get("deadline_seconds") else None,"progress":{},"status":"active"}
    for i,t in enumerate(_tasks(data,sid)):state["progress"][str(t.get("task_id") or f"{sid}:{i}")]={"current":0,"required":max(1,int(t.get("required_count") or 1)),"done":False}
    _bucket(player)["active"][quest_id]=state
    for row in data.get("quest_items") or []:
        if isinstance(row,dict) and row.get("give_on_accept") and row.get("item_id"):
            from services.item_registry import build_inventory_item
            from services.inventory_service import add_inventory_item
            item=build_inventory_item(str(row["item_id"]),max(1,int(row.get("count") or 1)),item_id=str(row["item_id"]));item.update({"quest_item":True,"bound":bool(row.get("bound")),"cannot_drop":bool(row.get("cannot_drop")),"cannot_transfer":bool(row.get("cannot_transfer")),"hidden":bool(row.get("hidden"))});add_inventory_item(player,item,max(1,int(row.get("count") or 1)),default_source="quest")
    for reward in data.get("rewards") or []:
        if isinstance(reward,dict) and str(reward.get("grant_timing") or "end") in {"accept","immediate"}:_grant(player,reward,quest_id=quest_id)
    try:
        from services.achievement_engine import record_game_event
        record_game_event(player, "start_quest", target=quest_id)
    except Exception: pass
    return {"state":state,"text":data.get("accept_text") or data.get("appear_text") or data.get("description") or "Квест принят."}

def _matches(task:dict[str,Any],event_type:str,target_id:str)->bool:
    return str(task.get("task_type") or "")==event_type and (not str(task.get("target_id") or "") or str(task.get("target_id"))==str(target_id))
def progress(player:dict[str,Any],event_type:str,target_id:str="",amount:int=1,*,now:datetime|None=None)->list[dict[str,Any]]:
    results=[]; q=_bucket(player); moment=now or _now()
    for quest_id,state in list(q["active"].items()):
        data=published_definition(quest_id)
        if not data:continue
        failure_map={"death":"fail_on_death","item_lost":"fail_on_item_loss","npc_death":"fail_on_npc_death","get_fine":"fail_on_fine","reputation_failed":"fail_on_reputation","choice_failed":"fail_on_choice"}
        if data.get(failure_map.get(event_type,"")):results.append(fail(player,quest_id,event_type,now=moment));continue
        if state.get("deadline_at"):
            try:deadline=datetime.fromisoformat(state["deadline_at"])
            except ValueError:deadline=None
            if deadline and moment>=deadline:results.append(fail(player,quest_id,"deadline",now=moment));continue
        sid=str(state.get("stage_id") or _first_stage(data)); tasks=_tasks(data,sid); changed=False
        for i,task in enumerate(tasks):
            if not _matches(task,event_type,target_id):continue
            if task.get("count_condition") and _condition_error(player,{"accept_conditions":[task["count_condition"]]}):continue
            key=str(task.get("task_id") or f"{sid}:{i}"); row=state["progress"].setdefault(key,{"current":0,"required":max(1,int(task.get("required_count") or 1)),"done":False})
            row["current"]=min(row["required"],int(row.get("current") or 0)+max(0,int(amount))); row["done"]=row["current"]>=row["required"];changed=True
            if row["done"] and task.get("failure_task"):results.append(fail(player,quest_id,"failure_task",now=moment));changed=False;break
        if quest_id not in q["active"]:continue
        required=[row for i,t in enumerate(tasks) if not t.get("optional") and not t.get("alternative") and not t.get("failure_task") for row in [state["progress"].get(str(t.get("task_id") or f"{sid}:{i}"),{})]]
        alternatives=[row for i,t in enumerate(tasks) if t.get("alternative") for row in [state["progress"].get(str(t.get("task_id") or f"{sid}:{i}"),{})]]
        if changed and (not required or all(r.get("done") for r in required)) and (not alternatives or any(r.get("done") for r in alternatives)):
            stage=_stage(data,sid); nxt=str(stage.get("next_stage") or "")
            for reward in stage.get("stage_rewards") or []:
                if isinstance(reward,dict):_grant(player,reward,quest_id=quest_id)
            if nxt:
                state["stage_id"]=nxt;state["progress"]={}
                for i,t in enumerate(_tasks(data,nxt)):state["progress"][str(t.get("task_id") or f"{nxt}:{i}")]={"current":0,"required":max(1,int(t.get("required_count") or 1)),"done":False}
                results.append({"quest_id":quest_id,"status":"stage","stage_id":nxt,"text":_stage(data,nxt).get("player_text") or "Новый этап."})
            else:results.append(complete(player,quest_id,now=moment))
        elif changed:
            completed_task=next((task for i,task in enumerate(tasks) if state["progress"].get(str(task.get("task_id") or f"{sid}:{i}"),{}).get("done") and task.get("complete_text")),None)
            results.append({"quest_id":quest_id,"status":"progress","state":state,"text":str((completed_task or {}).get("complete_text") or data.get("progress_text") or "Прогресс обновлён.")})
    return results

def _grant(player:dict[str,Any],reward:dict[str,Any],*,quest_id:str="")->None:
    kind=str(reward.get("type") or ""); oid=str(reward.get("object_id") or reward.get("item_id") or ""); amount=max(1,int(reward.get("count") or reward.get("amount") or 1))
    if reward.get("formula_id"):
     from services.formula_runtime import evaluate
     amount=max(0,int(evaluate(reward["formula_id"],{"base_amount":amount,"player_level":player.get("level",1)},default=amount)))
    if kind=="currency":
     amount*= _RATES.get(oid or "copper",1)
     try:
      from services.economy_runtime import change,reward_amount
      amount=reward_amount("quest",amount,{"quest_id":quest_id,"player_level":player.get("level",1)})
      change(player,"copper",amount,operation="quest_reward",source="quest",source_id=quest_id)
     except (ImportError,ValueError):player["money"]=int(player.get("money") or 0)+amount
    elif kind=="exp":
     from services.progression_service import grant_experience
     grant_experience(player,amount,source_type="quest",context={"quest_id":quest_id})
    elif kind=="energy":player["energy"]=min(int(player.get("max_energy") or 100),int(player.get("energy") or 0)+amount)
    elif kind=="skill_points":player["free_skill_points"]=int(player.get("free_skill_points") or 0)+amount
    elif kind=="stat_points":player["free_stat_points"]=int(player.get("free_stat_points") or 0)+amount
    elif kind=="item" and oid:
        from services.item_registry import build_inventory_item
        item=build_inventory_item(oid,amount,item_id=oid)
        if str(reward.get("delivery_mode") or "inventory")=="delivery":
         from services.craft_result_delivery import place
         place(player,item,amount,mode="delivery",source=f"Квест {quest_id}")
        else:
         from services.inventory_service import add_inventory_item
         add_inventory_item(player,item,amount,default_source="quest")
    elif kind=="effect" and oid:
     from services.effect_formula_runtime import apply_to_player
     apply_to_player(player,oid,source="quest")
    elif kind=="skill" and oid:player.setdefault("unlocked_skills",[]).append(oid) if oid not in player.setdefault("unlocked_skills",[]) else None
    elif kind=="achievement" and oid:player.setdefault("achievements",{})[oid]={"earned":True,"source":"quest"}
    elif kind in {"reputation","hidden_reputation"} and oid:
     bucket=player.setdefault("hidden_reputations" if kind=="hidden_reputation" else "reputations",{});bucket[oid]=int(bucket.get(oid) or 0)+amount
    elif kind=="promo" and oid:player.setdefault("promo_unlocks",[]).append(oid)
    elif kind in ("npc_helper","npc_ally") and oid:
     from services.npc_ally_runtime import grant
     grant(player,oid,source="quest")
    elif kind in ("system_flag","access_location","access_sublocation","access_camp","access_npc","access_market","recipe","title") and oid:player.setdefault("unlocks",{})[oid]=True

def complete(player:dict[str,Any],quest_id:str,*,now:datetime|None=None)->dict[str,Any]:
    q=_bucket(player);state=q["active"].pop(quest_id,None)
    if not state:raise ValueError("Квест не активен.")
    data=published_definition(quest_id) or {}; claim=f"quest:{quest_id}:{state.get('accepted_at')}";claims=player.setdefault("reward_claims",[])
    for row in data.get("quest_items") or []:
        if isinstance(row,dict) and row.get("take_on_complete") and row.get("item_id") and not _remove_item(player,str(row["item_id"]),max(1,int(row.get("count") or 1))):
            _bucket(player)["active"][quest_id]=state;raise ValueError(str(data.get("missing_item_text") or "Не хватает квестового предмета."))
        if isinstance(row,dict) and row.get("transform_to_item_id"):
            _grant(player,{"type":"item","object_id":row["transform_to_item_id"],"count":row.get("count") or 1},quest_id=quest_id)
        if isinstance(row,dict) and row.get("open_access_id"):player.setdefault("unlocks",{})[str(row["open_access_id"])]=True
        if isinstance(row,dict) and row.get("craft_recipe_id"):player.setdefault("unlocks",{})[str(row["craft_recipe_id"])]=True
    if claim not in claims:
        for reward in data.get("rewards") or []:
            if isinstance(reward,dict) and str(reward.get("grant_timing") or "end") not in {"accept","immediate"}:_grant(player,reward,quest_id=quest_id)
        claims.append(claim)
    q["completed"][quest_id]={"at":_iso(now or _now()),"count":int((q["completed"].get(quest_id) or {}).get("count") or 0)+1}
    try:
        from services.reputation_runtime_service import apply_trigger
        apply_trigger(player, "quest_complete", quest_id)
    except Exception:
        pass
    try:
        from services.achievement_engine import record_game_event
        record_game_event(player, "complete_quest", target=quest_id)
        from services.event_campaign_runtime import progress as event_progress
        event_progress(player, "complete_quest", quest_id, 1)
    except Exception: pass
    return {"quest_id":quest_id,"status":"completed","text":data.get("complete_text") or data.get("reward_text") or "Квест завершён.","rewards":data.get("rewards") or []}

def fail(player:dict[str,Any],quest_id:str,reason:str="manual",*,now:datetime|None=None)->dict[str,Any]:
    q=_bucket(player);state=q["active"].pop(quest_id,None)
    if not state:raise ValueError("Квест не активен.")
    data=published_definition(quest_id) or {};q["failed"][quest_id]={"at":_iso(now or _now()),"reason":reason}
    for row in data.get("quest_items") or []:
        if isinstance(row,dict) and row.get("take_on_fail") and row.get("item_id"):_remove_item(player,str(row["item_id"]),max(1,int(row.get("count") or 1)))
    for row in data.get("fail_consequences") or []:
        if isinstance(row,str):kind,_,oid=row.partition(":");row={"type":kind,"object_id":oid}
        if not isinstance(row,dict):continue
        kind=str(row.get("type") or "");oid=str(row.get("object_id") or "");amount=max(1,int(row.get("amount") or 1))
        if kind=="item":_remove_item(player,oid,amount)
        elif kind in {"reputation","hidden_reputation"}:
            bucket=player.setdefault("hidden_reputations" if kind=="hidden_reputation" else "reputations",{});bucket[oid]=int(bucket.get(oid) or 0)+int(row.get("amount") or -1)
        elif kind=="fine":
            from services.fine_service import create_raid_fine
            create_raid_fine(player,oid or "quest_fail")
        elif kind=="event":player["constructor_event_id"]=oid
        elif kind=="block_branch":player.setdefault("blocked_quest_branches",{})[oid]=True
    try:
        from services.reputation_runtime_service import apply_trigger
        apply_trigger(player, "quest_fail", quest_id, reason=reason)
    except Exception:
        pass
    return {"quest_id":quest_id,"status":"failed","text":data.get("fail_text") or "Квест провален.","reason":reason}

def choose(player:dict[str,Any],quest_id:str,choice_id:str)->dict[str,Any]:
    q=_bucket(player);state=q["active"].get(quest_id);data=published_definition(quest_id)
    if not state or not data:raise ValueError("Квест не активен.")
    choice=next((row for row in data.get("choices") or [] if isinstance(row,dict) and str(row.get("choice_id") or "")==str(choice_id)),None)
    if not choice:raise ValueError("Вариант выбора не найден.")
    if choice.get("condition"):
        error=_condition_error(player,{"accept_conditions":[choice["condition"]],"unavailable_text":data.get("unavailable_text")})
        if error:raise ValueError(error)
    if choice.get("block_other_path") and str(choice_id) in (state.get("blocked_choices") or []):raise ValueError("Этот путь уже заблокирован.")
    state["choice_id"]=choice_id
    if choice.get("remember_choice"):player.setdefault("quest_choices",{})[quest_id]=choice_id
    if choice.get("next_stage"):state["stage_id"]=str(choice["next_stage"]);state["progress"]={}
    for reward in choice.get("rewards") or []:
        if isinstance(reward,dict):_grant(player,reward,quest_id=quest_id)
    for loss in choice.get("losses") or []:
        if isinstance(loss,dict) and loss.get("type")=="item":_remove_item(player,str(loss.get("object_id") or ""),max(1,int(loss.get("amount") or 1)))
    for kind,key in (("reputation","reputation_id"),("hidden_reputation","hidden_reputation_id")):
        oid=str(choice.get(key) or "");amount=int(choice.get(f"{kind}_change") or choice.get("reputation_change") or 0)
        if oid:bucket=player.setdefault("hidden_reputations" if kind.startswith("hidden") else "reputations",{});bucket[oid]=int(bucket.get(oid) or 0)+amount
    if choice.get("next_quest"):player.setdefault("unlocked_quests",{})[str(choice["next_quest"])]=True
    return {"quest_id":quest_id,"status":"choice","choice_id":choice_id,"stage_id":state.get("stage_id"),"text":choice.get("result_text") or choice.get("text") or "Выбор принят."}

def available(player:dict[str,Any],*,source_type:str="",source_id:str="",include_hidden:bool=False)->list[dict[str,Any]]:
    from services import quest_constructor_service as definitions
    result=[]
    for env in definitions.store().list(status=definitions.STATUS_PUBLISHED):
        data={"id":env.get("id"),**dict(env.get("data") or {})}
        if source_type and str(data.get("source_type") or "") not in {source_type,"auto"}:continue
        configured=str(data.get("source_id") or data.get("source_npc_id") or "")
        if source_id and configured and configured!=source_id:continue
        ok,error=can_accept(player,str(env.get("id") or ""))
        hidden=bool(data.get("hidden")) or str(data.get("quest_type") or "") in {"hidden","secret"};revealed=True
        if data.get("reveal_condition"):revealed=not bool(_condition_error(player,{"accept_conditions":[data["reveal_condition"]]}))
        if hidden and not include_hidden and (not ok or not revealed):continue
        if ok:result.append({"id":env.get("id"),"name":data.get("name"),"description":data.get("description"),"source_text":data.get("source_text"),"hidden":hidden})
    return result
def trigger_source(player:dict[str,Any],source_type:str,source_id:str)->list[dict[str,Any]]:
    accepted=[]
    for row in available(player,source_type=source_type,source_id=source_id,include_hidden=True):
        try:accepted.append(accept(player,str(row["id"])))
        except ValueError:pass
    return accepted
def npc_dialogue(player:dict[str,Any],npc_id:str)->dict[str,Any]|None:
    from services import quest_constructor_service as definitions
    q=_bucket(player)
    for env in definitions.store().list(status=definitions.STATUS_PUBLISHED):
        qid=str(env.get("id") or "");data=env.get("data") or {};state=q["active"].get(qid);phase="progress" if state else "complete" if qid in q["completed"] else "fail" if qid in q["failed"] else "before"
        for row in data.get("dialogs") or []:
            if not isinstance(row,dict) or str(row.get("npc_id") or "")!=str(npc_id):continue
            if row.get("stage_id") and (not state or str(row.get("stage_id"))!=str(state.get("stage_id"))):continue
            text=row.get(f"{phase}_text") or (row.get("text") if str(row.get("phase") or phase)==phase else "")
            if text:return {"quest_id":qid,"phase":phase,"text":str(text),"choice_id":row.get("choice_id"),"next_stage":row.get("next_stage")}
    return None

def card(player:dict[str,Any],quest_id:str)->dict[str,Any]:
    data=published_definition(quest_id)
    if not data:raise ValueError("Квест не найден.")
    state=_bucket(player)["active"].get(quest_id);buttons=[]
    if state:
        sid=str(state.get("stage_id") or "");tasks=_tasks(data,sid);lines=[f"📜 {data.get('name')}",str(_stage(data,sid).get("player_text") or data.get("description") or "")]
        for i,task in enumerate(tasks):
            key=str(task.get("task_id") or f"{sid}:{i}");row=state.get("progress",{}).get(key,{})
            if not task.get("hidden_progress"):lines.append(f"• {task.get('target_name') or task.get('task_type')}: {row.get('current',0)}/{row.get('required',task.get('required_count',1))}")
        for choice in data.get("choices") or []:
            if isinstance(choice,dict) and (not choice.get("stage_id") or str(choice.get("stage_id"))==sid):buttons.append([f"Выбор квеста: {quest_id}:{choice.get('choice_id')}"])
        return {"text":"\n".join(lines),"buttons":buttons or [["Квесты и задания"]]}
    ok,error=can_accept(player,quest_id);return {"text":str(data.get("appear_text") or data.get("description") or data.get("name")),"buttons":[[f"Принять квест: {quest_id}"],["Квесты и задания"]] if ok else [["Квесты и задания"]],"error":error}
