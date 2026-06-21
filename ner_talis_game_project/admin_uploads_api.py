"""FastAPI router for Admin V2 image uploads (file, not external URL).

Mounted under ``/api/admin/v2/uploads``. Конструкторы грузят картинки файлом
(base64), они сохраняются в постоянный том assets/admin_uploads/<category>/ и
возвращают локальный путь /assets/… — его и пишут в поле image/icon объекта
(ТЗ доп.§2). Право assets.manage; действие пишется в аудит.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.admin_operation import record_admin_operation
from services.admin_panel_service import require_admin_session, save_uploaded_image
from services.admin_rbac import PERM_ASSETS_MANAGE, identity_key, require_permission


class UploadImageRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    category: str = "misc"
    key: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
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


def create_admin_uploads_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/uploads", tags=["admin-uploads"])

    @router.post("/image")
    def upload_image(payload: UploadImageRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        try:
            require_permission(session, PERM_ASSETS_MANAGE)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        try:
            result = save_uploaded_image(category=payload.category, key=payload.key, content_base64=payload.content_base64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_admin_operation(
            session=session, action="asset.upload_image",
            target_type="asset", target_id=result["path"],
            after={"path": result["path"]}, reason=payload.reason,
            details={"category": payload.category},
        )
        return {"ok": True, **result}

    return router
