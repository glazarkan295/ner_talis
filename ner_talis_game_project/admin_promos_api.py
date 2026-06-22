"""FastAPI router for Admin V2 Promo codes + Broadcasts (ТЗ §9).

Mounted under ``/api/admin/v2/promos`` and ``/api/admin/v2/broadcast``. Migrates
the V1 admin-panel promo/broadcast tools into the RBAC-aware V2 console: reads
need promos.view, promo create/delete need promos.manage, broadcasts need
broadcast.send. Reuses the existing services (admin_panel_service promo helpers,
broadcast_service) so behaviour/rewards/audit stay identical — V2 only adds the
per-action permission gate. Reward items use the same catalog as the V1 panel
(GET /api/admin/catalog), including synthetic coin/exp/points ids.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_operation import record_admin_operation
from services.admin_panel_service import (
    create_admin_promo,
    delete_admin_promo,
    duration_to_expires_at,
    promo_list_payload,
    require_admin_session,
)
from services.admin_rbac import (
    PERM_BROADCAST_SEND,
    PERM_PROMOS_MANAGE,
    PERM_PROMOS_VIEW,
    identity_key,
    require_permission,
)


class RewardItem(BaseModel):
    item_id: str
    amount: int = Field(gt=0)


class PromoCreateRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    code: str = Field(min_length=1)
    uses_left: int = Field(gt=0)
    duration: str = "never"
    rewards: list[RewardItem] = Field(default_factory=list)
    reason: str = ""


class BroadcastPreviewRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    audience: str
    specific_players: list[str] = Field(default_factory=list)


class BroadcastRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    audience: str
    message: str = Field(min_length=1)
    specific_players: list[str] = Field(default_factory=list)
    reason: str = ""


# Поддерживаемые «времена жизни» промокода (значение → русская подпись).
PROMO_DURATIONS = [
    ("never", "Бессрочно"), ("1h", "1 час"), ("12h", "12 часов"),
    ("1d", "1 день"), ("7d", "7 дней"), ("30d", "30 дней"), ("365d", "1 год"),
]


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


def _reward_dicts(rewards: list[RewardItem]) -> list[dict[str, Any]]:
    return [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in rewards]


def create_admin_promos_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2", tags=["admin-promos"])

    @router.get("/promos/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_PROMOS_VIEW)
        from services.broadcast_service import AUDIENCE_LABELS
        return {
            "ok": True,
            "durations": [{"value": v, "label": label} for v, label in PROMO_DURATIONS],
            "audiences": [{"value": v, "label": label} for v, label in AUDIENCE_LABELS.items()],
        }

    @router.get("/promos")
    def list_promos(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        _require(_session(storage, request, token), PERM_PROMOS_VIEW)
        return {"ok": True, "promos": promo_list_payload(storage)}

    @router.post("/promos")
    def create_promo(payload: PromoCreateRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_PROMOS_MANAGE)
        # Раннее понятное сообщение про неизвестное время жизни (до создания).
        try:
            duration_to_expires_at(payload.duration)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            promo = create_admin_promo(
                storage, code=payload.code, uses_left=payload.uses_left,
                duration=payload.duration, rewards=_reward_dicts(payload.rewards),
                admin_session=session,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "promo": promo}

    @router.delete("/promos")
    def delete_promo(request: Request, code: str = Query(..., min_length=1), token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        # Код в query, а не в path: промокоды могут содержать слэши/пробелы.
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_PROMOS_MANAGE)
        if not delete_admin_promo(storage, code=code, admin_session=session):
            raise HTTPException(status_code=404, detail="Промокод не найден.")
        return {"ok": True, "code": code}

    @router.post("/broadcast/preview")
    def broadcast_preview(payload: BroadcastPreviewRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        _require(_session(storage, request, payload.token), PERM_BROADCAST_SEND)
        from services.broadcast_service import AUDIENCE_LABELS, BroadcastError, select_recipient_ids
        try:
            recipient_ids = select_recipient_ids(storage, payload.audience, payload.specific_players)
        except BroadcastError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True, "audience": payload.audience,
            "audienceLabel": AUDIENCE_LABELS.get(payload.audience, payload.audience),
            "recipients": len(recipient_ids),
        }

    @router.post("/broadcast")
    def broadcast_send(payload: BroadcastRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_BROADCAST_SEND)
        from services.broadcast_service import BroadcastError, broadcast_message
        try:
            result = broadcast_message(storage, payload.audience, payload.message, payload.specific_players)
        except BroadcastError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_admin_operation(
            session=session, action="broadcast.send", target_type="broadcast",
            target_id=str(result.get("audience") or payload.audience),
            target_name=str(result.get("audienceLabel") or result.get("audience") or payload.audience),
            reason=payload.reason,
            details={
                "audience": result.get("audience"), "recipients": result.get("recipients"),
                "delivered": result.get("delivered"), "message_preview": payload.message[:80],
            },
        )
        return {"ok": True, **result}

    return router
