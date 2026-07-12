"""Authenticated player API for the trading pavilion."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from services.web_profile import PAVILION_SCOPE
from services import pavilion_runtime as runtime

class ListingBody(BaseModel):
    item_id:str=Field(min_length=1,max_length=160);quantity:int=Field(default=1,ge=1,le=100000);price:int=Field(ge=1);inventory_index:int|None=Field(default=None,ge=0)
class ListingAction(BaseModel): listing_id:str=Field(min_length=8,max_length=80)
def _bearer(request:Request)->str:
    scheme,_,value=str(request.headers.get("authorization") or "").partition(" ");return value.strip() if scheme.casefold()=="bearer" else ""
def create_pavilion_router(get_storage)->APIRouter:
    router=APIRouter(prefix="/api/pavilion",tags=["pavilion"])
    def auth(request:Request,token:str|None=None):
        effective=_bearer(request) or str(token or "").strip();storage=get_storage()
        if not effective:raise HTTPException(status_code=401,detail="Не передана ссылка-сессия павильона.")
        pair=storage.get_player_by_web_token(effective,scope=PAVILION_SCOPE) if hasattr(storage,"get_player_by_web_token") else (None,None)
        player,session=pair
        if not player or not session:raise HTTPException(status_code=401,detail="Недействительная или истёкшая ссылка павильона.")
        return storage,player,session
    def call(fn,*args,**kwargs):
        try:return fn(*args,**kwargs)
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    @router.get("")
    def overview(request:Request,token:str|None=Query(default=None,min_length=16))->dict[str,Any]:
        storage,player,session=auth(request,token);return {"ok":True,"sessionToken":session.get("token") or _bearer(request) or token,"accessActive":runtime.access_active(player),"playerState":player.get("pavilion") or {},"items":runtime.listings(storage)}
    @router.post("/rent")
    def rent(request:Request,token:str|None=Query(default=None,min_length=16))->dict[str,Any]:
        storage,player,session=auth(request,token);return {"ok":True,"sessionToken":session.get("token") or _bearer(request) or token,"result":call(runtime.rent,storage,player)}
    @router.post("/listings")
    def create_listing(payload:ListingBody,request:Request,token:str|None=Query(default=None,min_length=16))->dict[str,Any]:
        storage,player,session=auth(request,token);return {"ok":True,"sessionToken":session.get("token") or _bearer(request) or token,"item":call(runtime.create_listing,storage,player,payload.item_id,payload.quantity,payload.price,inventory_index=payload.inventory_index)}
    @router.post("/buy")
    def buy(payload:ListingAction,request:Request,token:str|None=Query(default=None,min_length=16))->dict[str,Any]:
        storage,player,session=auth(request,token);return {"ok":True,"sessionToken":session.get("token") or _bearer(request) or token,"result":call(runtime.buy,storage,player,payload.listing_id)}
    @router.post("/cancel")
    def cancel(payload:ListingAction,request:Request,token:str|None=Query(default=None,min_length=16))->dict[str,Any]:
        storage,player,session=auth(request,token);return {"ok":True,"sessionToken":session.get("token") or _bearer(request) or token,"item":call(runtime.cancel,storage,player,payload.listing_id)}
    return router
