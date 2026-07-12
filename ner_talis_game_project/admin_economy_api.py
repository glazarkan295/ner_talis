"""API самостоятельного конструктора экономики ТЗ 2.0."""
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request
from services import economy_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_rbac import PERM_ECONOMY_VIEW, PERM_ECONOMY_MANAGE, require_permission

_PERMS = {"view": PERM_ECONOMY_VIEW, "create": PERM_ECONOMY_MANAGE, "edit": PERM_ECONOMY_MANAGE,
          "validate": PERM_ECONOMY_MANAGE, "publish": PERM_ECONOMY_MANAGE, "disable": PERM_ECONOMY_MANAGE,
          "archive": PERM_ECONOMY_MANAGE, "delete": PERM_ECONOMY_MANAGE}
def _meta(_svc: Any) -> dict[str, Any]:
    return {"currencyCodes": list(svc.CURRENCY_CODES), "priceModes": list(svc.PRICE_MODES)}

def _bearer(request: Request) -> str:
    scheme, _, value = str(request.headers.get("authorization") or "").strip().partition(" ")
    return value.strip() if scheme.casefold() == "bearer" else ""

def create_admin_economy_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(get_storage=get_storage, prefix="/api/admin/v2/economy", tags=["admin-economy"],
        svc=svc, perms=_PERMS, target_type="economy", name_field="name", not_found="Экономический профиль не найден.", meta_extra=_meta)

    @router.get("/operations/logs")
    def operation_logs(request: Request, token: str | None = Query(default=None, min_length=16),
                       limit: int = Query(default=500, ge=1, le=5000), game_id: str = "") -> dict[str, Any]:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, PERM_ECONOMY_VIEW)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        from services.economy_runtime import transactions
        return {"ok": True, "items": transactions(limit, game_id)}

    return router
