"""FastAPI router for V2 feature flags (full-import ТЗ §14, AC#12).

Mounted under ``/api/admin/v2/feature-flags``. Lets admins gradually switch the
game to read V2-constructor data per domain (use_v2_*), keeping old code as
fallback. Viewing needs system.view; toggling a flag flips the live data source
for a domain → requires system.manage and is audited (dangerous).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_operation import run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_SYSTEM_MANAGE,
    PERM_SYSTEM_VIEW,
    require_permission,
)
from services import feature_flags_service as ff


class FlagRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    name: str = ""
    enabled: bool = False
    reason: str = ""


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


def _session(storage: Any, request: Request | None, token: str | None) -> dict[str, Any]:
    effective_token = _bearer_token(request) or str(token or "").strip()
    if not effective_token:
        raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
    try:
        return require_admin_session(storage, effective_token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _require(session: dict[str, Any], permission: str) -> str:
    try:
        return require_permission(session, permission)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def create_admin_feature_flags_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/feature-flags", tags=["admin-feature-flags"])

    @router.get("")
    def list_flags(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_SYSTEM_VIEW)
        return {"ok": True, "flags": ff.all_flags(), "meta": ff.meta()["flags"]}

    @router.put("")
    def set_flag(payload: FlagRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_SYSTEM_MANAGE)
        name = str(payload.name or "").strip()
        if name not in ff.FLAG_LABELS:
            raise HTTPException(status_code=400, detail=f"Неизвестный feature flag: {name}")
        before = ff.is_enabled(name)
        flags = run_admin_operation(
            session=session, action="system.feature_flag",
            func=lambda: ff.set_flag(name, payload.enabled),
            target_type="feature_flag", target_id=name,
            before={"enabled": before}, after_func=lambda r: {"enabled": r.get(name)},
            reason=payload.reason,
        )
        return {"ok": True, "flags": flags}

    return router
