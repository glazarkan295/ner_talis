"""Completion runtime for published world-constructor events."""

from __future__ import annotations

import random
from typing import Any

from services.derived_stats_service import safe_int


def _amount(row: dict[str, Any], rng: random.Random) -> int:
    fixed = row.get("amount", row.get("fixed_amount"))
    if fixed not in (None, ""):
        return max(0, safe_int(fixed, 0))
    low = max(0, safe_int(row.get("min_amount", row.get("min")), 1))
    high = max(low, safe_int(row.get("max_amount", row.get("max")), low))
    return rng.randint(low, high)


def _remove_item(player: dict[str, Any], item_id: str, amount: int) -> int:
    left = max(0, amount); removed = 0
    for row in player.get("inventory") or []:
        if left <= 0 or not isinstance(row, dict) or str(row.get("item_id") or row.get("id") or "") != item_id:
            continue
        current = max(1, safe_int(row.get("amount"), 1)); take = min(current, left)
        row["amount"] = current - take; removed += take; left -= take
    player["inventory"] = [row for row in player.get("inventory") or [] if not isinstance(row, dict) or safe_int(row.get("amount"), 1) > 0]
    return removed


def complete(player: dict[str, Any], event: dict[str, Any], *, rng: random.Random | None = None) -> dict[str, Any]:
    rng = rng or random.Random()
    event_id = str(event.get("id") or "")
    occurrence = safe_int((player.get("sublocation_event_usage") or {}).get(event_id), 0) or safe_int((player.get("constructor_event_occurrences") or {}).get(event_id), 1)
    claim_id = f"{event_id}:{occurrence}"
    claims = player.setdefault("constructor_event_claims", [])
    if claim_id in claims:
        return {"lines": [], "already_claimed": True}
    lines: list[str] = []
    rewards = [row for row in event.get("rewards") or [] if isinstance(row, dict)]
    if event.get("given_item"):
        rewards.append({"type": "item", "object_id": event.get("given_item"), "amount": event.get("given_amount", 1), "text": event.get("given_item_text")})
    if event.get("effect"):
        rewards.append({"type": "effect", "object_id": event.get("effect")})
    for row in rewards:
        chance = max(0.0, min(100.0, float(row.get("chance", 100) or 0)))
        if rng.uniform(0, 100) > chance:
            continue
        kind = str(row.get("type") or row.get("reward_type") or "item")
        object_id = str(row.get("object_id") or row.get("item_id") or row.get("id") or "")
        amount = _amount(row, rng)
        if kind in {"item", "unique_item"} and object_id and amount:
            from services.inventory_service import add_inventory_item
            from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item
            definition = get_item_definition_by_id(object_id)
            if definition:
                item = registry_item_to_inventory_item(definition, amount)
                if row.get("bind_on_receive"): item["bound_on_receive"] = True
                result = add_inventory_item(player, item, amount, default_source=f"Событие: {event.get('name') or event_id}")
                lines.append(str(row.get("text") or f"Получено: {object_id} ×{result.added}."))
        elif kind in {"currency", "coins", "money"}:
            try:
                from services.economy_runtime import change,reward_amount
                amount=reward_amount("event",amount,{"event_id":event_id});change(player,"copper",amount,operation="event_reward",source="event",source_id=event_id)
            except (ImportError,ValueError):
                key = "money_copper" if "money_copper" in player else "money"; player[key] = safe_int(player.get(key), 0) + amount
                if key=="money_copper":player["money"]=player[key]
            lines.append(str(row.get("text") or f"Монеты: +{amount}."))
        elif kind in {"experience", "exp"}:
            player["experience"] = safe_int(player.get("experience"), 0) + amount; lines.append(str(row.get("text") or f"Опыт: +{amount}."))
        elif kind in {"energy", "hp", "mana", "spirit"}:
            maximum = safe_int(player.get(f"max_{kind}"), safe_int(player.get(kind), 0) + amount); player[kind] = min(maximum, safe_int(player.get(kind), 0) + amount); lines.append(str(row.get("text") or f"{kind}: +{amount}."))
        elif kind in {"stat_points", "attribute_points"}:
            player["free_stat_points"] = safe_int(player.get("free_stat_points"), 0) + amount; lines.append(f"Очки характеристик: +{amount}.")
        elif kind == "skill_points":
            player["free_skill_points"] = safe_int(player.get("free_skill_points"), 0) + amount; lines.append(f"Очки навыков: +{amount}.")
        elif kind in {"reputation", "hidden_reputation"} and object_id:
            key = "hidden_reputations" if kind == "hidden_reputation" else "reputations"; bucket = player.setdefault(key, {}); bucket[object_id] = safe_int(bucket.get(object_id), 0) + amount; lines.append(str(row.get("text") or f"Репутация {object_id}: +{amount}."))
        elif kind in {"effect", "curse"} and object_id:
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player, object_id, source=f"event:{event_id}"); lines.append(str(row.get("text") or f"Получен эффект: {object_id}."))
        elif kind in {"unlock", "location_access"} and object_id:
            player.setdefault("unlocks", {})[object_id] = True; lines.append(str(row.get("text") or f"Открыт доступ: {object_id}."))
        elif kind == "achievement" and object_id:
            from services.achievement_engine import grant
            if grant(None, player, object_id, source=f"event:{event_id}", save=False, notify=False): lines.append(str(row.get("text") or f"Получено достижение: {object_id}."))
        elif kind in {"npc_helper", "npc_ally"} and object_id:
            from services.npc_ally_runtime import grant
            grant(player, object_id, source=f"event:{event_id}")
            lines.append(str(row.get("text") or f"Получен NPC-помощник: {object_id}."))
        elif kind == "fine":
            from services.fine_service import create_raid_fine
            create_raid_fine(player, object_id or f"event:{event_id}"); lines.append(str(row.get("text") or "Получен штраф."))
    losses = [row for row in event.get("losses") or [] if isinstance(row, dict)]
    if event.get("consumed_item"):
        losses.append({"type": "item", "object_id": event.get("consumed_item"), "amount": event.get("consumed_amount", 1)})
    for row in losses:
        kind = str(row.get("type") or row.get("loss_type") or ""); object_id = str(row.get("object_id") or row.get("item_id") or ""); amount = _amount(row, rng)
        if kind == "item" and object_id:
            removed = _remove_item(player, object_id, amount); lines.append(str(row.get("text") or f"Потеряно: {object_id} ×{removed}."))
        elif kind in {"hp", "mana", "spirit", "energy", "experience", "money"}:
            key = "money_copper" if kind == "money" and "money_copper" in player else kind; before = safe_int(player.get(key), 0); loss = round(before * amount / 100) if row.get("percent") else amount
            if kind=="money":
                try:
                    from services.economy_runtime import change
                    change(player,"copper",-min(before,loss),operation="event_loss",source="event",source_id=event_id)
                except (ImportError,ValueError):player[key]=max(0,before-loss)
            else:player[key]=max(0,before-loss)
            lines.append(str(row.get("text") or f"Потеря {kind}: {loss}."))
    route: dict[str, str] = {}
    battle_mob = str(event.get("battle_mob") or "")
    consequences = [row for row in event.get("consequences") or [] if isinstance(row, dict)]
    if event.get("next_event"):
        consequences.append({"type": "next_event", "object_id": event.get("next_event")})
    for row in consequences:
        chance = max(0.0, min(100.0, float(row.get("chance", 100) or 0)))
        if rng.uniform(0, 100) > chance: continue
        kind = str(row.get("type") or row.get("action") or "")
        object_id = str(row.get("object_id") or row.get("target_id") or row.get("target") or "")
        if kind in {"apply_effect", "effect", "curse"} and object_id:
            from services.effect_formula_runtime import apply_to_player
            apply_to_player(player, object_id, source=f"event:{event_id}"); lines.append(str(row.get("text") or f"Получен эффект: {object_id}."))
        elif kind == "remove_effect" and object_id:
            for field in ("active_effects", "active_curses"):
                player[field] = [effect for effect in player.get(field) or [] if not isinstance(effect, dict) or str(effect.get("effect_id") or effect.get("id") or "") != object_id]
            lines.append(str(row.get("text") or f"Эффект снят: {object_id}."))
        elif kind in {"unlock", "open_access"} and object_id:
            player.setdefault("unlocks", {})[object_id] = True; lines.append(str(row.get("text") or f"Открыт доступ: {object_id}."))
        elif kind == "close_access" and object_id:
            unlocks = player.setdefault("unlocks", {})
            if isinstance(unlocks, dict): unlocks.pop(object_id, None)
            elif isinstance(unlocks, list) and object_id in unlocks: unlocks.remove(object_id)
            lines.append(str(row.get("text") or f"Доступ закрыт: {object_id}."))
        elif kind in {"next_event", "open_event"} and object_id: route = {"kind": "event", "id": object_id}
        elif kind == "open_npc" and object_id: route = {"kind": "npc", "id": object_id}
        elif kind == "open_sublocation" and object_id: route = {"kind": "sublocation", "id": object_id}
        elif kind in {"open_location", "goto_location"} and object_id: route = {"kind": "location", "id": object_id}
        elif kind in {"battle", "start_battle"} and object_id: battle_mob = object_id
        elif kind == "quest_progress" and object_id:
            from services.quest_runtime_service import progress
            progress(player, str(row.get("event_type") or "event"), object_id, max(1, _amount(row, rng)))
        elif kind == "achievement" and object_id:
            from services.achievement_engine import grant
            grant(None, player, object_id, source=f"event:{event_id}", save=False, notify=False)
        elif kind == "fine":
            from services.fine_service import create_raid_fine
            create_raid_fine(player, object_id or f"event:{event_id}")
        elif kind in {"message", "chat_message"}:
            message = str(row.get("text") or object_id)
            lines.append(message)
            if row.get("deliver"):
                player.setdefault("pending_bot_messages", []).append({"type": "event", "text": message, "source": f"event:{event_id}"})
    claims.append(claim_id)
    if len(claims) > 500: del claims[:-500]
    try:
        from services.event_campaign_runtime import progress as event_progress
        event_progress(player, "finish_event", event_id, 1)
    except Exception:
        pass
    try:
        from services.quest_runtime_service import trigger_source,progress as quest_progress
        trigger_source(player,"event",event_id);quest_progress(player,"pass_event",event_id,1)
    except Exception:pass
    battle_text = ""
    mob_id = battle_mob
    if mob_id:
        from services.pve_battle_service import create_battle_for_constructor_mob
        _battle, battle_text = create_battle_for_constructor_mob(player, mob_id, rng=rng, location_id=str(event.get("location") or player.get("constructor_location_id") or "event"))
    return {"lines": lines, "already_claimed": False, "battle_text": battle_text, "route": route}
