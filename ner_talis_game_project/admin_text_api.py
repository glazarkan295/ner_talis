"""FastAPI router for the bot-text constructor (full-import ТЗ §5.18).

CRUD/lifecycle/versioning via the shared factory; adds a render-preview endpoint
(substitute test variables into a saved/ad-hoc template). Guarded by text.*
permissions. Mounted under ``/api/admin/v2/texts``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import text_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_TEXT_ARCHIVE, PERM_TEXT_CREATE, PERM_TEXT_DELETE, PERM_TEXT_DISABLE,
    PERM_TEXT_EDIT, PERM_TEXT_PUBLISH, PERM_TEXT_VALIDATE, PERM_TEXT_VIEW,
    require_permission,
)

_PERMS = {
    "view": PERM_TEXT_VIEW, "create": PERM_TEXT_CREATE, "edit": PERM_TEXT_EDIT,
    "validate": PERM_TEXT_VALIDATE, "publish": PERM_TEXT_PUBLISH,
    "disable": PERM_TEXT_DISABLE, "archive": PERM_TEXT_ARCHIVE,
    "delete": PERM_TEXT_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "platforms": [{"value": p, "label": svc.PLATFORM_LABELS.get(p, p)} for p in svc.PLATFORMS],
        "parseModes": list(svc.PARSE_MODES),
        "contexts": [{"value": c, "label": svc.CONTEXT_LABELS.get(c, c)} for c in svc.CONTEXTS],
        "entityTypes": list(svc.ENTITY_TYPES),
    }


class _PreviewBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    variables: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] | None = None


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_text_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/texts",
        tags=["admin-texts"],
        svc=svc,
        perms=_PERMS,
        target_type="text",
        name_field="text_key",
        not_found="Текст не найден.",
        meta_extra=_meta_extra,
        import_fn_name="import_texts",
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_TEXT_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{text_id}/preview")
    def preview(text_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(text_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Текст не найден.")
        return {"ok": True, "preview": svc.render(item.get("data") or {}, payload.variables)}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.render(payload.data or {}, payload.variables)}

    return router
