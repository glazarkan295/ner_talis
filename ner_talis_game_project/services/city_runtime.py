"""Рантайм города/крепости (ТЗ §4, «живой» слой конструктора города).

Чистое ЧТЕНИЕ опубликованного контента конструктора города (city_constructor):
узел + его кнопки/дочерние узлы/товары/сервисы — в виде, готовом для навигации
бота. Включается флагом окружения ``CITY_CONSTRUCTOR_LIVE`` (по умолчанию ВЫКЛ),
как ``WORLD_CONSTRUCTOR_LIVE`` у локаций: при выключенном флаге игра работает 1:1
как раньше (статическая городская логика city_service). Подключение к хендлерам
бота — отдельный аккуратный шаг; здесь — reader + предпросмотр для админки.
"""

from __future__ import annotations

import os
from typing import Any

from services import city_constructor_service as city


def live_enabled() -> bool:
    """«Живой» город включён?

    Источники (15-CODEX §5): env ``CITY_CONSTRUCTOR_LIVE`` (аварийный override)
    ИЛИ feature flag ``use_v2_buttons`` из админ-панели (городская навигация —
    кнопочная). По умолчанию ВЫКЛ — игра работает 1:1 как раньше."""
    raw=str(os.getenv("CITY_CONSTRUCTOR_LIVE", "")).strip().lower()
    if raw in {"0","false","no","off"}:return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    try:
        from services import feature_flags_service as ff

        if ff.is_enabled("use_v2_buttons"):return True
    except Exception:
        pass
    # Published root is itself the operator's activation decision. ENV=false is
    # retained as an emergency rollback, but a valid published city is live.
    try:return any(str((row.get("data") or {}).get("node_type") or "") in {"city","fortress"} for row in city.store().list(status=city.STATUS_PUBLISHED))
    except Exception:return False


def _published() -> list[dict[str, Any]]:
    return [i for i in city.store().list(status=city.STATUS_PUBLISHED)]


def _of_kind(items: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [i for i in items if (i.get("data") or {}).get("_kind") == kind]


def _order(env: dict[str, Any]) -> float:
    try:
        return float((env.get("data") or {}).get("order"))
    except (TypeError, ValueError):
        return 0.0


def published_node_ids() -> list[str]:
    return [n.get("id") for n in _of_kind(_published(), city.KIND_NODE)]


def root_nodes() -> list[dict[str, Any]]:
    """Опубликованные корневые узлы (город/крепость или без родителя)."""
    items = _published()
    nodes = _of_kind(items, city.KIND_NODE)
    ids = {n.get("id") for n in nodes}
    roots = [n for n in nodes if str((n.get("data") or {}).get("parent_id") or "") not in ids]
    roots.sort(key=_order)
    return [{"id": n.get("id"), "name": (n.get("data") or {}).get("name"), "type": (n.get("data") or {}).get("node_type")} for n in roots]

def _city_root_data(items:list[dict[str,Any]],node_id:str)->dict[str,Any]:
    nodes={str(row.get("id") or ""):row for row in _of_kind(items,city.KIND_NODE)};current=str(node_id);seen=set()
    while current and current not in seen:
        seen.add(current);env=nodes.get(current)
        if not env:return {}
        data=env.get("data") or {}
        if data.get("node_type")=="city":return {"id":current,**data}
        current=str(data.get("parent_id") or "")
    return {}


def node_runtime_view(node_id: str) -> dict[str, Any] | None:
    """Готовое представление узла для навигации бота: сам узел + кнопки (по
    порядку) + дочерние узлы + товары/сервисы/криминал, привязанные к узлу.
    Только опубликованное; неопубликованный/несуществующий узел → None."""
    nid = str(node_id or "").strip()
    if not nid:
        return None
    items = _published()
    node = next((n for n in _of_kind(items, city.KIND_NODE) if n.get("id") == nid), None)
    if node is None:
        return None
    data = node.get("data") or {}

    buttons = [b for b in _of_kind(items, city.KIND_BUTTON) if str((b.get("data") or {}).get("node_id") or "") == nid]
    buttons.sort(key=_order)
    children = [c for c in _of_kind(items, city.KIND_NODE) if str((c.get("data") or {}).get("parent_id") or "") == nid]
    children.sort(key=_order)
    shop_items = [s for s in _of_kind(items, city.KIND_SHOP_ITEM) if str((s.get("data") or {}).get("node_id") or "") == nid]
    services = [s for s in _of_kind(items, city.KIND_SERVICE) if str((s.get("data") or {}).get("node_id") or "") == nid]
    criminal = [s for s in _of_kind(items, city.KIND_CRIMINAL) if str((s.get("data") or {}).get("node_id") or "") == nid]
    root_city=_city_root_data(items,nid)
    def _links(key):
        return [dict(row) for row in root_city.get(key) or [] if isinstance(row,dict) and row.get("active",True) is not False and (not row.get("quarter_id") or str(row.get("quarter_id"))==nid or nid==str(root_city.get("id")))]

    def _btn(b: dict[str, Any]) -> dict[str, Any]:
        d = b.get("data") or {}
        return {
            "id": b.get("id"), "label": d.get("label"), "icon": d.get("icon"),
            "action": d.get("action"), "target_node_id": d.get("target_node_id"),
            "cost": d.get("cost"), "energy_cost": d.get("energy_cost"),
            "condition": d.get("condition"),
        }

    def _named(env: dict[str, Any], *keys: str) -> dict[str, Any]:
        d = env.get("data") or {}
        out = {"id": env.get("id")}
        for k in keys:
            out[k] = d.get(k)
        return out

    return {
        "id": node.get("id"),
        "name": data.get("name"),
        "node_type": data.get("node_type"),
        "description": data.get("description") or data.get("short_description") or "",
        "image": data.get("image"),
        "background": data.get("background"),
        "entry_message": data.get("entry_message"),
        "fortress": ({k: v for k, v in data.items() if k in {
            "fortress_type", "region", "parent_location_id", "parent_city_id", "danger_level",
            "safe", "partially_safe", "dangerous", "penalty", "military", "criminal",
            "available_to_all", "only_with_fine", "after_event_id", "after_quest_id",
            "min_reputation", "required_item_id", "after_raid", "after_transfer",
            "exit_allowed", "exit_after_fine_payment", "exit_via_npc", "exit_via_quest",
            "exit_via_battle", "exit_after_time", "punishment_seconds", "permanent_punishment",
            "accepts_fined_players", "accepts_after_raid", "accepts_after_third_fine",
            "allow_fine_payment", "allow_fine_removal_npc", "allow_fine_removal_admin",
            "safe_inside", "dangerous_inside", "mobs_allowed", "events_allowed",
            "pvp_allowed", "pvp_forbidden", "raids_allowed", "guard_active",
            "escape_possible", "escape_impossible", "death_returns_fortress",
            "death_returns_camp", "death_returns_city", "npc_ids", "event_ids",
            *city.FORTRESS_TEXT_FIELDS,
        }} if data.get("node_type") == "fortress" else None),
        "buttons": [_btn(b) for b in buttons],
        "children": [{"id": c.get("id"), "name": (c.get("data") or {}).get("name"), "node_type": (c.get("data") or {}).get("node_type")} for c in children],
        "shop_items": [_named(s, "item_id", "shop_kind", "price_buy", "price_sell", "currency", "can_buy", "can_sell") for s in shop_items],
        "services": [_named(s, "name", "service_kind", "enabled") for s in services],
        "criminal_zones": [_named(s, "name", "raid_chance", "fine_amount", "enter_text", "raid_text", "move_to_node", "restrictions") for s in criminal],
        "city":root_city or None,"sublocation_links":_links("sublocation_links"),"transition_links":_links("transition_links"),"npc_links":_links("npc_links"),"market_links":_links("market_links"),"workshop_links":_links("workshop_links"),"tavern_links":_links("tavern_links"),"event_links":_links("event_links"),"governance":_links("governance"),
    }


def _message_text(entry_message: Any) -> str:
    """Плоский текст из объекта вывода сообщения (для текста бота)."""
    if not isinstance(entry_message, dict):
        return ""
    if str(entry_message.get("format") or "single") == "multiple":
        parts = [str((b or {}).get("text") or "") for b in (entry_message.get("blocks") or []) if isinstance(b, dict)]
        return "\n\n".join(p for p in parts if p)
    return str(entry_message.get("text") or "")


def render_node(view: dict[str, Any]) -> dict[str, Any]:
    """Текст + кнопки узла для навигации бота из его рантайм-представления."""
    lines = [f"📍 {view.get('name') or ''}".strip()]
    fortress = view.get("fortress") or {}
    city_data=view.get("city") or {};body = fortress.get("entry_text") or (city_data.get("entry_text") or city_data.get("main_menu_text") if view.get("node_type")=="city" else "") or view.get("description") or ""
    msg = _message_text(view.get("entry_message"))
    if msg:
        body = (body + "\n\n" + msg).strip() if body else msg
    if body:
        lines.append(body)
    text = "\n\n".join(line for line in lines if line)
    # Кнопки: явные кнопки узла + переходы в дочерние узлы + возврат в город.
    rows: list[list[str]] = []
    for b in view.get("buttons") or []:
        label = str(b.get("label") or "").strip()
        if label:
            rows.append([(f"{b.get('icon')} {label}".strip()) if b.get("icon") else label])
    for c in view.get("children") or []:
        name = str(c.get("name") or "").strip()
        if name:
            rows.append([name])
    for row in view.get("sublocation_links") or []:rows.append([str(row.get("name") or f"Подлокация: {row.get('sublocation_id')}")])
    for row in view.get("transition_links") or []:rows.append([str(row.get("label") or f"Перейти: {row.get('target_id')}")])
    for row in view.get("npc_links") or []:rows.append([str(row.get("label") or f"NPC: {row.get('npc_id')}")])
    for row in view.get("market_links") or []:rows.append([str(row.get("label") or {"port":"Портовый рынок","black":"Чёрный рынок"}.get(str(row.get("market_type") or ""),"Рынок"))])
    for row in view.get("workshop_links") or []:rows.append([str(row.get("label") or row.get("name") or row.get("workshop_id"))])
    for row in view.get("tavern_links") or []:rows.append([str(row.get("name") or row.get("tavern_id"))])
    for row in view.get("event_links") or []:rows.append([str(row.get("label") or f"Событие: {row.get('event_id')}")])
    for row in view.get("governance") or []:
        if row.get("townhall_id"):rows.append([str(row.get("label") or "Ратуша")])
        if row.get("fine_payment"):rows.append(["Оплатить штрафы"])
    for row in view.get("criminal_zones") or []:rows.append([str(row.get("name") or row.get("id"))])
    try:
        from services.tavern_runtime import taverns_for_parent
        parent_type = "fortress" if view.get("node_type") == "fortress" or _fortress_for_node(str(view.get("id") or "")) else "city"
        rows.extend([[row["name"]] for row in taverns_for_parent(parent_type,str(view.get("id") or ""))])
    except Exception: pass
    if fortress.get("events_allowed"):
        for event_id in fortress.get("event_ids") or []:
            rows.append([f"Событие: {event_id}"])
    for npc_id in fortress.get("npc_ids") or []:
        rows.append([f"NPC: {npc_id}"])
    rows.append(["В город"])
    return {"text": text or (view.get("name") or "Локация"), "buttons": rows}


def _published_label_index() -> tuple[dict[str, str], dict[str, str]]:
    """Карты: имя узла → id узла; подпись кнопки goto → id целевого узла."""
    items = _published()
    node_by_name: dict[str, str] = {}
    for n in _of_kind(items, city.KIND_NODE):
        name = str((n.get("data") or {}).get("name") or "").strip()
        if name and name not in node_by_name:
            node_by_name[name] = n.get("id")
    button_to_target: dict[str, str] = {}
    for b in _of_kind(items, city.KIND_BUTTON):
        d = b.get("data") or {}
        label = str(d.get("label") or "").strip()
        target = str(d.get("target_node_id") or "").strip()
        icon = str(d.get("icon") or "").strip()
        if label and target:
            button_to_target.setdefault(label, target)
            if icon:
                button_to_target.setdefault(f"{icon} {label}", target)
    return node_by_name, button_to_target


def _button_target_on_node(node_id: str, action: str) -> str | None:
    """Цель кнопки-перехода с заданной подписью, ПРИВЯЗАННОЙ к конкретному узлу
    (Codex P2: одинаковые подписи «Назад»/«Войти» на разных узлах ведут в разные
    места — нельзя резолвить по глобальной карте подписей)."""
    if not node_id:
        return None
    for b in _of_kind(_published(), city.KIND_BUTTON):
        d = b.get("data") or {}
        if str(d.get("node_id") or "") != node_id:
            continue
        label = str(d.get("label") or "").strip()
        icon = str(d.get("icon") or "").strip()
        target = str(d.get("target_node_id") or "").strip()
        if target and action in (label, f"{icon} {label}".strip()):
            return target
    return None

def _action_button_on_node(node_id:str,label:str)->dict[str,Any]|None:
    for env in _of_kind(_published(),city.KIND_BUTTON):
        data=env.get("data") or {};text=str(data.get("label") or "").strip();icon=str(data.get("icon") or "").strip()
        if str(data.get("node_id") or "")==str(node_id) and label in {text,f"{icon} {text}".strip()}:return data
    return None

def _apply_button_cost(button:dict[str,Any],player:dict[str,Any])->str|None:
    condition=button.get("condition")
    if condition:
        key,sep,expected=str(condition).partition("=")
        if sep and str(player.get(key.strip()) or "")!=expected.strip():return str(button.get("denied_text") or "Кнопка сейчас недоступна.")
    energy=max(0,int(button.get("energy_cost") or 0));cost=max(0,int(button.get("cost") or 0));current_energy=int(player.get("energy") or player.get("current_energy") or 0);money=int(player.get("money") or player.get("money_copper") or 0)
    if current_energy<energy or money<cost:return str(button.get("denied_text") or "Не хватае энергии или денег.")
    if energy:player["energy"]=player["current_energy"]=current_energy-energy
    if cost:player["money"]=player["money_copper"]=money-cost
    return None


def _child_node_by_name(parent_id: str, label: str) -> str | None:
    """ID дочернего узла с заданным display name В КОНТЕКСТЕ текущего родителя
    (19-CODEX §3): одинаковые названия дочерних узлов у разных родителей не должны
    конфликтовать — клик «Таверна» в районе A открывает таверну именно района A."""
    if not parent_id or not label:
        return None
    for n in _of_kind(_published(), city.KIND_NODE):
        d = n.get("data") or {}
        if str(d.get("parent_id") or "") == parent_id and str(d.get("name") or "").strip() == label:
            return n.get("id")
    return None


def _has_active_fine(player: dict[str, Any]) -> bool:
    try:
        from services.fine_service import active_fines
        return bool(active_fines(player))
    except Exception:
        return bool(player.get("active_fine") or player.get("active_fines"))


def _fortress_access_error(data: dict[str, Any], player: dict[str, Any]) -> str | None:
    if data.get("available_to_all"):
        return None
    if data.get("only_with_fine") and not _has_active_fine(player):
        return str(data.get("denied_text") or "В крепость допускают только игроков со штрафом.")
    item = str(data.get("required_item_id") or "").strip()
    if item and not any(str(x.get("item_id") or x.get("id") or "") == item for x in (player.get("inventory") or []) if isinstance(x, dict)):
        return str(data.get("denied_text") or "Для входа нужен специальный предмет.")
    try:
        if data.get("min_reputation") not in (None, "") and float(player.get("reputation") or 0) < float(data["min_reputation"]):
            return str(data.get("denied_text") or "Недостаточно репутации для входа.")
    except (TypeError, ValueError):
        pass
    return None


def _fortress_exit_error(data: dict[str, Any], player: dict[str, Any]) -> str | None:
    if data.get("exit_allowed"):
        return None
    if data.get("exit_after_fine_payment") and _has_active_fine(player):
        return str(data.get("exit_denied_text") or "Выход закрыт до оплаты штрафа.")
    if data.get("exit_after_fine_payment") and not _has_active_fine(player):
        return None
    return str(data.get("exit_denied_text") or "Выход из крепости запрещён.")

def _node_access_error(data:dict[str,Any],player:dict[str,Any])->str|None:
    denied=str(data.get("denied_text") or data.get("quarter_denied_text") or "Эта часть города вам недоступна.")
    if data.get("active") is False:return denied
    if int(player.get("level") or 1)<int(data.get("required_level") or 0):return denied
    item=str(data.get("required_item_id") or "")
    if item and not any(str(x.get("item_id") or x.get("id") or "")==item for x in player.get("inventory") or [] if isinstance(x,dict)):return denied
    if data.get("requires_no_fine") and _has_active_fine(player):return denied
    rep=str(data.get("required_reputation_id") or "")
    if rep:
        try:
            from services.reputation_runtime_service import value
            if value(player,rep)<float(data.get("required_reputation_value") or 0):return denied
        except Exception:return denied
    return None


def _fortress_for_node(node_id: str) -> dict[str, Any] | None:
    """Корневая крепость для любой внутренней зоны, с защитой от циклов."""
    items = _of_kind(_published(), city.KIND_NODE)
    by_id = {str(row.get("id") or ""): row for row in items}
    current = str(node_id or "")
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        env = by_id.get(current)
        if not env:
            return None
        data = env.get("data") or {}
        if data.get("node_type") == "fortress":
            view = node_runtime_view(current)
            return (view or {}).get("fortress")
        current = str(data.get("parent_id") or "")
    return None


def try_handle(action: str, current_node_id: str | None = None, *, player: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """«Живая» навигация по опубликованным узлам (ТЗ §4). Сначала — кнопка-переход
    с этой подписью НА ТЕКУЩЕМ узле, затем — узел по имени. Иначе None → легаси.
    Только при включённом флаге."""
    if not live_enabled():
        return None
    act = str(action or "").strip()
    if not act:
        return None
    current_view = node_runtime_view(str(current_node_id or "")) if current_node_id else None
    current_fortress = _fortress_for_node(str(current_node_id or "")) or {}
    if player is not None and current_fortress and act in {"В город", "Выйти", "Выход", "Наружу"}:
        denied = _fortress_exit_error(current_fortress, player)
        if denied:
            return {"text": denied, "buttons": render_node(current_view)["buttons"], "node_id": current_node_id}
    if player is not None and current_fortress and act.startswith("NPC: "):
        from services.world_runtime import render_npc
        response = render_npc(act.removeprefix("NPC: ").strip(), player=player)
        if response:
            return {"text": response.get("text") or "", "buttons": response.get("buttons") or [], "node_id": current_node_id}
    if player is not None and current_fortress and act.startswith("Событие: "):
        from services.world_runtime import render_event
        event_id = act.removeprefix("Событие: ").strip()
        response = render_event(event_id, player=player)
        if response:
            player["constructor_event_id"] = event_id
            return {"text": response.get("text") or "", "buttons": response.get("buttons") or [], "node_id": current_node_id}
    if player is not None and current_view:
        for row in current_view.get("criminal_zones") or []:
            if act!=str(row.get("name") or row.get("id")):continue
            import random
            raided=random.random()*100<float(row.get("raid_chance") or 0);text=str(row.get("enter_text") or f"Вы входите в зону «{row.get('name')}».")
            if raided:
                from services.fine_service import create_raid_fine
                fine=create_raid_fine(player,str(row.get("id") or "criminal_zone"));amount=max(0,int(row.get("fine_amount") or 0))
                if amount:fine["current_amount"]=fine["original_amount"]=amount
                text=str(row.get("raid_text") or "Началась облава. Вам выписан штраф.")
            return {"text":text,"buttons":render_node(current_view)["buttons"],"node_id":current_node_id}
        for row in current_view.get("npc_links") or []:
            if act==str(row.get("label") or f"NPC: {row.get('npc_id')}"):
                from services.world_runtime import render_npc
                response=render_npc(str(row.get("npc_id") or ""),player=player)
                if response:return {"text":response.get("text") or "","buttons":response.get("buttons") or [],"node_id":current_node_id}
        for row in current_view.get("sublocation_links") or []:
            if act==str(row.get("name") or f"Подлокация: {row.get('sublocation_id')}"):
                from services.world_runtime import render_sublocation
                response=render_sublocation(str(row.get("sublocation_id") or ""),player=player)
                if response:return {"text":response.get("text") or "","buttons":response.get("buttons") or [],"node_id":current_node_id}
        for row in current_view.get("event_links") or []:
            if act==str(row.get("label") or f"Событие: {row.get('event_id')}"):
                from services.world_runtime import render_event
                response=render_event(str(row.get("event_id") or ""),player=player)
                if response:return {"text":response.get("text") or "","buttons":response.get("buttons") or [],"node_id":current_node_id}
        for row in current_view.get("market_links") or []:
            label=str(row.get("label") or {"port":"Портовый рынок","black":"Чёрный рынок"}.get(str(row.get("market_type") or ""),"Рынок"))
            if act==label:return {"delegate_action":label,"node_id":current_node_id}
        for row in current_view.get("workshop_links") or []:
            label=str(row.get("label") or row.get("name") or row.get("workshop_id") or "")
            if act==label:return {"delegate_action":label,"node_id":current_node_id}
        for row in current_view.get("transition_links") or []:
            if act!=str(row.get("label") or f"Перейти: {row.get('target_id')}"):continue
            target_type=str(row.get("target_type") or "");target=str(row.get("target_id") or "")
            error=str(row.get("error_text") or "Условия перехода не выполнены.");required_item=str(row.get("required_item_id") or "");required_quest=str(row.get("required_quest_id") or "");required_rep=str(row.get("required_reputation_id") or "")
            if required_item and not any(str(x.get("item_id") or x.get("id") or "")==required_item for x in player.get("inventory") or [] if isinstance(x,dict)):return {"text":error,"buttons":render_node(current_view)["buttons"],"node_id":current_node_id}
            if required_quest and required_quest not in ((player.get("quests") or {}).get("completed") or {}):return {"text":error,"buttons":render_node(current_view)["buttons"],"node_id":current_node_id}
            if required_rep:
                try:
                    from services.reputation_runtime_service import value
                    if value(player,required_rep)<float(row.get("required_reputation_value") or 0):return {"text":error,"buttons":render_node(current_view)["buttons"],"node_id":current_node_id}
                except Exception:return {"text":error,"buttons":render_node(current_view)["buttons"],"node_id":current_node_id}
            energy=max(0,int(row.get("energy_cost") or 0));cost=max(0,int(row.get("currency_cost") or 0))
            if int(player.get("energy") or player.get("current_energy") or 0)<energy or int(player.get("money") or player.get("money_copper") or 0)<cost:return {"text":error,"buttons":render_node(current_view)["buttons"],"node_id":current_node_id}
            if energy:player["energy"]=max(0,int(player.get("energy") or player.get("current_energy") or 0)-energy);player["current_energy"]=player["energy"]
            if cost:player["money"]=max(0,int(player.get("money") or player.get("money_copper") or 0)-cost);player["money_copper"]=player["money"]
            if target_type in {"city","fortress"}:
                view=node_runtime_view(target)
                if view:return {**render_node(view),"node_id":target}
            if target_type=="sublocation":
                from services.world_runtime import render_sublocation
                response=render_sublocation(target,player=player)
                if response:return {"text":response.get("text") or "","buttons":response.get("buttons") or [],"node_id":current_node_id}
            return {"text":str(row.get("transition_text") or "Переход выполнен."),"buttons":render_node(current_view)["buttons"],"node_id":current_node_id,"target_type":target_type,"target_id":target}
    # 1) Кнопка-переход на текущем узле (контекстно — без коллизий подписей).
    node_id = _button_target_on_node(str(current_node_id or ""), act)
    clicked=_action_button_on_node(str(current_node_id or ""),act)
    if clicked and player is not None:
        denied=_apply_button_cost(clicked,player)
        if denied:return {"text":denied,"buttons":render_node(current_view)["buttons"] if current_view else [],"node_id":current_node_id}
    # 2) Дочерний узел ТЕКУЩЕГО родителя по display name (19-CODEX §3) — раньше
    #    глобального поиска, чтобы одинаковые названия детей не конфликтовали.
    if not node_id and current_node_id:
        node_id = _child_node_by_name(str(current_node_id), act)
    # 3) Имя узла глобально (вход в узел по его названию).
    if not node_id:
        node_by_name, button_to_target = _published_label_index()
        node_id = node_by_name.get(act)
        # 4) Глобальный фолбэк по подписи кнопки — только если текущий узел неизвестен.
        if not node_id and not current_node_id:
            node_id = button_to_target.get(act)
    if not node_id:
        button=clicked or _action_button_on_node(str(current_node_id or ""),act)
        if button and str(button.get("action") or "")!="goto_node":
            mapped={"open_market":"Рынок","open_craft":"Ремесленный квартал","open_alchemy":"Алхимическая мастерская","start_fishing":"Рыбалка","open_fines":"Оплатить штрафы","open_board":"Доска заданий","open_quests":"Задания"}.get(str(button.get("action") or ""),str(button.get("target_action") or ""))
            if mapped:return {"delegate_action":mapped,"node_id":current_node_id}
        return None
    view = node_runtime_view(node_id)
    if view is None:
        return None
    if player is not None:
        denied=_node_access_error(view.get("city") if view.get("node_type")=="city" else next(((x.get("data") or {}) for x in _of_kind(_published(),city.KIND_NODE) if str(x.get("id"))==str(node_id)),{}),player)
        if denied:return {"text":denied,"buttons":render_node(current_view)["buttons"] if current_view else [["В город"]],"node_id":current_node_id or ""}
    if player is not None and view.get("fortress"):
        denied = _fortress_access_error(view["fortress"], player)
        if denied:
            return {"text": denied, "buttons": [["В город"]], "node_id": current_node_id or ""}
    # node_id возвращаем, чтобы вызывающий сохранил текущий V2-узел на игроке
    # (15-CODEX §1) — иначе следующая кнопка («Назад») потеряет контекст.
    return {**render_node(view), "node_id": node_id}
