"""FastAPI router for the Reputation constructor (item-reputation §3, эффекты §3).

CRUD/lifecycle/versioning via the shared factory; adds a consequences preview
endpoint (§3.12). Guarded by reputation.* permissions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import reputation_constructor_service as svc
from services.admin_constructor_factory import create_entity_constructor_router
from services.admin_panel_service import require_admin_session
from services.admin_operation import record_admin_operation
from services import reputation_runtime_service as runtime
from services.admin_rbac import (
    PERM_REPUTATION_ARCHIVE, PERM_REPUTATION_CREATE, PERM_REPUTATION_DELETE,
    PERM_REPUTATION_DISABLE, PERM_REPUTATION_EDIT, PERM_REPUTATION_PUBLISH,
    PERM_REPUTATION_VALIDATE, PERM_REPUTATION_VIEW, require_permission,
)

_PERMS = {
    "view": PERM_REPUTATION_VIEW, "create": PERM_REPUTATION_CREATE, "edit": PERM_REPUTATION_EDIT,
    "validate": PERM_REPUTATION_VALIDATE, "publish": PERM_REPUTATION_PUBLISH,
    "disable": PERM_REPUTATION_DISABLE, "archive": PERM_REPUTATION_ARCHIVE,
    "delete": PERM_REPUTATION_DELETE,
}


def _meta_extra(_svc: Any) -> dict[str, Any]:
    return {
        "visibility": [{"value": v, "label": svc.VISIBILITY_LABELS.get(v, v)} for v in svc.VISIBILITY],
        "reputationTypes": list(svc.REPUTATION_TYPES),
        "scopeTypes": list(svc.SCOPE_TYPES),
        "displayModes": list(svc.DISPLAY_MODES),
        "changeTriggers": list(svc.CHANGE_TRIGGERS),
        "accessTypes": list(svc.ACCESS_TYPES),
        "decayDirections": list(svc.DECAY_DIRECTIONS),
    }


class _PreviewBody(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    value: float | None = None
    delta: float = 0
class _PlayerChangeBody(BaseModel):
    token:str|None=Field(default=None,min_length=16);delta:float;reason:str=Field(min_length=1);source_id:str=""


def _bearer(request: Request | None) -> str:
    if request is None:
        return ""
    authorization = str(request.headers.get("authorization") or "").strip()
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.casefold() == "bearer" and value.strip() else ""


def create_admin_reputation_router(get_storage) -> APIRouter:
    router = create_entity_constructor_router(
        get_storage=get_storage,
        prefix="/api/admin/v2/reputations",
        tags=["admin-reputations"],
        svc=svc,
        perms=_PERMS,
        target_type="reputation",
        name_field="name_ru",
        not_found="Репутация не найдена.",
        meta_extra=_meta_extra,
    )

    def _guard(request: Request, token: str | None, permission: str = PERM_REPUTATION_VIEW) -> dict[str,Any]:
        effective = _bearer(request) or str(token or "").strip()
        if not effective:
            raise HTTPException(status_code=401, detail="Админ-сессия не передана.")
        try:
            session = require_admin_session(get_storage(), effective)
            require_permission(session, permission);return session
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.post("/{reputation_id}/preview")
    def preview(reputation_id: str, payload: _PreviewBody, request: Request) -> dict[str, Any]:
        _guard(request, payload.token)
        item = svc.store().get(reputation_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Репутация не найдена.")
        return {"ok": True, "preview": svc.preview(item.get("data") or {}, payload.value, payload.delta)}

    @router.get("/{reputation_id}/player-history")
    def history(reputation_id:str,request:Request,token:str|None=None)->dict[str,Any]:
        _guard(request,token);rows=[];storage=get_storage()
        for audience in storage.list_player_audience_rows() if hasattr(storage,"list_player_audience_rows") else []:
            gid=str(audience.get("game_id") or "");player=storage.get_player_by_game_id(gid)
            for row in (player or {}).get("reputation_history") or []:
                if isinstance(row,dict) and str(row.get("reputation_id"))==reputation_id:rows.append({"game_id":gid,**row})
        rows.sort(key=lambda x:str(x.get("at") or ""),reverse=True);return {"ok":True,"history":rows[:1000]}

    @router.post("/{reputation_id}/players/{game_id}/change")
    def change_player(reputation_id:str,game_id:str,payload:_PlayerChangeBody,request:Request)->dict[str,Any]:
        session=_guard(request,payload.token,PERM_REPUTATION_EDIT);storage=get_storage();player=storage.get_player_by_game_id(game_id)
        if not isinstance(player,dict):raise HTTPException(status_code=404,detail="Игрок не найден.")
        try:row=runtime.change(player,reputation_id,payload.delta,source="admin",source_id=payload.source_id,reason=payload.reason,admin=str(session.get("identity") or session.get("admin_id") or "admin"))
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
        storage.update_player(player);record_admin_operation(session=session,action="reputation.player_change",target_type="reputation",target_id=reputation_id,reason=payload.reason,details={"game_id":game_id,"delta":payload.delta,"new_value":row.get("new_value")});return {"ok":True,"change":row}

    return router
