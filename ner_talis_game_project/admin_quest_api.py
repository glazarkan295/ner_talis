"""FastAPI router for the quest constructor (ТЗ 2.0, файл 10, часть 2).

CRUD/lifecycle/versioning via the shared factory; adds a render-preview endpoint
(§38). Guarded by quest.* permissions. Mounted under ``/api/admin/v2/quests``.
Quest runtime does not exist yet — this is the authoring layer only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import quest_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_QUEST_ARCHIVE, PERM_QUEST_CREATE, PERM_QUEST_DELETE, PERM_QUEST_DISABLE,
    PERM_QUEST_EDIT, PERM_QUEST_PUBLISH, PERM_QUEST_VALIDATE, PERM_QUEST_VIEW,
    require_permission,
)

_PERMS = {
    "view": PERM_QUEST_VIEW, "create": PERM_QUEST_CREATE, "edit": PERM_QUEST_EDIT,
    "validate": PERM_QUEST_VALIDATE, "publish": PERM_QUEST_PUBLISH,
    "disable": PERM_QUEST_DISABLE, "archive": PERM_QUEST_ARCHIVE,
    "delete": PERM_QUEST_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "questTypes": [{"value": t, "label": svc.QUEST_TYPE_LABELS.get(t, t)} for t in svc.QUEST_TYPES],
        "sourceTypes": list(svc.SOURCE_TYPES),
        "taskTypes": list(svc.TASK_TYPES),
        "rewardTypes": list(svc.REWARD_TYPES),
        "repeatModes": list(svc.REPEAT_MODES),
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


def create_admin_quest_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/quests",
        tags=["admin-quests"],
        svc=svc,
        perms=_PERMS,
        target_type="quest",
        name_field="name",
        not_found="Квест не найден.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_QUEST_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{quest_id}/preview")
    def preview(quest_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(quest_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Квест не найден.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {})}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.preview(payload.data or {})}

    return router
