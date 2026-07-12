"""FastAPI router for Admin V2 Camp constructor (доп. ТЗ §4).

Mounted under ``/api/admin/v2/camps``. Reads need camp.view; the
draft→validate→publish→archive lifecycle + delete are gated per stage by camp.*
permissions and recorded via admin_operation. POST /import surfaces existing camp
data (data/*.json locations) as published records. GET /for-location/{id}
lists published camps bound to a location (for the location constructor §4.8).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_CAMP_ARCHIVE,
    PERM_CAMP_CREATE,
    PERM_CAMP_DELETE,
    PERM_CAMP_DISABLE,
    PERM_CAMP_EDIT,
    PERM_CAMP_PUBLISH,
    PERM_CAMP_VALIDATE,
    PERM_CAMP_VIEW,
    identity_key,
    require_permission,
)
from services import camp_constructor_service as camps
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
    return str((data or {}).get("name") or fallback)


def create_admin_camp_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/camps", tags=["admin-camps"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_CAMP_VIEW)
        return {
            "ok": True,
            "campTypes": list(camps.CAMP_TYPES),
            "campCategories": list(camps.CAMP_CATEGORIES),
            "safetyTypes": list(camps.SAFETY_TYPES),
            "recoveryTargets": list(camps.RECOVERY_TARGETS),
            "campActions": list(camps.CAMP_ACTIONS),
            "statuses": [{"value": s, "label": camps.STATUS_LABELS.get(s, s)} for s in camps.STATUSES],
        }

    @router.get("")
    def list_camps(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_CAMP_VIEW)
        return {"ok": True, "items": camps.store().list(status=status)}

    @router.get("/for-location/{location_id}")
    def for_location(location_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_CAMP_VIEW)
        return {"ok": True, "camps": camps.published_for_location(location_id)}

    @router.get("/{camp_id}")
    def get_camp(camp_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_CAMP_VIEW)
        item = camps.store().get(camp_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Лагерь не найден.")
        return {"ok": True, "item": item, "validation": camps.validate(item)}

    @router.get("/{camp_id}/usage")
    def camp_usage(camp_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_CAMP_VIEW)
        if camps.store().get(camp_id) is None:
            raise HTTPException(status_code=404, detail="Лагерь не найден.")
        return {"ok": True, "usage": camps.where_used(camp_id)}

    @router.post("")
    def create_camp(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CAMP_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="camp.create",
                func=lambda: camps.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="camp", target_id=payload.id, target_name=_name(payload.data, payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{camp_id}")
    def update_camp(camp_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CAMP_EDIT)
        before = camps.store().get(camp_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Лагерь не найден.")
        # 18-CODEX §2: правка опубликованного лагеря меняет live → нужно publish-право.
        if before.get("status") == camps.STATUS_PUBLISHED:
            _require(session, PERM_CAMP_PUBLISH)
        try:
            item = run_admin_operation(
                session=session, action="camp.edit",
                func=lambda: camps.store().update(camp_id, payload.data, actor=_actor(session)),
                target_type="camp", target_id=camp_id, target_name=_name(before.get("data"), camp_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/import")
    def import_existing(payload: ImportRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CAMP_PUBLISH)
        from services import constructor_import
        report = run_admin_operation(
            session=session, action="camp.import_existing",
            func=lambda: constructor_import.import_camps(mode=payload.mode, actor=_actor(session)),
            target_type="constructor_import", target_id="camp",
            after_func=lambda r: {"created": r.get("created"), "skipped": r.get("skipped")}, reason=payload.reason,
        )
        return {"ok": True, "report": report}

    @router.post("/{camp_id}/validate")
    def validate_camp(camp_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CAMP_VALIDATE)
        item = camps.store().get(camp_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Лагерь не найден.")
        result = camps.validate(item)
        record_admin_operation(
            session=session, action="camp.validate", target_type="camp",
            target_id=camp_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{camp_id}/publish")
    def publish_camp(camp_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CAMP_PUBLISH)
        before = camps.store().get(camp_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Лагерь не найден.")
        result = camps.validate(before)
        if not result["ok"]:
            try:
                camps.store().set_status(camp_id, camps.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="camp.publish", target_type="camp",
                target_id=camp_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (camps.STATUS_READY, camps.STATUS_DISABLED):
                camps.store().set_status(camp_id, camps.STATUS_READY, actor=_actor(session), force=True)
            return camps.store().set_status(camp_id, camps.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="camp.publish", func=_publish,
            target_type="camp", target_id=camp_id, target_name=_name(before.get("data"), camp_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(camp_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = camps.store().get(camp_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Лагерь не найден.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: camps.store().set_status(camp_id, target_status, actor=_actor(session)),
                target_type="camp", target_id=camp_id, target_name=_name(before.get("data"), camp_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{camp_id}/disable")
    def disable_camp(camp_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(camp_id, payload, request, perm=PERM_CAMP_DISABLE, action="camp.disable", target_status=camps.STATUS_DISABLED)

    @router.post("/{camp_id}/archive")
    def archive_camp(camp_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(camp_id, payload, request, perm=PERM_CAMP_ARCHIVE, action="camp.archive", target_status=camps.STATUS_ARCHIVE)

    @router.delete("/{camp_id}")
    def delete_camp(camp_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CAMP_DELETE)
        if payload.confirm != camp_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID лагеря в поле подтверждения.")
        before = camps.store().get(camp_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Лагерь не найден.")
        usage = camps.where_used(camp_id)
        if usage.get("total"):
            raise HTTPException(
                status_code=409,
                detail="Лагерь используется. Сначала удалите связи, показанные в «Где используется».",
            )
        run_admin_operation(
            session=session, action="camp.delete",
            func=lambda: camps.store().delete(camp_id),
            target_type="camp", target_id=camp_id, target_name=_name(before.get("data"), camp_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    attach_entity_versioning_routes(
        router,
        session_for=lambda req, tok: _session(get_storage(), req, tok),
        require=_require, actor=_actor, store=camps.store,
        target_type="camp",
        view_perm=PERM_CAMP_VIEW, edit_perm=PERM_CAMP_EDIT, publish_perm=PERM_CAMP_PUBLISH,
        not_found="Лагерь не найден.",
    )
    return router
