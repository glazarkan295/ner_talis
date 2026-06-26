"""FastAPI router for the Sublocation constructor helpers (ТЗ 09 §2–§14).

CRUD/lifecycle/versioning for the kinds ``sublocation`` /
``sublocation_node`` / ``sublocation_transition`` is served generically by the
world router (``/api/admin/v2/world/{kind}``). This router adds the pieces the
generic one can't: constructor metadata, the structural schema check (§13) and
a compact nodes+transitions view for the visual editor (§13). Read-only,
guarded by world.view.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from services import world_content_registry as registry
from services.admin_panel_service import require_admin_session
from services.admin_rbac import PERM_WORLD_VIEW, require_permission


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
        require_permission(session, PERM_WORLD_VIEW)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return session


def create_admin_sublocation_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/sublocations", tags=["admin-sublocations"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        return {
            "ok": True,
            "sublocationTypes": list(registry.SUBLOCATION_TYPES),
            "nodeTypes": list(registry.SUBLOCATION_NODE_TYPES),
            "accessConditions": list(registry.ACCESS_CONDITIONS),
            "statuses": [{"value": s, "label": registry.STATUS_LABELS.get(s, s)}
                         for s in registry.STATUS_LABELS],
        }

    @router.get("/{sublocation_id}/schema")
    def schema(sublocation_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        if registry.get_content(registry.KIND_SUBLOCATION, sublocation_id) is None:
            raise HTTPException(status_code=404, detail="Подлокация не найдена.")
        return {"ok": True, "schema": registry.validate_sublocation_schema(sublocation_id)}

    @router.get("/{sublocation_id}/nodes")
    def nodes(sublocation_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        node_items = [n for n in registry.list_content(registry.KIND_SUBLOCATION_NODE)
                      if str((n.get("data") or {}).get("sublocation_id") or "") == sublocation_id]
        transitions = [t for t in registry.list_content(registry.KIND_SUBLOCATION_TRANSITION)
                       if str((t.get("data") or {}).get("sublocation_id") or "") == sublocation_id]
        return {"ok": True, "nodes": node_items, "transitions": transitions}

    return router
