"""Live-агрегатор активных мировых событий и их модификаторов (§29–38)."""
from __future__ import annotations
import json,os,random,threading,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from project_paths import resolve_project_path
from services import world_event_service as events

_lock=threading.RLock();_worker_started=False
MULTIPLIER_KEYS={"event_chance":"event_chance_multiplier","mob_chance":"mob_chance_multiplier","elite_mob_chance":"elite_mob_chance_multiplier","pvp_chance":"pvp_chance_multiplier","pve_chance":"pve_chance_multiplier","drop_chance":"drop_multiplier","resource_amount":"resource_multiplier","buy_price":"buy_price_multiplier","sell_price":"sell_price_multiplier","commission":"commission_multiplier","reward":"reward_multiplier","experience":"exp_multiplier","energy":"energy_multiplier","rest_time":"rest_time_multiplier","craft_time":"craft_time_multiplier","craft_success":"craft_success_multiplier"}
DEFAULTS={v:1.0 for v in MULTIPLIER_KEYS.values()}
def _now():return datetime.now(timezone.utc)
def _dt(v):
 try:
  value=datetime.fromisoformat(str(v).replace("Z","+00:00")) if v else None;return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
 except (TypeError,ValueError):return None
def _repeat_window(data,now):
 typ=str(data.get("repeat_type") or "none");hour=int(data.get("repeat_start_hour") or 0);duration=max(1,int(data.get("repeat_duration_days") or 1));tz=ZoneInfo(str(data.get("timezone") or "UTC"));local=now.astimezone(tz)
 if typ=="daily":start=local.replace(hour=hour,minute=0,second=0,microsecond=0)
 elif typ=="weekly":start=(local-timedelta(days=(local.weekday()-int(data.get("repeat_weekday") or 0))%7)).replace(hour=hour,minute=0,second=0,microsecond=0)
 elif typ=="monthly":
  try:start=local.replace(day=int(data.get("repeat_day_of_month") or 1),hour=hour,minute=0,second=0,microsecond=0)
  except ValueError:return False
 elif typ=="yearly":
  try:start=local.replace(month=int(data.get("repeat_month") or 1),day=int(data.get("repeat_start_day") or 1),hour=hour,minute=0,second=0,microsecond=0)
  except ValueError:return False
 else:return False
 if start>local:start=start-timedelta(days=1 if typ=="daily" else 7 if typ=="weekly" else (365 if typ=="yearly" else 31))
 return start<=local<start+timedelta(days=duration)
def is_effectively_active(env,now=None):
 now=now or _now();data=env.get("data") or {};status=env.get("status")
 if status==events.STATUS_ACTIVE:
  start,end=_dt(data.get("start_date")),_dt(data.get("end_date"));return (not start or now>=start) and (data.get("endless") or not end or now<end)
 if status==events.STATUS_SCHEDULED:
  if data.get("repeat_enabled"):return _repeat_window(data,now)
  start,end=_dt(data.get("start_date")),_dt(data.get("end_date"));return bool(start and now>=start and (not end or now<end))
 return False
def _scope_matches(data,context):
 scope=str(data.get("scope_type") or "world");target=str(data.get("scope_id") or "")
 if scope in ("","world","global") or data.get("all_world"):return True
 if scope in ("player_group","players"):
  allowed={str(x) for x in data.get("player_ids") or data.get("participant_ids") or data.get("scope_ids") or []};groups={str(x) for x in context.get("group_ids") or []}
  return str(context.get("game_id") or "") in allowed or bool(groups & {str(x) for x in data.get("player_group_ids") or []})
 values={"region":context.get("region_id"),"city":context.get("city_id"),"location":context.get("location_id"),"sublocation":context.get("sublocation_id"),"camp":context.get("camp_id"),"market":context.get("market_id"),"npc":context.get("npc_id"),"player":context.get("game_id")}
 if target and str(values.get(scope) or "")!=target:return False
 ids={str(x) for x in data.get(f"{scope}_ids") or data.get("scope_ids") or []};return not ids or str(values.get(scope) or "") in ids
def active_events(*,context=None,now=None):
 context=context or {};result=[]
 for env in events.store().list():
  data=env.get("data") or {}
  if not is_effectively_active(env,now) or not _scope_matches(data,context):continue
  if data.get("start_by_condition") and not _condition_matches(data.get("start_condition"),context):continue
  if data.get("end_by_condition") and _condition_matches(data.get("end_condition"),context):continue
  result.append(env)
 return result
def _condition_matches(condition,context):
 if not condition:return True
 if isinstance(condition,dict):return all(str(context.get(k) or "")==str(v) for k,v in condition.items())
 raw=str(condition);key,sep,value=raw.partition("=");return not sep or str(context.get(key.strip()) or "")==value.strip()
def _value(row,context):
 formula_id=str(row.get("formula_id") or "")
 if formula_id:
  from services.formula_runtime import evaluate
  calculated=evaluate(formula_id,context,default=None)
  if calculated is not None:return float(calculated)
 return float(row.get("value") or 0)
def modifiers(*,context=None,now=None):
 context=context or {}
 result=dict(DEFAULTS);result.update({"craft_success_percent":0.0,"energy_flat":0.0,"location_access":{},"npc_access":{},"active_zones":{},"effects":[]})
 for env in active_events(context=context,now=now):
  data=env.get("data") or {}
  for legacy,target in (("exp_multiplier","exp_multiplier"),("drop_multiplier","drop_multiplier"),("coin_multiplier","reward_multiplier")):
   if data.get(legacy) not in (None,""):result[target]*=max(0,float(data[legacy]))
  for row in data.get("modifiers") or []:
   if not isinstance(row,dict):continue
   if not _condition_matches(row.get("condition"),context):continue
   typ=str(row.get("type") or "");value=_value(row,context);mode=str(row.get("value_mode") or row.get("mode") or "percent")
   target=str(row.get("object_id") or row.get("target_id") or "")
   if target and typ not in ("location_access","npc_access","active_zone","player_effect") and target not in {str(context.get(k) or "") for k in ("object_id","mob_id","event_id","recipe_id","market_id","location_id")}:continue
   key=MULTIPLIER_KEYS.get(typ)
   if key:
    factor=value if mode in ("multiplier","number") else 1+value/100.0;result[key]*=max(0,factor)
   elif typ=="craft_success_percent":result["craft_success_percent"]+=value
   elif typ=="energy_flat":result["energy_flat"]+=value
   elif typ in ("location_access","npc_access"):
    oid=str(row.get("object_id") or row.get("target_id") or "");result[typ][oid]=bool(row.get("enabled",value>0))
   elif typ=="active_zone":result["active_zones"][target]=bool(row.get("enabled",value>0))
   elif typ=="player_effect" and (row.get("object_id") or row.get("effect_id")):result["effects"].append({"effect_id":row.get("object_id") or row.get("effect_id"),"world_event_id":env.get("id")})
 return result
def multiplier(key,*,context=None,now=None):return float(modifiers(context=context,now=now).get(key,1.0) or 0)
def access_allowed(kind,object_id,*,context=None):
 mapping=modifiers(context=context).get(f"{kind}_access",{}) or {};return mapping.get(str(object_id),True)
def zone_active(zone_id,*,context=None):return bool(modifiers(context=context).get("active_zones",{}).get(str(zone_id),False))
def apply_player_effects(player,*,context=None):
 applied=player.setdefault("world_event_effect_claims",[]);active=player.setdefault("active_effects",[]);added=[]
 for row in modifiers(context={**(context or {}),"game_id":player.get("game_id")}).get("effects") or []:
  claim=f"{row['world_event_id']}:{row['effect_id']}"
  if claim not in applied:active.append({"effect_id":row["effect_id"],"source":"world_event","world_event_id":row["world_event_id"]});applied.append(claim);added.append(row["effect_id"])
 return added

def _loot_path():return resolve_project_path(os.getenv("WORLD_EVENT_LOOT_STATE_PATH","data/world_event_loot_state.json"))
def _loot_state():
 try:
  value=json.loads(_loot_path().read_text(encoding="utf-8"));return value if isinstance(value,dict) else {}
 except (OSError,json.JSONDecodeError):return {}
def _save_loot(value):
 path=_loot_path();path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8");tmp.replace(path)
def roll_special_loot(player,source,*,location_id="",object_id="",rng=None):
 rng=rng or random.Random();gid=str(player.get("game_id") or player.get("id") or "");wins=[]
 with _lock:
  state=_loot_state()
  for env in active_events(context={"location_id":location_id}):
   data=env.get("data") or {}
   for idx,row in enumerate(data.get("special_loot") or []):
    if not isinstance(row,dict):continue
    src=str(row.get("source") or "");allowed={source}
    if source in ("battle","mob_drop"):allowed.update(("all_mobs","selected_mobs","battle"))
    if source in ("event","search"):allowed.update(("all_events","selected_events","locations","search"))
    if src not in allowed:continue
    selected={str(x) for x in row.get("object_ids") or row.get("mob_ids") or row.get("event_ids") or []}
    if selected and str(object_id) not in selected:continue
    key=f"{env.get('id')}:{env.get('version')}:{idx}";bucket=state.setdefault(key,{"total":0,"players":{}});used=int(bucket["players"].get(gid,0));plim=int(row.get("per_player_limit") or 0);tlim=int(row.get("total_limit") or 0)
    if (plim and used>=plim) or (tlim and int(bucket["total"])>=tlim):continue
    if rng.random()*100>float(row.get("chance") or 0):continue
    amount=rng.randint(max(1,int(row.get("min_count") or 1)),max(1,int(row.get("max_count") or 1)));amount=min(amount,plim-used if plim else amount,tlim-int(bucket["total"]) if tlim else amount)
    if amount<=0:continue
    item_id=str(row.get("item_id") or "");wins.append({"item_id":item_id,"amount":amount,"world_event_id":env.get("id")});bucket["total"]+=amount;bucket["players"][gid]=used+amount
  _save_loot(state)
 return wins
def sync_and_notify(storage):
 # Состояние уведомлений хранится рядом с loot; отдельный ключ не участвует в лимитах.
 with _lock:
  state=_loot_state();active_rows=active_events();prev=set(state.get("_active_events") or []);current={str(e.get("id")) for e in active_rows};started=current-prev;ended=prev-current;reminders=[];reminder_state=state.setdefault("_reminders",{})
  now_ts=_now().timestamp()
  for env in active_rows:
   data=env.get("data") or {};eid=str(env.get("id"));interval=int(data.get("reminder_interval_seconds") or 0)
   if data.get("send_reminder") and data.get("reminder_message") and interval>0 and now_ts-float(reminder_state.get(eid) or 0)>=interval:reminders.append(eid);reminder_state[eid]=now_ts
  state["_active_events"]=sorted(current);_save_loot(state)
 for event_id,kind in [(x,"start") for x in started]+[(x,"end") for x in ended]+[(x,"reminder") for x in reminders]:
  env=events.store().get(event_id);data=(env or {}).get("data") or {};text=str(data.get(f"{kind}_message") or "")
  enabled=data.get("send_reminder") if kind=="reminder" else data.get(f"send_{kind}_message",True)
  if not text or not enabled:continue
  for row in storage.list_player_audience_rows() if hasattr(storage,"list_player_audience_rows") else []:
   gid=str(row.get("game_id") or "")
   if not data.get("notify_all",True):
    player=storage.get_player_by_game_id(gid)
    if not isinstance(player,dict) or not _scope_matches(data,{"game_id":gid,"location_id":player.get("current_location") or player.get("location_id"),"sublocation_id":player.get("current_sublocation") or player.get("sublocation_id"),"city_id":player.get("current_city") or player.get("city_id"),"region_id":player.get("region_id"),"camp_id":player.get("camp_id"),"group_ids":player.get("group_ids") or []}):continue
   try:
    from services.message_delivery import notify_player
    rich={"type":"world_event","text":text,"image":data.get("image"),"buttons":data.get("buttons") or [],"source":"world_event","delivery_key":f"world-event-{kind}:{event_id}:{gid}"}
    notify_player(storage,gid,text,type="world_event",source="world_event",delivery_key=rich["delivery_key"],fallback_message=rich)
   except Exception:pass
 return {"started":sorted(started),"ended":sorted(ended),"reminders":sorted(reminders)}
def start_worker(storage,interval_seconds=30):
 global _worker_started
 with _lock:
  if _worker_started:return False
  _worker_started=True
 def loop():
  while True:
   try:sync_and_notify(storage)
   except Exception:pass
   time.sleep(max(1,int(interval_seconds)))
 threading.Thread(target=loop,name="world-event-runtime",daemon=True).start();return True
