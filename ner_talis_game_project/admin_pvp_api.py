"""FastAPI router for the future-PVP constructor (ТЗ 4 §1).

CRUD/lifecycle/versioning via the shared factory; adds a render-preview endpoint
(§1.7). Guarded by pvp.* permissions. Mounted under ``/api/admin/v2/pvp``.
PVP runtime does not exist yet — this is the authoring layer only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import pvp_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_PVP_ARCHIVE, PERM_PVP_CREATE, PERM_PVP_DELETE, PERM_PVP_DISABLE,
    PERM_PVP_EDIT, PERM_PVP_PUBLISH, PERM_PVP_VALIDATE, PERM_PVP_VIEW,
    require_permission,
)

_PERMS = {
    "view": PERM_PVP_VIEW, "create": PERM_PVP_CREATE, "edit": PERM_PVP_EDIT,
    "validate": PERM_PVP_VALIDATE, "publish": PERM_PVP_PUBLISH,
    "disable": PERM_PVP_DISABLE, "archive": PERM_PVP_ARCHIVE,
    "delete": PERM_PVP_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "pvpTypes": [{"value": t, "label": svc.PVP_TYPE_LABELS.get(t, t)} for t in svc.PVP_TYPES],
        "buttonActions": [{"value": a, "label": svc.PVP_BUTTON_LABELS.get(a, a)} for a in svc.PVP_BUTTON_ACTIONS],
        "conditionTypes": list(svc.CONDITION_TYPES),
        "textKeys": list(svc.TEXT_KEYS),
        "timeoutActions": list(svc.PVP_TIMEOUT_ACTIONS),
        "actionOrderTypes": list(svc.ACTION_ORDER_TYPES),
        "logModes": list(svc.LOG_MODES),
    }


class _PreviewBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    data: dict[str, Any] | None = None


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_pvp_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/pvp",
        tags=["admin-pvp"],
        svc=svc,
        perms=_PERMS,
        target_type="pvp",
        name_field="name",
        not_found="PVP-правило не найдено.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_PVP_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{pvp_id}/preview")
    def preview(pvp_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(pvp_id)
        if item is None:
            raise HTTPException(status_code=404, detail="PVP-правило не найдено.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {})}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.preview(payload.data or {})}

    return router
