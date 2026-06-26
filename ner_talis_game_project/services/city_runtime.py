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
    """«Живой» город включён? (ENV CITY_CONSTRUCTOR_LIVE, по умолчанию выкл.)"""
    return str(os.getenv("CITY_CONSTRUCTOR_LIVE", "")).strip().lower() in {"1", "true", "yes", "on"}


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
        "buttons": [_btn(b) for b in buttons],
        "children": [{"id": c.get("id"), "name": (c.get("data") or {}).get("name"), "node_type": (c.get("data") or {}).get("node_type")} for c in children],
        "shop_items": [_named(s, "item_id", "shop_kind", "price_buy", "price_sell", "currency", "can_buy", "can_sell") for s in shop_items],
        "services": [_named(s, "name", "service_kind", "enabled") for s in services],
        "criminal_zones": [_named(s, "name", "raid_chance", "fine_amount") for s in criminal],
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
    body = view.get("description") or ""
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


def try_handle(action: str, current_node_id: str | None = None) -> dict[str, Any] | None:
    """«Живая» навигация по опубликованным узлам (ТЗ §4). Сначала — кнопка-переход
    с этой подписью НА ТЕКУЩЕМ узле, затем — узел по имени. Иначе None → легаси.
    Только при включённом флаге."""
    if not live_enabled():
        return None
    act = str(action or "").strip()
    if not act:
        return None
    # 1) Кнопка-переход на текущем узле (контекстно — без коллизий подписей).
    target = _button_target_on_node(str(current_node_id or ""), act)
    node_id = target
    # 2) Имя узла (вход в узел по его названию).
    if not node_id:
        node_by_name, button_to_target = _published_label_index()
        node_id = node_by_name.get(act)
        # 3) Глобальный фолбэк по подписи кнопки — только если текущий узел неизвестен.
        if not node_id and not current_node_id:
            node_id = button_to_target.get(act)
    if not node_id:
        return None
    view = node_runtime_view(node_id)
    if view is None:
        return None
    return render_node(view)
