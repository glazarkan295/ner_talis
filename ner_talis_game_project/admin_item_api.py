"""FastAPI router for Admin V2 Item Constructor (authoring).

Mounted under ``/api/admin/v2/items``. Reads need item.view; the
draft→validate→publish→archive lifecycle, versions, where-used and delete
(soft/hard) are gated per stage by item.* permissions and recorded via
admin_operation. Live game consumption of constructor items is a runtime step,
deferred.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    OWNER,
    PERM_ITEM_ARCHIVE,
    PERM_ITEM_CREATE,
    PERM_ITEM_DELETE_HARD,
    PERM_ITEM_DELETE_SOFT,
    PERM_ITEM_DISABLE,
    PERM_ITEM_EDIT,
    PERM_ITEM_EDIT_PUBLISHED,
    PERM_ITEM_PUBLISH,
    PERM_ITEM_RESTORE,
    PERM_ITEM_VALIDATE,
    PERM_ITEM_VIEW,
    PERM_ITEM_VIEW_USAGE,
    identity_key,
    require_permission,
    role_for_session,
)
from services import item_constructor_service as items


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


class HardDeleteRequest(BaseModel):
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


def create_admin_item_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/items", tags=["admin-items"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_ITEM_VIEW)
        return {
            "ok": True,
            "categories": list(items.ITEM_CATEGORIES),
            "types": list(items.ITEM_TYPES),
            "qualities": list(items.QUALITIES),
            "equipSlots": list(items.EQUIP_SLOTS),
            "tags": list(items.TAGS),
            "propertyTypes": list(items.PROPERTY_TYPES),
            "effectTypes": list(items.EFFECT_TYPES),
            "statuses": [{"value": s, "label": items.STATUS_LABELS.get(s, s)} for s in items.STATUSES],
        }

    @router.get("")
    def list_items(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_ITEM_VIEW)
        return {"ok": True, "items": items.store().list(status=status)}

    @router.get("/{item_id}")
    def get_item(item_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_ITEM_VIEW)
        item = items.store().get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        return {"ok": True, "item": item, "validation": items.validate(item)}

    @router.get("/{item_id}/usage")
    def item_usage(item_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_ITEM_VIEW_USAGE)
        if items.store().get(item_id) is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        return {"ok": True, "usage": items.where_used(item_id)}

    @router.get("/{item_id}/craft-usage")
    def item_craft_usage(item_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        """Блок «Используется в ремесле» (ТЗ 13 §6): по ролям + цепочка + ошибки."""
        _require(_session(get_storage(), request, token), PERM_ITEM_VIEW_USAGE)
        if items.store().get(item_id) is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        from services import recipe_constructor_service as recipes
        return {"ok": True, "craft": recipes.item_craft_usage(item_id)}

    @router.post("")
    def create_item(payload: IdDataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ITEM_CREATE)
        try:
            item = run_admin_operation(
                session=session, action="item.create",
                func=lambda: items.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type="item", target_id=payload.id,
                target_name=str(payload.data.get("name") or payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{item_id}")
    def update_item(item_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        before = items.store().get(item_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        published = before.get("status") == items.STATUS_PUBLISHED
        # Правка опубликованного предмета — отдельное право; изменения уходят в
        # черновик (новая версия), пока не опубликуют заново (ТЗ §3, §21).
        _require(session, PERM_ITEM_EDIT_PUBLISHED if published else PERM_ITEM_EDIT)
        try:
            def _do_update() -> dict[str, Any]:
                if published:
                    items.record_version(item_id, by=_actor(session), reason=payload.reason)
                item = items.store().update(item_id, payload.data, actor=_actor(session))
                if published:
                    item = items.store().set_status(item_id, items.STATUS_DRAFT, actor=_actor(session), force=True)
                return item

            item = run_admin_operation(
                session=session, action="item.edit",
                func=_do_update, target_type="item", target_id=item_id,
                target_name=str(before.get("data", {}).get("name") or item_id),
                before={"status": before.get("status"), "version": before.get("version")},
                after_func=lambda r: {"status": r.get("status"), "version": r.get("version")},
                reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{item_id}/validate")
    def validate_item(item_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ITEM_VALIDATE)
        item = items.store().get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        result = items.validate(item)
        record_admin_operation(
            session=session, action="item.validate", target_type="item",
            target_id=item_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{item_id}/publish")
    def publish_item(item_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ITEM_PUBLISH)
        before = items.store().get(item_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        result = items.validate(before)
        if not result["ok"]:
            try:
                items.store().set_status(item_id, items.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="item.publish", target_type="item",
                target_id=item_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            items.record_version(item_id, by=_actor(session), reason=payload.reason or "publish")
            return items.store().set_status(item_id, items.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="item.publish", func=_publish,
            target_type="item", target_id=item_id,
            target_name=str(before.get("data", {}).get("name") or item_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(item_id, payload, request, *, perm, action, target_status):
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = items.store().get(item_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: items.store().set_status(item_id, target_status, actor=_actor(session)),
                target_type="item", target_id=item_id,
                target_name=str(before.get("data", {}).get("name") or item_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{item_id}/disable")
    def disable_item(item_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(item_id, payload, request, perm=PERM_ITEM_DISABLE, action="item.disable", target_status=items.STATUS_DISABLED)

    @router.post("/{item_id}/archive")
    def archive_item(item_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(item_id, payload, request, perm=PERM_ITEM_ARCHIVE, action="item.archive", target_status=items.STATUS_ARCHIVE)

    @router.post("/{item_id}/delete-soft")
    def soft_delete_item(item_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(item_id, payload, request, perm=PERM_ITEM_DELETE_SOFT, action="item.delete_soft", target_status=items.STATUS_DELETED_SOFT)

    @router.post("/{item_id}/restore")
    def restore_item(item_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(item_id, payload, request, perm=PERM_ITEM_RESTORE, action="item.restore", target_status=items.STATUS_DRAFT)

    @router.delete("/{item_id}")
    def hard_delete_item(item_id: str, payload: HardDeleteRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_ITEM_DELETE_HARD)
        # Полное удаление — только owner (ТЗ §22, §30).
        if role_for_session(session) != OWNER:
            raise HTTPException(status_code=403, detail="Полное удаление доступно только владельцу (owner).")
        if payload.confirm != item_id:
            raise HTTPException(status_code=400, detail="Для полного удаления введите точный item_id в поле подтверждения.")
        before = items.store().get(item_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Предмет не найден.")
        usage = items.where_used(item_id)
        if usage.get("total"):
            raise HTTPException(status_code=409, detail="Предмет используется в системах — сначала уберите ссылки или используйте мягкое удаление.")
        run_admin_operation(
            session=session, action="item.delete_hard",
            func=lambda: items.store().delete(item_id),
            target_type="item", target_id=item_id,
            target_name=str(before.get("data", {}).get("name") or item_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    return router
