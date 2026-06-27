"""FastAPI router for the Reputation constructor (item-reputation §3, эффекты §3).

CRUD/lifecycle/versioning via the shared factory; adds a consequences preview
endpoint (§3.12). Guarded by reputation.* permissions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import reputation_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_REPUTATION_ARCHIVE, PERM_REPUTATION_CREATE, PERM_REPUTATION_DELETE,
    PERM_REPUTATION_DISABLE, PERM_REPUTATION_EDIT, PERM_REPUTATION_PUBLISH,
    PERM_REPUTATION_VALIDATE, PERM_REPUTATION_VIEW, require_permission,
)

_PERMS = {
    "view": PERM_REPUTATION_VIEW, "create": PERM_REPUTATION_CREATE, "edit": PERM_REPUTATION_EDIT,
    "validate": PERM_REPUTATION_VALIDATE, "publish": PERM_REPUTATION_PUBLISH,
    "disable": PERM_REPUTATION_DISABLE, "archive": PERM_REPUTATION_ARCHIVE,
    "delete": PERM_REPUTATION_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "visibility": [{"value": v, "label": svc.VISIBILITY_LABELS.get(v, v)} for v in svc.VISIBILITY],
        "scopeTypes": list(svc.SCOPE_TYPES),
        "displayModes": list(svc.DISPLAY_MODES),
        "changeTriggers": list(svc.CHANGE_TRIGGERS),
        "decayDirections": list(svc.DECAY_DIRECTIONS),
    }


class _PreviewBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    value: float | None = None
    delta: float = 0


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_reputation_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/reputations",
        tags=["admin-reputations"],
        svc=svc,
        perms=_PERMS,
        target_type="reputation",
        name_field="name_ru",
        not_found="Репутация не найдена.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_REPUTATION_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{reputation_id}/preview")
    def preview(reputation_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(reputation_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Репутация не найдена.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {}, payload.value, payload.delta)}

    return router
