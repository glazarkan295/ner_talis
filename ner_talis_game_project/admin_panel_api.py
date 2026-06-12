"""FastAPI router for the protected admin panel."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_panel_service import (
    admin_catalog,
    admin_catalog_item,
    admin_player_detail,
    create_admin_player_view_token,
    create_admin_promo,
    deliver_rewards_to_player,
    get_admin_player_view_profile,
    list_admin_players,
    player_logs_last_24h,
    promo_list_payload,
    require_admin_session,
    update_item_image_from_base64,
)
from services.admin_player_service import delete_player_profile
from services.admin_audit import write_admin_audit


class AdminSessionRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)


class AdminRewardItem(BaseModel):
    item_id: str
    amount: int = Field(gt=0)


class AdminDeliveryRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    target_game_id: str
    rewards: list[AdminRewardItem]


class AdminPromoCreateRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    code: str = Field(min_length=1)
    uses_left: int = Field(gt=0)
    duration: str = "never"
    rewards: list[AdminRewardItem]


class AdminDeletePlayerRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    confirm: str


class AdminChangeImageRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    filename: str = "item.png"
    content_base64: str = Field(min_length=16)
    content_type: str | None = None


def _bearer_token(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not value.strip():
        return ""
    return value.strip()


def _admin_token(request: Request | None, fallback: str | None = None) -> str:
    return _bearer_token(request) or str(fallback or "").strip()


def _session_or_403(storage: Any, request: Request | None = None, token: str | None = None) -> dict[str, Any]:
    effective_token = _admin_token(request, token)
    if not effective_token:
        raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
    try:
        return require_admin_session(storage, effective_token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _reward_dicts(rewards: list[AdminRewardItem]) -> list[dict[str, Any]]:
    return [reward.model_dump() if hasattr(reward, "model_dump") else reward.dict() for reward in rewards]


def create_admin_panel_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin-panel"])

    @router.get("/session/{token}")
    def activate_admin_session(token: str) -> dict[str, Any]:
        storage = get_storage()
        from services.admin_panel_service import consume_or_read_admin_session

        session = consume_or_read_admin_session(storage, token)
        if not session or session.get("kind") != "active":
            raise HTTPException(status_code=401, detail="Админ-ссылка недействительна или истекла.")
        return {
            "ok": True,
            "sessionToken": session.get("token"),
            "admin": {
                "platform": session.get("platform"),
                "admin_user_id": session.get("admin_user_id"),
                "chat_id": session.get("chat_id"),
                "expires_at": session.get("expires_at"),
            },
        }

    @router.get("/catalog")
    def get_catalog(request: Request, token: str | None = Query(default=None, min_length=16), q: str = "", category: str = "") -> dict[str, Any]:
        _session_or_403(get_storage(), request, token)
        return admin_catalog(query=q, category=category)

    @router.get("/catalog/{item_id}")
    def get_catalog_item(item_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _session_or_403(get_storage(), request, token)
        item = admin_catalog_item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        return {"item": item}

    @router.post("/catalog/{item_id}/image")
    def change_item_image(item_id: str, payload: AdminChangeImageRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session_or_403(storage, request, payload.token)
        try:
            return update_item_image_from_base64(
                storage,
                item_id=item_id,
                filename=payload.filename,
                content_base64=payload.content_base64,
                content_type=payload.content_type,
                admin_session=session,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/players")
    def get_players(request: Request, token: str | None = Query(default=None, min_length=16), q: str = "", limit: int = 200) -> dict[str, Any]:
        storage = get_storage()
        _session_or_403(storage, request, token)
        return {"players": list_admin_players(storage, query=q, limit=limit)}

    @router.get("/players/{game_id}")
    def get_player(game_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        _session_or_403(storage, request, token)
        detail = admin_player_detail(storage, game_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Игрок не найден.")
        return {"player": detail}

    @router.delete("/players/{game_id}")
    def delete_player(game_id: str, payload: AdminDeletePlayerRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session_or_403(storage, request, payload.token)
        if payload.confirm != "CONFIRM_DELETE":
            raise HTTPException(status_code=400, detail="Для удаления нужно подтверждение CONFIRM_DELETE.")
        ok, message, player = delete_player_profile(storage, game_id)
        if ok:
            write_admin_audit(
                platform=str(session.get("platform") or "admin_panel"),
                admin_user_id=str(session.get("admin_user_id") or "unknown"),
                command="admin_panel_delete_player",
                action="admin_panel_delete_player",
                details={"game_id": game_id, "deleted_player_name": (player or {}).get("name") if isinstance(player, dict) else None},
            )
            return {"ok": True, "message": message}
        raise HTTPException(status_code=400, detail=message)

    @router.post("/players/{game_id}/view-token")
    def player_view_token(game_id: str, payload: AdminSessionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session_or_403(storage, request, payload.token)
        try:
            token = create_admin_player_view_token(storage, target_game_id=game_id, admin_session=session)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "token": token, "url": f"/admin_view_profile?token={token}"}

    @router.get("/players/{game_id}/logs")
    def player_logs(game_id: str, request: Request, token: str | None = Query(default=None, min_length=16), limit: int = 200) -> dict[str, Any]:
        storage = get_storage()
        _session_or_403(storage, request, token)
        return {"logs": player_logs_last_24h(storage, game_id=game_id, limit=limit)}

    @router.post("/delivery/send")
    def send_delivery(payload: AdminDeliveryRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session_or_403(storage, request, payload.token)
        try:
            return deliver_rewards_to_player(
                storage,
                target_game_id=payload.target_game_id,
                rewards=_reward_dicts(payload.rewards),
                admin_session=session,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/promos")
    def get_promos(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        _session_or_403(storage, request, token)
        return {"promos": promo_list_payload(storage)}

    @router.post("/promos")
    def create_promo(payload: AdminPromoCreateRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session_or_403(storage, request, payload.token)
        try:
            promo = create_admin_promo(
                storage,
                code=payload.code,
                uses_left=payload.uses_left,
                duration=payload.duration,
                rewards=_reward_dicts(payload.rewards),
                admin_session=session,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "promo": promo}

    @router.get("/player-view")
    def get_admin_player_view(request: Request) -> dict[str, Any]:
        storage = get_storage()
        token = _bearer_token(request)
        payload = get_admin_player_view_profile(storage, token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Ссылка просмотра профиля недействительна или истекла.")
        return payload

    @router.get("/player-view/{token}")
    def get_admin_player_view_legacy(token: str) -> dict[str, Any]:
        storage = get_storage()
        payload = get_admin_player_view_profile(storage, token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Ссылка просмотра профиля недействительна или истекла.")
        return payload

    return router
