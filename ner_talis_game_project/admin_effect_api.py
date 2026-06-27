"""FastAPI router for Admin V2 Effect Constructor (authoring).

Mounted under ``/api/admin/v2/effects``. Reads need effect.view; the
draft→validate→publish→archive lifecycle + delete are gated per stage by
effect.* permissions and recorded via admin_operation. Engine consumption of
these definitions is a runtime step, deferred.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_EFFECT_ARCHIVE,
    PERM_EFFECT_CREATE,
    PERM_EFFECT_DELETE,
    PERM_EFFECT_DISABLE,
    PERM_EFFECT_EDIT,
    PERM_EFFECT_PUBLISH,
    PERM_EFFECT_VALIDATE,
    PERM_EFFECT_VIEW,
    identity_key,
    require_permission,
)
from services import effect_constructor_service as effects
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
    overwrite: bool = False
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


def create_admin_effect_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/effects", tags=["admin-effects"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_EFFECT_VIEW)
        return {
            "ok": True,
            "effectTypes": list(effects.EFFECT_TYPES),
            "categories": list(effects.EFFECT_CATEGORIES),
            "sourceTypes": list(effects.SOURCE_TYPES),
            "targets": list(effects.TARGETS),
            "targetTypes": list(effects.TARGET_TYPES),
            "activeWhen": list(effects.ACTIVE_WHEN),
            "triggerTypes": list(effects.TRIGGER_TYPES),
            "durationModes": list(effects.DURATION_MODES),
            "stackRules": list(effects.STACK_RULES),
            "visibilityModes": list(effects.VISIBILITY_MODES),
            "resources": list(effects.RESOURCES),
            "stats": list(effects.STATS),
            "controlKinds": list(effects.CONTROL_KINDS),
            "cleanseTags": list(effects.CLEANSE_TAGS),
            "zoneElements": list(effects.ZONE_ELEMENTS),
            "statuses": [{"value": s, "label": effects.STATUS_LABELS.get(s, s)} for s in effects.STATUSES],
        }

    @router.get("")
    def list_effects(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_EFFECT_VIEW)
        return {"ok": True, "items": effects.store().list(status=status)}

    @router.post("/import")
    def import_existing(payload: ImportRequest, request: Request) -> dict[str, Any]:
        # Импорт существующих эффектов/состояний/проклятий в конструктор (ТЗ §2).
        # Объявлено до /{effect_id}, публикует → гейт publish, аудит.
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_EFFECT_PUBLISH)
        from services import constructor_import

        return run_admin_operation(
            session=session, action="effect.import_existing",
            func=lambda: constructor_import.import_effects(overwrite=bool(payload.overwrite), actor=_actor(session)),
            target_type="constructor_import", target_id="effect",
            after_func=lambda r: {"created": r.get("created"), "skipped": r.get("skipped")},
            reason=payload.reason, details={"overwrite": bool(payload.overwrite)},
        )

    @router.get("/{effect_id}")
    def get_effect(effect_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_EFFECT_VIEW)
        item = effects.store().get(effect_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Эффект не найден.")
        return {"ok": True, "item": item, "validation": effects.validate(item)}

    @router.get("/{effect_id}/usage")
    def effect_usage(effect_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_EFFECT_VIEW)
        return {"ok": True, "usage": effects.where_used(effect_id)}

    @router.post("")
    def create_effect(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_EFFECT_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="effect.create",
                func=lambda: effects.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="effect", target_id=payload.id,
                target_name=str(payload.data.get("effect_name") or payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{effect_id}")
    def update_effect(effect_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_EFFECT_EDIT)
        before = effects.store().get(effect_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Эффект не найден.")
        try:
            item = run_admin_operation(
                session=session, action="effect.edit",
                func=lambda: effects.store().update(effect_id, payload.data, actor=_actor(session)),
                target_type="effect", target_id=effect_id,
                target_name=str(before.get("data", {}).get("effect_name") or effect_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{effect_id}/validate")
    def validate_effect(effect_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_EFFECT_VALIDATE)
        item = effects.store().get(effect_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Эффект не найден.")
        result = effects.validate(item)
        record_admin_operation(
            session=session, action="effect.validate", target_type="effect",
            target_id=effect_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{effect_id}/publish")
    def publish_effect(effect_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_EFFECT_PUBLISH)
        before = effects.store().get(effect_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Эффект не найден.")
        result = effects.validate(before)
        if not result["ok"]:
            try:
                effects.store().set_status(effect_id, effects.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="effect.publish", target_type="effect",
                target_id=effect_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (effects.STATUS_READY, effects.STATUS_DISABLED):
                effects.store().set_status(effect_id, effects.STATUS_READY, actor=_actor(session), force=True)
            return effects.store().set_status(effect_id, effects.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="effect.publish", func=_publish,
            target_type="effect", target_id=effect_id,
            target_name=str(before.get("data", {}).get("effect_name") or effect_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(effect_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = effects.store().get(effect_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Эффект не найден.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: effects.store().set_status(effect_id, target_status, actor=_actor(session)),
                target_type="effect", target_id=effect_id,
                target_name=str(before.get("data", {}).get("effect_name") or effect_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{effect_id}/disable")
    def disable_effect(effect_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(effect_id, payload, request, perm=PERM_EFFECT_DISABLE, action="effect.disable", target_status=effects.STATUS_DISABLED)

    @router.post("/{effect_id}/archive")
    def archive_effect(effect_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(effect_id, payload, request, perm=PERM_EFFECT_ARCHIVE, action="effect.archive", target_status=effects.STATUS_ARCHIVE)

    @router.delete("/{effect_id}")
    def delete_effect(effect_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_EFFECT_DELETE)
        if payload.confirm != effect_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный effect_id в поле подтверждения.")
        before = effects.store().get(effect_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Эффект не найден.")
        run_admin_operation(
            session=session, action="effect.delete",
            func=lambda: effects.store().delete(effect_id),
            target_type="effect", target_id=effect_id,
            target_name=str(before.get("data", {}).get("effect_name") or effect_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    attach_entity_versioning_routes(
        router,
        session_for=lambda req, tok: _session(get_storage(), req, tok),
        require=_require, actor=_actor, store=effects.store,
        target_type="effect", name_field="effect_name",
        view_perm=PERM_EFFECT_VIEW, edit_perm=PERM_EFFECT_EDIT, publish_perm=PERM_EFFECT_PUBLISH,
        not_found="Эффект не найден.",
    )
    return router
