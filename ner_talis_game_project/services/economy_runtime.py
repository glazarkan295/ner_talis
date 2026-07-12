"""Published economy wallet, price rules and immutable transaction journal."""
from __future__ import annotations
import json,os,threading,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Any
from project_paths import resolve_project_path
from services.economy_constructor_service import active_profile

_lock=threading.RLock()
def _now():return datetime.now(timezone.utc).isoformat()
def _path()->Path:return resolve_project_path(os.getenv("ECONOMY_TRANSACTION_LOG_PATH","data/economy_transactions.jsonl"))
def _int(v,d=0):
 try:return int(float(v))
 except (TypeError,ValueError):return d
def currency_definition(code:str)->dict[str,Any]:return next((dict(row) for row in active_profile().get("currencies") or [] if isinstance(row,dict) and str(row.get("code") or row.get("currency_id") or "")==str(code)),{})
def wallet_ref(player:dict[str,Any],code:str)->tuple[dict[str,Any],str]:
 if code in {"copper","coins","money"}:return player,"money_copper"
 return player.setdefault("currencies",{}),str(code)
def balance(player:dict[str,Any],code:str="copper")->int:
 bucket,key=wallet_ref(player,code);return _int(bucket.get(key,player.get("money") if bucket is player else 0))
def record(player:dict[str,Any],operation:str,code:str,amount:int,before:int,after:int,*,source:str="",source_id:str="",admin:str="",reason:str="",status:str="success",error:str="")->dict[str,Any]:
 row={"transaction_id":uuid.uuid4().hex,"game_id":str(player.get("game_id") or player.get("id") or ""),"operation":operation,"currency":code,"amount":amount,"before":before,"after":after,"source":source,"source_id":source_id,"admin":admin,"reason":reason,"at":_now(),"status":status,"error":error}
 path=_path();path.parent.mkdir(parents=True,exist_ok=True)
 with _lock:
  with path.open("a",encoding="utf-8") as fh:fh.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
 player.setdefault("economy_transaction_ids",[]).append(row["transaction_id"]);player["economy_transaction_ids"]=player["economy_transaction_ids"][-500:]
 return row
def transactions(limit:int=500,game_id:str="")->list[dict[str,Any]]:
 try:lines=_path().read_text(encoding="utf-8").splitlines()
 except OSError:return []
 rows=[]
 for line in reversed(lines):
  try:row=json.loads(line)
  except json.JSONDecodeError:continue
  if game_id and str(row.get("game_id"))!=str(game_id):continue
  rows.append(row)
  if len(rows)>=max(1,min(limit,5000)):break
 return rows
def _cap_remaining(player:dict[str,Any],code:str,amount:int,before:int)->int:
 if amount<=0:return amount
 now=datetime.now(timezone.utc);allowed=amount;gid=str(player.get("game_id") or player.get("id") or "")
 for row in active_profile().get("money_caps") or []:
  if not isinstance(row,dict) or row.get("enabled") is False:continue
  if str(row.get("currency") or code)!=code:continue
  limit=_int(row.get("amount") or row.get("limit"),0)
  if not limit:continue
  scope=str(row.get("scope") or "player_balance");period=str(row.get("period") or "")
  if scope in {"player","player_balance","balance","wallet"} and not period:allowed=min(allowed,max(0,limit-before));continue
  start=None
  if period in {"day","daily"}:start=now.replace(hour=0,minute=0,second=0,microsecond=0)
  elif period in {"week","weekly"}:start=(now-timedelta(days=now.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
  elif period in {"month","monthly"}:start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
  if start:
   used=0
   for tx in transactions(5000,gid if scope not in {"global","server"} else ""):
    try:at=datetime.fromisoformat(str(tx.get("at") or "").replace("Z","+00:00"))
    except ValueError:continue
    if at<start:continue
    if str(tx.get("currency"))==code and tx.get("status")=="success" and _int(tx.get("amount"))>0:used+=_int(tx.get("amount"))
   allowed=min(allowed,max(0,limit-used))
 return allowed
def change(player:dict[str,Any],code:str,amount:int,*,operation:str,source:str="",source_id:str="",reason:str="")->dict[str,Any]:
 definition=currency_definition(code);bucket,key=wallet_ref(player,code);before=_int(bucket.get(key,player.get("money") if bucket is player else 0));minimum=_int(definition.get("min_value"),0);maximum=_int(definition.get("max_value"),0);allow_negative=bool(definition.get("allow_negative"));requested=int(amount);amount=_cap_remaining(player,code,requested,before);after=before+amount
 if requested>0 and amount<=0:
  record(player,operation,code,requested,before,before,source=source,source_id=source_id,reason=reason,status="error",error="Достигнут лимит денежной массы.");raise ValueError("Достигнут лимит денежной массы.")
 if not allow_negative and after<minimum:
  record(player,operation,code,amount,before,before,source=source,source_id=source_id,reason=reason,status="error",error="Недостаточно средств.");raise ValueError("Недостаточно средств.")
 if maximum and after>maximum:after=maximum
 bucket[key]=after
 if bucket is player and key=="money_copper":player["money"]=after
 return record(player,operation,code,after-before,before,after,source=source,source_id=source_id,reason=reason)
def exchange(player:dict[str,Any],source_code:str,target_code:str,amount:int,*,rate_id:str="")->dict[str,Any]:
 profile=active_profile();rule=next((row for row in profile.get("exchange_rates") or [] if isinstance(row,dict) and (not rate_id or str(row.get("rate_id") or row.get("id"))==rate_id) and str(row.get("source_currency"))==source_code and str(row.get("target_currency"))==target_code and row.get("active",True)),None)
 if not rule:raise ValueError("Курс обмена не опубликован.")
 rate=float(rule.get("rate") or rule.get("coefficient") or 0)
 if rule.get("formula_id"):
  from services.formula_runtime import evaluate
  rate=float(evaluate(rule["formula_id"],{"base_amount":rate,"amount":amount,"player_level":player.get("level",1)},default=rate))
 rate=max(float(rule.get("min_rate") or 0),rate);maximum=float(rule.get("max_rate") or 0);rate=min(rate,maximum) if maximum else rate;commission=max(0,min(100,float(rule.get("commission_percent") or 0)));received=max(0,int(amount*rate*(100-commission)/100));received=commission_adjusted(received,"currency_exchange",player,{"source_currency":source_code,"target_currency":target_code},payout=True)
 change(player,source_code,-amount,operation="exchange_debit",source="exchange_rate",source_id=str(rule.get("rate_id") or rate_id));change(player,target_code,received,operation="exchange_credit",source="exchange_rate",source_id=str(rule.get("rate_id") or rate_id));return {"spent":amount,"received":received,"rate":rate,"text":rule.get("success_text") or f"Обменено: {amount} {source_code} → {received} {target_code}."}
def dynamic_multiplier(context:dict[str,Any])->float:
 result=1.0
 for row in active_profile().get("dynamic_rules") or []:
  if not isinstance(row,dict) or row.get("active") is False:continue
  key=str(row.get("context_key") or row.get("condition") or "");expected=row.get("value")
  if key and key in context and (expected in (None,"") or str(context.get(key))==str(expected)):
   result*=float(row.get("multiplier") or 1)
   if row.get("min") not in (None,""):result=max(float(row["min"]),result)
   if row.get("max") not in (None,""):result=min(float(row["max"]),result)
 return max(0,result)

def reward_amount(source:str,amount:int,context:dict[str,Any]|None=None)->int:
 profile=active_profile();factor=float(profile.get("reward_multiplier") or 1);matched=False
 for row in profile.get("rewards") or []:
  if not isinstance(row,dict) or row.get("enabled") is False:continue
  if str(row.get("source_type") or row.get("source") or row.get("reward_source") or "") not in {"",source}:continue
  matched=True;factor*=float(row.get("multiplier") or 1)
  if row.get("formula_id"):
   from services.formula_runtime import evaluate
   amount=_int(evaluate(row["formula_id"],{"base_amount":amount,**(context or {})},default=amount),amount)
  amount+=_int(row.get("fixed_bonus",row.get("fixed")),0)
  if row.get("min") not in (None,""):amount=max(_int(row["min"]),amount)
  if row.get("max") not in (None,"") and _int(row["max"]):amount=min(_int(row["max"]),amount)
 return max(0,int(amount*factor)) if amount or matched else 0

def _player_effect_ids(player:dict[str,Any]|None)->set[str]:
 result:set[str]=set()
 for row in (player or {}).get("active_effects") or []:
  value=row.get("effect_id") or row.get("id") if isinstance(row,dict) else row
  if value:result.add(str(value))
 return result

def economic_multiplier(applies_to:str,player:dict[str,Any]|None=None)->float:
 result=1.0;active=_player_effect_ids(player)
 for row in active_profile().get("economic_effects") or []:
  if not isinstance(row,dict):continue
  target=str(row.get("applies_to") or "all")
  if target not in {"","all",applies_to}:continue
  effect_id=str(row.get("effect_id") or "")
  if effect_id and effect_id not in active:continue
  influence=str(row.get("influence_type") or "multiplier")
  value=float(row.get("percent") if row.get("percent") not in (None,"") else row.get("value") or 0)
  if influence in {"discount","discount_percent","decrease"}:result*=max(0,(100-value)/100)
  elif influence in {"markup","surcharge","increase","bonus_percent"}:result*=max(0,(100+value)/100)
  elif influence in {"multiplier","coefficient"}:result*=value if value else 1
  if row.get("min") not in (None,""):result=max(float(row["min"]),result)
  if row.get("max") not in (None,""):result=min(float(row["max"]),result)
 return max(0,result)

def commission_adjusted(amount:int,applies_to:str,player:dict[str,Any]|None=None,context:dict[str,Any]|None=None,*,payout:bool=False)->int:
 base=max(0,int(amount));total=base;active=_player_effect_ids(player);ctx={"base_amount":base,"price":base,"player_level":int((player or {}).get("level") or 1),**(context or {})}
 for row in active_profile().get("commissions") or []:
  if not isinstance(row,dict) or row.get("enabled") is False:continue
  targets={part.strip() for part in str(row.get("applies_to") or "").replace(",","\n").splitlines() if part.strip()}
  if targets and applies_to not in targets and "all" not in targets:continue
  effect_id=str(row.get("effect_id") or "")
  if effect_id and effect_id not in active:continue
  reputation_id=str(row.get("reputation_id") or "")
  if reputation_id and reputation_id not in ((player or {}).get("reputations") or {}):continue
  fee=max(0,_int(row.get("fixed_amount"),0)+int(base*float(row.get("percent") or 0)/100))
  if row.get("formula_id"):
   from services.formula_runtime import evaluate
   fee=max(0,_int(evaluate(row["formula_id"],{**ctx,"base_amount":fee},default=fee),fee))
  if row.get("min") not in (None,""):fee=max(_int(row["min"]),fee)
  if row.get("max") not in (None,"") and _int(row["max"]):fee=min(_int(row["max"]),fee)
  total=total-fee if payout else total+fee
 try:
  from services.world_event_runtime import multiplier
  world_factor=multiplier("commission_multiplier",context={"game_id":(player or {}).get("game_id"),**ctx})
  fee=max(0,total-base if not payout else base-total);fee=max(0,int(fee*world_factor));total=base-fee if payout else base+fee
 except Exception:pass
 try:
  from services.reputation_runtime_service import economic_modifiers
  rep=economic_modifiers(player or {});key="delivery_commission_percent" if applies_to in {"delivery","courier"} else "market_commission_percent";fee=max(0,int(base*float(rep.get(key) or 0)/100));total=total-fee if payout else total+fee
 except Exception:pass
 return max(0,total)

def service_price(service_type:str,base:int,player:dict[str,Any]|None=None,context:dict[str,Any]|None=None)->int:
 amount=max(0,int(base));ctx={"base_amount":amount,"price":amount,"player_level":int((player or {}).get("level") or 1),**(context or {})}
 for row in active_profile().get("services") or []:
  if not isinstance(row,dict) or row.get("enabled") is False:continue
  if str(row.get("service_type") or "") not in {"",service_type}:continue
  if any(str(row.get(field) or "") and str(row.get(field))!=str(ctx.get(field) or "") for field in ("npc_id","location_id","sublocation_id","camp_id")):continue
  reputation_id=str(row.get("reputation_id") or "")
  if reputation_id and int(((player or {}).get("reputations") or {}).get(reputation_id) or 0)<_int(row.get("min_reputation"),0):continue
  if row.get("price") not in (None,""):amount=max(0,_int(row.get("price"),amount));ctx["base_amount"]=amount
  if row.get("formula_id"):
   from services.formula_runtime import evaluate
   amount=max(0,_int(evaluate(row["formula_id"],ctx,default=amount),amount))
  break
 amount=max(0,int(amount*economic_multiplier(service_type,player)))
 try:
  from services.reputation_runtime_service import economic_modifiers
  rep=economic_modifiers(player or {});percent=float(rep.get("service_price_percent") or 0)+(float(rep.get("fine_modifier_percent") or 0) if service_type in {"fine","fine_payment"} else 0);amount=max(0,int(amount*(100+percent)/100))
  from services.reputation_runtime_service import price_by_reputation
  amount=price_by_reputation(player or {},amount,{"service_type":service_type,**ctx})
 except Exception:pass
 return commission_adjusted(amount,service_type,player,ctx)

def service_rule(service_type:str,context:dict[str,Any]|None=None)->dict[str,Any]:
 ctx=context or {}
 return next((dict(row) for row in active_profile().get("services") or [] if isinstance(row,dict) and row.get("enabled") is not False
  and str(row.get("service_type") or "") in {"",service_type}
  and not any(str(row.get(field) or "") and str(row.get(field))!=str(ctx.get(field) or "") for field in ("npc_id","location_id","sublocation_id","camp_id"))),{})

def casino_rule(casino_id:str)->dict[str,Any]:
 return next((dict(row) for row in active_profile().get("casinos") or [] if isinstance(row,dict) and row.get("enabled") is not False and str(row.get("casino_id") or "")==str(casino_id)),{})
