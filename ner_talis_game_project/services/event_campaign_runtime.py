"""Runtime участия, задач, этапов, наград и рейтинга игровых эвентов."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from services.event_campaign_service import published

def _now(): return datetime.now(timezone.utc)
def _dt(v):
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")) if v else None
    except ValueError:return None
def _bucket(player):
    value=player.get("event_campaigns");value=value if isinstance(value,dict) else {};player["event_campaigns"]=value;return value
def _notify(player,text,storage=None):
    gid=str(player.get("game_id") or player.get("id") or "")
    try:
        from services.message_delivery import notify_player
        status=notify_player(storage,gid,text,type="event",source="event_campaign")
        if status!="skipped":return
    except Exception:pass
    player.setdefault("pending_bot_messages",[]).append({"type":"event","text":text,"source":"event_campaign"})
def _linked_broadcasts(player,data,scope,storage=None):
    for raw in data.get("broadcast_ids") or []:
        row=raw if isinstance(raw,dict) else {"broadcast_id":str(raw),"scope":"final"};broadcast_id=str(row.get("broadcast_id") or row.get("id") or "")
        if str(row.get("scope") or "final")!=scope or not broadcast_id:continue
        if storage is None:
            player.setdefault("pending_event_broadcasts",[]).append({"broadcast_id":broadcast_id,"scope":scope});continue
        try:
            from services.broadcast_campaign_runtime import _deliver_one
            from services import broadcast_constructor_service as definitions
            env=definitions.store().get(broadcast_id)
            if env and env.get("status")==definitions.STATUS_PUBLISHED:_deliver_one(storage,broadcast_id,env.get("data") or {},str(player.get("game_id") or player.get("id") or ""))
        except Exception:pass
def _active(data,now):
    start,end=_dt(data.get("start_at")),_dt(data.get("end_at"));return (not start or now>=start) and (data.get("endless") or not end or now<end)
def eligible(player:dict[str,Any],event_id:str,*,now=None)->tuple[bool,str]:
    data=published(event_id)
    if not data:return False,"Эвент не опубликован."
    if not _active(data,now or _now()):return False,"Эвент сейчас не активен."
    gid=str(player.get("game_id") or player.get("id") or "")
    if gid in {str(x) for x in data.get("excluded_player_ids") or []}:return False,"Игрок исключён из эвента."
    explicit={str(x) for x in data.get("participant_ids") or []}
    if explicit and gid not in explicit:return False,"Игрок не включён в список участников."
    if int(player.get("level") or 1)<int(data.get("min_level") or 0):return False,"Недостаточный уровень."
    race=str(data.get("required_race") or "")
    if race and race!=str(player.get("race_id") or ""):return False,"Раса не подходит."
    ach=str(data.get("required_achievement") or "")
    if ach:
        from services.achievement_engine import is_earned
        if not is_earned(player,ach):return False,"Нет требуемого достижения."
    rep=str(data.get("required_reputation_id") or "")
    if rep:
        from services.reputation_runtime_service import value
        if value(player,rep)<float(data.get("required_reputation_value") or 0):return False,"Недостаточная репутация."
    if data.get("exclude_with_fine"):
        from services.fine_service import has_active_fine
        if has_active_fine(player):return False,"Игрок со штрафом не может участвовать."
    return True,""
def _tasks(data,stage):return [x for x in data.get("tasks") or [] if isinstance(x,dict) and str(x.get("stage_id") or stage)==stage]
def _stage_ids(data):return [str(x.get("stage_id")) for x in data.get("stages") or [] if isinstance(x,dict) and x.get("stage_id")]
def join(player,event_id,*,now=None,method="button",storage=None):
    ok,error=eligible(player,event_id,now=now)
    if not ok:raise ValueError(error)
    states=_bucket(player)
    if event_id in states:return states[event_id]
    data=published(event_id) or {}
    allowed_methods=[]
    if data.get("registration_via_button",True):allowed_methods.append("button")
    if data.get("registration_via_npc"):allowed_methods.append("npc")
    if data.get("registration_via_item"):allowed_methods.append("item")
    if data.get("registration_required") and method not in allowed_methods:raise ValueError("Этот способ регистрации в эвенте недоступен.")
    registration_item=str(data.get("registration_item_id") or "")
    if method=="item" or registration_item:
        inventory=player.get("inventory") or [];found=next((row for row in inventory if isinstance(row,dict) and str(row.get("item_id") or row.get("id") or "")==registration_item and int(row.get("amount") or 1)>0),None)
        if registration_item and not found:raise ValueError("Для регистрации нужен специальный предмет.")
        if found and data.get("consume_registration_item"):
            found["amount"]=int(found.get("amount") or 1)-1;player["inventory"]=[row for row in inventory if not isinstance(row,dict) or int(row.get("amount") or 0)>0]
    ids=_stage_ids(data);stage=ids[0] if ids else "main"
    state={"event_id":event_id,"status":"active","joined_at":(now or _now()).isoformat(),"stage_id":stage,"progress":{},"points":0,"claimed":[]}
    for row in _tasks(data,stage):state["progress"][str(row.get("task_id"))]={"current":0,"required":max(1,int(row.get("required_count") or 1)),"done":False}
    states[event_id]=state
    _grant_scope(player,state,data,"participation")
    _linked_broadcasts(player,data,"participation",storage)
    player.setdefault("event_temporary_content",{})[event_id]={k:list(data.get(k) or []) for k in ("locations","location_events","mobs","npcs","items","buttons")}
    try:
        from services.achievement_engine import record_game_event
        record_game_event(player,"join_world_event",1,event_id)
        from services.reputation_runtime_service import apply_trigger
        apply_trigger(player,"event_campaign",event_id,reason="Участие в эвенте")
    except Exception:pass
    return state

def auto_join_all(player:dict[str,Any],storage=None)->list[str]:
    from services.event_campaign_service import store,STATUS_PUBLISHED
    joined=[]
    for env in store().list(status=STATUS_PUBLISHED):
        event_id=str(env.get("id"));data=env.get("data") or {}
        if not data.get("all_players") or event_id in _bucket(player):continue
        ok,_=eligible(player,event_id)
        if ok:join(player,event_id,storage=storage);joined.append(event_id)
    return joined
def _grant(player,reward):
    kind=str(reward.get("type") or "");oid=str(reward.get("object_id") or reward.get("item_id") or "");amount=max(1,int(reward.get("amount") or reward.get("count") or 1))
    if kind in ("reputation","hidden_reputation"):
        from services.reputation_runtime_service import change
        change(player,oid,amount,source="event_campaign")
    elif kind=="achievement" and oid:
        from services.achievement_engine import grant
        grant(None,player,oid,source="event_campaign",save=False,notify=False)
    elif kind in ("skill","title","recipe","access") and oid:
        bucket={"skill":"unlocked_skills","title":"titles","recipe":"unlocked_recipes","access":"unlocks"}[kind]
        value=player.setdefault(bucket,{} if kind=="access" else [])
        if isinstance(value,dict):value[oid]=True
        elif oid not in value:value.append(oid)
    else:
        from services.quest_runtime_service import _grant as grant
        aliases={"experience":"exp","access":"system_flag"};grant(player,{"type":aliases.get(kind,kind),"object_id":oid,"count":amount})
def _grant_scope(player,state,data,scope,scope_id=""):
    claim=f"{scope}:{scope_id or 'all'}"
    if claim in state["claimed"]:return
    for reward in data.get("rewards") or []:
        if not isinstance(reward,dict):continue
        reward_scope=str(reward.get("scope") or ("participation" if reward.get("for_participation") else "final"))
        if reward_scope==scope and (not scope_id or not reward.get("scope_id") or str(reward.get("scope_id"))==scope_id):_grant(player,reward)
    state["claimed"].append(claim)
def progress(player,event_type,target_id="",amount=1,*,storage=None):
    auto_join_all(player,storage);results=[]
    for event_id,state in list(_bucket(player).items()):
        if state.get("status")!="active":continue
        data=published(event_id)
        if not data:continue
        stage=str(state.get("stage_id") or "main");changed=False
        for row in _tasks(data,stage):
            if str(row.get("task_type") or "")!=str(event_type):continue
            expected=str(row.get("target_id") or "")
            if expected and expected!=str(target_id):continue
            tid=str(row.get("task_id"));item=state["progress"].setdefault(tid,{"current":0,"required":max(1,int(row.get("required_count") or 1)),"done":False})
            before=item["done"];item["current"]=min(item["required"],int(item.get("current") or 0)+max(0,int(amount)));item["done"]=item["current"]>=item["required"];changed=True
            if item["done"] and not before:
                base_points=int(row.get("points") or item["required"])
                try:
                    from services.formula_runtime import evaluate,numeric_context
                    awarded=max(0,int(evaluate(data.get("points_formula_id"),numeric_context({"base_amount":base_points,"item_count":int(amount),"event_points":int(state.get("points") or 0)},player=player),default=base_points)))
                except Exception:awarded=base_points
                state["points"]+=awarded;_grant_scope(player,state,{"rewards":[{**r,"scope":"task"} for r in row.get("rewards") or [] if isinstance(r,dict)]},"task",tid)
                _notify(player,str(row.get("complete_text") or f"Задача эвента выполнена: {tid}."),storage)
        required=[x for x in state["progress"].values()]
        if changed and required and all(x.get("done") for x in required):
            ids=_stage_ids(data);idx=ids.index(stage) if stage in ids else -1;_grant_scope(player,state,data,"stage",stage)
            if idx+1<len(ids):
                state["stage_id"]=ids[idx+1];state["progress"]={}
                for row in _tasks(data,state["stage_id"]):state["progress"][str(row.get("task_id"))]={"current":0,"required":max(1,int(row.get("required_count") or 1)),"done":False}
                results.append({"event_id":event_id,"status":"stage","stage_id":state["stage_id"]})
                _notify(player,f"Открыт новый этап эвента: {state['stage_id']}.",storage)
            else:
                state["status"]="completed";state["completed_at"]=_now().isoformat();_grant_scope(player,state,data,"final")
                _linked_broadcasts(player,data,"final",storage)
                for world_event_id in data.get("world_event_ids") or []:
                    try:
                        from services import world_event_service as world_events
                        env=world_events.store().get(str(world_event_id))
                        if env and env.get("status")!=world_events.STATUS_ACTIVE:world_events.store().set_status(str(world_event_id),world_events.STATUS_ACTIVE,force=True,actor="event_campaign")
                    except Exception:pass
                try:
                    from services.achievement_engine import record_game_event
                    record_game_event(player,"finish_event",1,event_id)
                except Exception:pass
                results.append({"event_id":event_id,"status":"completed"})
                _notify(player,str(data.get("complete_text") or f"Эвент «{data.get('player_name') or data.get('name') or event_id}» завершён."),storage)
        elif changed:results.append({"event_id":event_id,"status":"progress"})
    return results
def ranking(storage,event_id):
    rows=[]
    for summary in storage.list_player_audience_rows() if hasattr(storage,"list_player_audience_rows") else []:
        gid=str(summary.get("game_id") or "");player=storage.get_player_by_game_id(gid);state=((player or {}).get("event_campaigns") or {}).get(event_id)
        if isinstance(state,dict):rows.append({"game_id":gid,"name":player.get("name"),"points":int(state.get("points") or 0)})
    rows.sort(key=lambda x:(-x["points"],x["game_id"]))
    for i,row in enumerate(rows,1):row["place"]=i
    return rows

def finalize_ranking(storage,event_id):
    """Issue place/range rewards once and return the finalized table."""
    data=published(event_id)
    if not data:raise ValueError("Эвент не опубликован.")
    rows=ranking(storage,event_id);issued=[]
    for row in rows:
        player=storage.get_player_by_game_id(row["game_id"]);state=((player or {}).get("event_campaigns") or {}).get(event_id)
        if not isinstance(state,dict):continue
        claim=f"rating:{event_id}:final"
        if claim in state.setdefault("claimed",[]):continue
        place=int(row["place"])
        for reward in data.get("rewards") or []:
            if not isinstance(reward,dict) or str(reward.get("scope") or "")!="rating":continue
            exact=int(reward.get("place") or 0);start=int(reward.get("place_from") or reward.get("min_place") or 0);end=int(reward.get("place_to") or reward.get("max_place") or 0)
            if exact and place!=exact:continue
            if start and place<start or end and place>end:continue
            _grant(player,reward)
        state["claimed"].append(claim);state["rating_place"]=place
        storage.update_player(player);issued.append(row["game_id"])
        _notify(player,str(data.get("rating_result_text") or f"Итоги эвента: ваше место — {place}."),storage)
    return {"event_id":event_id,"ranking":rows,"issued":issued}
