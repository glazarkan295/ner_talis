"""API конструктора реферальных правил Telegram/VK."""
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from services import referral_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_rbac import PERM_PROMOS_VIEW, PERM_PROMOS_MANAGE

_PERMS = {"view": PERM_PROMOS_VIEW, "create": PERM_PROMOS_MANAGE, "edit": PERM_PROMOS_MANAGE,
          "validate": PERM_PROMOS_MANAGE, "publish": PERM_PROMOS_MANAGE, "disable": PERM_PROMOS_MANAGE,
          "archive": PERM_PROMOS_MANAGE, "delete": PERM_PROMOS_MANAGE}
def _meta(_svc: Any) -> dict[str, Any]:
    return {"platforms": list(svc.PLATFORMS), "linkTypes": list(svc.LINK_TYPES), "rewardTypes": list(svc.REWARD_TYPES), "triggers": list(svc.TRIGGERS)}
def create_admin_referral_router(get_storage) -> APIRouter:
    router=create_entity_constructor_router(get_storage=get_storage, prefix="/api/admin/v2/referrals", tags=["admin-referrals"],
        svc=svc, perms=_PERMS, target_type="referral_rule", name_field="name", not_found="Реферальное правило не найдено.", meta_extra=_meta)
    from services.admin_panel_service import require_admin_session
    from services.admin_rbac import require_permission
    from services.referral_service import referral_statistics, review_invitation
    def session(request,token):
        raw=str(request.headers.get("authorization") or "").removeprefix("Bearer ").strip() or str(token or "")
        try:s=require_admin_session(get_storage(),raw);require_permission(s,PERM_PROMOS_VIEW);return s
        except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc
    @router.get("/operations/statistics")
    def statistics(request:Request,token:str|None=Query(default=None)):
        session(request,token);return {"ok":True,**referral_statistics(get_storage())}
    class Review(BaseModel):
        approve:bool;reason:str="";token:str|None=None
    @router.post("/operations/review/{invite_id}")
    def review(invite_id:str,payload:Review,request:Request):
        s=session(request,payload.token);require_permission(s,PERM_PROMOS_MANAGE)
        if not review_invitation(get_storage(),invite_id,payload.approve,payload.reason):raise HTTPException(status_code=404,detail="Приглашение на ручной проверке не найдено.")
        return {"ok":True}
    # Литеральные operations-маршруты должны стоять раньше generic /{id}.
    router.routes.insert(0,router.routes.pop());router.routes.insert(0,router.routes.pop())
    return router
