"""FastAPI router for the global admin search (ТЗ 11 §4.2).

GET /api/admin/v2/search?q=… — entities matched by title/ID, grouped by type.
Read-only; guarded by the graph.view permission (any content viewer).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from services import admin_search_service as search_svc
from services.admin_panel_service import require_admin_session
from services.admin_rbac import PERM_GRAPH_VIEW, require_permission


def _bearer_token(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def _guard(storage: Any, request: Request | None, token: str | None) -> None:
    effective = _bearer_token(request) or str(token or "").strip()
    if not effective:
        raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
    try:
        session = require_admin_session(storage, effective)
        require_permission(session, PERM_GRAPH_VIEW)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def create_admin_search_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/search", tags=["admin-search"])

    @router.get("")
    def global_search(
        request: Request,
        q: str = Query(default=""),
        limit: int = Query(default=8, ge=1, le=30),
        token: str | None = Query(default=None, min_length=16),
    ) -> dict[str, Any]:
        _guard(get_storage(), request, token)
        return {"ok": True, **search_svc.search(q, limit=limit)}

    return router
