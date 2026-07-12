"""FastAPI router for the message-queue-rule constructor (ТЗ 2.0, файл 18).

CRUD/lifecycle/versioning via the shared factory; adds a render-preview endpoint.
Guarded by message_rule.* permissions. Mounted under
``/api/admin/v2/message-rules``. Runtime queue = services/bot_message_queue.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import message_queue_rule_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_MESSAGE_RULE_ARCHIVE, PERM_MESSAGE_RULE_CREATE, PERM_MESSAGE_RULE_DELETE,
    PERM_MESSAGE_RULE_DISABLE, PERM_MESSAGE_RULE_EDIT, PERM_MESSAGE_RULE_PUBLISH,
    PERM_MESSAGE_RULE_VALIDATE, PERM_MESSAGE_RULE_VIEW, require_permission,
)

_PERMS = {
    "view": PERM_MESSAGE_RULE_VIEW, "create": PERM_MESSAGE_RULE_CREATE,
    "edit": PERM_MESSAGE_RULE_EDIT, "validate": PERM_MESSAGE_RULE_VALIDATE,
    "publish": PERM_MESSAGE_RULE_PUBLISH, "disable": PERM_MESSAGE_RULE_DISABLE,
    "archive": PERM_MESSAGE_RULE_ARCHIVE, "delete": PERM_MESSAGE_RULE_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "messageTypes": list(svc.MESSAGE_TYPES),
        "sourceTypes": list(svc.SOURCE_TYPES),
        "sendModes": [{"value": m, "label": svc.SEND_MODE_LABELS.get(m, m)} for m in svc.SEND_MODES],
        "platforms": list(svc.PLATFORMS),
        "templateVariables":list(svc.TEMPLATE_VARIABLES),
        "buttonActions":list(svc.BUTTON_ACTIONS),
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


def create_admin_message_queue_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/message-rules",
        tags=["admin-message-rules"],
        svc=svc,
        perms=_PERMS,
        target_type="message_rule",
        name_field="name",
        not_found="Правило очереди не найдено.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_MESSAGE_RULE_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{rule_id}/preview")
    def preview(rule_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(rule_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Правило очереди не найдено.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {})}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.preview(payload.data or {})}

    return router
