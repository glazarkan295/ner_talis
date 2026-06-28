"""FastAPI router for the NPC-ally constructor (ТЗ 21 §2).

CRUD/lifecycle/versioning via the shared factory; adds a render-preview endpoint
(§2.4 card). Guarded by npc_ally.* permissions. Mounted under
``/api/admin/v2/npc-allies``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import npc_ally_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_NPC_ALLY_ARCHIVE, PERM_NPC_ALLY_CREATE, PERM_NPC_ALLY_DELETE,
    PERM_NPC_ALLY_DISABLE, PERM_NPC_ALLY_EDIT, PERM_NPC_ALLY_PUBLISH,
    PERM_NPC_ALLY_VALIDATE, PERM_NPC_ALLY_VIEW, require_permission,
)

_PERMS = {
    "view": PERM_NPC_ALLY_VIEW, "create": PERM_NPC_ALLY_CREATE,
    "edit": PERM_NPC_ALLY_EDIT, "validate": PERM_NPC_ALLY_VALIDATE,
    "publish": PERM_NPC_ALLY_PUBLISH, "disable": PERM_NPC_ALLY_DISABLE,
    "archive": PERM_NPC_ALLY_ARCHIVE, "delete": PERM_NPC_ALLY_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "allyTypes": [{"value": t, "label": svc.ALLY_TYPE_LABELS.get(t, t)} for t in svc.ALLY_TYPES],
        "acquireMethods": [{"value": m, "label": svc.ACQUIRE_METHOD_LABELS.get(m, m)} for m in svc.ACQUIRE_METHODS],
        "combatTurnModes": [{"value": t, "label": svc.COMBAT_TURN_LABELS.get(t, t)} for t in svc.COMBAT_TURN_MODES],
        "targetModes": [{"value": t, "label": svc.TARGET_MODE_LABELS.get(t, t)} for t in svc.TARGET_MODES],
        "abilities": list(svc.ABILITIES),
        "currencies": list(svc.CURRENCIES),
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


def create_admin_npc_ally_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/npc-allies",
        tags=["admin-npc-allies"],
        svc=svc,
        perms=_PERMS,
        target_type="npc_ally",
        name_field="name",
        not_found="NPC-союзник не найден.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_NPC_ALLY_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{ally_id}/preview")
    def preview(ally_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(ally_id)
        if item is None:
            raise HTTPException(status_code=404, detail="NPC-союзник не найден.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {})}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.preview(payload.data or {})}

    return router
