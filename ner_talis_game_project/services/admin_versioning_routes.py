"""Переиспользуемые admin-маршруты версионирования для EntityStore-конструкторов
(Этап 1: история/откат).

Все конструкторы на EntityStore (предметы/эффекты/навыки/штрафы/рецепты/
достижения) повторяют один паттерн роутера (_session/_require/_actor + X.store()),
поэтому маршруты history/rollback выносятся сюда и подключаются одной строкой —
без дублирования в каждом роутере.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import run_admin_operation


class _RollbackBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    version: int
    reason: str = ""


def _entity_name(data: Any, entity_id: str, name_field: str) -> str:
    d = data if isinstance(data, dict) else {}
    for key in (name_field, "name", "title", "effect_name", "label"):
        if key and d.get(key):
            return str(d.get(key))
    return entity_id


def attach_entity_versioning_routes(
    router: APIRouter,
    *,
    session_for: Callable[[Request, str | None], dict[str, Any]],
    require: Callable[[dict[str, Any], str], Any],
    actor: Callable[[dict[str, Any]], str],
    store: Callable[[], Any],
    target_type: str,
    view_perm: str,
    edit_perm: str,
    publish_perm: str,
    name_field: str = "",
    published_status: str = "published",
    not_found: str = "Объект не найден.",
) -> None:
    """Зарегистрировать GET …/{id}/history и POST …/{id}/rollback на роутере."""

    @router.get("/{entity_id}/history")
    def _history(entity_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        require(session_for(request, token), view_perm)
        if store().get(entity_id) is None:
            raise HTTPException(status_code=404, detail=not_found)
        return {"ok": True, "history": store().history(entity_id)}

    @router.post("/{entity_id}/rollback")
    def _rollback(entity_id: str, payload: _RollbackBody, request: Request) -> dict[str, Any]:
        session = session_for(request, payload.token)
        require(session, edit_perm)
        before = store().get(entity_id)
        if before is None:
            raise HTTPException(status_code=404, detail=not_found)
        # Откат ОПУБЛИКОВАННОГО объекта меняет live-данные (рантайм читает
        # published) → требует прав публикации, как и правка published.
        if str(before.get("status") or "") == published_status:
            require(session, publish_perm)
        name = _entity_name(before.get("data"), entity_id, name_field)
        try:
            item = run_admin_operation(
                session=session,
                action=f"{target_type}.rollback",
                func=lambda: store().rollback(entity_id, payload.version, actor=actor(session)),
                target_type=target_type,
                target_id=entity_id,
                target_name=name,
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")},
                reason=payload.reason,
                details={"rollback_to": payload.version},
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}


def attach_kinded_versioning_routes(
    router: APIRouter,
    *,
    session_for: Callable[[Request, str | None], dict[str, Any]],
    require: Callable[[dict[str, Any], str], Any],
    actor: Callable[[dict[str, Any]], str],
    store: Callable[[], Any],
    get_checked: Callable[[str, str], dict[str, Any]],
    view_perm_for: Callable[[str], str],
    edit_perm_for: Callable[[str], str],
    publish_perm_for: Callable[[str], str],
    target_type_for: Callable[[str], str] | None = None,
    name_field: str = "",
    published_status: str = "published",
) -> None:
    """Версионирование для multi-kind конструкторов (пути /{kind}/{id}/…).

    get_checked(id, kind) должен вернуть конверт или бросить HTTPException(404),
    проверив, что stored data._kind == kind (защита от кросс-kind доступа).
    Права берутся per-kind через *_perm_for(kind)."""

    def _ttype(kind: str) -> str:
        return target_type_for(kind) if target_type_for else str(kind)

    @router.get("/{kind}/{entity_id}/history")
    def _history(kind: str, entity_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        require(session_for(request, token), view_perm_for(kind))
        get_checked(entity_id, kind)
        return {"ok": True, "history": store().history(entity_id)}

    @router.post("/{kind}/{entity_id}/rollback")
    def _rollback(kind: str, entity_id: str, payload: _RollbackBody, request: Request) -> dict[str, Any]:
        session = session_for(request, payload.token)
        require(session, edit_perm_for(kind))
        before = get_checked(entity_id, kind)
        if str(before.get("status") or "") == published_status:
            require(session, publish_perm_for(kind))
        name = _entity_name(before.get("data"), entity_id, name_field)
        try:
            item = run_admin_operation(
                session=session,
                action=f"{_ttype(kind)}.rollback",
                func=lambda: store().rollback(entity_id, payload.version, actor=actor(session)),
                target_type=_ttype(kind),
                target_id=entity_id,
                target_name=name,
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")},
                reason=payload.reason,
                details={"kind": kind, "rollback_to": payload.version},
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}
