"""FastAPI router for Admin V2 Recipe (crafting) constructor (ТЗ «импорт ремесла»).

Mounted under ``/api/admin/v2/recipes``. Reads need recipe.view; the
draft→validate→publish→archive lifecycle + delete are gated per stage by recipe.*
permissions and recorded via admin_operation. Runtime crafting stays in
services/crafting_service.py. POST /import surfaces existing recipes
(data/crafting_recipes.json) as published constructor records.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_RECIPE_ARCHIVE,
    PERM_RECIPE_CREATE,
    PERM_RECIPE_DELETE,
    PERM_RECIPE_DISABLE,
    PERM_RECIPE_EDIT,
    PERM_RECIPE_PUBLISH,
    PERM_RECIPE_VALIDATE,
    PERM_RECIPE_VIEW,
    identity_key,
    require_permission,
)
from services import recipe_constructor_service as recipes
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


def create_admin_recipes_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/recipes", tags=["admin-recipes"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_RECIPE_VIEW)
        return {
            "ok": True,
            "workshops": list(recipes.WORKSHOPS),
            "workshopLabels": recipes.WORKSHOP_LABELS,
            "recipeTypes": [{"value": t, "label": recipes.RECIPE_TYPE_LABELS.get(t, t)} for t in recipes.RECIPE_TYPES],
            "materialRoles": [{"value": r, "label": recipes.MATERIAL_ROLE_LABELS.get(r, r)} for r in recipes.MATERIAL_ROLES],
            "statuses": [{"value": s, "label": recipes.STATUS_LABELS.get(s, s)} for s in recipes.STATUSES],
        }

    @router.get("")
    def list_recipes(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_RECIPE_VIEW)
        return {"ok": True, "items": recipes.store().list(status=status)}

    @router.get("/{recipe_id}")
    def get_recipe(recipe_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_RECIPE_VIEW)
        item = recipes.store().get(recipe_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Рецепт не найден.")
        return {"ok": True, "item": item, "validation": recipes.validate(item)}

    @router.post("")
    def create_recipe(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_RECIPE_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="recipe.create",
                func=lambda: recipes.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="recipe", target_id=payload.id, target_name=_name(payload.data, payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{recipe_id}")
    def update_recipe(recipe_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_RECIPE_EDIT)
        before = recipes.store().get(recipe_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Рецепт не найден.")
        try:
            item = run_admin_operation(
                session=session, action="recipe.edit",
                func=lambda: recipes.store().update(recipe_id, payload.data, actor=_actor(session)),
                target_type="recipe", target_id=recipe_id, target_name=_name(before.get("data"), recipe_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/import")
    def import_existing(payload: ImportRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_RECIPE_PUBLISH)
        from services import constructor_import
        report = run_admin_operation(
            session=session, action="recipe.import_existing",
            func=lambda: constructor_import.import_recipes(mode=payload.mode, actor=_actor(session)),
            target_type="constructor_import", target_id="recipe",
            after_func=lambda r: {"created": r.get("created"), "skipped": r.get("skipped")}, reason=payload.reason,
        )
        return {"ok": True, "report": report}

    @router.get("/{recipe_id}/usage")
    def usage(recipe_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        # «Где используется» предмет-результат рецепта (как ингредиент/результат).
        _require(_session(get_storage(), request, token), PERM_RECIPE_VIEW)
        item = recipes.store().get(recipe_id)
        out_id = str((item.get("data") if item else {} or {}).get("output_item_id") or "") if item else ""
        return {"ok": True, "usedBy": recipes.where_used(out_id) if out_id else []}

    @router.post("/{recipe_id}/validate")
    def validate_recipe(recipe_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_RECIPE_VALIDATE)
        item = recipes.store().get(recipe_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Рецепт не найден.")
        result = recipes.validate(item)
        record_admin_operation(
            session=session, action="recipe.validate", target_type="recipe",
            target_id=recipe_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{recipe_id}/publish")
    def publish_recipe(recipe_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_RECIPE_PUBLISH)
        before = recipes.store().get(recipe_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Рецепт не найден.")
        result = recipes.validate(before)
        if not result["ok"]:
            try:
                recipes.store().set_status(recipe_id, recipes.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="recipe.publish", target_type="recipe",
                target_id=recipe_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (recipes.STATUS_READY, recipes.STATUS_DISABLED):
                recipes.store().set_status(recipe_id, recipes.STATUS_READY, actor=_actor(session), force=True)
            return recipes.store().set_status(recipe_id, recipes.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="recipe.publish", func=_publish,
            target_type="recipe", target_id=recipe_id, target_name=_name(before.get("data"), recipe_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(recipe_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = recipes.store().get(recipe_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Рецепт не найден.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: recipes.store().set_status(recipe_id, target_status, actor=_actor(session)),
                target_type="recipe", target_id=recipe_id, target_name=_name(before.get("data"), recipe_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{recipe_id}/disable")
    def disable_recipe(recipe_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(recipe_id, payload, request, perm=PERM_RECIPE_DISABLE, action="recipe.disable", target_status=recipes.STATUS_DISABLED)

    @router.post("/{recipe_id}/archive")
    def archive_recipe(recipe_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(recipe_id, payload, request, perm=PERM_RECIPE_ARCHIVE, action="recipe.archive", target_status=recipes.STATUS_ARCHIVE)

    @router.delete("/{recipe_id}")
    def delete_recipe(recipe_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_RECIPE_DELETE)
        if payload.confirm != recipe_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID рецепта в поле подтверждения.")
        before = recipes.store().get(recipe_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Рецепт не найден.")
        run_admin_operation(
            session=session, action="recipe.delete",
            func=lambda: recipes.store().delete(recipe_id),
            target_type="recipe", target_id=recipe_id, target_name=_name(before.get("data"), recipe_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    attach_entity_versioning_routes(
        router,
        session_for=lambda req, tok: _session(get_storage(), req, tok),
        require=_require, actor=_actor, store=recipes.store,
        target_type="recipe",
        view_perm=PERM_RECIPE_VIEW, edit_perm=PERM_RECIPE_EDIT, publish_perm=PERM_RECIPE_PUBLISH,
        not_found="Рецепт не найден.",
    )
    return router
