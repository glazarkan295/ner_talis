"""FastAPI router for Admin V2 Skill Constructor (authoring skill definitions).

Mounted under ``/api/admin/v2/skills``. Reads need skill_def.view; the
draft→validate→publish→archive lifecycle + delete are gated per stage by
skill_def.* permissions and recorded via admin_operation. The per-player skill
runtime (Order Stone choices, resource spend, cooldowns) lives in
services/active_skill_service.py, not here. POST /import surfaces the existing
catalog (data/active_skills_registry.json) as published constructor records.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_SKILL_DEF_ARCHIVE,
    PERM_SKILL_DEF_CREATE,
    PERM_SKILL_DEF_DELETE,
    PERM_SKILL_DEF_DISABLE,
    PERM_SKILL_DEF_EDIT,
    PERM_SKILL_DEF_PUBLISH,
    PERM_SKILL_DEF_VALIDATE,
    PERM_SKILL_DEF_VIEW,
    identity_key,
    require_permission,
)
from services import skill_constructor_service as skills


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


def _name(data: dict[str, Any], fallback: str) -> str:
    return str((data or {}).get("name") or fallback)


def create_admin_skills_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/skills", tags=["admin-skills"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_SKILL_DEF_VIEW)
        return {
            "ok": True,
            "skillTypes": list(skills.SKILL_TYPES),
            "branches": list(skills.BRANCHES),
            "paths": list(skills.PATHS),
            "pathsByBranch": {k: list(v) for k, v in skills.PATHS_BY_BRANCH.items()},
            "resourceTypes": list(skills.RESOURCE_TYPES),
            "damageTypes": list(skills.DAMAGE_TYPES),
            "targetModes": list(skills.TARGET_MODES),
            "weaponRequirements": list(skills.WEAPON_REQUIREMENTS),
            "statuses": [{"value": s, "label": skills.STATUS_LABELS.get(s, s)} for s in skills.STATUSES],
        }

    @router.get("")
    def list_skills(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_SKILL_DEF_VIEW)
        return {"ok": True, "items": skills.store().list(status=status)}

    @router.get("/{skill_id}")
    def get_skill(skill_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_SKILL_DEF_VIEW)
        item = skills.store().get(skill_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Навык не найден.")
        return {"ok": True, "item": item, "validation": skills.validate(item)}

    @router.post("")
    def create_skill(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_SKILL_DEF_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="skill_def.create",
                func=lambda: skills.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="skill_def", target_id=payload.id, target_name=_name(payload.data, payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{skill_id}")
    def update_skill(skill_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_SKILL_DEF_EDIT)
        before = skills.store().get(skill_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Навык не найден.")
        try:
            item = run_admin_operation(
                session=session, action="skill_def.edit",
                func=lambda: skills.store().update(skill_id, payload.data, actor=_actor(session)),
                target_type="skill_def", target_id=skill_id, target_name=_name(before.get("data"), skill_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/import")
    def import_existing(payload: ImportRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_SKILL_DEF_PUBLISH)
        from services import constructor_import
        report = run_admin_operation(
            session=session, action="skill_def.import_existing",
            func=lambda: constructor_import.import_skills(overwrite=bool(payload.overwrite), actor=_actor(session)),
            target_type="constructor_import", target_id="skill",
            after_func=lambda r: dict(r), reason=payload.reason,
        )
        return {"ok": True, "report": report}

    @router.post("/{skill_id}/validate")
    def validate_skill(skill_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_SKILL_DEF_VALIDATE)
        item = skills.store().get(skill_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Навык не найден.")
        result = skills.validate(item)
        record_admin_operation(
            session=session, action="skill_def.validate", target_type="skill_def",
            target_id=skill_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{skill_id}/publish")
    def publish_skill(skill_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_SKILL_DEF_PUBLISH)
        before = skills.store().get(skill_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Навык не найден.")
        result = skills.validate(before)
        if not result["ok"]:
            try:
                skills.store().set_status(skill_id, skills.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="skill_def.publish", target_type="skill_def",
                target_id=skill_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (skills.STATUS_READY, skills.STATUS_DISABLED):
                skills.store().set_status(skill_id, skills.STATUS_READY, actor=_actor(session), force=True)
            return skills.store().set_status(skill_id, skills.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="skill_def.publish", func=_publish,
            target_type="skill_def", target_id=skill_id, target_name=_name(before.get("data"), skill_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(skill_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = skills.store().get(skill_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Навык не найден.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: skills.store().set_status(skill_id, target_status, actor=_actor(session)),
                target_type="skill_def", target_id=skill_id, target_name=_name(before.get("data"), skill_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{skill_id}/disable")
    def disable_skill(skill_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(skill_id, payload, request, perm=PERM_SKILL_DEF_DISABLE, action="skill_def.disable", target_status=skills.STATUS_DISABLED)

    @router.post("/{skill_id}/archive")
    def archive_skill(skill_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(skill_id, payload, request, perm=PERM_SKILL_DEF_ARCHIVE, action="skill_def.archive", target_status=skills.STATUS_ARCHIVE)

    @router.delete("/{skill_id}")
    def delete_skill(skill_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_SKILL_DEF_DELETE)
        if payload.confirm != skill_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID навыка в поле подтверждения.")
        before = skills.store().get(skill_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Навык не найден.")
        run_admin_operation(
            session=session, action="skill_def.delete",
            func=lambda: skills.store().delete(skill_id),
            target_type="skill_def", target_id=skill_id, target_name=_name(before.get("data"), skill_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    return router
