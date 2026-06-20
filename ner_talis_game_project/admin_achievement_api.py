"""FastAPI router for Admin V2 Achievements (authoring).

Mounted under ``/api/admin/v2`` with ``/achievements`` (definitions) and
``/achievements/categories``. Reads need achievement.view; the
draft→validate→publish→archive lifecycle is gated per stage by achievement.*
permissions, and every mutation is recorded via admin_operation. Manual
grant/revoke against live players belongs to the achievement engine (runtime)
and is intentionally not here yet.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_ACHIEVEMENT_ARCHIVE,
    PERM_ACHIEVEMENT_CREATE,
    PERM_ACHIEVEMENT_DISABLE,
    PERM_ACHIEVEMENT_EDIT,
    PERM_ACHIEVEMENT_GRANT_MANUAL,
    PERM_ACHIEVEMENT_MANAGE_CATEGORIES,
    PERM_ACHIEVEMENT_PUBLISH,
    PERM_ACHIEVEMENT_REVOKE_MANUAL,
    PERM_ACHIEVEMENT_VALIDATE,
    PERM_ACHIEVEMENT_VIEW,
    PERM_ACHIEVEMENT_VIEW_PLAYER_PROGRESS,
    identity_key,
    require_permission,
)
from services import achievement_service as ach
from services import achievement_engine as engine


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


class PlayerActionRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    game_id: str = Field(min_length=2)
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


def create_admin_achievement_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/achievements", tags=["admin-achievements"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_ACHIEVEMENT_VIEW)
        return {
            "ok": True,
            "types": list(ach.ACHIEVEMENT_TYPES),
            "rarities": list(ach.RARITIES),
            "visibilities": list(ach.VISIBILITIES),
            "conditionLogic": list(ach.CONDITION_LOGIC),
            "conditionTypes": list(ach.CONDITION_TYPES),
            "progressTypes": list(ach.PROGRESS_TYPES),
            "rewardTypes": list(ach.REWARD_TYPES),
            "repeatPeriods": list(ach.REPEAT_PERIODS),
            "statuses": [{"value": s, "label": ach.STATUS_LABELS.get(s, s)} for s in ach.STATUSES],
            "categories": [
                {"id": c.get("id"), "name": (c.get("data") or {}).get("name"), "status": c.get("status")}
                for c in ach.categories().list()
            ],
        }

    # ----- категории -----
    @router.get("/categories")
    def cat_list(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_ACHIEVEMENT_VIEW)
        return {"ok": True, "items": ach.categories().list()}

    @router.post("/categories")
    def cat_create(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ACHIEVEMENT_MANAGE_CATEGORIES)
        try:
            item = run_admin_operation(
                session=session, action="achievement.category_create",
                func=lambda: ach.categories().create(payload.id, payload.data, actor=_actor(session)),
                target_type="achievement_category", target_id=payload.id,
                target_name=str(payload.data.get("name") or payload.id), reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/categories/{cat_id}")
    def cat_update(cat_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ACHIEVEMENT_MANAGE_CATEGORIES)
        try:
            item = run_admin_operation(
                session=session, action="achievement.category_edit",
                func=lambda: ach.categories().update(cat_id, payload.data, actor=_actor(session)),
                target_type="achievement_category", target_id=cat_id, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    # ----- достижения -----
    @router.get("")
    def list_achievements(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_ACHIEVEMENT_VIEW)
        return {"ok": True, "items": ach.store().list(status=status)}

    @router.get("/{ach_id}")
    def get_achievement(ach_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_ACHIEVEMENT_VIEW)
        item = ach.store().get(ach_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Достижение не найдено.")
        return {"ok": True, "item": item, "validation": ach.validate(item)}

    @router.post("")
    def create_achievement(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ACHIEVEMENT_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="achievement.create",
                func=lambda: ach.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="achievement", target_id=payload.id,
                target_name=str(payload.data.get("name") or payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{ach_id}")
    def update_achievement(ach_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ACHIEVEMENT_EDIT)
        before = ach.store().get(ach_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Достижение не найдено.")
        try:
            item = run_admin_operation(
                session=session, action="achievement.edit",
                func=lambda: ach.store().update(ach_id, payload.data, actor=_actor(session)),
                target_type="achievement", target_id=ach_id,
                target_name=str(before.get("data", {}).get("name") or ach_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{ach_id}/validate")
    def validate_achievement(ach_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ACHIEVEMENT_VALIDATE)
        item = ach.store().get(ach_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Достижение не найдено.")
        result = ach.validate(item)
        record_admin_operation(
            session=session, action="achievement.validate", target_type="achievement",
            target_id=ach_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{ach_id}/publish")
    def publish_achievement(ach_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ACHIEVEMENT_PUBLISH)
        before = ach.store().get(ach_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Достижение не найдено.")
        result = ach.validate(before)
        if not result["ok"]:
            try:
                ach.store().set_status(ach_id, ach.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="achievement.publish", target_type="achievement",
                target_id=ach_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (ach.STATUS_READY, ach.STATUS_DISABLED):
                ach.store().set_status(ach_id, ach.STATUS_READY, actor=_actor(session), force=True)
            return ach.store().set_status(ach_id, ach.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="achievement.publish", func=_publish,
            target_type="achievement", target_id=ach_id,
            target_name=str(before.get("data", {}).get("name") or ach_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(ach_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = ach.store().get(ach_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Достижение не найдено.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: ach.store().set_status(ach_id, target_status, actor=_actor(session)),
                target_type="achievement", target_id=ach_id,
                target_name=str(before.get("data", {}).get("name") or ach_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{ach_id}/disable")
    def disable_achievement(ach_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(ach_id, payload, request, perm=PERM_ACHIEVEMENT_DISABLE, action="achievement.disable", target_status=ach.STATUS_DISABLED)

    @router.post("/{ach_id}/archive")
    def archive_achievement(ach_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(ach_id, payload, request, perm=PERM_ACHIEVEMENT_ARCHIVE, action="achievement.archive", target_status=ach.STATUS_ARCHIVE)

    # ----- прогресс игрока + ручная выдача/откат (achievement engine) -----
    def _load_player(storage, game_id):
        player = storage.get_player_by_game_id(game_id) if hasattr(storage, "get_player_by_game_id") else None
        if not player:
            raise HTTPException(status_code=404, detail="Игрок не найден.")
        return player

    @router.get("/players/{game_id}")
    def player_progress(game_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_ACHIEVEMENT_VIEW_PLAYER_PROGRESS)
        player = _load_player(storage, game_id)
        return {"ok": True, "progress": engine.admin_player_progress(player)}

    @router.post("/{ach_id}/grant")
    def grant_manual(ach_id: str, payload: PlayerActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_ACHIEVEMENT_GRANT_MANUAL)
        if ach.store().get(ach_id) is None:
            raise HTTPException(status_code=404, detail="Достижение не найдено.")
        player = _load_player(storage, payload.game_id)
        granted = run_admin_operation(
            session=session, action="achievement.grant_manual",
            func=lambda: engine.grant(storage, player, ach_id, source="manual", by=_actor(session), reason=payload.reason),
            target_type="achievement", target_id=ach_id, target_name=payload.game_id,
            after_func=lambda r: {"granted": bool(r)}, reason=payload.reason,
            details={"game_id": payload.game_id},
        )
        return {"ok": True, "granted": bool(granted)}

    @router.post("/{ach_id}/revoke")
    def revoke_manual(ach_id: str, payload: PlayerActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_ACHIEVEMENT_REVOKE_MANUAL)
        player = _load_player(storage, payload.game_id)
        removed = run_admin_operation(
            session=session, action="achievement.revoke_manual",
            func=lambda: engine.revoke(storage, player, ach_id, by=_actor(session), reason=payload.reason),
            target_type="achievement", target_id=ach_id, target_name=payload.game_id,
            after_func=lambda r: {"revoked": bool(r)}, reason=payload.reason,
            details={"game_id": payload.game_id},
        )
        return {"ok": True, "revoked": bool(removed)}

    return router
