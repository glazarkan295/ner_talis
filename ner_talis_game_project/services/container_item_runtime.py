"""Atomic runtime for published container/openable item definitions."""
from __future__ import annotations
from copy import deepcopy
import random
from typing import Any
from services.inventory_service import add_inventory_item, build_inventory_item
from services.item_formula_runtime import definition

def _int(value: Any, default: int = 0) -> int:
    try: return int(float(value))
    except (TypeError, ValueError): return default

def _amount(row, rng):
    fixed=_int(row.get("fixed_amount",row.get("amount")),0)
    if fixed>0:return fixed
    low=max(1,_int(row.get("min_amount",row.get("min_count")),1));high=max(low,_int(row.get("max_amount",row.get("max_count")),low))
    return rng.randint(low,high)

def _roll_rows(data, rng, pity):
    rows=[r for r in (data.get("guaranteed_rewards") or data.get("container_contents") or []) if isinstance(r,dict)]
    result=[r for r in rows if r.get("guaranteed",True) or rng.uniform(0,100)<=float(r.get("chance",100) or 0)]
    groups=data.get("reward_groups") or []
    for group in groups if isinstance(groups,list) else []:
        if not isinstance(group,dict):continue
        entries=[r for r in (group.get("rewards") or group.get("items") or []) if isinstance(r,dict)]
        total=sum(max(0.0,float(r.get("weight",r.get("chance",1)) or 0)) for r in entries)
        if total<=0:continue
        roll=rng.uniform(0,total);upto=0.0;chosen=entries[-1]
        for row in entries:
            upto+=max(0.0,float(row.get("weight",row.get("chance",1)) or 0))
            if roll<=upto:chosen=row;break
        result.append(chosen)
    if pity and not result:
        candidates=rows+[r for g in groups if isinstance(g,dict) for r in (g.get("rewards") or []) if isinstance(r,dict)]
        if candidates:result.append(max(candidates,key=lambda r:float(r.get("rarity_weight",r.get("weight",1)) or 1)))
    return result

def open_container(player: dict[str,Any], inventory_index: int, *, rng=None):
    rng=rng or random.Random();inventory=player.get("inventory")
    if not isinstance(inventory,list) or not 0<=inventory_index<len(inventory):raise ValueError("Контейнер в инвентаре не найден.")
    source=inventory[inventory_index];data=definition(source)
    if not data.get("can_open",str(data.get("item_type") or "") in {"container","openable"}):raise ValueError("Этот предмет нельзя открыть.")
    snapshot=deepcopy(player);source_id=str(source.get("item_id") or source.get("id") or "container");count=max(1,_int(source.get("amount"),1))
    if data.get("consume_on_open",data.get("consumed_on_open",True)):
        if count>1:source["amount"]=count-1
        else:inventory.pop(inventory_index)
    counters=player.setdefault("container_pity",{});opened=_int(counters.get(source_id),0)+1;threshold=max(0,_int(data.get("pity_count"),0));pity=bool(data.get("pity_enabled") and threshold and opened>=threshold)
    granted=[]
    try:
        for row in _roll_rows(data,rng,pity):
            item_id=str(row.get("item_id") or row.get("id") or "").strip()
            if not item_id:continue
            amount=_amount(row,rng);built=build_inventory_item(item_id,amount,item_id=item_id);result=add_inventory_item(player,built,amount,item_id=item_id,default_source=str(data.get("name") or data.get("inventory_name") or "Контейнер"))
            if result.discarded:raise ValueError(str(data.get("inventory_full_text") or "Не хватает места для содержимого контейнера."))
            granted.append({"item_id":item_id,"amount":result.added,"text":row.get("drop_text") or row.get("text")})
    except Exception:
        player.clear();player.update(snapshot);raise
    player.setdefault("container_pity",{})[source_id]=0 if pity else opened
    return {"container_id":source_id,"granted":granted,"pity_triggered":pity}
