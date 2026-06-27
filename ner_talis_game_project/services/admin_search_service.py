"""Глобальный поиск по админ-панели (ТЗ 11 §4.2).

Лёгкий поиск по названию/ID всех редактируемых сущностей, сгруппированный по
типу. Переиспользует описания источников из admin_graph_service (world-реестр,
конструкторы на EntityStore, реестры сайта/профиля с тегом _kind), но не строит
рёбра и не валидирует — только сопоставление строки, чтобы поиск был быстрым.
"""

from __future__ import annotations

import importlib
from typing import Any

from services import admin_graph_service as graph
from services import world_content_registry as wcr

DEFAULT_LIMIT = 8  # элементов на группу


def _title(data: dict[str, Any], fallback: str, *extra: str) -> str:
    for key in (*extra, "name", "title", "label", "question", "race_name",
                "city_name", "effect_name", "trait_name", "blessing_name",
                "skill_name", "admin_name"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _matches(q: str, eid: str, title: str) -> bool:
    return q in eid.lower() or q in title.lower()


def search(query: str, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Найти сущности по подстроке в названии/ID, сгруппировать по типу."""
    q = str(query or "").strip().lower()
    if len(q) < 2:
        return {"query": query, "groups": [], "total": 0}
    by_type: dict[str, list[dict[str, Any]]] = {}
    total = 0

    def _add(node_type: str, eid: str, title: str, status: Any) -> None:
        nonlocal total
        bucket = by_type.setdefault(node_type, [])
        if len(bucket) >= limit:
            bucket_full[node_type] = True
            return
        bucket.append({"id": f"{node_type}:{eid}", "entity_id": eid,
                       "type": node_type, "title": title, "status": status})
        total += 1

    bucket_full: dict[str, bool] = {}

    # Мир.
    for kind in wcr.KINDS:
        try:
            for env in wcr.list_content(kind):
                eid = str(env.get("id") or "")
                data = env.get("data") or {}
                title = _title(data, eid)
                if eid and _matches(q, eid, title):
                    _add(kind, eid, title, env.get("status"))
        except Exception:
            continue

    # Конструкторы на EntityStore.
    for node_type, module_name, title_field in graph.CONSTRUCTOR_SOURCES:
        try:
            svc = importlib.import_module(f"services.{module_name}")
            for env in svc.store().list():
                eid = str(env.get("id") or "")
                data = env.get("data") or {}
                title = _title(data, eid, title_field)
                if eid and _matches(q, eid, title):
                    _add(node_type, eid, title, env.get("status"))
        except Exception:
            continue

    # Реестры с _kind (сайт/профиль).
    for prefix, module_name, kind_is_full in graph.KINDED_SOURCES:
        try:
            svc = importlib.import_module(f"services.{module_name}")
            for env in svc.store().list():
                eid = str(env.get("id") or "")
                data = env.get("data") or {}
                kind = str(data.get("_kind") or "")
                if not eid or not kind:
                    continue
                node_type = kind if kind_is_full else f"{prefix}{kind}"
                title = _title(data, eid)
                if _matches(q, eid, title):
                    _add(node_type, eid, title, env.get("status"))
        except Exception:
            continue

    groups = [{
        "type": t,
        "label": graph.NODE_TYPE_LABELS.get(t, t),
        "items": items,
        "truncated": bool(bucket_full.get(t)),
    } for t, items in sorted(by_type.items(), key=lambda kv: graph.NODE_TYPE_LABELS.get(kv[0], kv[0]))]
    return {"query": query, "groups": groups, "total": total}
