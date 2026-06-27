"""FastAPI router for the admin dashboard (ТЗ 11 §16).

Mounted under ``/api/admin/v2/dashboard``. Read-only aggregate for the home
screen: entity counts, active errors/link/image issues, recent changes, active
world events, last import. Available to any authenticated admin (the home page),
each metric computed best-effort.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from services import admin_dashboard_service as dash
from services.admin_panel_service import require_admin_session


def _bearer_token(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_dashboard_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/dashboard", tags=["admin-dashboard"])

    @router.get("")
    def dashboard(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        effective = _bearer_token(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        storage = get_storage()
        try:
            require_admin_session(storage, effective)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {"ok": True, **dash.summary(storage)}

    return router
