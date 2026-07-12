"""Player-to-player trading pavilion governed by the published economy profile."""
from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from services.derived_stats_service import safe_int
from services.economy_constructor_service import active_profile
from services.inventory_service import add_inventory_item, recalculate_inventory_overflow

_LOCK = threading.RLock()

def _now() -> datetime: return datetime.now(timezone.utc)
def _iso(value: datetime) -> str: return value.isoformat()
def _config() -> dict[str, Any]:
    rows=active_profile().get("pavilion") or []
    if isinstance(rows,dict): return dict(rows)
    return dict(next((row for row in rows if isinstance(row,dict) and row.get("enabled",True)),{}))
def _state(player:dict[str,Any])->dict[str,Any]: return player.setdefault("pavilion",{})
def _parse(value:Any)->datetime|None:
    try:return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError):return None
def _enabled(config:dict[str,Any])->None:
    if not config.get("enabled") or not config.get("player_available",True):raise ValueError("Торговый павильон сейчас недоступен.")
def access_active(player:dict[str,Any],now:datetime|None=None)->bool:
    state=_state(player);expires=_parse(state.get("rent_expires_at"));return bool(state.get("purchased") or (expires and expires>(now or _now())))
def rent(storage:Any,player:dict[str,Any],*,now:datetime|None=None)->dict[str,Any]:
    config=_config();_enabled(config);moment=now or _now();seconds=max(1,safe_int(config.get("rent_seconds"),86400));cost=max(0,safe_int(config.get("rent_cost"),0))
    from services.economy_runtime import change,service_price
    cost=service_price("pavilion_rent",cost,player)
    with _LOCK:
        fresh=storage.get_player_by_game_id(str(player.get("game_id") or player.get("id"))) or player
        change(fresh,"copper",-cost,operation="pavilion_rent",source="pavilion")
        state=_state(fresh);current=_parse(state.get("rent_expires_at"));start=current if current and current>moment else moment;state["rented"]=True;state["rent_expires_at"]=_iso(start+timedelta(seconds=seconds))
        storage.update_player(fresh);player.clear();player.update(fresh)
    return {"cost":cost,"rent_expires_at":state["rent_expires_at"],"text":config.get("rent_text") or "Аренда торгового места оплачена."}
def _inventory_index(player:dict[str,Any],item_id:str,index:int|None)->int|None:
    inventory=player.get("inventory") or []
    if index is not None and 0<=index<len(inventory) and str(inventory[index].get("item_id") or inventory[index].get("id") or "")==item_id:return index
    return next((i for i,row in enumerate(inventory) if isinstance(row,dict) and str(row.get("item_id") or row.get("id") or "")==item_id),None)
def create_listing(storage:Any,player:dict[str,Any],item_id:str,quantity:int,price:int,*,inventory_index:int|None=None,now:datetime|None=None)->dict[str,Any]:
    config=_config();_enabled(config);quantity=max(1,safe_int(quantity,1));price=max(1,safe_int(price,1));moment=now or _now()
    if not access_active(player,moment):raise ValueError(config.get("expire_text") or "Сначала арендуйте торговое место.")
    if safe_int(config.get("price_limit"),0) and price>safe_int(config["price_limit"]):raise ValueError("Цена превышает лимит павильона.")
    with _LOCK:
        fresh=storage.get_player_by_game_id(str(player.get("game_id") or player.get("id"))) or player;state=_state(fresh)
        active=[row for row in state.get("listings") or [] if isinstance(row,dict) and row.get("status")=="active"]
        if safe_int(config.get("item_limit"),0) and len(active)>=safe_int(config["item_limit"]):raise ValueError("Достигнут лимит товаров павильона.")
        index=_inventory_index(fresh,item_id,inventory_index)
        if index is None:raise ValueError("Предмет не найден в инвентаре.")
        item=(fresh.get("inventory") or [])[index];available=max(1,safe_int(item.get("amount"),1))
        if quantity>available:raise ValueError("В стопке недостаточно предметов.")
        if item.get("quest_item") or item.get("bound") or item.get("bound_on_receive") or item.get("can_trade") is False:raise ValueError("Этот предмет нельзя выставить в павильоне.")
        category=str(item.get("category") or item.get("category_ru") or "")
        allowed={str(x) for x in config.get("allowed_categories") or []};forbidden={str(x) for x in config.get("forbidden_categories") or []}
        if (allowed and category not in allowed) or category in forbidden:raise ValueError("Категория предмета запрещена в павильоне.")
        snapshot=deepcopy(item);snapshot["amount"]=quantity
        if quantity==available:(fresh.get("inventory") or []).pop(index)
        else:item["amount"]=available-quantity
        listing={"listing_id":uuid.uuid4().hex,"seller_game_id":str(fresh.get("game_id") or fresh.get("id")),"seller_name":str(fresh.get("name") or "Игрок"),"item_id":item_id,"item":snapshot,"quantity":quantity,"price":price,"status":"active","created_at":_iso(moment)}
        state.setdefault("listings",[]).append(listing);recalculate_inventory_overflow(fresh);storage.update_player(fresh);player.clear();player.update(fresh);return deepcopy(listing)
def listings(storage:Any,*,now:datetime|None=None)->list[dict[str,Any]]:
    moment=now or _now();data=storage.load();result=[]
    for seller in (data.get("players") or {}).values():
        for row in (_state(seller).get("listings") or []):
            if isinstance(row,dict) and row.get("status")=="active":result.append({k:deepcopy(v) for k,v in row.items() if k!="item"}|{"item_name":(row.get("item") or {}).get("name") or row.get("item_id")})
    return sorted(result,key=lambda row:str(row.get("created_at") or ""),reverse=True)
def _find(storage:Any,listing_id:str)->tuple[dict[str,Any],dict[str,Any]]:
    for seller in (storage.load().get("players") or {}).values():
        row=next((x for x in _state(seller).get("listings") or [] if isinstance(x,dict) and str(x.get("listing_id"))==listing_id),None)
        if row:return seller,row
    raise ValueError("Объявление не найдено.")
def buy(storage:Any,buyer:dict[str,Any],listing_id:str)->dict[str,Any]:
    config=_config();_enabled(config)
    with _LOCK:
        seller_hint,row_hint=_find(storage,listing_id);seller=storage.get_player_by_game_id(str(seller_hint.get("game_id") or seller_hint.get("id"))) or seller_hint;buyer_fresh=storage.get_player_by_game_id(str(buyer.get("game_id") or buyer.get("id"))) or buyer
        row=next((x for x in _state(seller).get("listings") or [] if str(x.get("listing_id"))==listing_id),None)
        if not row or row.get("status")!="active":raise ValueError("Товар уже продан или снят.")
        if str(seller.get("game_id") or seller.get("id"))==str(buyer_fresh.get("game_id") or buyer_fresh.get("id")):raise ValueError("Нельзя купить собственный товар.")
        price=max(1,safe_int(row.get("price"),1));from services.economy_runtime import balance,change
        if balance(buyer_fresh,"copper")<price:raise ValueError("Недостаточно средств для покупки.")
        simulated=deepcopy(buyer_fresh);added=add_inventory_item(simulated,deepcopy(row.get("item") or {}),safe_int(row.get("quantity"),1),default_source="pavilion")
        if added.added<safe_int(row.get("quantity"),1):raise ValueError("В инвентаре недостаточно места.")
        commission=max(0,min(100,float(config.get("commission_percent") or 0)));seller_amount=max(0,int(price*(100-commission)/100));buyer_before=deepcopy(buyer_fresh);seller_before=deepcopy(seller)
        try:
            buyer_fresh=simulated;change(buyer_fresh,"copper",-price,operation="pavilion_purchase",source="pavilion",source_id=listing_id);change(seller,"copper",seller_amount,operation="pavilion_sale",source="pavilion",source_id=listing_id)
            row["status"]="sold";row["buyer_game_id"]=str(buyer_fresh.get("game_id") or buyer_fresh.get("id"));row["sold_at"]=_iso(_now());row["commission"]=price-seller_amount
            _state(seller).setdefault("sales_history",[]).append({k:deepcopy(v) for k,v in row.items() if k!="item"});storage.update_player(seller);storage.update_player(buyer_fresh)
        except Exception:
            try:storage.update_player(seller_before);storage.update_player(buyer_before)
            except Exception:pass
            raise
        buyer.clear();buyer.update(buyer_fresh);return {"listing_id":listing_id,"price":price,"seller_received":seller_amount,"commission":price-seller_amount,"text":config.get("purchase_text") or "Покупка завершена."}
def cancel(storage:Any,player:dict[str,Any],listing_id:str)->dict[str,Any]:
    with _LOCK:
        fresh=storage.get_player_by_game_id(str(player.get("game_id") or player.get("id"))) or player;row=next((x for x in _state(fresh).get("listings") or [] if str(x.get("listing_id"))==listing_id),None)
        if not row or row.get("status")!="active":raise ValueError("Активное объявление не найдено.")
        result=add_inventory_item(fresh,deepcopy(row.get("item") or {}),safe_int(row.get("quantity"),1),default_source="pavilion_return")
        if result.added<safe_int(row.get("quantity"),1):raise ValueError("Освободите место в инвентаре перед снятием товара.")
        row["status"]="cancelled";row["cancelled_at"]=_iso(_now());storage.update_player(fresh);player.clear();player.update(fresh);return deepcopy(row)
