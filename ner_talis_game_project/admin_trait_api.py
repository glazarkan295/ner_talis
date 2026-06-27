"""FastAPI router for Admin V2 Trait constructor (ТЗ «черты/благословения/фазы»).

Mounted under ``/api/admin/v2/traits``. Reads need trait.view; lifecycle gated by
trait.* permissions and audited. POST /import seeds the universal trait library.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_TRAIT_ARCHIVE,
    PERM_TRAIT_CREATE,
    PERM_TRAIT_DELETE,
    PERM_TRAIT_DISABLE,
    PERM_TRAIT_EDIT,
    PERM_TRAIT_PUBLISH,
    PERM_TRAIT_VALIDATE,
    PERM_TRAIT_VIEW,
    identity_key,
    require_permission,
)
from services import trait_constructor_service as traits
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
    return str((data or {}).get("trait_name") or fallback)


def create_admin_trait_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/traits", tags=["admin-traits"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_TRAIT_VIEW)
        return {
            "ok": True,
            "traitRanks": [{"value": r, "label": traits.TRAIT_RANK_LABELS.get(r, r)} for r in traits.TRAIT_RANKS],
            "triggers": [{"value": t, "label": traits.TRIGGER_LABELS.get(t, t)} for t in traits.TRIGGERS],
            "stackRules": list(traits.STACK_RULES),
            "mobCategories": list(traits.MOB_CATEGORIES),
            "statuses": [{"value": s, "label": traits.STATUS_LABELS.get(s, s)} for s in traits.STATUSES],
        }

    @router.get("")
    def list_traits(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_TRAIT_VIEW)
        return {"ok": True, "items": traits.store().list(status=status)}

    @router.get("/{trait_id}")
    def get_trait(trait_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_TRAIT_VIEW)
        item = traits.store().get(trait_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Черта не найдена.")
        return {"ok": True, "item": item, "validation": traits.validate(item)}

    @router.post("")
    def create_trait(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_TRAIT_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="trait.create",
                func=lambda: traits.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="trait", target_id=payload.id, target_name=_name(payload.data, payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{trait_id}")
    def update_trait(trait_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_TRAIT_EDIT)
        before = traits.store().get(trait_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Черта не найдена.")
        # 18-CODEX §2: правка опубликованной черты меняет live → нужно publish-право.
        if before.get("status") == traits.STATUS_PUBLISHED:
            _require(session, PERM_TRAIT_PUBLISH)
        try:
            item = run_admin_operation(
                session=session, action="trait.edit",
                func=lambda: traits.store().update(trait_id, payload.data, actor=_actor(session)),
                target_type="trait", target_id=trait_id, target_name=_name(before.get("data"), trait_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/import")
    def import_existing(payload: ImportRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_TRAIT_PUBLISH)
        from services import constructor_import
        report = run_admin_operation(
            session=session, action="trait.import_existing",
            func=lambda: constructor_import.import_traits(mode=payload.mode, actor=_actor(session)),
            target_type="constructor_import", target_id="trait",
            after_func=lambda r: {"created": r.get("created"), "skipped": r.get("skipped")}, reason=payload.reason,
        )
        return {"ok": True, "report": report}

    @router.post("/{trait_id}/validate")
    def validate_trait(trait_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_TRAIT_VALIDATE)
        item = traits.store().get(trait_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Черта не найдена.")
        result = traits.validate(item)
        record_admin_operation(
            session=session, action="trait.validate", target_type="trait",
            target_id=trait_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{trait_id}/publish")
    def publish_trait(trait_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_TRAIT_PUBLISH)
        before = traits.store().get(trait_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Черта не найдена.")
        result = traits.validate(before)
        if not result["ok"]:
            try:
                traits.store().set_status(trait_id, traits.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="trait.publish", target_type="trait",
                target_id=trait_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (traits.STATUS_READY, traits.STATUS_DISABLED):
                traits.store().set_status(trait_id, traits.STATUS_READY, actor=_actor(session), force=True)
            return traits.store().set_status(trait_id, traits.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="trait.publish", func=_publish,
            target_type="trait", target_id=trait_id, target_name=_name(before.get("data"), trait_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(trait_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = traits.store().get(trait_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Черта не найдена.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: traits.store().set_status(trait_id, target_status, actor=_actor(session)),
                target_type="trait", target_id=trait_id, target_name=_name(before.get("data"), trait_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{trait_id}/disable")
    def disable_trait(trait_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(trait_id, payload, request, perm=PERM_TRAIT_DISABLE, action="trait.disable", target_status=traits.STATUS_DISABLED)

    @router.post("/{trait_id}/archive")
    def archive_trait(trait_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(trait_id, payload, request, perm=PERM_TRAIT_ARCHIVE, action="trait.archive", target_status=traits.STATUS_ARCHIVE)

    @router.delete("/{trait_id}")
    def delete_trait(trait_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_TRAIT_DELETE)
        if payload.confirm != trait_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID черты в поле подтверждения.")
        before = traits.store().get(trait_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Черта не найдена.")
        run_admin_operation(
            session=session, action="trait.delete",
            func=lambda: traits.store().delete(trait_id),
            target_type="trait", target_id=trait_id, target_name=_name(before.get("data"), trait_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    attach_entity_versioning_routes(
        router,
        session_for=lambda req, tok: _session(get_storage(), req, tok),
        require=_require, actor=_actor, store=traits.store,
        target_type="trait", name_field="trait_name",
        view_perm=PERM_TRAIT_VIEW, edit_perm=PERM_TRAIT_EDIT, publish_perm=PERM_TRAIT_PUBLISH,
        not_found="Черта не найдена.",
    )
    return router
