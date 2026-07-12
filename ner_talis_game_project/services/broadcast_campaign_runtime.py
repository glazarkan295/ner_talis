"""Пакетное/плановое исполнение рассылок с наградами и журналом."""
from __future__ import annotations
import json,os,threading,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
from project_paths import resolve_project_path
from services import broadcast_constructor_service as defs

_lock=threading.RLock();LOG_LIMIT=10000
_worker_started=False
def _path():return resolve_project_path(os.getenv("BROADCAST_RUNTIME_PATH","data/broadcast_runtime.json"))
def _load():
 try:
  value=json.loads(_path().read_text(encoding="utf-8"));return value if isinstance(value,dict) else {}
 except (OSError,json.JSONDecodeError):return {}
def _save(value):
 path=_path();path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8");tmp.replace(path)
def _now():return datetime.now(timezone.utc)
def _iso(dt=None):return (dt or _now()).isoformat()
def _parse(v):
 value=datetime.fromisoformat(str(v).replace("Z","+00:00"));return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
def get_run(broadcast_id):
 with _lock:return dict(_load().get(str(broadcast_id)) or {})
def _inventory_has(player,item_id):return any(isinstance(x,dict) and str(x.get("item_id") or x.get("id") or "")==item_id and int(x.get("amount") or 1)>0 for x in player.get("inventory") or [])
def _effect_has(player,effect_id):return any(isinstance(x,dict) and str(x.get("effect_id") or x.get("id") or "")==effect_id for x in player.get("active_effects") or [])
def _matches(player,d):
 mode=str(d.get("audience_mode") or "all");gid=str(player.get("game_id") or player.get("id") or "")
 if gid in {str(x) for x in d.get("exclude_player_ids") or []}:return False
 if mode=="all":return True
 if mode in ("telegram","vk"):return mode==str(player.get("main_platform") or "") or bool((player.get("linked_accounts") or {}).get(mode))
 if mode=="specific":return gid in {str(x) for x in d.get("specific_player_ids") or []}
 if mode=="level":return int(d.get("min_level") or 0)<=int(player.get("level") or 1)<=int(d.get("max_level") or 10**9)
 if mode=="race":return str(player.get("race_id") or "")==str(d.get("race_id") or "")
 if mode=="location":return str(player.get("current_location") or player.get("location_id") or "")==str(d.get("location_id") or "")
 if mode in ("active","inactive"):
  raw=player.get("last_activity") or player.get("updated_at");active=False
  try:active=_now()-datetime.fromisoformat(str(raw).replace("Z","+00:00"))<=timedelta(days=int(d.get("active_days") or 30))
  except (TypeError,ValueError):pass
  return active if mode=="active" else not active
 if mode in ("with_fine","without_fine"):
  from services.fine_service import has_active_fine
  value=has_active_fine(player);return value if mode=="with_fine" else not value
 if mode in ("has_item","without_item"):
  value=_inventory_has(player,str(d.get("item_id") or ""));return value if mode=="has_item" else not value
 if mode in ("has_effect","without_effect"):
  value=_effect_has(player,str(d.get("effect_id") or ""));return value if mode=="has_effect" else not value
 if mode in ("has_achievement","without_achievement"):
  from services.achievement_engine import is_earned
  value=is_earned(player,str(d.get("achievement_id") or ""));return value if mode=="has_achievement" else not value
 if mode=="has_quest":return str(d.get("quest_id") or "") in ((player.get("quests") or {}).get("active") or {})
 if mode in ("reputation","hidden_reputation"):
  from services.reputation_runtime_service import value
  return value(player,str(d.get("reputation_id") or ""))>=float(d.get("reputation_value") or 0)
 if mode=="admins":return bool(player.get("is_admin"))
 return False
def recipients(storage,data):
 rows=storage.list_player_audience_rows() if hasattr(storage,"list_player_audience_rows") else []
 result=[]
 for row in rows:
  gid=str(row.get("game_id") or "");player=storage.get_player_by_game_id(gid)
  if isinstance(player,dict) and _matches(player,data):result.append(gid)
 return result
def preview_recipients(storage,broadcast_id):
 env=defs.store().get(str(broadcast_id))
 if not env:raise ValueError("Рассылка не найдена.")
 ids=recipients(storage,env.get("data") or {});return {"recipients":len(ids),"sample":ids[:20]}
def _message(data):
 parts=[]
 if data.get("title"):parts.append(str(data["title"]))
 if data.get("text"):parts.append(str(data["text"]))
 if data.get("image"):parts.append(f"🖼 {data['image']}")
 for b in data.get("buttons") or []:
  if isinstance(b,dict):parts.append(f"[{b.get('text') or b.get('button_id')}] {b.get('target') or ''}".strip())
 if data.get("rewards"):
  gifts=[f"• {r.get('receive_text') or r.get('object_id') or r.get('item_id') or r.get('type')} ×{r.get('amount') or 1}" for r in data.get("rewards") or [] if isinstance(r,dict)]
  if gifts:parts.append("Вы получили в дар от высших сил:\n"+"\n".join(gifts))
 return "\n\n".join(parts)
def _site_value(value):
 try:
  from services.web_profile import get_site_base_url
  base=get_site_base_url().rstrip("/")
 except Exception:base=""
 return str(value or "").replace("{site_url}",base).replace("{{site_url}}",base)
def _resolve_site_links(data):
 result={**data,"title":_site_value(data.get("title")),"text":_site_value(data.get("text"))}
 buttons=[]
 for row in data.get("buttons") or []:
  if not isinstance(row,dict):continue
  target=row.get("target")
  if row.get("use_active_site"):
   path=str(row.get("site_path") or target or "/site")
   target=_site_value("{site_url}"+('/'+path.lstrip('/')))
  else:target=_site_value(target)
  buttons.append({**row,"target":target})
 result["buttons"]=buttons
 return result
def _visible_buttons(player,data):
 result=[]
 for button in data.get("buttons") or []:
  if not isinstance(button,dict):continue
  condition=button.get("condition")
  if not isinstance(condition,dict) or _matches(player,{**condition,"audience_mode":condition.get("audience_mode") or condition.get("type") or "all"}):result.append(button)
 return result
def _grant(storage,player,reward):
 kind=str(reward.get("type") or "");oid=str(reward.get("object_id") or reward.get("item_id") or "");amount=max(1,int(reward.get("amount") or 1))
 if kind=="item" and oid:
  from copy import deepcopy
  from services.inventory_service import add_inventory_item
  from services.item_registry import build_inventory_item
  item=build_inventory_item(oid,amount,item_id=oid)
  if reward.get("quality"):item["quality"]=reward["quality"]
  if reward.get("item_level") not in (None,""):item["level"]=int(reward["item_level"])
  if reward.get("bind_on_receive") or reward.get("bind"):item["bound_on_receive"]=True;item["binding_type"]=str(reward.get("binding_type") or "character")
  mode=str(reward.get("delivery_mode") or "inventory")
  if mode=="delivery":player.setdefault("broadcast_delivery_inbox",[]).append({"item":item,"amount":amount,"source":"broadcast"})
  else:
   if mode=="reject":
    probe=deepcopy(player)
    if add_inventory_item(probe,item,amount,default_source="broadcast").added<amount:raise ValueError("Инвентарь заполнен, награду рассылки выдать нельзя.")
   result=add_inventory_item(player,item,amount,default_source="broadcast")
   if result.added<amount:raise ValueError("Для награды рассылки не хватило места даже в перегрузе.")
 elif kind=="currency":
  from services.economy_runtime import change,reward_amount
  currency=str(reward.get("currency") or oid or "copper");value=reward_amount("broadcast",amount,{"broadcast_id":reward.get("broadcast_id"),"player_level":player.get("level",1)})
  change(player,currency,value,operation="broadcast_reward",source="broadcast")
 elif kind=="achievement":
  from services.achievement_engine import grant;grant(storage,player,oid,source="broadcast",save=False)
 elif kind in ("reputation",):
  from services.reputation_runtime_service import change;change(player,oid,amount,source="broadcast")
 elif kind=="promo":player.setdefault("received_promocodes",[]).append(oid)
 elif kind=="skill":player.setdefault("unlocked_skills",[]).append(oid) if oid not in player.setdefault("unlocked_skills",[]) else None
 else:
  from services.quest_runtime_service import _grant as grant
  aliases={"experience":"exp","access":"system_flag"};grant(player,{"type":aliases.get(kind,kind),"object_id":oid,"count":amount})
def _deliver_one(storage,broadcast_id,data,gid):
 player=storage.get_player_by_game_id(gid)
 if not isinstance(player,dict):raise ValueError("Игрок не найден.")
 reward_claims=player.setdefault("broadcast_reward_claims",[]);delivery_claims=player.setdefault("broadcast_delivery_claims",[])
 if broadcast_id in delivery_claims:return "duplicate"
 if broadcast_id not in reward_claims:
  for reward in data.get("rewards") or []:
   if isinstance(reward,dict):_grant(storage,player,reward)
  reward_claims.append(broadcast_id);player["broadcast_reward_claims"]=reward_claims[-500:];storage.update_player(player)
 resolved=_resolve_site_links(data);visible=_visible_buttons(player,resolved);message_data={**resolved,"buttons":visible}
 rich={"type":"broadcast","text":_message(message_data),"image":data.get("image"),"buttons":visible,"source":"broadcast_campaign","broadcast_id":broadcast_id,"delivery_key":f"broadcast:{broadcast_id}:{gid}"}
 from services.message_delivery import notify_player
 notify_player(storage,gid,rich["text"],type="broadcast",priority="high" if data.get("broadcast_type") in ("urgent","warning") else "normal",source="broadcast_campaign",delivery_key=f"broadcast:{broadcast_id}:{gid}",fallback_message=rich)
 delivery_claims.append(broadcast_id);player["broadcast_delivery_claims"]=delivery_claims[-500:];storage.update_player(player)
 return "sent"
def start(storage,broadcast_id,*,confirm=False,confirm_rewards=False,test_only=False):
 env=defs.store().get(str(broadcast_id))
 if not env or env.get("status")!=defs.STATUS_PUBLISHED:raise ValueError("Отправить можно только опубликованную рассылку.")
 data=env.get("data") or {}
 if not confirm:raise ValueError("Нужно подтвердить массовую рассылку.")
 if data.get("rewards") and not confirm_rewards:raise ValueError("Для наград требуется второе подтверждение.")
 run_key=f"{broadcast_id}:test" if test_only else str(broadcast_id)
 if not test_only and data.get("test_before_main"):
  test_run=get_run(f"{broadcast_id}:test")
  if test_run.get("status")!="sent":raise ValueError("Перед основной рассылкой выполните успешную тестовую отправку.")
 test_ids=[str(x) for x in data.get("test_player_ids") or []]
 ids=recipients(storage,{**data,"audience_mode":"specific","specific_player_ids":test_ids}) if test_only and test_ids else recipients(storage,{**data,"audience_mode":"admins"}) if test_only else recipients(storage,data)
 if not ids:raise ValueError("Получатели не найдены.")
 schedule=data.get("schedule_at");status="scheduled" if schedule and _parse(schedule)>_now() else "running"
 with _lock:
  all_=_load();previous=all_.get(run_key) or {};history=list(previous.get("history") or [])
  if previous:history.append({k:previous.get(k) for k in ("created_at","finished_at","stopped_at","status","sent","failed","duplicates","logs","test_only")})
  run={"broadcast_id":broadcast_id,"run_key":run_key,"status":status,"created_at":_iso(),"scheduled_at":schedule,"recipients":ids,"cursor":0,"sent":0,"failed":0,"duplicates":0,"logs":[],"history":history[-49:],"test_only":test_only,"next_batch_at":schedule or _iso()}
  all_[run_key]=run;_save(all_)
 if status=="running":run_batch(storage,run_key)
 return get_run(run_key)
def run_batch(storage,broadcast_id):
 with _lock:
  all_=_load();run=all_.get(str(broadcast_id));definition_id=str((run or {}).get("broadcast_id") or str(broadcast_id).split(":test",1)[0]);env=defs.store().get(definition_id)
  if not isinstance(run,dict) or run.get("status") not in ("running","scheduled"):return dict(run or {})
  if not env or env.get("status")!=defs.STATUS_PUBLISHED:run["status"]="stopped";all_[broadcast_id]=run;_save(all_);return dict(run)
  due=_parse(run.get("next_batch_at") or _iso())
  if due>_now():return dict(run)
  run["status"]="running";data=env.get("data") or {};size=int(data.get("batch_size") or len(run["recipients"]) or 1) if data.get("send_in_batches") else len(run["recipients"])
  batch=run["recipients"][run["cursor"]:run["cursor"]+max(1,size)]
  processed=0
  for gid in batch:
   platform="";reward_summary=[]
   try:
    pl=storage.get_player_by_game_id(gid);platform=str((pl or {}).get("main_platform") or "")
    reward_summary=[{"type":r.get("type"),"object_id":r.get("object_id") or r.get("item_id"),"amount":r.get("amount")} for r in data.get("rewards") or [] if isinstance(r,dict)]
    claim_id=str(run.get("run_key") or broadcast_id);result=_deliver_one(storage,claim_id,data,gid);run["duplicates" if result=="duplicate" else "sent"]+=1;error=""
   except Exception as exc:run["failed"]+=1;result="error";error=str(exc)
   run["logs"].append({"game_id":gid,"platform":platform,"status":result,"error":error,"rewards":reward_summary,"at":_iso()})
   processed+=1
   if result=="error" and data.get("stop_on_errors"):
    run["status"]="error";break
  run["logs"]=run["logs"][-LOG_LIMIT:];run["cursor"]+=processed
  if run.get("status")!="error":
   if run["cursor"]>=len(run["recipients"]):run["status"]="sent";run["finished_at"]=_iso()
   else:run["next_batch_at"]=_iso(_now()+timedelta(seconds=max(0,int(data.get("batch_delay_seconds") or 0))))
  all_[broadcast_id]=run;_save(all_);return dict(run)
def stop(broadcast_id):
 with _lock:
  all_=_load();run=all_.get(str(broadcast_id))
  if not isinstance(run,dict):raise ValueError("Запуск рассылки не найден.")
  run["status"]="stopped";run["stopped_at"]=_iso();all_[broadcast_id]=run;_save(all_);return dict(run)
def retry_failed(broadcast_id):
 with _lock:
  all_=_load();run=all_.get(str(broadcast_id))
  if not isinstance(run,dict):raise ValueError("Запуск рассылки не найден.")
  failed=[]
  for row in run.get("logs") or []:
   if row.get("status")=="error" and row.get("game_id") not in failed:failed.append(row["game_id"])
  if not failed:raise ValueError("Ошибочных получателей нет.")
  run.update({"status":"running","recipients":failed,"cursor":0,"failed":0,"sent":0,"duplicates":0,"next_batch_at":_iso()});all_[broadcast_id]=run;_save(all_);return dict(run)
def run_due(storage):
 results=[]
 for bid,run in _load().items():
  if isinstance(run,dict) and run.get("status") in ("scheduled","running"):results.append(run_batch(storage,bid))
 return results
def start_worker(storage,interval_seconds=10):
 global _worker_started
 with _lock:
  if _worker_started:return False
  _worker_started=True
 def loop():
  while True:
   try:run_due(storage)
   except Exception:pass
   time.sleep(max(1,int(interval_seconds)))
 threading.Thread(target=loop,name="broadcast-campaign-worker",daemon=True).start();return True
