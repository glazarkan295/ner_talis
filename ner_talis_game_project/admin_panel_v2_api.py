"""FastAPI router for Admin Panel V2 (RBAC-aware, audited).

Phase P0: identity/permissions (`/me`), audit viewer (`/audit`) and role
management (`/roles`). Runs in parallel with the V1 router under
``/api/admin/v2`` — the existing panel is untouched. Every mutating endpoint
checks a permission via admin_rbac and records an admin_operation in the audit.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.admin_audit import read_admin_audit_records
from services.admin_operation import record_admin_operation
from services.admin_panel_service import require_admin_session
from services.admin_rbac import (
    ALL_PERMISSIONS,
    DANGEROUS_ACTIONS,
    OWNER,
    PERM_AUDIT_VIEW,
    PERM_ROLES_MANAGE,
    PERM_SYSTEM_MANAGE,
    PERM_SYSTEM_VIEW,
    ROLE_LABELS,
    ROLES,
    get_role_overrides,
    identity_key,
    normalize_role,
    permissions_for,
    remove_role_override,
    require_permission,
    resolve_admin_role,
    role_for_session,
    set_role_override,
)


class RoleAssignRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    platform: str
    admin_user_id: str
    role: str
    reason: str = ""


class SessionRevokeRequest(BaseModel):
    token: str | None = Field(default=None, min_length=16)
    id: str = Field(min_length=4)
    reason: str = ""


def _session_token_id(token: Any) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()[:16]


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


def _permission_catalog() -> dict[str, list[str]]:
    return {role: sorted(permissions_for(role)) for role in ROLES}


def create_admin_panel_v2_router(get_storage) -> APIRouter:
    router = APIRouter(prefix="/api/admin/v2", tags=["admin-panel-v2"])

    @router.get("/me")
    def get_me(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        role = role_for_session(session)
        return {
            "ok": True,
            "admin_user_id": str(session.get("admin_user_id") or ""),
            "platform": session.get("platform"),
            "role": role,
            "roleLabel": ROLE_LABELS.get(role, role),
            "isOwner": role == OWNER,
            "permissions": sorted(permissions_for(role)),
            "sessionExpiresAt": session.get("expires_at"),
        }

    @router.get("/audit")
    def get_audit(
        request: Request,
        token: str | None = Query(default=None, min_length=16),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        since: str | None = None,
        until: str | None = None,
        admin_user_id: str | None = None,
        role: str | None = None,
        action: str | None = None,
        action_prefix: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        dangerous_only: bool = False,
        errors_only: bool = False,
    ) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_AUDIT_VIEW)
        records = read_admin_audit_records(
            limit=limit,
            offset=offset,
            since=since,
            until=until,
            admin_user_id=admin_user_id,
            role=role,
            action=action,
            action_prefix=action_prefix,
            target_type=target_type,
            target_id=target_id,
            dangerous_actions=DANGEROUS_ACTIONS,
            dangerous_only=dangerous_only,
            errors_only=errors_only,
        )
        return {"ok": True, "records": records, "limit": limit, "offset": offset}

    @router.get("/roles")
    def get_roles(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_ROLES_MANAGE)
        overrides = get_role_overrides()
        return {
            "ok": True,
            "roles": [{"role": r, "label": ROLE_LABELS.get(r, r)} for r in ROLES],
            "permissions": list(ALL_PERMISSIONS),
            "matrix": _permission_catalog(),
            "overrides": [{"key": key, "role": role} for key, role in sorted(overrides.items())],
            "dangerousActions": sorted(DANGEROUS_ACTIONS),
        }

    @router.post("/roles")
    def assign_role(payload: RoleAssignRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        actor_role = _require(session, PERM_ROLES_MANAGE)
        new_role = normalize_role(payload.role)
        if str(payload.role).strip().casefold() not in ROLES:
            raise HTTPException(status_code=400, detail="Неизвестная роль.")
        target_key = identity_key(payload.platform, payload.admin_user_id)
        actor_key = identity_key(session.get("platform"), session.get("admin_user_id"))
        # Защита от самоблокировки: owner не может понизить сам себя.
        if target_key == actor_key and actor_role == OWNER and new_role != OWNER:
            raise HTTPException(
                status_code=400,
                detail="Нельзя понизить собственную роль owner (защита от потери доступа).",
            )
        before = resolve_admin_role(payload.platform, payload.admin_user_id)
        set_role_override(payload.platform, payload.admin_user_id, new_role)
        record_admin_operation(
            session=session,
            action="roles.change",
            target_type="admin",
            target_id=target_key,
            target_name=str(payload.admin_user_id),
            before={"role": before},
            after={"role": new_role},
            reason=payload.reason,
        )
        return {"ok": True, "key": target_key, "role": new_role}

    @router.delete("/roles")
    def clear_role(
        request: Request,
        platform: str = Query(...),
        admin_user_id: str = Query(...),
        token: str | None = Query(default=None, min_length=16),
    ) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_ROLES_MANAGE)
        target_key = identity_key(platform, admin_user_id)
        before = resolve_admin_role(platform, admin_user_id)
        removed = remove_role_override(platform, admin_user_id)
        after = resolve_admin_role(platform, admin_user_id)
        record_admin_operation(
            session=session,
            action="roles.change",
            target_type="admin",
            target_id=target_key,
            target_name=str(admin_user_id),
            before={"role": before},
            after={"role": after, "override_removed": removed},
            reason="reset role override",
        )
        return {"ok": True, "key": target_key, "removed": removed, "role": after}

    @router.get("/sessions")
    def get_sessions(request: Request, token: str | None = Query(default=None, min_length=16)) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, token)
        _require(session, PERM_SYSTEM_VIEW)
        current = _bearer_token(request) or str(token or "")
        raw = storage.list_admin_panel_sessions() if hasattr(storage, "list_admin_panel_sessions") else []
        items: list[dict[str, Any]] = []
        for sess in raw:
            tok = sess.get("token") or ""
            items.append({
                "id": _session_token_id(tok),
                "platform": sess.get("platform"),
                "adminUserId": str(sess.get("admin_user_id") or ""),
                "scope": sess.get("scope"),
                "kind": sess.get("kind"),
                "role": resolve_admin_role(sess.get("platform"), sess.get("admin_user_id")),
                "createdAt": sess.get("activated_at") or sess.get("created_at"),
                "expiresAt": sess.get("expires_at"),
                "isCurrent": tok == current,
            })
        items.sort(key=lambda s: str(s.get("createdAt") or ""), reverse=True)
        return {"ok": True, "sessions": items}

    @router.post("/sessions/revoke")
    def revoke_session(payload: SessionRevokeRequest, request: Request) -> dict[str, Any]:
        storage = get_storage()
        session = _session(storage, request, payload.token)
        _require(session, PERM_SYSTEM_MANAGE)
        raw = storage.list_admin_panel_sessions() if hasattr(storage, "list_admin_panel_sessions") else []
        target = next((s for s in raw if _session_token_id(s.get("token") or "") == payload.id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Сессия не найдена.")
        removed = bool(storage.delete_admin_panel_session(target.get("token")))
        record_admin_operation(
            session=session,
            action="session.revoke",
            target_type="admin_session",
            target_id=payload.id,
            target_name=str(target.get("admin_user_id") or ""),
            before={"scope": target.get("scope"), "expires_at": target.get("expires_at")},
            after={"revoked": removed},
            reason=payload.reason,
        )
        return {"ok": True, "removed": removed}

    return router
