"""FastAPI router for Admin V2 Blessing constructor (ТЗ «черты/благословения/фазы» §8).

Mounted under ``/api/admin/v2/blessings``. Reads need blessing.view; lifecycle
gated by blessing.* and audited. POST /import seeds the blessing library.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_BLESSING_ARCHIVE,
    PERM_BLESSING_CREATE,
    PERM_BLESSING_DELETE,
    PERM_BLESSING_DISABLE,
    PERM_BLESSING_EDIT,
    PERM_BLESSING_PUBLISH,
    PERM_BLESSING_VALIDATE,
    PERM_BLESSING_VIEW,
    identity_key,
    require_permission,
)
from services import blessing_constructor_service as blessings
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


class ImportRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    mode: str = "new"
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
    return str((data or {}).get("blessing_name") or fallback)


def create_admin_blessing_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/blessings", tags=["admin-blessings"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_BLESSING_VIEW)
        return {
            "ok": True,
            "sourceTypes": [{"value": s, "label": blessings.SOURCE_TYPE_LABELS.get(s, s)} for s in blessings.SOURCE_TYPES],
            "allowedTargets": [{"value": t, "label": blessings.TARGET_LABELS.get(t, t)} for t in blessings.ALLOWED_TARGETS],
            "stackRules": list(blessings.STACK_RULES),
            "statuses": [{"value": s, "label": blessings.STATUS_LABELS.get(s, s)} for s in blessings.STATUSES],
        }

    @router.get("")
    def list_blessings(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_BLESSING_VIEW)
        return {"ok": True, "items": blessings.store().list(status=status)}

    @router.get("/{blessing_id}")
    def get_blessing(blessing_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_BLESSING_VIEW)
        item = blessings.store().get(blessing_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Благословение не найдено.")
        return {"ok": True, "item": item, "validation": blessings.validate(item)}

    @router.post("")
    def create_blessing(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_BLESSING_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="blessing.create",
                func=lambda: blessings.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="blessing", target_id=payload.id, target_name=_name(payload.data, payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{blessing_id}")
    def update_blessing(blessing_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_BLESSING_EDIT)
        before = blessings.store().get(blessing_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Благословение не найдено.")
        try:
            item = run_admin_operation(
                session=session, action="blessing.edit",
                func=lambda: blessings.store().update(blessing_id, payload.data, actor=_actor(session)),
                target_type="blessing", target_id=blessing_id, target_name=_name(before.get("data"), blessing_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/import")
    def import_existing(payload: ImportRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_BLESSING_PUBLISH)
        from services import constructor_import
        report = run_admin_operation(
            session=session, action="blessing.import_existing",
            func=lambda: constructor_import.import_blessings(mode=payload.mode, actor=_actor(session)),
            target_type="constructor_import", target_id="blessing",
            after_func=lambda r: {"created": r.get("created"), "skipped": r.get("skipped")}, reason=payload.reason,
        )
        return {"ok": True, "report": report}

    @router.post("/{blessing_id}/validate")
    def validate_blessing(blessing_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_BLESSING_VALIDATE)
        item = blessings.store().get(blessing_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Благословение не найдено.")
        result = blessings.validate(item)
        record_admin_operation(
            session=session, action="blessing.validate", target_type="blessing",
            target_id=blessing_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{blessing_id}/publish")
    def publish_blessing(blessing_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_BLESSING_PUBLISH)
        before = blessings.store().get(blessing_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Благословение не найдено.")
        result = blessings.validate(before)
        if not result["ok"]:
            try:
                blessings.store().set_status(blessing_id, blessings.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="blessing.publish", target_type="blessing",
                target_id=blessing_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (blessings.STATUS_READY, blessings.STATUS_DISABLED):
                blessings.store().set_status(blessing_id, blessings.STATUS_READY, actor=_actor(session), force=True)
            return blessings.store().set_status(blessing_id, blessings.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="blessing.publish", func=_publish,
            target_type="blessing", target_id=blessing_id, target_name=_name(before.get("data"), blessing_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(blessing_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = blessings.store().get(blessing_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Благословение не найдено.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: blessings.store().set_status(blessing_id, target_status, actor=_actor(session)),
                target_type="blessing", target_id=blessing_id, target_name=_name(before.get("data"), blessing_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{blessing_id}/disable")
    def disable_blessing(blessing_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(blessing_id, payload, request, perm=PERM_BLESSING_DISABLE, action="blessing.disable", target_status=blessings.STATUS_DISABLED)

    @router.post("/{blessing_id}/archive")
    def archive_blessing(blessing_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(blessing_id, payload, request, perm=PERM_BLESSING_ARCHIVE, action="blessing.archive", target_status=blessings.STATUS_ARCHIVE)

    @router.delete("/{blessing_id}")
    def delete_blessing(blessing_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_BLESSING_DELETE)
        if payload.confirm != blessing_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID благословения.")
        before = blessings.store().get(blessing_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Благословение не найдено.")
        run_admin_operation(
            session=session, action="blessing.delete",
            func=lambda: blessings.store().delete(blessing_id),
            target_type="blessing", target_id=blessing_id, target_name=_name(before.get("data"), blessing_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    attach_entity_versioning_routes(
        router,
        session_for=lambda req, tok: _session(get_storage(), req, tok),
        require=_require, actor=_actor, store=blessings.store,
        target_type="blessing", name_field="blessing_name",
        view_perm=PERM_BLESSING_VIEW, edit_perm=PERM_BLESSING_EDIT, publish_perm=PERM_BLESSING_PUBLISH,
        not_found="Благословение не найдено.",
    )
    return router
