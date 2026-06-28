"""FastAPI router for the Workshop message constructor (ТЗ 14).

CRUD/lifecycle/versioning via the shared factory; adds preview endpoints (§12):
- POST /{id}/preview  — render a saved template with an optional test state
- POST /preview        — render an ad-hoc template (data) with a test state
Guarded by workshop_message.* permissions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import workshop_message_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_WORKSHOP_MSG_ARCHIVE, PERM_WORKSHOP_MSG_CREATE, PERM_WORKSHOP_MSG_DELETE,
    PERM_WORKSHOP_MSG_DISABLE, PERM_WORKSHOP_MSG_EDIT, PERM_WORKSHOP_MSG_PUBLISH,
    PERM_WORKSHOP_MSG_VALIDATE, PERM_WORKSHOP_MSG_VIEW, require_permission,
)

_PERMS = {
    "view": PERM_WORKSHOP_MSG_VIEW, "create": PERM_WORKSHOP_MSG_CREATE, "edit": PERM_WORKSHOP_MSG_EDIT,
    "validate": PERM_WORKSHOP_MSG_VALIDATE, "publish": PERM_WORKSHOP_MSG_PUBLISH,
    "disable": PERM_WORKSHOP_MSG_DISABLE, "archive": PERM_WORKSHOP_MSG_ARCHIVE,
    "delete": PERM_WORKSHOP_MSG_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "blockTypes": [{"value": b, "label": svc.BLOCK_LABELS.get(b, b)} for b in svc.BLOCK_TYPES],
        "scopes": [{"value": s, "label": svc.SCOPE_LABELS.get(s, s)} for s in svc.SCOPES],
        "groupingModes": list(svc.GROUPING_MODES),
        "sortModes": list(svc.SORT_MODES),
        "unavailableDisplay": list(svc.UNAVAILABLE_DISPLAY),
        "sendFormats": list(svc.SEND_FORMATS),
        "placeholders": sorted(svc.KNOWN_PLACEHOLDERS),
    }


class _PreviewBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    state: dict[str, Any] | None = None


class _PreviewDataBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    data: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] | None = None


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_workshop_message_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/workshop-messages",
        tags=["admin-workshop-messages"],
        svc=svc,
        perms=_PERMS,
        target_type="workshop_message",
        name_field="name",
        not_found="Шаблон сообщения не найден.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_WORKSHOP_MSG_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{template_id}/preview")
    def preview(template_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(template_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Шаблон сообщения не найден.")
        return {"ok": True, "preview": svc.render_preview(item.get("data") or {}, payload.state)}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewDataBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.render_preview(payload.data or {}, payload.state)}

    return router
