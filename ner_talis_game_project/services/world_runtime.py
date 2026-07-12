"""Runtime-чтение опубликованного контента «Конструктора мира» (ТЗ §17).

Единая точка, через которую ИГРА читает data-driven контент из реестра —
только статус ``published``. Бот по нажатию кнопки определяет локацию, берёт её
сцену (описание + кнопки + переходы + события), а при бое — моба и его дроп.

Слой только читает реестр (world_content_registry); он НЕ переписывает игровые
циклы. Подключение к конкретным хендлерам (city/боя) — отдельный аккуратный шаг.
"""

from __future__ import annotations

import random
from datetime import datetime
from copy import deepcopy
from typing import Any

from services import world_content_registry as registry

_PUBLISHED = registry.STATUS_PUBLISHED


def _published(kind: str) -> list[dict[str, Any]]:
    return registry.list_content(kind, status=_PUBLISHED)


def _data(envelope: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(envelope, dict):
        return None
    data = dict(envelope.get("data") or {})
    data["id"] = envelope.get("id")
    return data


def get_published(kind: str, content_id: str) -> dict[str, Any] | None:
    envelope = registry.get_content(kind, content_id)
    if envelope is None or envelope.get("status") != _PUBLISHED:
        return None
    return _data(envelope)


def campaign_content_allowed(player: dict[str, Any] | None, kind: str, content_id: str) -> bool:
    """Temporary campaign content is visible only to active participants."""
    field = {registry.KIND_LOCATION: "locations", registry.KIND_EVENT: "location_events", registry.KIND_MOB: "mobs", registry.KIND_NPC: "npcs", registry.KIND_BUTTON: "buttons"}.get(kind)
    if not field: return True
    try:
        from services.event_campaign_service import store, STATUS_PUBLISHED
        owners=[]
        for env in store().list(status=STATUS_PUBLISHED):
            values=(env.get("data") or {}).get(field) or []
            ids={str(row.get("id") or row.get(f"{kind}_id") or "") if isinstance(row,dict) else str(row) for row in values}
            if str(content_id) in ids: owners.append(str(env.get("id")))
        if not owners:return True
        states=(player or {}).get("event_campaigns") or {}
        return any(isinstance(states.get(event_id),dict) and states[event_id].get("status")=="active" for event_id in owners)
    except Exception:return True


def location(loc_id: str) -> dict[str, Any] | None:
    return get_published(registry.KIND_LOCATION, loc_id)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _player_has_item(player: dict[str, Any], item_id: str, amount: int = 1) -> bool:
    total = sum(int(float(row.get("amount") or 1)) for row in (player.get("inventory") or [])
                if isinstance(row, dict) and str(row.get("item_id") or row.get("id") or "") == str(item_id))
    return total >= max(1, amount)


def event_access_error(player: dict[str, Any], event: dict[str, Any], *, now: datetime | None = None) -> str | None:
    """Single access gate for location and sublocation event entry."""
    denied = str(event.get("access_denied_text") or event.get("condition_error_text") or "Условия запуска события не выполнены.")
    level = int(player.get("level") or 1)
    minimum = int(float(event.get("min_level") or 0)); maximum = int(float(event.get("max_level") or 0))
    if minimum and level < minimum or maximum and level > maximum: return denied
    min_energy = int(float(event.get("min_energy") or event.get("required_energy") or 0))
    if min_energy and int(player.get("energy") or 0) < min_energy: return str(event.get("not_enough_energy_text") or denied)
    race = str(event.get("required_race") or "")
    if race and str(player.get("race_id") or player.get("race") or "") != race: return denied
    required_item = str(event.get("required_item_id") or event.get("required_item") or "")
    if required_item and not _player_has_item(player, required_item, int(float(event.get("required_item_amount") or 1))): return str(event.get("missing_item_text") or denied)
    equipped_item = str(event.get("required_equipped_item_id") or "")
    if equipped_item and not any(str(row.get("item_id") or row.get("id") or "") == equipped_item for row in (player.get("equipment") or {}).values() if isinstance(row, dict)): return denied
    effects = {str(row.get("effect_id") or row.get("id") or "") for field in ("active_effects", "active_curses") for row in player.get(field) or [] if isinstance(row, dict)}
    required_effect = str(event.get("required_effect_id") or ""); forbidden_effect = str(event.get("forbidden_effect_id") or "")
    if required_effect and required_effect not in effects or forbidden_effect and forbidden_effect in effects: return denied
    reputations = player.get("reputations") or {}; hidden = player.get("hidden_reputations") or {}
    reputation_id = str(event.get("required_reputation_id") or ""); hidden_id = str(event.get("required_hidden_reputation_id") or "")
    def rep(source: Any, key: str) -> float:
        value = source.get(key, 0) if isinstance(source, dict) else 0
        return float(value.get("value", 0) if isinstance(value, dict) else value or 0)
    if reputation_id and rep(reputations, reputation_id) < float(event.get("min_reputation") or 0): return denied
    if hidden_id and rep(hidden, hidden_id) < float(event.get("min_hidden_reputation") or 0): return denied
    fines = player.get("fines") or []
    has_fine = any(isinstance(row, dict) and str(row.get("status") or "active") not in {"paid", "removed", "expired"} for row in fines)
    if event.get("requires_fine") and not has_fine or event.get("requires_no_fine") and has_fine: return denied
    quest = str(event.get("required_quest_id") or "")
    if quest and quest not in set(player.get("completed_quests") or []): return denied
    achievement = str(event.get("required_achievement_id") or "")
    achievement_ids = {str(row.get("id") or "") if isinstance(row, dict) else str(row) for row in player.get("achievements") or []}
    if achievement and achievement not in achievement_ids: return denied
    world_event = str(event.get("required_world_event_id") or "")
    if world_event and world_event not in set(player.get("active_world_events") or []): return denied
    if event.get("admin_only") and not player.get("is_admin"): return denied
    moment = now or datetime.now()
    weekdays = event.get("weekdays") or []
    if weekdays and moment.weekday() not in {int(day) for day in weekdays}: return denied
    start = str(event.get("time_start") or ""); end = str(event.get("time_end") or "")
    if start or end:
        current = moment.hour * 60 + moment.minute
        def minutes(value: str, fallback: int) -> int:
            try:
                h, m = value.split(":", 1); return int(h) * 60 + int(m)
            except (ValueError, AttributeError): return fallback
        if not minutes(start, 0) <= current <= minutes(end, 1439): return denied
    return None


def button_visible(button: dict[str, Any], player: dict[str, Any]) -> bool:
    level = int(player.get("level") or 1)
    minimum = int(float(button.get("min_level") or button.get("show_from_level") or 0))
    maximum = int(float(button.get("max_level") or button.get("show_to_level") or 0))
    if minimum and level < minimum or maximum and level > maximum:
        return False
    required_item = str(button.get("show_required_item_id") or button.get("required_item_id") or "")
    if required_item and not _player_has_item(player, required_item):
        return False
    required_quest = str(button.get("required_quest_id") or "")
    if required_quest and required_quest not in set(player.get("completed_quests") or []):
        return False
    required_achievement = str(button.get("required_achievement_id") or "")
    achievements = player.get("achievements") or {}
    if required_achievement and required_achievement not in achievements:
        return False
    required_effect = str(button.get("required_effect_id") or "")
    effects = {str(row.get("effect_id") or row.get("id") or "") for row in (player.get("active_effects") or []) if isinstance(row, dict)}
    if required_effect and required_effect not in effects:
        return False
    hidden_effect = str(button.get("hidden_by_effect_id") or "")
    if hidden_effect and hidden_effect in effects:
        return False
    reputation_id = str(button.get("required_reputation_id") or "")
    if reputation_id:
        value = (player.get("reputations") or {}).get(reputation_id, 0)
        if isinstance(value, dict):
            value = value.get("value", 0)
        if float(value or 0) < float(button.get("min_reputation") or 0):
            return False
    hidden_rep=str(button.get("required_hidden_reputation_id") or "")
    if hidden_rep and float((player.get("hidden_reputations") or {}).get(hidden_rep,0) or 0)<float(button.get("min_hidden_reputation") or 0):return False
    fines=player.get("active_fines") or player.get("fines") or []
    required_fine=str(button.get("required_fine_id") or "");hidden_fine=str(button.get("hidden_by_fine_id") or "")
    fine_ids={str(row.get("fine_type_id") or row.get("type_id") or row.get("id") or "") for row in fines if isinstance(row,dict)}
    if required_fine and required_fine not in fine_ids:return False
    if hidden_fine and hidden_fine in fine_ids:return False
    button_id = str(button.get("id") or "")
    if button.get("one_time") and button_id in set(player.get("used_world_buttons") or []):
        return False
    return True


def apply_button_consequences(player: dict[str, Any], button: dict[str, Any]) -> str | None:
    """Атомарно применить общие последствия кнопки или вернуть русский текст ошибки."""
    energy_cost = max(0, int(float(button.get("energy_cost") or (1 if button.get("uses_energy") else 0))))
    take_item = str(button.get("take_item_id") or (button.get("target") if button.get("action") == "take_item" else "") or "")
    take_amount = max(1, int(float(button.get("take_item_amount") or button.get("amount") or 1)))
    if energy_cost and int(player.get("energy") or 0) < energy_cost:
        return str(button.get("not_enough_energy_text") or button.get("error_text") or "Недостаточно энергии.")
    if take_item and not _player_has_item(player, take_item, take_amount):
        return str(button.get("unavailable_text") or button.get("error_text") or "Не хватает требуемого предмета.")
    snapshot = deepcopy(player)
    if energy_cost:
        player["energy"] = int(player.get("energy") or 0) - energy_cost
    if take_item:
        left = take_amount
        for row in player.get("inventory") or []:
            if left <= 0 or not isinstance(row, dict) or str(row.get("item_id") or row.get("id") or "") != take_item:
                continue
            amount = int(float(row.get("amount") or 1))
            used = min(left, amount)
            row["amount"] = amount - used
            left -= used
        player["inventory"] = [row for row in (player.get("inventory") or []) if not isinstance(row, dict) or int(float(row.get("amount") or 0)) > 0]
    give_item = str(button.get("give_item_id") or (button.get("target") if button.get("action") == "give_item" else "") or "")
    if give_item:
        try:
            from services.inventory_service import add_inventory_item
            from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item

            definition = get_item_definition_by_id(give_item)
            amount = max(1, int(float(button.get("give_item_amount") or button.get("amount") or 1)))
            result = add_inventory_item(player, registry_item_to_inventory_item(definition, amount) if definition else give_item, amount)
            if result.discarded:
                player.clear(); player.update(snapshot)
                return str(button.get("error_text") or "В инвентаре недостаточно места.")
        except Exception:
            player.clear(); player.update(snapshot)
            return str(button.get("error_text") or "Не удалось выдать предмет.")
    effect_id = str(button.get("apply_effect_id") or "")
    if effect_id:
        from services.effect_formula_runtime import apply_to_player
        apply_to_player(player, effect_id, source=f"button:{button.get('id')}")
    remove_effect = str(button.get("remove_effect_id") or "")
    if remove_effect:
        player["active_effects"] = [row for row in (player.get("active_effects") or [])
                                    if not isinstance(row, dict) or str(row.get("effect_id") or row.get("id") or "") != remove_effect]
    unlock = str(button.get("open_access") or "")
    if unlock:
        player.setdefault("unlocks", {})[unlock] = {"permanent": True, "source": f"button:{button.get('id')}"}
    if button.get("one_time"):
        player.setdefault("used_world_buttons", []).append(str(button.get("id") or ""))
    return None


def owned_buttons(owner_field: str, owner_id: str, *, platform: str | None = None,
                  player: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Опубликованные кнопки заданного родителя с platform/access фильтрами."""
    owner_id = str(owner_id)
    result = []
    for env in _published(registry.KIND_BUTTON):
        data = env.get("data") or {}
        if str(data.get(owner_field) or "") != owner_id:
            continue
        if platform == "telegram" and not data.get("show_telegram"):
            continue
        if platform == "vk" and not data.get("show_vk"):
            continue
        runtime_data = _data(env) or {}
        if player is not None and not campaign_content_allowed(player, registry.KIND_BUTTON, str(runtime_data.get("id") or "")):
            continue
        if player is not None and not button_visible(runtime_data, player):
            continue
        result.append(runtime_data)
    result.sort(key=lambda b: _num(b.get("order"), 0))
    return result


def location_buttons(loc_id: str, *, platform: str | None = None, player: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return owned_buttons("owner_location", loc_id, platform=platform, player=player)


def location_transitions(loc_id: str) -> list[dict[str, Any]]:
    loc_id = str(loc_id)
    return [_data(e) for e in _published(registry.KIND_TRANSITION)
            if str((e.get("data") or {}).get("from_location") or "") == loc_id]


def location_events(loc_id: str, *, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    loc_id = str(loc_id)
    rows = [_data(e) for e in _published(registry.KIND_EVENT)
            if str((e.get("data") or {}).get("location") or "") == loc_id]
    from services.formula_runtime import evaluate
    for row in rows:
        if not row:
            continue
        fixed = row.get("chance", row.get("weight", 0))
        row["runtime_chance"] = evaluate(row.get("chance_formula_id"), {
            "base_chance": fixed, "base_amount": fixed, **(context or {}),
        }, default=fixed)
    return rows


def pick_event_group(player: dict[str, Any], group_id: str, *, location_id: str = "", sublocation_id: str = "", node_id: str = "", rng: random.Random | None = None) -> dict[str, Any] | None:
    """Roll eligible events in one group with exhausted-chance redistribution."""
    rng = rng or random.Random(); group_id = str(group_id or "")
    rows: list[dict[str, Any]] = []
    occurrences = player.get("constructor_event_occurrences") or {}
    for envelope in _published(registry.KIND_EVENT):
        data = _data(envelope)
        if not campaign_content_allowed(player, registry.KIND_EVENT, str(envelope.get("id") or "")): continue
        if not data or str(data.get("event_group") or data.get("random_group") or "") != group_id: continue
        if location_id and str(data.get("location") or "") != str(location_id): continue
        if sublocation_id and str(data.get("sublocation_id") or "") != str(sublocation_id): continue
        bound_node = str(data.get("node_id") or data.get("sublocation_node_id") or "")
        if bound_node and bound_node != str(node_id): continue
        if event_access_error(player, data): continue
        base = max(0.0, min(100.0, _num(data.get("chance"), 0)))
        limit = max(0, int(_num(data.get("limit") or data.get("repeat_limit"), 0)))
        used = int(occurrences.get(str(data.get("id") or ""), 0))
        exhausted = bool(limit and used >= limit)
        effective = max(0.0, min(100.0, _num(data.get("chance_after_limit", data.get("min_chance")), 0))) if exhausted else base
        rows.append({**data, "_base": base, "_effective": effective, "_exhausted": exhausted})
    if not rows: return None
    mode = str(next((row.get("redistribution_mode") for row in rows if row.get("redistribution_mode")), "none"))
    freed = sum(max(0.0, row["_base"] - row["_effective"]) for row in rows if row["_exhausted"])
    active = [row for row in rows if not row["_exhausted"]]
    if freed and active and mode in {"even", "by_weight", "weighted", "same_group"}:
        denominator = sum(max(0.0, _num(row.get("weight"), 1)) for row in active) if mode in {"by_weight", "weighted"} else len(active)
        for row in active:
            share = (max(0.0, _num(row.get("weight"), 1)) / denominator if mode in {"by_weight", "weighted"} and denominator else 1 / len(active))
            row["_effective"] = min(max(0.0, _num(row.get("max_chance"), 100)), row["_effective"] + freed * share)
    passed = [row for row in rows if row["_effective"] > 0 and rng.uniform(0, 100) <= row["_effective"]]
    if not passed: return None
    weights = [max(0.0, _num(row.get("weight"), 1)) for row in passed]
    if not any(weights): weights = [1.0] * len(passed)
    return rng.choices(passed, weights=weights, k=1)[0]


def npc_visible(npc:dict[str,Any],player:dict[str,Any]|None)->bool:
    if player is None:return not bool(npc.get("hidden_until_condition"))
    from services.item_access_runtime import has_access
    appear=str(npc.get("appear_condition") or "");disappear=str(npc.get("disappear_condition") or "")
    if appear and not has_access(player,appear):return False
    if disappear and has_access(player,disappear):return False
    event=str(npc.get("event_appear_id") or "")
    if event and event not in {str(player.get("constructor_event_id") or ""),*[str(value) for value in player.get("active_world_events") or []]}:return False
    gone=str(npc.get("event_disappear_id") or "")
    if gone and gone in {str(value) for value in player.get("completed_events") or []}:return False
    return True


def location_npcs(loc_id: str, *, player: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    loc_id = str(loc_id)
    return [_data(e) for e in _published(registry.KIND_NPC)
            if str((e.get("data") or {}).get("location") or "") == loc_id and campaign_content_allowed(player, registry.KIND_NPC, str(e.get("id") or "")) and npc_visible(_data(e),player)]


def _spawns_in(mob_data: dict[str, Any], loc_id: str) -> bool:
    raw = mob_data.get("locations")
    ids = [str(x).strip() for x in raw] if isinstance(raw, list) else [p.strip() for p in str(raw or "").split(",")]
    return loc_id in [i for i in ids if i]


def mobs_in_location(loc_id: str, *, player: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    loc_id = str(loc_id)
    return [_data(e) for e in _published(registry.KIND_MOB) if _spawns_in(e.get("data") or {}, loc_id) and campaign_content_allowed(player, registry.KIND_MOB, str(e.get("id") or ""))]


def mob(mob_id: str) -> dict[str, Any] | None:
    return get_published(registry.KIND_MOB, mob_id)


def location_scene(loc_id: str, *, platform: str | None = None, player: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Готовая «сцена» локации для бота: заголовок, текст, кнопки и связи."""
    data = location(loc_id)
    if data is None or not campaign_content_allowed(player, registry.KIND_LOCATION, loc_id):
        return None
    return {
        "id": loc_id,
        "title": data.get("name"),
        "text": data.get("description") or data.get("short_description") or "",
        "buttons": [b.get("text") for b in location_buttons(loc_id, platform=platform, player=player)]
        + [t.get("name") or t.get("to_location") for t in location_transitions(loc_id)]
        + [npc_action_label(npc) for npc in location_npcs(loc_id, player=player)],
        "transitions": location_transitions(loc_id),
        "events": location_events(loc_id),
        "npcs": location_npcs(loc_id, player=player),
    }


def render_location(loc_id: str, *, platform: str | None = None, player: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if isinstance(player, dict):
        try:
            from services.race_runtime import restriction_error
            denied = restriction_error(player, "location", loc_id)
            if denied: return {"kind": "location_denied", "location_id": loc_id, "text": denied, "buttons": [["Назад"]]}
        except Exception: pass
    scene = location_scene(loc_id, platform=platform, player=player)
    if not scene:
        return None
    title = str(scene.get("title") or loc_id)
    body = str(scene.get("text") or "")
    text = f"📍 {title}" + (f"\n\n{body}" if body else "")
    labels = [str(label) for label in scene.get("buttons") or [] if str(label or "").strip()]
    try:
        from services.tavern_runtime import taverns_for_parent
        labels.extend(row["name"] for row in taverns_for_parent("location",loc_id,platform=platform))
    except Exception: pass
    try:
        from services.casino_runtime import casinos_for_parent
        labels.extend(row["name"] for row in casinos_for_parent("location",loc_id))
    except Exception: pass
    return {"kind": "location", "location_id": loc_id, "text": text, "buttons": [[label] for label in labels]}


def try_handle_location_action(
    player: dict[str, Any], action: str, *, platform: str | None = None,
) -> dict[str, Any] | None:
    """Разрешить вход/навигацию опубликованной локации из общего bot-flow."""
    from services import location_runtime

    if not location_runtime.live_enabled():
        return None
    label = str(action or "").strip()
    if not label:
        return None
    current_id = str(player.get("constructor_location_id") or "").strip()

    if current_id and location(current_id):
        button = next((row for row in location_buttons(current_id, platform=platform, player=player) if str(row.get("text") or "") == label), None)
        if button:
            consequence_error = apply_button_consequences(player, button)
            if consequence_error:
                view = render_location(current_id, platform=platform, player=player) or {"buttons": []}
                return {**view, "text": consequence_error}
            action_type = str(button.get("action") or "")
            target = str(button.get("target") or "").strip()
            if action_type == "goto_location":
                return render_location(target, platform=platform, player=player)
            if action_type == "show_message":
                view = render_location(current_id, platform=platform, player=player) or {"buttons": []}
                return {**view, "text": str(button.get("message") or button.get("result_text") or button.get("text") or "")}
            if action_type == "open_npc":
                npc = get_published(registry.KIND_NPC, target)
                if npc:
                    rendered = render_npc(target, player=player, platform=platform)
                    if rendered:
                        return rendered
            if action_type == "start_event":
                event = get_published(registry.KIND_EVENT, target)
                if event:
                    access_error = event_access_error(player, event)
                    if access_error:
                        view = render_location(current_id, platform=platform, player=player) or {"buttons": []}
                        return {**view, "text": access_error}
                    occurrences = player.setdefault("constructor_event_occurrences", {})
                    occurrences[target] = int(occurrences.get(target, 0)) + 1
                    return render_event(target, player=player, platform=platform)
            if action_type == "start_event_group":
                event = pick_event_group(player, target, location_id=current_id, rng=random.Random())
                if event:
                    event_id = str(event.get("id") or ""); occurrences = player.setdefault("constructor_event_occurrences", {}); occurrences[event_id] = int(occurrences.get(event_id, 0)) + 1
                    return render_event(event_id, player=player, platform=platform)
                view = render_location(current_id, platform=platform, player=player) or {"buttons": []}
                return {**view, "text": str(button.get("empty_group_text") or "Сейчас в этой группе событий ничего не произошло.")}
            if action_type == "open_camp":
                return {"kind": "open_camp", "camp_id": target, "location_id": current_id}
            if action_type == "open_sublocation":
                rendered = render_sublocation(target, platform=platform, player=player)
                if rendered:
                    return rendered
            if action_type in {"start_battle"} and target:
                return {"kind":"button_battle","mob_id":target,"location_id":current_id,"text":str(button.get("message") or "Начинается бой!"),"buttons":[]}
            if action_type in {"open_npc","open_dialog"} and target:
                rendered=render_npc(target,player=player,platform=platform)
                if rendered:return rendered
            route_actions={"open_shop":"Рынок","open_market":"Рынок","open_craft":"Ремесленный квартал","open_profile":"👤 Профиль","open_inventory":"👤 Профиль","open_delivery":"👤 Профиль","open_promo":"Промокоды","open_quest":"Задания","open_quests":"Задания","open_raids":"Рейды","open_fishing":"Рыбалка","start_search":"Искать","open_tavern":target,"system_command":target}
            if action_type in route_actions:
                route=str(route_actions[action_type] or "")
                return {"kind":"button_route","route_action":route,"location_id":current_id,"text":str(button.get("message") or button.get("success_text") or "Переход выполнен."),"buttons":[[route]] if route else []}
            if action_type in {"hide_menu","show_menu"}:
                command="/hide_menu" if action_type=="hide_menu" else "/menu"
                return {"kind":"button_route","route_action":command,"location_id":current_id,"text":str(button.get("message") or ("Меню скрыто." if action_type=="hide_menu" else "Меню возвращено.")),"buttons":[]}
            if action_type=="go_back":
                return render_location(target or str(button.get("previous_location") or ""),platform=platform,player=player) or {"kind":"button_route","route_action":"Назад","location_id":current_id,"text":"Возврат.","buttons":[["Назад"]]}
            if action_type in {"give_item", "take_item", "use_item", "check_condition", "claim_reward", "confirm", "cancel", "look_around", "gather_resource"}:
                view = render_location(current_id, platform=platform, player=player) or {"buttons": []}
                return {**view, "text": str(button.get("message") or button.get("success_text") or "Действие выполнено.")}
        transition = next((row for row in location_transitions(current_id) if label in {str(row.get("name") or ""), str(row.get("to_location") or "")}), None)
        if transition:
            return render_location(str(transition.get("to_location") or ""), platform=platform, player=player)
        npc = next((row for row in location_npcs(current_id, player=player) if npc_action_label(row) == label), None)
        if npc:
            return render_npc(str(npc.get("id") or ""), player=player, platform=platform)

    # Вход по ID или отображаемому названию опубликованной локации.
    for envelope in _published(registry.KIND_LOCATION):
        data = envelope.get("data") or {}
        loc_id = str(envelope.get("id") or "")
        if label in {loc_id, str(data.get("name") or "").strip()}:
            return render_location(loc_id, platform=platform, player=player)
    return None


def render_event(event_id: str, *, player: dict[str, Any], platform: str | None = None) -> dict[str, Any] | None:
    event = get_published(registry.KIND_EVENT, event_id)
    if not event:
        return None
    buttons = [[str(row.get("text"))] for row in owned_buttons("owner_event", event_id, platform=platform, player=player)]
    buttons.append(["Завершить событие"])
    return {
        "kind": "event", "event_id": event_id,
        "location_id": str(event.get("location") or player.get("constructor_location_id") or ""),
        "text": str(event.get("text") or event.get("name") or event_id), "buttons": buttons,
    }


def try_handle_event_action(player: dict[str, Any], action: str, *, platform: str | None = None) -> dict[str, Any] | None:
    event_id = str(player.get("constructor_event_id") or "")
    label = str(action or "").strip()
    if not event_id or not label:
        return None
    if label == "Завершить событие":
        event = get_published(registry.KIND_EVENT, event_id) or {"id": event_id}
        from services.constructor_event_runtime import complete
        report = complete(player, event)
        suffix = "\n".join(str(line) for line in report.get("lines") or [])
        if report.get("battle_text"):
            from services.pve_battle_service import battle_buttons
            player.pop("constructor_event_id", None)
            player.pop("constructor_event_return_sublocation_id", None)
            player.pop("constructor_event_return_node_id", None)
            text = (suffix + "\n\n" if suffix else "") + str(report["battle_text"])
            return {"kind": "event_battle", "location_id": str(event.get("location") or player.get("constructor_location_id") or ""), "text": text, "buttons": battle_buttons(player)}
        route = report.get("route") or {}
        route_kind, route_id = str(route.get("kind") or ""), str(route.get("id") or "")
        if route_kind == "event" and route_id:
            occurrences = player.setdefault("constructor_event_occurrences", {}); occurrences[route_id] = int(occurrences.get(route_id, 0)) + 1
            rendered = render_event(route_id, player=player, platform=platform)
            if rendered and suffix: rendered["text"] = suffix + "\n\n" + str(rendered.get("text") or "")
            return rendered
        if route_kind == "npc" and route_id:
            player.pop("constructor_event_id", None); player.pop("constructor_event_return_sublocation_id", None); player.pop("constructor_event_return_node_id", None)
            rendered = render_npc(route_id, player=player, platform=platform)
            if rendered and suffix: rendered["text"] = suffix + "\n\n" + str(rendered.get("text") or "")
            return rendered
        if route_kind == "sublocation" and route_id:
            player.pop("constructor_event_id", None); player.pop("constructor_event_return_sublocation_id", None); player.pop("constructor_event_return_node_id", None)
            rendered = render_sublocation(route_id, platform=platform, player=player)
            if rendered and suffix: rendered["text"] = suffix + "\n\n" + str(rendered.get("text") or "")
            return rendered
        if route_kind == "location" and route_id:
            player.pop("constructor_event_id", None); player.pop("constructor_event_return_sublocation_id", None); player.pop("constructor_event_return_node_id", None)
            rendered = render_location(route_id, platform=platform, player=player)
            if rendered and suffix: rendered["text"] = suffix + "\n\n" + str(rendered.get("text") or "")
            return rendered
        if player.get("constructor_event_return_sublocation_id"):
            sub_id = str(player.get("constructor_event_return_sublocation_id") or "")
            node_id = str(player.get("constructor_event_return_node_id") or "")
            rendered = render_sublocation(sub_id, node_id, platform=platform, player=player)
            result = {**(rendered or {}), "kind": "leave_event_to_sublocation"}
            if suffix: result["text"] = suffix + "\n\n" + str(result.get("text") or "")
            return result
        return {"kind": "leave_event", "location_id": str(player.get("constructor_location_id") or ""), "reward_text": suffix}
    button = next((row for row in owned_buttons("owner_event", event_id, platform=platform, player=player)
                   if str(row.get("text") or "") == label), None)
    if not button:
        return None
    error = apply_button_consequences(player, button)
    current = render_event(event_id, player=player, platform=platform) or {"buttons": []}
    return {**current, "text": error or str(button.get("message") or button.get("success_text") or "Действие выполнено.")}


def _sublocation_nodes(sub_id: str) -> list[dict[str, Any]]:
    rows = [_data(row) for row in _published(registry.KIND_SUBLOCATION_NODE)
            if str((row.get("data") or {}).get("sublocation_id") or "") == str(sub_id)]
    return [row for row in rows if row]


def _sublocation_transitions(sub_id: str, node_id: str) -> list[dict[str, Any]]:
    rows = [_data(row) for row in _published(registry.KIND_SUBLOCATION_TRANSITION)
            if str((row.get("data") or {}).get("sublocation_id") or "") == str(sub_id)
            and str((row.get("data") or {}).get("from_node") or "") == str(node_id)
            and not (row.get("data") or {}).get("hidden")]
    return [row for row in rows if row]


def sublocation_events(sub_id: str, node_id: str = "", *, player: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for envelope in _published(registry.KIND_EVENT):
        data = _data(envelope)
        if not campaign_content_allowed(player, registry.KIND_EVENT, str(envelope.get("id") or "")): continue
        if not data or str(data.get("sublocation_id") or "") != str(sub_id):
            continue
        bound_node = str(data.get("node_id") or data.get("sublocation_node_id") or "")
        if bound_node and bound_node != str(node_id):
            continue
        if player is not None:
            if event_access_error(player, data):
                continue
            level = int(player.get("level") or 1)
            minimum = int(float(data.get("min_level") or 0))
            maximum = int(float(data.get("max_level") or 0))
            if minimum and level < minimum or maximum and level > maximum:
                continue
            required_item = str(data.get("required_item_id") or "")
            if required_item and not any(str(item.get("item_id") or item.get("id") or "") == required_item for item in player.get("inventory") or [] if isinstance(item, dict)):
                continue
            required_unlock = str(data.get("required_unlock") or "")
            from services.item_access_runtime import has_access
            if required_unlock and not has_access(player,required_unlock):
                continue
            limit = max(0, int(float(data.get("limit") or data.get("repeat_limit") or 0)))
            if not data.get("repeatable") and not limit:
                limit = 1
            used = int((player.get("sublocation_event_usage") or {}).get(str(data.get("id") or ""), 0))
            if limit and used >= limit:
                continue
            cooldown = max(0, int(float(data.get("cooldown") or 0)))
            last_at = float((player.get("sublocation_event_last_at") or {}).get(str(data.get("id") or ""), 0) or 0)
            if cooldown:
                import time
                if time.time() - last_at < cooldown:
                    continue
        rows.append(data)
    return rows


def sublocation_event_label(event: dict[str, Any]) -> str:
    return str(event.get("button_text") or event.get("start_text") or f"Событие: {event.get('name') or event.get('id')}")

_SUB_SERVICES={"market":"Рынок","port_market":"Портовый рынок","black_market":"Чёрный рынок","tavern":"Таверна","rest":"Отдых","rumors":"Слухи","quest_board":"Доска заданий","craft":"Ремесло","alchemy":"Алхимия","forge":"Кузница","leather":"Кожевенная мастерская","smelting":"Плавильня","jewelry":"Ювелирная мастерская","enchant":"Чародейская мастерская","fines":"Управляющий штрафами","coordinator":"Координатор","informant":"Информатор","casino":"Казино","fishing":"Рыбалка","delivery":"Доставка","promo":"Промокоды"}

def sublocation_access_error(player:dict[str,Any],sub:dict[str,Any])->str|None:
    level=int(player.get("level") or 1);minimum=int(float(sub.get("min_level") or 0));maximum=int(float(sub.get("max_level") or 0))
    denied=str(sub.get("denied_text") or "Подлокация сейчас недоступна.")
    if minimum and level<minimum or maximum and level>maximum:return denied
    item=str(sub.get("required_item") or "")
    if item and not any(str((x or {}).get("item_id") or (x or {}).get("id") or "")==item for x in player.get("inventory") or [] if isinstance(x,dict)):return denied
    quest=str(sub.get("required_quest") or "")
    completed=((player.get("quests") or {}).get("completed") or {})
    if quest and quest not in completed:return denied
    npc=str(sub.get("required_npc") or "")
    if npc and npc not in {str(x) for x in player.get("met_npcs") or []}:return denied
    rid=str(sub.get("required_reputation_id") or "")
    if rid and float((player.get("reputations") or {}).get(rid) or 0)<float(sub.get("required_reputation_value") or 0):return denied
    if sub.get("require_no_fine"):
        try:
            from services.fine_service import active_fines
            if active_fines(player):return denied
        except Exception:pass
    event=str(sub.get("required_event") or "")
    if event and event not in {str(x) for x in player.get("active_world_events") or []} and event not in (player.get("world_event_flags") or {}):return denied
    if sub.get("required_time_start") or sub.get("required_time_end"):
        from datetime import datetime
        now=datetime.now().strftime("%H:%M");start=str(sub.get("required_time_start") or "00:00");end=str(sub.get("required_time_end") or "23:59")
        if not (start<=now<=end):return denied
    return None


def render_sublocation(sub_id: str, node_id: str | None = None, *, platform: str | None = None,
                       player: dict[str, Any] | None = None) -> dict[str, Any] | None:
    sub = get_published(registry.KIND_SUBLOCATION, sub_id)
    if not sub:
        return None
    if player is not None:
        error=sublocation_access_error(player,sub)
        if error:return {"kind":"sublocation_denied","sublocation_id":sub_id,"location_id":str(sub.get("parent_location") or ""),"text":error,"buttons":[]}
    nodes = _sublocation_nodes(sub_id)
    node = next((row for row in nodes if str(row.get("id")) == str(node_id)), None) if node_id else None
    if node is None:
        node = next((row for row in nodes if row.get("node_type") == "entry"), None) or (nodes[0] if nodes else None)
    if node is None:
        return None
    transitions = _sublocation_transitions(sub_id, str(node.get("id") or ""))
    buttons = [[str(row.get("button_text") or row.get("to_node"))] for row in transitions]
    buttons.extend([[str(row.get("text"))] for row in owned_buttons("owner_sublocation", sub_id, platform=platform, player=player)])
    for button_id in sub.get("button_ids") or []:
        button=get_published(registry.KIND_BUTTON,str(button_id))
        if button and button_visible(button,player or {}):buttons.append([str(button.get("text") or button.get("name") or button_id)])
    buttons.extend([[sublocation_event_label(row)] for row in sublocation_events(sub_id, str(node.get("id") or ""), player=player)])
    for event_id in sub.get("event_ids") or []:
        event=get_published(registry.KIND_EVENT,str(event_id))
        if event and event_access_error(player or {},event) is None:buttons.append([sublocation_event_label(event)])
    buttons.extend([[_SUB_SERVICES.get(str(x),str(x))] for x in sub.get("service_types") or []])
    try:
        from services.tavern_runtime import taverns_for_parent
        buttons.extend([[row["name"]] for row in taverns_for_parent("sublocation",sub_id,platform=platform)])
    except Exception: pass
    try:
        from services.casino_runtime import casinos_for_parent
        buttons.extend([[row["name"]] for row in casinos_for_parent("sublocation",sub_id)])
    except Exception: pass
    if sub.get("can_leave") is not False:
        buttons.append(["Покинуть подлокацию"])
    for envelope in _published(registry.KIND_NPC):
        npc = _data(envelope)
        if npc and campaign_content_allowed(player, registry.KIND_NPC, str(npc.get("id") or "")) and npc_visible(npc,player) and (str(npc.get("sublocation_id") or "") == str(sub_id) or str(npc.get("id")) in {str(x) for x in sub.get("npc_ids") or []}):
            buttons.append([npc_action_label(npc)])
    text = str(node.get("player_text") or (sub.get("entry_text") if str(node.get("node_type"))=="entry" else "") or node.get("description") or node.get("name") or sub.get("description") or sub.get("name") or sub_id)
    return {
        "kind": "sublocation", "sublocation_id": sub_id,
        "location_id": str(sub.get("parent_location") or ""),
        "node_id": str(node.get("id") or ""), "text": text, "buttons": buttons,
    }


def try_handle_sublocation_action(player: dict[str, Any], action: str, *, platform: str | None = None) -> dict[str, Any] | None:
    from services import location_runtime

    if not location_runtime.live_enabled():
        return None
    sub_id = str(player.get("constructor_sublocation_id") or "")
    node_id = str(player.get("constructor_sublocation_node_id") or "")
    label = str(action or "").strip()
    if not sub_id or not node_id or not label:
        return None
    sub = get_published(registry.KIND_SUBLOCATION, sub_id)
    if not sub:
        return None
    if label in {_SUB_SERVICES.get(str(x),str(x)) for x in sub.get("service_types") or []}:
        return {"kind":"button_route","route_action":label,"location_id":str(sub.get("parent_location") or ""),"text":str(sub.get("look_text") or f"Открывается: {label}."),"buttons":[[label]]}
    event = next((row for row in sublocation_events(sub_id, node_id, player=player) if sublocation_event_label(row) == label), None)
    if not event:
        event=next((candidate for event_id in sub.get("event_ids") or [] for candidate in [get_published(registry.KIND_EVENT,str(event_id))] if candidate and sublocation_event_label(candidate)==label and event_access_error(player,candidate) is None),None)
    if event:
        import random
        chance = max(0.0, min(100.0, float(event.get("chance") or 100)))
        if random.uniform(0, 100) > chance:
            current = render_sublocation(sub_id, node_id, platform=platform, player=player) or {"buttons": []}
            return {**current, "text": str(event.get("miss_text") or sub.get("empty_text") or "Событие не произошло.")}
        event_id = str(event.get("id") or "")
        usage = player.setdefault("sublocation_event_usage", {})
        usage[event_id] = int(usage.get(event_id, 0)) + 1
        import time
        player.setdefault("sublocation_event_last_at", {})[event_id] = time.time()
        player["constructor_event_return_sublocation_id"] = sub_id
        player["constructor_event_return_node_id"] = node_id
        return render_event(event_id, player=player, platform=platform)
    for envelope in _published(registry.KIND_NPC):
        npc = _data(envelope)
        if npc and npc_visible(npc,player) and str(npc.get("sublocation_id") or "") == sub_id and npc_action_label(npc) == label:
            return render_npc(str(npc.get("id") or ""), player=player, platform=platform)
    owned = next((row for row in owned_buttons("owner_sublocation", sub_id, platform=platform, player=player)
                  if str(row.get("text") or "") == label), None)
    if not owned:
        for button_id in sub.get("button_ids") or []:
            candidate=get_published(registry.KIND_BUTTON,str(button_id))
            if candidate and button_visible(candidate,player) and label==str(candidate.get("text") or candidate.get("name") or button_id):owned=candidate;break
    if owned:
        error = apply_button_consequences(player, owned)
        current = render_sublocation(sub_id, node_id, platform=platform, player=player) or {"buttons": []}
        if error:
            return {**current, "text": error}
        action_type = str(owned.get("action") or "")
        target = str(owned.get("target") or "")
        if action_type in {"open_npc", "open_dialog"}:
            return render_npc(target, player=player, platform=platform)
        if action_type == "goto_location":
            return render_location(target, platform=platform, player=player)
        if action_type == "open_camp":
            return {"kind": "open_camp", "camp_id": target, "location_id": str(sub.get("parent_location") or "")}
        if action_type == "start_event_group":
            event = pick_event_group(player, target, sublocation_id=sub_id, node_id=node_id, rng=random.Random())
            if event:
                event_id = str(event.get("id") or ""); occurrences = player.setdefault("constructor_event_occurrences", {}); occurrences[event_id] = int(occurrences.get(event_id, 0)) + 1
                player["constructor_event_return_sublocation_id"] = sub_id; player["constructor_event_return_node_id"] = node_id
                return render_event(event_id, player=player, platform=platform)
            return {**current, "text": str(owned.get("empty_group_text") or "Сейчас в этой группе событий ничего не произошло.")}
        return {**current, "text": str(owned.get("message") or owned.get("success_text") or "Действие выполнено.")}
    if label == "Покинуть подлокацию" and sub.get("can_leave") is not False:
        return {"kind": "leave_sublocation", "location_id": str(sub.get("parent_location") or ""),"text":str(sub.get("exit_text") or "Вы покинули подлокацию.")}
    transition = next((row for row in _sublocation_transitions(sub_id, node_id)
                       if label == str(row.get("button_text") or row.get("to_node") or "")), None)
    if not transition:
        return None
    required_level = int(float(transition.get("required_level") or 0))
    if required_level and int(player.get("level") or 1) < required_level:
        current = render_sublocation(sub_id, node_id, platform=platform, player=player) or {"buttons": []}
        return {**current, "text": str(transition.get("denied_text") or f"Требуется {required_level} уровень.")}
    energy_cost = max(0, int(float(transition.get("energy_cost") or 0)))
    if energy_cost and int(player.get("energy") or 0) < energy_cost:
        current = render_sublocation(sub_id, node_id, platform=platform, player=player) or {"buttons": []}
        return {**current, "text": str(transition.get("denied_text") or "Недостаточно энергии.")}
    if energy_cost:
        player["energy"] = int(player.get("energy") or 0) - energy_cost
    return render_sublocation(sub_id, str(transition.get("to_node") or ""), platform=platform, player=player)


def _dialogue_allowed(player: dict[str, Any], row: dict[str, Any]) -> bool:
    minimum = int(float(row.get("min_level") or 0))
    maximum = int(float(row.get("max_level") or 0))
    level = int(player.get("level") or 1)
    if minimum and level < minimum or maximum and level > maximum:
        return False
    required_item = str(row.get("required_item_id") or "")
    if required_item and not any(str((item or {}).get("item_id") or (item or {}).get("id") or "") == required_item
                                 for item in (player.get("inventory") or []) if isinstance(item, dict)):
        return False
    required_unlock = str(row.get("required_unlock") or "")
    from services.item_access_runtime import has_access
    if required_unlock and not has_access(player,required_unlock):
        return False
    reputation_id = str(row.get("reputation_id") or "")
    if reputation_id:
        reputation = (player.get("reputations") or {}).get(reputation_id, 0)
        if isinstance(reputation, dict):
            reputation = reputation.get("value", 0)
        if float(reputation or 0) < float(row.get("min_reputation") or 0):
            return False
    return True


def npc_action_label(npc: dict[str, Any]) -> str:
    return str(npc.get("button_text") or f"Поговорить: {npc.get('player_name') or npc.get('name') or npc.get('id')}")


def npc_service_rows(npc:dict[str,Any])->list[dict[str,Any]]:
    return [{"service_id":str(row.get("service_id") or f"service_{index+1}"),**row} for index,row in enumerate(npc.get("services") or []) if isinstance(row,dict) and row.get("active") is not False]


def npc_service_label(row:dict[str,Any])->str:return str(row.get("name") or row.get("label") or row.get("service_id"))


def use_npc_service(player:dict[str,Any],npc:dict[str,Any],row:dict[str,Any])->dict[str,Any]:
    denied=str(row.get("error_text") or "Услуга NPC недоступна.");condition=str(row.get("condition") or "")
    if condition:
        from services.item_access_runtime import has_access
        if not has_access(player,condition):return {"kind":"npc","npc_id":npc["id"],"text":denied,"buttons":[["Завершить разговор"]]}
    item_id=str(row.get("required_item_id") or "");inventory=player.get("inventory") or []
    if item_id and not any(isinstance(item,dict) and str(item.get("item_id") or item.get("id") or "")==item_id for item in inventory):return {"kind":"npc","npc_id":npc["id"],"text":denied,"buttons":[["Завершить разговор"]]}
    kind=str(row.get("service_type") or "");route={"shop":"Рынок","black_market":"Чёрный рынок","port_market":"Портовый рынок","repair":"👤 Профиль","craft":"Ремесленный квартал","alchemy":"Алхимическая мастерская","enchant":"Зачарование","remove_curse":"Очищение","rest":"Лагерь","rumors":"Слухи","find_player":"Поиск игроков","assassin_order":"Заказ убийц","board":"Задания","pay_fines":"Оплатить штраф","training":"Навыки","guide":"Путешествие"}.get(kind)
    cost=max(0,int(float(row.get("cost") or 0)));currency=str(row.get("currency") or "copper")
    try:
        from services.economy_runtime import service_price,change,service_rule
        context={"npc_id":npc.get("id"),"location_id":player.get("location_id"),"sublocation_id":player.get("current_zone")}
        cost=service_price(kind or "npc_service",cost,player,context);change(player,currency,-cost,operation=f"service_{kind or 'npc'}",source="npc",source_id=str(npc.get("id") or ""));economy_row=service_rule(kind or "npc_service",context)
    except ValueError:return {"kind":"npc","npc_id":npc["id"],"text":denied,"buttons":[["Завершить разговор"]]}
    except ImportError:
        bucket=player if currency in {"copper","coins"} else player.setdefault("currencies",{});key="money_copper" if bucket is player and "money_copper" in player else "money" if bucket is player else currency
        if int(bucket.get(key) or 0)<cost:return {"kind":"npc","npc_id":npc["id"],"text":denied,"buttons":[["Завершить разговор"]]}
        bucket[key]=int(bucket.get(key) or 0)-cost;economy_row={}
    if kind=="healing":player["hp"]=min(int(player.get("max_hp") or 0),int(player.get("hp") or 0)+int(row.get("amount") or player.get("max_hp") or 0))
    action=str(row.get("target_action") or route or "")
    if kind=="shop" and (npc.get("trade") or {}).get("sells"):
        buttons=[[f"Купить у NPC: {item.get('item_id')}"] for item in (npc.get("trade") or {}).get("sells") or [] if isinstance(item,dict)]+[["Завершить разговор"]];action=""
    else:buttons=[[action]] if action else [["Завершить разговор"]]
    return {"kind":"npc","npc_id":npc["id"],"dialogue_id":"","text":str(economy_row.get("success_text") or row.get("success_text") or "Услуга оказана."),"buttons":buttons,"route_action":action}


def npc_trade_buy(player:dict[str,Any],npc:dict[str,Any],item_id:str)->str:
    row=next((row for row in (npc.get("trade") or {}).get("sells") or [] if isinstance(row,dict) and str(row.get("item_id") or "")==str(item_id)),None)
    if not row:raise ValueError("Товар NPC не найден.")
    stock=max(0,int(row.get("stock") or row.get("amount") or 0));usage=player.setdefault("npc_trade_purchases",{});key=f"{npc['id']}:{item_id}"
    if stock and int(usage.get(key) or 0)>=stock:raise ValueError("Товар у NPC закончился.")
    price=max(0,int(float(row.get("price") or 0)));trade=npc.get("trade") or {};price=round(price*(1+float(trade.get("markup_percent") or 0)/100)*(1-float(trade.get("discount_percent") or 0)/100))
    money_key="money_copper" if "money_copper" in player else "money"
    if int(player.get(money_key) or 0)<price:raise ValueError("Недостаточно денег.")
    from services.item_registry import get_item_definition_by_id,registry_item_to_inventory_item
    from services.inventory_service import add_inventory_item
    definition=get_item_definition_by_id(item_id)
    if not definition:raise ValueError("Предмет товара не опубликован.")
    result=add_inventory_item(player,registry_item_to_inventory_item(definition,1),1,default_source=f"NPC: {npc.get('name')}")
    if result.added<1:raise ValueError("В инвентаре нет места.")
    before=int(player.get(money_key) or 0);player[money_key]=before-price
    if money_key=="money_copper":player["money"]=player[money_key]
    try:
        from services.economy_runtime import record
        record(player,"npc_purchase","copper",-price,before,int(player.get(money_key) or 0),source="npc",source_id=str(npc.get("id") or ""))
    except (ImportError,OSError):pass
    usage[key]=int(usage.get(key) or 0)+1
    return str(row.get("success_text") or f"Куплено: {definition.get('name') or item_id} за {price} монет.")


def npc_access_error(player: dict[str, Any], npc: dict[str, Any], *, now: datetime | None = None) -> str | None:
    level = int(player.get("level") or 1)
    minimum = int(float(npc.get("min_level") or 0))
    maximum = int(float(npc.get("max_level") or 0))
    if minimum and level < minimum or maximum and level > maximum:
        return str(npc.get("denied_text") or "NPC сейчас недоступен для вашего уровня.")
    required_race = str(npc.get("required_race") or "")
    if required_race and str(player.get("race_id") or player.get("race") or "") != required_race:
        return str(npc.get("denied_text") or "NPC не разговаривает с представителями вашей расы.")
    required_item = str(npc.get("required_item_id") or "")
    if required_item and not any(str((row or {}).get("item_id") or (row or {}).get("id") or "") == required_item
                                 for row in (player.get("inventory") or []) if isinstance(row, dict)):
        return str(npc.get("denied_text") or "Для разговора нужен особый предмет.")
    reputation_id = str(npc.get("required_reputation_id") or "")
    if reputation_id:
        value = (player.get("reputations") or {}).get(reputation_id, 0)
        if isinstance(value, dict):
            value = value.get("value", 0)
        if float(value or 0) < float(npc.get("min_reputation") or 0):
            return str(npc.get("denied_text") or "Недостаточно репутации.")
    hidden_id=str(npc.get("required_hidden_reputation_id") or "")
    if hidden_id and float((player.get("hidden_reputations") or {}).get(hidden_id,0) or 0)<float(npc.get("min_hidden_reputation") or 0):return str(npc.get("denied_text") or "Недостаточно скрытой репутации.")
    schedule = npc.get("schedule") or []
    if schedule:
        moment = now or datetime.now()
        weekday = moment.weekday()
        current_minutes = moment.hour * 60 + moment.minute
        active = False
        for row in schedule:
            if not isinstance(row, dict) or row.get("active") is False:
                continue
            days = row.get("weekdays") or row.get("days") or list(range(7))
            days = [int(day) for day in days] if isinstance(days, list) else list(range(7))
            try:
                start_h, start_m = [int(part) for part in str(row.get("start") or "00:00").split(":", 1)]
                end_h, end_m = [int(part) for part in str(row.get("end") or "23:59").split(":", 1)]
            except (TypeError, ValueError):
                continue
            if weekday in days and start_h * 60 + start_m <= current_minutes <= end_h * 60 + end_m:
                active = True
                break
        if not active:
            return str(npc.get("schedule_closed_text") or npc.get("denied_text") or "NPC сейчас отсутствует.")
    return None


def _apply_dialogue_outcome(player: dict[str, Any], npc_id: str, row: dict[str, Any]) -> None:
    row_id = str(row.get("id") or "")
    claims = player.setdefault("npc_dialogue_claims", {}).setdefault(npc_id, [])
    if row_id in claims:
        return
    changed = False
    reward_item = str(row.get("reward_item_id") or "").strip()
    if reward_item:
        try:
            from services.inventory_service import add_inventory_item
            from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item

            definition = get_item_definition_by_id(reward_item)
            if definition:
                add_inventory_item(player, registry_item_to_inventory_item(definition, max(1, int(float(row.get("reward_amount") or 1)))))
                changed = True
        except Exception:
            pass
    effect_id = str(row.get("effect_id") or "").strip()
    if effect_id:
        try:
            from services.effect_formula_runtime import apply_to_player
            changed = bool(apply_to_player(player, effect_id, source=f"npc:{npc_id}")) or changed
        except Exception:
            pass
    unlock = str(row.get("open_access") or row.get("unlock_id") or "").strip()
    if unlock:
        player.setdefault("unlocks", {})[unlock] = {"permanent": True, "source": f"npc:{npc_id}"}
        changed = True
    loss_item=str(row.get("loss_item_id") or "")
    if loss_item:
        left=max(1,int(float(row.get("loss_amount") or 1)))
        for item in player.get("inventory") or []:
            if left<=0 or not isinstance(item,dict) or str(item.get("item_id") or item.get("id") or "")!=loss_item:continue
            take=min(left,int(item.get("amount") or 1));item["amount"]=int(item.get("amount") or 1)-take;left-=take
        player["inventory"]=[item for item in player.get("inventory") or [] if not isinstance(item,dict) or int(item.get("amount") or 0)>0];changed=True
    reputation_id=str(row.get("reputation_id") or "")
    if reputation_id:
        try:
            from services.reputation_runtime_service import change
            change(player,reputation_id,int(row.get("reputation_delta") or 0),source="npc_dialogue",source_id=npc_id,reason=str(row.get("reputation_text") or ""))
        except ValueError:
            bucket=player.setdefault("hidden_reputations" if row.get("hidden_reputation") else "reputations",{});bucket[reputation_id]=int(bucket.get(reputation_id) or 0)+int(row.get("reputation_delta") or 0)
        changed=True
    try:
        from services.reputation_runtime_service import apply_trigger
        if apply_trigger(player,"npc_dialogue",npc_id,reason=str(row.get("reputation_text") or "")):changed=True
    except Exception:pass
    if row.get("quest_progress_id"):
        try:
            from services.quest_runtime_service import progress
            progress(player,"talk_npc",str(row.get("quest_progress_id")),1);changed=True
        except Exception:pass
    if changed or row.get("one_time_reward", True):
        claims.append(row_id)


def render_npc(npc_id: str, *, player: dict[str, Any], dialogue_id: str | None = None,
               platform: str | None = None) -> dict[str, Any] | None:
    npc = get_published(registry.KIND_NPC, npc_id)
    if not npc or not campaign_content_allowed(player, registry.KIND_NPC, npc_id):
        return None
    try:
        from services.world_event_runtime import access_allowed
        if not access_allowed("npc",npc_id,context={"game_id":player.get("game_id"),"npc_id":npc_id,"location_id":player.get("current_location") or player.get("location_id"),"city_id":player.get("current_city") or player.get("city_id")}):
            return {"kind":"npc","npc_id":npc_id,"dialogue_id":"","text":"NPC временно недоступен из-за мирового события.","buttons":[["Завершить разговор"]]}
    except Exception:pass
    visited = player.setdefault("event_campaign_npc_visits", [])
    if npc_id not in visited:
        try:
            from services.event_campaign_runtime import progress as event_progress
            event_progress(player, "talk_npc", npc_id, 1)
            visited.append(npc_id)
        except Exception:
            pass
    denied = npc_access_error(player, npc)
    if denied:
        return {"kind": "npc", "npc_id": npc_id, "dialogue_id": "", "text": denied, "buttons": [["Завершить разговор"]]}
    rows = [row for row in (npc.get("dialogues") or []) if isinstance(row, dict)]
    current = next((row for row in rows if str(row.get("id") or "") == str(dialogue_id)), None) if dialogue_id else None
    if current is None:
        current = next((row for row in rows if row.get("dialogue_type") in {"greeting", "start"}), None)
        current = current or next((row for row in rows if not row.get("parent_id")), None)
    if current and not _dialogue_allowed(player, current):
        return {"kind": "npc", "npc_id": npc_id, "dialogue_id": "", "text": str(npc.get("denied_text") or "NPC сейчас не хочет разговаривать."), "buttons": [["Завершить разговор"]]}
    if current:
        _apply_dialogue_outcome(player, npc_id, current)
        current_id = str(current.get("id") or "")
        choices = [row for row in rows if str(row.get("parent_id") or "") == current_id and _dialogue_allowed(player, row)]
        if not choices and current.get("next_id") and current.get("player_button"):
            choices = [current]
        buttons = [[str(row.get("player_button") or row.get("reply_button") or row.get("button_text") or "Продолжить")] for row in choices]
        buttons.extend([[npc_service_label(row)] for row in npc_service_rows(npc)])
        buttons.extend([[f"Принять квест: {quest_id}"] for quest_id in npc.get("quest_ids") or []])
        if npc.get("combat_mob_id"):buttons.append([["Сразиться"]][0])
        buttons.extend([[str(row.get("text"))] for row in owned_buttons("owner_npc", npc_id, platform=platform, player=player)])
        if current.get("ends_dialogue") or not buttons:
            buttons.append(["Завершить разговор"])
        text = str(current.get("npc_text") or current.get("text") or npc.get("first_message") or npc.get("name") or npc_id)
        try:
            from services.quest_runtime_service import npc_dialogue
            quest_line=npc_dialogue(player,npc_id)
            if quest_line:text+=f"\n\n📜 {quest_line['text']}"
        except Exception:pass
        return {"kind": "npc", "npc_id": npc_id, "dialogue_id": current_id, "text": text, "buttons": buttons}
    service_buttons = [[str(row.get("text"))] for row in owned_buttons("owner_npc", npc_id, platform=platform, player=player)]
    service_buttons.extend([[npc_service_label(row)] for row in npc_service_rows(npc)])
    service_buttons.extend([[f"Принять квест: {quest_id}"] for quest_id in npc.get("quest_ids") or []])
    if npc.get("combat_mob_id"):service_buttons.append(["Сразиться"])
    text=str(npc.get("first_message") or npc.get("description") or npc.get("name") or npc_id)
    try:
        from services.quest_runtime_service import npc_dialogue
        quest_line=npc_dialogue(player,npc_id)
        if quest_line:text+=f"\n\n📜 {quest_line['text']}"
    except Exception:pass
    return {"kind": "npc", "npc_id": npc_id, "dialogue_id": "", "text": text, "buttons": service_buttons + [["Завершить разговор"]]}


def try_handle_npc_action(player: dict[str, Any], action: str, *, platform: str | None = None) -> dict[str, Any] | None:
    npc_id = str(player.get("constructor_npc_id") or "")
    dialogue_id = str(player.get("constructor_npc_dialogue_id") or "")
    label = str(action or "").strip()
    if not npc_id or not label:
        return None
    if label == "Завершить разговор":
        return {"kind": "leave_npc", "location_id": str(player.get("constructor_location_id") or "")}
    npc = get_published(registry.KIND_NPC, npc_id)
    if not npc:
        return None
    service=next((row for row in npc_service_rows(npc) if npc_service_label(row)==label),None)
    if service:
        result=use_npc_service(player,npc,service);result["dialogue_id"]=dialogue_id;return result
    if label.startswith("Купить у NPC: "):
        try:text=npc_trade_buy(player,npc,label.split(":",1)[1].strip())
        except ValueError as exc:text=str(exc)
        return {"kind":"npc","npc_id":npc_id,"dialogue_id":dialogue_id,"text":text,"buttons":[[npc_service_label(row)] for row in npc_service_rows(npc)]+[["Завершить разговор"]]}
    if label.startswith("Принять квест: "):
        quest_id=label.split(":",1)[1].strip()
        try:
            from services.quest_runtime_service import accept
            result=accept(player,quest_id);text=str(result.get("text") or "Квест принят.")
        except ValueError as exc:
            legacy=get_published(registry.KIND_QUEST,quest_id)
            if legacy:player.setdefault("active_world_quests",{})[quest_id]={"status":"active","progress":0};text=str(legacy.get("accept_text") or legacy.get("description") or "Квест принят.")
            else:text=str(exc)
        current=render_npc(npc_id,player=player,dialogue_id=dialogue_id,platform=platform) or {"buttons":[["Завершить разговор"]]}
        return {**current,"text":text}
    if label=="Сразиться" and npc.get("combat_mob_id"):
        return {"kind":"npc_battle","npc_id":npc_id,"mob_id":str(npc.get("combat_mob_id")),"text":str(npc.get("battle_start_text") or "Начинается бой!"),"buttons":[]}
    owned = next((row for row in owned_buttons("owner_npc", npc_id, platform=platform, player=player)
                  if str(row.get("text") or "") == label), None)
    if owned:
        error = apply_button_consequences(player, owned)
        current = render_npc(npc_id, player=player, dialogue_id=dialogue_id, platform=platform) or {"buttons": []}
        return {**current, "text": error or str(owned.get("message") or owned.get("success_text") or "Действие выполнено.")}
    rows = [row for row in (npc.get("dialogues") or []) if isinstance(row, dict)]
    candidates = [row for row in rows if str(row.get("parent_id") or "") == dialogue_id]
    current = next((row for row in rows if str(row.get("id") or "") == dialogue_id), None)
    selected = next((row for row in candidates if label == str(row.get("player_button") or row.get("reply_button") or row.get("button_text") or "Продолжить")), None)
    if selected:
        next_id = str(selected.get("id") or "")
    elif current and current.get("next_id") and label == str(current.get("player_button") or current.get("reply_button") or current.get("button_text") or "Продолжить"):
        next_id = str(current.get("next_id") or "")
    else:
        return None
    return render_npc(npc_id, player=player, dialogue_id=next_id, platform=platform)


def roll_drop(mob_or_id: Any, *, rng: random.Random | None = None, enhanced: bool = False, event: bool = False) -> list[dict[str, Any]]:
    """Прокрутить таблицу дропа моба. Возвращает список {item_id, amount}.

    Чистая функция (rng инъектируется для тестов). Учитывает флаги строки
    «только усиленный» / «только событие».
    """
    rng = rng or random.Random()
    data = mob(mob_or_id) if isinstance(mob_or_id, str) else (mob_or_id or {})
    rows = (data or {}).get("drop")
    if not isinstance(rows, list):
        return []
    drops: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("only_enhanced") and not enhanced:
            continue
        if row.get("only_event") and not event:
            continue
        item_id = str(row.get("item_id") or "").strip()
        chance = _num(row.get("chance"), 0)
        if not item_id or chance <= 0:
            continue
        if rng.uniform(0, 100) <= chance:
            cmin = int(_num(row.get("min_count"), 1) or 1)
            cmax = int(_num(row.get("max_count"), cmin) or cmin)
            if cmax < cmin:
                cmax = cmin
            drops.append({"item_id": item_id, "amount": rng.randint(cmin, cmax)})
    return drops
