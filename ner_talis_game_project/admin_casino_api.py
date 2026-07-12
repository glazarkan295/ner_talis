"""FastAPI router for the «Подпольное казино» constructor (ТЗ 21 §4).

CRUD/lifecycle/versioning via the shared factory; adds preview and a wheel-
redistribute helper endpoint (§4.8). Guarded by casino.* permissions. Mounted
under ``/api/admin/v2/casino``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from services import casino_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_CASINO_ARCHIVE, PERM_CASINO_CREATE, PERM_CASINO_DELETE,
    PERM_CASINO_DISABLE, PERM_CASINO_EDIT, PERM_CASINO_PUBLISH,
    PERM_CASINO_VALIDATE, PERM_CASINO_VIEW, require_permission,
)

_PERMS = {
    "view": PERM_CASINO_VIEW, "create": PERM_CASINO_CREATE,
    "edit": PERM_CASINO_EDIT, "validate": PERM_CASINO_VALIDATE,
    "publish": PERM_CASINO_PUBLISH, "disable": PERM_CASINO_DISABLE,
    "archive": PERM_CASINO_ARCHIVE, "delete": PERM_CASINO_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "gameTypes": [{"value": g, "label": svc.GAME_TYPE_LABELS.get(g, g)} for g in svc.GAME_TYPES],
        "wheelPrizeTypes": [{"value": p, "label": svc.WHEEL_PRIZE_LABELS.get(p, p)} for p in svc.WHEEL_PRIZE_TYPES],
        "currencies": list(svc.CURRENCIES),
        "wheelMinPrizes": svc.WHEEL_MIN_PRIZES,
        "wheelMaxPrizes": svc.WHEEL_MAX_PRIZES,
    }


class _PreviewBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    data: dict[str, Any] | None = None


class _WheelBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    prizes: list[dict[str, Any]] = Field(default_factory=list)
    empty_chance: float = 0
    won_index: int = 0


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_casino_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/casino",
        tags=["admin-casino"],
        svc=svc,
        perms=_PERMS,
        target_type="casino",
        name_field="name",
        not_found="Казино не найдено.",
        meta_extra=_meta_extra,
    )

    @router.get("/operations/logs")
    def operation_logs(request: Request, token: str | None = Query(default=None, min_length=16), limit: int = Query(default=200, ge=1, le=2000)) -> dict[str, Any]:
        _guard(request, token)
        from services.casino_runtime import read_logs
        rows=read_logs(limit)
        return {"ok":True,"items":rows,"suspicious":[row for row in rows if row.get("suspicious")]}

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_CASINO_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{casino_id}/preview")
    def preview(casino_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(casino_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Казино не найдено.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {})}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.preview(payload.data or {})}

    @router.post("/wheel-redistribute")
    def wheel_redistribute(payload: _WheelBody, request: Request) -> dict[str, Any]:
        """Симуляция особого правила колеса (§4.8): шанс выпавшего приза переходит
        в шанс пустого результата."""
        _guard(request, payload.token)
        return {"ok": True, "result": svc.wheel_redistribute(payload.prizes, payload.empty_chance, payload.won_index)}

    return router
