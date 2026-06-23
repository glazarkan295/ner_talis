"""FastAPI router for Admin V2 Guilds + World Events.

Mounted under ``/api/admin/v2`` with two groups: ``/guilds`` and ``/events``.
Reads need the matching .view permission; every mutation is gated by the staged
guild.* / world_event.* permissions and recorded via admin_operation. The data
layer is guild_service / world_event_service (generic EntityStore).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_operation import run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_entity_store import EntityError
from services.admin_rbac import (
    PERM_GUILD_CREATE,
    PERM_GUILD_DISABLE,
    PERM_GUILD_EDIT,
    PERM_GUILD_MANAGE_MEMBERS,
    PERM_GUILD_VIEW,
    PERM_WORLD_EVENT_ARCHIVE,
    PERM_WORLD_EVENT_CREATE,
    PERM_WORLD_EVENT_EDIT,
    PERM_WORLD_EVENT_REWARD,
    PERM_WORLD_EVENT_SCHEDULE,
    PERM_WORLD_EVENT_START,
    PERM_WORLD_EVENT_STOP,
    PERM_WORLD_EVENT_VIEW,
    identity_key,
    require_permission,
)
from services import guild_service as guilds
from services import world_event_service as events


class IdDataRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    id: str = Field(min_length=2)
    data: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class DataRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    data: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ActionRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    reason: str = ""


class MemberRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    user_id: str = Field(min_length=1)
    role: str = "newbie"
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


def create_admin_community_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2", tags=["admin-community"])

    # ===================== ГИЛЬДИИ =====================
    @router.get("/guilds/meta")
    def guild_meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_GUILD_VIEW)
        return {
            "ok": True,
            "types": list(guilds.GUILD_TYPES),
            "roles": list(guilds.GUILD_ROLES),
            "statuses": [{"value": s, "label": guilds.STATUS_LABELS.get(s, s)} for s in guilds.STATUSES],
        }

    @router.get("/guilds")
    def guild_list(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_GUILD_VIEW)
        return {"ok": True, "items": guilds.store().list(status=status)}

    @router.get("/guilds/{guild_id}")
    def guild_get(guild_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_GUILD_VIEW)
        item = guilds.store().get(guild_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Гильдия не найдена.")
        return {"ok": True, "item": item, "validation": guilds.validate(item)}

    @router.post("/guilds")
    def guild_create(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_GUILD_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="guild.create",
                func=lambda: guilds.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="guild", target_id=payload.id,
                target_name=str(payload.data.get("name") or payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/guilds/{guild_id}")
    def guild_update(guild_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_GUILD_EDIT)
        before = guilds.store().get(guild_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Гильдия не найдена.")
        try:
            item = run_admin_operation(
                session=session, action="guild.edit",
                func=lambda: guilds.store().update(guild_id, payload.data, actor=_actor(session)),
                target_type="guild", target_id=guild_id,
                target_name=str(before.get("data", {}).get("name") or guild_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    def _guild_status(guild_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = guilds.store().get(guild_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Гильдия не найдена.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: guilds.store().set_status(guild_id, target_status, actor=_actor(session)),
                target_type="guild", target_id=guild_id,
                target_name=str(before.get("data", {}).get("name") or guild_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/guilds/{guild_id}/activate")
    def guild_activate(guild_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _guild_status(guild_id, payload, request, perm=PERM_GUILD_EDIT, action="guild.activate", target_status=guilds.STATUS_ACTIVE)

    @router.post("/guilds/{guild_id}/freeze")
    def guild_freeze(guild_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _guild_status(guild_id, payload, request, perm=PERM_GUILD_EDIT, action="guild.freeze", target_status=guilds.STATUS_FROZEN)

    @router.post("/guilds/{guild_id}/disband")
    def guild_disband(guild_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _guild_status(guild_id, payload, request, perm=PERM_GUILD_DISABLE, action="guild.disable", target_status=guilds.STATUS_DISBANDED)

    @router.post("/guilds/{guild_id}/archive")
    def guild_archive(guild_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _guild_status(guild_id, payload, request, perm=PERM_GUILD_DISABLE, action="guild.archive", target_status=guilds.STATUS_ARCHIVE)

    @router.post("/guilds/{guild_id}/members")
    def guild_add_member(guild_id: str, payload: MemberRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_GUILD_MANAGE_MEMBERS)
        try:
            item = run_admin_operation(
                session=session, action="guild.member_add",
                func=lambda: guilds.add_member(guild_id, payload.user_id, payload.role, actor=_actor(session)),
                target_type="guild", target_id=guild_id, target_name=payload.user_id,
                after_func=lambda r: {"members": len((r.get("data") or {}).get("members") or [])},
                reason=payload.reason, details={"user_id": payload.user_id, "role": payload.role},
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/guilds/{guild_id}/members/set-role")
    def guild_set_role(guild_id: str, payload: MemberRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_GUILD_MANAGE_MEMBERS)
        try:
            item = run_admin_operation(
                session=session, action="guild.member_role",
                func=lambda: guilds.set_member_role(guild_id, payload.user_id, payload.role, actor=_actor(session)),
                target_type="guild", target_id=guild_id, target_name=payload.user_id,
                reason=payload.reason, details={"user_id": payload.user_id, "role": payload.role},
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/guilds/{guild_id}/members/remove")
    def guild_remove_member(guild_id: str, payload: MemberRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_GUILD_MANAGE_MEMBERS)
        try:
            item = run_admin_operation(
                session=session, action="guild.member_remove",
                func=lambda: guilds.remove_member(guild_id, payload.user_id, actor=_actor(session)),
                target_type="guild", target_id=guild_id, target_name=payload.user_id,
                reason=payload.reason, details={"user_id": payload.user_id},
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    # ===================== МИРОВЫЕ СОБЫТИЯ =====================
    @router.get("/events/meta")
    def event_meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_WORLD_EVENT_VIEW)
        return {
            "ok": True,
            "types": list(events.EVENT_TYPES),
            "repeatTypes": list(events.REPEAT_TYPES),
            "rewardTypes": list(events.REWARD_TYPES),
            "specialLootSources": list(events.SPECIAL_LOOT_SOURCES),
            "locationBindings": list(events.LOCATION_BINDINGS),
            "statuses": [{"value": s, "label": events.STATUS_LABELS.get(s, s)} for s in events.STATUSES],
            "maxMultiplier": events.MAX_WORLD_MULTIPLIER,
        }

    @router.get("/events")
    def event_list(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_WORLD_EVENT_VIEW)
        return {"ok": True, "items": events.store().list(status=status)}

    @router.get("/events/{event_id}")
    def event_get(event_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_WORLD_EVENT_VIEW)
        item = events.store().get(event_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Событие не найдено.")
        return {"ok": True, "item": item, "validation": events.validate(item)}

    @router.post("/events")
    def event_create(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_WORLD_EVENT_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="world_event.create",
                func=lambda: events.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="world_event", target_id=payload.id,
                target_name=str(payload.data.get("name") or payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/events/{event_id}")
    def event_update(event_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_WORLD_EVENT_EDIT)
        before = events.store().get(event_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Событие не найдено.")
        try:
            item = run_admin_operation(
                session=session, action="world_event.edit",
                func=lambda: events.store().update(event_id, payload.data, actor=_actor(session)),
                target_type="world_event", target_id=event_id,
                target_name=str(before.get("data", {}).get("name") or event_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    def _event_status(event_id, payload, request, *, perm, action, target_status, validate_first=False):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = events.store().get(event_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Событие не найдено.")
        if validate_first:
            result = events.validate(before)
            if not result["ok"]:
                raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: events.store().set_status(event_id, target_status, actor=_actor(session)),
                target_type="world_event", target_id=event_id,
                target_name=str(before.get("data", {}).get("name") or event_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/events/{event_id}/schedule")
    def event_schedule(event_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _event_status(event_id, payload, request, perm=PERM_WORLD_EVENT_SCHEDULE, action="world_event.schedule", target_status=events.STATUS_SCHEDULED, validate_first=True)

    @router.post("/events/{event_id}/start")
    def event_start(event_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _event_status(event_id, payload, request, perm=PERM_WORLD_EVENT_START, action="world_event.start", target_status=events.STATUS_ACTIVE, validate_first=True)

    @router.post("/events/{event_id}/stop")
    def event_stop(event_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _event_status(event_id, payload, request, perm=PERM_WORLD_EVENT_STOP, action="world_event.stop", target_status=events.STATUS_DISABLED)

    @router.post("/events/{event_id}/finish")
    def event_finish(event_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _event_status(event_id, payload, request, perm=PERM_WORLD_EVENT_STOP, action="world_event.finish", target_status=events.STATUS_FINISHED)

    @router.post("/events/{event_id}/archive")
    def event_archive(event_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _event_status(event_id, payload, request, perm=PERM_WORLD_EVENT_ARCHIVE, action="world_event.archive", target_status=events.STATUS_ARCHIVE)

    @router.post("/events/{event_id}/reward")
    def event_reward(event_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_WORLD_EVENT_REWARD)
        before = events.store().get(event_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Событие не найдено.")
        item = run_admin_operation(
            session=session, action="world_event.reward",
            func=lambda: events.store().update(event_id, {"rewards_distributed": True}, actor=_actor(session)),
            target_type="world_event", target_id=event_id,
            target_name=str(before.get("data", {}).get("name") or event_id),
            after_func=lambda r: {"rewards_distributed": True}, reason=payload.reason,
        )
        return {"ok": True, "item": item}

    return router
