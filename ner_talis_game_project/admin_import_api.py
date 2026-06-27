"""FastAPI router for Admin V2 unified import-migration (ТЗ «импорт в админку»).

Mounted under ``/api/admin/v2/import``. Triggers the constructor import-migration
for existing game data (items/mobs/effects/skills/locations/events/city nodes),
with re-import modes and a detailed report, and runs the post-import integrity
check. Bulk import publishes content into the live constructors, so it requires a
publish-level permission (world.publish) and is fully audited; the check is
read-only (world.view).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_operation import record_admin_operation, run_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    PERM_WORLD_PUBLISH,
    PERM_WORLD_VIEW,
    identity_key,
    require_permission,
)
from services import constructor_import as ci


class ImportRunRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    kinds: list[str] = Field(default_factory=list)
    mode: str = "new"
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


def create_admin_import_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2/import", tags=["admin-import"])

    @router.get("/meta")
    def meta(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_WORLD_VIEW)
        return {
            "ok": True,
            "kinds": list(ci.IMPORTERS.keys()),
            "modes": [{"value": m, "label": ci.MODE_LABELS.get(m, m)} for m in ci.IMPORT_MODES],
            "supportsDryRun": True,
            "reportFormats": ["json", "md"],
        }

    @router.post("/dry-run")
    def dry_run(payload: ImportRunRequest, request: Request) -> dict[str, Any]:
        # Dry-run ничего не пишет (ТЗ §3.3, §16) → достаточно права просмотра.
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_WORLD_VIEW)
        requested = list(payload.kinds or [])
        kinds = [k for k in requested if k in ci.IMPORTERS]
        if requested and not kinds:
            raise HTTPException(status_code=400, detail="Неизвестные типы импорта: " + ", ".join(requested))
        result = ci.import_all(kinds or None, mode=payload.mode, actor=_actor(session), dry_run=True)
        record_admin_operation(
            session=session, action="import.dry_run", target_type="constructor_import",
            target_id=",".join(kinds or list(ci.IMPORTERS.keys())),
            after=result.get("summary"), reason=payload.reason,
        )
        return result

    @router.get("/report")
    def report(request: Request, token: str | None = Query(default=None, min_length=16),
               format: str = Query(default="json")) -> dict[str, Any]:
        _require(_session(get_storage(), request, token), PERM_WORLD_VIEW)
        last = ci.load_last_report()
        if str(format).lower() in ("md", "markdown"):
            return {"ok": True, "format": "md", "content": ci.build_import_markdown(last)}
        return {"ok": True, "format": "json", "content": last}

    @router.post("/run")
    def run(payload: ImportRunRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_WORLD_PUBLISH)
        # Защита (Codex P1): если клиент прислал типы, но все они неизвестны —
        # ошибка, а не «импортировать всё». Пустой список = осознанный импорт всего.
        requested = list(payload.kinds or [])
        kinds = [k for k in requested if k in ci.IMPORTERS]
        if requested and not kinds:
            raise HTTPException(status_code=400, detail="Неизвестные типы импорта: " + ", ".join(requested))
        kinds = kinds or None
        result = run_admin_operation(
            session=session, action="import.run",
            func=lambda: ci.import_all(kinds, mode=payload.mode, actor=_actor(session)),
            target_type="constructor_import", target_id=",".join(kinds or ci.IMPORTERS.keys()),
            after_func=lambda r: r.get("summary"), reason=payload.reason,
        )
        return result

    @router.post("/rollback")
    def rollback(payload: ActionRequest, request: Request) -> dict[str, Any]:
        # Откат удаляет записи из живых конструкторов → publish-level, опасное.
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_WORLD_PUBLISH)
        result = run_admin_operation(
            session=session, action="import.rollback",
            func=lambda: ci.rollback_last(actor=_actor(session)),
            target_type="constructor_import", target_id="last",
            after_func=lambda r: {"deleted": r.get("deleted"), "kept": r.get("kept")},
            reason=payload.reason,
        )
        return result

    @router.post("/check")
    def check(payload: ActionRequest, request: Request) -> dict[str, Any]:
        session = _session(get_storage(), request, payload.token)
        _require(session, PERM_WORLD_VIEW)
        report = ci.check_import()
        record_admin_operation(
            session=session, action="import.check", target_type="constructor_import",
            target_id="all", after={"ok": report["ok"], "issues": report["count"]},
            reason=payload.reason,
        )
        return {"ok": True, "report": report}

    return router
