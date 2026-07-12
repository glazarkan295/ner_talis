"""Craft result placement policies: inventory, overflow, partial or delivery."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.inventory_service import InventoryAddResult, add_inventory_item, build_inventory_item


def can_place(player: dict[str, Any], item: dict[str, Any], amount: int, mode: str) -> bool:
    if mode in {"delivery", "partial", "overload"}:
        return True
    shadow = deepcopy(player)
    result = add_inventory_item(shadow, item, amount, item_id=str(item.get("item_id") or item.get("id") or ""), default_source="Проверка ремесла")
    if mode == "inventory":
        return result.added_to_regular >= amount
    return result.discarded == 0


def place(player: dict[str, Any], item: dict[str, Any], amount: int, *, mode: str = "overload", source: str = "Ремесло") -> tuple[InventoryAddResult | None, int]:
    mode = mode if mode in {"inventory", "overload", "partial", "delivery", "reject"} else "overload"
    if mode == "delivery":
        player.setdefault("craft_delivery_inbox", []).append({"item": dict(item), "amount": amount, "source": source})
        return None, amount
    result = add_inventory_item(player, item, amount, item_id=str(item.get("item_id") or item.get("id") or ""), default_source=source)
    if result.discarded and mode not in {"partial"}:
        # Never silently destroy a completed craft: route the remainder to delivery.
        delivery_item = dict(item)
        player.setdefault("craft_delivery_inbox", []).append({"item": delivery_item, "amount": result.discarded, "source": source})
        delivered = result.discarded
        result.discarded = 0
        return result, delivered
    return result, 0


def claim(player: dict[str, Any]) -> dict[str, int]:
    queue = player.get("craft_delivery_inbox")
    if not isinstance(queue, list):
        return {"claimed": 0, "remaining": 0}
    kept = []
    claimed = 0
    for row in queue:
        if not isinstance(row, dict):
            continue
        item = dict(row.get("item") or {})
        amount = max(0, int(row.get("amount") or 0))
        result = add_inventory_item(player, item or build_inventory_item("Результат ремесла", amount), amount,
                                    item_id=str(item.get("item_id") or item.get("id") or ""), default_source=str(row.get("source") or "Доставка ремесла"))
        claimed += result.added
        if result.discarded:
            kept.append({**row, "amount": result.discarded})
    player["craft_delivery_inbox"] = kept
    return {"claimed": claimed, "remaining": sum(int(row.get("amount") or 0) for row in kept)}
