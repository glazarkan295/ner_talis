"""FastAPI routers for addiction & tolerance constructors (ТЗ эффектов §4–§5).

Built on the shared factory; reuse effect.* permissions (effect subsystems).
Extra endpoints: addiction /{id}/stage (stage for a value), tolerance
/{id}/effectiveness (effectiveness % for a value).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import addiction_constructor_service as addiction
from services import tolerance_constructor_service as tolerance
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_EFFECT_ARCHIVE, PERM_EFFECT_CREATE, PERM_EFFECT_DELETE, PERM_EFFECT_DISABLE,
    PERM_EFFECT_EDIT, PERM_EFFECT_PUBLISH, PERM_EFFECT_VALIDATE, PERM_EFFECT_VIEW,
    require_permission,
)

_PERMS = {
    "view": PERM_EFFECT_VIEW, "create": PERM_EFFECT_CREATE, "edit": PERM_EFFECT_EDIT,
    "validate": PERM_EFFECT_VALIDATE, "publish": PERM_EFFECT_PUBLISH,
    "disable": PERM_EFFECT_DISABLE, "archive": PERM_EFFECT_ARCHIVE, "delete": PERM_EFFECT_DELETE,
}


class _ValueBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    value: float = 0


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def _guard(get_storage, request: Request, token: str | None) -> None:
    effective = _bearer(request) or str(token or "").strip()
    if not effective:
        raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
    try:
        session = require_admin_session(get_storage(), effective)
        require_permission(session, PERM_EFFECT_VIEW)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def create_admin_addiction_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/addictions", tags=["admin-addictions"],
        svc=addiction, perms=_PERMS, target_type="addiction", name_field="name_admin",
        not_found="Зависимость не найдена.",
        meta_extra=lambda _s: {"scopes": list(addiction.ADDICTION_SCOPES),
                               "gainOn": list(addiction.GAIN_ON),
                               "visibilityModes": list(addiction.VISIBILITY_MODES)},
    )

    @router.post("/{addiction_id}/stage")
    def stage(addiction_id: str, payload: _ValueBody, request: Request) -> dict[str, Any]:
        _guard(get_storage, request, payload.token)
        item = addiction.store().get(addiction_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Зависимость не найдена.")
        return {"ok": True, "stage": addiction.stage_for_value(item.get("data") or {}, payload.value)}

    return router


def create_admin_tolerance_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage, prefix="/api/admin/v2/tolerances", tags=["admin-tolerances"],
        svc=tolerance, perms=_PERMS, target_type="tolerance", name_field="name_admin",
        not_found="Привыкание не найдено.",
        meta_extra=lambda _s: {"scopes": list(tolerance.TOLERANCE_SCOPES)},
    )

    @router.post("/{tolerance_id}/effectiveness")
    def effectiveness(tolerance_id: str, payload: _ValueBody, request: Request) -> dict[str, Any]:
        _guard(get_storage, request, payload.token)
        item = tolerance.store().get(tolerance_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Привыкание не найдено.")
        return {"ok": True, "effectiveness": tolerance.effectiveness(item.get("data") or {}, payload.value)}

    return router
