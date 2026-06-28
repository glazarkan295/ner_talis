"""FastAPI router for Admin V2 Fine Constructor (authoring fine TYPES).

Mounted under ``/api/admin/v2/fines``. Reads need fine_def.view; the
draft→validate→publish→archive lifecycle + delete are gated per stage by
fine_def.* permissions and recorded via admin_operation. Per-player active fines
(issue/pay/forgive/repair) live in services/fine_service.py, not here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_FINE_DEF_ARCHIVE,
    PERM_FINE_DEF_CREATE,
    PERM_FINE_DEF_DELETE,
    PERM_FINE_DEF_DISABLE,
    PERM_FINE_DEF_EDIT,
    PERM_FINE_DEF_PUBLISH,
    PERM_FINE_DEF_VALIDATE,
    PERM_FINE_DEF_VIEW,
    identity_key,
    require_permission,
)
from services import fine_constructor_service as fines
from services.admin_versioning_routes import attach_entity_versioning_routes


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


def _name(data: dict[str, Any], fallback: str) -> str:
    return str((data or {}).get("name") or fallback)


def create_admin_fines_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/fines", tags=["admin-fines"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_FINE_DEF_VIEW)
        return {
            "ok": True,
            "fineTypes": list(fines.FINE_TYPES),
            "sources": list(fines.FINE_SOURCES),
            "issuerRoles": list(fines.ISSUER_ROLES),
            "currencies": list(fines.CURRENCIES),
            "restrictions": list(fines.RESTRICTIONS),
            "statuses": [{"value": s, "label": fines.STATUS_LABELS.get(s, s)} for s in fines.STATUSES],
        }

    @router.get("")
    def list_fines(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_FINE_DEF_VIEW)
        return {"ok": True, "items": fines.store().list(status=status)}

    @router.get("/{fine_id}")
    def get_fine(fine_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_FINE_DEF_VIEW)
        item = fines.store().get(fine_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Тип штрафа не найден.")
        return {"ok": True, "item": item, "validation": fines.validate(item)}

    @router.post("")
    def create_fine(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_FINE_DEF_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="fine_def.create",
                func=lambda: fines.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="fine_def", target_id=payload.id, target_name=_name(payload.data, payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{fine_id}")
    def update_fine(fine_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_FINE_DEF_EDIT)
        before = fines.store().get(fine_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Тип штрафа не найден.")
        try:
            item = run_admin_operation(
                session=session, action="fine_def.edit",
                func=lambda: fines.store().update(fine_id, payload.data, actor=_actor(session)),
                target_type="fine_def", target_id=fine_id, target_name=_name(before.get("data"), fine_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{fine_id}/validate")
    def validate_fine(fine_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_FINE_DEF_VALIDATE)
        item = fines.store().get(fine_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Тип штрафа не найден.")
        result = fines.validate(item)
        record_admin_operation(
            session=session, action="fine_def.validate", target_type="fine_def",
            target_id=fine_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{fine_id}/publish")
    def publish_fine(fine_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_FINE_DEF_PUBLISH)
        before = fines.store().get(fine_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Тип штрафа не найден.")
        result = fines.validate(before)
        if not result["ok"]:
            try:
                fines.store().set_status(fine_id, fines.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="fine_def.publish", target_type="fine_def",
                target_id=fine_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (fines.STATUS_READY, fines.STATUS_DISABLED):
                fines.store().set_status(fine_id, fines.STATUS_READY, actor=_actor(session), force=True)
            return fines.store().set_status(fine_id, fines.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="fine_def.publish", func=_publish,
            target_type="fine_def", target_id=fine_id, target_name=_name(before.get("data"), fine_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(fine_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = fines.store().get(fine_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Тип штрафа не найден.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: fines.store().set_status(fine_id, target_status, actor=_actor(session)),
                target_type="fine_def", target_id=fine_id, target_name=_name(before.get("data"), fine_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{fine_id}/disable")
    def disable_fine(fine_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(fine_id, payload, request, perm=PERM_FINE_DEF_DISABLE, action="fine_def.disable", target_status=fines.STATUS_DISABLED)

    @router.post("/{fine_id}/archive")
    def archive_fine(fine_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(fine_id, payload, request, perm=PERM_FINE_DEF_ARCHIVE, action="fine_def.archive", target_status=fines.STATUS_ARCHIVE)

    @router.delete("/{fine_id}")
    def delete_fine(fine_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_FINE_DEF_DELETE)
        if payload.confirm != fine_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID типа штрафа в поле подтверждения.")
        before = fines.store().get(fine_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Тип штрафа не найден.")
        run_admin_operation(
            session=session, action="fine_def.delete",
            func=lambda: fines.store().delete(fine_id),
            target_type="fine_def", target_id=fine_id, target_name=_name(before.get("data"), fine_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    attach_entity_versioning_routes(
        router,
        session_for=lambda req, tok: _session(get_storage(), req, tok),
        require=_require, actor=_actor, store=fines.store,
        target_type="fine_def",
        view_perm=PERM_FINE_DEF_VIEW, edit_perm=PERM_FINE_DEF_EDIT, publish_perm=PERM_FINE_DEF_PUBLISH,
        not_found="Штраф не найден.",
    )
    return router
