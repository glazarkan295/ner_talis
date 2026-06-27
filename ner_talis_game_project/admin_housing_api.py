"""FastAPI router for the housing (жилой район/дом) constructor (ТЗ 21 §6).

CRUD/lifecycle/versioning via the shared factory; adds a render-preview endpoint.
Guarded by housing.* permissions. Mounted under ``/api/admin/v2/housing``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import housing_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_HOUSING_ARCHIVE, PERM_HOUSING_CREATE, PERM_HOUSING_DELETE,
    PERM_HOUSING_DISABLE, PERM_HOUSING_EDIT, PERM_HOUSING_PUBLISH,
    PERM_HOUSING_VALIDATE, PERM_HOUSING_VIEW, require_permission,
)

_PERMS = {
    "view": PERM_HOUSING_VIEW, "create": PERM_HOUSING_CREATE,
    "edit": PERM_HOUSING_EDIT, "validate": PERM_HOUSING_VALIDATE,
    "publish": PERM_HOUSING_PUBLISH, "disable": PERM_HOUSING_DISABLE,
    "archive": PERM_HOUSING_ARCHIVE, "delete": PERM_HOUSING_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "plotTypes": [{"value": t, "label": svc.PLOT_TYPE_LABELS.get(t, t)} for t in svc.PLOT_TYPES],
        "houseTypes": [{"value": t, "label": svc.HOUSE_TYPE_LABELS.get(t, t)} for t in svc.HOUSE_TYPES],
        "cookingTiers": [{"value": t, "label": svc.COOKING_TIER_LABELS.get(t, t)} for t in svc.COOKING_TIERS],
        "dishTypes": [{"value": t, "label": svc.DISH_TYPE_LABELS.get(t, t)} for t in svc.DISH_TYPES],
        "statKeys": [{"value": s, "label": svc.STAT_LABELS.get(s, s)} for s in svc.STAT_KEYS],
        "specialRoomTypes": [{"value": r, "label": svc.SPECIAL_ROOM_LABELS.get(r, r)} for r in svc.SPECIAL_ROOM_TYPES],
        "fixedBuildings": [{"value": b, "label": svc.FIXED_BUILDING_LABELS.get(b, b)} for b in svc.FIXED_BUILDINGS],
        "upgradableBuildings": [{"value": b, "label": svc.UPGRADABLE_BUILDING_LABELS.get(b, b)} for b in svc.UPGRADABLE_BUILDINGS],
        "currencies": list(svc.CURRENCIES),
        "plotPresets": svc.PLOT_PRESETS,
        "roomPresets": svc.ROOM_PRESETS,
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


def create_admin_housing_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/housing",
        tags=["admin-housing"],
        svc=svc,
        perms=_PERMS,
        target_type="housing",
        name_field="name",
        not_found="План жилья не найден.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_HOUSING_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{housing_id}/preview")
    def preview(housing_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(housing_id)
        if item is None:
            raise HTTPException(status_code=404, detail="План жилья не найден.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {})}

    @router.post("/preview")
    def preview_adhoc(payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "preview": svc.preview(payload.data or {})}

    return router
