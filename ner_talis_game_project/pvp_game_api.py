"""Игровой HTTP API PVP для web-профиля; использует тот же runtime, что боты."""
from typing import Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from services import pvp_runtime_service as pvp
from site_api import bearer_token_from_request, get_session_and_player_by_token

class Challenge(BaseModel):
    opponent_game_id: str; pvp_type: str = "duel"; location_id: str = ""; ally_game_ids: list[str] = Field(default_factory=list)
class Response(BaseModel):
    accept: bool
class Action(BaseModel):
    action: str

def create_pvp_game_router(get_storage) -> APIRouter:
    router=APIRouter(prefix="/api/pvp",tags=["pvp-game"])
    def player(request: Request) -> dict[str,Any]:
        token=bearer_token_from_request(request); found,_=get_session_and_player_by_token(get_storage(),token)
        if not found: raise HTTPException(status_code=401,detail="Нужна активная ссылка профиля.")
        return found
    def guarded_session(session_id: str, current: dict[str,Any]) -> dict[str,Any]:
        s=pvp.get_session(session_id); gid=str(current.get("game_id") or "")
        if not s: raise HTTPException(status_code=404,detail="PVP-бой не найден.")
        if gid not in (s.get("challenger"),s.get("opponent")): raise HTTPException(status_code=403,detail="Вы не участник этого боя.")
        return s
    @router.post("/challenge")
    def challenge(body: Challenge, request: Request):
        me=player(request); opponent=get_storage().get_player_by_game_id(body.opponent_game_id)
        if not opponent: raise HTTPException(status_code=404,detail="Игрок не найден.")
        allowed={str(x) for x in (me.get("pvp_ally_game_ids") or me.get("combat_group_member_ids") or [])}
        requested={str(x) for x in body.ally_game_ids}
        if not requested.issubset(allowed): raise HTTPException(status_code=400,detail="Союзник не состоит в вашей боевой группе или не принял приглашение.")
        allies=[p for gid in body.ally_game_ids if (p:=get_storage().get_player_by_game_id(gid))]
        opponent_ids=[str(x) for x in (opponent.get("pvp_ally_game_ids") or opponent.get("combat_group_member_ids") or [])]
        opponent_allies=[p for gid in opponent_ids if (p:=get_storage().get_player_by_game_id(gid))]
        try: return {"ok":True,"session":pvp.create_challenge(me,opponent,pvp_type=body.pvp_type,location_id=body.location_id,challenger_allies=allies,opponent_allies=opponent_allies)}
        except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    @router.get("/{session_id}")
    def status(session_id: str, request: Request):
        me=player(request);session=guarded_session(session_id,me);return {"ok":True,"session":session,"rendered":pvp.render_session(session,str(me.get("game_id") or ""))}
    @router.post("/{session_id}/respond")
    def respond(session_id: str, body: Response, request: Request):
        me=player(request); guarded_session(session_id,me)
        try: return {"ok":True,"session":pvp.respond(session_id,str(me.get("game_id")),body.accept)}
        except PermissionError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc
        except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    @router.post("/{session_id}/action")
    def action(session_id: str, body: Action, request: Request):
        me=player(request); guarded_session(session_id,me)
        try:
            result=pvp.act(session_id,str(me.get("game_id")),body.action)
            if result.get("state")=="finished": result=pvp.apply_result_to_players(get_storage(),session_id)
            return {"ok":True,"session":result}
        except PermissionError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc
        except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    @router.post("/{session_id}/timeout")
    def timeout(session_id: str, request: Request):
        me=player(request);guarded_session(session_id,me)
        try:
            result=pvp.handle_timeout(session_id)
            if result.get("state")=="finished":result=pvp.apply_result_to_players(get_storage(),session_id)
            return {"ok":True,"session":result}
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return router
