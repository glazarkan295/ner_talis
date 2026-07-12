"""Live-runtime опубликованных лагерей конструктора.

Конструкторный лагерь накладывается на существующий внешний camp-flow. Если для
локации нет опубликованной записи, вызывающий код сохраняет legacy-поведение.
"""

from __future__ import annotations

import random
from typing import Any

from services import camp_constructor_service as camps


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _locations(data: dict[str, Any]) -> set[str]:
    values = data.get("locations") or []
    if isinstance(values, str):
        values = [part.strip() for part in values.split(",")]
    result = {str(value).strip() for value in values if str(value).strip()}
    for key in ("parent_location", "location_id"):
        if data.get(key):
            result.add(str(data[key]).strip())
    return result


def is_bound_to_location(camp: dict[str, Any], location_id: str) -> bool:
    return str(location_id or "").strip() in _locations(camp)


def published_for_location(location_id: str, *, purpose: str = "entry") -> dict[str, Any] | None:
    """Выбрать live-лагерь по назначению, default-флагу и приоритету."""
    location_id = str(location_id or "").strip()
    candidates: list[dict[str, Any]] = []
    for envelope in camps.store().list(status=camps.STATUS_PUBLISHED):
        data = envelope.get("data") or {}
        if location_id not in _locations(data):
            continue
        if data.get("active") is False or data.get("hidden_from_players") is True:
            continue
        row = dict(data)
        row["id"] = envelope.get("id")
        candidates.append(row)
    purpose_flag = {
        "death": "death_camp",
        "rest": "rest_camp",
        "battle_exit": "battle_exit_camp",
        "event_exit": "event_exit_camp",
        "teleport": "teleport_camp",
    }.get(purpose)
    candidates.sort(
        key=lambda data: (
            bool(purpose_flag and data.get(purpose_flag)),
            bool(data.get("default_camp")),
            _int(data.get("priority"), 0),
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def published(camp_id: str) -> dict[str, Any] | None:
    envelope = camps.store().get(str(camp_id or ""))
    if not envelope or envelope.get("status") != camps.STATUS_PUBLISHED:
        return None
    data = dict(envelope.get("data") or {})
    data["id"] = envelope.get("id")
    return data


def access_error(player: dict[str, Any], camp: dict[str, Any]) -> str | None:
    level = _int(player.get("level"), 1)
    minimum = _int(camp.get("min_level"), 0)
    maximum = _int(camp.get("max_level"), 0)
    if minimum and level < minimum:
        return str(camp.get("access_denied_text") or f"Лагерь доступен с {minimum} уровня.")
    if maximum and level > maximum:
        return str(camp.get("access_denied_text") or f"Лагерь доступен до {maximum} уровня.")
    required_item = str(camp.get("required_item_id") or "").strip()
    if required_item:
        inventory = player.get("inventory") or []
        if not any(str((row or {}).get("item_id") or (row or {}).get("id") or "") == required_item for row in inventory if isinstance(row, dict)):
            return str(camp.get("missing_item_text") or "Для входа в лагерь нужен особый предмет.")
    inventory=player.get("inventory") or []
    for row in camp.get("items") or []:
        if not isinstance(row,dict) or row.get("active") is False:continue
        role=str(row.get("role") or "")
        if role not in {"entry","entry_required","access"} and not (row.get("required") and str(row.get("used_in_service") or "") in {"entry","access"}):continue
        item_id=str(row.get("item_id") or "");needed=max(1,_int(row.get("amount"),1));have=sum(_int(item.get("amount"),1) for item in inventory if isinstance(item,dict) and str(item.get("item_id") or item.get("id") or "")==item_id)
        if have<needed:return str(row.get("error_text") or camp.get("missing_item_text") or f"Для входа нужен предмет «{item_id}» ×{needed}.")
    for row in camp.get("access_conditions") or []:
        if not isinstance(row, dict) or row.get("active") is False:
            continue
        kind = str(row.get("type") or row.get("condition_type") or "").strip()
        ref = str(row.get("object_id") or row.get("id") or "").strip()
        expected = row.get("value", True)
        actual: Any = None
        if kind == "level":
            actual = level
        elif kind == "race":
            actual = player.get("race_id") or player.get("race")
        elif kind == "item":
            actual = sum(_int(item.get("amount"), 1) for item in player.get("inventory") or [] if isinstance(item, dict) and str(item.get("item_id") or item.get("id") or "") == ref)
        elif kind in {"flag", "unlock", "event", "quest"}:
            source = player.get({"event": "completed_events", "quest": "completed_quests"}.get(kind, "unlocks")) or []
            if kind in {"flag","unlock"}:
                from services.item_access_runtime import has_access
                actual=has_access(player,ref)
            else:actual = ref in source if isinstance(source, (list, set, tuple)) else bool(source.get(ref)) if isinstance(source, dict) else False
        elif kind in {"reputation", "hidden_reputation"}:
            source = player.get("hidden_reputations" if kind == "hidden_reputation" else "reputations") or {}
            actual = source.get(ref, 0) if isinstance(source, dict) else 0
        elif kind == "fine":
            actual = any(str(item.get("type_id") or item.get("id") or "") == ref for item in player.get("fines") or [] if isinstance(item, dict))
        elif kind == "state":
            actual = player.get(ref)
        else:
            continue
        operator = str(row.get("operator") or "eq")
        if operator == "eq":
            passed = actual == expected
        elif operator == "ne":
            passed = actual != expected
        else:
            try:
                passed = {"gte": float(actual) >= float(expected), "lte": float(actual) <= float(expected), "gt": float(actual) > float(expected), "lt": float(actual) < float(expected)}.get(operator, bool(actual))
            except (TypeError, ValueError):
                passed = False
        if not passed:
            return str(row.get("error_text") or camp.get("access_denied_text") or "Условия доступа в лагерь не выполнены.")
    return None


def prepare_rest_payment(player: dict[str, Any], camp: dict[str, Any]) -> str | None:
    """Атомарно проверить и списать цену/предметы, требуемые для отдыха."""
    price = max(0, _int(camp.get("rest_price") or camp.get("price_rest") or camp.get("price"), 0))
    currency = str(camp.get("rest_currency") or camp.get("currency") or "copper").lower()
    rate = {"copper": 1, "money_copper": 1, "silver": 100, "gold": 10_000}.get(currency, 1)
    price_copper = price * rate
    try:
        from services.economy_runtime import service_price
        price_copper = service_price("camp_rest", price_copper, player, {"camp_id": camp.get("camp_id") or camp.get("id")})
    except (ImportError, ValueError): pass
    money_key = "money_copper" if "money_copper" in player else "money"
    if price_copper and _int(player.get(money_key), 0) < price_copper:
        return str(camp.get("not_enough_money_text") or "Недостаточно денег для отдыха.")

    inventory = player.get("inventory") or []
    requirements: list[tuple[str, int, bool]] = []
    required_id = str(camp.get("rest_item_id") or camp.get("required_item_id") or "").strip()
    if required_id:
        requirements.append((required_id, max(1, _int(camp.get("rest_item_amount"), 1)), bool(camp.get("consume_rest_item") or camp.get("consume_required_item"))))
    for row in camp.get("items") or []:
        if not isinstance(row, dict) or row.get("active") is False:
            continue
        role=str(row.get("role") or "")
        if role not in {"rest", "rest_required", "food", "drink", "healing"} and not (row.get("required") and str(row.get("used_in_service") or "") in {"rest","healing"}):
            continue
        item_id = str(row.get("item_id") or "").strip()
        if item_id:
            requirements.append((item_id, max(1, _int(row.get("amount"), 1)), bool(row.get("consumed"))))

    def available(item_id: str) -> int:
        return sum(_int(row.get("amount"), 1) for row in inventory if isinstance(row, dict) and str(row.get("item_id") or row.get("id") or "") == item_id)

    for item_id, amount, _consume in requirements:
        if available(item_id) < amount:
            return str(camp.get("missing_item_text") or f"Для отдыха нужен предмет «{item_id}» ×{amount}.")

    if price_copper:
        before_money=_int(player.get(money_key),0)
        player[money_key] = _int(player.get(money_key), 0) - price_copper
        if money_key == "money_copper" and "money" in player:
            player["money"] = player[money_key]
        try:
            from services.economy_runtime import record
            record(player,"camp_rest","copper",-price_copper,before_money,_int(player.get(money_key),0),source="camp",source_id=str(camp.get("camp_id") or camp.get("id") or ""))
        except (ImportError,OSError):pass
    for item_id, amount, consume in requirements:
        if not consume:
            continue
        left = amount
        for row in inventory:
            if left <= 0 or not isinstance(row, dict) or str(row.get("item_id") or row.get("id") or "") != item_id:
                continue
            take = min(left, max(1, _int(row.get("amount"), 1)))
            row["amount"] = max(0, _int(row.get("amount"), 1) - take)
            left -= take
        player["inventory"] = [row for row in inventory if not isinstance(row, dict) or _int(row.get("amount"), 1) > 0]
        inventory = player["inventory"]
    return None


def rest_seconds(player: dict[str, Any], camp: dict[str, Any], legacy_seconds: int) -> int:
    base = _int(camp.get("base_time") or camp.get("rest_duration"), legacy_seconds)
    energy = _int(player.get("energy"), 0)
    maximum = max(1, _int(player.get("max_energy"), 100))
    if energy <= 0:
        base = _int(camp.get("zero_energy_time"), base)
    elif energy / maximum <= 0.25:
        base = _int(camp.get("low_energy_time"), base)
    minimum = max(1, _int(camp.get("min_time"), 1))
    maximum_time = max(minimum, _int(camp.get("max_time"), max(base, minimum)))
    return min(maximum_time, max(minimum, base))


def apply_recovery(player: dict[str, Any], camp: dict[str, Any]) -> dict[str, int]:
    """Применить flat/percent/full/min/max настройки и вернуть фактические дельты."""
    deltas: dict[str, int] = {}
    aliases = {
        "hp": ("hp", "max_hp"),
        "mana": ("mana", "max_mana"),
        "spirit": ("spirit", "max_spirit"),
        "energy": ("energy", "max_energy"),
        "stamina": ("stamina", "max_stamina"),
    }
    rows = camp.get("recovery") or []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or str(row.get("target") or "") not in aliases:
            continue
        target = str(row["target"])
        current_key, max_key = aliases[target]
        maximum = max(0, _int(player.get(max_key), 0))
        if maximum <= 0:
            continue
        before = max(0, _int(player.get(current_key), 0))
        if row.get("full") or row.get("full_restore"):
            gain = maximum
        else:
            gain = _int(row.get("flat"), 0) + round(maximum * max(0, _int(row.get("percent"), 0)) / 100)
        row_min = max(0, _int(row.get("min"), 0))
        row_max = max(0, _int(row.get("max"), 0))
        gain = max(row_min, gain)
        if row_max:
            gain = min(gain, row_max)
        after = min(maximum, before + max(0, gain))
        player[current_key] = after
        deltas[target] = after - before
    return deltas


def grant_rest_items(player: dict[str, Any], camp: dict[str, Any]) -> list[dict[str, Any]]:
    """Выдать предметы с ролью результата отдыха/награды лагеря."""
    from services.inventory_service import add_inventory_item
    from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item

    issued: list[dict[str, Any]] = []
    for row in camp.get("items") or []:
        if not isinstance(row, dict) or row.get("active") is False or str(row.get("role") or "") not in {"reward", "rest_reward", "give", "issued"}:
            continue
        item_id = str(row.get("item_id") or "").strip()
        definition = get_item_definition_by_id(item_id)
        if not definition:
            continue
        requested = max(1, _int(row.get("amount"), 1))
        result = add_inventory_item(player, registry_item_to_inventory_item(definition, requested), requested, default_source=f"Лагерь: {camp.get('name') or camp.get('id')}")
        issued.append({"item_id": item_id, "requested": requested, "added": result.added, "discarded": result.discarded})
    return issued


def death_camp(location_id: str) -> dict[str, Any] | None:
    camp = published_for_location(location_id, purpose="death")
    if not camp or not (camp.get("use_as_respawn") or camp.get("return_after_death") or camp.get("death_camp")):
        return None
    return camp


def _weekly_rows(camp: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in (camp.get("weekly_limits") or []) if isinstance(row, dict)]
    try:
        from services import world_content_registry as world

        for limit_id in camp.get("weekly_limit_ids") or []:
            envelope = world.get_content(world.KIND_LOCATION_WEEKLY_LIMIT, str(limit_id))
            if envelope and envelope.get("status") == world.STATUS_PUBLISHED:
                row = dict(envelope.get("data") or {})
                row["id"] = envelope.get("id")
                rows.append(row)
    except Exception:
        pass
    return rows


def _rest_limit(camp: dict[str, Any]) -> dict[str, Any] | None:
    for row in _weekly_rows(camp):
        if str(row.get("limit_type") or row.get("type") or row.get("target_type") or "") in {"rest", "camp_rest", "recovery"}:
            return row
    return None


def _typed_limit(camp: dict[str, Any], limit_type: str, object_id: str = "") -> dict[str, Any] | None:
    aliases = {limit_type, f"camp_{limit_type}"}
    for row in _weekly_rows(camp):
        if str(row.get("limit_type") or row.get("type") or row.get("target_type") or "") not in aliases:
            continue
        target = str(row.get("object_id") or row.get("target_id") or "")
        if not target or not object_id or target == object_id:
            return row
    return None


def limit_error(player: dict[str, Any], camp: dict[str, Any], limit_type: str, object_id: str = "") -> str | None:
    row = _typed_limit(camp, limit_type, object_id)
    if not row:
        return None
    maximum = max(0, _int(row.get("max_per_week") or row.get("maximum") or row.get("limit"), 0))
    limit_id = str(row.get("id") or row.get("limit_id") or f"{limit_type}:{object_id}")
    if maximum and _int(_usage_bucket(player, str(camp.get("id") or "")).get(limit_id), 0) >= maximum:
        return str(row.get("exhausted_text") or camp.get("limit_exhausted_text") or "Недельный лимит лагеря исчерпан.")
    return None


def consume_limit(player: dict[str, Any], camp: dict[str, Any], limit_type: str, object_id: str = "") -> None:
    row = _typed_limit(camp, limit_type, object_id)
    if row:
        limit_id = str(row.get("id") or row.get("limit_id") or f"{limit_type}:{object_id}")
        bucket = _usage_bucket(player, str(camp.get("id") or ""))
        bucket[limit_id] = _int(bucket.get(limit_id), 0) + 1


def _usage_bucket(player: dict[str, Any], camp_id: str) -> dict[str, int]:
    from services.location_runtime import current_week_key

    root = player.setdefault("camp_weekly_usage", {})
    week = root.setdefault(current_week_key(), {})
    return week.setdefault(str(camp_id), {})


def rest_limit_error(player: dict[str, Any], camp: dict[str, Any]) -> str | None:
    row = _rest_limit(camp)
    if not row:
        return None
    maximum = max(0, _int(row.get("max_per_week") or row.get("maximum") or row.get("total_stock") or row.get("limit"), 0))
    if not maximum:
        return None
    limit_id = str(row.get("id") or row.get("limit_id") or "rest")
    used = _int(_usage_bucket(player, str(camp.get("id") or "")).get(limit_id), 0)
    if used >= maximum:
        return str(row.get("exhausted_text") or camp.get("limit_exhausted_text") or "Недельный лимит отдыха в этом лагере исчерпан.")
    return None


def consume_rest_limit(player: dict[str, Any], camp: dict[str, Any]) -> None:
    row = _rest_limit(camp)
    if not row:
        return
    limit_id = str(row.get("id") or row.get("limit_id") or "rest")
    bucket = _usage_bucket(player, str(camp.get("id") or ""))
    bucket[limit_id] = _int(bucket.get(limit_id), 0) + 1


def apply_effects(player: dict[str, Any], camp: dict[str, Any], trigger: str, *, rng: random.Random | None = None) -> list[dict[str, Any]]:
    from services.effect_formula_runtime import apply_to_player

    applied: list[dict[str, Any]] = []
    rng=rng or random.Random()
    for row in camp.get("effect_links") or []:
        if not isinstance(row, dict) or row.get("active") is False:
            continue
        row_trigger = str(row.get("trigger") or "passive")
        if row_trigger not in {trigger, "always", "passive"}:
            continue
        if rng.uniform(0,100)>max(0,min(100,float(row.get("chance") or 100))):continue
        protect_id=str(row.get("protection_item_id") or row.get("protection_potion_id") or "")
        if protect_id and any(isinstance(item,dict) and str(item.get("item_id") or item.get("id") or "")==protect_id for item in player.get("inventory") or []):continue
        effect_id = str(row.get("effect_id") or "").strip()
        if not effect_id:
            continue
        payload = apply_to_player(
            player, effect_id, source=f"camp:{camp.get('id')}",
            context={"camp_id": camp.get("id"), "duration_seconds": row.get("duration_seconds") or row.get("duration")},
            rng=rng,
        )
        if payload:
            applied.append(payload)
    return applied


def roll_events(camp: dict[str, Any], trigger: str, *, player:dict[str,Any]|None=None, rng: random.Random | None = None) -> list[str]:
    from services import world_content_registry as world

    rng = rng or random.Random()
    configured = camp.get("camp_events") or camp.get("events") or camp.get("event_ids") or []
    texts: list[str] = []
    for raw in configured:
        row = raw if isinstance(raw, dict) else {"event_id": raw}
        if row.get("active") is False:
            continue
        row_trigger = str(row.get("trigger") or ("on_rest" if row.get("on_rest") else "on_enter" if row.get("on_enter") else "on_rest"))
        if row_trigger != trigger:
            continue
        event_id = str(row.get("event_id") or row.get("id") or "").strip()
        if player is not None:
            if limit_error(player,camp,"event",event_id):continue
            minimum=_int(row.get("min_level"),0)
            if minimum and _int(player.get("level"),1)<minimum:continue
            required=str(row.get("required_item_id") or "")
            if required and not any(isinstance(item,dict) and str(item.get("item_id") or item.get("id") or "")==required for item in player.get("inventory") or []):continue
        envelope = world.get_content(world.KIND_EVENT, event_id) if event_id else None
        if not envelope or envelope.get("status") != world.STATUS_PUBLISHED:
            continue
        event = envelope.get("data") or {}
        chance = float(row.get("chance", event.get("chance", 100)) or 0)
        if rng.uniform(0, 100) <= max(0.0, min(100.0, chance)):
            texts.append(str(row.get("text") or event.get("text") or event.get("name") or event_id))
            if player is not None:consume_limit(player,camp,"event",event_id)
    return texts


def service_rows(camp: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(camp.get("services") or []):
        row = dict(raw) if isinstance(raw, dict) else {"service_id": str(raw), "name": str(raw), "service_type": str(raw)}
        if row.get("active") is False:
            continue
        row.setdefault("service_id", f"service_{index + 1}")
        row.setdefault("name", row.get("label") or row.get("service_type") or row["service_id"])
        rows.append(row)
    return rows


def service_buttons(camp: dict[str, Any]) -> list[str]:
    buttons=[str(row.get("name") or "").strip() for row in service_rows(camp) if str(row.get("name") or "").strip()]
    try:
        from services.tavern_runtime import taverns_for_parent
        buttons.extend(row["name"] for row in taverns_for_parent("camp",str(camp.get("id") or camp.get("camp_id") or "")))
    except Exception: pass
    return buttons


def npc_rows(camp: dict[str, Any],player:dict[str,Any]|None=None) -> list[dict[str, Any]]:
    from services import world_content_registry as world
    rows: list[dict[str, Any]] = []
    configured=list(camp.get("camp_npcs") or [])+list(camp.get("npc_ids") or [])
    for raw in configured:
        if isinstance(raw,dict) and (raw.get("active") is False or raw.get("hidden")):continue
        if isinstance(raw,dict) and player is not None:
            from services.item_access_runtime import has_access
            appear=str(raw.get("appear_condition") or "");disappear=str(raw.get("disappear_condition") or "")
            if appear and not has_access(player,appear):continue
            if disappear and has_access(player,disappear):continue
        npc_id = str((raw.get("npc_id") or raw.get("id")) if isinstance(raw, dict) else raw or "").strip()
        envelope = world.get_content(world.KIND_NPC, npc_id) if npc_id else None
        if envelope and envelope.get("status") == world.STATUS_PUBLISHED:
            data = dict(envelope.get("data") or {})
            data["id"] = npc_id
            if isinstance(raw,dict):data.update({key:value for key,value in raw.items() if value not in (None,"")})
            rows.append(data)
    return rows


def npc_buttons(camp: dict[str, Any],player:dict[str,Any]|None=None) -> list[str]:
    from services.world_runtime import npc_action_label
    return [npc_action_label(row) for row in npc_rows(camp,player)]


def npc_id_for_label(camp: dict[str, Any], label: str,player:dict[str,Any]|None=None) -> str | None:
    from services.world_runtime import npc_action_label
    row = next((row for row in npc_rows(camp,player) if npc_action_label(row) == str(label)), None)
    return str(row.get("id")) if row else None


SPECIAL_SERVICE_ACTIONS = {
    "trade": "Рынок",
    "craft": "Ремесленный квартал",
    "alchemy": "Алхимическая мастерская",
    "cooking": "Готовить",
    "pay_fines": "Оплатить штраф",
    "repair": "👤 Профиль",
    "delivery": "👤 Профиль",
    "storage": "👤 Профиль",
    "quests": "Задания",
    "transition": "",
    "rumors": "",
}


def prepare_service_route(player: dict[str, Any], camp: dict[str, Any], label: str) -> tuple[bool, str | None, str]:
    """Charge a specialised service and return its real shared-runtime action."""
    row = next((item for item in service_rows(camp) if str(item.get("name") or "") == str(label)), None)
    if not row:
        return False, None, ""
    service_type = str(row.get("service_type") or row.get("type") or "")
    if service_type not in SPECIAL_SERVICE_ACTIONS:
        return False, None, ""
    service_id = str(row.get("service_id") or "")
    exhausted = limit_error(player, camp, "service", service_id)
    if exhausted:
        return True, None, exhausted
    action = str(row.get("target_action") or row.get("target") or SPECIAL_SERVICE_ACTIONS[service_type]).strip()
    if not action:
        return True, None, str(row.get("error_text") or "Для услуги не настроено игровое действие.")
    payment_error = prepare_rest_payment(player, {
        "rest_price": row.get("cost"), "rest_currency": row.get("currency"),
        "rest_item_id": row.get("required_item_id") or row.get("required_item"),
        "rest_item_amount": row.get("required_item_amount", 1),
        "consume_rest_item": row.get("consume_required_item"),
        "missing_item_text": row.get("error_text"), "not_enough_money_text": row.get("error_text"),
    })
    if payment_error:
        return True, None, payment_error
    consume_limit(player, camp, "service", service_id)
    return True, action, str(row.get("success_text") or "")


def use_service(player: dict[str, Any], camp: dict[str, Any], label: str) -> tuple[bool, str]:
    row = next((item for item in service_rows(camp) if str(item.get("name") or "") == str(label)), None)
    if not row:
        return False, ""
    service_id = str(row.get("service_id") or "")
    exhausted = limit_error(player, camp, "service", service_id)
    if exhausted:
        return True, exhausted
    service_type = str(row.get("service_type") or row.get("type") or "")
    supported = {"healing", "heal", "restore_hp", "restore_energy", "energy", "restore_mana", "mana", "restore_spirit", "spirit", "remove_effect", "cleanse", "remove_curse", "apply_effect", "blessing", "protection"}
    if service_type not in supported:
        return True, str(row.get("error_text") or "Эта услуга лагеря пока недоступна.")
    payment_error = prepare_rest_payment(player, {
        "rest_price": row.get("cost"), "rest_currency": row.get("currency"),
        "rest_item_id": row.get("required_item_id") or row.get("required_item"),
        "rest_item_amount": row.get("required_item_amount", 1),
        "consume_rest_item": row.get("consume_required_item"),
        "missing_item_text": row.get("error_text"), "not_enough_money_text": row.get("error_text"),
    })
    if payment_error:
        return True, payment_error
    recovery_target = {
        "healing": "hp", "heal": "hp", "restore_hp": "hp",
        "restore_energy": "energy", "energy": "energy",
        "restore_mana": "mana", "mana": "mana",
        "restore_spirit": "spirit", "spirit": "spirit",
    }.get(service_type)
    if recovery_target:
        apply_recovery(player, {"recovery": [{
            "target": recovery_target, "flat": row.get("flat", row.get("amount", 0)),
            "percent": row.get("percent", 0), "full": row.get("full_restore"),
            "min": row.get("min", 0), "max": row.get("max", 0),
        }]})
    elif service_type in {"remove_effect", "cleanse", "remove_curse"}:
        effect_id = str(row.get("effect_id") or "")
        player["active_effects"] = [effect for effect in (player.get("active_effects") or [])
                                    if not isinstance(effect, dict) or (
                                        str(effect.get("effect_id") or effect.get("id") or "") != effect_id
                                        if effect_id else not bool(effect.get("negative") or effect.get("is_curse") or effect.get("effect_type") in {"debuff", "curse"})
                                    )]
    elif service_type in {"apply_effect", "blessing", "protection"} and row.get("effect_id"):
        from services.effect_formula_runtime import apply_to_player
        apply_to_player(player, str(row["effect_id"]), source=f"camp_service:{camp.get('id')}")
    consume_limit(player, camp, "service", service_id)
    return True, str(row.get("success_text") or f"Услуга «{row.get('name')}» оказана.")
