"""FastAPI router for the Formula constructor (ТЗ 13 §2).

CRUD/lifecycle/versioning come from the shared constructor factory. On top it
adds the §2.6 "Проверить формулу" endpoints: /{id}/test (run a saved formula
with test values) and /evaluate (ad-hoc expression + variables). Guarded by
formula.* permissions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import formula_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_FORMULA_ARCHIVE, PERM_FORMULA_CREATE, PERM_FORMULA_DELETE,
    PERM_FORMULA_DISABLE, PERM_FORMULA_EDIT, PERM_FORMULA_PUBLISH,
    PERM_FORMULA_VALIDATE, PERM_FORMULA_VIEW, require_permission,
)

_PERMS = {
    "view": PERM_FORMULA_VIEW, "create": PERM_FORMULA_CREATE, "edit": PERM_FORMULA_EDIT,
    "validate": PERM_FORMULA_VALIDATE, "publish": PERM_FORMULA_PUBLISH,
    "disable": PERM_FORMULA_DISABLE, "archive": PERM_FORMULA_ARCHIVE,
    "delete": PERM_FORMULA_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "categories": [{"value": c, "label": svc.FORMULA_CATEGORY_LABELS.get(c, c)}
                       for c in svc.FORMULA_CATEGORIES],
        "roundingModes": [{"value": r, "label": svc.ROUNDING_LABELS.get(r, r)}
                          for r in svc.ROUNDING_MODES],
        "variableCatalog": list(svc.VARIABLE_CATALOG),
        "functions": sorted(svc._FUNCS.keys()),
    }


class _TestBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    values: dict[str, Any] = Field(default_factory=dict)


class _EvalBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    data: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_formula_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/formulas",
        tags=["admin-formulas"],
        svc=svc,
        perms=_PERMS,
        target_type="formula",
        name_field="name",
        not_found="Формула не найдена.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None) -> None:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_FORMULA_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{formula_id}/test")
    def test_formula(formula_id: str, payload: _TestBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(formula_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Формула не найдена.")
        return {"ok": True, "test": svc.test_formula(item.get("data") or {}, payload.values)}

    @router.post("/evaluate")
    def evaluate(payload: _EvalBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        return {"ok": True, "test": svc.test_formula(payload.data or {}, payload.values)}

    @router.get("/{formula_id}/where-used")
    def where_used(formula_id: str, request: Request, token: str | None = None) -> dict[str, Any]:
        _guard(request, token)
        return {"ok": True, "usage": svc.where_used(formula_id)}

    return router
