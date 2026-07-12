"""Lifecycle опубликованных эффектов: expiry, ticks, curses, trauma and zones."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _definition(effect: dict[str, Any]) -> dict[str, Any]:
    effect_id = str(effect.get("effect_id") or effect.get("id") or "")
    try:
        from services.effect_formula_runtime import resolve
        data = resolve(effect_id) or {}
    except Exception:
        data = {}
    return {**data, **effect}


def effect_fields() -> tuple[str, ...]:
    return ("active_effects", "active_curses")


def prune_expired(player: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    from services.derived_stats_service import is_effect_active

    now = now or datetime.now(timezone.utc)
    removed: list[dict[str, Any]] = []
    for field in effect_fields():
        rows = player.get(field)
        if not isinstance(rows, list):
            continue
        kept = []
        for row in rows:
            if isinstance(row, dict) and not is_effect_active(row, now):
                removed.append(row)
            else:
                kept.append(row)
        player[field] = kept
    return removed


def _apply_periodic(player: dict[str, Any], effect: dict[str, Any]) -> int:
    data = _definition(effect)
    etype = str(data.get("effect_type") or "")
    if etype not in {"periodic_damage", "resource_regeneration", "instant_heal", "instant_resource_restore"}:
        return 0
    resource = str(data.get("resource") or "hp")
    current_key = {"hp": "hp", "mana": "mana", "spirit": "spirit", "energy": "energy"}.get(resource, resource)
    max_key = f"max_{current_key}"
    maximum = max(0, _int(player.get(max_key), 0))
    before = _int(player.get(current_key), maximum)
    flat = _int(data.get("tick_value", data.get("value", data.get("flat_damage", data.get("flat_bonus", 0)))), 0)
    percent_raw = data.get("percent_max_hp_damage", data.get("value_percent", 0)) if etype == "periodic_damage" else data.get("percent_max_hp_heal", data.get("value_percent", 0))
    percent = float(percent_raw or 0)
    amount = flat + round(maximum * percent / 100)
    if etype == "periodic_damage":
        after = max(0, before - amount)
    else:
        after = min(maximum, before + amount) if maximum else before + amount
    player[current_key] = after
    return after - before


def advance_turn(player: dict[str, Any], *, turns: int = 1) -> dict[str, Any]:
    """Tick effects once per battle turn and expire duration_turns."""
    turns = max(1, _int(turns, 1))
    ticks: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for field in effect_fields():
        rows = player.get(field)
        if not isinstance(rows, list):
            continue
        kept = []
        for raw in rows:
            if not isinstance(raw, dict):
                kept.append(raw); continue
            row = raw
            data = _definition(row)
            period = max(1, _int(data.get("tick_period_turns") or data.get("period_turns"), 1))
            elapsed = _int(row.get("elapsed_turns"), 0) + turns
            while elapsed >= period:
                delta = _apply_periodic(player, row)
                ticks.append({"effect_id": row.get("effect_id") or row.get("id"), "delta": delta})
                elapsed -= period
            row["elapsed_turns"] = elapsed
            duration = row.get("remaining_turns", row.get("duration_turns", data.get("duration_turns")))
            if duration not in (None, ""):
                left = _int(duration) - turns
                row["remaining_turns"] = left
                if left <= 0:
                    removed.append(row); continue
            kept.append(row)
        player[field] = kept
    return {"ticks": ticks, "removed": removed}


def advance_time(player: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Prune seconds-duration effects and catch up periodic second ticks."""
    now = now or datetime.now(timezone.utc)
    removed = prune_expired(player, now=now)
    ticks: list[dict[str, Any]] = []
    for field in effect_fields():
        for row in player.get(field) or []:
            if not isinstance(row, dict):
                continue
            data = _definition(row)
            period = _int(data.get("tick_period_seconds") or data.get("period_seconds"), 0)
            if period <= 0:
                continue
            raw_last = row.get("last_tick_at") or row.get("applied_at")
            try:
                last = datetime.fromisoformat(str(raw_last).replace("Z", "+00:00")) if raw_last else now
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
            except ValueError:
                last = now
            due = max(0, int((now - last).total_seconds()) // period)
            # A damaged timestamp must not create an unbounded catch-up loop.
            for _ in range(min(due, 1000)):
                delta = _apply_periodic(player, row)
                ticks.append({"effect_id": row.get("effect_id") or row.get("id"), "delta": delta})
            if due:
                row["last_tick_at"] = now.isoformat()
    return {"ticks": ticks, "removed": removed}


def blocked_slots(player: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in effect_fields():
        for raw in player.get(field) or []:
            if not isinstance(raw, dict):
                continue
            data = _definition(raw)
            if data.get("effect_category") != "trauma" and data.get("effect_type") not in {"slot_block", "action_block"}:
                continue
            slots = data.get("blocked_slots") or data.get("slots") or ([data.get("slot")] if data.get("slot") else [])
            if isinstance(slots, str):
                slots = [slot.strip() for slot in slots.split(",") if slot.strip()]
            for slot in slots:
                if slot:
                    result[str(slot)] = str(data.get("player_text") or data.get("player_name") or data.get("effect_name") or "Слот заблокирован травмой.")
    return result


def combat_flags(player:dict[str,Any])->dict[str,Any]:
    """Сводит authored control/defence mechanics активных эффектов для боя."""
    result={"skip_turn":False,"confusion_chance":0.0,"panic_chance":0.0,"disable_critical":False,"invulnerable":False,"reflect_physical_percent":0.0,"reflect_magic_percent":0.0,"berserk_percent":0.0,"trigger_text":""}
    for field in effect_fields():
        for raw in player.get(field) or []:
            if not isinstance(raw,dict):continue
            data=_definition(raw);etype=str(data.get("effect_type") or "");control=str(data.get("control_kind") or "");chance=float(data.get("trigger_chance") or data.get("chance") or 100)
            if etype=="control_effect":
                if control=="stun":result["skip_turn"]=True
                elif control in {"confusion","mind_control"}:result["confusion_chance"]=max(result["confusion_chance"],chance)
                elif control=="panic":result["panic_chance"]=max(result["panic_chance"],float(data.get("escape_chance") or chance))
                elif control in {"doomed_luck","no_critical"}:result["disable_critical"]=True
            if etype in {"invulnerability","invulnerability_effect"} or data.get("blocks_all_damage"):result["invulnerable"]=True
            if etype=="damage_response":
                key="reflect_magic_percent" if str(data.get("damage_type") or "physical")=="magic" else "reflect_physical_percent";result[key]=max(result[key],float(data.get("reflect_percent") or data.get("value_percent") or 0))
            if etype=="special_combat" and str(data.get("special_kind") or "")=="berserk":result["berserk_percent"]=max(result["berserk_percent"],float(data.get("value_percent") or data.get("damage_percent") or 0))
            if not result["trigger_text"]:result["trigger_text"]=str(data.get("trigger_text") or data.get("player_text") or "")
    return result


def zone_effect_ids(location_id: str, *, city_id: str = "", region_id: str = "") -> list[str]:
    from services import world_content_registry as world

    ids: list[str] = []
    for envelope in world.list_content(world.KIND_LOCATION_ZONE, status=world.STATUS_PUBLISHED):
        data = envelope.get("data") or {}
        if str(data.get("location") or "") not in {"", str(location_id)}:
            continue
        if data.get("city_id") and str(data.get("city_id")) != str(city_id):
            continue
        if data.get("region_id") and str(data.get("region_id")) != str(region_id):
            continue
        for row in data.get("effects") or []:
            effect_id = str((row or {}).get("effect_id") if isinstance(row, dict) else row or "")
            if effect_id:
                ids.append(effect_id)
        direct = str(data.get("effect_id") or "")
        if direct:
            ids.append(direct)
    return list(dict.fromkeys(ids))


def sync_zone_effects(player: dict[str, Any], location_id: str, *, city_id: str = "", region_id: str = "") -> bool:
    from services.effect_formula_runtime import apply_to_player

    desired = set(zone_effect_ids(location_id, city_id=city_id, region_id=region_id))
    before = sum(len(player.get(field) or []) for field in effect_fields())
    present: set[str] = set()
    for field in effect_fields():
        effects = player.setdefault(field, [])
        effects[:] = [row for row in effects if not isinstance(row, dict) or row.get("source") != "zone" or str(row.get("effect_id") or "") in desired]
        present.update(str(row.get("effect_id") or "") for row in effects if isinstance(row, dict) and row.get("source") == "zone")
    for effect_id in desired - present:
        apply_to_player(player, effect_id, source="zone", context={"location_id": location_id})
    after = sum(len(player.get(field) or []) for field in effect_fields())
    return after != before or desired != present


def apply_to_item(item: dict[str, Any], effect_id: str, *, amount: int | float | None = None) -> dict[str, Any] | None:
    """Apply accumulator/storage and lifecycle effects directly to an item instance."""
    try:
        from services.effect_formula_runtime import resolve
        data = resolve(effect_id) or {}
    except Exception:
        data = {}
    etype = str(data.get("effect_type") or "")
    if etype not in {"item_charge_effect", "item_durability_effect", "item_binding_effect", "item_lifecycle"}:
        return None
    if etype == "item_charge_effect":
        field = str(data.get("storage_field") or data.get("value_field") or "charges")
        maximum = max(0, _int(data.get("storage_max") or data.get("max_value") or data.get("max_charges") or item.get("max_charges"), 0))
    elif etype == "item_durability_effect":
        field = str(data.get("storage_field") or "durability")
        maximum = max(0, _int(data.get("storage_max") or data.get("max_value") or item.get("max_durability"), 0))
    elif etype == "item_binding_effect":
        item["bound"] = bool(data.get("bound", True))
        item["binding_type"] = data.get("binding_type") or "character"
        return {"effect_id": effect_id, "field": "bound", "value": item["bound"]}
    else:
        field = str(data.get("storage_field") or "stored_value")
        maximum = max(0, _int(data.get("storage_max") or data.get("max_value"), 0))
    delta = float(amount if amount is not None else data.get("value", data.get("flat_bonus", 0)) or 0)
    current = float(item.get(field) or 0)
    value = max(float(data.get("storage_min") or data.get("min_value") or 0), current + delta)
    if maximum:
        value = min(maximum, value)
    item[field] = int(value) if value.is_integer() else value
    item.setdefault("stored_effect_values", {})[effect_id] = item[field]
    return {"effect_id": effect_id, "field": field, "value": item[field], "delta": item[field] - current}
