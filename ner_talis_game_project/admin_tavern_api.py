"""FastAPI router for the Tavern constructor (ТЗ таверны).

CRUD/lifecycle/versioning via the shared factory; adds a player-view preview
endpoint (§21). Guarded by tavern.* permissions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import tavern_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_TAVERN_ARCHIVE, PERM_TAVERN_CREATE, PERM_TAVERN_DELETE, PERM_TAVERN_DISABLE,
    PERM_TAVERN_EDIT, PERM_TAVERN_PUBLISH, PERM_TAVERN_VALIDATE, PERM_TAVERN_VIEW,
    require_permission,
)

_PERMS = {
    "view": PERM_TAVERN_VIEW, "create": PERM_TAVERN_CREATE, "edit": PERM_TAVERN_EDIT,
    "validate": PERM_TAVERN_VALIDATE, "publish": PERM_TAVERN_PUBLISH,
    "disable": PERM_TAVERN_DISABLE, "archive": PERM_TAVERN_ARCHIVE, "delete": PERM_TAVERN_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "tavernTypes": [{"value": t, "label": svc.TAVERN_TYPE_LABELS.get(t, t)} for t in svc.TAVERN_TYPES],
        "tavernModes": list(svc.TAVERN_MODES),
        "serviceTypes": list(svc.SERVICE_TYPES),
        "menuCategories": list(svc.MENU_CATEGORIES),
        "rumorTypes": list(svc.RUMOR_TYPES),
        "eventTypes": list(svc.EVENT_TYPES),
        "riskTypes": list(svc.RISK_TYPES),
        "scheduleModes": list(svc.SCHEDULE_MODES),
        "currencies": list(svc.CURRENCIES),
        "statKeys": [{"value": s, "label": svc.STAT_LABELS.get(s, s)} for s in svc.STAT_KEYS],
        "foodTypes": [{"value": f, "label": svc.FOOD_TYPE_LABELS.get(f, f)} for f in svc.FOOD_TYPES],
        "maxWorkReductionPercent": svc.MAX_WORK_REDUCTION_PERCENT,
    }


class _PreviewBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    mock: dict[str, Any] | None = None


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_tavern_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/taverns",
        tags=["admin-taverns"],
        svc=svc,
        perms=_PERMS,
        target_type="tavern",
        name_field="name",
        not_found="Таверна не найдена.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_TAVERN_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{tavern_id}/preview")
    def preview(tavern_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(tavern_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Таверна не найдена.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {}, payload.mock)}

    return router
