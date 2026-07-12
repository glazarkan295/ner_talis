"""Игровой web API участия в опубликованных эвентах."""
from typing import Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from services import event_campaign_runtime as runtime
from site_api import bearer_token_from_request, get_session_and_player_by_token

class ProgressBody(BaseModel):event_type:str;target_id:str="";amount:int=1
class JoinBody(BaseModel):method:str="button"
def create_event_campaign_router(get_storage):
    router=APIRouter(prefix="/api/events",tags=["event-campaigns"])
    def current(request:Request):
        player,_=get_session_and_player_by_token(get_storage(),bearer_token_from_request(request))
        if not player:raise HTTPException(status_code=401,detail="Профильная сессия недействительна.")
        return player
    @router.post("/{event_id}/join")
    def join(event_id:str,request:Request,body:JoinBody|None=None)->dict[str,Any]:
        player=current(request)
        try:state=runtime.join(player,event_id,method=(body.method if body else "button"),storage=get_storage())
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
        get_storage().update_player(player);return {"ok":True,"state":state}
    @router.get("/{event_id}/me")
    def me(event_id:str,request:Request)->dict[str,Any]:
        player=current(request);state=(player.get("event_campaigns") or {}).get(event_id)
        return {"ok":True,"state":state}
    @router.get("/{event_id}/ranking")
    def ranking(event_id:str,request:Request)->dict[str,Any]:
        player=current(request);rows=runtime.ranking(get_storage(),event_id);gid=str(player.get("game_id") or "")
        own=next((r for r in rows if r["game_id"]==gid),None)
        if own and isinstance((player.get("event_campaigns") or {}).get(event_id),dict):
            player["event_campaigns"][event_id]["place"]=own["place"];get_storage().update_player(player)
        from services.event_campaign_service import published
        data=published(event_id) or {};show_top=bool(data.get("show_top")) and not bool(data.get("hide_full_rating"))
        return {"ok":True,"myPlace":own,"top":rows[:100] if show_top else []}
    @router.post("/{event_id}/progress")
    def progress(event_id:str,body:ProgressBody,request:Request)->dict[str,Any]:
        current(request)
        raise HTTPException(status_code=403,detail="Прогресс эвента начисляется автоматически игровыми действиями.")
    return router
