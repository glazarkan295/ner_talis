"""Access grants produced by published access items."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from services.item_formula_runtime import definition

def grant(player: dict[str,Any], item: dict[str,Any]) -> dict[str,Any]:
 data=definition(item);target=str(data.get("access_target_id") or data.get("access_target") or "").strip();target_type=str(data.get("access_type") or data.get("access_target_type") or "").strip()
 if not data.get("opens_access") or not target:raise ValueError("Предмет не открывает доступ.")
 payload={"granted":True,"source_item_id":str(item.get("item_id") or item.get("id") or ""),"target_type":target_type,"while_inventory":bool(data.get("access_while_inventory")),"while_equipped":bool(data.get("access_while_equipped")),"lose_on_sale":bool(data.get("access_lose_on_sale")),"lose_on_drop":bool(data.get("access_lose_on_drop")),"lose_on_transfer":bool(data.get("access_lose_on_transfer"))}
 if data.get("access_temporary"):
  try:seconds=max(1,int(float(data.get("access_duration_seconds") or 0) or float(data.get("access_duration") or 0)*60))
  except (TypeError,ValueError):seconds=1
  payload["expires_at"]=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()
 player.setdefault("unlocks",{})[target]=payload
 if target_type:player["unlocks"][f"{target_type}:{target}"]=payload
 return {"target":target,**payload}

def has_access(player: dict[str,Any], target: str) -> bool:
 unlocks=player.get("unlocks") or {}
 if isinstance(unlocks,(list,set,tuple)):return str(target) in {str(row) for row in unlocks}
 value=unlocks.get(str(target)) if isinstance(unlocks,dict) else None
 if value is True:return True
 if not isinstance(value,dict) or not value.get("granted"):return False
 source=str(value.get("source_item_id") or "")
 def present(rows):
  values=rows.values() if isinstance(rows,dict) else rows or []
  return any(isinstance(row,dict) and str(row.get("item_id") or row.get("id") or "")==source and int(row.get("amount") or 1)>0 for row in values)
 if value.get("while_inventory") and not present(player.get("inventory")):return False
 if value.get("while_equipped") and not present(player.get("equipped_items") or player.get("equipment")):return False
 expires=value.get("expires_at")
 if not expires:return True
 try:return datetime.fromisoformat(str(expires).replace("Z","+00:00"))>datetime.now(timezone.utc)
 except ValueError:return False

def revoke_for_item_action(player:dict[str,Any],item_id:str,action:str)->int:
 """Revoke authored grants when their source item is sold, dropped or transferred."""
 flag={"sell":"lose_on_sale","drop":"lose_on_drop","transfer":"lose_on_transfer"}.get(str(action))
 if not flag:return 0
 unlocks=player.get("unlocks") if isinstance(player.get("unlocks"),dict) else {};remove=[key for key,value in unlocks.items() if isinstance(value,dict) and str(value.get("source_item_id") or "")==str(item_id) and value.get(flag)]
 for key in remove:unlocks.pop(key,None)
 return len(remove)
