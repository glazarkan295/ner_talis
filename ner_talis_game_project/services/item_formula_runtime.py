"""Formula-backed calculations shared by item gameplay systems."""

from __future__ import annotations

from typing import Any

from services.formula_runtime import evaluate, numeric_context
from services.item_registry import get_item_definition_by_id


def definition(item: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, dict):
        item_id = str(item.get("item_id") or item.get("id") or "")
        base = dict(get_item_definition_by_id(item_id) or {})
        base.update(item)
        return base
    return dict(get_item_definition_by_id(str(item or "")) or {})


def use_result(item: str | dict[str, Any], player: dict[str, Any], base_amount: Any = 0,
               *, context: dict[str, Any] | None = None) -> float:
    data = definition(item)
    values = numeric_context({"base_amount": base_amount, "item_level": data.get("item_level", 1),
                              "quality": data.get("quality_value", 0), **(context or {})}, player=player)
    return float(evaluate(data.get("use_formula_id"), values, default=base_amount) or 0)


def drop_chance(item_id: str, base_chance: Any, *, player: dict[str, Any] | None = None,
                context: dict[str, Any] | None = None) -> float:
    data = definition(item_id)
    values = numeric_context({"base_chance": base_chance, "base_amount": base_chance,
                              "item_level": data.get("item_level", 1),
                              "quality": data.get("quality_value", 0), **(context or {})}, player=player)
    value = evaluate(data.get("drop_chance_formula_id"), values, default=base_chance)
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return max(0.0, min(100.0, float(base_chance or 0)))


def repair_cost(item: str | dict[str, Any], player: dict[str, Any] | None = None,
                *, current_durability: Any = None) -> int:
    data = definition(item)
    maximum = max(0, int(float(data.get("max_durability") or data.get("durability_max") or 0)))
    current = maximum if current_durability is None else max(0, int(float(current_durability or 0)))
    missing = max(0, maximum - current)
    base = int(float(data.get("repair_base_cost") or data.get("price_sell") or data.get("sell_price_copper") or 0))
    values = numeric_context({"base_amount": base, "price": base, "item_level": data.get("item_level", 1),
                              "difficulty": missing, "multiplier": (missing / maximum if maximum else 0)}, player=player)
    result=max(0, int(float(evaluate(data.get("repair_cost_formula_id"), values, default=base) or 0)))
    try:
        from services.economy_runtime import service_price
        return service_price("repair",result,player,{"item_id":data.get("item_id") or data.get("id"),"missing_durability":missing})
    except (ImportError,ValueError):return result


def repair_inventory_item(player: dict[str, Any], item: dict[str, Any]) -> dict[str, int]:
    data = definition(item)
    if not data.get("can_be_repaired", data.get("has_durability", False)):
        raise ValueError("Этот предмет нельзя отремонтировать.")
    maximum = max(0, int(float(data.get("max_durability") or item.get("max_durability") or item.get("durability_max") or 0)))
    current_key = "current_durability" if "current_durability" in item else "durability"
    current = max(0, int(float(item.get(current_key, maximum) or 0)))
    if maximum <= 0:
        raise ValueError("Для предмета не задана максимальная прочность.")
    if current >= maximum:
        raise ValueError("Предмет уже имеет максимальную прочность.")
    cost = repair_cost(data, player, current_durability=current)
    money_key = "money_copper" if "money_copper" in player else "money"
    money = max(0, int(player.get(money_key) or 0))
    if money < cost:
        raise ValueError("Недостаточно монет для ремонта.")
    player[money_key] = money - cost
    if money_key == "money_copper" and "money" in player:
        player["money"] = player[money_key]
    try:
        from services.economy_runtime import record
        record(player,"repair","copper",-cost,money,int(player.get(money_key) or 0),source="repair",source_id=str(data.get("item_id") or data.get("id") or ""))
    except (ImportError,OSError):pass
    item[current_key] = maximum
    item["max_durability"] = maximum
    return {"cost": cost, "before": current, "after": maximum}
