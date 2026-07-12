"""Published constructor runtime for upgrade, enchant, purify and disassembly."""

from __future__ import annotations

import random
from typing import Any

from services.inventory_service import add_inventory_item, build_inventory_item, remove_empty_stacks_and_recalculate
from services.derived_stats_service import safe_int


def _service(operation: str):
    if operation == "upgrade":
        from services import upgrade_constructor_service as service
    elif operation in {"enchant", "purify"}:
        from services import enchant_constructor_service as service
    elif operation == "disassemble":
        from services import disassemble_constructor_service as service
    elif operation == "repair":
        from services import repair_constructor_service as service
    else:
        raise ValueError("Неизвестная ремесленная операция.")
    return service


def published_rule(operation: str, rule_id: str) -> dict[str, Any]:
    row = _service(operation).store().get(rule_id)
    if not row or row.get("status") != "published":
        raise ValueError("Ремесленная операция не опубликована или не найдена.")
    return dict(row.get("data") or {})


def available_rules(item: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for operation in ("upgrade", "enchant", "purify", "disassemble", "repair"):
        service = _service(operation)
        for row in service.store().list(status="published"):
            data = row.get("data") or {}
            if operation == "purify" and not data.get("clear_enchant"):
                continue
            if operation == "enchant" and data.get("clear_enchant"):
                continue
            if operation == "disassemble" and data.get("source_item_id") and str(data.get("source_item_id")) != _item_id(item):
                continue
            if operation == "repair" and safe_int(item.get("durability", item.get("current_durability")), 0) >= safe_int(item.get("max_durability", item.get("durability_max")), 0):
                continue
            target_type = str(data.get("target_item_type") or "")
            if target_type and target_type not in {str(item.get("type") or ""), str(item.get("category") or ""), str(item.get("item_type") or "")}:
                continue
            result.append({"operation": operation, "rule_id": row.get("id"), "name": data.get("name") or row.get("id")})
    return result


def _item_id(item: dict[str, Any]) -> str:
    return str(item.get("item_id") or item.get("id") or "")


def _consume(player: dict[str, Any], item_id: str, amount: int = 1) -> None:
    left = max(0, amount)
    inventory = player.setdefault("inventory", [])
    if sum(safe_int(row.get("amount"), 1) for row in inventory if isinstance(row, dict) and _item_id(row) == item_id) < left:
        raise ValueError(f"Не хватает материала «{item_id}».")
    for row in list(inventory):
        if not isinstance(row, dict) or _item_id(row) != item_id:
            continue
        take = min(left, safe_int(row.get("amount"), 1))
        row["amount"] = safe_int(row.get("amount"), 1) - take
        left -= take
        if row["amount"] <= 0:
            inventory.remove(row)
        if left <= 0:
            break
    remove_empty_stacks_and_recalculate(player)


def _consume_materials(player: dict[str, Any], materials: list[Any]) -> None:
    for raw in materials:
        if isinstance(raw, str):
            _consume(player, raw, 1)
        elif isinstance(raw, dict):
            _consume(player, str(raw.get("item_id") or ""), max(1, safe_int(raw.get("amount"), 1)))

def _validate_materials(player:dict[str,Any],materials:list[Any])->None:
    required:dict[str,int]={}
    for raw in materials:
        item_id=str(raw if isinstance(raw,str) else raw.get("item_id") or "") if isinstance(raw,(str,dict)) else ""
        amount=1 if isinstance(raw,str) else max(1,safe_int(raw.get("amount"),1)) if isinstance(raw,dict) else 0
        if item_id:required[item_id]=required.get(item_id,0)+amount
    for item_id,amount in required.items():
        available=sum(safe_int(row.get("amount"),1) for row in player.get("inventory") or [] if isinstance(row,dict) and _item_id(row)==item_id)
        if available<amount:raise ValueError(f"Не хватает материала «{item_id}».")

def _record_achievement(player:dict[str,Any],operation:str,item_id:str)->None:
    event={"disassemble":"disassemble_item","repair":"repair_item","upgrade":"upgrade_item","enchant":"enchant_item","purify":"remove_curse"}.get(operation)
    if event:
        try:
            from services.achievement_engine import record_game_event
            record_game_event(player,event,1,item_id)
        except Exception:pass


def apply(player: dict[str, Any], operation: str, rule_id: str, inventory_index: int, *, rng: random.Random | Any = random) -> dict[str, Any]:
    rule = published_rule(operation, rule_id)
    inventory = player.setdefault("inventory", [])
    if inventory_index < 0 or inventory_index >= len(inventory) or not isinstance(inventory[inventory_index], dict):
        raise ValueError("Целевой предмет не найден в инвентаре.")
    item = inventory[inventory_index]
    target_item_id = _item_id(item)
    target_type = str(rule.get("target_item_type") or "")
    if target_type and target_type not in {str(item.get("type") or ""), str(item.get("category") or ""), str(item.get("item_type") or "")}:
        raise ValueError("Предмет не подходит для этой операции.")
    if operation == "disassemble":
        source = str(rule.get("source_item_id") or "")
        if source and _item_id(item) != source:
            raise ValueError("Этот предмет нельзя разобрать по выбранному правилу.")
    materials=list(rule.get("materials") or []);_validate_materials(player,materials)
    service_type={"upgrade":"upgrade","enchant":"enchant","purify":"purification","disassemble":"disassembly","repair":"repair"}.get(operation,operation)
    try:
        from services.economy_runtime import service_price,change
        price=service_price(service_type,safe_int(rule.get("price"),0),player,{"item_id":target_item_id})
        change(player,"copper",-price,operation=f"{service_type}_service",source=operation,source_id=rule_id)
    except ValueError as exc:
        raise ValueError("Недостаточно монет для ремесленной услуги.") from exc
    except ImportError:pass
    _consume_materials(player, materials)
    inventory = player.setdefault("inventory", [])
    item = next((row for row in inventory if isinstance(row, dict) and _item_id(row) == target_item_id), item)
    base_chance = safe_int(rule.get("success_chance", rule.get("output_chance", 100)), 100)
    formula_field = {"upgrade": "upgrade_formula_id", "enchant": "enchant_formula_id", "purify": "purify_formula_id"}.get(operation, "success_formula_id")
    from services.formula_runtime import evaluate, numeric_context
    context = numeric_context({"item_level": item.get("item_level", item.get("level", 1)), "base_amount": base_chance}, player=player)
    chance = max(0, min(100, safe_int(evaluate(rule.get(formula_field) or rule.get("success_formula_id"), context, default=base_chance), base_chance)))
    if rng.randint(1, 100) > chance:
        base_break = safe_int(rule.get("break_risk"), 0)
        break_risk = safe_int(evaluate(rule.get("break_risk_formula_id"), context | {"base_amount": base_break}, default=base_break), base_break)
        if rng.randint(1, 100) <= max(0, min(100, break_risk)):
            item["durability"] = 0
        return {"ok": False, "message": str(rule.get("fail_text") or "Ремесленная операция завершилась неудачей."), "rule_id": rule_id}
    if operation == "disassemble":
        if not any(row is item for row in inventory):
            raise ValueError("Целевой предмет был списан как материал операции.")
        inventory.remove(item)
        outputs = []
        for raw in rule.get("outputs") or []:
            row = {"item_id": raw, "amount": 1, "chance": rule.get("output_chance", 100)} if isinstance(raw, str) else dict(raw)
            oid = str(row.get("item_id") or "")
            if oid and rng.randint(1, 100) <= max(0, min(100, safe_int(row.get("chance"), 100))):
                amount = max(1, safe_int(row.get("amount"), 1))
                add_inventory_item(player, build_inventory_item(oid, amount, item_id=oid), amount, item_id=oid, default_source="Разборка")
                outputs.append({"item_id": oid, "amount": amount})
        remove_empty_stacks_and_recalculate(player)
        _record_achievement(player,operation,target_item_id)
        return {"ok": True, "message": str(rule.get("success_text") or "Предмет разобран."), "outputs": outputs, "rule_id": rule_id}
    if operation == "repair":
        maximum = max(0, safe_int(item.get("max_durability", item.get("durability_max")), 0))
        if maximum <= 0:
            raise ValueError("У предмета нет настраиваемой прочности.")
        current = max(0, safe_int(item.get("durability", item.get("current_durability")), 0))
        base_percent = max(1, safe_int(rule.get("repair_percent"), 100))
        percent = max(1, safe_int(evaluate(rule.get("repair_formula_id"), context | {"base_amount": base_percent}, default=base_percent), base_percent))
        restored = max(1, round(maximum * percent / 100))
        item["durability"] = min(maximum, current + restored)
        item["current_durability"] = item["durability"]
    elif operation == "upgrade":
        utype = str(rule.get("upgrade_type") or "raise_level")
        if utype == "raise_level":
            item["item_level"] = safe_int(item.get("item_level", item.get("level", 1)), 1) + max(1, safe_int(rule.get("level_increase"), 1))
        elif utype == "raise_quality":
            qualities = ["common", "uncommon", "rare", "epic", "legendary", "mythic", "celestial", "divine"]
            current = str(item.get("quality") or "common")
            item["quality"] = qualities[min(len(qualities) - 1, (qualities.index(current) if current in qualities else 0) + 1)]
        effect = str(rule.get("result_effect") or "")
        if effect:
            item.setdefault("effect_ids", []).append(effect)
    else:
        effects = item.setdefault("effect_ids", [])
        effect = str(rule.get("enchant_effect") or "")
        if operation == "purify" or rule.get("clear_enchant"):
            remove_id = str(rule.get("remove_effect_id") or effect or "")
            item["effect_ids"] = [eid for eid in effects if not remove_id or str(eid) != remove_id]
            item["cursed"] = False
        elif effect and effect not in effects:
            effects.append(effect)
    _record_achievement(player,operation,target_item_id)
    return {"ok": True, "message": str(rule.get("success_text") or "Ремесленная операция выполнена."), "item": item, "rule_id": rule_id}
