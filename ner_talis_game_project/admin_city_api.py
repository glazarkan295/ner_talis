"""FastAPI router for Admin V2 City/Fortress constructor (ТЗ §4–§6).

Mounted under ``/api/admin/v2/city``. Generic over kind (city_node / city_button /
city_shop_item / city_service / criminal_zone). Reads need city.view; create →
city.create; edit/validate → city.edit; publish/disable/archive/delete → their
own city.* permissions (all dangerous, audited). GET /tree returns the node tree
for the structure visualization (§5).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_CITY_ARCHIVE,
    PERM_CITY_CREATE,
    PERM_CITY_DELETE,
    PERM_CITY_DISABLE,
    PERM_CITY_EDIT,
    PERM_CITY_PUBLISH,
    PERM_CITY_VIEW,
    identity_key,
    require_permission,
)
from services import city_constructor_service as city
from services import message_output_service as message_output


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
    if kind not in city.KINDS:
        raise HTTPException(status_code=404, detail=f"Неизвестный тип объекта: {kind}.")


def _title(data: dict[str, Any], kind: str) -> str:
    if kind == city.KIND_BUTTON:
        return str(data.get("label") or "")
    if kind == city.KIND_SHOP_ITEM:
        return str(data.get("item_id") or "")
    return str(data.get("name") or "")


def create_admin_city_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/city", tags=["admin-city"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_CITY_VIEW)
        return {
            "ok": True,
            "kinds": list(city.KINDS),
            "nodeTypes": list(city.NODE_TYPES),
            "buttonActions": list(city.BUTTON_ACTIONS),
            "shopKinds": list(city.SHOP_KINDS),
            "serviceKinds": list(city.SERVICE_KINDS),
            "currencies": list(city.CURRENCIES),
            "stockTypes": list(city.STOCK_TYPES),
            "statuses": [{"value": s, "label": city.STATUS_LABELS.get(s, s)} for s in city.STATUSES],
            "messageOutput": message_output.meta(),
        }

    @router.get("/tree")
    def tree(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_CITY_VIEW)
        return {"ok": True, "tree": city.build_tree()}

    @router.get("/node/{node_id}/runtime")
    def node_runtime(node_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        # Предпросмотр «живого» вида узла (как его увидит навигация бота при
        # включённом CITY_CONSTRUCTOR_LIVE). Только чтение опубликованного.
        from services import city_runtime
        _require(_session(get_storage(), request, token), PERM_CITY_VIEW)
        view = city_runtime.node_runtime_view(node_id)
        if view is None:
            raise HTTPException(status_code=404, detail="Опубликованный узел не найден.")
        return {"ok": True, "view": view, "liveEnabled": city_runtime.live_enabled()}

    @router.get("/{kind}")
    def list_kind(kind: str, request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _check_kind(kind)
        _require(_session(get_storage(), request, token), PERM_CITY_VIEW)
        items = [i for i in city.store().list(status=status) if (i.get("data") or {}).get("_kind") == kind]
        return {"ok": True, "items": items}

    @router.get("/{kind}/{object_id}")
    def get_one(kind: str, object_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _check_kind(kind)
        _require(_session(get_storage(), request, token), PERM_CITY_VIEW)
        item = city.store().get(object_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        return {"ok": True, "item": item, "validation": city.validate(kind, item)}

    @router.get("/{kind}/{object_id}/where-used")
    def where_used(kind: str, object_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _check_kind(kind)
        _require(_session(get_storage(), request, token), PERM_CITY_VIEW)
        return {"ok": True, "usedBy": city.where_used(object_id)}

    @router.post("/{kind}")
    def create(kind: str, payload: IdDataRequest, request: Request) -> dict[str, Any]:
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CITY_CREATE)
        data = {**payload.data, "_kind": kind}
        try:
            item = run_admin_operation(
                session=session, action="city.create",
                func=lambda: city.store().create(payload.id, data, actor=_actor(session)),
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
        _require(session, PERM_CITY_EDIT)
        before = city.store().get(object_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        # 19-CODEX §1: правка ОПУБЛИКОВАННОГО city-объекта меняет live (update
        # сохраняет статус) → требует city.publish (draft-overlay пока нет).
        if before.get("status") == city.STATUS_PUBLISHED:
            _require(session, PERM_CITY_PUBLISH)
        try:
            item = run_admin_operation(
                session=session, action="city.edit",
                func=lambda: city.store().update(object_id, {**payload.data, "_kind": kind}, actor=_actor(session)),
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
        _require(session, PERM_CITY_EDIT)
        item = city.store().get(object_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        result = city.validate(kind, item)
        record_admin_operation(
            session=session, action="city.validate", target_type=kind,
            target_id=object_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{kind}/{object_id}/publish")
    def publish(kind: str, object_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CITY_PUBLISH)
        before = city.store().get(object_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        result = city.validate(kind, before)
        if not result["ok"]:
            try:
                city.store().set_status(object_id, city.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action="city.publish", target_type=kind,
                target_id=object_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (city.STATUS_READY, city.STATUS_DISABLED):
                city.store().set_status(object_id, city.STATUS_READY, actor=_actor(session), force=True)
            return city.store().set_status(object_id, city.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action="city.publish", func=_publish,
            target_type=kind, target_id=object_id, target_name=_title(before.get("data", {}), kind),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(kind, object_id, payload, request, *, perm, action, target_status):
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, perm)
        before = city.store().get(object_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: city.store().set_status(object_id, target_status, actor=_actor(session)),
                target_type=kind, target_id=object_id, target_name=_title(before.get("data", {}), kind),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{kind}/{object_id}/disable")
    def disable(kind: str, object_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(kind, object_id, payload, request, perm=PERM_CITY_DISABLE, action="city.disable", target_status=city.STATUS_DISABLED)

    @router.post("/{kind}/{object_id}/archive")
    def archive(kind: str, object_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(kind, object_id, payload, request, perm=PERM_CITY_ARCHIVE, action="city.archive", target_status=city.STATUS_ARCHIVE)

    @router.delete("/{kind}/{object_id}")
    def delete(kind: str, object_id: str, payload: DeleteRequest, request: Request) -> dict[str, Any]:
        _check_kind(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_CITY_DELETE)
        if payload.confirm != object_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID объекта в поле подтверждения.")
        before = city.store().get(object_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Объект не найден.")
        run_admin_operation(
            session=session, action="city.delete",
            func=lambda: city.store().delete(object_id),
            target_type=kind, target_id=object_id, target_name=_title(before.get("data", {}), kind),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    return router
