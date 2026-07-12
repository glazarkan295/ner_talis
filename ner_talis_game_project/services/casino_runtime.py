"""Published underground casino runtime and audit log (§28–§51)."""

from __future__ import annotations

import json
import os
import random
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_paths import resolve_project_path
from services import casino_constructor_service as casinos

_lock=threading.RLock()

def _int(v:Any,d:int=0)->int:
    try:return int(float(v))
    except (TypeError,ValueError):return d
def _now()->datetime:return datetime.now(timezone.utc)
def _log_path()->Path:return resolve_project_path(os.getenv("CASINO_LOG_PATH","data/casino_operations.jsonl"))

def _published()->list[dict[str,Any]]:
    return [e for e in casinos.store().list(status=casinos.STATUS_PUBLISHED) if (e.get("data") or {}).get("enabled",True)]
def definition(cid:str)->dict[str,Any]|None:
    env=next((e for e in _published() if str(e.get("id"))==str(cid)),None)
    return {"id":env.get("id"),**dict(env.get("data") or {})} if env else None

def casinos_for_parent(parent_type:str,parent_id:str)->list[dict[str,Any]]:
    field={"city":"city_id","location":"location_id","sublocation":"sublocation_id","tavern":"tavern_id","criminal_zone":"criminal_zone_id"}.get(parent_type)
    return [{"id":e.get("id"),"name":(e.get("data") or {}).get("player_name") or (e.get("data") or {}).get("name") or e.get("id")} for e in _published() if field and str((e.get("data") or {}).get(field) or "")==str(parent_id)]

def _active_fines(player:dict[str,Any])->list[dict[str,Any]]:
    try:
        from services.fine_service import active_fines
        return active_fines(player)
    except Exception:return []

def access_error(player:dict[str,Any],data:dict[str,Any],*,now:datetime|None=None)->str|None:
    denied=str(data.get("access_denied_text") or "Вход в казино закрыт.")
    if data.get("closed_by_admin") or player.get("casino_blocked",{}).get(data["id"]):return str(data.get("closed_text") or denied)
    if _int(player.get("level"),1)<_int(data.get("min_level")):return denied
    rep=str(data.get("required_reputation_id") or "")
    if rep and _int((player.get("reputations") or {}).get(rep))<_int(data.get("required_reputation_value")):return denied
    hidden=str(data.get("required_hidden_reputation_id") or "")
    if hidden and _int((player.get("hidden_reputations") or {}).get(hidden))<_int(data.get("required_hidden_reputation_value")):return denied
    item=str(data.get("required_item_id") or "")
    if item and not any(isinstance(r,dict) and str(r.get("item_id") or r.get("id") or "")==item and _int(r.get("amount"),1)>0 for r in player.get("inventory") or []):return denied
    fines=_active_fines(player)
    if data.get("requires_no_fine") and fines:return denied
    if data.get("required_fine_id") and not any(str(f.get("fine_type_id") or f.get("source") or "")==str(data["required_fine_id"]) for f in fines):return denied
    hour=(now or _now()).hour
    if data.get("night_only") and not (hour>=20 or hour<6):return denied
    return None

def _currency_key(player:dict[str,Any],currency:str)->tuple[dict[str,Any],str]:
    if currency in {"copper","coins"}:return player,"money_copper" if "money_copper" in player else "money"
    bucket=player.setdefault("currencies",{});return bucket,currency

def _usage(player:dict[str,Any],cid:str,gid:str)->dict[str,Any]:
    day=_now().date().isoformat();year,week,_=_now().isocalendar();key=f"{year}-W{week:02d}"
    root=player.setdefault("casino_usage",{}).setdefault(cid,{});root.setdefault("day",{})
    if root["day"].get("key")!=day:root["day"]={"key":day,"games":0,"wins":0,"losses":0,"bet":0,"won":0}
    root.setdefault("week",{})
    if root["week"].get("key")!=key:root["week"]={"key":key,"games":0,"wins":0,"losses":0,"bet":0,"won":0}
    game=root.setdefault("games",{}).setdefault(gid,{"plays":0,"wins":0,"losses":0,"bet":0,"won":0})
    return {"_root":root,"_game":game}

def _check_limits(player:dict[str,Any],data:dict[str,Any],game:dict[str,Any],bet:int)->str|None:
    gid=str(game.get("game_id") or game.get("id") or game.get("game_type"));usage=_usage(player,data["id"],gid);root=usage["_root"];game_usage=usage["_game"]
    limits=(("games_per_day",root["day"]["games"]),("games_per_week",root["week"]["games"]),("game_limit",game_usage["plays"]),("bet_sum_per_day",root["day"]["bet"]+bet))
    for field,current in limits:
        maximum=_int(game.get(field) or data.get(field))
        if maximum and current>=maximum:return str(game.get("limit_text") or data.get("limit_text") or "Лимит игры исчерпан.")
    return None

def _append_log(record:dict[str,Any])->None:
    path=_log_path();path.parent.mkdir(parents=True,exist_ok=True)
    with _lock:
        with path.open("a",encoding="utf-8") as fh:fh.write(json.dumps(record,ensure_ascii=False,separators=(",",":"))+"\n")

def read_logs(limit:int=200)->list[dict[str,Any]]:
    try:lines=_log_path().read_text(encoding="utf-8").splitlines()[-max(1,min(limit,2000)):]
    except OSError:return []
    out=[]
    for line in lines:
        try:out.append(json.loads(line))
        except json.JSONDecodeError:pass
    return list(reversed(out))

def _give_reward(player:dict[str,Any],row:dict[str,Any],amount:int)->str:
    kind=str(row.get("type") or row.get("reward_type") or row.get("prize_type") or "currency");oid=str(row.get("object_id") or row.get("item_id") or row.get("prize_id") or "")
    if kind in {"currency","coins"}:
        currency=str(row.get("currency") or "copper")
        try:
            from services.economy_runtime import reward_amount
            amount=reward_amount("casino",amount,{"player_level":player.get("level",1)})
        except (ImportError,ValueError):pass
        bucket,key=_currency_key(player,currency);bucket[key]=_int(bucket.get(key))+amount
        if bucket is player and key=="money_copper":player["money"]=bucket[key]
    elif kind in {"item","rare_item"} and oid:
        from services.inventory_service import add_inventory_item
        from services.item_registry import build_inventory_item
        add_inventory_item(player,build_inventory_item(oid,amount,item_id=oid),amount,default_source="casino")
    elif kind in {"experience","exp"}:player["experience"]=_int(player.get("experience"))+amount
    elif kind in {"reputation","hidden_reputation"}:
        key="hidden_reputations" if kind=="hidden_reputation" else "reputations";bucket=player.setdefault(key,{});bucket[oid]=_int(bucket.get(oid))+amount
    elif kind=="achievement" and oid:
        from services.achievement_engine import grant
        grant(None,player,oid,source="casino",save=False,notify=False)
    elif kind in {"access_npc","access_quest","unlock"} and oid:player.setdefault("unlocks",{})[oid]=True
    return str(row.get("text") or f"Награда: {kind} {oid} ×{amount}.")

def _wheel_result(player:dict[str,Any],data:dict[str,Any],rng:random.Random)->tuple[bool,dict[str,Any]|None,float]:
    """Roll the persistent wheel and move a won prize's chance to the empty sector."""
    state=player.setdefault("casino_wheels",{}).setdefault(data["id"],{})
    if not state.get("initialized"):
        state.update({"initialized":True,"prizes":[dict(row) for row in data.get("wheel_prizes") or []],"empty_chance":float(data.get("wheel_empty_chance") or 0)})
    prizes=state.get("prizes") or [];weights=[max(0,float(row.get("chance") or 0)) for row in prizes];empty=max(0,float(state.get("empty_chance") or 0));total=sum(weights)+empty
    if total<=0:return False,None,0.0
    roll=rng.random()*total;cursor=0.0
    for index,(row,weight) in enumerate(zip(prizes,weights)):
        cursor+=weight
        if roll<cursor and weight>0:
            updated=casinos.wheel_redistribute(prizes,empty,index);state.update(updated)
            return True,row,roll
    return False,None,roll

def _loss(player:dict[str,Any],row:dict[str,Any],data:dict[str,Any])->str:
    kind=str(row.get("type") or row.get("loss_type") or "stake");amount=max(0,_int(row.get("amount") or row.get("value")));oid=str(row.get("object_id") or "")
    if kind in {"currency","extra_currency"}:
        bucket,key=_currency_key(player,str(row.get("currency") or "copper"));bucket[key]=max(0,_int(bucket.get(key))-amount)
    elif kind=="fine":
        from services.fine_service import create_raid_fine
        create_raid_fine(player,oid or str(data.get("fine_id") or "underground_casino"))
    elif kind in {"reputation","hidden_reputation"}:
        key="hidden_reputations" if kind=="hidden_reputation" else "reputations";bucket=player.setdefault(key,{});bucket[oid]=_int(bucket.get(oid))-amount
    elif kind=="effect" and oid:
        from services.effect_formula_runtime import apply_to_player
        apply_to_player(player,oid,source="casino_loss")
    elif kind=="debt":player["debt"]=_int(player.get("debt"))+amount
    elif kind=="block":player.setdefault("casino_blocked",{})[data["id"]]=True
    return str(row.get("text") or row.get("consequence_text") or "Применено последствие проигрыша.")

def _raid(player:dict[str,Any],data:dict[str,Any],game:dict[str,Any],bet:int,rng:random.Random)->tuple[bool,list[str]]:
    if not data.get("raid_enabled",bool(data.get("raid_risk_percent"))):return False,[]
    chance=float(game.get("raid_risk_percent") or data.get("raid_risk_percent") or 0)
    if data.get("raid_depends_bet"):chance+=min(25,bet/max(1,_int(data.get("max_bet"),bet))*10)
    if rng.random()*100>=chance:return False,[]
    lines=[str(data.get("raid_text") or "🚨 Началась облава!")]
    if data.get("raid_gives_fine",True):
        from services.fine_service import create_raid_fine
        result=create_raid_fine(player,str(data.get("fine_id") or "underground_casino"));lines.append(str(data.get("fine_text") or "Вы получили штраф."))
        if data.get("raid_moves_fortress"):
            from services.fine_service import move_player_to_fortress
            move_player_to_fortress(player)
    if data.get("raid_closes_casino"):player.setdefault("casino_blocked",{})[data["id"]]=True
    player.pop("current_casino_id",None)
    return True,lines

def play(player:dict[str,Any],cid:str,gid:str,bet:int,*,platform:str="",rng:random.Random|None=None)->dict[str,Any]:
    rng=rng or random.Random();data=definition(cid)
    if not data:raise ValueError("Казино не опубликовано.")
    try:
        from services.economy_runtime import casino_rule
        economy=casino_rule(cid)
    except ImportError:economy={}
    if economy:
        overlay={"min_bet":economy.get("min_bet"),"max_bet":economy.get("max_bet"),"currency":economy.get("currency"),"win_chance":economy.get("win_chance"),"win_multiplier":economy.get("win_multiplier"),"commission":economy.get("commission_percent"),"games_per_week":economy.get("weekly_limit"),"game_limit":economy.get("game_limit"),"raid_chance":economy.get("fine_risk"),"bet_text":economy.get("bet_text"),"win_text":economy.get("win_text"),"loss_text":economy.get("loss_text"),"limit_text":economy.get("limit_text")}
        data={**data,**{key:value for key,value in overlay.items() if value not in (None,"")}}
    denied=access_error(player,data)
    if denied:raise ValueError(denied)
    game=next((g for g in data.get("games") or [] if isinstance(g,dict) and str(g.get("game_id") or g.get("id") or g.get("game_type"))==gid and g.get("active",True)),None)
    if not game:raise ValueError("Игра не найдена или отключена.")
    minimum=max(0,_int(data.get("min_bet"),_int(game.get("min_bet"))) if economy else _int(game.get("min_bet"),_int(data.get("min_bet"))));maximum=max(minimum,(_int(data.get("max_bet"),minimum) if economy else _int(game.get("max_bet"),_int(data.get("max_bet"),minimum))))
    if bet<minimum or bet>maximum:raise ValueError(f"Ставка должна быть от {minimum} до {maximum}.")
    limit=_check_limits(player,data,game,bet)
    if limit:raise ValueError(limit)
    currency=str((data.get("currency") if economy else game.get("currency") or data.get("currency")) or "copper");bucket,key=_currency_key(player,currency)
    if _int(bucket.get(key))<bet:raise ValueError(str(data.get("not_enough_money_text") or "Недостаточно игровой валюты."))
    before=_int(bucket.get(key));bucket[key]=before-bet;operation_id=uuid.uuid4().hex;chance=float(data.get("win_chance") if economy and data.get("win_chance") not in (None,"") else game.get("win_chance") or 0);roll=rng.random()*100;wheel_prize=None
    record={"operation_id":operation_id,"at":_now().isoformat(),"casino_id":cid,"game_id":gid,"game_id_player":str(player.get("game_id") or player.get("id") or ""),"nt_id":str(player.get("game_id") or ""),"platform":platform,"bet":bet,"currency":currency,"chance":chance,"roll":roll,"formula":game.get("win_formula_id"),"risks":[],"fines":[],"error":None}
    lines=[]
    try:
        if game.get("win_formula_id"):
            from services.formula_runtime import evaluate
            chance=float(evaluate(game.get("win_formula_id"),{"base_amount":chance,"bet":bet,"player_level":player.get("level",1)},default=chance))
        is_wheel=str(game.get("game_type") or "")=="wheel" and bool(data.get("wheel_enabled") or data.get("wheel_prizes"))
        if is_wheel:won,wheel_prize,roll=_wheel_result(player,data,rng);chance=sum(max(0,float(row.get("chance") or 0)) for row in player.get("casino_wheels",{}).get(cid,{}).get("prizes",[]))
        else:won=roll<max(0,min(100,chance))
        coefficient=float(data.get("win_multiplier") if economy and data.get("win_multiplier") not in (None,"") else game.get("coefficient") or game.get("win_multiplier") or 1)
        payout=max(0,int(bet*coefficient));commission=max(0,min(100,float(data.get("commission") if economy else game.get("commission") or data.get("commission") or 0)));payout=max(0,int(payout*(100-commission)/100))
        try:
            from services.economy_runtime import commission_adjusted
            payout=commission_adjusted(payout,"casino",player,{"casino_id":cid,"game_id":gid},payout=True)
        except (ImportError,ValueError):pass
        if _int(economy.get("win_limit"),0):payout=min(payout,_int(economy.get("win_limit")))
        if won:
            bucket[key]=_int(bucket.get(key))+payout
            lines.append(str(data.get("win_text") if economy and data.get("win_text") else game.get("win_text") or data.get("win_text") or f"Вы выиграли {payout} {currency}."))
            if wheel_prize:lines.append(_give_reward(player,wheel_prize,max(1,_int(wheel_prize.get("amount"),1))))
            for row in game.get("rewards") or data.get("win_rewards") or []:
                if isinstance(row,dict) and rng.random()*100<float(row.get("chance") or 100):lines.append(_give_reward(player,row,max(1,_int(row.get("amount"),1))))
        else:
            lines.append(str(data.get("loss_text") if economy and data.get("loss_text") else game.get("loss_text") or data.get("loss_text") or "Ставка проиграна."))
            for row in game.get("losses") or data.get("losses") or []:
                if isinstance(row,dict) and rng.random()*100<float(row.get("chance") or 100):lines.append(_loss(player,row,data))
        raided,raid_lines=_raid(player,data,game,bet,rng);lines.extend(raid_lines)
        usage=_usage(player,cid,gid);root=usage["_root"];game_usage=usage["_game"]
        for period in (root["day"],root["week"]):period["games"]+=1;period["bet"]+=bet;period["wins" if won else "losses"]+=1;period["won"]+=payout if won else 0
        game_usage["plays"]+=1;game_usage["bet"]+=bet;game_usage["wins" if won else "losses"]+=1;game_usage["won"]+=payout if won else 0
        streak=player.setdefault("casino_win_streaks",{});streak[cid]=_int(streak.get(cid))+1 if won else 0;suspicious=streak[cid]>=_int(data.get("suspicious_win_streak"),5)
        trigger="win" if won else "loss"
        for row in data.get("reputation_rules") or []:
            if not isinstance(row,dict) or str(row.get("trigger") or "play") not in {"play",trigger,"raid" if raided else ""}:continue
            rid=str(row.get("reputation_id") or "");rep_bucket=player.setdefault("hidden_reputations" if row.get("hidden") else "reputations",{});rep_bucket[rid]=_int(rep_bucket.get(rid))+_int(row.get("value"))
        for row in data.get("events") or []:
            if not isinstance(row,dict) or str(row.get("trigger") or "") not in {"play",trigger,"raid" if raided else ""}:continue
            if rng.random()*100<float(row.get("chance") or 100) and row.get("event_id"):player["constructor_event_id"]=str(row["event_id"]);lines.append(str(row.get("text") or "Запущено событие казино."))
        for row in data.get("achievement_rules") or []:
            if not isinstance(row,dict):continue
            condition=str(row.get("condition") or "win")
            matched=(condition==trigger or condition=="play" or condition=="first_win" and won and root["day"]["wins"]==1 or condition=="win_streak" and won and streak[cid]>=_int(row.get("value"),2))
            if matched and row.get("achievement_id"):
                try:
                    from services.achievement_engine import grant
                    grant(None,player,str(row["achievement_id"]),source=f"casino:{cid}",save=False,notify=False);lines.append(str(row.get("text") or "Получено достижение казино."))
                except Exception:pass
        record.update({"result":"win" if won else "loss","won":payout if won else 0,"lost":bet if not won else 0,"wheel_prize":str((wheel_prize or {}).get("name") or (wheel_prize or {}).get("prize_id") or "") or None,"raid":raided,"suspicious":suspicious,"balance_before":before,"balance_after":_int(bucket.get(key))})
        try:
            from services.economy_runtime import record as economy_record
            economy_record(player,"casino_play",currency,_int(bucket.get(key))-before,before,_int(bucket.get(key)),source="casino",source_id=cid)
        except (ImportError,OSError):pass
        try:
            from services.achievement_engine import record_game_event
            record_game_event(player,"casino_win" if won else "casino_loss",1,gid)
        except Exception:pass
        return {"text":"\n".join(lines),"won":won,"payout":payout if won else 0,"raid":raided,"operation_id":operation_id}
    except Exception as exc:
        bucket[key]=before;record.update({"result":"error","error":str(exc),"balance_after":before});raise
    finally:_append_log(record)

def _main(data:dict[str,Any])->dict[str,Any]:
    buttons=[]
    for game in data.get("games") or []:
        if isinstance(game,dict) and game.get("active",True):buttons.append([f"Игра казино: {data['id']}:{game.get('game_id') or game.get('id') or game.get('game_type')}"])
    buttons.append([str(data.get("exit_button_text") or "Покинуть казино")])
    return {"text":str(data.get("entry_text") or data.get("description") or data.get("name")),"buttons":buttons}

def try_handle(player:dict[str,Any],action:str,*,platform:str="",rng:random.Random|None=None)->dict[str,Any]|None:
    act=str(action or "").strip();data=None
    for env in _published():
        d={"id":env.get("id"),**dict(env.get("data") or {})}
        if act in {str(env.get("id")),str(d.get("name") or ""),str(d.get("player_name") or ""),f"Казино: {env.get('id')}"}:data=d;break
    if data:
        denied=access_error(player,data)
        if denied:return {"text":denied,"buttons":[[str(data.get("exit_button_text") or "Назад")]]}
        player["current_casino_id"]=data["id"];return _main(data)
    cid=str(player.get("current_casino_id") or "");data=definition(cid)
    if not data:return None
    if act.startswith(f"Игра казино: {cid}:"):
        gid=act.rsplit(":",1)[1];game=next((g for g in data.get("games") or [] if isinstance(g,dict) and str(g.get("game_id") or g.get("id") or g.get("game_type"))==gid),{})
        lo=max(0,_int(game.get("min_bet"),_int(data.get("min_bet"))));hi=max(lo,_int(game.get("max_bet"),_int(data.get("max_bet"),lo)));choices=sorted(set([lo,hi,(lo+hi)//2]))
        return {"text":str(data.get("bet_text") or f"Выберите ставку от {lo} до {hi}."),"buttons":[[f"Ставка казино: {cid}:{gid}:{x}"] for x in choices] + [[f"Казино: {cid}"]]}
    if act.startswith(f"Ставка казино: {cid}:"):
        _,_,gid,amount=act.split(":",3)
        try:result=play(player,cid,gid,_int(amount),platform=platform,rng=rng)
        except ValueError as exc:return {"text":str(exc),"buttons":[[f"Казино: {cid}"]]}
        return {"text":result["text"],"buttons":[] if result["raid"] else [[f"Игра казино: {cid}:{gid}"],[f"Казино: {cid}"]]}
    if act in {str(data.get("exit_button_text") or "Покинуть казино"),"Назад","Покинуть казино"}:
        player.pop("current_casino_id",None);target=str(data.get("tavern_id") or data.get("location_id") or data.get("city_id") or "")
        return {"text":str(data.get("exit_text") or "Вы покинули казино."),"buttons":[[str(data.get("return_button_text") or "Назад")]],"target":target}
    return None
