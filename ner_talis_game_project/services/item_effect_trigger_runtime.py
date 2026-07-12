"""Dispatch item effect_links for gameplay triggers from the item TZ."""
from __future__ import annotations
import random
from typing import Any
from services.effect_formula_runtime import apply_to_player
from services.item_formula_runtime import definition
from services.effect_runtime_service import apply_to_item
from services.effect_formula_runtime import resolve

ALIASES={"on_receive":"on_receive_item","on_open":"on_open","battle_start":"on_battle_start","each_turn":"on_battle_turn","battle_end":"after_battle","on_sell":"on_sell","on_drop":"on_drop","on_zone":"in_zone","on_fishing":"on_fishing","on_gather":"on_gather"}

def trigger(player:dict[str,Any],item:dict[str,Any],event:str,*,context=None,rng=None):
 rng=rng or random.Random();event=ALIASES.get(str(event),str(event));data=definition(item);added=[]
 for link in data.get("effect_links") or []:
  if not isinstance(link,dict) or str(link.get("trigger") or "passive")!=event:continue
  if rng.uniform(0,100)>float(link.get("chance_percent",link.get("chance",100)) or 0):continue
  effect_id=str(link.get("effect_id") or "").strip()
  if not effect_id:continue
  effect_definition=resolve(effect_id,player=player,context=context) or {}
  if str(effect_definition.get("effect_type") or "").startswith("item_") or effect_definition.get("effect_type")=="item_lifecycle":
   stored=apply_to_item(item,effect_id,amount=link.get("strength"))
   if stored:added.append(stored)
   continue
  payload=apply_to_player(player,effect_id,source=f"item:{item.get('item_id') or item.get('id') or ''}",context=context,rng=rng)
  if payload:
   if link.get("duration_seconds") not in (None,""):payload["duration_seconds"]=max(0,int(float(link["duration_seconds"])))
   if link.get("duration_turns") not in (None,""):payload["duration_turns"]=max(0,int(float(link["duration_turns"])))
   if link.get("strength") not in (None,""):payload["value"]=float(link["strength"])
   added.append(payload)
 return added

def trigger_equipped(player,event,*,context=None,rng=None):
 out=[]
 for item in (player.get("equipment") or {}).values():
  if isinstance(item,dict):out.extend(trigger(player,item,event,context=context,rng=rng))
 return out

def trigger_owned(player,event,*,context=None,rng=None):
 out=[];seen=set()
 for item in [*(player.get("inventory") or []),*(player.get("equipment") or {}).values()]:
  if not isinstance(item,dict):continue
  key=(str(item.get("item_id") or item.get("id") or ""),id(item))
  if key in seen:continue
  seen.add(key);out.extend(trigger(player,item,event,context=context,rng=rng))
 return out
