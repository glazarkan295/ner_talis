"""FastAPI router for the Admin V2 «Конструктор мира» (data-driven world editor).

Mounted under ``/api/admin/v2/world``, parallel to the rest of V2. Generic over
content ``kind`` (first kind: ``location``). Reads need world.view; the
draft→validate→publish→archive lifecycle is gated per stage by the world.*
permissions, and every mutation is recorded as an admin_operation (so it shows
up in the audit viewer with role + reason + before/after).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_WORLD_ARCHIVE,
    PERM_WORLD_CREATE_DRAFT,
    PERM_WORLD_DISABLE,
    PERM_WORLD_EDIT_DRAFT,
    PERM_WORLD_PUBLISH,
    PERM_WORLD_VALIDATE,
    PERM_WORLD_VIEW,
    identity_key,
    require_permission,
)
from services import world_content_registry as registry


# --- Запросы ----------------------------------------------------------------
class WorldCreateRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    id: str = Field(min_length=2)
    data: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class WorldUpdateRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    data: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class WorldStatusRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    status: str
    reason: str = ""


class WorldActionRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    reason: str = ""


# --- Хелперы аутентификации (зеркалят admin_panel_v2_api, держим изолированно)
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


def _ensure_kind(kind: str) -> str:
    if kind not in registry.KINDS:
        raise HTTPException(status_code=404, detail=f"Неизвестный тип контента: {kind}.")
    return kind


# Статусы, которые можно ставить обычной правкой (без опасных прав publish и т.п.)
_DRAFT_FLOW_STATUSES = {
    registry.STATUS_DRAFT,
    registry.STATUS_REVIEW,
    registry.STATUS_READY,
}


def create_admin_world_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/world", tags=["admin-world"])

    @router.get("/kinds")
    def get_kinds(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_WORLD_VIEW)
        return {
            "ok": True,
            "kinds": list(registry.KINDS),
            "statuses": [{"value": s, "label": registry.STATUS_LABELS.get(s, s)} for s in registry.STATUSES],
            "locationTypes": list(registry.LOCATION_TYPES),
            "mobTypes": list(registry.MOB_TYPES),
        }

    @router.get("/{kind}")
    def list_kind(kind: str, request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_WORLD_VIEW)
        _ensure_kind(kind)
        return {"ok": True, "items": registry.list_content(kind, status=status)}

    @router.get("/{kind}/{content_id}")
    def get_one(kind: str, content_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_WORLD_VIEW)
        _ensure_kind(kind)
        obj = registry.get_content(kind, content_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        return {"ok": True, "item": obj}

    @router.post("/{kind}")
    def create(kind: str, payload: WorldCreateRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_WORLD_CREATE_DRAFT)
        _ensure_kind(kind)
        try:
            item = run_admin_operation(
                session=session,
                action="world.create_draft",
                func=lambda: registry.create_content(kind, payload.id, payload.data, actor=_actor(session)),
                target_type=kind,
                target_id=payload.id,
                target_name=str(payload.data.get("name") or payload.id),
                after_func=lambda r: {"status": r.get("status")},
                reason=payload.reason,
                details={"kind": kind},
            )
        except registry.ContentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{kind}/{content_id}")
    def update(kind: str, content_id: str, payload: WorldUpdateRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_WORLD_EDIT_DRAFT)
        _ensure_kind(kind)
        before = registry.get_content(kind, content_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        try:
            item = run_admin_operation(
                session=session,
                action="world.edit_draft",
                func=lambda: registry.update_content(kind, content_id, payload.data, actor=_actor(session)),
                target_type=kind,
                target_id=content_id,
                target_name=str(before.get("data", {}).get("name") or content_id),
                before={"status": before.get("status"), "version": before.get("version")},
                after_func=lambda r: {"status": r.get("status"), "version": r.get("version")},
                reason=payload.reason,
                details={"kind": kind},
            )
        except registry.ContentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{kind}/{content_id}/status")
    def change_status(kind: str, content_id: str, payload: WorldStatusRequest, request: Request) -> dict[str, Any]:
        # Обычные переходы черновика (draft/review/ready). Опасные publish/
        # disable/archive — отдельными эндпоинтами с отдельными правами.
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_WORLD_EDIT_DRAFT)
        _ensure_kind(kind)
        if payload.status not in _DRAFT_FLOW_STATUSES:
            raise HTTPException(status_code=400, detail="Для публикации/отключения/архива используйте отдельные действия.")
        before = registry.get_content(kind, content_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        try:
            item = run_admin_operation(
                session=session,
                action="world.set_status",
                func=lambda: registry.set_status(kind, content_id, payload.status, actor=_actor(session)),
                target_type=kind,
                target_id=content_id,
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")},
                reason=payload.reason,
                details={"kind": kind, "status": payload.status},
            )
        except registry.ContentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{kind}/{content_id}/validate")
    def validate(kind: str, content_id: str, payload: WorldActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_WORLD_VALIDATE)
        _ensure_kind(kind)
        obj = registry.get_content(kind, content_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        result = registry.validate_envelope(obj)
        registry.record_validation(kind, content_id, result)
        record_admin_operation(
            session=session,
            action="world.validate",
            target_type=kind,
            target_id=content_id,
            after={"ok": result["ok"], "errors": len(result["errors"]), "warnings": len(result["warnings"])},
            reason=payload.reason,
            details={"kind": kind},
        )
        return {"ok": True, "validation": result}

    @router.post("/{kind}/{content_id}/publish")
    def publish(kind: str, content_id: str, payload: WorldActionRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_WORLD_PUBLISH)
        _ensure_kind(kind)
        before = registry.get_content(kind, content_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        # Публиковать можно только то, что прошло проверку без ошибок.
        result = registry.validate_envelope(before)
        registry.record_validation(kind, content_id, result)
        if not result["ok"]:
            # Помечаем как ошибку проверки и не публикуем.
            try:
                registry.set_status(kind, content_id, registry.STATUS_ERROR, actor=_actor(session), force=True)
            except registry.ContentError:
                pass
            record_admin_operation(
                session=session, action="world.publish", target_type=kind,
                target_id=content_id, status="error",
                error="; ".join(result["errors"]), reason=payload.reason,
                details={"kind": kind, "errors": result["errors"]},
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            # Перевести через ready (если ещё черновик), затем опубликовать.
            if before.get("status") not in (registry.STATUS_READY, registry.STATUS_DISABLED):
                registry.set_status(kind, content_id, registry.STATUS_READY, actor=_actor(session), force=True)
            return registry.set_status(kind, content_id, registry.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session,
            action="world.publish",
            func=_publish,
            target_type=kind,
            target_id=content_id,
            target_name=str(before.get("data", {}).get("name") or content_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")},
            reason=payload.reason,
            details={"kind": kind, "warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    @router.post("/{kind}/{content_id}/disable")
    def disable(kind: str, content_id: str, payload: WorldActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(get_storage(), request, kind, content_id, payload,
                          perm=PERM_WORLD_DISABLE, action="world.disable",
                          target_status=registry.STATUS_DISABLED)

    @router.post("/{kind}/{content_id}/archive")
    def archive(kind: str, content_id: str, payload: WorldActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(get_storage(), request, kind, content_id, payload,
                          perm=PERM_WORLD_ARCHIVE, action="world.archive",
                          target_status=registry.STATUS_ARCHIVED)

    def _lifecycle(storage, request, kind, content_id, payload, *, perm, action, target_status) -> dict[str, Any]:
        session = _session(storage, request, payload.token)
        _require(session, perm)
        _ensure_kind(kind)
        before = registry.get_content(kind, content_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        try:
            item = run_admin_operation(
                session=session,
                action=action,
                func=lambda: registry.set_status(kind, content_id, target_status, actor=_actor(session)),
                target_type=kind,
                target_id=content_id,
                target_name=str(before.get("data", {}).get("name") or content_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")},
                reason=payload.reason,
                details={"kind": kind},
            )
        except registry.ContentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    return router
