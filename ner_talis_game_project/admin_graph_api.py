"""FastAPI router for the Admin V2 interactive graph (ТЗ 12, backend).

Mounted under ``/api/admin/v2/graph``. Read-only aggregation of every game
entity into one nodes/edges graph, served in several modes:

- GET /                — full map (optional ?types=&statuses= filters)
- GET /legend          — node/edge type labels for the UI legend
- GET /around/{id}     — subgraph around an object (?depth=)
- GET /errors          — only broken/orphan nodes and edges
- GET /location/{id}   — one location and its immediate neighbours
- GET /path?source&target — shortest connection path between two objects
- GET /node/{id}       — side-card detail (incoming/outgoing/used-by)
- GET /validate        — graph health summary (broken edges, orphans)

All endpoints require the graph.view permission. Node ids are "<type>:<id>".
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from services import admin_graph_service as graph
from services.admin_panel_service import require_admin_session
from services.admin_rbac import PERM_GRAPH_VIEW, require_permission


def _bearer_token(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not value.strip():
        return ""
    return value.strip()


def _guard(storage: Any, request: Request | None, token: str | None) -> dict[str, Any]:
    effective_token = _bearer_token(request) or str(token or "").strip()
    if not effective_token:
        raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
    try:
        session = require_admin_session(storage, effective_token)
        require_permission(session, PERM_GRAPH_VIEW)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return session


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    out = [p.strip() for p in str(value).split(",") if p.strip()]
    return out or None


def create_admin_graph_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/graph", tags=["admin-graph"])

    @router.get("/legend")
    def legend(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        return {"ok": True, **graph.legend()}

    @router.get("")
    def full(
        request: Request,
        token: str | None = Query(default=None, min_length=16),
        types: str | None = Query(default=None),
        statuses: str | None = Query(default=None),
    ) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        result = graph.full_graph(types=_split(types), statuses=_split(statuses))
        return {"ok": True, **result}

    @router.get("/errors")
    def errors(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        return {"ok": True, **graph.error_graph()}

    @router.get("/validate")
    def validate(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        return {"ok": True, **graph.validate_graph()}

    @router.get("/path")
    def path(
        request: Request,
        source: str = Query(min_length=3),
        target: str = Query(min_length=3),
        token: str | None = Query(default=None, min_length=16),
    ) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        return {"ok": True, **graph.path_graph(source, target)}

    @router.get("/location/{location_id}")
    def location(location_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        return {"ok": True, **graph.location_graph(location_id)}

    @router.get("/around/{node_type}/{entity_id}")
    def around(
        node_type: str,
        entity_id: str,
        request: Request,
        token: str | None = Query(default=None, min_length=16),
        depth: int = Query(default=2, ge=1, le=6),
    ) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        return {"ok": True, **graph.graph_around(graph.node_id(node_type, entity_id), depth=depth)}

    @router.get("/node/{node_type}/{entity_id}")
    def node(node_type: str, entity_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        detail = graph.node_detail(graph.node_id(node_type, entity_id))
        if detail is None:
            raise HTTPException(status_code=404, detail="Объект схемы не найден.")
        return {"ok": True, **detail}

    @router.get("/export")
    def export(
        request: Request,
        token: str | None = Query(default=None, min_length=16),
        mode: str = Query(default="full"),
        format: str = Query(default="json"),
        focus: str | None = Query(default=None),
        location_id: str | None = Query(default=None),
        source: str | None = Query(default=None),
        target: str | None = Query(default=None),
        types: str | None = Query(default=None),
        statuses: str | None = Query(default=None),
    ) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        result = graph.export(
            mode, fmt=format, focus=focus, location_id=location_id,
            source=source, target=target, types=_split(types), statuses=_split(statuses),
        )
        return {"ok": True, **result}

    return router
