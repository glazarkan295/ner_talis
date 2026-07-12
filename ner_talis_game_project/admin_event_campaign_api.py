"""Admin API конструктора игровых эвентов."""
from typing import Any
from fastapi import HTTPException, Request
from pydantic import BaseModel
from services import event_campaign_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_rbac import *  # noqa: F403

class FinalizeRequest(BaseModel):
    reason:str=""

def create_admin_event_campaign_router(get_storage):
    perms={"view":PERM_EVENT_VIEW,"create":PERM_EVENT_CREATE,"edit":PERM_EVENT_EDIT,"validate":PERM_EVENT_VALIDATE,
           "publish":PERM_EVENT_PUBLISH,"disable":PERM_EVENT_DISABLE,"archive":PERM_EVENT_ARCHIVE,"delete":PERM_EVENT_DELETE}  # noqa: F405
    router=create_entity_constructor_router(get_storage=get_storage,prefix="/api/admin/v2/event-campaigns",tags=["admin-event-campaigns"],svc=svc,perms=perms,target_type="event_campaign",name_field="name",not_found="Эвент не найден.",meta_extra=lambda _:{"eventTypes":list(svc.EVENT_TYPES),"taskTypes":list(svc.TASK_TYPES),"rewardTypes":list(svc.REWARD_TYPES),"ratingTypes":list(svc.RATING_TYPES)})
    @router.post("/{event_id}/finalize-ranking")
    def finalize(event_id:str,payload:FinalizeRequest,request:Request)->dict[str,Any]:
        from services.admin_panel_service import require_admin_session
        from services.admin_rbac import require_permission
        token=str(request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        try:session=require_admin_session(get_storage(),token);require_permission(session,PERM_EVENT_PUBLISH)  # noqa: F405
        except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc
        from services.event_campaign_runtime import finalize_ranking
        from services.admin_operation import run_admin_operation
        try:
            result=run_admin_operation(session=session,action="event_campaign.finalize_ranking",target_type="event_campaign",target_id=event_id,reason=payload.reason,func=lambda:finalize_ranking(get_storage(),event_id),after_func=lambda value:{"issued":len(value.get("issued") or [])})
            return {"ok":True,"result":result}
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return router
