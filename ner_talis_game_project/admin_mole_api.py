"""FastAPI router for the «Информатор Крот» constructor (ТЗ 21 §3).

CRUD/lifecycle/versioning via the shared factory; adds a render-preview endpoint
and an order-allowed check endpoint (§3.5 mandatory bans). Guarded by mole.*
permissions. Mounted under ``/api/admin/v2/mole``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import mole_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_MOLE_ARCHIVE, PERM_MOLE_CREATE, PERM_MOLE_DELETE, PERM_MOLE_DISABLE,
    PERM_MOLE_EDIT, PERM_MOLE_PUBLISH, PERM_MOLE_VALIDATE, PERM_MOLE_VIEW,
    require_permission,
)

_PERMS = {
    "view": PERM_MOLE_VIEW, "create": PERM_MOLE_CREATE, "edit": PERM_MOLE_EDIT,
    "validate": PERM_MOLE_VALIDATE, "publish": PERM_MOLE_PUBLISH,
    "disable": PERM_MOLE_DISABLE, "archive": PERM_MOLE_ARCHIVE,
    "delete": PERM_MOLE_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "infoSearchModes": [{"value": m, "label": svc.INFO_SEARCH_LABELS.get(m, m)} for m in svc.INFO_SEARCH_MODES],
        "compassModes": [{"value": m, "label": svc.COMPASS_MODE_LABELS.get(m, m)} for m in svc.COMPASS_MODES],
        "assassinCategories": [{"value": c, "label": svc.ASSASSIN_CATEGORY_LABELS.get(c, c)} for c in svc.ASSASSIN_CATEGORIES],
        "refundPolicies": [{"value": r, "label": svc.REFUND_POLICY_LABELS.get(r, r)} for r in svc.REFUND_POLICIES],
        "currencies": list(svc.CURRENCIES),
        "defaultMaxLevelDiff": svc.DEFAULT_MAX_LEVEL_DIFF,
        "defaultWeakerRatio": svc.DEFAULT_WEAKER_RATIO,
    }


class _PreviewBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    data: dict[str, Any] | None = None


class _OrderCheckBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    orderer_level: float
    target_level: float
    max_level_diff: float | None = None
    weaker_ratio: float | None = None


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_mole_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/mole",
        tags=["admin-mole"],
        svc=svc,
        perms=_PERMS,
        target_type="mole",
        name_field="name",
        not_found="Сервис Крота не найден.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_MOLE_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{mole_id}/preview")
    def preview(mole_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(mole_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Сервис Крота не найден.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {})}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.preview(payload.data or {})}

    @router.post("/order-check")
    def order_check(payload: _OrderCheckBody, request: Request) -> dict[str, Any]:
        """Проверка обязательных запретов заказа (§3.5)."""
        _guard(request, payload.token)
        kwargs: dict[str, Any] = {}
        if payload.max_level_diff is not None:
            kwargs["max_level_diff"] = payload.max_level_diff
        if payload.weaker_ratio is not None:
            kwargs["weaker_ratio"] = payload.weaker_ratio
        return {"ok": True, "result": svc.check_order_allowed(payload.orderer_level, payload.target_level, **kwargs)}

    return router
