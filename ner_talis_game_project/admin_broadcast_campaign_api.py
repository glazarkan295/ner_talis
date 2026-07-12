"""Admin API полного конструктора рассылок."""
from typing import Any
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field
from services import broadcast_constructor_service as svc
from services import broadcast_campaign_runtime as runtime
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_operation import record_admin_operation
from services.admin_rbac import *  # noqa: F403

PERMS={"view":PERM_BROADCAST_VIEW,"create":PERM_BROADCAST_CREATE,"edit":PERM_BROADCAST_EDIT,"validate":PERM_BROADCAST_VALIDATE,"publish":PERM_BROADCAST_PUBLISH,"disable":PERM_BROADCAST_DISABLE,"archive":PERM_BROADCAST_ARCHIVE,"delete":PERM_BROADCAST_DELETE}  # noqa: F405
class Action(BaseModel):token:str|None=Field(default=None,min_length=16);reason:str="";confirm:bool=False;confirm_rewards:bool=False
def _token(request,token):
 auth=str(request.headers.get("authorization") or "");scheme,_,value=auth.partition(" ");return value.strip() if scheme.casefold()=="bearer" else str(token or "")
def create_admin_broadcast_campaign_router(get_storage)->APIRouter:
 router=create_entity_constructor_router(get_storage=get_storage,prefix="/api/admin/v2/broadcast-campaigns",tags=["admin-broadcast-campaigns"],svc=svc,perms=PERMS,target_type="broadcast_campaign",name_field="name",not_found="Рассылка не найдена.",meta_extra=lambda _:{"broadcastTypes":list(svc.BROADCAST_TYPES),"sendModes":list(svc.SEND_MODES),"formats":list(svc.FORMATS),"audienceModes":list(svc.AUDIENCE_MODES),"rewardTypes":list(svc.REWARD_TYPES),"buttonActions":list(svc.BUTTON_ACTIONS)})
 def guard(request,token,permission):
  try:session=require_admin_session(get_storage(),_token(request,token));require_permission(session,permission);return session
  except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc
 @router.post("/{broadcast_id}/recipient-preview")
 def recipient_preview(broadcast_id:str,payload:Action,request:Request):
  guard(request,payload.token,PERM_BROADCAST_VIEW)
  try:return {"ok":True,**runtime.preview_recipients(get_storage(),broadcast_id)}
  except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
 @router.post("/{broadcast_id}/start")
 def start(broadcast_id:str,payload:Action,request:Request):
  session=guard(request,payload.token,PERM_BROADCAST_PUBLISH)
  try:run=runtime.start(get_storage(),broadcast_id,confirm=payload.confirm,confirm_rewards=payload.confirm_rewards)
  except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
  record_admin_operation(session=session,action="broadcast_campaign.start",target_type="broadcast_campaign",target_id=broadcast_id,reason=payload.reason,details={"recipients":len(run.get("recipients") or []),"scheduled_at":run.get("scheduled_at")});return {"ok":True,"run":run}
 @router.post("/{broadcast_id}/test-send")
 def test_send(broadcast_id:str,payload:Action,request:Request):
  session=guard(request,payload.token,PERM_BROADCAST_PUBLISH)
  try:run=runtime.start(get_storage(),broadcast_id,confirm=True,confirm_rewards=True,test_only=True)
  except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
  record_admin_operation(session=session,action="broadcast_campaign.test_send",target_type="broadcast_campaign",target_id=broadcast_id,reason=payload.reason,details={"recipients":len(run.get("recipients") or [])});return {"ok":True,"run":run}
 @router.post("/{broadcast_id}/run-batch")
 def run_batch(broadcast_id:str,payload:Action,request:Request):guard(request,payload.token,PERM_BROADCAST_PUBLISH);return {"ok":True,"run":runtime.run_batch(get_storage(),broadcast_id)}
 @router.post("/{broadcast_id}/stop")
 def stop(broadcast_id:str,payload:Action,request:Request):
  session=guard(request,payload.token,PERM_BROADCAST_DISABLE)
  try:run=runtime.stop(broadcast_id)
  except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
  record_admin_operation(session=session,action="broadcast_campaign.stop",target_type="broadcast_campaign",target_id=broadcast_id,reason=payload.reason,details={"cursor":run.get("cursor")});return {"ok":True,"run":run}
 @router.post("/{broadcast_id}/retry-failed")
 def retry_failed(broadcast_id:str,payload:Action,request:Request):
  guard(request,payload.token,PERM_BROADCAST_PUBLISH)
  try:return {"ok":True,"run":runtime.retry_failed(broadcast_id)}
  except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
 @router.get("/{broadcast_id}/run-state")
 def run_state(broadcast_id:str,request:Request,token:str|None=None):guard(request,token,PERM_BROADCAST_VIEW);return {"ok":True,"run":runtime.get_run(broadcast_id)}
 return router
