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
