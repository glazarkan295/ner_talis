"""FastAPI router for Admin V2 outgoing message queue (ТЗ §14–16, 25–26).

Mounted under ``/api/admin/v2/messages``. Reads need messages.view_queue;
sending/retry/cancel/dispatch are gated per stage and recorded via
admin_operation. Backed by bot_message_queue (the dispatcher + sender hook).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_MESSAGES_CANCEL,
    PERM_MESSAGES_MANAGE_DISPATCHER,
    PERM_MESSAGES_RETRY,
    PERM_MESSAGES_SEND_DIRECT,
    PERM_MESSAGES_VIEW_PLAYER,
    PERM_MESSAGES_VIEW_QUEUE,
    identity_key,
    require_permission,
)
from services import bot_message_queue as mq


class SendDirectRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    game_id: str = Field(min_length=2)
    text: str = Field(min_length=1)
    priority: str = "high"
    type: str = "admin"
    reason: str = ""


class ActionRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    reason: str = ""


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


def _session(storage: Any, request: Request | None, token: str | None) -> dict[str, Any]:
    effective_token = _bearer_token(request) or str(token or "").strip()
    if not effective_token:
        raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
    try:
        return require_admin_session(storage, effective_token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _require(session: dict[str, Any], permission: str) -> str:
    try:
        return require_permission(session, permission)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _actor(session: dict[str, Any]) -> str:
    return identity_key(session.get("platform"), session.get("admin_user_id"))


def _resolve_recipient(player: dict[str, Any]) -> tuple[str, str]:
    """Платформа + получатель из профиля игрока (ТЗ §12–13)."""
    linked = player.get("linked_accounts") if isinstance(player.get("linked_accounts"), dict) else {}
    platform = str(player.get("main_platform") or "").strip()
    if platform and linked.get(platform):
        return platform, str(linked.get(platform))
    for plat in ("telegram", "vk"):
        if linked.get(plat):
            return plat, str(linked.get(plat))
    return "", ""


def create_admin_messages_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/messages", tags=["admin-messages"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_MESSAGES_VIEW_QUEUE)
        return {
            "ok": True,
            "statuses": list(mq.STATUSES),
            "priorities": list(mq.PRIORITIES),
            "dispatcher": mq.dispatcher_status(),
        }

    @router.get("/stats")
    def stats(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_MESSAGES_VIEW_QUEUE)
        return {"ok": True, "stats": mq.stats(), "dispatcher": mq.dispatcher_status()}

    @router.get("/players/{game_id}")
    def player_messages(game_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_MESSAGES_VIEW_PLAYER)
        return {"ok": True, "messages": mq.list_messages(game_id=game_id, limit=100)}

    @router.post("/dispatch")
    def dispatch(payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_MESSAGES_MANAGE_DISPATCHER)
        counts = mq.dispatch_once()
        record_admin_operation(
            session=session, action="messages.dispatch", target_type="dispatcher",
            target_id="bot_message_dispatcher", after=counts, reason=payload.reason,
        )
        return {"ok": True, "result": counts, "dispatcher": mq.dispatcher_status()}

    @router.get("")
    def list_queue(
        request: Request,
        token: str | None = Query(default=None, min_length=16),
        status: str | None = None,
        game_id: str | None = None,
        errors_only: bool = False,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_MESSAGES_VIEW_QUEUE)
        return {"ok": True, "messages": mq.list_messages(status=status, game_id=game_id, errors_only=errors_only, limit=limit)}

    @router.post("/send")
    def send_direct(payload: SendDirectRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_MESSAGES_SEND_DIRECT)
        player = storage.get_player_by_game_id(payload.game_id) if hasattr(storage, "get_player_by_game_id") else None
        if not player:
            raise HTTPException(status_code=404, detail="Игрок не найден.")
        platform, recipient = _resolve_recipient(player)
        def _enqueue() -> dict[str, Any]:
            message, _created = mq.enqueue(
                game_id=payload.game_id, platform=platform, recipient=recipient,
                text=payload.text, type=payload.type or "admin",
                priority=payload.priority if payload.priority in mq.PRIORITIES else mq.PRIORITY_HIGH,
                source="admin_panel_v2",
                initial_status=mq.STATUS_QUEUED if recipient else mq.STATUS_NOTIFICATION_PENDING,
            )
            return message

        message = run_admin_operation(
            session=session, action="messages.send_direct",
            func=_enqueue, target_type="player", target_id=payload.game_id,
            after_func=lambda m: {"message_id": m.get("id"), "platform": platform},
            reason=payload.reason, details={"text": payload.text[:200], "priority": payload.priority},
        )
        # Сразу пробуем доставить (мгновенная доставка — основной путь).
        if recipient:
            mq.dispatch_once(limit=5)
        return {"ok": True, "message": message}

    @router.post("/{message_id}/retry")
    def retry_message(message_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_MESSAGES_RETRY)
        msg = mq.retry(message_id, force=True)
        if msg is None:
            raise HTTPException(status_code=404, detail="Сообщение не найдено.")
        record_admin_operation(
            session=session, action="messages.retry", target_type="message",
            target_id=message_id, after={"status": msg.get("status")}, reason=payload.reason,
        )
        mq.dispatch_once(limit=5)
        return {"ok": True, "message": mq.get(message_id)}

    @router.post("/{message_id}/cancel")
    def cancel_message(message_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_MESSAGES_CANCEL)
        msg = mq.cancel(message_id)
        if msg is None:
            raise HTTPException(status_code=404, detail="Сообщение не найдено.")
        record_admin_operation(
            session=session, action="messages.cancel", target_type="message",
            target_id=message_id, after={"status": msg.get("status")}, reason=payload.reason,
        )
        return {"ok": True, "message": msg}

    @router.post("/{message_id}/delete")
    def delete_message(message_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_MESSAGES_CANCEL)
        msg = mq.delete(message_id)
        if msg is None:
            raise HTTPException(status_code=404, detail="Сообщение не найдено.")
        record_admin_operation(session=session,action="messages.delete",target_type="message",target_id=message_id,after={"status":msg.get("status")},reason=payload.reason)
        return {"ok":True,"message":msg}

    return router
