"""Фабрика роутера конструктора на EntityStore (единый стандарт, ТЗ 11 §унификация).

Все простые EntityStore-конструкторы повторяют один роутер
(meta/list/get/create/update/validate/publish/lifecycle/delete + версионирование +
импорт). Эта фабрика собирает его из сервиса конструктора одной функцией, чтобы
не дублировать ~270 строк на каждый новый конструктор.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import identity_key, require_permission
from services.admin_versioning_routes import attach_entity_versioning_routes


class _IdData(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    id: str = Field(min_length=2)
    data: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class _Data(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    data: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class _Action(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    reason: str = ""


class _Delete(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    confirm: str = ""
    reason: str = ""


class _Import(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    mode: str = "new"
    reason: str = ""


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_entity_constructor_router(
    *,
    get_storage: Callable[[], Any],
    prefix: str,
    tags: list[str],
    svc: Any,                 # модуль сервиса: store()/validate()/STATUS_*/STATUSES/STATUS_LABELS
    perms: dict[str, str],    # ключи: view/create/edit/validate/publish/disable/archive/delete
    target_type: str,
    name_field: str,
    not_found: str,
    meta_extra: Callable[[Any], dict[str, Any]] | None = None,
    import_fn_name: str | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags)

    def _session(request: Request | None, token: str | None) -> dict[str, Any]:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            return require_admin_session(get_storage(), effective)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    def _require(session: dict[str, Any], perm: str) -> str:
        try:
            return require_permission(session, perm)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    def _actor(session: dict[str, Any]) -> str:
        return identity_key(session.get("platform"), session.get("admin_user_id"))

    def _name(data: Any, fallback: str) -> str:
        return str((data or {}).get(name_field) or fallback)

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(request, token), perms["view"])
        out: dict[str, Any] = {
            "ok": True,
            "statuses": [{"value": s, "label": svc.STATUS_LABELS.get(s, s)} for s in svc.STATUSES],
        }
        if meta_extra:
            out.update(meta_extra(svc))
        return out

    @router.get("")
    def list_items(request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(request, token), perms["view"])
        return {"ok": True, "items": svc.store().list(status=status)}

    @router.get("/{item_id}")
    def get_item(item_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(request, token), perms["view"])
        item = svc.store().get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=not_found)
        return {"ok": True, "item": item, "validation": svc.validate(item)}

    @router.post("")
    def create_item(payload: _IdData, request: Request) -> dict[str, Any]:
        session = _session(request, payload.token)
        _require(session, perms["create"])
        try:
            item = run_admin_operation(
                session=session, action=f"{target_type}.create",
                func=lambda: svc.store().create(payload.id, payload.data, actor=_actor(session)),
                target_type=target_type, target_id=payload.id, target_name=_name(payload.data, payload.id),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{item_id}")
    def update_item(item_id: str, payload: _Data, request: Request) -> dict[str, Any]:
        session = _session(request, payload.token)
        _require(session, perms["edit"])
        before = svc.store().get(item_id)
        if before is None:
            raise HTTPException(status_code=404, detail=not_found)
        # 15-CODEX §3: правка ОПУБЛИКОВАННОГО объекта меняет live-версию (update
        # сохраняет статус), поэтому требует publish-права. У EntityStore нет
        # draft-overlay, поэтому используем строгую проверку (Вариант A): сначала
        # сними с публикации/получи publish-право.
        published = getattr(svc, "STATUS_PUBLISHED", "published")
        if before.get("status") == published:
            _require(session, perms["publish"])
        try:
            item = run_admin_operation(
                session=session, action=f"{target_type}.edit",
                func=lambda: svc.store().update(item_id, payload.data, actor=_actor(session)),
                target_type=target_type, target_id=item_id, target_name=_name(before.get("data"), item_id),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    if import_fn_name:
        @router.post("/import")
        def import_existing(payload: _Import, request: Request) -> dict[str, Any]:
            session = _session(request, payload.token)
            _require(session, perms["publish"])
            from services import constructor_import
            fn = getattr(constructor_import, import_fn_name)
            report = run_admin_operation(
                session=session, action=f"{target_type}.import_existing",
                func=lambda: fn(mode=payload.mode, actor=_actor(session)),
                target_type="constructor_import", target_id=target_type,
                after_func=lambda r: {"created": r.get("created"), "skipped": r.get("skipped")}, reason=payload.reason,
            )
            return {"ok": True, "report": report}

    @router.post("/{item_id}/validate")
    def validate_item(item_id: str, payload: _Action, request: Request) -> dict[str, Any]:
        session = _session(request, payload.token)
        _require(session, perms["validate"])
        item = svc.store().get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=not_found)
        result = svc.validate(item)
        record_admin_operation(
            session=session, action=f"{target_type}.validate", target_type=target_type,
            target_id=item_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{item_id}/publish")
    def publish_item(item_id: str, payload: _Action, request: Request) -> dict[str, Any]:
        session = _session(request, payload.token)
        _require(session, perms["publish"])
        before = svc.store().get(item_id)
        if before is None:
            raise HTTPException(status_code=404, detail=not_found)
        result = svc.validate(before)
        if not result["ok"]:
            try:
                svc.store().set_status(item_id, svc.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action=f"{target_type}.publish", target_type=target_type,
                target_id=item_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (svc.STATUS_READY, svc.STATUS_DISABLED):
                svc.store().set_status(item_id, svc.STATUS_READY, actor=_actor(session), force=True)
            return svc.store().set_status(item_id, svc.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action=f"{target_type}.publish", func=_publish,
            target_type=target_type, target_id=item_id, target_name=_name(before.get("data"), item_id),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            details={"warnings": result["warnings"]},
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(item_id, payload, request, *, perm, action, target_status):
        session = _session(request, payload.token)
        _require(session, perm)
        before = svc.store().get(item_id)
        if before is None:
            raise HTTPException(status_code=404, detail=not_found)
        try:
            item = run_admin_operation(
                session=session, action=action,
                func=lambda: svc.store().set_status(item_id, target_status, actor=_actor(session)),
                target_type=target_type, target_id=item_id, target_name=_name(before.get("data"), item_id),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{item_id}/disable")
    def disable_item(item_id: str, payload: _Action, request: Request) -> dict[str, Any]:
        return _lifecycle(item_id, payload, request, perm=perms["disable"], action=f"{target_type}.disable", target_status=svc.STATUS_DISABLED)

    @router.post("/{item_id}/archive")
    def archive_item(item_id: str, payload: _Action, request: Request) -> dict[str, Any]:
        return _lifecycle(item_id, payload, request, perm=perms["archive"], action=f"{target_type}.archive", target_status=svc.STATUS_ARCHIVE)

    @router.delete("/{item_id}")
    def delete_item(item_id: str, payload: _Delete, request: Request) -> dict[str, Any]:
        session = _session(request, payload.token)
        _require(session, perms["delete"])
        if payload.confirm != item_id:
            raise HTTPException(status_code=400, detail="Для удаления введите точный ID в поле подтверждения.")
        before = svc.store().get(item_id)
        if before is None:
            raise HTTPException(status_code=404, detail=not_found)
        run_admin_operation(
            session=session, action=f"{target_type}.delete",
            func=lambda: svc.store().delete(item_id),
            target_type=target_type, target_id=item_id, target_name=_name(before.get("data"), item_id),
            before={"status": before.get("status")}, after_func=lambda r: {"deleted": bool(r)},
            reason=payload.reason,
        )
        return {"ok": True, "deleted": True}

    attach_entity_versioning_routes(
        router,
        session_for=lambda req, tok: _session(req, tok),
        require=_require, actor=_actor, store=svc.store,
        target_type=target_type, name_field=name_field,
        view_perm=perms["view"], edit_perm=perms["edit"], publish_perm=perms["publish"],
        not_found=not_found,
    )
    return router
