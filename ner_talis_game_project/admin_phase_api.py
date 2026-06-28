"""FastAPI router for Admin V2 Boss-phase constructor (ТЗ «черты/благословения/фазы» §7).

Mounted under ``/api/admin/v2/phases``. Reads need phase.view; lifecycle gated by
phase.* and audited. POST /import seeds the universal boss-phase library.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_PHASE_ARCHIVE,
    PERM_PHASE_CREATE,
    PERM_PHASE_DELETE,
    PERM_PHASE_DISABLE,
    PERM_PHASE_EDIT,
    PERM_PHASE_PUBLISH,
    PERM_PHASE_VALIDATE,
    PERM_PHASE_VIEW,
    identity_key,
    require_permission,
)
from services import phase_constructor_service as phases
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
    return str((data or {}).get("phase_name") or fallback)


def create_admin_phase_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/phases", tags=["admin-phases"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_PHASE_VIEW)
        return {
            "ok": True,
            "bossRanks": [{"value": r, "label": phases.BOSS_RANK_LABELS.get(r, r)} for r in phases.BOSS_RANKS],
            "triggerTypes": [{"value": t, "label": phases.TRIGGER_TYPE_LABELS.get(t, t)} for t in phases.TRIGGER_TYPES],
            "statuses": [{"value": s, "label": phases.STATUS_LABELS.get(s, s)} for s in phases.STATUSES],
        }

    @router.get("")
    def list_phases(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_PHASE_VIEW)
        return {"ok": True, "items": phases.store().list(status=status)}

    @router.get("/{phase_id}")
    def get_phase(phase_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_PHASE_VIEW)
        item = phases.store().get(phase_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Фаза не найдена.")
        return {"ok": True, "item": item, "validation": phases.validate(item)}

    @router.post("")
    def create_phase(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PHASE_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="phase.create",
                func=lambda: phases.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="phase", target_id=payload.id, target_name=_name(payload.data, payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{phase_id}")
    def update_phase(phase_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PHASE_EDIT)
        before = phases.store().get(phase_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Фаза не найдена.")
        # 18-CODEX §2: правка опубликованной фазы меняет live → нужно publish-право.
        if before.get("status") == phases.STATUS_PUBLISHED:
            _require(session, PERM_PHASE_PUBLISH)
        try:
            item = run_admin_operation(
                session=session, action="phase.edit",
                func=lambda: phases.store().update(phase_id, payload.data, actor=_actor(session)),
                target_type="phase", target_id=phase_id, target_name=_name(before.get("data"), phase_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/import")
    def import_existing(payload: ImportRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PHASE_PUBLISH)
        from services import constructor_import
        report = run_admin_operation(
            session=session, action="phase.import_existing",
            func=lambda: constructor_import.import_phases(mode=payload.mode, actor=_actor(session)),
            target_type="constructor_import", target_id="phase",
            after_func=lambda r: {"created": r.get("created"), "skipped": r.get("skipped")}, reason=payload.reason,
        )
        return {"ok": True, "report": report}

    @router.post("/{phase_id}/validate")
    def validate_phase(phase_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PHASE_VALIDATE)
        item = phases.store().get(phase_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Фаза не найдена.")
        result = phases.validate(item)
        record_admin_operation(
            session=session, action="phase.validate", target_type="phase",
            target_id=phase_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{phase_id}/publish")
    def publish_phase(phase_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PHASE_PUBLISH)
        before = phases.store().get(phase_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Фаза не найдена.")
        result = phases.validate(before)
        if not result["ok"]:
            try:
                phases.store().set_status(phase_id, phases.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="phase.publish", target_type="phase",
                target_id=phase_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (phases.STATUS_READY, phases.STATUS_DISABLED):
                phases.store().set_status(phase_id, phases.STATUS_READY, actor=_actor(session), force=True)
            return phases.store().set_status(phase_id, phases.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="phase.publish", func=_publish,
            target_type="phase", target_id=phase_id, target_name=_name(before.get("data"), phase_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(phase_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = phases.store().get(phase_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Фаза не найдена.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: phases.store().set_status(phase_id, target_status, actor=_actor(session)),
                target_type="phase", target_id=phase_id, target_name=_name(before.get("data"), phase_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{phase_id}/disable")
    def disable_phase(phase_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(phase_id, payload, request, perm=PERM_PHASE_DISABLE, action="phase.disable", target_status=phases.STATUS_DISABLED)

    @router.post("/{phase_id}/archive")
    def archive_phase(phase_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(phase_id, payload, request, perm=PERM_PHASE_ARCHIVE, action="phase.archive", target_status=phases.STATUS_ARCHIVE)

    @router.delete("/{phase_id}")
    def delete_phase(phase_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_PHASE_DELETE)
        if payload.confirm != phase_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID фазы.")
        before = phases.store().get(phase_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Фаза не найдена.")
        run_admin_operation(
            session=session, action="phase.delete",
            func=lambda: phases.store().delete(phase_id),
            target_type="phase", target_id=phase_id, target_name=_name(before.get("data"), phase_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    attach_entity_versioning_routes(
        router,
        session_for=lambda req, tok: _session(get_storage(), req, tok),
        require=_require, actor=_actor, store=phases.store,
        target_type="phase", name_field="phase_name",
        view_perm=PERM_PHASE_VIEW, edit_perm=PERM_PHASE_EDIT, publish_perm=PERM_PHASE_PUBLISH,
        not_found="Фаза не найдена.",
    )
    return router
