"""FastAPI router for Admin V2 Site Constructor — publishable content.

Mounted under ``/api/admin/v2/site``. Generic over content kind (news/guide/
faq/banner/announcement); each kind maps to its own permission family
(news.* / guides.* / faq.* / site.* for banners). Lifecycle draft→validate→
publish→hide→archive is gated per stage and recorded via admin_operation.
Pavilion / ratings / profile-layout are separate subsystems (deferred).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_entity_store import EntityError
from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_FAQ_CREATE,
    PERM_FAQ_EDIT,
    PERM_FAQ_PUBLISH,
    PERM_FAQ_VIEW,
    PERM_GUIDES_ARCHIVE,
    PERM_GUIDES_CREATE,
    PERM_GUIDES_EDIT,
    PERM_GUIDES_PUBLISH,
    PERM_GUIDES_VIEW,
    PERM_NEWS_ARCHIVE,
    PERM_NEWS_CREATE,
    PERM_NEWS_EDIT,
    PERM_NEWS_PUBLISH,
    PERM_NEWS_VIEW,
    PERM_SITE_HOMEPAGE_EDIT,
    PERM_SITE_VIEW,
    identity_key,
    require_permission,
)
from services import site_content_registry as site


# Конфигурация прав по типу: view/create/edit/publish/archive + семья (для аудита).
_KIND_CONFIG = {
    site.KIND_NEWS: {"family": "news", "view": PERM_NEWS_VIEW, "create": PERM_NEWS_CREATE, "edit": PERM_NEWS_EDIT, "publish": PERM_NEWS_PUBLISH, "archive": PERM_NEWS_ARCHIVE},
    site.KIND_GUIDE: {"family": "guides", "view": PERM_GUIDES_VIEW, "create": PERM_GUIDES_CREATE, "edit": PERM_GUIDES_EDIT, "publish": PERM_GUIDES_PUBLISH, "archive": PERM_GUIDES_ARCHIVE},
    site.KIND_FAQ: {"family": "faq", "view": PERM_FAQ_VIEW, "create": PERM_FAQ_CREATE, "edit": PERM_FAQ_EDIT, "publish": PERM_FAQ_PUBLISH, "archive": PERM_FAQ_PUBLISH},
    site.KIND_BANNER: {"family": "site", "view": PERM_SITE_VIEW, "create": PERM_SITE_HOMEPAGE_EDIT, "edit": PERM_SITE_HOMEPAGE_EDIT, "publish": PERM_SITE_HOMEPAGE_EDIT, "archive": PERM_SITE_HOMEPAGE_EDIT},
    site.KIND_ANNOUNCEMENT: {"family": "site", "view": PERM_SITE_VIEW, "create": PERM_SITE_HOMEPAGE_EDIT, "edit": PERM_SITE_HOMEPAGE_EDIT, "publish": PERM_SITE_HOMEPAGE_EDIT, "archive": PERM_SITE_HOMEPAGE_EDIT},
}


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


def _cfg(kind: str) -> dict[str, Any]:
    cfg = _KIND_CONFIG.get(kind)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Неизвестный тип контента: {kind}.")
    return cfg


def _title(data: dict[str, Any], kind: str) -> str:
    if kind == site.KIND_FAQ:
        return str(data.get("question") or "")
    return str(data.get("title") or "")


def create_admin_site_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/site", tags=["admin-site"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_SITE_VIEW)
        return {
            "ok": True,
            "kinds": list(site.KINDS),
            "statuses": [{"value": s, "label": site.STATUS_LABELS.get(s, s)} for s in site.STATUSES],
            "newsCategories": list(site.NEWS_CATEGORIES),
            "guideDifficulties": list(site.GUIDE_DIFFICULTIES),
            "bannerTypes": list(site.BANNER_TYPES),
        }

    @router.get("/{kind}")
    def list_kind(kind: str, request: Request, token: str | None = Query(default=None, min_length=16), status: str | None = None) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), _cfg(kind)["view"])
        # Все типы лежат в одном сторе; фильтруем по тегу _kind в data.
        items = [i for i in site.store().list(status=status) if (i.get("data") or {}).get("_kind") == kind]
        return {"ok": True, "items": items}

    @router.get("/{kind}/{content_id}")
    def get_one(kind: str, content_id: str, request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), _cfg(kind)["view"])
        item = site.store().get(content_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Материал не найден.")
        return {"ok": True, "item": item, "validation": site.validate(kind, item)}

    @router.post("/{kind}")
    def create(kind: str, payload: IdDataRequest, request: Request) -> dict[str, Any]:
        cfg = _cfg(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, cfg["create"])
        data = {**payload.data, "_kind": kind}
        try:
            item = run_admin_operation(
                session=session, action=f"{cfg['family']}.create",
                func=lambda: site.store().create(payload.id, data, actor=_actor(session)),
                target_type=kind, target_id=payload.id, target_name=_title(payload.data, kind),
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.put("/{kind}/{content_id}")
    def update(kind: str, content_id: str, payload: DataRequest, request: Request) -> dict[str, Any]:
        cfg = _cfg(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, cfg["edit"])
        before = site.store().get(content_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Материал не найден.")
        try:
            item = run_admin_operation(
                session=session, action=f"{cfg['family']}.edit",
                func=lambda: site.store().update(content_id, {**payload.data, "_kind": kind}, actor=_actor(session)),
                target_type=kind, target_id=content_id,
                target_name=_title(before.get("data", {}), kind),
                before={"version": before.get("version")},
                after_func=lambda r: {"version": r.get("version")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{kind}/{content_id}/validate")
    def validate_one(kind: str, content_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        cfg = _cfg(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, cfg["edit"])
        item = site.store().get(content_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Материал не найден.")
        result = site.validate(kind, item)
        record_admin_operation(
            session=session, action=f"{cfg['family']}.validate", target_type=kind,
            target_id=content_id, after={"ok": result["ok"], "errors": len(result["errors"])},
            reason=payload.reason,
        )
        return {"ok": True, "validation": result}

    @router.post("/{kind}/{content_id}/publish")
    def publish(kind: str, content_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        cfg = _cfg(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, cfg["publish"])
        before = site.store().get(content_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Материал не найден.")
        result = site.validate(kind, before)
        if not result["ok"]:
            try:
                site.store().set_status(content_id, site.STATUS_ERROR, actor=_actor(session), force=True)
            except EntityError:
                pass
            record_admin_operation(
                session=session, action=f"{cfg['family']}.publish", target_type=kind,
                target_id=content_id, status="error", error="; ".join(result["errors"]),
                reason=payload.reason,
            )
            raise HTTPException(status_code=400, detail="Проверка не пройдена: " + "; ".join(result["errors"]))

        def _publish() -> dict[str, Any]:
            if before.get("status") not in (site.STATUS_READY, site.STATUS_HIDDEN, site.STATUS_SCHEDULED):
                site.store().set_status(content_id, site.STATUS_READY, actor=_actor(session), force=True)
            return site.store().set_status(content_id, site.STATUS_PUBLISHED, actor=_actor(session), force=True)

        item = run_admin_operation(
            session=session, action=f"{cfg['family']}.publish", func=_publish,
            target_type=kind, target_id=content_id, target_name=_title(before.get("data", {}), kind),
            before={"status": before.get("status")},
            after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
        )
        return {"ok": True, "item": item, "validation": result}

    def _lifecycle(kind, content_id, payload, request, *, perm_key, action_suffix, target_status):
        cfg = _cfg(kind)
        session = _session(get_storage(), request, payload.token)
        _require(session, cfg[perm_key])
        before = site.store().get(content_id)
        if before is None:
            raise HTTPException(status_code=404, detail="Материал не найден.")
        try:
            item = run_admin_operation(
                session=session, action=f"{cfg['family']}.{action_suffix}",
                func=lambda: site.store().set_status(content_id, target_status, actor=_actor(session)),
                target_type=kind, target_id=content_id, target_name=_title(before.get("data", {}), kind),
                before={"status": before.get("status")},
                after_func=lambda r: {"status": r.get("status")}, reason=payload.reason,
            )
        except EntityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "item": item}

    @router.post("/{kind}/{content_id}/hide")
    def hide(kind: str, content_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(kind, content_id, payload, request, perm_key="publish", action_suffix="hide", target_status=site.STATUS_HIDDEN)

    @router.post("/{kind}/{content_id}/archive")
    def archive(kind: str, content_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(kind, content_id, payload, request, perm_key="archive", action_suffix="archive", target_status=site.STATUS_ARCHIVE)

    @router.post("/{kind}/{content_id}/schedule")
    def schedule(kind: str, content_id: str, payload: ActionRequest, request: Request) -> dict[str, Any]:
        return _lifecycle(kind, content_id, payload, request, perm_key="edit", action_suffix="schedule", target_status=site.STATUS_SCHEDULED)

    return router
