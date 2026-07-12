"""FastAPI router for Admin V2 Profile Layout constructor (ТЗ §3).

Mounted under ``/api/admin/v2/profile-layout``. Generic over kind (profile_settings /
profile_tab / profile_block / profile_theme). Reads need profile_layout.view; create/edit need
profile_layout.edit; publish/disable/archive/delete need profile_layout.publish.
Every mutation is recorded via admin_operation. The layout runtime (applying the
published layout to the player profile) is a separate step.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_PROFILE_LAYOUT_EDIT,
    PERM_PROFILE_LAYOUT_PUBLISH,
    PERM_PROFILE_LAYOUT_VIEW,
    identity_key,
    require_permission,
)
from services import profile_layout_service as layout
from services.admin_versioning_routes import attach_kinded_versioning_routes


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


class DeleteRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    confirm: str = ""
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


def _check_kind(kind: str) -> None:
    if kind not in layout.KINDS:
        raise HTTPException(status_code=404, detail=f"Неизвестный тип объекта раскладки: {kind}.")


def _title(data: dict[str, Any], kind: str) -> str:
    if kind == layout.KIND_TAB:
        return str(data.get("label") or "")
    if kind == layout.KIND_BLOCK:
        return str(data.get("name") or "")
    return str(data.get("title") or "")


def create_admin_profile_layout_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/profile-layout", tags=["admin-profile-layout"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_PROFILE_LAYOUT_VIEW)
        return {
            "ok": True,
            "kinds": list(layout.KINDS),
            "tabPresets": list(layout.TAB_PRESETS),
            "blockTypes": list(layout.PROFILE_BLOCK_TYPES),
            "visibilities": list(layout.VISIBILITIES),
            "blockWidths": list(layout.BLOCK_WIDTHS),
            "statuses": [{"value": s, "label": layout.STATUS_LABELS.get(s, s)} for s in layout.STATUSES],
        }

    @router.get("/{kind}")
    def list_kind(kind: str, request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _check_kind(kind)
        _require(_session(get_storage(), request, token), PERM_PROFILE_LAYOUT_VIEW)
        items = [i for i in layout.store().list(status=status) if (i.get("data") or {}).get("_kind") == kind]
        return {"ok": True, "items": items}

    @router.get("/{kind}/{object_id}")
    def get_one(kind: str, object_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _check_kind(kind)
        _require(_session(get_storage(), request, token), PERM_PROFILE_LAYOUT_VIEW)
        item = layout.store().get(object_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Объект раскладки не найден.")
        return {"ok": True, "item": item, "validation": layout.validate(kind, item)}

    @router.get("/{kind}/{object_id}/where-used")
    def layout_where_used(kind: str, object_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _check_kind(kind)
        _require(_session(get_storage(), request, token), PERM_PROFILE_LAYOUT_VIEW)
        return {"ok": True, "usedBy": layout.where_used(object_id)}

    @router.post("/{kind}")
    def create(kind: str, payload: IdDataRequest, request: Request) -> dict[str, Any]:
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PROFILE_LAYOUT_EDIT)
        data = {**payload.data, "_kind": kind}
        try:
            item = run_admin_operation(
                session=session, action="profile_layout.create",
                func=lambda: layout.store().create(payload.id, data, actor=_actor(session)),
                target_type=kind, target_id=payload.id, target_name=_title(payload.data, kind),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{kind}/{object_id}")
    def update(kind: str, object_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PROFILE_LAYOUT_EDIT)
        before = layout.store().get(object_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект раскладки не найден.")
        try:
            item = run_admin_operation(
                session=session, action="profile_layout.edit",
                func=lambda: layout.store().update(object_id, {**payload.data, "_kind": kind}, actor=_actor(session)),
                target_type=kind, target_id=object_id, target_name=_title(before.get("data", {}), kind),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{kind}/{object_id}/validate")
    def validate_one(kind: str, object_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PROFILE_LAYOUT_EDIT)
        item = layout.store().get(object_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Объект раскладки не найден.")
        result = layout.validate(kind, item)
        record_admin_operation(
            session=session, action="profile_layout.validate", target_type=kind,
            target_id=object_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{kind}/{object_id}/publish")
    def publish(kind: str, object_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PROFILE_LAYOUT_PUBLISH)
        before = layout.store().get(object_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект раскладки не найден.")
        result = layout.validate(kind, before)
        if not result["ok"]:
            try:
                layout.store().set_status(object_id, layout.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="profile_layout.publish", target_type=kind,
                target_id=object_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (layout.STATUS_READY, layout.STATUS_DISABLED):
                layout.store().set_status(object_id, layout.STATUS_READY, actor=_actor(session), force=True)
            return layout.store().set_status(object_id, layout.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="profile_layout.publish", func=_publish,
            target_type=kind, target_id=object_id, target_name=_title(before.get("data", {}), kind),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(kind, object_id, payload, request, *, action, target_status):
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PROFILE_LAYOUT_PUBLISH)
        before = layout.store().get(object_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект раскладки не найден.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: layout.store().set_status(object_id, target_status, actor=_actor(session)),
                target_type=kind, target_id=object_id, target_name=_title(before.get("data", {}), kind),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{kind}/{object_id}/disable")
    def disable(kind: str, object_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(kind, object_id, payload, request, action="profile_layout.disable", target_status=layout.STATUS_DISABLED)

    @router.post("/{kind}/{object_id}/archive")
    def archive(kind: str, object_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(kind, object_id, payload, request, action="profile_layout.archive", target_status=layout.STATUS_ARCHIVE)

    @router.delete("/{kind}/{object_id}")
    def delete(kind: str, object_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PROFILE_LAYOUT_PUBLISH)
        if payload.confirm != object_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID объекта в поле подтверждения.")
        before = layout.store().get(object_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект раскладки не найден.")
        run_admin_operation(
            session=session, action="profile_layout.delete",
            func=lambda: layout.store().delete(object_id),
            target_type=kind, target_id=object_id, target_name=_title(before.get("data", {}), kind),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    def _pl_get_checked(object_id: str, kind: str) -> dict[str, Any]:
        _check_kind(kind)
        item = layout.store().get(object_id)
        if item is None or (item.get("data") or {}).get("_kind") != kind:
            raise HTTPException(status_code=404, detail="Объект раскладки не найден.")
        return item

    attach_kinded_versioning_routes(
        router,
        session_for=lambda req, tok: _session(get_storage(), req, tok),
        require=_require, actor=_actor, store=layout.store,
        get_checked=_pl_get_checked,
        view_perm_for=lambda k: PERM_PROFILE_LAYOUT_VIEW,
        edit_perm_for=lambda k: PERM_PROFILE_LAYOUT_EDIT,
        publish_perm_for=lambda k: PERM_PROFILE_LAYOUT_PUBLISH,
        target_type_for=lambda k: f"profile_layout.{k}",
    )
    return router
